#include <unity.h>

#include <cstdio>

#include "fixture_parse.h"
#include "host_gfx.h"
#include "render.h"

// 픽스처 → renderLayout → PNG 파이프라인 전체. 화면 세부는 test_render_layout 이 본다.
void test_pipeline_end_to_end() {
  RenderModel m{};
  char name[64];
  // PlatformIO native 테스트의 CWD 는 firmware/ (test_codec/vectors_path.h 와 같은 전제).
  TEST_ASSERT_TRUE(parseFixtureFile("test/fixtures/render/layout1_class.json", m, name, sizeof(name)));
  HostGfx g;
  renderLayout(g, m);
  TEST_ASSERT_EQUAL(HColor::RED, g.pixelAt(10, 60));     // layout 1 = RED 상태 띠
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(400, 50));  // 헤더 하단선
  TEST_ASSERT_TRUE(g.savePNG("layout1_class_out.png"));
  FILE* f = fopen("layout1_class_out.png", "rb");
  TEST_ASSERT_NOT_NULL(f);
  fclose(f);
  remove("layout1_class_out.png");
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_pipeline_end_to_end);
  return UNITY_END();
}
