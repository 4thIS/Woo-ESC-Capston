// dh-04 Task 4.3 — 화면 픽셀 테스트. 좌표 근거: terminal-epaper.md "골격"·"영역별 규격".
#include <unity.h>

#include <cstring>
#include <initializer_list>

#include "host_gfx.h"
#include "render.h"

static int countColor(const HostGfx& g, int x0, int y0, int x1, int y1, HColor c) {
  int n = 0;
  for (int y = y0; y < y1; y++)
    for (int x = x0; x < x1; x++)
      if (g.pixelAt((int16_t)x, (int16_t)y) == c) n++;
  return n;
}

static void setSlot(TodaySlot& t, uint8_t sH, uint8_t eH, const char* subj, uint8_t type) {
  t.sH = sH;
  t.sM = 0;
  t.eH = eH;
  t.eM = 50;
  strcpy(t.subj, subj);
  t.type = type;
}

// layout 1 기본 모델: 오늘 3개, 현재 = 1번(13:00 캡스톤디자인), 2번은 시험.
static RenderModel layout1Model() {
  RenderModel m{};
  m.layout = 1;
  m.bld = 'E';
  m.room = 301;
  m.unit = 1;
  m.weekday = 2;
  strcpy(m.cur.subj, "캡스톤디자인");
  strcpy(m.cur.prof, "김교수");
  m.cur.sH = 13;
  m.cur.eH = 14;
  m.cur.eM = 50;
  m.cur.type = 1;
  m.cur.flags = 1;
  m.nToday = 3;
  setSlot(m.today[0], 9, 10, "자료구조", 1);
  setSlot(m.today[1], 13, 14, "캡스톤디자인", 1);
  setSlot(m.today[2], 15, 16, "웹프로그래밍", 2);
  return m;
}

void test_skeleton_lines_and_footer() {
  HostGfx g;
  renderLayout(g, layout1Model());
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(400, 50));  // 헤더 하단선 y 50–51
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(400, 51));
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(498, 300));  // 좌우 분할 x 498–499
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(499, 300));
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(790, 470));                              // 푸터 흑 바탕
  TEST_ASSERT_GREATER_THAN_INT(30, countColor(g, 24, 445, 200, 478, HColor::WHITE));  // 푸터 흰 글자
}

void test_header_room_and_weekday() {
  HostGfx g;
  renderLayout(g, layout1Model());
  TEST_ASSERT_GREATER_THAN_INT(50, countColor(g, 24, 5, 120, 48, HColor::BLACK));   // "301 호"
  TEST_ASSERT_GREATER_THAN_INT(20, countColor(g, 690, 5, 777, 48, HColor::BLACK));  // "화요일"
}

void test_red_band_with_white_text() {
  HostGfx g;
  renderLayout(g, layout1Model());
  TEST_ASSERT_EQUAL(HColor::RED, g.pixelAt(10, 60));
  TEST_ASSERT_EQUAL(HColor::RED, g.pixelAt(490, 210));
  TEST_ASSERT_GREATER_THAN_INT(500, countColor(g, 0, 52, 498, 216, HColor::WHITE));  // 상태명 + 보조 문구
  TEST_ASSERT_EQUAL_INT(0, countColor(g, 0, 52, 498, 216, HColor::BLACK));  // RED 띠에는 흑 글자·하단선 없음
}

void test_black_band_has_bottom_line() {
  RenderModel m = layout1Model();
  m.layout = 2;  // 쉬는시간 — BLACK
  m.next.sH = 14;
  m.next.flags = 1;
  HostGfx g;
  renderLayout(g, m);
  TEST_ASSERT_EQUAL(HColor::WHITE, g.pixelAt(10, 60));
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(10, 214));
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(10, 215));
  TEST_ASSERT_EQUAL_INT(0, countColor(g, 0, 0, 800, 480, HColor::RED));
}

void test_info_form_a_dividers_and_values() {
  HostGfx g;
  renderLayout(g, layout1Model());
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(300, 291));
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(300, 365));
  TEST_ASSERT_GREATER_THAN_INT(40, countColor(g, 24, 240, 128, 290, HColor::BLACK));   // 라벨 "과목명"
  TEST_ASSERT_GREATER_THAN_INT(80, countColor(g, 146, 235, 480, 290, HColor::BLACK));  // 값 "캡스톤디자인"
}

void test_today_current_row_inverted() {
  HostGfx g;
  renderLayout(g, layout1Model());
  // 목록 행: y 100 + 36·r. 1행(13:00)이 현재 행.
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(795, 137));
  TEST_ASSERT_EQUAL(HColor::WHITE, g.pixelAt(795, 101));
  TEST_ASSERT_GREATER_THAN_INT(30, countColor(g, 518, 136, 780, 172, HColor::WHITE));  // 반전 행 흰 글자
}

void test_today_type_chip_right_aligned() {
  HostGfx g;
  renderLayout(g, layout1Model());
  // 2행(15:00, 시험) 오른쪽 끝(x 782 이전)에 칩 글자.
  TEST_ASSERT_GREATER_THAN_INT(10, countColor(g, 740, 172, 782, 208, HColor::BLACK));
}

void test_today_empty_message() {
  RenderModel m = layout1Model();
  m.nToday = 0;
  HostGfx g;
  renderLayout(g, m);
  TEST_ASSERT_GREATER_THAN_INT(30, countColor(g, 518, 100, 760, 136, HColor::BLACK));  // "오늘 일정 없음"
  TEST_ASSERT_EQUAL(HColor::WHITE, g.pixelAt(795, 137));                               // 반전 행 없음
}

void test_today_overflow_shows_more_rows() {
  RenderModel m = layout1Model();
  m.nToday = 12;
  for (uint8_t i = 0; i < 12; i++) setSlot(m.today[i], (uint8_t)(8 + i), (uint8_t)(8 + i), "자료구조", 1);
  m.cur.sH = 14;  // today[6] = 14:00
  m.cur.eH = 14;
  HostGfx g;
  renderLayout(g, m);
  // start = clamp(6-1, 0, 3) = 3 → 0행 "↑ 4개 더", 현재 항목 6 은 3행(y 208).
  TEST_ASSERT_GREATER_THAN_INT(10, countColor(g, 518, 100, 640, 136, HColor::BLACK));
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(795, 209));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_skeleton_lines_and_footer);
  RUN_TEST(test_header_room_and_weekday);
  RUN_TEST(test_red_band_with_white_text);
  RUN_TEST(test_black_band_has_bottom_line);
  RUN_TEST(test_info_form_a_dividers_and_values);
  RUN_TEST(test_today_current_row_inverted);
  RUN_TEST(test_today_type_chip_right_aligned);
  RUN_TEST(test_today_empty_message);
  RUN_TEST(test_today_overflow_shows_more_rows);
  return UNITY_END();
}
