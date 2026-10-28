#include "host_gfx.h"

#include <cassert>

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

// Adafruit_GFX 가 넘겨주는 raw uint16_t(=GxEPD2 색상 상수)를 HColor 로 매핑한다.
// 3색 e-Paper 라 그 밖의 값은 표현할 수 없다 — 조용히 아무 색이나 찍지 않고 assert 로 멈춘다.
// NDEBUG 빌드에서는 assert 가 사라지므로 WHITE 로 떨어뜨려 최소한 크래시는 피한다.
static HColor toHColor(uint16_t color) {
  switch (color) {
    case static_cast<uint16_t>(HColor::WHITE):
      return HColor::WHITE;
    case static_cast<uint16_t>(HColor::BLACK):
      return HColor::BLACK;
    case static_cast<uint16_t>(HColor::RED):
      return HColor::RED;
    default:
      assert(false && "HostGfx: 3색(GxEPD_WHITE/BLACK/RED) 외의 색상 값");
      return HColor::WHITE;
  }
}

void HostGfx::drawPixel(int16_t x, int16_t y, uint16_t color) {
  if (x < 0 || y < 0 || x >= w_ || y >= h_) return;  // v2 §12 밖 좌표는 무시(크래시 방지)
  buf_[(size_t)y * w_ + x] = toHColor(color);
}

void HostGfx::setRotation(uint8_t r) {
  assert(r == 0 && "HostGfx: 호스트 프리뷰는 rotation 0 만 지원한다");
  Adafruit_GFX::setRotation(r);
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
