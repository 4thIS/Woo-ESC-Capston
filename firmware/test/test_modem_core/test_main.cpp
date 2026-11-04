// S7 모뎀 펌웨어 순수 로직 — v2 §4.2~4.5 를 가짜 라디오·가짜 시계로 확인한다.
#include <ArduinoJson.h>
#include <unity.h>

#include <cstring>
#include <deque>
#include <string>
#include <vector>

#include "lora_codec.h"
#include "modem_core.h"

using namespace mc;

// ---------------- 가짜 ----------------
struct FakeHost : Host {
  uint32_t now = 1000;
  std::vector<std::string> lines;
  std::vector<uint32_t> delays;
  int restarts = 0;
  uint32_t millis() override { return now; }
  void delayMs(uint32_t ms) override {
    delays.push_back(ms);
    now += ms;
  }
  uint32_t randomRange(uint32_t lo, uint32_t hi) override { return lo + (hi - lo) / 2; }
  void writeLine(const char* s) override { lines.emplace_back(s); }
  void restart() override { ++restarts; }
};

struct FakeRadio : RadioPort {
  FakeHost* host = nullptr;
  int begins = 0, applies = 0, listens = 0;
  RadioCfg last{};
  std::deque<Cad> cad;  // 비면 Free
  int scans = 0;
  std::vector<std::vector<uint8_t>> sent;
  std::vector<uint16_t> preambles;
  uint32_t airMs = 200;
  int txErr = 0;
  std::deque<RxPacket> inbox;  // receive() 가 차례로 꺼낸다
  int begin(const RadioCfg& c) override {
    ++begins;
    last = c;
    return 0;
  }
  int apply(const RadioCfg& c) override {
    ++applies;
    last = c;
    return 0;
  }
  Cad scanChannel() override {
    ++scans;
    if (cad.empty()) return Cad::Free;
    Cad c = cad.front();
    cad.pop_front();
    return c;
  }
  int transmit(const uint8_t* b, size_t n, uint16_t pre) override {
    sent.emplace_back(b, b + n);
    preambles.push_back(pre);
    host->now += airMs;
    return txErr;
  }
  void listen() override { ++listens; }
  bool receive(RxPacket& p, uint32_t timeoutMs) override {
    if (inbox.empty()) {
      host->now += timeoutMs;
      return false;
    }
    p = inbox.front();
    inbox.pop_front();
    host->now += 50;
    return true;
  }
};

static FakeHost* H;
static FakeRadio* R;
static Modem* M;

void setUp() {
  H = new FakeHost();
  R = new FakeRadio();
  R->host = H;
  M = new Modem(*R, *H, "gw-test");
}
void tearDown() {
  delete M;
  delete R;
  delete H;
}

static JsonDocument last() {
  JsonDocument d;
  TEST_ASSERT_FALSE(H->lines.empty());
  deserializeJson(d, H->lines.back());
  return d;
}

static void send(const char* s) {
  M->handleLine(s, strlen(s));
}

static std::vector<uint8_t> frame(uint8_t type, uint8_t txn, uint16_t room = 301) {
  lc::Header h{};
  h.ver = LP_PROTO_VER;
  h.netId = RP_NET_ID;
  h.type = type;
  h.bld = 'E';
  h.room = room;
  h.unit = 1;
  h.txn = txn;
  uint8_t pl[1] = {0};
  uint8_t out[64];
  size_t n = lc::encodeFrame(h, pl, type == LP_TYPE_ACK ? 1 : 0, out, sizeof out);
  TEST_ASSERT_TRUE(n > 0);
  return {out, out + n};
}

static std::string hex(const std::vector<uint8_t>& v) {
  std::string s(v.size() * 2 + 1, '\0');
  hexEncode(v.data(), v.size(), &s[0]);
  s.resize(v.size() * 2);
  return s;
}

static std::string txLine(const std::vector<uint8_t>& f, bool wake, int ackMs) {
  return std::string("{\"op\":\"tx\",\"id\":17,\"frame\":\"") + hex(f) +
         "\",\"wake\":" + (wake ? "true" : "false") + ",\"ack_ms\":" + std::to_string(ackMs) + "}";
}

