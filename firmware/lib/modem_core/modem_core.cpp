#include "modem_core.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "lora_codec.h"

namespace mc {

RadioCfg defaultCfg() {
  return RadioCfg{RP_FREQ_MHZ, RP_BW_KHZ, RP_SF, RP_CR, RP_TX_POWER_DBM, RP_PREAMBLE_WAKE_MS};
}

const char* validateCfg(const RadioCfg& c) {
  // KR920: 917.0~923.5 MHz 1채널. 922.1~923.3 MHz 출력 상한 +14 dBm(안테나 포함) — 그 위로는 받지 않는다.
  if (!(c.freq >= 917.0f && c.freq <= 923.5f)) return "freq";
  static const float kBw[] = {62.5f, 125.0f, 250.0f, 500.0f};
  bool bwOk = false;
  for (float b : kBw) bwOk = bwOk || fabsf(c.bw - b) < 0.01f;
  if (!bwOk) return "bw";
  if (c.sf < 7 || c.sf > 12) return "sf";
  if (c.cr < 5 || c.cr > 8) return "cr";
  if (c.power < -9 || c.power > 14) return "power";
  if (c.wakeMs > 10000) return "wake_ms";
  return nullptr;
}

uint16_t wakeSymbols(const RadioCfg& c) {
  float symMs = (float)(1u << c.sf) / c.bw;
  uint32_t s = (uint32_t)((float)c.wakeMs / symMs) + 1;
  return s > 65535 ? 65535 : (uint16_t)s;
}

int hexDecode(const char* s, uint8_t* out, size_t cap) {
  size_t n = 0;
  int hi = -1;
  for (; *s; ++s) {
    char c = *s;
    int v = (c >= '0' && c <= '9')   ? c - '0'
            : (c >= 'a' && c <= 'f') ? c - 'a' + 10
            : (c >= 'A' && c <= 'F') ? c - 'A' + 10
                                     : -1;
    if (v < 0) {
      if (c == ' ') continue;  // §4.2 공백 허용
      return -1;
    }
    if (hi < 0) {
      hi = v;
      continue;
    }
    if (n >= cap) return -1;
    out[n++] = (uint8_t)(hi << 4 | v);
    hi = -1;
  }
  return hi < 0 ? (int)n : -1;
}

void hexEncode(const uint8_t* b, size_t n, char* out) {
  static const char* H = "0123456789abcdef";
  for (size_t i = 0; i < n; ++i) {
    out[2 * i] = H[b[i] >> 4];
    out[2 * i + 1] = H[b[i] & 15];
  }
  out[2 * n] = '\0';
}

Modem::Modem(RadioPort& r, Host& h, const char* fw) : r_(r), h_(h), fw_(fw), cfg_(defaultCfg()) {}

void Modem::emit(JsonDocument& d) {
  static char buf[kMaxLine + 64];
  size_t n = serializeJson(d, buf, sizeof buf);
  if (n >= sizeof buf - 1) return;  // 넘치는 줄은 쓰지 않는다(rx 프레임 최대 ≈ 520 B 라 실제로는 없음)
  h_.writeLine(buf);
}

void Modem::log(const char* level, const char* msg) {
  JsonDocument d;
  d["op"] = "log";
  d["level"] = level;
  d["msg"] = msg;
  emit(d);
}

void Modem::emitRx(const RxPacket& p) {
  static char hex[sizeof p.data * 2 + 1];
  hexEncode(p.data, p.len, hex);
  JsonDocument d;
  d["op"] = "rx";
  d["rssi"] = p.rssi;
  d["snr"] = p.snr;
  d["frame"] = (const char*)hex;
  emit(d);
  ++stats_.rx;
}

void Modem::boot() {
  int st = r_.begin(cfg_);
  JsonDocument d;
  d["op"] = "ready";
  d["fw"] = fw_;
  d["sf"] = cfg_.sf;
  d["freq"] = cfg_.freq;
  if (st != 0) d["radio_err"] = st;
  emit(d);
  r_.listen();
  lastPing_ = h_.millis();
}

void Modem::handleLine(const char* line, size_t n) {
  if (n > kMaxLine) {
    log("warn", "line too long");
    return;
  }
  JsonDocument req;
  if (deserializeJson(req, line, n) || !req["op"].is<const char*>()) {
    log("warn", "parse error");
    return;
  }
  const char* op = req["op"];
  if (!strcmp(op, "ping")) {
    lastPing_ = h_.millis();
    JsonDocument d;
    d["op"] = "pong";
    d["uptime_s"] = h_.millis() / 1000;
    emit(d);
  } else if (!strcmp(op, "tx")) {
    onTx(req.as<JsonVariantConst>());
  } else if (!strcmp(op, "cfg")) {
    onCfg(req.as<JsonVariantConst>());
  } else if (!strcmp(op, "stats")) {
    JsonDocument d;
    d["op"] = "stats";
    d["tx"] = stats_.tx;
    d["acked"] = stats_.acked;
    d["no_ack"] = stats_.noAck;
    d["cad_busy"] = stats_.cadBusy;
    d["rx"] = stats_.rx;
    d["error"] = stats_.errors;
    emit(d);
  } else if (!strcmp(op, "reset")) {
    h_.restart();  // 다시 부팅하며 ready 를 보낸다
  } else {
    char m[48];
    snprintf(m, sizeof m, "unknown op %.24s", op);
    log("warn", m);
  }
}

void Modem::onCfg(JsonVariantConst req) {
  // §4.2: cfg 는 응답이 없다. 범위 밖이면 이전 값을 유지하고 log 로만 알린다.
  RadioCfg c = cfg_;
  c.sf = req["sf"] | c.sf;
  c.bw = req["bw"] | c.bw;
  c.cr = req["cr"] | c.cr;
  c.power = req["power"] | c.power;
  c.freq = req["freq"] | c.freq;
  c.wakeMs = req["wake_ms"] | c.wakeMs;
  char m[96];
  if (const char* bad = validateCfg(c)) {
    snprintf(m, sizeof m, "cfg rejected: %s out of range — keeping sf=%u power=%d", bad, cfg_.sf, cfg_.power);
    log("warn", m);
    return;
  }
  int st = r_.apply(c);
  if (st != 0) {
    snprintf(m, sizeof m, "cfg apply failed (%d) — reinit with previous", st);
    log("error", m);
    r_.begin(cfg_);
    r_.listen();
    return;
  }
  cfg_ = c;
  snprintf(m, sizeof m, "cfg sf=%u bw=%.1f cr=%u power=%d freq=%.1f wake_ms=%u", c.sf, c.bw, c.cr, c.power,
           c.freq, (unsigned)c.wakeMs);
  log("info", m);
  r_.listen();
}

void Modem::onTx(JsonVariantConst req) {
  JsonDocument res;
  res["op"] = "tx_done";
  res["id"] = req["id"];
  static uint8_t buf[256];
  int n = hexDecode(req["frame"] | "", buf, sizeof buf);
  lc::Header h{};
  const uint8_t* pl = nullptr;
  // 길이·CRC8 만 본다(§4.4 1단계). NET_ID 는 프레임에 적힌 값을 그대로 믿는다 — 해석은 호스트 몫.
  if (n <= 1 || !lc::decodeFrame(buf, (size_t)n, h, pl, buf[1])) {
    ++stats_.errors;
    res["status"] = "error";
    res["reason"] = "bad_crc8";
    emit(res);
    return;
  }
  // §4.4 2단계: CAD(LBT). busy 면 50~200 ms 쉬고 다시, RP_CAD_MAX_TRIES 번 모두 busy 면 포기.
  int tries = 0;
  for (;;) {
    Cad c = r_.scanChannel();
    if (c == Cad::Error) log("warn", "cad error — sending anyway");
    if (c != Cad::Busy) break;
    if (++tries >= RP_CAD_MAX_TRIES) {
      ++stats_.cadBusy;
      res["status"] = "cad_busy";
      res["tries"] = tries;
      emit(res);
      r_.listen();
      return;
    }
    h_.delayMs(h_.randomRange(RP_CAD_BACKOFF_MIN_MS, RP_CAD_BACKOFF_MAX_MS));
  }
  bool wake = req["wake"] | false;
  uint32_t ackMs = req["ack_ms"] | 0;
  uint32_t t0 = h_.millis();
  int st = r_.transmit(buf, (size_t)n, wake ? wakeSymbols(cfg_) : (uint16_t)RP_PREAMBLE_NORMAL);
  uint32_t airMs = h_.millis() - t0;
  ++stats_.tx;
  if (st != 0) {
    ++stats_.errors;
    res["status"] = "error";
    res["reason"] = "tx_fail";
    emit(res);
    r_.listen();
    return;
  }
  res["air_ms"] = airMs;
  if (ackMs == 0) {
    res["status"] = "sent";
    emit(res);
    r_.listen();
    return;
  }
  r_.listen();
  uint32_t deadline = h_.millis() + ackMs;
  static RxPacket p;
  while ((int32_t)(deadline - h_.millis()) > 0) {
    if (!r_.receive(p, deadline - h_.millis())) break;
    lc::Header ah{};
    const uint8_t* ap = nullptr;
    if (lc::decodeFrame(p.data, p.len, ah, ap, h.netId) && lc::matchesAck(h, ah)) {
      static char hex[sizeof p.data * 2 + 1];
      hexEncode(p.data, p.len, hex);
      ++stats_.acked;
      res["status"] = "acked";
      res["rssi"] = p.rssi;
      res["snr"] = p.snr;
      res["ack"] = (const char*)hex;
      emit(res);
      return;
    }
    emitRx(p);  // 짝이 아닌 프레임은 업링크로 넘기고 계속 기다린다
  }
  ++stats_.noAck;
  res["status"] = "no_ack";
  emit(res);
}

void Modem::poll() {
  static RxPacket p;
  if (r_.receive(p, 0)) emitRx(p);
  if (h_.millis() - lastPing_ > kWatchdogMs) {
    log("warn", "no host ping for 30 s — radio reinit");
    int st = r_.begin(cfg_);
    if (st != 0) {
      char m[48];
      snprintf(m, sizeof m, "radio reinit failed (%d)", st);
      log("error", m);
    }
    r_.listen();
    lastPing_ = h_.millis();
  }
}

}  // namespace mc
