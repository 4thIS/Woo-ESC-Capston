#pragma once
#include <Adafruit_GFX.h>

#include <cstdint>
#include <vector>

// 색상 규약 (전체 리뷰 finding I-1 해소) — 값을 바꾸지 말 것.
//
// 아래 값은 임의의 내부 번호가 아니라 **실기 GxEPD2 의 색상 상수 그 자체**다
// (`GxEPD_WHITE`=0xFFFF, `GxEPD_BLACK`=0x0000, `GxEPD_RED`=0xF800).
// 규약을 호스트용·실기용 두 벌로 나누지 않고 하나로 맞춰 둔 것이라,
// dh-04 가 v1 렌더 코드를 **무수정으로** 이식해 GxEPD2 상수를 렌더 함수에 그대로 넘겨도
// `HostGfx::drawPixel` 이 같은 색으로 해석한다. (출처: cw 의 PR #23 승인 코멘트)
//
// 이전에는 0/1/2 였고, 그 경우 `GxEPD_BLACK`(=0x0000)이 `HColor::WHITE`(=0)로 들어와
// 검정이 통째로 흰색이 되는 — 컴파일 에러도 런타임 에러도 없이 **조용히 빈 PNG 가 나오는**
// 사고가 가능했다. 값 일치는 test_host_gfx 의
// `test_hcolor_values_match_gxepd2_constants` 가 지킨다.
// 세 값 밖의 색을 넘기면 drawPixel 이 assert 로 시끄럽게 실패한다(조용한 오염 방지).
enum class HColor : uint16_t { WHITE = 0xFFFF, BLACK = 0x0000, RED = 0xF800 };

// 3색 e-Paper 색 → PNG 로 내보낼 RGB. savePNG 가 쓰는 유일한 "출력이 맞는가" 판정 지점이라
// 테스트 가능하도록 순수 함수로 분리해 둔다. 아는 값이 아니면 WHITE 로 떨어진다.
void hcolorToRGB(HColor c, uint8_t& r, uint8_t& g, uint8_t& b);

// 800x480x3색 호스트 프레임버퍼. Adafruit_GFX 파생이라 fillRect/print/drawBitmap 등
// 상위 도형 함수는 전부 Adafruit_GFX 원본 코드가 그린다 — 우리는 drawPixel만 구현한다.
class HostGfx : public Adafruit_GFX {
 public:
  explicit HostGfx(int16_t w = 800, int16_t h = 480);
  void drawPixel(int16_t x, int16_t y, uint16_t color) override;
  // 호스트 프리뷰는 회전을 지원하지 않는다(프레임버퍼·PNG 가 800x480 고정).
  // r != 0 이면 assert 로 즉시 중단한다 — 조용히 무시하면 실기와 다른 그림이 나온다.
  void setRotation(uint8_t r) override;
  HColor pixelAt(int16_t x, int16_t y) const;
  bool savePNG(const char* path) const;

 private:
  int16_t w_, h_;
  std::vector<HColor> buf_;
};
