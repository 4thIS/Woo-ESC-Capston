// S8 노드 펌웨어 — 깨어 있는 모드(NODE_SLEEP_MODE 없음, USB 전원 시연용). 로직은 lib/node_core(nc::*), 여기는
// 어댑터만.
//  - 무선: SX1262 DIO1 인터럽트 송수신(2026-10-21 교훈). ACK 는 저장 직후·렌더 전에(v2 §6.4), 송신 전 CAD
//  1회(§6.8)
//  - 저장: ns::NodeStore(NVS 버전·LittleFS 레코드·RTC 캐시) + sch:: 판정. 어댑터는 esp_store.h
//  - 화면: renderLayout(dh, #89) + RenderModel(계약 ④). 패널 리프레시(약 27 s) 동안에도 busy 콜백에서
//  수신·ACK
//  - 정체성: NVS(관리자 웹 배정 → SET_ROOM). 없으면 설정 대기 화면 + HELLO. 빌드 플래그 NODE_ROOM 을 주면 그
//  방으로 강제
//  - CMD·PRG 버튼(짧게 = 다시 그리기 + STATUS, 5 s = 공장 초기화) — 절전 2단계
//  - 시계: TIME 으로 맞춘다. 시계가 무효면 그리지 않는다 — e-Paper 는 마지막 화면을 그대로 둔다(§5.2)
//  - STATUS(부팅·하루 1회·요청)·배터리 실측 — 절전 1단계
//  - 절전: NODE_SLEEP_MODE=1 이면 light sleep, 2 면 deep sleep(할 일이 없을 때). 무선은 수신 duty cycle(절전
//  3단계)
#include <Arduino.h>
#include <GxEPD2_3C.h>
#include <LittleFS.h>
#include <RadioLib.h>
#include <SPI.h>
#include <WiFi.h>
#include <driver/gpio.h>
#include <driver/rtc_io.h>
#include <esp_private/esp_clk.h>
#include <esp_random.h>
#include <esp_sleep.h>
#include <esp_timer.h>
#include <sys/time.h>

#include <type_traits>

#include "esp_store.h"
#include "kst_time.h"
#include "lora_codec.h"
#include "node_core.h"
#include "node_store.h"
#include "render.h"
#include "render_model.h"
#include "schedule.h"

#ifndef NODE_BLD
#define NODE_BLD 'E'
#endif
#ifndef NODE_UNIT
#define NODE_UNIT 1
#endif
#ifndef NODE_SLEEP_MODE
#define NODE_SLEEP_MODE 0  // 0 = 깨어 있음(시연), 1 = LIGHT(v2 §6.7 1단계 검증), 2 = DEEP(운영)
#endif