static RxPacket pkt(const std::vector<uint8_t>& f, float rssi = -80, float snr = 7.5) {
  RxPacket p{};
  memcpy(p.data, f.data(), f.size());
  p.len = f.size();
  p.rssi = rssi;
  p.snr = snr;
  return p;
}

// ---------------- 도우미 ----------------
void test_wake_symbols_sf9() {
  TEST_ASSERT_EQUAL_UINT16(733, wakeSymbols(defaultCfg()));  // v2 §2: 3000 ms / 4.096 ms
}

void test_wake_symbols_follow_sf() {
  RadioCfg c = defaultCfg();
  c.sf = 10;
  TEST_ASSERT_EQUAL_UINT16(367, wakeSymbols(c));  // 3000 / 8.192 = 366.2 → 367
}

void test_validate_cfg_ranges() {
  TEST_ASSERT_NULL(validateCfg(defaultCfg()));
  RadioCfg c = defaultCfg();
  c.sf = 13;
  TEST_ASSERT_NOT_NULL(validateCfg(c));
  c = defaultCfg();
  c.power = 15;  // KR920 922.1~923.3 MHz 상한 +14 dBm
  TEST_ASSERT_NOT_NULL(validateCfg(c));
  c = defaultCfg();
  c.bw = 100;
  TEST_ASSERT_NOT_NULL(validateCfg(c));
  c = defaultCfg();
  c.freq = 930;
  TEST_ASSERT_NOT_NULL(validateCfg(c));
  c = defaultCfg();
  c.cr = 9;
  TEST_ASSERT_NOT_NULL(validateCfg(c));
}

void test_hex_roundtrip_and_errors() {
  uint8_t b[4];
  TEST_ASSERT_EQUAL_INT(3, hexDecode("0a FF 10", b, sizeof b));
  TEST_ASSERT_EQUAL_HEX8(0xff, b[1]);
  TEST_ASSERT_EQUAL_INT(-1, hexDecode("abc", b, sizeof b));         // 홀수
  TEST_ASSERT_EQUAL_INT(-1, hexDecode("0102030405", b, sizeof b));  // 넘침
  hexDecode("0aff10", b, sizeof b);                                 // 넘친 디코드가 b 를 덮어썼으므로 다시
  char s[7];
  hexEncode(b, 3, s);
  TEST_ASSERT_EQUAL_STRING("0aff10", s);
}

// ---------------- §4.3 기본 ----------------
void test_boot_emits_ready() {
  M->boot();
  JsonDocument d = last();
  TEST_ASSERT_EQUAL_STRING("ready", d["op"]);
  TEST_ASSERT_EQUAL_STRING("gw-test", d["fw"]);
  TEST_ASSERT_EQUAL_INT(9, d["sf"]);
  TEST_ASSERT_EQUAL_FLOAT(922.5f, d["freq"].as<float>());
  TEST_ASSERT_EQUAL_INT(1, R->begins);
}

void test_ping_pong() {
  M->boot();
  H->now = 12345000;
  send("{\"op\":\"ping\"}");
  JsonDocument d = last();
  TEST_ASSERT_EQUAL_STRING("pong", d["op"]);
  TEST_ASSERT_EQUAL_INT(12345, d["uptime_s"]);
}

void test_bad_lines_log_warn() {
  M->boot();
  send("not json");
  TEST_ASSERT_EQUAL_STRING("warn", last()["level"]);
  send("{\"op\":\"dance\"}");
  TEST_ASSERT_EQUAL_STRING("log", last()["op"]);
  std::string big(1100, 'x');
  M->handleLine(big.c_str(), big.size());
  TEST_ASSERT_EQUAL_STRING("warn", last()["level"]);
}

void test_reset_restarts() {
  M->boot();
  send("{\"op\":\"reset\"}");
  TEST_ASSERT_EQUAL_INT(1, H->restarts);
}

// ---------------- §4.4 tx ----------------
void test_tx_bad_crc() {
  M->boot();
  auto f = frame(LP_TYPE_TIME, 0);
  f.back() ^= 0xff;
  send(txLine(f, false, 0).c_str());
  JsonDocument d = last();
  TEST_ASSERT_EQUAL_STRING("tx_done", d["op"]);
  TEST_ASSERT_EQUAL_INT(17, d["id"]);
  TEST_ASSERT_EQUAL_STRING("error", d["status"]);
  TEST_ASSERT_EQUAL_STRING("bad_crc8", d["reason"]);
  TEST_ASSERT_TRUE(R->sent.empty());
}

