#include "snapshot.h"

#include <cstdint>
#include <vector>

// PNG 디코드는 벤더링한 stb_image(v2.30, nothings/stb 커밋 a7d4c2175630e1ea5b6f8dd00ab96fed0b97b96d,
// 공개 도메인/MIT — 파일 무수정). 구현은 이 번역 단위에서만 정의한다. host_gfx.cpp 와 같은 이유로
// 서드파티 경고만 이 범위에서 끈다.
#define STB_IMAGE_IMPLEMENTATION
#define STBI_ONLY_PNG
#if defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wmissing-field-initializers"
#pragma GCC diagnostic ignored "-Wunused-function"  // STBI_ONLY_PNG 로 안 쓰게 된 헬퍼
#endif
#include "vendor/stb_image.h"
#if defined(__GNUC__)
#pragma GCC diagnostic pop
#endif
#include "vendor/stb_image_write.h"

namespace {

// 정답을 3채널로 강제해 읽는다(알파·팔레트 PNG 도 색만 비교). 크기가 다르면 실패로 본다.
struct Baseline {
  unsigned char* px = nullptr;
  int w = 0, h = 0;  // 디코드에 실패하면 0
  ~Baseline() {
    if (px != nullptr) stbi_image_free(px);
  }
  bool load(const char* path, const HostGfx& g) {
    int n = 0;
    px = stbi_load(path, &w, &h, &n, 3);
    if (px == nullptr) w = h = 0;
    return px != nullptr && w == g.width() && h == g.height();
  }
  const unsigned char* at(int16_t x, int16_t y, int16_t w) const { return px + ((size_t)y * w + x) * 3; }
};

bool samePixel(const HostGfx& g, const Baseline& b, int16_t x, int16_t y) {
  uint8_t r, gr, bl;
  hcolorToRGB(g.pixelAt(x, y), r, gr, bl);
  const unsigned char* e = b.at(x, y, g.width());
  return e[0] == r && e[1] == gr && e[2] == bl;
}

}  // namespace

SnapshotDiff compareToBaseline(const HostGfx& g, const char* baselinePng) {
  Baseline b;
  if (!b.load(baselinePng, g)) return {false, 0, b.w, b.h};
  long diff = 0;
  for (int16_t y = 0; y < g.height(); y++)
    for (int16_t x = 0; x < g.width(); x++)
      if (!samePixel(g, b, x, y)) diff++;
  return {true, diff, b.w, b.h};
}

bool saveDiffPNG(const HostGfx& g, const char* baselinePng, const char* outPng) {
  Baseline b;
  if (!b.load(baselinePng, g)) return false;
  const int16_t w = g.width(), h = g.height();
  std::vector<unsigned char> rgb((size_t)w * h * 3);
  for (int16_t y = 0; y < h; y++) {
    for (int16_t x = 0; x < w; x++) {
      unsigned char* o = &rgb[((size_t)y * w + x) * 3];
      if (!samePixel(g, b, x, y)) {
        o[0] = 0, o[1] = 0, o[2] = 255;
        continue;
      }
      switch (g.pixelAt(x, y)) {
        case HColor::BLACK:
          o[0] = o[1] = o[2] = 160;
          break;
        case HColor::RED:
          o[0] = 255, o[1] = 180, o[2] = 180;
          break;
        default:
          o[0] = o[1] = o[2] = 255;
          break;
      }
    }
  }
  return stbi_write_png(outPng, w, h, 3, rgb.data(), w * 3) != 0;
}
