#include "bitmap_font.h"

#include <Adafruit_GFX.h>

int32_t bfFindGlyph(const BitmapFont& f, uint32_t cp) {
  int32_t lo = 0, hi = (int32_t)f.count - 1;
  while (lo <= hi) {
    const int32_t mid = lo + (hi - lo) / 2;
    // 표는 uint16 이지만 비교는 uint32 로 한다 — cp 를 uint16 으로 자르면 0x10020 이 공백(0x20)으로 오인된다.
    const uint32_t v = f.codepoints[mid];
    if (v == cp) return mid;
    if (v < cp)
      lo = mid + 1;
    else
      hi = mid - 1;
  }
  return -1;
}

int16_t bfDrawGlyph(Adafruit_GFX& gfx, const BitmapFont& f, uint32_t cp, int16_t x, int16_t baselineY,
                    uint16_t color) {
  const int32_t idx = bfFindGlyph(f, cp);
  if (idx < 0) return 0;
  const uint8_t* g = bfGlyphBitmap(f, idx);
  const int16_t left = (int16_t)(x - f.originX);
  const int16_t top = (int16_t)(baselineY - f.baseline);
  for (int16_t row = 0; row < f.cellH; row++) {
    const uint8_t* line = g + row * f.bytesPerRow;
    for (int16_t col = 0; col < f.cellW; col++) {
      if (line[col >> 3] & (0x80 >> (col & 7)))
        gfx.drawPixel((int16_t)(left + col), (int16_t)(top + row), color);
    }
  }
  return f.advances[idx];
}
