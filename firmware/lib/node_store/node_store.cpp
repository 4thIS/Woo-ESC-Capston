#include "node_store.h"

#include <cstring>

namespace ns {

namespace {

constexpr const char* kVerSpace = "ver";  // NVS 키 이름은 v2 §5.1
constexpr const char* kSchedVerKey = "schedVer";
constexpr const char* kResvVerKey = "resvVer";
constexpr const char* kExamVerKey = "examVer";
constexpr const char* kSchedPath = "/schedule.bin";
constexpr const char* kResvPath = "/resv.bin";
constexpr const char* kExamPath = "/exam.bin";

// 작업 버퍼(임시 사본·직렬화). 정적이라 ESP32 스택을 쓰지 않는다. kSchedFileMax 가 셋 중 가장 크다.
static_assert(kSchedFileMax >= kResvFileMax && kSchedFileMax >= kExamFileMax, "파일 버퍼 크기");
lc::SlotRec gWeek[LP_SLOT_WEEK_MAX];
lc::ResvRec gResv[kResvMax];
lc::ExamRec gExam[kExamMax];
uint8_t gFile[kSchedFileMax];

// 멱등 키 SLOT = (day, sH, sM) — 주간 표 정렬 순서이기도 하다.
int cmpSlotKey(const lc::SlotRec& a, uint8_t day, uint8_t sH, uint8_t sM) {
  if (a.day != day) return a.day < day ? -1 : 1;
  if (a.sH != sH) return a.sH < sH ? -1 : 1;
  if (a.sM != sM) return a.sM < sM ? -1 : 1;
  return 0;
}

// gWeek[0, n) 에서 key 이상인 첫 위치
uint8_t lowerBound(uint8_t n, uint8_t day, uint8_t sH, uint8_t sM) {
  uint8_t i = 0;
  while (i < n && cmpSlotKey(gWeek[i], day, sH, sM) < 0) ++i;
  return i;
}

// gWeek[0, n) 을 키 오름차순으로(안정 삽입 정렬, n ≤ 96)
void sortWeek(uint8_t n) {
  for (uint8_t i = 1; i < n; ++i) {
    lc::SlotRec cur;
    std::memcpy(&cur, &gWeek[i], sizeof(cur));
    uint8_t j = i;
    while (j > 0 && cmpSlotKey(gWeek[j - 1], cur.day, cur.sH, cur.sM) > 0) {
      std::memcpy(&gWeek[j], &gWeek[j - 1], sizeof(cur));
      --j;
    }
    std::memcpy(&gWeek[j], &cur, sizeof(cur));
  }
}

bool isPast(const lc::ResvRec& r, Date today) {
  if (r.y != today.y) return r.y < today.y;
  if (r.m != today.m) return r.m < today.m;
  return r.d < today.d;
}

// gResv[0, n) 에서 today 이전 날짜를 지운다. 반환 = 남은 개수.
uint8_t purgeResv(uint8_t n, Date today) {
  uint8_t m = 0;
  for (uint8_t i = 0; i < n; ++i) {
    if (isPast(gResv[i], today)) continue;
    if (m != i) std::memcpy(&gResv[m], &gResv[i], sizeof(lc::ResvRec));
    ++m;
  }
  return m;
}

StoreStatus toStatus(ParseResult pr) {
  if (pr == ParseResult::Ok) return StoreStatus::Ok;
  return pr == ParseResult::Corrupt ? StoreStatus::BadPayload : StoreStatus::StoreFail;
}

}  // namespace

NodeStore::NodeStore(KvStore& kv, FileStore& fs, RtcState& rtc) : kv_(kv), fs_(fs), rtc_(rtc) {}

// /schedule.bin → gWeek. 없으면 빈 표. 읽기 오류(일시적일 수 있음)는 StoreFail 만.
// 손상(Corrupt·OverCapacity)이면 버전 0·RTC 슬롯 캐시 비움 → 다음 STATUS 버전 비교로 서버가 FILE 재동기를
// 건다(v2 §5.1). 파일은 다시 쓰지도 지우지도 않는다 — 빈 표 뒤에 SLOT_SET 이 오면 데이터를 잃고도 새 버전을
// 주장하게 되므로, 덮어쓰기는 재동기(replaceKind)에 맡긴다.
StoreStatus NodeStore::loadWeek(uint8_t& n) {
  n = 0;
  size_t len = 0;
  const ReadResult rr = fs_.read(kSchedPath, gFile, sizeof(gFile), len);
  if (rr == ReadResult::NotFound) return StoreStatus::Ok;
  if (rr != ReadResult::Ok) return StoreStatus::StoreFail;
  if (parseSlots(gFile, static_cast<uint16_t>(len), gWeek, n) != ParseResult::Ok) {
    n = 0;
    (void)kv_.set(kVerSpace, kSchedVerKey, 0);  // best effort — 실패해도 RTC 버전 0 이 STATUS 로 나간다
    rtc_.schedVer = 0;
    std::memset(rtc_.slots, 0, sizeof(rtc_.slots));
    rtc_.nSlots = 0;  // slotsDay 는 유지
    return StoreStatus::StoreFail;
  }
  return StoreStatus::Ok;
}

// gWeek[0, n) 을 파일 → 버전 → RTC(slotsDay 요일만) 순으로 확정한다.
StoreStatus NodeStore::commitSlots(uint8_t newVer, uint8_t n) {
  const size_t len = writeSlots(gWeek, n, gFile, sizeof(gFile));
  if (n > 0 && len == 0) return StoreStatus::StoreFail;
  if (!fs_.writeAtomic(kSchedPath, gFile, len)) return StoreStatus::StoreFail;
  if (!kv_.set(kVerSpace, kSchedVerKey, newVer)) return StoreStatus::StoreFail;
  std::memset(rtc_.slots, 0, sizeof(rtc_.slots));
  rtc_.nSlots = slotsOfDay(gWeek, n, rtc_.slotsDay, rtc_.slots);
  rtc_.schedVer = newVer;
  return StoreStatus::Ok;
}

StoreStatus NodeStore::commitResv(uint8_t newVer, uint8_t n) {
  const size_t len = writeResv(gResv, n, gFile, sizeof(gFile));
  if (n > 0 && len == 0) return StoreStatus::StoreFail;
  if (!fs_.writeAtomic(kResvPath, gFile, len)) return StoreStatus::StoreFail;
  if (!kv_.set(kVerSpace, kResvVerKey, newVer)) return StoreStatus::StoreFail;
  std::memset(rtc_.resv, 0, sizeof(rtc_.resv));
  std::memcpy(rtc_.resv, gResv, n * sizeof(lc::ResvRec));
  rtc_.nResv = n;
  rtc_.resvVer = newVer;
  return StoreStatus::Ok;
}

StoreStatus NodeStore::commitExams(uint8_t newVer, uint8_t n) {
  const size_t len = writeExams(gExam, n, gFile, sizeof(gFile));
  if (n > 0 && len == 0) return StoreStatus::StoreFail;
  if (!fs_.writeAtomic(kExamPath, gFile, len)) return StoreStatus::StoreFail;
  if (!kv_.set(kVerSpace, kExamVerKey, newVer)) return StoreStatus::StoreFail;
  std::memset(rtc_.exams, 0, sizeof(rtc_.exams));
  std::memcpy(rtc_.exams, gExam, n * sizeof(lc::ExamRec));
  rtc_.nExam = n;
  rtc_.examVer = newVer;
  return StoreStatus::Ok;
}

StoreStatus NodeStore::applySlotSet(uint8_t newVer, const lc::SlotRec& rec) {
  uint8_t n = 0;
  const StoreStatus st = loadWeek(n);
  if (st != StoreStatus::Ok) return st;
  const uint8_t pos = lowerBound(n, rec.day, rec.sH, rec.sM);
  if (pos < n && cmpSlotKey(gWeek[pos], rec.day, rec.sH, rec.sM) == 0) {
    std::memcpy(&gWeek[pos], &rec, sizeof(rec));  // 같은 키 → 교체(상한과 무관)
    return commitSlots(newVer, n);
  }
  uint8_t perDay = 0;
  for (uint8_t i = 0; i < n; ++i) {
    if (gWeek[i].day == rec.day) ++perDay;
  }
  if (n >= LP_SLOT_WEEK_MAX || perDay >= LP_SLOT_DAY_MAX) return StoreStatus::StoreFail;
  for (uint8_t i = n; i > pos; --i) std::memcpy(&gWeek[i], &gWeek[i - 1], sizeof(lc::SlotRec));
  std::memcpy(&gWeek[pos], &rec, sizeof(rec));
  return commitSlots(newVer, static_cast<uint8_t>(n + 1));
}

StoreStatus NodeStore::applySlotDel(uint8_t newVer, const lc::SlotDel& del) {
  uint8_t n = 0;
  const StoreStatus st = loadWeek(n);
  if (st != StoreStatus::Ok) return st;
  const uint8_t pos = lowerBound(n, del.day, del.sH, del.sM);
  if (pos < n && cmpSlotKey(gWeek[pos], del.day, del.sH, del.sM) == 0) {
    for (uint8_t i = pos; i + 1 < n; ++i) std::memcpy(&gWeek[i], &gWeek[i + 1], sizeof(lc::SlotRec));
    --n;
  }
  return commitSlots(newVer, n);  // 없는 키도 Ok + 버전 갱신(서버는 삭제에도 버전을 올린다)
}

StoreStatus NodeStore::applyDayClear(uint8_t newVer, const lc::DayClear& dc) {
  uint8_t n = 0;
  const StoreStatus st = loadWeek(n);
  if (st != StoreStatus::Ok) return st;
  uint8_t m = 0;
  for (uint8_t i = 0; i < n; ++i) {
    if (gWeek[i].day == dc.day) continue;
    if (m != i) std::memcpy(&gWeek[m], &gWeek[i], sizeof(lc::SlotRec));
    ++m;
  }
  return commitSlots(newVer, m);
}

StoreStatus NodeStore::applyResvSet(uint8_t newVer, const lc::ResvRec& rec, Date today, bool clockValid) {
  uint8_t n = rtc_.nResv;
  std::memcpy(gResv, rtc_.resv, sizeof(gResv));
  if (clockValid) n = purgeResv(n, today);  // 정리가 상한 검사보다 먼저
  uint8_t pos = 0;
  while (pos < n && gResv[pos].resvId != rec.resvId) ++pos;
  if (pos == n) {
    if (n >= kResvMax) return StoreStatus::StoreFail;
    ++n;
  }
  std::memcpy(&gResv[pos], &rec, sizeof(rec));
  return commitResv(newVer, n);
}

StoreStatus NodeStore::applyResvDel(uint8_t newVer, const lc::ResvDel& del) {
  uint8_t n = 0;
  for (uint8_t i = 0; i < rtc_.nResv; ++i) {
    if (rtc_.resv[i].resvId == del.resvId) continue;
    std::memcpy(&gResv[n++], &rtc_.resv[i], sizeof(lc::ResvRec));
  }
  return commitResv(newVer, n);
}

StoreStatus NodeStore::applyExamSet(uint8_t newVer, const lc::ExamRec& rec) {
  uint8_t n = rtc_.nExam;
  std::memcpy(gExam, rtc_.exams, sizeof(gExam));
  uint8_t pos = 0;
  while (pos < n && gExam[pos].examId != rec.examId) ++pos;
  if (pos == n) {
    if (n >= kExamMax) return StoreStatus::StoreFail;
    ++n;
  }
  std::memcpy(&gExam[pos], &rec, sizeof(rec));
  return commitExams(newVer, n);
}

StoreStatus NodeStore::applyExamDel(uint8_t newVer, const lc::ExamDel& del) {
  uint8_t n = 0;
  for (uint8_t i = 0; i < rtc_.nExam; ++i) {
    if (rtc_.exams[i].examId == del.examId) continue;
    std::memcpy(&gExam[n++], &rtc_.exams[i], sizeof(lc::ExamRec));
  }
  return commitExams(newVer, n);
}

StoreStatus NodeStore::replaceKind(uint8_t kind, uint8_t newVer, const uint8_t* body, uint16_t len,
                                   Date today, bool clockValid) {
  uint8_t n = 0;
  StoreStatus st = StoreStatus::BadPayload;
  switch (kind) {
    case LP_FILEKIND_SCHEDULE:
      st = toStatus(parseSlots(body, len, gWeek, n));
      if (st != StoreStatus::Ok) return st;
      sortWeek(n);
      return commitSlots(newVer, n);
    case LP_FILEKIND_RESV:
      st = toStatus(parseResv(body, len, gResv, n));
      if (st != StoreStatus::Ok) return st;
      if (clockValid) n = purgeResv(n, today);
      return commitResv(newVer, n);
    case LP_FILEKIND_EXAM:
      st = toStatus(parseExams(body, len, gExam, n));
      if (st != StoreStatus::Ok) return st;
      return commitExams(newVer, n);
    default:
      return StoreStatus::BadPayload;  // 모르는 kind
  }
}

// /resv.bin 만 다시 쓰고 버전은 그대로(서버는 이 정리에 버전을 올리지 않는다, v2 §5.1).
StoreStatus NodeStore::purgePast(Date today, bool clockValid) {
  if (!clockValid) return StoreStatus::Ok;
  std::memcpy(gResv, rtc_.resv, sizeof(gResv));
  const uint8_t n = purgeResv(rtc_.nResv, today);
  if (n == rtc_.nResv) return StoreStatus::Ok;  // 지울 것 없음 — 쓰지 않는다
  const size_t len = writeResv(gResv, n, gFile, sizeof(gFile));
  if (n > 0 && len == 0) return StoreStatus::StoreFail;
  if (!fs_.writeAtomic(kResvPath, gFile, len)) return StoreStatus::StoreFail;
  std::memset(rtc_.resv, 0, sizeof(rtc_.resv));
  std::memcpy(rtc_.resv, gResv, n * sizeof(lc::ResvRec));
  rtc_.nResv = n;
  return StoreStatus::Ok;
}

}  // namespace ns