namespace {

constexpr uint8_t FW_VER = 6;
// 배터리(Heltec V3.2): GPIO37 HIGH 로 분압(390 k/100 k)을 켜고 GPIO1 을 잰다(2026-11-17 실기 확인, 3.5~4.0
// V). V3.0/3.1 보드는 극성이 반대(LOW)라 이 값으로는 0 근처가 나온다
constexpr int VBAT_ADC = 1, VBAT_CTRL = 37;
constexpr uint8_t VBAT_CTRL_ON = HIGH;
constexpr float VBAT_DIVIDER = 4.9f;
constexpr uint32_t BATT_PERIOD_MS = 60000;
constexpr uint32_t QUIET_MS_DEFAULT =
    8000;                      // 마지막 수신 뒤 이만큼 조용하면 그린다(웨이크 프리앰블 3 s 보다 길게)
constexpr int BUTTON_PIN = 0;  // PRG 버튼, 눌림 LOW

constexpr int LORA_NSS = 8, LORA_SCK = 9, LORA_MOSI = 10, LORA_MISO = 11;
constexpr int LORA_RST = 12, LORA_BUSY = 13, LORA_DIO1 = 14;
constexpr int EPD_SCK = 5, EPD_MOSI = 6, EPD_CS = 7, EPD_DC = 4, EPD_RST = 3, EPD_BUSY = 2;
constexpr int VEXT_CTRL = 36;  // LOW = Vext(패널 3.3 V) 켜짐

SX1262 radio = new Module(LORA_NSS, LORA_DIO1, LORA_RST, LORA_BUSY);
volatile bool g_irq = false;
void IRAM_ATTR onDio1() {
  g_irq = true;
}

// GxEPD2 Z08 초기화에는 승압 소프트스타트(0x06, BTST)가 없다. Good Display GDEY075Z08 은 기본값으로도
// 그려지지만, Waveshare 7.5" (B)(SKU 13380) 은 승압이 서지 않아 리프레시가 ~1 s 만에 끝나고 화면이 그대로다
// (2026-11-04 2번 노드 실측: 1.1 s → 0x06 추가 시 17.9 s). 제조사 예제 값(17 17 28 17)을 POWER ON 전에
// 넣는다.
class EpdZ08 : public GxEPD2_750c_Z08 {
 public:
  using GxEPD2_750c_Z08::GxEPD2_750c_Z08;
  // init() 의 하드웨어 리셋 뒤, 첫 POWER ON(0x04) 전에 부른다. 레지스터는 다음 리셋까지 유지된다.
  void boosterSoftStart() {
    _writeCommand(0x06);
    _writeData(0x17);
    _writeData(0x17);
    _writeData(0x28);
    _writeData(0x17);
  }
};

SPIClass epdSpi(HSPI);
GxEPD2_3C<EpdZ08, EpdZ08::HEIGHT / 2> display(EpdZ08(EPD_CS, EPD_DC, EPD_RST, EPD_BUSY));

// 딥슬립 깨어남에서만 산다. 0 초기화 RTC_DATA_ATTR 은 .rtc.bss 라 딥슬립 외 리셋(esp_restart·WDT·패닉·전원)
// 에서는 지워지고, rtcValid 가 거짓이라 load() 가 NVS·LittleFS 에서 재구축한다.
RTC_DATA_ATTR ns::RtcState g_rtc;
EspKv g_kv;
LittleFsFiles g_fs;
ns::NodeStore g_store(g_kv, g_fs, g_rtc);
nc::FileRx g_file;
uint8_t g_layout = LP_LAYOUT_EMPTY;  // 마지막으로 그린 화면(ACK 에 싣는다)
bool g_dirty = true;
uint32_t g_lastRxMs = 0;
uint16_t g_battMv = 0;  // 0 = 아직 못 잼
int8_t g_rssiLast = 0;  // 마지막으로 받은 내 프레임
int8_t g_snrX4 = 0;
uint32_t g_macHash = 0;  // 노드마다 다른 값 — 부팅 직후 esp_random 은 RF 를 안 켜면 노드끼리 같은 값이 나온다
uint32_t g_spread = 0;   // 하루 STATUS 분산(초) = hash(mac) % 1800
nc::StatusPlan g_status;
uint8_t g_mac[6] = {};
uint32_t g_quietMs = QUIET_MS_DEFAULT;      // SET_PARAM 2 sessionWindowMs
uint8_t g_statusHour = nc::kStatusHourUtc;  // SET_PARAM 1 statusHourUtc
bool g_forceRender = false;                 // CMD FORCE_RENDER·버튼 — 같은 화면이어도 한 번 그린다
uint8_t g_testLayout = 0;                   // CMD TEST_RENDER — 다음 렌더 한 번 이 레이아웃으로
nc::Button g_button;
RenderModel g_shown{};  // 마지막으로 그린 화면
bool g_shownValid = false;

// StatusPlan 의 시간 기준(ms). DEEP 은 깰 때마다 millis 가 0 으로 돌아가므로 딥슬립에도 이어지는 RTC 시간을
// 쓴다
uint32_t nowMs() {
#if NODE_SLEEP_MODE == 2
  return (uint32_t)(esp_clk_rtc_time() / 1000ULL);
#else
  return millis();
#endif
}

#if NODE_SLEEP_MODE == 2
// 딥슬립을 건너 남겨야 하는 런타임 상태(RAM 은 깰 때마다 지워진다). 저장 데이터는 g_rtc(RtcState)에 따로 있다
struct WakeState {
  uint32_t magic;
  nc::StatusPlan status;
  RenderModel shown;
  bool shownValid;
  uint8_t layout;
  int8_t rssiLast, snrX4;
};
constexpr uint32_t kWakeMagic = 0x57414B33u;  // 'WAK3'
// 원시 바이트로 둔다 — StatusPlan 에 기본 생성자가 있어 객체로 두면 깰 때마다 전역 생성자가 내용을 지운다
RTC_NOINIT_ATTR alignas(4) uint8_t g_wakeRaw[sizeof(WakeState)];
static_assert(std::is_trivially_copyable<WakeState>::value, "WakeState 는 memcpy 로 옮긴다");
#endif

nc::Ident me() {
  return nc::Ident(g_rtc.bld, g_rtc.room, g_rtc.unit, g_rtc.provisioned != 0, g_mac);
}

// SET_PARAM 으로 저장한 값(없으면 기본값)
void loadParams() {
  uint32_t v = 0;
  g_statusHour = g_store.param(1, v) && v < 24 ? (uint8_t)v : nc::kStatusHourUtc;
  g_quietMs = g_store.param(2, v) && v >= 2000 && v <= 60000 ? v : QUIET_MS_DEFAULT;
}

// ACK 를 보낸 뒤 실행 — 서버가 결과를 받게
[[noreturn]] void restartAfterAck(bool reset) {
  delay(500);
  if (reset) {
    Serial.println("[node] 공장 초기화");
    (void)g_store.factoryReset();
  }
  Serial.println("[node] 재시작");
  Serial.flush();
  esp_restart();
  while (true) {
  }
}

bool clockValid() {
  return (uint32_t)time(nullptr) > nc::kClockValidEpoch;
}

// 시계가 유효하면 RTC 의 오늘 슬롯이 오늘 요일 것인지 맞추고, 지난 예약을 정리한다. TIME 수신·매초 루프에서
// 부른다. refreshDay 가 실패하면 60 s 뒤에야 다시 시도하고, 성공했을 때만 다시 그리게 표시한다.
void syncDay() {
  if (!clockValid()) return;
  const uint32_t now = (uint32_t)time(nullptr);
  const uint8_t wd = sch::toKst(now).weekday;
  if (g_rtc.slotsDay == wd) return;
  // 읽기 실패로 slotsDay 가 그대로면 매초 다시 시도하며 패널을 연달아 다시 그리게 된다 — 실패 뒤엔 60 s
  // 마다만
  static bool failed = false;
  static uint32_t failedAtMs = 0;
  if (failed && millis() - failedAtMs < 60000) return;
  const ns::StoreStatus s = g_store.refreshDay(wd);
  Serial.printf("[node] 요일 %u 슬롯 다시 채움 st=%u n=%u\n", wd, (unsigned)s, g_rtc.nSlots);
  if (s != ns::StoreStatus::Ok) {
    failed = true;
    failedAtMs = millis();
    return;
  }
  failed = false;
  (void)g_store.purgePast(nc::todayOf(now), true);
  g_dirty = true;
}

// ---------------- 무선 ----------------
bool waitIrq(uint32_t ms) {
  uint32_t t0 = millis();
  while (!g_irq) {
    if (millis() - t0 >= ms) return false;
    delay(1);
  }
  g_irq = false;
  return true;
}

// 수신 쪽 프리앰블 길이 — 웨이크 프레임(≈3 s, SF9 733 심볼)을 받으려면 수신기 설정도 그만큼 길어야 한다.
// 8 로 두면 깨어 있는 노드가 웨이크 프레임을 절반쯤 놓쳤다(2026-11-04 실측: wake 7/10, normal 20/20).
constexpr uint16_t RX_PREAMBLE_SYM = (uint16_t)(RP_PREAMBLE_WAKE_MS / ((float)(1u << RP_SF) / RP_BW_KHZ)) + 1;

void listen() {
  g_irq = false;
  radio.standby();
  radio.setPreambleLength(RX_PREAMBLE_SYM);
  int st = radio.startReceive();
  if (st != RADIOLIB_ERR_NONE) Serial.printf("[node] startReceive 실패 %d\n", st);
}

int radioBegin() {
  SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_NSS);
  int st = radio.begin(RP_FREQ_MHZ, RP_BW_KHZ, RP_SF, RP_CR, RP_SYNC_WORD, RP_TX_POWER_DBM,
                       RP_PREAMBLE_NORMAL, 1.8f);
  if (st != RADIOLIB_ERR_NONE) return st;
  radio.setDio2AsRfSwitch(true);
  radio.setCRC(RP_HW_CRC);
  radio.setDio1Action(onDio1);
  return 0;
}

