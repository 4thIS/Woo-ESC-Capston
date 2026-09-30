#include "text.h"

uint32_t utf8Next(const char*& p) {
  const uint8_t* s = reinterpret_cast<const uint8_t*>(p);
  const uint8_t c = s[0];
  if (c == 0) return 0;
  if (c < 0x80) {
    p += 1;
    return c;
  }
  int n;
  uint32_t cp;
  if ((c & 0xE0) == 0xC0) {
    n = 1;
    cp = c & 0x1F;
  } else if ((c & 0xF0) == 0xE0) {
    n = 2;
    cp = c & 0x0F;
  } else if ((c & 0xF8) == 0xF0) {
    n = 3;
    cp = c & 0x07;
  } else {
    p += 1;
    return '?';
  }
  // s[i] 는 s[i-1] 이 NUL 이 아닌 연속 바이트임을 확인한 뒤에만 읽는다 — NUL 너머를 읽지 않는다.
  for (int i = 1; i <= n; i++) {
    if ((s[i] & 0xC0) != 0x80) {
      p += 1;
      return '?';
    }
    cp = (cp << 6) | (s[i] & 0x3F);
  }
  p += n + 1;
  return cp;
}

int16_t textWidth(const BitmapFont& f, const char* utf8, int8_t trackingPx) {
  int16_t w = 0;
  bool any = false;
  const char* p = utf8;
  for (uint32_t cp = utf8Next(p); cp != 0; cp = utf8Next(p)) {
    const int32_t idx = bfFindGlyph(f, cp);
    if (idx < 0) continue;
    w = (int16_t)(w + f.advances[idx] + trackingPx);
    any = true;
  }
  return any ? (int16_t)(w - trackingPx) : 0;
}

int16_t drawText(Adafruit_GFX& gfx, const BitmapFont& f, const char* utf8, int16_t x, int16_t baselineY,
                 uint16_t color, int8_t trackingPx) {
  int16_t pen = x;
  bool any = false;
  const char* p = utf8;
  for (uint32_t cp = utf8Next(p); cp != 0; cp = utf8Next(p)) {
    const int16_t a = bfDrawGlyph(gfx, f, cp, pen, baselineY, color);
    if (a == 0) continue;
    pen = (int16_t)(pen + a + trackingPx);
    any = true;
  }
  return any ? (int16_t)(pen - x - trackingPx) : 0;
}
