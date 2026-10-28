#pragma once
// S3 spec §4.3 — 실기(GxEPD2)·호스트(HostGfx) 공용 렌더 진입점.
// 화면 규격 원본: docs/design/screens/terminal-epaper.md
#include <Adafruit_GFX.h>

#include "render_model.h"

void renderLayout(Adafruit_GFX& gfx, const RenderModel& model);
