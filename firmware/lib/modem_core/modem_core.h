#pragma once
// S7 모뎀 펌웨어의 순수 로직 — v2 §4.2~4.5. 라디오·시계·시리얼은 인터페이스로 받는다(native 테스트용).
// 프레임 내용은 해석하지 않는다(§4.1) — 길이·CRC8 검증과 ACK 짝 맞추기만 lora_codec 으로 한다.
#include <ArduinoJson.h>
#include <stddef.h>
#include <stdint.h>

#include "radio_params.h"

namespace mc {

struct RadioCfg {
  float freq;  // MHz
  float bw;    // kHz
  uint8_t sf;
  uint8_t cr;    // 4/cr
  int8_t power;  // dBm
  uint32_t wakeMs;
};

RadioCfg defaultCfg();                                   // radio_params.h 값
const char* validateCfg(const RadioCfg&);                // 문제 없으면 nullptr, 있으면 이유
uint16_t wakeSymbols(const RadioCfg&);                   // wakeMs 를 덮는 프리앰블 심볼 수
int hexDecode(const char* s, uint8_t* out, size_t cap);  // 공백 허용. 홀수·넘침 → -1
void hexEncode(const uint8_t* b, size_t n, char* out);   // out 은 2n+1 바이트

enum class Cad { Free, Busy, Error };

struct RxPacket {
  uint8_t data[256];
  size_t len;
  float rssi, snr;
};

class RadioPort {
 public:
  virtual ~RadioPort() = default;
  virtual int begin(const RadioCfg&) = 0;  // (재)초기화. 0 = 성공
  virtual int apply(const RadioCfg&) = 0;  // 무선 설정만 바꾼다
  virtual Cad scanChannel() = 0;
  virtual int transmit(const uint8_t* b, size_t n, uint16_t preambleSym) = 0;  // 끝날 때까지 블로킹
  virtual void listen() = 0;
  // timeoutMs 안에 CRC 가 맞는 패킷 하나를 받으면 true. 0 이면 이미 받아 둔 것만 본다. 받은 뒤에도 수신 대기
  // 유지
  virtual bool receive(RxPacket& p, uint32_t timeoutMs) = 0;
};

class Host {
 public:
  virtual ~Host() = default;
  virtual uint32_t millis() = 0;
  virtual void delayMs(uint32_t ms) = 0;
  virtual uint32_t randomRange(uint32_t lo, uint32_t hi) = 0;  // [lo, hi]
  virtual void writeLine(const char* s) = 0;                   // '\n' 은 호출 측이 붙인다
  virtual void restart() = 0;
};

struct Stats {
  uint32_t tx = 0, acked = 0, noAck = 0, cadBusy = 0, rx = 0, errors = 0;
};

constexpr size_t kMaxLine = 1024;        // §4.5
constexpr uint32_t kWatchdogMs = 30000;  // §4.5: 30 s 동안 ping 없으면 라디오 재초기화

class Modem {
 public:
  Modem(RadioPort& r, Host& h, const char* fw);
  void boot();
  void handleLine(const char* line, size_t n);
  void poll();  // 비요청 업링크 → rx, 워치독
  const Stats& stats() const { return stats_; }
  const RadioCfg& cfg() const { return cfg_; }

 private:
  void log(const char* level, const char* msg);
  void emitRx(const RxPacket& p);
  void emit(JsonDocument& d);
  void onCfg(JsonVariantConst req);
  void onTx(JsonVariantConst req);
  RadioPort& r_;
  Host& h_;
  const char* fw_;
  RadioCfg cfg_;
  Stats stats_;
  uint32_t lastPing_ = 0;
};

}  // namespace mc