// §6.8: 송신 전 CAD 1회, busy 면 30~120 ms 쉬고 1회 더, 그래도 busy 면 포기(백엔드가 재시도한다)
bool channelFree() {
  for (int i = 0; i < 2; ++i) {
    radio.standby();
    int st = radio.scanChannel();
    g_irq = false;
    if (st != RADIOLIB_LORA_DETECTED) return true;
    if (i == 0) delay(30 + esp_random() % 91);
  }
  return false;
}

uint16_t readBattMv() {
  pinMode(VBAT_CTRL, OUTPUT);
  digitalWrite(VBAT_CTRL, VBAT_CTRL_ON);
  delay(10);
  uint32_t sum = 0;
  for (int i = 0; i < 8; ++i) sum += analogReadMilliVolts(VBAT_ADC);
  digitalWrite(VBAT_CTRL, VBAT_CTRL_ON == HIGH ? LOW : HIGH);
  return (uint16_t)(sum / 8 * VBAT_DIVIDER);
}

// §6.8 업링크 송신(ACK·STATUS 공용). 채널이 바쁘면 false
bool txUplink(const lc::Header& h, const uint8_t* pl, size_t pn, const char* what) {
  uint8_t out[64];
  size_t n = lc::encodeFrame(h, pl, (uint8_t)pn, out, sizeof out);
  delay(20);  // 모뎀이 송신 → 수신으로 넘어갈 틈
  if (!channelFree()) {
    Serial.printf("[node] %s 포기 — 채널 사용 중\n", what);
    listen();
    return false;
  }
  g_irq = false;
  uint32_t t0 = millis();
  radio.setPreambleLength(RP_PREAMBLE_NORMAL);  // 업링크는 짧은 프리앰블(§6.8)
  int st = radio.startTransmit(out, n);
  bool done = st == RADIOLIB_ERR_NONE && waitIrq(2000);
  radio.finishTransmit();
  Serial.printf("[node] %s 송신 st=%d done=%d %lums\n", what, st, done, (unsigned long)(millis() - t0));
  listen();
  return done;
}

void sendAck(const lc::Header& req, uint8_t status, uint8_t detail) {
  const lc::Ack a = nc::buildAck(g_rtc, status, detail, g_battMv, FW_VER, g_layout);
  uint8_t pl[32];
  size_t pn = lc::encAck(a, pl, sizeof pl);
  lc::Header h{};
  h.ver = LP_PROTO_VER;
  h.netId = req.netId;
  h.type = LP_TYPE_ACK;
  h.bld = req.bld;
  h.room = req.room;
  h.unit = req.unit;
  h.txn = req.txn;
  (void)txUplink(h, pl, pn, "ACK");
}

