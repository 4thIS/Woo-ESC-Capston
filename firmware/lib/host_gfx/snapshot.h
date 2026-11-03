#pragma once
// 렌더 스냅샷 대조 — HostGfx 프레임버퍼를 정답 PNG 와 픽셀 단위로 비교한다(호스트 전용, dh-05).
// 정답은 test/fixtures/render/snapshots/<픽스처>.png, 다시 만드는 명령은 tools/render_preview.py
// --update-snapshots.
#include "host_gfx.h"

struct SnapshotDiff {
  bool baselineLoaded;  // 파일 없음·디코드 실패·크기가 gfx 와 다름이면 false
  long diffPixels;      // baselineLoaded 일 때만 의미. RGB 가 하나라도 다르면 1 픽셀
};

SnapshotDiff compareToBaseline(const HostGfx& g, const char* baselinePng);

// 차이 이미지: 같은 픽셀은 흐리게(흰 그대로, 검정 → (160,160,160), 빨강 → (255,180,180)),
// 다른 픽셀은 (0,0,255). 정답을 못 읽으면 false.
bool saveDiffPNG(const HostGfx& g, const char* baselinePng, const char* outPng);
