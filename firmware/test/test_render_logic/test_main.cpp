// dh-04 Task 4.2 — 픽셀을 찍지 않는 렌더 판단. 근거: terminal-epaper.md "상태 띠"·"레이아웃 8종"·"오늘 목록".
#include <unity.h>

#include <initializer_list>

#include "image_data.h"
#include "render_logic.h"

static void setToday(RenderModel& m, uint8_t n) {
  m.nToday = n;
  for (uint8_t i = 0; i < n && i < 24; i++) {
    m.today[i].sH = (uint8_t)(8 + i / 2);
    m.today[i].sM = (uint8_t)((i % 2) * 30);
    m.today[i].eH = m.today[i].sH;
    m.today[i].eM = (uint8_t)(m.today[i].sM + 25);
  }
}

static void pointAt(RenderSlot& s, const TodaySlot& t) {
  s.sH = t.sH;
  s.sM = t.sM;
  s.eH = t.eH;
  s.eM = t.eM;
  s.flags = 1;
}

void test_band_style_per_layout() {
  TEST_ASSERT_EQUAL(BandStyle::Red, bandStyle(1));
  TEST_ASSERT_EQUAL(BandStyle::Black, bandStyle(2));
  TEST_ASSERT_EQUAL(BandStyle::Black, bandStyle(3));
  TEST_ASSERT_EQUAL(BandStyle::Black, bandStyle(4));
  TEST_ASSERT_EQUAL(BandStyle::Red, bandStyle(5));
  TEST_ASSERT_EQUAL(BandStyle::Red, bandStyle(6));
  TEST_ASSERT_EQUAL(BandStyle::Red, bandStyle(7));
  TEST_ASSERT_EQUAL(BandStyle::None, bandStyle(8));
  TEST_ASSERT_EQUAL(BandStyle::None, bandStyle(0));
}

void test_status_image_per_layout() {
  TEST_ASSERT_EQUAL_PTR(&kImgStatusSueopjung, statusImage(1));
  TEST_ASSERT_EQUAL_PTR(&kImgStatusSwineunsigan, statusImage(2));
  TEST_ASSERT_EQUAL_PTR(&kImgStatusHyugang, statusImage(3));
  TEST_ASSERT_EQUAL_PTR(&kImgStatusBinganguisil, statusImage(4));
  TEST_ASSERT_EQUAL_PTR(&kImgStatusSiheomjung, statusImage(5));
  TEST_ASSERT_EQUAL_PTR(&kImgStatusTeukgang, statusImage(6));
  TEST_ASSERT_EQUAL_PTR(&kImgStatusDaeyeojung, statusImage(7));
  TEST_ASSERT_NULL(statusImage(8));
  TEST_ASSERT_NULL(statusImage(0));
}

void test_weekday_names() {
  TEST_ASSERT_EQUAL_STRING("월요일", weekdayName(1));
  TEST_ASSERT_EQUAL_STRING("일요일", weekdayName(7));
  TEST_ASSERT_EQUAL_STRING("", weekdayName(0));
  TEST_ASSERT_EQUAL_STRING("", weekdayName(8));
}

void test_type_chips() {
  TEST_ASSERT_NULL(typeChip(1));  // 수업은 생략
  TEST_ASSERT_EQUAL_PTR(&kImgChipSiheom, typeChip(2));
  TEST_ASSERT_EQUAL_PTR(&kImgChipHyugang, typeChip(3));
  TEST_ASSERT_NULL(typeChip(4));  // 빈강의실은 today[] 에 오지 않는다
  TEST_ASSERT_EQUAL_PTR(&kImgChipTeukgang, typeChip(5));
  TEST_ASSERT_EQUAL_PTR(&kImgChipDaeyeo, typeChip(6));
}

void test_format_hm_pads_zero() {
  char s[6];
  formatHM(9, 5, s, sizeof s);
  TEST_ASSERT_EQUAL_STRING("09:05", s);
}

void test_subline_in_use_states_uses_cur_end() {
  RenderModel m{};
  m.cur.eH = 15;
  m.cur.eM = 0;
  m.cur.flags = 1;
  char s[32];
  for (uint8_t layout : {1, 5, 6, 7}) {
    m.layout = layout;
    TEST_ASSERT_TRUE(statusSubline(m, s, sizeof s));
    TEST_ASSERT_EQUAL_STRING("15:00에 끝납니다", s);
  }
}

void test_subline_break_uses_next_start() {
  RenderModel m{};
  m.layout = 2;
  m.next.sH = 14;
  m.next.flags = 1;
  char s[32];
  TEST_ASSERT_TRUE(statusSubline(m, s, sizeof s));
  TEST_ASSERT_EQUAL_STRING("14:00 수업 재개", s);
}

void test_subline_cancel_and_empty() {
  RenderModel m{};
  char s[32];
  m.layout = 3;
  TEST_ASSERT_TRUE(statusSubline(m, s, sizeof s));
  TEST_ASSERT_EQUAL_STRING("오늘 휴강입니다", s);
  m.layout = 4;
  TEST_ASSERT_FALSE(statusSubline(m, s, sizeof s));
  TEST_ASSERT_EQUAL_STRING("", s);
}

