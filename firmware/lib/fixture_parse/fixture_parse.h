#pragma once
#include <cstddef>

#include "render_model.h"

// 픽스처 JSON(spec §4.4, snake_case) → RenderModel(camelCase). 실패 시 false.
// render_model.h 는 상대경로가 아니라 바로 include 한다 — firmware/lib/render_model/ 에 있어
// LDF가 lib 간 의존으로 자동으로 찾는다(이슈 #34, -Isrc/terminal 플래그 불필요). lib/fixture_parse/
// 에서 본 상대경로("../render_model/..." 등)로 적으면 이 헤더의 위치가 바뀔 때마다 같이 깨지므로 쓰지 않는다.
bool parseFixtureFile(const char* path, RenderModel& out, char* nameOut, size_t nameCap);
