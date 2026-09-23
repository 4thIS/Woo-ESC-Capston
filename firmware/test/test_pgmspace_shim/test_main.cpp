// dh-04 Task 2 회귀 테스트: v1 렌더 코드를 이식하기 전에, v1 폰트·이미지 헤더가 요구하는
// 호스트 심(shim) 두 가지가 실제로 동작하는지 확인한다.
//   (1) <pgmspace.h> 단독 include — v1 의 폰트·이미지 헤더 6개가 전부 이 이름을 직접 쓴다.
//   (2) GxEPD_BLACK 등 GxEPD2 색상 상수 — v1 의 ngDrawChar/ngPrintLine 이 기본 인자로 쓴다.
// 이 파일은 일부러 <pgmspace.h> 를 **맨 처음** include 한다. WProgram.h 가 먼저 들어와야만
// PROGMEM/pgm_read_byte 가 생기는 상태였다면 여기서 컴파일이 깨진다.
#include <pgmspace.h>
#include <unity.h>

#include "host_gfx.h"  // GxEPD_BLACK 매크로 + HostGfx. WProgram.h 를 전이적으로 끌고 온다
                       // → pgmspace.h → WProgram.h 순서에서 재정의 충돌이 없음도 함께 증명한다.

// 반대 순서(WProgram.h → pgmspace.h)는 별도 번역 단위(reverse_include_order.cpp)에서 본다.
// 그 파일이 컴파일된다는 것 자체가 검증이고, 아래 함수는 그 TU 의 PROGMEM 읽기를 확인한다.
void test_reverse_include_order_compiles();

// ---------------------------------------------------------------------------
// (1) v1 폰트 헤더의 PROGMEM 배열 패턴
// ---------------------------------------------------------------------------

// v1 AsciiGlyphs.h 의 실제 형태: `static const uint8_t NAME[] PROGMEM = {...}`
// (선언자 뒤에 PROGMEM 이 온다 — 앞에 오는 형태도 함께 쓰이므로 둘 다 확인한다.)
static const uint8_t kGlyphRow[] PROGMEM = {0x1E, 0x3E, 0x00};
static const uint8_t PROGMEM kGlyphRowPrefix[] = {0x01, 0x02, 0x03};
// 주의: pgm_read_word/dword 는 대상을 각각 `unsigned short`·`unsigned long` 으로 역참조한다
// (WProgram.h·벤더 Adafruit_GFX.cpp 의 폴백 정의와 동일 — 상류 관례라 바꾸지 않는다).
// `unsigned long` 은 리눅스 CI(LP64)에서 8바이트라 uint32_t 배열에 쓰면 범위 밖을 읽는다.
// 그래서 여기선 배열 타입을 매크로가 읽는 타입에 그대로 맞춘다.
static const unsigned short kWidths[] PROGMEM = {10, 14};
static const unsigned long kOffsets[] PROGMEM = {0ul, 88ul};

void test_pgm_read_byte_reads_progmem_array() {
  TEST_ASSERT_EQUAL_HEX8(0x3E, pgm_read_byte(&kGlyphRow[1]));
  TEST_ASSERT_EQUAL_HEX8(0x02, pgm_read_byte(&kGlyphRowPrefix[1]));
}

void test_pgm_read_word_and_dword() {
  TEST_ASSERT_EQUAL_UINT16(14, pgm_read_word(&kWidths[1]));
  TEST_ASSERT_EQUAL_UINT32(88u, pgm_read_dword(&kOffsets[1]));
}

// ---------------------------------------------------------------------------
// (2) GxEPD2 색상 매크로
// ---------------------------------------------------------------------------

void test_gxepd_macros_match_hcolor() {
  TEST_ASSERT_EQUAL_HEX16((uint16_t)HColor::WHITE, GxEPD_WHITE);
  TEST_ASSERT_EQUAL_HEX16((uint16_t)HColor::BLACK, GxEPD_BLACK);
  TEST_ASSERT_EQUAL_HEX16((uint16_t)HColor::RED, GxEPD_RED);
}

// ---------------------------------------------------------------------------
// (3) v1 패턴 스모크 — Task 3/4 에서 진짜 폰트를 이식하기 전 마지막 안전장치
// ---------------------------------------------------------------------------

// v1 KoreanFont.h 의 ngDrawChar 시그니처를 최소로 재현한다:
// GFX 템플릿 + `uint16_t color = GxEPD_BLACK` 기본 인자 + PROGMEM 비트맵 읽기.
template <typename GFX>
void fakeNgDrawChar(GFX& d, int16_t x, int16_t y, uint16_t color = GxEPD_BLACK) {
  uint8_t bits = pgm_read_byte(&kGlyphRow[0]);  // 0x1E = 0b00011110
  for (int bit = 0; bit < 8; bit++) {
    if (bits & (0x80 >> bit)) d.drawPixel(x + bit, y, color);
  }
}

void test_v1_default_color_arg_draws_black() {
  HostGfx g;
  fakeNgDrawChar(g, 0, 0);                            // color 생략 → GxEPD_BLACK
  TEST_ASSERT_EQUAL(HColor::WHITE, g.pixelAt(2, 0));  // 0x1E 의 상위 3비트는 0
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(3, 0));
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(6, 0));
  TEST_ASSERT_EQUAL(HColor::WHITE, g.pixelAt(7, 0));
}

void test_v1_explicit_color_arg_still_works() {
  HostGfx g;
  fakeNgDrawChar(g, 0, 1, GxEPD_RED);
  TEST_ASSERT_EQUAL(HColor::RED, g.pixelAt(3, 1));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_pgm_read_byte_reads_progmem_array);
  RUN_TEST(test_pgm_read_word_and_dword);
  RUN_TEST(test_gxepd_macros_match_hcolor);
  RUN_TEST(test_v1_default_color_arg_draws_black);
  RUN_TEST(test_v1_explicit_color_arg_still_works);
  RUN_TEST(test_reverse_include_order_compiles);
  return UNITY_END();
}
