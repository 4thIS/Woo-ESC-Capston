// S7 모뎀 펌웨어 — 실물 어댑터. 프로토콜·절차는 전부 lib/modem_core(mc::Modem) 가 한다(v2 §4).
// 송수신은 DIO1 인터럽트 방식이다. 블로킹 transmit()/receive() 를 섞으면 송신이 사라진다(2026-10-21 실기).
#include <Arduino.h>
#include <RadioLib.h>
#include <SPI.h>
#include <WiFi.h>
#include <esp_bt.h>
#include <esp_random.h>

#include "modem_core.h"

namespace {

constexpr int LORA_NSS = 8, LORA_SCK = 9, LORA_MOSI = 10, LORA_MISO = 11;
constexpr int LORA_RST = 12, LORA_BUSY = 13, LORA_DIO1 = 14;
constexpr int VEXT_CTRL = 36;  // LOW = Vext(OLED) 켜짐 — 모뎀은 쓰지 않는다(§4.5)
constexpr float TCXO_V = 1.8f;
constexpr const char* FW = "gw-2.0.0";

SX1262 radio = new Module(LORA_NSS, LORA_DIO1, LORA_RST, LORA_BUSY);
volatile bool g_irq = false;
void IRAM_ATTR onDio1() {
  g_irq = true;
}

bool waitIrq(uint32_t ms) {
  uint32_t t0 = millis();
  while (!g_irq) {
    if (millis() - t0 >= ms) return false;
    delay(1);
  }
  g_irq = false;
  return true;
}

class Sx1262Port : public mc::RadioPort {
 public:
  int begin(const mc::RadioCfg& c) override {
    SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_NSS);
    int st = radio.begin(c.freq, c.bw, c.sf, c.cr, RP_SYNC_WORD, c.power, RP_PREAMBLE_NORMAL, TCXO_V);
    if (st != RADIOLIB_ERR_NONE) return st;
    radio.setDio2AsRfSwitch(true);
    radio.setCRC(RP_HW_CRC);
    radio.setDio1Action(onDio1);
    listening_ = false;
    return 0;
  }
  int apply(const mc::RadioCfg& c) override {
    radio.standby();
    listening_ = false;
    int st = radio.setFrequency(c.freq);
    if (st == RADIOLIB_ERR_NONE) st = radio.setBandwidth(c.bw);
    if (st == RADIOLIB_ERR_NONE) st = radio.setSpreadingFactor(c.sf);
    if (st == RADIOLIB_ERR_NONE) st = radio.setCodingRate(c.cr);
    if (st == RADIOLIB_ERR_NONE) st = radio.setOutputPower(c.power);
    return st == RADIOLIB_ERR_NONE ? 0 : st;
  }
  mc::Cad scanChannel() override {
    radio.standby();
    listening_ = false;
    int st = radio.scanChannel();  // 내부에서 DIO1 을 기다린다 — 우리 ISR 플래그도 섰을 수 있어 지운다
    g_irq = false;
    if (st == RADIOLIB_LORA_DETECTED) return mc::Cad::Busy;
    if (st == RADIOLIB_CHANNEL_FREE) return mc::Cad::Free;
    return mc::Cad::Error;
  }
  int transmit(const uint8_t* b, size_t n, uint16_t pre) override {
    radio.standby();
    listening_ = false;
    radio.setPreambleLength(pre);
    g_irq = false;
    int st = radio.startTransmit(b, n);
    // 최악: SF12 wake 10 s + 255 B ≈ 13 s. 넉넉히 20 s.
    if (st == RADIOLIB_ERR_NONE && !waitIrq(20000)) st = RADIOLIB_ERR_TX_TIMEOUT;
    radio.finishTransmit();
    radio.setPreambleLength(RP_PREAMBLE_NORMAL);
    return st == RADIOLIB_ERR_NONE ? 0 : st;
  }
  void listen() override {
    if (listening_) return;
    g_irq = false;
    radio.startReceive();
    listening_ = true;
  }
  bool receive(mc::RxPacket& p, uint32_t timeoutMs) override {
    listen();
    uint32_t t0 = millis();
    for (;;) {
      uint32_t spent = millis() - t0;
      if (!g_irq && (timeoutMs == 0 || !waitIrq(timeoutMs > spent ? timeoutMs - spent : 0))) return false;
      g_irq = false;
      size_t len = radio.getPacketLength();
      if (len > sizeof p.data) len = sizeof p.data;
      int st = radio.readData(p.data, len);
      p.len = len;
      p.rssi = radio.getRSSI();
      p.snr = radio.getSNR();
      listening_ = false;
      listen();  // 다음 패킷을 계속 받는다
      if (st == RADIOLIB_ERR_NONE) return true;
      if (timeoutMs == 0 || millis() - t0 >= timeoutMs)
        return false;  // CRC 불량은 버리고 남은 시간 동안 더 기다린다
    }
  }

 private:
  bool listening_ = false;
};

class ArduinoHost : public mc::Host {
 public:
  uint32_t millis() override { return ::millis(); }
  void delayMs(uint32_t ms) override { ::delay(ms); }
  uint32_t randomRange(uint32_t lo, uint32_t hi) override { return lo + esp_random() % (hi - lo + 1); }
  void writeLine(const char* s) override {
    Serial.print(s);
    Serial.print('\n');
  }
  void restart() override {
    Serial.flush();
    ESP.restart();
  }
};

Sx1262Port g_port;
ArduinoHost g_host;
mc::Modem g_modem(g_port, g_host, FW);
char g_line[mc::kMaxLine + 2];
size_t g_len = 0;
bool g_overflow = false;

}  // namespace

void setup() {
  pinMode(VEXT_CTRL, OUTPUT);
  digitalWrite(VEXT_CTRL, HIGH);  // OLED 전원 차단
  WiFi.mode(WIFI_OFF);
  btStop();
  Serial.setRxBufferSize(4096);  // tx 처리 중(최대 수 초) 들어온 줄을 잃지 않게
  Serial.begin(115200);
  delay(200);
  g_modem.boot();
}

void loop() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (g_overflow) {
        g_modem.handleLine(g_line, mc::kMaxLine + 1);  // 길이 초과로 알리게
      } else if (g_len) {
        g_line[g_len] = '\0';
        g_modem.handleLine(g_line, g_len);
      }
      g_len = 0;
      g_overflow = false;
    } else if (g_len < mc::kMaxLine) {
      g_line[g_len++] = c;
    } else {
      g_overflow = true;
    }
  }
  g_modem.poll();
}
