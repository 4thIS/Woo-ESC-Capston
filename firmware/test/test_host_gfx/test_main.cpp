#include <unity.h>

#include <cstdio>

#include "host_gfx.h"

void test_default_size_is_800x480_white() {
  HostGfx g;
  TEST_ASSERT_EQUAL(HColor::WHITE, g.pixelAt(0, 0));
  TEST_ASSERT_EQUAL(HColor::WHITE, g.pixelAt(799, 479));
}

void test_draw_pixel_sets_and_reads_back() {
  HostGfx g;
  g.drawPixel(10, 20, (uint16_t)HColor::RED);
  TEST_ASSERT_EQUAL(HColor::RED, g.pixelAt(10, 20));
  TEST_ASSERT_EQUAL(HColor::WHITE, g.pixelAt(11, 20));
}

void test_out_of_bounds_draw_is_ignored_not_crash() {
  HostGfx g;
  g.drawPixel(-1, -1, (uint16_t)HColor::BLACK);
  g.drawPixel(9999, 9999, (uint16_t)HColor::BLACK);
  TEST_ASSERT_TRUE(true);  // 크래시 안 하면 성공
}

void test_fill_rect_via_adafruit_gfx_sets_region() {
  HostGfx g;
  g.fillRect(0, 0, 3, 3, (uint16_t)HColor::BLACK);
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(2, 2));
  TEST_ASSERT_EQUAL(HColor::WHITE, g.pixelAt(3, 3));
}

void test_save_png_writes_valid_signature() {
  HostGfx g;
  g.fillRect(0, 0, 10, 10, (uint16_t)HColor::RED);
  TEST_ASSERT_TRUE(g.savePNG("test_host_gfx_out.png"));
  FILE* f = fopen("test_host_gfx_out.png", "rb");
  TEST_ASSERT_NOT_NULL(f);
  uint8_t sig[8];
  TEST_ASSERT_EQUAL(8, fread(sig, 1, 8, f));
  fclose(f);
  const uint8_t PNG_SIG[8] = {0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n'};
  TEST_ASSERT_EQUAL_UINT8_ARRAY(PNG_SIG, sig, 8);
  remove("test_host_gfx_out.png");
}

// savePNG 가 프레임버퍼를 RGB 로 바꿀 때 쓰는 매핑. PNG 시그니처 검사만으로는
// "색이 맞게 나갔는가"를 전혀 판정하지 못해 따로 어서션한다.
void test_hcolor_to_rgb_maps_three_colors() {
  uint8_t r = 0, g = 0, b = 0;

  hcolorToRGB(HColor::BLACK, r, g, b);
  TEST_ASSERT_EQUAL_UINT8(0, r);
  TEST_ASSERT_EQUAL_UINT8(0, g);
  TEST_ASSERT_EQUAL_UINT8(0, b);

  hcolorToRGB(HColor::RED, r, g, b);
  TEST_ASSERT_EQUAL_UINT8(200, r);
  TEST_ASSERT_EQUAL_UINT8(16, g);
  TEST_ASSERT_EQUAL_UINT8(46, b);

  hcolorToRGB(HColor::WHITE, r, g, b);
  TEST_ASSERT_EQUAL_UINT8(255, r);
  TEST_ASSERT_EQUAL_UINT8(255, g);
  TEST_ASSERT_EQUAL_UINT8(255, b);
}

// HColor 는 실기 GxEPD2 의 색상 상수와 **같은 값**이어야 한다(cw PR #23 승인 코멘트).
// 이 어서션이 깨지면 dh-04 가 이식한 v1 렌더 코드가 조용히 빈 PNG 를 뱉는다 —
// 심볼만 쓰는 다른 테스트는 값이 틀려도 전부 통과하므로 여기서만 값을 직접 못 박는다.
void test_hcolor_values_match_gxepd2_constants() {
  TEST_ASSERT_EQUAL_HEX16(0xFFFF, (uint16_t)HColor::WHITE);  // GxEPD_WHITE
  TEST_ASSERT_EQUAL_HEX16(0x0000, (uint16_t)HColor::BLACK);  // GxEPD_BLACK
  TEST_ASSERT_EQUAL_HEX16(0xF800, (uint16_t)HColor::RED);    // GxEPD_RED
}

// setRotation 은 0 만 지원한다(그 외는 assert 로 중단 — 프로세스가 죽어 단위 테스트로 못 잡는다).
// 정상 경로가 베이스 클래스 동작을 그대로 수행하는지만 검증한다.
void test_set_rotation_zero_keeps_base_behaviour() {
  HostGfx g;
  g.setRotation(0);
  TEST_ASSERT_EQUAL_UINT8(0, g.getRotation());
  TEST_ASSERT_EQUAL_INT16(800, g.width());
  TEST_ASSERT_EQUAL_INT16(480, g.height());
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_hcolor_values_match_gxepd2_constants);
  RUN_TEST(test_set_rotation_zero_keeps_base_behaviour);
  RUN_TEST(test_default_size_is_800x480_white);
  RUN_TEST(test_draw_pixel_sets_and_reads_back);
  RUN_TEST(test_out_of_bounds_draw_is_ignored_not_crash);
  RUN_TEST(test_fill_rect_via_adafruit_gfx_sets_region);
  RUN_TEST(test_save_png_writes_valid_signature);
  RUN_TEST(test_hcolor_to_rgb_maps_three_colors);
  return UNITY_END();
}
