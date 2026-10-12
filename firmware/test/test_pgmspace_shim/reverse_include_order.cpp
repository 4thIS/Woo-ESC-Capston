// test_main.cpp 와 반대 순서로 include 한다: WProgram.h 가 PROGMEM/pgm_read_* 를 먼저 정의한
// 뒤 pgmspace.h 가 들어온다. 두 헤더가 같은 이름을 #ifndef 가드 없이 정의하면 여기서 깨진다.
// 이 번역 단위가 컴파일된다는 사실 자체가 "어느 순서든 충돌 없음"의 증거다.
#include <WProgram.h>
#include <pgmspace.h>
#include <unity.h>

static const uint8_t kReverseOrderGlyph[] PROGMEM = {0xAA, 0x55};

void test_reverse_include_order_compiles() {
  TEST_ASSERT_EQUAL_HEX8(0xAA, pgm_read_byte(&kReverseOrderGlyph[0]));
  TEST_ASSERT_EQUAL_HEX8(0x55, pgm_read_byte(&kReverseOrderGlyph[1]));
}