bool sendStatus(uint32_t now, uint8_t& flags) {
#if NODE_SLEEP_MODE == 2
  const uint64_t up = esp_clk_rtc_time() / 3600000000ULL;  // 딥슬립에도 이어진다
#else
  const uint64_t up = (uint64_t)esp_timer_get_time() / 3600000000ULL;  // millis 는 49.7 일에 넘어간다
#endif
  const lc::Status s =
      nc::buildStatus(g_rtc, now, g_battMv, FW_VER, g_layout,
                      nc::LinkInfo{g_rssiLast, g_snrX4, (uint16_t)(up > 65535 ? 65535 : up)});
  uint8_t pl[32];
  size_t pn = lc::encStatus(s, pl, sizeof pl);
  lc::Header h{};
  h.ver = LP_PROTO_VER;
  h.netId = RP_NET_ID;
  h.type = LP_TYPE_STATUS;
  h.bld = g_rtc.bld;
  h.room = g_rtc.room;
  h.unit = g_rtc.unit;
  h.txn = 0;
  flags = s.flags;
  const bool done = txUplink(h, pl, pn, "STATUS");
  Serial.printf("[node] STATUS flags=0x%02x batt=%umV ver S%u/R%u/E%u\n", s.flags, g_battMv, g_rtc.schedVer,
                g_rtc.resvVer, g_rtc.examVer);
  return done;
}

void maybeMeasureBatt() {
  static uint32_t last = 0;
  if (g_battMv != 0 && millis() - last < BATT_PERIOD_MS) return;
  last = millis();
  g_battMv = readBattMv();
}

// 미설정 노드의 자기소개(§3.3 HELLO, 헤더 BLD/ROOM/UNIT 0·TXN 0)
bool sendHello() {
  lc::Hello hl{};
  memcpy(hl.mac, g_mac, 6);
  hl.fw = FW_VER;
  hl.battMv = g_battMv;
  uint8_t pl[16];
  const size_t pn = lc::encHello(hl, pl, sizeof pl);
  lc::Header h{};
  h.ver = LP_PROTO_VER;
  h.netId = RP_NET_ID;
  h.type = LP_TYPE_HELLO;
  return txUplink(h, pl, pn, "HELLO");
}

constexpr uint32_t HELLO_PERIOD_MS = 600000;  // 미설정이면 10 min 마다(§6.2)

void maybeSendStatus() {
  const uint32_t ms = nowMs();
  const uint32_t now = (uint32_t)time(nullptr);
  const bool clk = clockValid();
  if (!g_status.due(ms, clk, now, g_rtc.nextStatusEpoch)) return;
  if (g_irq)
    return;  // 받은 프레임이 있으면 먼저 처리 — CAD(standby)가 그 프레임을 버리지 않게, 다음 틱에 보낸다
  if (!g_rtc.provisioned) {
    const bool ok = sendHello();
    if (ok) {
      g_status.sent(ms, true, true, 0);  // 예약을 비우고
      g_status.request(ms, HELLO_PERIOD_MS);
    } else {
      g_status.sent(ms, false, false, 0);  // 채널 사용 중 — 5 s 뒤
    }
    return;
  }
  uint8_t flags = 0;
  const bool done = sendStatus(now, flags);
  g_status.sent(ms, done, clk, flags);
  if (clk) {
    // now + 30 min 기준 — 18:00:05 TIME REQUEST_STATUS 로 막 보냈으면 같은 날 18:00+분산 슬롯은 건너뛴다(하루
    // 2회 방지)
    g_rtc.nextStatusEpoch = nc::nextDailyStatus(now + nc::kStatusSpreadSec, g_statusHour, g_spread);
    ns::rtcSeal(g_rtc);
  }
}

// 받은 프레임 하나를 처리한다(저장·ACK). rs = 수신 결과(RADIOLIB_ERR_NONE 이어야 처리)
void handleRx(const uint8_t* buf, size_t len, int rs, float rssi, float snr) {
  lc::Header h{};
  const uint8_t* p = nullptr;
  bool ok = rs == RADIOLIB_ERR_NONE && lc::decodeFrame(buf, len, h, p);
  if (!ok) Serial.printf("[node] 수신 버림 rs=%d len=%u RSSI %.0f\n", rs, (unsigned)len, rssi);
  if (ok && nc::isForMe(me(), h)) {
    g_lastRxMs = millis();
    g_rssiLast = (int8_t)constrain((int)lroundf(rssi), -128, 127);
    g_snrX4 = (int8_t)constrain((int)lroundf(snr * 4), -128, 127);
    const uint32_t ts = millis();
    nc::Outcome o = nc::handleFrame(g_store, g_file, h, p, (uint32_t)time(nullptr), g_mac);
    if (o.ignored) return;  // 다른 노드의 SET_ROOM — 응답하지 않는다(§6.6)
    const uint32_t saveMs = millis() - ts;
    if (o.timeSet) {
      timeval tv{(time_t)o.epoch, 0};
      settimeofday(&tv, nullptr);
      g_rtc.lastTimeSyncEpoch = o.epoch;
      syncDay();
      g_dirty = true;
      g_status.onTimeSet(nowMs());
      if (g_rtc.nextStatusEpoch == 0)
        g_rtc.nextStatusEpoch = nc::nextDailyStatus(o.epoch, g_statusHour, g_spread);
    }
    if (o.statusReq)
      g_status.request(nowMs(), 300 + (o.statusSpreadMs ? (esp_random() ^ g_macHash) % o.statusSpreadMs : 0));
    if (o.changed) g_dirty = true;
    if (o.provisionedNow) {
      Serial.printf("[node] 정체성 받음 %c%u-%u\n", g_rtc.bld, g_rtc.room, g_rtc.unit);
      g_shownValid = false;
      g_status.sent(nowMs(), true, true, 0);  // HELLO 예약을 비우고 STATUS 로
      g_status.request(nowMs(), 300);
    }
    if (o.forceRender || o.testLayout) {
      g_forceRender = true;
      g_testLayout = o.testLayout;
      g_dirty = true;
    }
    if (h.type == LP_TYPE_CMD) loadParams();
    if (o.status != nc::kNoAck) sendAck(h, o.status, o.detail);
    if (o.reboot || o.factoryReset) restartAfterAck(o.factoryReset);
    Serial.printf("[node] type=0x%02x txn=%u ACK=%d ver S%u/R%u/E%u today=%u save=%lums RSSI %.0f SNR %.1f\n",
                  h.type, h.txn, o.status == nc::kNoAck ? -1 : o.status, g_rtc.schedVer, g_rtc.resvVer,
                  g_rtc.examVer, g_rtc.nSlots, (unsigned long)saveMs, rssi, snr);
  }
}