void test_tx_no_ack_wait_is_sent() {
  M->boot();
  send(txLine(frame(LP_TYPE_TIME, 0), false, 0).c_str());
  JsonDocument d = last();
  TEST_ASSERT_EQUAL_STRING("sent", d["status"]);
  TEST_ASSERT_EQUAL_INT(200, d["air_ms"]);
  TEST_ASSERT_EQUAL_UINT16(RP_PREAMBLE_NORMAL, R->preambles.back());
}

void test_tx_wake_uses_long_preamble() {
  M->boot();
  send(txLine(frame(LP_TYPE_TIME, 0), true, 0).c_str());
  TEST_ASSERT_EQUAL_UINT16(733, R->preambles.back());
}

void test_tx_acked() {
  M->boot();
  auto f = frame(LP_TYPE_SLOT_SET, 7);
  auto ack = frame(LP_TYPE_ACK, 7);
  R->inbox.push_back(pkt(ack, -61, 10.5));
  send(txLine(f, true, 3000).c_str());
  JsonDocument d = last();
  TEST_ASSERT_EQUAL_STRING("acked", d["status"]);
  TEST_ASSERT_EQUAL_FLOAT(-61, d["rssi"].as<float>());
  TEST_ASSERT_EQUAL_FLOAT(10.5f, d["snr"].as<float>());
  TEST_ASSERT_EQUAL_STRING(hex(ack).c_str(), d["ack"]);
  TEST_ASSERT_EQUAL_INT(1, M->stats().acked);
}

void test_tx_foreign_frame_goes_up_as_rx_then_acked() {
  M->boot();
  R->inbox.push_back(pkt(frame(LP_TYPE_ACK, 9)));       // 다른 TXN
  R->inbox.push_back(pkt(frame(LP_TYPE_ACK, 7, 302)));  // 다른 방
  R->inbox.push_back(pkt(frame(LP_TYPE_ACK, 7)));
  send(txLine(frame(LP_TYPE_SLOT_SET, 7), false, 3000).c_str());
  TEST_ASSERT_EQUAL_INT(3, (int)H->lines.size() - 1);  // ready 뒤 rx 2 + tx_done
  JsonDocument r;
  deserializeJson(r, H->lines[1]);
  TEST_ASSERT_EQUAL_STRING("rx", r["op"]);
  TEST_ASSERT_EQUAL_STRING("acked", last()["status"]);
}

void test_tx_no_ack() {
  M->boot();
  send(txLine(frame(LP_TYPE_SLOT_SET, 7), false, 3000).c_str());
  TEST_ASSERT_EQUAL_STRING("no_ack", last()["status"]);
  TEST_ASSERT_EQUAL_INT(1, M->stats().noAck);
}

void test_cad_busy_gives_up_after_max_tries() {
  M->boot();
  for (int i = 0; i < 10; ++i) R->cad.push_back(Cad::Busy);
  send(txLine(frame(LP_TYPE_SLOT_SET, 7), false, 3000).c_str());
  JsonDocument d = last();
  TEST_ASSERT_EQUAL_STRING("cad_busy", d["status"]);
  TEST_ASSERT_EQUAL_INT(RP_CAD_MAX_TRIES, d["tries"]);
  TEST_ASSERT_TRUE(R->sent.empty());
  TEST_ASSERT_EQUAL_INT(RP_CAD_MAX_TRIES, R->scans);
  for (uint32_t ms : H->delays) {
    TEST_ASSERT_TRUE(ms >= RP_CAD_BACKOFF_MIN_MS && ms <= RP_CAD_BACKOFF_MAX_MS);
  }
  TEST_ASSERT_EQUAL_INT(1, M->stats().cadBusy);
}

void test_cad_busy_then_free_transmits() {
  M->boot();
  R->cad.push_back(Cad::Busy);
  R->cad.push_back(Cad::Busy);
  send(txLine(frame(LP_TYPE_TIME, 0), false, 0).c_str());
  TEST_ASSERT_EQUAL_STRING("sent", last()["status"]);
  TEST_ASSERT_EQUAL_INT(1, (int)R->sent.size());
  TEST_ASSERT_EQUAL_INT(3, R->scans);
}

