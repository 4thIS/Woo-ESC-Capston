#pragma once
#include <Adafruit_GFX.h>

#include <cstdint>
#include <vector>

enum class HColor : uint16_t { WHITE = 0, BLACK = 1, RED = 2 };

// 3색 e-Paper 색 → PNG 로 내보낼 RGB. savePNG 가 쓰는 유일한 "출력이 맞는가" 판정 지점이라
// 테스트 가능하도록 순수 함수로 분리해 둔다. 아는 값이 아니면 WHITE 로 떨어진다.
void hcolorToRGB(HColor c, uint8_t& r, uint8_t& g, uint8_t& b);

// 800x480x3색 호스트 프레임버퍼. Adafruit_GFX 파생이라 fillRect/print/drawBitmap 등
// 상위 도형 함수는 전부 Adafruit_GFX 원본 코드가 그린다 — 우리는 drawPixel만 구현한다.
class HostGfx : public Adafruit_GFX {
 public:
  explicit HostGfx(int16_t w = 800, int16_t h = 480);
  void drawPixel(int16_t x, int16_t y, uint16_t color) override;
  HColor pixelAt(int16_t x, int16_t y) const;
  bool savePNG(const char* path) const;

 private:
  int16_t w_, h_;
  std::vector<HColor> buf_;
};
