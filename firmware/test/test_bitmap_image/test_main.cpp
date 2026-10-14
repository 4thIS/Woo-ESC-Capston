// dh-04 Task 3 Phase B — 이미지 자산(상태명 8종·layout 8 제목·칩 6종) 검증.
//
// 자산 경로: firmware/src/fonts/images/<name>.bin(+.json) → 빌드 직전 tools/embed_images.py 가
// lib/image_data/ 에 C 배열로 생성 → 여기서 링크. PlatformIO native 테스트는 firmware/ 가 CWD 다.
// bitmap_font 테스트(test_bitmap_font/test_main.cpp)와 같은 파이프라인 검증 패턴을 따른다.
#include <unity.h>

#include <cstdio>
#include <cstdlib>
#include <vector>

#include "bitmap_image.h"
#include "host_gfx.h"
#include "image_data.h"

static std::vector<uint8_t> readFile(const char* path) {
  std::vector<uint8_t> out;
  FILE* fp = std::fopen(path, "rb");
  if (!fp) return out;
  uint8_t buf[4096];
  size_t n;
  while ((n = std::fread(buf, 1, sizeof buf, fp)) > 0) out.insert(out.end(), buf, buf + n);
  std::fclose(fp);
  return out;
}

// ---------------------------------------------------------------------------
// 1. .bin → C 배열 파이프라인: 치수·전 바이트(0x00 포함) 일치
// ---------------------------------------------------------------------------

struct ImageCase {
  const BitmapImage* img;
  const char* binPath;
  uint16_t w, h;
  uint8_t bytesPerRow, baseline;
};

static const ImageCase kCases[] = {
    {&kImgChipByeongyeong, "src/fonts/images/chip_byeongyeong.bin", 27, 16, 4, 14},
    {&kImgChipDaeyeo, "src/fonts/images/chip_daeyeo.bin", 28, 16, 4, 14},
    {&kImgChipHyugang, "src/fonts/images/chip_hyugang.bin", 31, 15, 4, 14},
    {&kImgChipOneul, "src/fonts/images/chip_oneul.bin", 31, 14, 4, 13},
    {&kImgChipSiheom, "src/fonts/images/chip_siheom.bin", 28, 16, 4, 14},
    {&kImgChipTeukgang, "src/fonts/images/chip_teukgang.bin", 31, 17, 4, 14},
    {&kImgStatusBinganguisil, "src/fonts/images/status_binganguisil.bin", 270, 75, 34, 66},
    {&kImgStatusDaeyeojung, "src/fonts/images/status_daeyeojung.bin", 209, 76, 27, 67},
    {&kImgStatusHyugang, "src/fonts/images/status_hyugang.bin", 142, 76, 18, 67},
    {&kImgStatusSiheomjung, "src/fonts/images/status_siheomjung.bin", 210, 76, 27, 67},
    {&kImgStatusSueopjung, "src/fonts/images/status_sueopjung.bin", 212, 76, 27, 67},
    {&kImgStatusSwineunsigan, "src/fonts/images/status_swineunsigan.bin", 282, 75, 36, 67},
    {&kImgStatusTeukgang, "src/fonts/images/status_teukgang.bin", 142, 75, 18, 66},
    {&kImgTitleSeoljeongdaegi, "src/fonts/images/title_seoljeongdaegi.bin", 230, 60, 29, 53},
};
static const size_t kNumCases = sizeof(kCases) / sizeof(kCases[0]);

void test_embedded_bitmaps_equal_bin_files_for_all_images() {
  for (size_t i = 0; i < kNumCases; i++) {
    const ImageCase& c = kCases[i];
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(c.w, c.img->w, c.binPath);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(c.h, c.img->h, c.binPath);
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(c.bytesPerRow, c.img->bytesPerRow, c.binPath);
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(c.baseline, c.img->baseline, c.binPath);
    TEST_ASSERT_EQUAL_UINT8_MESSAGE((c.w + 7) / 8, c.img->bytesPerRow, c.binPath);

    std::vector<uint8_t> bin = readFile(c.binPath);
    TEST_ASSERT_FALSE_MESSAGE(bin.empty(), c.binPath);
    // 1. 실제 .bin 크기 == h 행 x bytesPerRow (w·h·바이트 수 정합)
    const size_t expectedSize = (size_t)c.img->h * c.img->bytesPerRow;
    TEST_ASSERT_EQUAL_size_t_MESSAGE(expectedSize, bin.size(), c.binPath);
    // 전 바이트 일치 — 0x00 이 하나라도 잘리거나 밀리면 여기서 어긋난다
    TEST_ASSERT_EQUAL_HEX8_ARRAY_MESSAGE(bin.data(), c.img->bitmap, bin.size(), c.binPath);
  }
}

// ---------------------------------------------------------------------------
// 2. HostGfx 에 Adafruit_GFX::drawBitmap 으로 직접 찍기 — 흰·검 두 색 모두
// ---------------------------------------------------------------------------

