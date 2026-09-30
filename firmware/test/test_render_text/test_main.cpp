// dh-04 Task 4.1 — UTF-8 해석과 한 줄 그리기.
#include <unity.h>

#include "font_data.h"
#include "host_gfx.h"
#include "text.h"

static int16_t adv(const BitmapFont& f, uint32_t cp) {
  return f.advances[bfFindGlyph(f, cp)];
}

static int countColor(const HostGfx& g, int x0, int y0, int x1, int y1, HColor c) {
  int n = 0;
  for (int y = y0; y < y1; y++)
    for (int x = x0; x < x1; x++)
      if (g.pixelAt((int16_t)x, (int16_t)y) == c) n++;
  return n;
}

void test_ascii_and_multibyte_decode() {
  const char* p = "A\xC2\xB7\xEA\xB0\x80";  // 'A', '·'(U+00B7), '가'(U+AC00)
  TEST_ASSERT_EQUAL_UINT32('A', utf8Next(p));
  TEST_ASSERT_EQUAL_UINT32(0x00B7, utf8Next(p));
  TEST_ASSERT_EQUAL_UINT32(0xAC00, utf8Next(p));
  TEST_ASSERT_EQUAL_UINT32(0, utf8Next(p));
}

void test_truncated_multibyte_stops_at_nul() {
  // '가'의 앞 2바이트만 있고 NUL. 그 뒤의 'A'를 읽으면 버퍼 밖 접근이다.
  const char buf[] = {(char)0xEA, (char)0xB0, 0, 'A'};
  const char* p = buf;
  TEST_ASSERT_EQUAL_UINT32('?', utf8Next(p));  // 잘린 글자 자리에 '?' 하나 — 고아 연속 바이트도 함께 넘긴다
  TEST_ASSERT_EQUAL_UINT32(0, utf8Next(p));    // NUL 에서 멈춘다 — 'A'를 읽지 않는다
}

void test_orphan_continuation_bytes_give_single_question_mark() {
  const char buf[] = {(char)0xB0, (char)0xB1, 'A', 0};  // 리드 자리에 연속 바이트가 연달아 온다
  const char* p = buf;
  TEST_ASSERT_EQUAL_UINT32('?', utf8Next(p));
  TEST_ASSERT_EQUAL_UINT32('A', utf8Next(p));
  TEST_ASSERT_EQUAL_UINT32(0, utf8Next(p));
}

void test_width_is_sum_of_advances() {
  const int16_t expected = adv(kNanum20Regular, 0xAC00) + adv(kNanum20Regular, 0xB098);  // 가, 나
  TEST_ASSERT_EQUAL_INT16(expected, textWidth(kNanum20Regular, "가나"));
}

void test_tracking_applies_between_glyphs_only() {
  const int16_t plain = textWidth(kNanum20Regular, "가나");
  TEST_ASSERT_EQUAL_INT16(plain - 1, textWidth(kNanum20Regular, "가나", -1));
  TEST_ASSERT_EQUAL_INT16(adv(kNanum20Regular, 0xAC00), textWidth(kNanum20Regular, "가", -1));
}

void test_unknown_glyph_is_skipped() {
  // '똠'(U+B620)은 KS X 1001 밖이라 charset.txt 에 없다.
  TEST_ASSERT_EQUAL_INT16(textWidth(kNanum20Regular, "가나"), textWidth(kNanum20Regular, "가똠나"));
}

void test_empty_string_has_zero_width() {
  TEST_ASSERT_EQUAL_INT16(0, textWidth(kNanum20Regular, ""));
}

void test_draw_returns_width_and_paints_from_x() {
  HostGfx g;
  const int16_t w = drawText(g, kNanum20Regular, "가나", 100, 100, GxEPD_BLACK);
  TEST_ASSERT_EQUAL_INT16(textWidth(kNanum20Regular, "가나"), w);
  TEST_ASSERT_GREATER_THAN_INT(20, countColor(g, 100, 80, 100 + w, 104, HColor::BLACK));
  TEST_ASSERT_EQUAL_INT(0, countColor(g, 0, 0, 100, 480, HColor::BLACK));  // x 왼쪽은 건드리지 않는다
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_ascii_and_multibyte_decode);
  RUN_TEST(test_truncated_multibyte_stops_at_nul);
  RUN_TEST(test_orphan_continuation_bytes_give_single_question_mark);
  RUN_TEST(test_width_is_sum_of_advances);
  RUN_TEST(test_tracking_applies_between_glyphs_only);
  RUN_TEST(test_unknown_glyph_is_skipped);
  RUN_TEST(test_empty_string_has_zero_width);
  RUN_TEST(test_draw_returns_width_and_paints_from_x);
  return UNITY_END();
}