// 수신 프레임 하나를 처리한다. loop 와 패널 BUSY 콜백 양쪽에서 부른다.
void pollRadio() {
  if (!g_irq) return;
  g_irq = false;
  static uint8_t buf[256];
  size_t len = radio.getPacketLength();
  if (len > sizeof buf) len = sizeof buf;
  int rs = radio.readData(buf, len);
  handleRx(buf, len, rs, radio.getRSSI(), radio.getSNR());
  listen();
}

void onPanelBusy(const void*) {
  pollRadio();  // 패널은 HSPI, 무선은 FSPI — 리프레시 중에도 듣고 ACK 한다
  delay(1);
}

void render(const RenderModel& m) {
  digitalWrite(VEXT_CTRL, LOW);
  delay(50);
  display.init(0, true, 2, false);
  display.epd2.boosterSoftStart();
  display.setRotation(0);
  display.setFullWindow();
  display.firstPage();
  do {
    renderLayout(display, m);
  } while (display.nextPage());
  display.hibernate();
  digitalWrite(VEXT_CTRL, HIGH);
}

#if NODE_SLEEP_MODE == 2
// ---- DEEP (v2 §6.7) ----
// SX1262 를 수신 duty cycle 로 두고 잔다. 웨이크 프레임을 다 받으면 DIO1(RX_DONE)이 ext0 로 ESP 를 깨우고,
// 패킷은 칩 버퍼에 남아 있다 — radio.begin() 은 칩을 리셋해 그 패킷을 지우므로, 깬 직후 SPI 명령으로 먼저
// 읽는다 (SX1262 데이터시트 13.5: GetIrqStatus 0x12, GetRxBufferStatus 0x13, GetPacketStatus 0x14, ReadBuffer
// 0x1E).
bool sxCmd(uint8_t op, const uint8_t* tx, size_t ntx, uint8_t* rx, size_t nrx) {
  const uint32_t t0 = millis();
  while (digitalRead(LORA_BUSY) == HIGH)
    if (millis() - t0 > 100) return false;
  SPI.beginTransaction(SPISettings(2000000, MSBFIRST, SPI_MODE0));
  digitalWrite(LORA_NSS, LOW);
  SPI.transfer(op);
  for (size_t i = 0; i < ntx; ++i) SPI.transfer(tx[i]);
  for (size_t i = 0; i < nrx; ++i) rx[i] = SPI.transfer(0x00);
  digitalWrite(LORA_NSS, HIGH);
  SPI.endTransaction();
  return true;
}

// 칩 버퍼의 패킷을 읽는다. 반환 = 길이(0 = 없음·CRC 오류)
size_t readHeldPacket(uint8_t* buf, size_t cap, float& rssi, float& snr) {
  pinMode(LORA_NSS, OUTPUT);
  digitalWrite(LORA_NSS, HIGH);
  pinMode(LORA_BUSY, INPUT);
  SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_NSS);
  uint8_t irq[3];  // status, irq[15:8], irq[7:0]
  if (!sxCmd(0x12, nullptr, 0, irq, 3)) return 0;
  const uint16_t flags = (uint16_t)(irq[1] << 8 | irq[2]);
  if (!(flags & 0x0002) || (flags & 0x0040)) {  // RX_DONE 아님 · CRC 오류
    Serial.printf("[node] 버퍼 패킷 없음 irq=0x%04x\n", flags);
    return 0;
  }
  uint8_t st[3];  // status, payloadLen, rxStartBufferPointer
  if (!sxCmd(0x13, nullptr, 0, st, 3)) return 0;
  const size_t n = st[1] < cap ? st[1] : cap;
  static uint8_t tmp[257];
  if (!sxCmd(0x1E, &st[2], 1, tmp, n + 1)) return 0;  // 첫 바이트는 status
  memcpy(buf, tmp + 1, n);
  uint8_t ps[4];  // status, rssiPkt, snrPkt, signalRssiPkt
  if (sxCmd(0x14, nullptr, 0, ps, 4)) {
    rssi = -(float)ps[1] / 2.0f;
    snr = (float)(int8_t)ps[2] / 4.0f;
  }
  return n;
}

