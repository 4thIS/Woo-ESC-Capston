// S8 노드 펌웨어 — 깨어 있는 모드(SLEEP_MODE 없음, USB 전원 시연용). 로직은 lib/node_core(nc::*), 여기는
// 어댑터만.
//  - 무선: SX1262 DIO1 인터럽트 송수신(2026-10-21 교훈). ACK 는 저장 직후·렌더 전에(v2 §6.4), 송신 전 CAD
//  1회(§6.8)
//  - 저장: ns::NodeStore(NVS 버전·LittleFS 레코드·RTC 캐시) + sch:: 판정. 어댑터는 esp_store.h
//  - 화면: renderLayout(dh, #89) + RenderModel(계약 ④). 패널 리프레시(약 27 s) 동안에도 busy 콜백에서
//  수신·ACK
//  - 정체성: 빌드 플래그 NODE_BLD·NODE_ROOM·NODE_UNIT (프로비저닝 SET_ROOM 은 S9)
//  - 시계: TIME 으로 맞춘다. 시계가 무효면 그리지 않는다 — e-Paper 는 마지막 화면을 그대로 둔다(§5.2)
//  - STATUS(부팅·하루 1회·요청)·배터리 실측 — 절전 1단계
#include <Arduino.h>
#include <GxEPD2_3C.h>
#include <LittleFS.h>
#include <RadioLib.h>
#include <SPI.h>
#include <WiFi.h>
#include <esp_random.h>
#include <esp_timer.h>
#include <sys/time.h>

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
#ifndef NODE_ROOM
#define NODE_ROOM 301
#endif
#ifndef NODE_UNIT
#define NODE_UNIT 1
#endif

