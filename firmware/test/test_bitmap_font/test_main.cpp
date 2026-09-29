// dh-04 Task 3A — 서브셋 비트맵 폰트 자산과 코드포인트 조회·그리기(낮은 계층) 검증.
//
// 자산 경로: firmware/src/fonts/<name>.bin(+.json) → 빌드 직전 tools/embed_fonts.py 가
// lib/font_data/ 에 C 배열로 생성 → 여기서 링크. PlatformIO native 테스트는 firmware/ 가 CWD 다.
#include <unity.h>

#include <cstdio>
#include <cstdlib>
#include <vector>

#include "bitmap_font.h"
#include "font_data.h"
#include "host_gfx.h"

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
// 1 + 4. .bin → C 배열 파이프라인: 크기·전 바이트 일치(0x00 포함)
// ---------------------------------------------------------------------------

static void assertEmbeddedEqualsBin(const BitmapFont& f, const char* binPath, uint16_t expectedCount) {
  std::vector<uint8_t> bin = readFile(binPath);
  TEST_ASSERT_FALSE_MESSAGE(bin.empty(), binPath);
  TEST_ASSERT_EQUAL_UINT16(expectedCount, f.count);
  const size_t expectedSize = (size_t)expectedCount * f.cellH * f.bytesPerRow;
  // 4. 실제 .bin 크기 == 글자 수 × 글자당 바이트
  TEST_ASSERT_EQUAL_size_t(expectedSize, bin.size());
  TEST_ASSERT_EQUAL_size_t(expectedSize, (size_t)f.count * bfBytesPerGlyph(f));
  // 1. 전 바이트 일치 — 0x00 이 하나라도 잘리거나 밀리면 여기서 어긋난다
  TEST_ASSERT_EQUAL_HEX8_ARRAY(bin.data(), f.bitmaps, bin.size());
}

void test_embedded_arrays_equal_bin_files() {
  assertEmbeddedEqualsBin(kNanum20Regular, "src/fonts/nanum20r.bin", 2459);
  assertEmbeddedEqualsBin(kNanum20Bold, "src/fonts/nanum20b.bin", 2459);
  assertEmbeddedEqualsBin(kNanum28Bold, "src/fonts/nanum28b.bin", 2459);
  assertEmbeddedEqualsBin(kNanum16Regular, "src/fonts/nanum16r.bin", 101);
  assertEmbeddedEqualsBin(kNanum32ExtraBold, "src/fonts/nanum32eb.bin", 10);
  assertEmbeddedEqualsBin(kNanum62ExtraBold, "src/fonts/nanum62eb.bin", 20);
}

void test_zero_bytes_inside_real_glyph_survive() {
  // 20px '가'(U+AC00, 인덱스 109)의 첫 5바이트. 앞 4바이트가 0x00(셀 윗줄 여백)이고 5번째가
  // 잉크다 — 0x00 이 잘리거나 문자열처럼 끊기면 이 위치가 밀려 0x02 가 나오지 않는다.
  // 기대값은 .bin 을 파이썬으로 직접 읽어 얻었다(생성 파이프라인과 독립).
  const uint8_t* g = bfGlyphBitmap(kNanum20Regular, 109);
  const uint8_t expected[] = {0x00, 0x00, 0x00, 0x00, 0x02};
  TEST_ASSERT_EQUAL_HEX8_ARRAY(expected, g, sizeof expected);
  // 20px 자산 전체에서 0x00 이 실데이터로 흔하다는 것 자체도 확인(154,917 B 중 77,232 B).
  size_t zeros = 0;
  const size_t total = (size_t)kNanum20Regular.count * bfBytesPerGlyph(kNanum20Regular);
  for (size_t i = 0; i < total; i++) zeros += kNanum20Regular.bitmaps[i] == 0x00;
  TEST_ASSERT_EQUAL_size_t(77232, zeros);
}

// ---------------------------------------------------------------------------
// 2. 코드포인트 → 글리프 인덱스(이진탐색)
// ---------------------------------------------------------------------------