static bool bitAt(const BitmapImage& img, int cx, int cy) {
  return img.bitmap[cy * img.bytesPerRow + cx / 8] & (0x80 >> (cx % 8));
}

static void assertDrawnMatchesMask(const BitmapImage& img, int16_t x, int16_t y, uint16_t color,
                                   uint16_t bgKnown, HColor bgWant) {
  HostGfx gfx;
  if (bgKnown != 0xFFFFu) gfx.fillRect(0, 0, gfx.width(), gfx.height(), bgKnown);
  gfx.drawBitmap(x, y, img.bitmap, img.w, img.h, color);
  int inkPixels = 0;
  for (int cy = 0; cy < img.h; cy++) {
    for (int cx = 0; cx < img.w; cx++) {
      const bool ink = bitAt(img, cx, cy);
      const HColor want = ink ? (HColor)color : bgWant;
      TEST_ASSERT_EQUAL(want, gfx.pixelAt(x + cx, y + cy));
      inkPixels += ink;
    }
  }
  TEST_ASSERT_GREATER_THAN(10, inkPixels);  // 실제로 무언가 그려졌다
}

void test_draw_bitmap_matches_mask_white_on_paper() {
  // 흰 바탕(기본) 위에 검정 글자 — BLACK 상태 띠 색 규약
  assertDrawnMatchesMask(kImgChipOneul, 50, 50, GxEPD_BLACK, 0xFFFFu, HColor::WHITE);
  assertDrawnMatchesMask(kImgStatusBinganguisil, 10, 10, GxEPD_BLACK, 0xFFFFu, HColor::WHITE);
}

void test_draw_bitmap_matches_mask_white_ink_on_black_bg() {
  // 검정 바탕(반전면) 위에 흰 글자 — RED 상태 띠에서 실제로는 RED 바탕이지만, 마스크가 색을
  // 가리지 않는다는 것(같은 마스크를 다른 색으로 찍어도 모양이 같다)을 흰/검 두 색으로 확인한다.
  assertDrawnMatchesMask(kImgChipOneul, 50, 50, GxEPD_WHITE, GxEPD_BLACK, HColor::BLACK);
  assertDrawnMatchesMask(kImgStatusSueopjung, 100, 40, GxEPD_WHITE, GxEPD_BLACK, HColor::BLACK);
}

void test_draw_bitmap_transparent_outside_canvas_untouched() {
  // drawBitmap 은 잉크 비트만 찍는다(벤더 주석 "unset bits are transparent") — 이미지 영역 밖은
  // 손대지 않는다.
  HostGfx gfx;
  gfx.fillRect(0, 0, gfx.width(), gfx.height(), GxEPD_RED);
  gfx.drawBitmap(200, 200, kImgChipDaeyeo.bitmap, kImgChipDaeyeo.w, kImgChipDaeyeo.h, GxEPD_BLACK);
  TEST_ASSERT_EQUAL(HColor::RED, gfx.pixelAt(0, 0));
  TEST_ASSERT_EQUAL(HColor::RED, gfx.pixelAt(199, 200));
  TEST_ASSERT_EQUAL(HColor::RED, gfx.pixelAt(200 + kImgChipDaeyeo.w + 5, 200));
}

// ---------------------------------------------------------------------------
// 3. 800 굵기가 실제로 반영됐는지 — 같은 문구 "휴강"을 400 굵기로 오프라인 렌더한 잉크 픽셀 수와 비교
// ---------------------------------------------------------------------------

void test_extrabold_status_heavier_than_regular_reference() {
  // 참고값(400/78px "휴강" 잉크 2,624px)은 gen_images.py 의 render_phrase 를 NanumGothic-400.ttf 로
  // 독립적으로 돌려 얻었다(파이프라인과 무관한 별도 확인, dh-04 Task 3A 46→108 검증과 같은 방식).
  const BitmapImage& img = kImgStatusHyugang;
  uint32_t ink = 0;
  for (uint16_t cy = 0; cy < img.h; cy++)
    for (uint16_t cx = 0; cx < img.w; cx++) ink += bitAt(img, cx, cy);
  TEST_ASSERT_EQUAL_UINT32(4600, ink);         // 800 굵기 실측(embed 파이프라인 결과)
  TEST_ASSERT_GREATER_THAN_UINT32(2624, ink);  // 400 굵기 참고값보다 무겁다
}

void setUp() {}
void tearDown() {}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_embedded_bitmaps_equal_bin_files_for_all_images);
  RUN_TEST(test_draw_bitmap_matches_mask_white_on_paper);
  RUN_TEST(test_draw_bitmap_matches_mask_white_ink_on_black_bg);
  RUN_TEST(test_draw_bitmap_transparent_outside_canvas_untouched);
  RUN_TEST(test_extrabold_status_heavier_than_regular_reference);
  return UNITY_END();
}