namespace {

constexpr uint8_t FW_VER = 4;
// 배터리(Heltec V3.2): GPIO37 HIGH 로 분압(390 k/100 k)을 켜고 GPIO1 을 잰다(2026-11-17 실기 확인, 3.5~4.0
// V). V3.0/3.1 보드는 극성이 반대(LOW)라 이 값으로는 0 근처가 나온다
constexpr int VBAT_ADC = 1, VBAT_CTRL = 37;
constexpr uint8_t VBAT_CTRL_ON = HIGH;
constexpr float VBAT_DIVIDER = 4.9f;
constexpr uint32_t BATT_PERIOD_MS = 60000;
constexpr uint32_t QUIET_MS = 8000;  // 마지막 수신 뒤 이만큼 조용하면 그린다(웨이크 프리앰블 3 s 보다 길게)

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

nc::Ident me() {
  return nc::Ident{g_rtc.bld, g_rtc.room, g_rtc.unit};
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
  const uint64_t up = (uint64_t)esp_timer_get_time() / 3600000000ULL;  // millis 는 49.7 일에 넘어간다
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

void maybeSendStatus() {
  const uint32_t ms = millis();
  const uint32_t now = (uint32_t)time(nullptr);
  const bool clk = clockValid();
  if (!g_status.due(ms, clk, now, g_rtc.nextStatusEpoch)) return;
  if (g_irq)
    return;  // 받은 프레임이 있으면 먼저 처리 — CAD(standby)가 그 프레임을 버리지 않게, 다음 틱에 보낸다
  uint8_t flags = 0;
  const bool done = sendStatus(now, flags);
  g_status.sent(ms, done, clk, flags);
  if (clk) {
    // now + 30 min 기준 — 18:00:05 TIME REQUEST_STATUS 로 막 보냈으면 같은 날 18:00+분산 슬롯은 건너뛴다(하루
    // 2회 방지)
    g_rtc.nextStatusEpoch = nc::nextDailyStatus(now + nc::kStatusSpreadSec, nc::kStatusHourUtc, g_spread);
    ns::rtcSeal(g_rtc);
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
  float rssi = radio.getRSSI(), snr = radio.getSNR();
  lc::Header h{};
  const uint8_t* p = nullptr;
  bool ok = rs == RADIOLIB_ERR_NONE && lc::decodeFrame(buf, len, h, p);
  if (!ok) Serial.printf("[node] 수신 버림 rs=%d len=%u RSSI %.0f\n", rs, (unsigned)len, rssi);
  if (ok && nc::isForMe(me(), h)) {
    g_lastRxMs = millis();
    g_rssiLast = (int8_t)constrain((int)lroundf(rssi), -128, 127);
    g_snrX4 = (int8_t)constrain((int)lroundf(snr * 4), -128, 127);
    const uint32_t ts = millis();
    nc::Outcome o = nc::handleFrame(g_store, g_file, h, p, (uint32_t)time(nullptr));
    const uint32_t saveMs = millis() - ts;
    if (o.timeSet) {
      timeval tv{(time_t)o.epoch, 0};
      settimeofday(&tv, nullptr);
      g_rtc.lastTimeSyncEpoch = o.epoch;
      syncDay();
      g_dirty = true;
      g_status.onTimeSet(millis());
      if (g_rtc.nextStatusEpoch == 0)
        g_rtc.nextStatusEpoch = nc::nextDailyStatus(o.epoch, nc::kStatusHourUtc, g_spread);
    }
    if (o.statusReq)
      g_status.request(millis(),
                       300 + (o.statusSpreadMs ? (esp_random() ^ g_macHash) % o.statusSpreadMs : 0));
    if (o.changed) g_dirty = true;
    if (o.status != nc::kNoAck) sendAck(h, o.status, o.detail);
    Serial.printf("[node] type=0x%02x txn=%u ACK=%d ver S%u/R%u/E%u today=%u save=%lums RSSI %.0f SNR %.1f\n",
                  h.type, h.txn, o.status == nc::kNoAck ? -1 : o.status, g_rtc.schedVer, g_rtc.resvVer,
                  g_rtc.examVer, g_rtc.nSlots, (unsigned long)saveMs, rssi, snr);
  }
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

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(200);
  WiFi.mode(WIFI_OFF);
  btStop();
  pinMode(VEXT_CTRL, OUTPUT);
  digitalWrite(VEXT_CTRL, HIGH);
  bool fs = LittleFS.begin(true);
  const uint8_t bootWd = clockValid() ? sch::toKst((uint32_t)time(nullptr)).weekday : 0;
  ns::LoadSource src = g_store.load(bootWd);
  // 0단계: 정체성은 아직 빌드 플래그(NODE_*). 2단계(프로비저닝)에서 SET_ROOM 으로 바뀐다
  if (!g_rtc.provisioned || g_rtc.room != NODE_ROOM || g_rtc.bld != NODE_BLD || g_rtc.unit != NODE_UNIT) {
    if (g_rtc.provisioned) {
      // 다른 방으로 바뀌었다 — 옛 방의 시간표·예약·버전을 지워 버전 0 으로 서버가 재동기하게 한다.
      // factoryReset 은 RTC 를 비우고 봉인하지 않으므로 load 로 빈 저장소에서 다시 채운 뒤 정체성을 쓴다.
      (void)g_store.factoryReset();
      src = g_store.load(bootWd);
    }
    (void)g_store.setIdentity(ns::Identity{NODE_BLD, NODE_ROOM, NODE_UNIT}, 0);
  }
  (void)LittleFS.remove("/state.bin");  // 0단계 전(임시 형식) 파일 — 버전 0 으로 시작해 서버가 재동기
  ns::rtcSeal(g_rtc);
  Serial.printf("[node] 저장 %s\n", src == ns::LoadSource::RtcCache ? "RTC 캐시" : "재구축");
  epdSpi.begin(EPD_SCK, -1, EPD_MOSI, EPD_CS);
  display.epd2.selectSPI(epdSpi, SPISettings(4000000, MSBFIRST, SPI_MODE0));
  display.epd2.setBusyCallback(onPanelBusy);
  int st = radioBegin();
  const uint64_t efuse = ESP.getEfuseMac();
  uint8_t mac[6];
  for (int i = 0; i < 6; ++i) mac[i] = (uint8_t)(efuse >> (8 * i));
  g_macHash = nc::macSpread(mac, 0xFFFFFFFFu);
  g_spread = nc::macSpread(mac, nc::kStatusSpreadSec);
  g_battMv = readBattMv();
  if (g_rtc.provisioned)
    g_status.request(millis(), 1000 + (esp_random() ^ g_macHash) % 3000);  // 부팅 보고(§6.2)
  Serial.printf("[node] %c%u-%u fw=%u radio=%d fs=%d ver S%u/R%u/E%u slots=%u batt=%umV\n", g_rtc.bld,
                g_rtc.room, g_rtc.unit, FW_VER, st, fs, g_rtc.schedVer, g_rtc.resvVer, g_rtc.examVer,
                g_rtc.nSlots, g_battMv);
  g_lastRxMs = millis();
  listen();
}

void loop() {
  pollRadio();
  maybeSendStatus();  // 1 s 틱 밖에서 — 임의 지연이 1 s 단위로 뭉쳐 동시 부팅 노드끼리 겹치지 않게
  static uint32_t lastCheck = 0;
  if (millis() - lastCheck < 1000) return;
  lastCheck = millis();
  maybeMeasureBatt();
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
  if (g_dirty && millis() - g_lastRxMs > QUIET_MS) {
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
    const uint32_t t0 = millis();
    render(m);
    Serial.printf("[node] 렌더 끝 %lu ms\n", (unsigned long)(millis() - t0));
  }
}
