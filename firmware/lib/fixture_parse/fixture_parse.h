#pragma once
#include <cstddef>

#include "render_model.h"

// 픽스처 JSON(spec §4.4, snake_case) → RenderModel(camelCase). 실패 시 false.
// render_model.h 는 상대경로가 아니라 바로 include 한다 — platformio.ini [env:native]의
// -Isrc/terminal 이 이 경로를 이미 잡고 있다(Task 2 근거). lib/fixture_parse/ 에서 본 상대
// 경로("../../src/terminal/...")로 적으면 이 헤더의 위치가 바뀔 때마다 같이 깨지므로 쓰지 않는다.
bool parseFixtureFile(const char* path, RenderModel& out, char* nameOut, size_t nameCap);
