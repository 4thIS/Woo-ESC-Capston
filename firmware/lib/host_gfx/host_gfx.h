#pragma once
#include <Adafruit_GFX.h>

#include <cstdint>
#include <vector>

// ⚠️ 색상 규약 경고 (전체 리뷰 finding I-1) — dh-04 착수 전 반드시 읽을 것.
//
// 아래 0/1/2 는 **호스트 프리뷰 전용 내부 표현**이며, 실기 GxEPD2 의 색상 상수
// (`GxEPD_BLACK`/`GxEPD_WHITE`/`GxEPD_RED` — 통상 RGB565 류 값)와 **일치하지 않는다.**
// `HostGfx::drawPixel` 은 Adafruit_GFX 가 넘겨준 `uint16_t color` 를
// `static_cast<HColor>(color)` 로 그대로 해석하므로, dh-04 가 v1 렌더 코드를 이식하면서
// 렌더 함수에 GxEPD2 상수를 그대로 넘기면 값이 엉뚱하게 매핑된다 —
// 예: `GxEPD_BLACK`(=0x0000)이 `HColor::WHITE`(=0)로 들어와 검정이 통째로 흰색이 된다.
// 컴파일 에러도 런타임 에러도 나지 않고 **조용히 빈 PNG 가 나온다.**
//
// 따라서 dh-04 착수 전에 색상 규약을 먼저 확정한다(렌더 함수가 쓸 색 상수를 한 곳에
// 정의하고 호스트·실기가 각자 자기 값으로 변환하든, HColor 값을 GxEPD2 상수에 맞추든).
// 지금은 실기 코드가 리포에 없어 완전한 수정이 불가능해 문서화만 해 둔다.
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
