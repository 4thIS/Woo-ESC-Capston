#pragma once
// 픽셀을 찍지 않는 렌더 판단. 근거: docs/design/screens/terminal-epaper.md
// ("상태 띠", "레이아웃 8종", "오늘 목록 — 창 규칙").
#include <cstddef>
#include <cstdint>

#include "bitmap_image.h"
#include "render_model.h"

enum class BandStyle : uint8_t { None, Red, Black };

// 1·5·6·7 RED, 2·3·4 BLACK, 8·범위 밖 None(상태 띠를 그리지 않는다).
BandStyle bandStyle(uint8_t layout);
// layout 1~7 → 상태명 이미지. 8·범위 밖은 nullptr.
const BitmapImage* statusImage(uint8_t layout);
// 1=월 ~ 7=일 → "월요일" ~ "일요일". 범위 밖은 "".
const char* weekdayName(uint8_t weekday);
// type 2 시험·3 휴강·5 특강·6 대여 → 칩 이미지. 1 수업·그 밖은 nullptr(그리지 않는다).
const BitmapImage* typeChip(uint8_t type);
// "HH:MM"
void formatHM(uint8_t h, uint8_t m, char* out, size_t cap);
// 상태 띠 보조 문구. 쓸 문구가 없으면 false 이고 out 은 "".
bool statusSubline(const RenderModel& m, char* out, size_t cap);

struct TodayWindow {
  uint8_t count;      // 쓸 항목 수 — nToday 를 24 로 자른 값
  uint8_t start;      // 표시 0행의 항목 인덱스
  uint8_t rows;       // 표시 행 수(최대 9, "n개 더" 행 포함)
  uint8_t moreAbove;  // 0 이 아니면 0행을 "↑ n개 더"로 대체
  uint8_t moreBelow;  // 0 이 아니면 마지막 행을 "↓ n개 더"로 대체
  int8_t curIdx;      // 반전할 항목 인덱스, 없으면 -1
};
// 표시 행 r 의 항목은 today[start + r].
TodayWindow todayWindow(const RenderModel& m);
