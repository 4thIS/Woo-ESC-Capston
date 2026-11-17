#include "schedule.h"

#include "kst_time.h"
#include "proto.h"

namespace sch {

namespace {

constexpr uint32_t kDaySec = 24u * 3600u;

uint8_t typeToLayout(uint8_t type) {
  switch (type) {
    case LP_SLOTTYPE_CLASS:
      return LP_LAYOUT_CLASS;
    case LP_SLOTTYPE_EXAM:
      return LP_LAYOUT_EXAM;
    case LP_SLOTTYPE_CANCELLED:
      return LP_LAYOUT_CANCELLED;
    case LP_SLOTTYPE_EMPTY:
      return LP_LAYOUT_EMPTY;
    case LP_SLOTTYPE_SPECIAL:
      return LP_LAYOUT_SPECIAL;
    case LP_SLOTTYPE_RENTAL:
      return LP_LAYOUT_RENTAL;
    default:
      return LP_LAYOUT_EMPTY;
  }
}

uint16_t startMin(uint8_t h, uint8_t m) {
  return static_cast<uint16_t>(h * 60 + m);
}

// 날짜 비교용 정수 YYYYMMDD (y = 전체 연도).
uint32_t dateKey(uint32_t y, uint8_t m, uint8_t d) {
  return y * 10000u + m * 100u + d;
}

// 그 날의 판정 문맥. 오늘이 아닌 슬롯·예약은 걸러서 본다.
struct Today {
  KstTime t;
  uint32_t key;
  bool inExam;
};

Today today(const ScheduleView& v, uint32_t nowEpoch) {
  Today d{toKst(nowEpoch), 0, false};
  d.key = dateKey(d.t.year, d.t.month, d.t.day);
  for (uint8_t i = 0; i < v.nExam; ++i) {
    const lc::ExamRec& x = v.exams[i];
    if (dateKey(2000u + x.y1, x.m1, x.d1) <= d.key && d.key <= dateKey(2000u + x.y2, x.m2, x.d2))
      d.inExam = true;
  }
  return d;
}

bool slotToday(const ScheduleView& v, const Today& d, uint8_t i) {
  return v.slots[i].day == d.t.weekday;
}

bool resvToday(const ScheduleView& v, const Today& d, uint8_t i) {
  const lc::ResvRec& r = v.resv[i];
  return dateKey(2000u + r.y, r.m, r.d) == d.key;
}

// 분 t 의 상태 (_ref 의 _state 와 같은 순서).
LayoutDecision stateAt(const ScheduleView& v, const Today& d, uint16_t t) {
  for (uint8_t i = 0; i < v.nResv; ++i) {  // 1. 예약
    if (!resvToday(v, d, i)) continue;
    const lc::ResvRec& r = v.resv[i];
    const uint16_t s = startMin(r.sH, r.sM);
    if (s <= t && t < startMin(r.eH, r.eM)) return {typeToLayout(r.type), Decider::Resv, i, d.t.weekday, s};
  }
  for (uint8_t i = 0; i < v.nSlots; ++i) {  // 2. 슬롯 안 (시험기간이면 시험)
    if (!slotToday(v, d, i)) continue;
    const lc::SlotRec& sl = v.slots[i];
    const uint16_t s = startMin(sl.sH, sl.sM);
    if (s <= t && t < startMin(sl.eH, sl.eM)) {
      if (d.inExam) return {LP_LAYOUT_EXAM, Decider::ExamSlot, i, d.t.weekday, s};
      return {typeToLayout(sl.type), Decider::Slot, i, d.t.weekday, s};
    }
  }
  // 3. 시작 순 인접 수업 슬롯 사이 틈 (0, LP_BREAK_GAP_MAX_MIN] → 쉬는시간. 같은 시작은 원래 순서(안정 정렬).
  uint8_t ord[255];
  uint8_t n = 0;
  for (uint8_t i = 0; i < v.nSlots; ++i) {
    if (!slotToday(v, d, i)) continue;
    const uint16_t s = startMin(v.slots[i].sH, v.slots[i].sM);
    uint8_t k = n++;
    while (k > 0 && startMin(v.slots[ord[k - 1]].sH, v.slots[ord[k - 1]].sM) > s) {
      ord[k] = ord[k - 1];
      --k;
    }
    ord[k] = i;
  }
  for (uint8_t k = 0; k + 1 < n; ++k) {
    const lc::SlotRec& a = v.slots[ord[k]];
    const lc::SlotRec& b = v.slots[ord[k + 1]];
    const int ae = startMin(a.eH, a.eM);
    const int bs = startMin(b.sH, b.sM);
    const int gap = bs - ae;
    if (a.type == LP_SLOTTYPE_CLASS && b.type == LP_SLOTTYPE_CLASS && gap > 0 &&
        gap <= LP_BREAK_GAP_MAX_MIN && ae <= t && t < bs)
      return {LP_LAYOUT_BREAK, Decider::Break, ord[k + 1], d.t.weekday, static_cast<uint16_t>(bs)};
  }
  return {LP_LAYOUT_EMPTY, Decider::Free, 0xFF, d.t.weekday, kNoSlot};  // 4. 빈강의실
}

bool sameState(const LayoutDecision& a, const LayoutDecision& b) {
  return a.layout == b.layout && a.by == b.by && a.index == b.index;
}

void takeMin(uint32_t& best, uint32_t c, uint32_t nowEpoch) {
  if (c > nowEpoch && c < best) best = c;
}

}  // namespace

LayoutDecision determineLayout(const ScheduleView& v, uint32_t nowEpoch) {
  const Today d = today(v, nowEpoch);
  return stateAt(v, d, minuteOfDay(d.t));
}

uint32_t nextChangeAt(const ScheduleView& v, uint32_t nowEpoch, uint32_t nextStatusEpoch) {
  const Today d = today(v, nowEpoch);
  const uint16_t nowMin = minuteOfDay(d.t);
  const uint32_t midnight = kstMidnight(d.t.year, d.t.month, d.t.day);
  const LayoutDecision now = stateAt(v, d, nowMin);

  uint32_t best = midnight + kDaySec;  // 다음 자정 — 항상 후보라 "now + 24 h" 분기는 없다

  // 오늘 상태 경계: 오늘 슬롯·예약의 시작·끝 중 now 뒤에서 가장 이른, 상태가 바뀌는 분.
  uint16_t boundary = kNoSlot;
  auto consider = [&](uint16_t b) {
    if (b > nowMin && b < boundary && !sameState(stateAt(v, d, b), now)) boundary = b;
  };
  for (uint8_t i = 0; i < v.nSlots; ++i) {
    if (!slotToday(v, d, i)) continue;
    consider(startMin(v.slots[i].sH, v.slots[i].sM));
    consider(startMin(v.slots[i].eH, v.slots[i].eM));
  }
  for (uint8_t i = 0; i < v.nResv; ++i) {
    if (!resvToday(v, d, i)) continue;
    consider(startMin(v.resv[i].sH, v.resv[i].sM));
    consider(startMin(v.resv[i].eH, v.resv[i].eM));
  }
  if (boundary != kNoSlot) takeMin(best, midnight + boundary * 60u, nowEpoch);

  for (uint8_t i = 0; i < v.nExam; ++i) {
    const lc::ExamRec& x = v.exams[i];
    takeMin(best, kstMidnight(2000u + x.y1, x.m1, x.d1), nowEpoch);
    takeMin(best, kstMidnight(2000u + x.y2, x.m2, x.d2) + kDaySec, nowEpoch);
  }
  takeMin(best, nextStatusEpoch, nowEpoch);
  return best + 2;
}

}  // namespace sch