void deepSleep(uint32_t ms) {
  radio.standby();
  radio.setPreambleLength(RX_PREAMBLE_SYM);
  const int st = radio.startReceiveDutyCycleAuto(RX_PREAMBLE_SYM, RP_RX_DUTY_MIN_SYM);
  if (st != RADIOLIB_ERR_NONE) {
    Serial.printf("[node] duty cycle 실패 %d — 자지 않음\n", st);
    listen();
    return;
  }
  WakeState w;
  w.magic = kWakeMagic;
  w.status = g_status;
  w.shown = g_shown;
  w.shownValid = g_shownValid;
  w.layout = g_layout;
  w.rssiLast = g_rssiLast;
  w.snrX4 = g_snrX4;
  memcpy(g_wakeRaw, &w, sizeof w);
  ns::rtcSeal(g_rtc);
  // 자는 동안 핀이 떠서 무선 칩이 리셋되거나(RST) SPI 로 깨거나(NSS), 패널 전원이 켜지지(Vext) 않게 붙잡는다
  digitalWrite(VEXT_CTRL, HIGH);
  gpio_hold_en((gpio_num_t)VEXT_CTRL);
  gpio_hold_en((gpio_num_t)LORA_NSS);
  gpio_hold_en((gpio_num_t)LORA_RST);
  gpio_deep_sleep_hold_en();
  esp_sleep_enable_ext0_wakeup((gpio_num_t)LORA_DIO1, 1);
  rtc_gpio_pullup_en((gpio_num_t)BUTTON_PIN);  // 자는 동안 디지털 풀업이 꺼진다
  rtc_gpio_pulldown_dis((gpio_num_t)BUTTON_PIN);
  esp_sleep_enable_ext1_wakeup(1ULL << BUTTON_PIN, ESP_EXT1_WAKEUP_ANY_LOW);
  esp_sleep_enable_timer_wakeup((uint64_t)ms * 1000ULL);
  Serial.printf("[node] 딥슬립 %lums\n", (unsigned long)ms);
  Serial.flush();
  esp_deep_sleep_start();
}
#endif

#if NODE_SLEEP_MODE == 1
// v2 §6.7 LIGHT — RAM·RadioLib 객체·millis 는 그대로. 무선은 수신 duty cycle 로 웨이크 프리앰블을 기다린다
void lightSleep(uint32_t ms) {
  radio.standby();
  radio.setPreambleLength(RX_PREAMBLE_SYM);
  g_irq = false;
  const int st = radio.startReceiveDutyCycleAuto(RX_PREAMBLE_SYM, RP_RX_DUTY_MIN_SYM);
  if (st != RADIOLIB_ERR_NONE) {
    Serial.printf("[node] duty cycle 실패 %d — 자지 않음\n", st);
    listen();
    return;
  }
  radio.clearDio1Action();  // level 깨우기를 쓰는 동안 엣지 인터럽트를 뗀다(붙인 채면 깬 뒤 ISR 이 끝없이
                            // 돈다)
  gpio_wakeup_enable((gpio_num_t)LORA_DIO1, GPIO_INTR_HIGH_LEVEL);
  gpio_wakeup_enable((gpio_num_t)BUTTON_PIN, GPIO_INTR_LOW_LEVEL);
  esp_sleep_enable_gpio_wakeup();
  esp_sleep_enable_timer_wakeup((uint64_t)ms * 1000ULL);
  Serial.flush();
  const uint32_t t0 = millis();
  esp_light_sleep_start();
  const esp_sleep_wakeup_cause_t why = esp_sleep_get_wakeup_cause();
  gpio_wakeup_disable((gpio_num_t)LORA_DIO1);
  gpio_wakeup_disable((gpio_num_t)BUTTON_PIN);
  esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_ALL);
  radio.setDio1Action(onDio1);
  const bool fromRadio = digitalRead(LORA_DIO1) == HIGH;
  if (fromRadio)
    g_irq = true;  // 패킷은 pollRadio 가 읽고 그 뒤 listen() 으로 연속 수신
  else
    listen();
  Serial.printf("[node] 깸 cause=%s slept=%lums\n",
                fromRadio ? "radio" : (why == ESP_SLEEP_WAKEUP_TIMER ? "timer" : "button"),
                (unsigned long)(millis() - t0));
}
#endif

#if NODE_SLEEP_MODE >= 1
void maybeSleep() {
  if (g_irq || millis() - g_lastRxMs <= g_quietMs) return;
  if (digitalRead(BUTTON_PIN) == LOW) return;  // 누르는 중 — 떼야 짧게/길게를 안다
  const bool clk = clockValid();
  const uint32_t now = (uint32_t)time(nullptr);
  const bool dayReady = clk && g_rtc.slotsDay == sch::toKst(now).weekday;
  if (g_dirty && (dayReady || !g_rtc.provisioned)) return;  // 그릴 것이 남았다 — 렌더 블록이 먼저
  uint32_t next = 0;
  if (dayReady) {
    next = sch::nextChangeAt(
        sch::ScheduleView{g_rtc.slots, g_rtc.nSlots, g_rtc.resv, g_rtc.nResv, g_rtc.exams, g_rtc.nExam}, now,
        g_rtc.nextStatusEpoch);
  } else if (clk) {
    next = now + nc::kSleepCapNoDayMs / 1000;
  }
  const uint32_t ms = nc::sleepMs(nowMs(), clk, now, next, dayReady, g_status);
  if (ms == 0) return;
#if NODE_SLEEP_MODE == 2
  deepSleep(ms);
#else
  lightSleep(ms);
#endif
}
#endif

}  // namespace

