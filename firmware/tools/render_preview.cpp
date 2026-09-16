// 픽스처 JSON 1개 → PNG 1장. dh-04 전까지는 smokeRender() 가 파이프라인만 증명한다.
// main() 을 가진 실행파일 진입점이라 test/ 밖(tools/)에 둔다 — pio test 가 링크하면
// Unity 의 main() 과 충돌한다. 빌드 환경(native_preview)은 Task 6 에서 추가한다.
#include <cstdio>

#include "fixture_parse.h"
#include "host_gfx.h"

void smokeRender(Adafruit_GFX& gfx, const RenderModel& model) {
  gfx.fillScreen((uint16_t)HColor::WHITE);
  gfx.drawRect(0, 0, 800, 480, (uint16_t)HColor::BLACK);
  if (model.layout >= 1 && model.layout <= 8) {
    gfx.fillRect(10, 10, 20, 20, (uint16_t)HColor::RED);
  }
}

int main(int argc, char** argv) {
  if (argc < 3) {
    fprintf(stderr, "usage: render_preview <fixture.json> <out.png>\n");
    return 1;
  }
  RenderModel model{};
  char name[64];
  if (!parseFixtureFile(argv[1], model, name, sizeof(name))) {
    fprintf(stderr, "fixture parse failed: %s\n", argv[1]);
    return 1;
  }
  HostGfx gfx;
  smokeRender(gfx, model);
  if (!gfx.savePNG(argv[2])) {
    fprintf(stderr, "PNG 저장 실패: %s\n", argv[2]);
    return 1;
  }
  printf("wrote %s (%s)\n", argv[2], name);
  return 0;
}
