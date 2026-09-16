#include "host_gfx.h"

// 벤더링한 stb 는 `-Wextra` 의 missing-field-initializers 를 24곳에서 띄운다(서드파티 코드,
// 우리가 고칠 대상이 아님). 이 include 범위에서만 억제하고 바로 복구한다 — 아래 우리 코드에는
// 경고가 그대로 적용된다.
#define STB_IMAGE_WRITE_IMPLEMENTATION
#if defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wmissing-field-initializers"
#endif
#include "vendor/stb_image_write.h"
#if defined(__GNUC__)
#pragma GCC diagnostic pop
#endif

HostGfx::HostGfx(int16_t w, int16_t h)
    : Adafruit_GFX(w, h), w_(w), h_(h), buf_((size_t)w * h, HColor::WHITE) {}

void HostGfx::drawPixel(int16_t x, int16_t y, uint16_t color) {
  if (x < 0 || y < 0 || x >= w_ || y >= h_) return;  // v2 §12 밖 좌표는 무시(크래시 방지)
  buf_[(size_t)y * w_ + x] = static_cast<HColor>(color);
}

HColor HostGfx::pixelAt(int16_t x, int16_t y) const {
  if (x < 0 || y < 0 || x >= w_ || y >= h_) return HColor::WHITE;
  return buf_[(size_t)y * w_ + x];
}

void hcolorToRGB(HColor c, uint8_t& r, uint8_t& g, uint8_t& b) {
  switch (c) {
    case HColor::BLACK:
      r = g = b = 0;
      break;
    case HColor::RED:
      r = 200;
      g = 16;
      b = 46;
      break;
    default:
      r = g = b = 255;
      break;  // WHITE
  }
}

bool HostGfx::savePNG(const char* path) const {
  std::vector<uint8_t> rgb((size_t)w_ * h_ * 3);
  for (size_t i = 0; i < buf_.size(); ++i) {
    uint8_t r, g, b;
    hcolorToRGB(buf_[i], r, g, b);
    rgb[i * 3 + 0] = r;
    rgb[i * 3 + 1] = g;
    rgb[i * 3 + 2] = b;
  }
  return stbi_write_png(path, w_, h_, 3, rgb.data(), w_ * 3) != 0;
}
