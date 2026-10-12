#pragma once
#include <Adafruit_GFX.h>

#include <cstdint>
#include <vector>

// ⚠️ 색상 규약 (전체 리뷰 finding I-1 해소) — 값을 바꾸지 말 것.
//
// 아래 값은 임의의 내부 번호가 아니라 **실기 GxEPD2 의 색상 상수 그 자체**다.
// 규약을 호스트용·실기용 두 벌로 나누지 않고 하나로 맞춰 둔 것이라,
// dh-04 가 v1 렌더 코드를 **무수정으로** 이식해 GxEPD2 상수를 렌더 함수에 그대로 넘겨도
// `HostGfx::drawPixel` 이 같은 색으로 해석한다. (출처: cw 의 PR #23 승인 코멘트)
//
// 호스트 빌드에는 GxEPD2 라이브러리가 없어 이 세 매크로를 정의한 곳이 없었다.
// v1 의 `ngDrawChar`/`ngPrintLine`/`ngPrint` 는 `uint16_t color = GxEPD_BLACK` 를 기본 인자로
// 쓰므로 이름 자체가 필요하다 → 여기서 매크로로 정의하고, `HColor` 는 그 매크로를 그대로 쓴다.
// 값이 한 곳에만 존재하므로 매크로와 enum 이 어긋나는 상태를 만들 수 없다.
// (실기 빌드는 이 헤더를 쓰지 않고 GxEPD2 의 정의를 쓴다.)
//
// 이전에는 0/1/2 였고, 그 경우 `GxEPD_BLACK`(=0x0000)이 `HColor::WHITE`(=0)로 들어와
// 검정이 통째로 흰색이 되는 — 컴파일 에러도 런타임 에러도 없이 **조용히 빈 PNG 가 나오는**
// 사고가 가능했다. 값 자체가 맞는지는 test_host_gfx 의
// `test_hcolor_values_match_gxepd2_constants` 가 숫자를 못 박아 지킨다.
// 세 값 밖의 색을 넘기면 drawPixel 이 assert 로 시끄럽게 실패한다(조용한 오염 방지).
#define GxEPD_WHITE 0xFFFF
#define GxEPD_BLACK 0x0000
#define GxEPD_RED 0xF800

enum class HColor : uint16_t { WHITE = GxEPD_WHITE, BLACK = GxEPD_BLACK, RED = GxEPD_RED };

// 위 정의 방식에서 이 어서션은 자명하게 참이다 — 누군가 enum 을 다시 숫자 리터럴로 되돌리면
// 그때 컴파일이 깨지라고 둔다(런타임 테스트보다 먼저 걸린다).
static_assert(static_cast<uint16_t>(HColor::WHITE) == GxEPD_WHITE, "HColor::WHITE != GxEPD_WHITE");
static_assert(static_cast<uint16_t>(HColor::BLACK) == GxEPD_BLACK, "HColor::BLACK != GxEPD_BLACK");
static_assert(static_cast<uint16_t>(HColor::RED) == GxEPD_RED, "HColor::RED != GxEPD_RED");

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