// ---------------- cfg ----------------
void test_cfg_applies_and_changes_wake() {
  M->boot();
  send("{\"op\":\"cfg\",\"sf\":10,\"bw\":125,\"cr\":5,\"power\":14,\"freq\":922.5,\"wake_ms\":3000}");
  TEST_ASSERT_EQUAL_INT(1, R->applies);
  TEST_ASSERT_EQUAL_UINT8(10, R->last.sf);
  send(txLine(frame(LP_TYPE_TIME, 0), true, 0).c_str());
  TEST_ASSERT_EQUAL_UINT16(367, R->preambles.back());
}

void test_cfg_out_of_range_is_rejected() {
  M->boot();
  send("{\"op\":\"cfg\",\"sf\":9,\"power\":20}");
  TEST_ASSERT_EQUAL_INT(0, R->applies);
  TEST_ASSERT_EQUAL_STRING("warn", last()["level"]);
  TEST_ASSERT_EQUAL_INT8(14, M->cfg().power);
}

// ---------------- 업링크·워치독·stats ----------------
void test_poll_forwards_uplink() {
  M->boot();
  R->inbox.push_back(pkt(frame(LP_TYPE_ACK, 1), -100, 2));
  M->poll();
  JsonDocument d = last();
  TEST_ASSERT_EQUAL_STRING("rx", d["op"]);
  TEST_ASSERT_EQUAL_FLOAT(-100, d["rssi"].as<float>());
  TEST_ASSERT_EQUAL_INT(1, M->stats().rx);
}

void test_watchdog_reinits_radio_without_ping() {
  M->boot();
  H->now += 30001;
  M->poll();
  TEST_ASSERT_EQUAL_INT(2, R->begins);
  TEST_ASSERT_EQUAL_STRING("warn", last()["level"]);
}

void test_watchdog_quiet_with_regular_ping() {
  M->boot();
  for (int i = 0; i < 6; ++i) {
    H->now += 10000;
    send("{\"op\":\"ping\"}");
    M->poll();
  }
  TEST_ASSERT_EQUAL_INT(1, R->begins);
}

void test_stats_reports_counters() {
  M->boot();
  send(txLine(frame(LP_TYPE_SLOT_SET, 7), false, 3000).c_str());  // no_ack
  send("{\"op\":\"stats\"}");
  JsonDocument d = last();
  TEST_ASSERT_EQUAL_STRING("stats", d["op"]);
  TEST_ASSERT_EQUAL_INT(1, d["tx"]);
  TEST_ASSERT_EQUAL_INT(1, d["no_ack"]);
  TEST_ASSERT_EQUAL_INT(0, d["acked"]);
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_wake_symbols_sf9);
  RUN_TEST(test_wake_symbols_follow_sf);
  RUN_TEST(test_validate_cfg_ranges);
  RUN_TEST(test_hex_roundtrip_and_errors);
  RUN_TEST(test_boot_emits_ready);
  RUN_TEST(test_ping_pong);
  RUN_TEST(test_bad_lines_log_warn);
  RUN_TEST(test_reset_restarts);
  RUN_TEST(test_tx_bad_crc);
  RUN_TEST(test_tx_no_ack_wait_is_sent);
  RUN_TEST(test_tx_wake_uses_long_preamble);
  RUN_TEST(test_tx_acked);
  RUN_TEST(test_tx_foreign_frame_goes_up_as_rx_then_acked);
  RUN_TEST(test_tx_no_ack);
  RUN_TEST(test_cad_busy_gives_up_after_max_tries);
  RUN_TEST(test_cad_busy_then_free_transmits);
  RUN_TEST(test_cfg_applies_and_changes_wake);
  RUN_TEST(test_cfg_out_of_range_is_rejected);
  RUN_TEST(test_poll_forwards_uplink);
  RUN_TEST(test_watchdog_reinits_radio_without_ping);
  RUN_TEST(test_watchdog_quiet_with_regular_ping);
  RUN_TEST(test_stats_reports_counters);
  return UNITY_END();
}