void setup() {
#if NODE_SLEEP_MODE == 2
  const bool deepWake = esp_reset_reason() == ESP_RST_DEEPSLEEP;
  const esp_sleep_wakeup_cause_t wakeCause = esp_sleep_get_wakeup_cause();
  if (deepWake) {
    gpio_hold_dis((gpio_num_t)VEXT_CTRL);
    gpio_hold_dis((gpio_num_t)LORA_NSS);
    gpio_hold_dis((gpio_num_t)LORA_RST);
    gpio_deep_sleep_hold_dis();
    rtc_gpio_deinit((gpio_num_t)LORA_DIO1);
    rtc_gpio_deinit((gpio_num_t)BUTTON_PIN);
  }
#else
  const bool deepWake = false;
#endif
  Serial.begin(115200);
  if (!deepWake) delay(200);
  WiFi.mode(WIFI_OFF);
  btStop();
  pinMode(VEXT_CTRL, OUTPUT);
  digitalWrite(VEXT_CTRL, HIGH);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  const uint64_t efuse = ESP.getEfuseMac();
  for (int i = 0; i < 6; ++i) g_mac[i] = (uint8_t)(efuse >> (8 * i));
  bool fs = LittleFS.begin(true);
  const uint8_t bootWd = clockValid() ? sch::toKst((uint32_t)time(nullptr)).weekday : 0;
  ns::LoadSource src = g_store.load(bootWd);
#ifdef NODE_ROOM
  // 빌드 플래그로 방을 줬으면 그 정체성을 강제한다(시연·실험용). 안 주면 NVS 정체성(SET_ROOM) 그대로
  if (!g_rtc.provisioned || g_rtc.room != NODE_ROOM || g_rtc.bld != NODE_BLD || g_rtc.unit != NODE_UNIT) {
    if (g_rtc.provisioned) {
      // 다른 방으로 바뀌었다 — 옛 방의 시간표·예약·버전을 지워 버전 0 으로 서버가 재동기하게 한다.
      // factoryReset 은 RTC 를 비우고 봉인하지 않으므로 load 로 빈 저장소에서 다시 채운 뒤 정체성을 쓴다.
      (void)g_store.factoryReset();
      src = g_store.load(bootWd);
    }
    (void)g_store.setIdentity(ns::Identity{NODE_BLD, NODE_ROOM, NODE_UNIT}, 0);
  }
#endif
  loadParams();
  if (!deepWake)
    (void)LittleFS.remove("/state.bin");  // 0단계 전(임시 형식) 파일 — 버전 0 으로 시작해 서버가 재동기
  ns::rtcSeal(g_rtc);
  Serial.printf("[node] 저장 %s\n", src == ns::LoadSource::RtcCache ? "RTC 캐시" : "재구축");
  epdSpi.begin(EPD_SCK, -1, EPD_MOSI, EPD_CS);
  display.epd2.selectSPI(epdSpi, SPISettings(4000000, MSBFIRST, SPI_MODE0));
  display.epd2.setBusyCallback(onPanelBusy);
#if NODE_SLEEP_MODE == 2
  // 무선으로 깼으면 radio.begin()(칩 리셋) 전에 버퍼의 패킷부터 읽는다
  static uint8_t held[256];
  size_t heldLen = 0;
  float heldRssi = 0, heldSnr = 0;
  if (deepWake && wakeCause == ESP_SLEEP_WAKEUP_EXT0)
    heldLen = readHeldPacket(held, sizeof held, heldRssi, heldSnr);
#endif
  int st = radioBegin();
  g_macHash = nc::macSpread(g_mac, 0xFFFFFFFFu);
  g_spread = nc::macSpread(g_mac, nc::kStatusSpreadSec);
  g_battMv = readBattMv();
#if NODE_SLEEP_MODE == 2
  WakeState w;
  memcpy(&w, g_wakeRaw, sizeof w);
  const bool resumed = deepWake && w.magic == kWakeMagic;
  if (resumed) {
    g_status = w.status;
    g_shown = w.shown;
    g_shownValid = w.shownValid;
    g_layout = w.layout;
    g_rssiLast = w.rssiLast;
    g_snrX4 = w.snrX4;
    g_dirty = false;  // 잠들기 전에 그릴 것은 다 그렸다 — 바뀌었으면 상태키·수신이 다시 표시한다
  }
  memset(g_wakeRaw, 0, sizeof(uint32_t));  // magic 무효화 — 한 번 쓰면 끝, 다음 잠들기가 다시 쓴다
#else
  const bool resumed = false;
#endif
  if (!resumed)
    g_status.request(nowMs(),
                     1000 + (esp_random() ^ g_macHash) % 3000);  // 부팅 보고(§6.2) — 미설정이면 HELLO
  if (g_rtc.provisioned)
    Serial.printf("[node] %c%u-%u fw=%u radio=%d fs=%d ver S%u/R%u/E%u slots=%u batt=%umV\n", g_rtc.bld,
                  g_rtc.room, g_rtc.unit, FW_VER, st, fs, g_rtc.schedVer, g_rtc.resvVer, g_rtc.examVer,
                  g_rtc.nSlots, g_battMv);
  else
    Serial.printf("[node] 미설정 NEW-%02X%02X mac=%02x%02x%02x%02x%02x%02x fw=%u radio=%d batt=%umV\n",
                  g_mac[4], g_mac[5], g_mac[0], g_mac[1], g_mac[2], g_mac[3], g_mac[4], g_mac[5], FW_VER, st,
                  g_battMv);
  g_lastRxMs = resumed ? millis() - g_quietMs - 1 : millis();  // 타이머로 깼으면 할 일만 하고 곧 다시 잔다
  listen();
#if NODE_SLEEP_MODE == 2
  if (deepWake)
    Serial.printf("[node] 깸(딥) cause=%s len=%u\n",
                  wakeCause == ESP_SLEEP_WAKEUP_EXT0   ? "radio"
                  : wakeCause == ESP_SLEEP_WAKEUP_EXT1 ? "button"
                                                       : "timer",
                  (unsigned)heldLen);
  if (heldLen) {
    handleRx(held, heldLen, RADIOLIB_ERR_NONE, heldRssi, heldSnr);
    listen();
  }
#endif
}

