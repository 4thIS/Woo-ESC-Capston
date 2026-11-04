// S8 노드 펌웨어 — 깨어 있는 모드(SLEEP_MODE 없음, USB 전원 시연용). 로직은 lib/node_core(nc::*), 여기는
// 어댑터만.
//  - 무선: SX1262 DIO1 인터럽트 송수신(2026-10-21 교훈). ACK 는 저장 직후·렌더 전에(v2 §6.4), 송신 전 CAD
//  1회(§6.8)
//  - 저장: LittleFS /state.bin 에 nc::State 통째(원자 교체). dh-08 저장 계층(KvStore·FileStore)이 오면 바꿔
//  끼운다
//  - 화면: renderLayout(dh, #89) + RenderModel(계약 ④). 패널 리프레시(약 27 s) 동안에도 busy 콜백에서
//  수신·ACK
//  - 정체성: 빌드 플래그 NODE_BLD·NODE_ROOM·NODE_UNIT (프로비저닝 SET_ROOM 은 S9)
//  - 시계: TIME 으로 맞춘다. 시계가 무효면 그리지 않는다 — e-Paper 는 마지막 화면을 그대로 둔다(§5.2)
#include <Arduino.h>
#include <GxEPD2_3C.h>
#include <LittleFS.h>
#include <RadioLib.h>
#include <SPI.h>
#include <WiFi.h>
#include <esp_random.h>
#include <sys/time.h>

#include "lora_codec.h"
#include "node_core.h"
#include "render.h"
#include "render_model.h"

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

constexpr nc::Ident ME{(uint8_t)NODE_BLD, (uint16_t)NODE_ROOM, (uint8_t)NODE_UNIT};
constexpr uint8_t FW_VER = 2;
constexpr uint32_t QUIET_MS = 8000;  // 마지막 수신 뒤 이만큼 조용하면 그린다(웨이크 프리앰블 3 s 보다 길게)
constexpr uint16_t BATT_MV_USB = 4000;  // 배터리 측정은 S9(절전) — 시연은 USB 전원

constexpr int LORA_NSS = 8, LORA_SCK = 9, LORA_MOSI = 10, LORA_MISO = 11;
constexpr int LORA_RST = 12, LORA_BUSY = 13, LORA_DIO1 = 14;
constexpr int EPD_SCK = 5, EPD_MOSI = 6, EPD_CS = 7, EPD_DC = 4, EPD_RST = 3, EPD_BUSY = 2;
constexpr int VEXT_CTRL = 36;  // LOW = Vext(패널 3.3 V) 켜짐

SX1262 radio = new Module(LORA_NSS, LORA_DIO1, LORA_RST, LORA_BUSY);
volatile bool g_irq = false;
void IRAM_ATTR onDio1() {
  g_irq = true;
}

SPIClass epdSpi(HSPI);
GxEPD2_3C<GxEPD2_750c_Z08, GxEPD2_750c_Z08::HEIGHT / 2> display(GxEPD2_750c_Z08(EPD_CS, EPD_DC, EPD_RST,
                                                                                EPD_BUSY));

nc::State g_state, g_backup;
nc::FileRx g_file;
uint8_t g_layout = LP_LAYOUT_EMPTY;  // 마지막으로 그린 화면(ACK 에 싣는다)
bool g_dirty = true;
uint32_t g_lastRxMs = 0;

// ---------------- 저장 (임시 — dh-08 전까지) ----------------
constexpr uint32_t STATE_MAGIC = 0x57534301;  // 'WSC' + 형식 1 — nc::State 가 바뀌면 올린다
struct StateFileHead {
  uint32_t magic;
  uint32_t size;
  uint16_t crc;
};

bool saveState() {
  StateFileHead h{STATE_MAGIC, sizeof g_state, lc::crc16((const uint8_t*)&g_state, sizeof g_state)};
  File f = LittleFS.open("/state.tmp", "w");
  if (!f) return false;
  bool ok = f.write((const uint8_t*)&h, sizeof h) == sizeof h &&
            f.write((const uint8_t*)&g_state, sizeof g_state) == sizeof g_state;
  f.close();
  return ok && LittleFS.rename("/state.tmp", "/state.bin");  // 원자 교체 — 실패하면 옛 파일 그대로
}