void test_find_glyph_in_charset_order() {
  const BitmapFont& f = kNanum20Regular;
  TEST_ASSERT_EQUAL_INT32(0, bfFindGlyph(f, 0x0020));  // 처음(공백)
  TEST_ASSERT_EQUAL_INT32(33, bfFindGlyph(f, 'A'));
  TEST_ASSERT_EQUAL_INT32(94, bfFindGlyph(f, '~'));       // ASCII 끝
  TEST_ASSERT_EQUAL_INT32(95, bfFindGlyph(f, 0x00B7));    // ·
  TEST_ASSERT_EQUAL_INT32(96, bfFindGlyph(f, 0x2013));    // –
  TEST_ASSERT_EQUAL_INT32(97, bfFindGlyph(f, 0x2160));    // Ⅰ
  TEST_ASSERT_EQUAL_INT32(108, bfFindGlyph(f, 0x2193));   // ↓
  TEST_ASSERT_EQUAL_INT32(109, bfFindGlyph(f, 0xAC00));   // 가
  TEST_ASSERT_EQUAL_INT32(110, bfFindGlyph(f, 0xAC01));   // 각
  TEST_ASSERT_EQUAL_INT32(1229, bfFindGlyph(f, 0xC0CC));  // 샌(중간)
  TEST_ASSERT_EQUAL_INT32(2012, bfFindGlyph(f, 0xCEA1));  // 캡
  TEST_ASSERT_EQUAL_INT32(2458, bfFindGlyph(f, 0xD79D));  // 힝(끝)
  // 28px 도 같은 순서(같은 charset.txt)
  TEST_ASSERT_EQUAL_INT32(2012, bfFindGlyph(kNanum28Bold, 0xCEA1));
}

void test_find_glyph_not_found() {
  const BitmapFont& f = kNanum20Regular;
  TEST_ASSERT_EQUAL_INT32(-1, bfFindGlyph(f, 0xB620));  // 똠 — KS X 1001 밖 음절
  TEST_ASSERT_EQUAL_INT32(-1, bfFindGlyph(f, 0xC00D));  // 쀍
  TEST_ASSERT_EQUAL_INT32(-1, bfFindGlyph(f, 0xD58F));  // 햏
  TEST_ASSERT_EQUAL_INT32(-1, bfFindGlyph(f, 0x001F));  // 첫 글자보다 작음
  TEST_ASSERT_EQUAL_INT32(-1, bfFindGlyph(f, 0x0000));
  TEST_ASSERT_EQUAL_INT32(-1, bfFindGlyph(f, 0x007F));  // ASCII 와 · 사이 빈 구간
  TEST_ASSERT_EQUAL_INT32(-1, bfFindGlyph(f, 0xD7A3));  // 마지막 글자보다 큼
  // 16비트로 잘라 비교하면 0x10020 이 공백(0x0020)으로 오인된다 — 그러면 안 된다.
  TEST_ASSERT_EQUAL_INT32(-1, bfFindGlyph(f, 0x10020));
  // 16px 은 부분집합: 호·개·더 는 있고 다른 한글은 없다
  TEST_ASSERT_EQUAL_INT32(100, bfFindGlyph(kNanum16Regular, 0xD638));  // 호
  TEST_ASSERT_EQUAL_INT32(-1, bfFindGlyph(kNanum16Regular, 0xAC00));   // 가
}

void test_full_fonts_follow_charset_txt_exactly() {
  // 단일 진실원(lora_proto/lora_proto/charset.txt)과 글리프 순서가 한 글자도 어긋나지 않는지.
  FILE* fp = std::fopen("../lora_proto/lora_proto/charset.txt", "rb");
  TEST_ASSERT_NOT_NULL(fp);
  std::vector<uint16_t> cps;
  char line[1024];  // 주석 줄(한글 UTF-8)이 길다 — 작은 버퍼면 줄이 쪼개져 이어진 조각을 데이터로 오인한다
  while (std::fgets(line, sizeof line, fp)) {
    if (line[0] == '#' || line[0] == '\n' || line[0] == '\r') continue;
    cps.push_back((uint16_t)std::strtoul(line, nullptr, 16));
  }
  std::fclose(fp);
  TEST_ASSERT_EQUAL_size_t(2459, cps.size());
  TEST_ASSERT_EQUAL_HEX16_ARRAY(cps.data(), kNanum20Regular.codepoints, cps.size());
  TEST_ASSERT_EQUAL_HEX16_ARRAY(cps.data(), kNanum20Bold.codepoints, cps.size());
  TEST_ASSERT_EQUAL_HEX16_ARRAY(cps.data(), kNanum28Bold.codepoints, cps.size());
}

// ---------------------------------------------------------------------------
// Q1·Q2 — 로마숫자 대체(Noto Sans KR)와 20px Bold
// ---------------------------------------------------------------------------

