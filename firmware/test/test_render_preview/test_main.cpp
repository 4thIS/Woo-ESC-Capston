#include <unity.h>

#include <cstdio>

#include "fixture_parse.h"
#include "host_gfx.h"

// smokeRender: dh-04 교체 대상. 여기서는 파이프라인 증명용 최소 그리기만 한다.
// tools/render_preview.cpp 의 동명 함수와 같은 내용이지만, tools/ 는 pio test 가
// 링크하지 않으므로(실행파일 main 충돌 방지) 여기서 따로 정의한다.
void smokeRender(Adafruit_GFX& gfx, const RenderModel& model) {
  gfx.fillScreen((uint16_t)HColor::WHITE);
  gfx.drawRect(0, 0, 800, 480, (uint16_t)HColor::BLACK);
  if (model.layout >= 1 && model.layout <= 8) {
    gfx.fillRect(10, 10, 20, 20, (uint16_t)HColor::RED);  // layout 존재 확인용 마커
  }
}

void test_pipeline_end_to_end() {
  RenderModel m{};
  char name[64];
  // PlatformIO native 테스트의 CWD 는 firmware/ (test_codec/vectors_path.h 와 같은 전제).
  TEST_ASSERT_TRUE(parseFixtureFile("test/fixtures/render/smoke_basic.json", m, name, sizeof(name)));
  HostGfx g;
  smokeRender(g, m);
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(0, 0));  // 테두리
  TEST_ASSERT_EQUAL(HColor::RED, g.pixelAt(15, 15));  // 마커
  TEST_ASSERT_TRUE(g.savePNG("smoke_basic_out.png"));
  FILE* f = fopen("smoke_basic_out.png", "rb");
  TEST_ASSERT_NOT_NULL(f);
  fclose(f);
  remove("smoke_basic_out.png");
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_pipeline_end_to_end);
  return UNITY_END();
}