void loadState() {
  nc::clear(g_state);
  File f = LittleFS.open("/state.bin", "r");
  if (!f) return;
  StateFileHead h{};
  static nc::State tmp;
  bool ok = f.read((uint8_t*)&h, sizeof h) == sizeof h && h.magic == STATE_MAGIC && h.size == sizeof tmp &&
            f.read((uint8_t*)&tmp, sizeof tmp) == sizeof tmp &&
            lc::crc16((const uint8_t*)&tmp, sizeof tmp) == h.crc;
  f.close();
  if (ok) g_state = tmp;  // 손상되면 비운다 — 버전 0 이라 다음 변경 때 서버가 GAP → FILE 재동기
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

void listen() {
  g_irq = false;
  radio.startReceive();
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

void sendAck(const lc::Header& req, uint8_t status, uint8_t detail) {
  lc::Ack a{};
  a.status = status;
  a.detail = detail;
  a.battMv = BATT_MV_USB;
  a.schedVer = g_state.schedVer;
  a.resvVer = g_state.resvVer;
  a.examVer = g_state.examVer;
  a.fw = FW_VER;
  a.layout = g_layout;
  uint8_t pl[32], out[64];
  size_t pn = lc::encAck(a, pl, sizeof pl);
  lc::Header h{};
  h.ver = LP_PROTO_VER;
  h.netId = req.netId;
  h.type = LP_TYPE_ACK;
  h.bld = req.bld;
  h.room = req.room;
  h.unit = req.unit;
  h.txn = req.txn;
  size_t n = lc::encodeFrame(h, pl, (uint8_t)pn, out, sizeof out);
  delay(20);  // 모뎀이 송신 → 수신으로 넘어갈 틈
  if (!channelFree()) {
    Serial.println("[node] ACK 포기 — 채널 사용 중");
    return;
  }
  g_irq = false;
  if (radio.startTransmit(out, n) == RADIOLIB_ERR_NONE) waitIrq(2000);
  radio.finishTransmit();
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
  if (rs == RADIOLIB_ERR_NONE && lc::decodeFrame(buf, len, h, p) && nc::isForMe(ME, h)) {
    g_lastRxMs = millis();
    g_backup = g_state;
    nc::Outcome o = nc::handleFrame(g_state, g_file, h, p);
    bool txnMoved = g_state.lastTxn != g_backup.lastTxn;
    if ((o.changed || txnMoved) && !saveState()) {
      g_state = g_backup;  // 저장 실패 — 적용도 되돌리고 STORE_FAIL(재송 1회 후 failed)
      o.changed = false;
      if (o.status != nc::kNoAck) o.status = LP_ACK_STORE_FAIL;
    }
    if (o.timeSet) {
      timeval tv{(time_t)o.epoch, 0};
      settimeofday(&tv, nullptr);
      g_dirty = true;
    }
    if (o.changed) g_dirty = true;
    if (o.status != nc::kNoAck) sendAck(h, o.status, o.detail);
    Serial.printf("[node] type=0x%02x txn=%u ACK=%d ver S%u/R%u/E%u slots=%u RSSI %.0f SNR %.1f\n", h.type,
                  h.txn, o.status == nc::kNoAck ? -1 : o.status, g_state.schedVer, g_state.resvVer,
                  g_state.examVer, g_state.nSlots, rssi, snr);
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
  display.setRotation(0);
  display.setFullWindow();
  display.firstPage();
  do {
    renderLayout(display, m);
  } while (display.nextPage());
  display.hibernate();
  digitalWrite(VEXT_CTRL, HIGH);
}

bool clockValid() {
  return (uint32_t)time(nullptr) > nc::kClockValidEpoch;
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
  loadState();
  epdSpi.begin(EPD_SCK, -1, EPD_MOSI, EPD_CS);
  display.epd2.selectSPI(epdSpi, SPISettings(4000000, MSBFIRST, SPI_MODE0));
  display.epd2.setBusyCallback(onPanelBusy);
  int st = radioBegin();
  Serial.printf("[node] %c%u-%u fw=%u radio=%d fs=%d ver S%u/R%u/E%u slots=%u\n", ME.bld, ME.room, ME.unit,
                FW_VER, st, fs, g_state.schedVer, g_state.resvVer, g_state.examVer, g_state.nSlots);
  g_lastRxMs = millis();
  listen();
}

void loop() {
  pollRadio();
  static uint32_t lastCheck = 0;
  if (millis() - lastCheck < 1000) return;
  lastCheck = millis();
  if (!clockValid()) return;  // 시계 전엔 그리지 않는다 — 마지막 화면 유지
  static RenderModel m;
  nc::Decision d = nc::buildModel(ME, g_state, (uint32_t)time(nullptr), m);
  m.battMv = BATT_MV_USB;
  // 상태키(레이아웃·요일·상태를 정한 항목의 시작) — 시각이 경계를 넘으면 다시 그린다
  static uint32_t lastKey = 0xFFFFFFFF;
  uint32_t key = (uint32_t)m.layout << 24 | (uint32_t)m.weekday << 16 |
                 (uint32_t)(m.cur.sH * 60 + m.cur.sM) << 2 | (d.src >= 0 ? 1u : 0u);
  if (key != lastKey) g_dirty = true;
  if (g_dirty && millis() - g_lastRxMs > QUIET_MS) {
    g_dirty = false;
    lastKey = key;
    g_layout = m.layout;
    Serial.printf("[node] 렌더 layout=%u today=%u until=%d\n", m.layout, m.nToday, d.until);
    uint32_t t0 = millis();
    render(m);
    Serial.printf("[node] 렌더 끝 %lu ms\n", (unsigned long)(millis() - t0));
  }
}
