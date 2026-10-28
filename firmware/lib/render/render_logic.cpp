#include "render_logic.h"

#include <cstdio>

#include "image_data.h"

namespace {
constexpr uint8_t kMaxToday = 24;
constexpr uint8_t kMaxRows = 9;

bool sameTimes(const TodaySlot& t, const RenderSlot& s) {
  return t.sH == s.sH && t.sM == s.sM && t.eH == s.eH && t.eM == s.eM;
}

// s 가 존재(flags bit0)하고 today[0..count) 에 같은 시각 항목이 있으면 그 인덱스, 아니면 -1.
int8_t findSlot(const RenderModel& m, uint8_t count, const RenderSlot& s) {
  if (!(s.flags & 0x01)) return -1;
  for (uint8_t i = 0; i < count; i++)
    if (sameTimes(m.today[i], s)) return (int8_t)i;
  return -1;
}
}  // namespace

BandStyle bandStyle(uint8_t layout) {
  switch (layout) {
    case 1:
    case 5:
    case 6:
    case 7:
      return BandStyle::Red;
    case 2:
    case 3:
    case 4:
      return BandStyle::Black;
    default:
      return BandStyle::None;
  }
}

const BitmapImage* statusImage(uint8_t layout) {
  switch (layout) {
    case 1:
      return &kImgStatusSueopjung;
    case 2:
      return &kImgStatusSwineunsigan;
    case 3:
      return &kImgStatusHyugang;
    case 4:
      return &kImgStatusBinganguisil;
    case 5:
      return &kImgStatusSiheomjung;
    case 6:
      return &kImgStatusTeukgang;
    case 7:
      return &kImgStatusDaeyeojung;
    default:
      return nullptr;
  }
}

const char* weekdayName(uint8_t weekday) {
  static const char* const kNames[] = {"월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"};
  if (weekday < 1 || weekday > 7) return "";
  return kNames[weekday - 1];
}

const BitmapImage* typeChip(uint8_t type) {
  switch (type) {
    case 2:
      return &kImgChipSiheom;
    case 3:
      return &kImgChipHyugang;
    case 5:
      return &kImgChipTeukgang;
    case 6:
      return &kImgChipDaeyeo;
    default:
      return nullptr;
  }
}

void formatHM(uint8_t h, uint8_t m, char* out, size_t cap) {
  snprintf(out, cap, "%02u:%02u", (unsigned)h, (unsigned)m);
}

bool statusSubline(const RenderModel& m, char* out, size_t cap) {
  out[0] = '\0';
  char hm[6];
  switch (m.layout) {
    case 1:
    case 5:
    case 6:
    case 7:
      if (!(m.cur.flags & 0x01)) return false;
      formatHM(m.cur.eH, m.cur.eM, hm, sizeof hm);
      snprintf(out, cap, "%s에 끝납니다", hm);
      return true;
    case 2:
      if (!(m.next.flags & 0x01)) return false;
      formatHM(m.next.sH, m.next.sM, hm, sizeof hm);
      snprintf(out, cap, "%s 수업 재개", hm);
      return true;
    case 3:
      snprintf(out, cap, "%s", "오늘 휴강입니다");
      return true;
    default:
      return false;
  }
}

TodayWindow todayWindow(const RenderModel& m) {
  TodayWindow w{};
  w.count = m.nToday > kMaxToday ? kMaxToday : m.nToday;
  w.curIdx = findSlot(m, w.count, m.cur);
  if (w.count <= kMaxRows) {
    w.rows = w.count;
    return w;
  }
  // 창 기준: 현재 항목, 없으면 다음 예정 항목, 둘 다 없으면 처음(⚠️ 계획서 "열린 질문" 2).
  int anchor = w.curIdx >= 0 ? w.curIdx : findSlot(m, w.count, m.next);
  if (anchor < 0) anchor = 0;
  int s = anchor - 1;
  if (s < 0) s = 0;
  if (s > w.count - kMaxRows) s = w.count - kMaxRows;
  w.start = (uint8_t)s;
  w.rows = kMaxRows;
  w.moreAbove = w.start > 0 ? (uint8_t)(w.start + 1) : 0;
  w.moreBelow = (w.start + kMaxRows < w.count) ? (uint8_t)(w.count - (w.start + kMaxRows - 1)) : 0;
  return w;
}