static uint32_t inkCount(const BitmapFont& f, uint32_t cp) {
  const int32_t idx = bfFindGlyph(f, cp);
  TEST_ASSERT_TRUE(idx >= 0);
  const uint8_t* g = bfGlyphBitmap(f, idx);
  uint32_t n = 0;
  for (uint16_t i = 0; i < bfBytesPerGlyph(f); i++)
    for (uint8_t b = g[i]; b; b &= (uint8_t)(b - 1)) n++;
  return n;
}

static uint8_t advanceOf(const BitmapFont& f, uint32_t cp) {
  const int32_t idx = bfFindGlyph(f, cp);
  TEST_ASSERT_TRUE(idx >= 0);
  return f.advances[idx];
}

void test_roman_numerals_are_inked_fullwidth_fallback_glyphs() {
  // 나눔고딕에는 Ⅰ~Ⅹ 가 없어 Noto Sans KR 로 대체했다(Q1 (a)). 대체가 빠지면 빈 셀(잉크 0)이 되고,
  // ASCII I·V·X 를 이어 붙인 식이면 폭이 글자마다 크게 다르다('I' 폭은 20px 에서 5).
  // Noto 의 로마숫자는 전각이라 폭이 대략 em(20/28)이다 — 값은 .bin/.json 을 파이썬으로 읽어 얻었다.
  const BitmapFont* fonts[] = {&kNanum20Regular, &kNanum20Bold, &kNanum28Bold};
  const uint8_t em[] = {20, 20, 28};
  for (int fi = 0; fi < 3; fi++) {
    for (uint32_t cp = 0x2160; cp <= 0x2169; cp++) {
      TEST_ASSERT_GREATER_THAN_UINT32(20, inkCount(*fonts[fi], cp));
      TEST_ASSERT_UINT8_WITHIN(2, em[fi], advanceOf(*fonts[fi], cp));
    }
  }
  TEST_ASSERT_EQUAL_UINT8(5, advanceOf(kNanum20Regular, 'I'));  // 주 폰트 'I' 와는 다른 글리프
}

void test_20px_bold_is_heavier_than_regular_same_cell() {
  // 같은 20px·같은 셀(20x21)이지만 700 은 400 보다 획이 굵다: '가' 46 → 108, '캡' 97 → 154 픽셀.
  TEST_ASSERT_EQUAL_UINT8(kNanum20Regular.cellW, kNanum20Bold.cellW);
  TEST_ASSERT_EQUAL_UINT8(kNanum20Regular.cellH, kNanum20Bold.cellH);
  TEST_ASSERT_EQUAL_UINT32(46, inkCount(kNanum20Regular, 0xAC00));
  TEST_ASSERT_EQUAL_UINT32(108, inkCount(kNanum20Bold, 0xAC00));
  TEST_ASSERT_EQUAL_UINT32(97, inkCount(kNanum20Regular, 0xCEA1));
  TEST_ASSERT_EQUAL_UINT32(154, inkCount(kNanum20Bold, 0xCEA1));
}

// ---------------------------------------------------------------------------
// 3. HostGfx 에 실제로 찍기
// ---------------------------------------------------------------------------

static bool bitAt(const BitmapFont& f, const uint8_t* g, int cx, int cy) {
  return g[cy * f.bytesPerRow + cx / 8] & (0x80 >> (cx % 8));
}

void test_draw_glyph_matches_bitmap_at_baseline_origin() {
  HostGfx gfx;
  const BitmapFont& f = kNanum20Regular;
  const int16_t penX = 100, baseY = 50;
  TEST_ASSERT_EQUAL_INT16(f.advances[109], bfDrawGlyph(gfx, f, 0xAC00, penX, baseY, GxEPD_BLACK));
  const uint8_t* g = bfGlyphBitmap(f, 109);
  const int left = penX - f.originX, top = baseY - f.baseline;
  int black = 0;
  // 셀 둘레 2px 까지 포함해 전부 대조 — 셀 안은 비트대로, 셀 밖은 흰색이어야 한다.
  for (int y = top - 2; y < top + f.cellH + 2; y++) {
    for (int x = left - 2; x < left + f.cellW + 2; x++) {
      const int cx = x - left, cy = y - top;
      const bool inCell = cx >= 0 && cx < f.cellW && cy >= 0 && cy < f.cellH;
      const HColor want = inCell && bitAt(f, g, cx, cy) ? HColor::BLACK : HColor::WHITE;
      TEST_ASSERT_EQUAL(want, gfx.pixelAt(x, y));
      black += want == HColor::BLACK;
    }
  }
  TEST_ASSERT_GREATER_THAN(20, black);  // 실제로 무언가 그려졌다
}

