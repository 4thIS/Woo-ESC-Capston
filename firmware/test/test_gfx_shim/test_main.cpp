// Task 1 회귀 테스트: 벤더링한 Adafruit_GFX가 host 빌드에서 서브클래싱·상위 도형 함수까지 도는지 확인.
// Task 3(HostGfx)의 실제 프레임버퍼가 아니라, 이 shim/vendor 조합 자체가 깨지지 않는지만 본다.
#include <Adafruit_GFX.h>
#include <unity.h>

#include <vector>

struct PixelCall {
  int16_t x, y;
  uint16_t color;
};

class SpyGfx : public Adafruit_GFX {
 public:
  SpyGfx() : Adafruit_GFX(5, 5) {}
  std::vector<PixelCall> calls;
  void drawPixel(int16_t x, int16_t y, uint16_t color) override { calls.push_back({x, y, color}); }
};

void test_fill_screen_calls_draw_pixel_for_every_cell() {
  SpyGfx g;
  g.fillScreen(7);
  TEST_ASSERT_EQUAL(25, g.calls.size());  // 5x5
  TEST_ASSERT_EQUAL_UINT16(7, g.calls[0].color);
}

void test_draw_rect_border_only() {
  SpyGfx g;
  g.drawRect(0, 0, 5, 5, 1);
  // drawRect 는 4변을 각각 drawFastHLine/VLine 으로 그리므로 모서리 4개가 두 번씩 호출된다
  // (5+5+5+5=20, 실제 실행으로 확인 — 내부 9칸은 비어 있고 고유 픽셀은 16개지만 "호출 횟수"는 20).
  TEST_ASSERT_EQUAL(20, g.calls.size());
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_fill_screen_calls_draw_pixel_for_every_cell);
  RUN_TEST(test_draw_rect_border_only);
  return UNITY_END();
}