// 설정 대기 화면(layout 8) — 시계와 무관하게 그린다
void renderSetupIfNeeded() {
  if (!g_dirty || millis() - g_lastRxMs <= g_quietMs) return;
  g_dirty = false;
  static RenderModel m;
  nc::setupModel(g_mac, m);
  g_layout = m.layout;
  if (g_shownValid && !g_forceRender && nc::sameScreen(g_shown, m)) return;
  g_forceRender = false;
  Serial.printf("[node] 렌더 설정 대기 %s\n", m.newTag);
  render(m);
  g_shown = m;
  g_shownValid = true;
}

void pollButton() {
  switch (g_button.update(millis(), digitalRead(BUTTON_PIN) == LOW)) {
    case nc::Button::kShort:
      Serial.println("[node] 버튼 짧게 — 다시 그리기 + STATUS");
      g_forceRender = true;
      g_dirty = true;
      g_status.request(nowMs(), 300);
      break;
    case nc::Button::kLong:
      Serial.println("[node] 버튼 5 s — 공장 초기화");
      restartAfterAck(true);
    default:
      break;
  }
}

static void loopBody() {
  pollRadio();
  pollButton();
  maybeSendStatus();  // 1 s 틱 밖에서 — 임의 지연이 1 s 단위로 뭉쳐 동시 부팅 노드끼리 겹치지 않게
  static uint32_t lastCheck = 0;
  if (millis() - lastCheck < 1000) return;
  lastCheck = millis();
  maybeMeasureBatt();
  if (!g_rtc.provisioned) {
    renderSetupIfNeeded();
    return;
  }
  if (!clockValid()) return;  // 시계 전엔 그리지 않는다 — 마지막 화면 유지
  syncDay();
  const uint32_t now = (uint32_t)time(nullptr);
  // 오늘 슬롯 캐시가 아직 오늘 요일 것이 아니면(refreshDay 실패 중) 그리지 않는다 — 빈 날 화면을 그렸다가 60
  // s 뒤 다시 그리지 않도록. g_dirty 는 그대로 둔다
  if (g_rtc.slotsDay != sch::toKst(now).weekday) return;
  static RenderModel m;
  const sch::LayoutDecision d = nc::buildModel(g_rtc, now, m);
  m.battMv = g_battMv;
  // 상태키(v2 §6.3) — 레이아웃·요일·상태를 정한 항목의 시작. 다르면 다시 그린다
  const bool keyChanged =
      d.layout != g_rtc.lastLayout || d.day != g_rtc.lastDay || d.slotStartMin != g_rtc.lastSlotStartMin;
  if (keyChanged) g_dirty = true;
  if (g_dirty && millis() - g_lastRxMs > g_quietMs) {
    g_dirty = false;
    g_rtc.lastLayout = d.layout;
    g_rtc.lastDay = d.day;
    g_rtc.lastSlotStartMin = d.slotStartMin;
    ns::rtcSeal(g_rtc);
    g_layout = m.layout;
    const uint8_t todayN = g_rtc.slotsDay == sch::toKst(now).weekday ? g_rtc.nSlots : 0;
    Serial.printf("[node] 렌더 layout=%u today=%u next=%lu\n", m.layout, m.nToday,
                  (unsigned long)sch::nextChangeAt(sch::ScheduleView{g_rtc.slots, todayN, g_rtc.resv,
                                                                     g_rtc.nResv, g_rtc.exams, g_rtc.nExam},
                                                   now, g_rtc.nextStatusEpoch));
    if (g_testLayout) {
      m.layout = g_testLayout;  // CMD TEST_RENDER — 한 번만
      g_testLayout = 0;
    }
    if (g_shownValid && !g_forceRender && nc::sameScreen(g_shown, m)) {
      Serial.printf("[node] 같은 화면 — 다시 그리지 않음 layout=%u\n", m.layout);
      return;
    }
    g_forceRender = false;
    const uint32_t t0 = millis();
    render(m);
    g_shown = m;
    g_shownValid = true;
    Serial.printf("[node] 렌더 끝 %lu ms\n", (unsigned long)(millis() - t0));
  }
}

void loop() {
  loopBody();
#if NODE_SLEEP_MODE >= 1
  maybeSleep();
#endif
}
