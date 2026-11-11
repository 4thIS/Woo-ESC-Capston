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

struct Identity {
  uint8_t bld;
  uint16_t room;
  uint8_t unit;
};
enum class LoadSource : uint8_t { RtcCache, Rebuilt };

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

  // 부팅 적재. RTC 가 유효하면 그대로(파일을 읽지 않는다 — 단 weekday != 0 이고 slotsDay 가 다르면 그 요일
  // 슬롯만 refreshDay), 아니면 NVS·파일에서 다시 채우고 봉인한다. weekday = 1(월)..7(일), 시계 무효면 0.
  // 재구축에서 파일이 Corrupt·OverCapacity·읽기 실패이거나, 버전이 있는데 파일이 없으면 그 kind 는 빈 표 +
  // 버전 0(NVS 에도 0) → 서버가 STATUS 버전 비교로 FILE 재동기를 건다(v2 §5.1).
  LoadSource load(uint8_t weekday);
  // 날짜가 바뀌면 cw 가 부른다 — /schedule.bin 에서 그 요일 슬롯을 RTC 에 다시 채운다(weekday 0 = 비움).
  // 실패하면 슬롯은 비운다(옛 요일 슬롯을 남기지 않는다). 손상(Corrupt·OverCapacity)이면 버전 0 + slotsDay =
  // weekday(재동기 replaceKind 가 오늘 슬롯을 채운다), 일시적 읽기 오류면 버전 그대로 + slotsDay = 0
  // (다음 load(weekday) 가 다시 시도한다). 둘 다 StoreFail.
  StoreStatus refreshDay(uint8_t weekday);
  StoreStatus setLastTxn(uint8_t txn);  // 저장만 한다 — Ok 일 때만 부르는 건 cw 몫(#74 10)
  StoreStatus setIdentity(const Identity& id, uint8_t identVer);  // provisioned = 1
  StoreStatus setParam(uint8_t paramId, uint32_t value);          // 1 statusHourUtc · 2 sessionWindowMs
  bool param(uint8_t paramId, uint32_t& out);                     // NVS 에서 읽음. 모르는 id·미설정이면 false
  // cfg·ver 를 지우고 파일 3개를 삭제, RTC 를 비운다(provisioned 0, 봉인 안 됨 → 다음 load 가 재구축).
  StoreStatus factoryReset();

 private:
  void rebuild(uint8_t weekday);
  bool readKind(const char* path, const char* verKey, uint8_t& ver, size_t& len);
  void dropKind(const char* verKey, uint8_t& ver);
  StoreStatus loadWeek(uint8_t& n, bool* readFailed = nullptr);
  StoreStatus commitSlots(uint8_t newVer, uint8_t n);
  StoreStatus commitResv(uint8_t newVer, uint8_t n);
  StoreStatus commitExams(uint8_t newVer, uint8_t n);

  KvStore& kv_;
  FileStore& fs_;
  RtcState& rtc_;
};

}  // namespace ns
