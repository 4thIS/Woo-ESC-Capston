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

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_default_size_is_800x480_white);
  RUN_TEST(test_draw_pixel_sets_and_reads_back);
  RUN_TEST(test_out_of_bounds_draw_is_ignored_not_crash);
  RUN_TEST(test_fill_rect_via_adafruit_gfx_sets_region);
  RUN_TEST(test_save_png_writes_valid_signature);
  return UNITY_END();
}
