#include <unity.h>

#include <cstdio>

#include "host_gfx.h"
#include "snapshot.h"
#include "vendor/stb_image.h"
#include "vendor/stb_image_write.h"

// 정답 PNG 대조 모듈(lib/host_gfx/snapshot). 정답은 매 테스트에서 HostGfx::savePNG 로 만들고 지운다.
// CWD 는 firmware/(test_render_preview 와 같은 전제).

static const char* kBase = "snapshot_base_tmp.png";
static const char* kDiff = "snapshot_diff_tmp.png";

void test_identical_is_zero() {
  HostGfx g;
  g.fillRect(10, 10, 50, 20, GxEPD_BLACK);
  TEST_ASSERT_TRUE(g.savePNG(kBase));
  const SnapshotDiff d = compareToBaseline(g, kBase);
  TEST_ASSERT_TRUE(d.baselineLoaded);
  TEST_ASSERT_EQUAL(0, d.diffPixels);
  remove(kBase);
}

void test_one_pixel_differs() {
  HostGfx g;
  TEST_ASSERT_TRUE(g.savePNG(kBase));
  g.drawPixel(5, 7, GxEPD_RED);
  const SnapshotDiff d = compareToBaseline(g, kBase);
  TEST_ASSERT_TRUE(d.baselineLoaded);
  TEST_ASSERT_EQUAL(1, d.diffPixels);
  remove(kBase);
}

void test_missing_file_is_not_loaded() {
  HostGfx g;
  remove(kBase);
  TEST_ASSERT_FALSE(compareToBaseline(g, kBase).baselineLoaded);
}

void test_size_mismatch_is_not_loaded() {
  HostGfx small(10, 10);
  TEST_ASSERT_TRUE(small.savePNG(kBase));
  HostGfx g;  // 800x480
  TEST_ASSERT_FALSE(compareToBaseline(g, kBase).baselineLoaded);
  remove(kBase);
}

void test_rgba_baseline_compares_by_rgb() {
  // 이미지 편집기로 다시 저장해 알파 채널이 생긴 정답 — 색만 같으면 같은 그림이다.
  HostGfx g;
  g.drawPixel(3, 4, GxEPD_BLACK);
  static unsigned char rgba[800 * 480 * 4];
  for (int i = 0; i < 800 * 480; i++) {
    rgba[i * 4 + 0] = rgba[i * 4 + 1] = rgba[i * 4 + 2] = 255;
    rgba[i * 4 + 3] = 255;
  }
  const int p = (4 * 800 + 3) * 4;
  rgba[p] = rgba[p + 1] = rgba[p + 2] = 0;
  TEST_ASSERT_NOT_EQUAL(0, stbi_write_png(kBase, 800, 480, 4, rgba, 800 * 4));
  const SnapshotDiff d = compareToBaseline(g, kBase);
  TEST_ASSERT_TRUE(d.baselineLoaded);
  TEST_ASSERT_EQUAL(0, d.diffPixels);
  remove(kBase);
}

void test_diff_png_marks_changed_pixel_blue() {
  HostGfx g;
  TEST_ASSERT_TRUE(g.savePNG(kBase));
  g.drawPixel(5, 7, GxEPD_RED);
  TEST_ASSERT_TRUE(saveDiffPNG(g, kBase, kDiff));
  int w = 0, h = 0, n = 0;
  unsigned char* px = stbi_load(kDiff, &w, &h, &n, 3);
  TEST_ASSERT_NOT_NULL(px);
  TEST_ASSERT_EQUAL(800, w);
  TEST_ASSERT_EQUAL(480, h);
  const unsigned char* changed = px + (7 * 800 + 5) * 3;
  TEST_ASSERT_EQUAL_UINT8(0, changed[0]);
  TEST_ASSERT_EQUAL_UINT8(0, changed[1]);
  TEST_ASSERT_EQUAL_UINT8(255, changed[2]);
  TEST_ASSERT_EQUAL_UINT8(255, px[0]);  // (0,0) 흰색은 같은 픽셀 — 흰색 그대로
  TEST_ASSERT_EQUAL_UINT8(255, px[1]);
  TEST_ASSERT_EQUAL_UINT8(255, px[2]);
  stbi_image_free(px);
  remove(kBase);
  remove(kDiff);
}

void test_diff_png_fails_without_baseline() {
  HostGfx g;
  remove(kBase);
  TEST_ASSERT_FALSE(saveDiffPNG(g, kBase, kDiff));
}

void setUp() {}
void tearDown() {}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_identical_is_zero);
  RUN_TEST(test_one_pixel_differs);
  RUN_TEST(test_missing_file_is_not_loaded);
  RUN_TEST(test_size_mismatch_is_not_loaded);
  RUN_TEST(test_rgba_baseline_compares_by_rgb);
  RUN_TEST(test_diff_png_marks_changed_pixel_blue);
  RUN_TEST(test_diff_png_fails_without_baseline);
  return UNITY_END();
}
