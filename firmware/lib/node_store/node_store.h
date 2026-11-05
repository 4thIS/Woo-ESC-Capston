// NodeStore — cw 수신 처리가 부르는 저장 API(v2 §5.1). 표준 C++ 만 쓴다 — Arduino/ESP 헤더 금지.
// 공통 쓰기 순서(write-through): 임시 사본에 적용 → 상한 검사 → 직렬화 → fs.writeAtomic → kv 버전 → RTC 확정.
// 파일을 버전보다 먼저 쓴다 — 어긋나도 버전이 옛 값이라 서버 STATUS 비교가 재동기를 건다.
// GAP 판정·lastTxn 기록은 cw 몫이다. RTC 봉인(rtcSeal)도 cw 가 잠들기 직전에 한다.
#pragma once

#include <cstdint>

#include "lora_codec.h"
#include "record_file.h"
#include "rtc_state.h"
#include "store_port.h"

namespace ns {

enum class StoreStatus : uint8_t { Ok, StoreFail, BadPayload, Unsupported };  // v2 §5.1, #74 11
struct Date {
  uint8_t y, m, d;  // y = year-2000 (ResvRec·ExamRec 과 같은 표현)
};

// 내부 작업 버퍼는 .cpp 의 정적 버퍼를 쓴다(ESP32 스택 보호) — 인스턴스가 여럿이어도 동시 호출은 금지.
class NodeStore {
 public:
  NodeStore(KvStore& kv, FileStore& fs, RtcState& rtc);
  const RtcState& state() const { return rtc_; }

  // 시간표: 한 주 표는 /schedule.bin, RTC 는 slotsDay 요일만 write-through
  StoreStatus applySlotSet(uint8_t newVer, const lc::SlotRec&);
  StoreStatus applySlotDel(uint8_t newVer, const lc::SlotDel&);
  StoreStatus applyDayClear(uint8_t newVer, const lc::DayClear&);
  // 예약: 지난 예약 정리(clockValid 일 때만) 뒤 용량 검사
  StoreStatus applyResvSet(uint8_t newVer, const lc::ResvRec&, Date today, bool clockValid);
  StoreStatus applyResvDel(uint8_t newVer, const lc::ResvDel&);
  StoreStatus applyExamSet(uint8_t newVer, const lc::ExamRec&);
  StoreStatus applyExamDel(uint8_t newVer, const lc::ExamDel&);
  // FILE_END CRC 검증 뒤. body 가 안 풀리면 BadPayload, 상한 초과면 StoreFail. 버전은 무조건 newVer(v2 §3.3)
  StoreStatus replaceKind(uint8_t kind, uint8_t newVer, const uint8_t* body, uint16_t len, Date today,
                          bool clockValid);
  StoreStatus purgePast(Date today, bool clockValid);  // clockValid 거짓이면 아무것도 안 하고 Ok
  // Task 5: load, refreshDay, setLastTxn, setIdentity, setParam, param, factoryReset

 private:
  StoreStatus loadWeek(uint8_t& n);
  StoreStatus commitSlots(uint8_t newVer, uint8_t n);
  StoreStatus commitResv(uint8_t newVer, uint8_t n);
  StoreStatus commitExams(uint8_t newVer, uint8_t n);

  KvStore& kv_;
  FileStore& fs_;
  RtcState& rtc_;
};

}  // namespace ns
