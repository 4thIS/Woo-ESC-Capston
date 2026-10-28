// 픽스처 JSON 1개 → PNG 1장. renderLayout()(lib/render/)으로 그린다.
// main() 을 가진 실행파일 진입점이라 test/ 밖(tools/)에 둔다 — pio test 가 링크하면
// Unity 의 main() 과 충돌한다. 빌드는 [env:native_preview].
#include <cstdio>

#include "fixture_parse.h"
#include "host_gfx.h"
#include "render.h"

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
  renderLayout(gfx, model);
  if (!gfx.savePNG(argv[2])) {
    fprintf(stderr, "PNG 저장 실패: %s\n", argv[2]);
    return 1;
  }
  printf("wrote %s (%s)\n", argv[2], name);
  return 0;
}