void test_subline_missing_slot_is_empty() {
  RenderModel m{};
  m.layout = 1;  // cur.flags bit0 = 0
  char s[32];
  TEST_ASSERT_FALSE(statusSubline(m, s, sizeof s));
  TEST_ASSERT_EQUAL_STRING("", s);
}

void test_window_short_list_shows_all() {
  RenderModel m{};
  setToday(m, 5);
  pointAt(m.cur, m.today[2]);
  const TodayWindow w = todayWindow(m);
  TEST_ASSERT_EQUAL_UINT8(5, w.count);
  TEST_ASSERT_EQUAL_UINT8(0, w.start);
  TEST_ASSERT_EQUAL_UINT8(5, w.rows);
  TEST_ASSERT_EQUAL_UINT8(0, w.moreAbove);
  TEST_ASSERT_EQUAL_UINT8(0, w.moreBelow);
  TEST_ASSERT_EQUAL_INT8(2, w.curIdx);
}

void test_window_cur_at_top_hides_below() {
  RenderModel m{};
  setToday(m, 12);
  pointAt(m.cur, m.today[0]);
  const TodayWindow w = todayWindow(m);
  TEST_ASSERT_EQUAL_UINT8(0, w.start);
  TEST_ASSERT_EQUAL_UINT8(9, w.rows);
  TEST_ASSERT_EQUAL_UINT8(0, w.moreAbove);
  TEST_ASSERT_EQUAL_UINT8(4, w.moreBelow);  // 항목 8~11 이 숨는다(8은 "↓ 4개 더" 행 자리)
}

void test_window_clamps_to_end() {
  RenderModel m{};
  setToday(m, 12);
  pointAt(m.cur, m.today[6]);
  const TodayWindow w = todayWindow(m);
  TEST_ASSERT_EQUAL_UINT8(3, w.start);      // clamp(6-1, 0, 12-9) = 3
  TEST_ASSERT_EQUAL_UINT8(4, w.moreAbove);  // 항목 0~3
  TEST_ASSERT_EQUAL_UINT8(0, w.moreBelow);
  TEST_ASSERT_EQUAL_INT8(6, w.curIdx);
}

void test_window_both_sides_cut_shows_seven() {
  RenderModel m{};
  setToday(m, 20);
  pointAt(m.cur, m.today[10]);
  const TodayWindow w = todayWindow(m);
  TEST_ASSERT_EQUAL_UINT8(9, w.start);
  TEST_ASSERT_EQUAL_UINT8(10, w.moreAbove);  // 항목 0~9
  TEST_ASSERT_EQUAL_UINT8(3, w.moreBelow);   // 항목 17~19
}

void test_window_clamps_count_to_24() {
  RenderModel m{};
  setToday(m, 24);
  m.nToday = 30;  // 손상된 값
  const TodayWindow w = todayWindow(m);
  TEST_ASSERT_EQUAL_UINT8(24, w.count);
  TEST_ASSERT_TRUE(w.start + w.rows <= 24);
}

void test_window_cur_not_in_today_uses_next() {
  RenderModel m{};
  setToday(m, 20);
  m.cur.flags = 1;
  m.cur.sH = 23;  // today[] 에 없는 시각
  pointAt(m.next, m.today[15]);
  const TodayWindow w = todayWindow(m);
  TEST_ASSERT_EQUAL_INT8(-1, w.curIdx);  // 반전 행 없음
  TEST_ASSERT_EQUAL_UINT8(11, w.start);  // clamp(15-1, 0, 11) = 11
}

void test_window_no_cur_no_next_starts_at_top() {
  RenderModel m{};
  setToday(m, 12);
  const TodayWindow w = todayWindow(m);
  TEST_ASSERT_EQUAL_UINT8(0, w.start);
  TEST_ASSERT_EQUAL_INT8(-1, w.curIdx);
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_band_style_per_layout);
  RUN_TEST(test_status_image_per_layout);
  RUN_TEST(test_weekday_names);
  RUN_TEST(test_type_chips);
  RUN_TEST(test_format_hm_pads_zero);
  RUN_TEST(test_subline_in_use_states_uses_cur_end);
  RUN_TEST(test_subline_break_uses_next_start);
  RUN_TEST(test_subline_cancel_and_empty);
  RUN_TEST(test_subline_missing_slot_is_empty);
  RUN_TEST(test_window_short_list_shows_all);
  RUN_TEST(test_window_cur_at_top_hides_below);
  RUN_TEST(test_window_clamps_to_end);
  RUN_TEST(test_window_both_sides_cut_shows_seven);
  RUN_TEST(test_window_clamps_count_to_24);
  RUN_TEST(test_window_cur_not_in_today_uses_next);
  RUN_TEST(test_window_no_cur_no_next_starts_at_top);
  return UNITY_END();
}