void test_draw_hyphen_sits_above_baseline_right_of_pen() {
  // 기하 앵커: 62px '-' 는 펜 원점 오른쪽, 베이스라인 위 가운데쯤의 가로 막대다.
  // (펜·베이스라인 좌표 규약이 뒤집히면 — 예: y 를 셀 윗변으로 해석 — 여기서 걸린다.)
  HostGfx gfx;
  const int16_t penX = 200, baseY = 300;
  bfDrawGlyph(gfx, kNanum62ExtraBold, '-', penX, baseY, GxEPD_BLACK);
  TEST_ASSERT_EQUAL(HColor::BLACK, gfx.pixelAt(penX + 12, baseY - 25));  // 막대 가운데
  TEST_ASSERT_EQUAL(HColor::WHITE, gfx.pixelAt(penX + 12, baseY - 35));  // 막대 위
  TEST_ASSERT_EQUAL(HColor::WHITE, gfx.pixelAt(penX + 12, baseY - 15));  // 막대 아래
  TEST_ASSERT_EQUAL(HColor::WHITE, gfx.pixelAt(penX + 12, baseY - 1));   // 베이스라인 바로 위
  TEST_ASSERT_EQUAL(HColor::WHITE, gfx.pixelAt(penX - 1, baseY - 25));   // 펜 왼쪽
}

void test_draw_passes_color_and_leaves_background() {
  HostGfx gfx;
  gfx.fillRect(0, 0, 60, 60, GxEPD_BLACK);  // 반전면(흑 바탕) 위에 흰 글자
  bfDrawGlyph(gfx, kNanum62ExtraBold, '-', 10, 50, GxEPD_WHITE);
  TEST_ASSERT_EQUAL(HColor::WHITE, gfx.pixelAt(10 + 12, 50 - 25));  // 잉크 = 지정 색
  TEST_ASSERT_EQUAL(HColor::BLACK, gfx.pixelAt(10 + 12, 50 - 35));  // 잉크 아닌 곳은 바탕 유지
  bfDrawGlyph(gfx, kNanum62ExtraBold, '-', 300, 300, GxEPD_RED);
  TEST_ASSERT_EQUAL(HColor::RED, gfx.pixelAt(300 + 12, 300 - 25));
}

void test_draw_missing_glyph_draws_nothing_returns_zero() {
  HostGfx gfx;
  TEST_ASSERT_EQUAL_INT16(0, bfDrawGlyph(gfx, kNanum20Regular, 0xB620, 100, 100, GxEPD_BLACK));  // 똠
  TEST_ASSERT_EQUAL_INT16(0, bfDrawGlyph(gfx, kNanum16Regular, 0xAC00, 100, 100, GxEPD_BLACK));  // 16px 가
  for (int16_t y = 0; y < 480; y++)
    for (int16_t x = 0; x < 800; x++) TEST_ASSERT_EQUAL(HColor::WHITE, gfx.pixelAt(x, y));
}

void test_space_advances_without_ink() {
  HostGfx gfx;
  const int16_t adv = bfDrawGlyph(gfx, kNanum20Regular, ' ', 100, 100, GxEPD_BLACK);
  TEST_ASSERT_GREATER_THAN_INT16(0, adv);
  for (int16_t y = 70; y < 110; y++)
    for (int16_t x = 90; x < 130; x++) TEST_ASSERT_EQUAL(HColor::WHITE, gfx.pixelAt(x, y));
}

void setUp() {}
void tearDown() {}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_embedded_arrays_equal_bin_files);
  RUN_TEST(test_zero_bytes_inside_real_glyph_survive);
  RUN_TEST(test_find_glyph_in_charset_order);
  RUN_TEST(test_find_glyph_not_found);
  RUN_TEST(test_full_fonts_follow_charset_txt_exactly);
  RUN_TEST(test_roman_numerals_are_inked_fullwidth_fallback_glyphs);
  RUN_TEST(test_20px_bold_is_heavier_than_regular_same_cell);
  RUN_TEST(test_draw_glyph_matches_bitmap_at_baseline_origin);
  RUN_TEST(test_draw_hyphen_sits_above_baseline_right_of_pen);
  RUN_TEST(test_draw_passes_color_and_leaves_background);
  RUN_TEST(test_draw_missing_glyph_draws_nothing_returns_zero);
  RUN_TEST(test_space_advances_without_ink);
  return UNITY_END();
}
