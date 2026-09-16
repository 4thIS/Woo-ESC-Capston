#pragma once
// spec §4.2 — cw(상태판단) → dh(렌더)로 넘기는 유일한 데이터. 렌더는 이 구조체 밖의 것을 읽지 않는다.
// today[24] 산정 근거: docs/specs/2026-09-16-s3-render-design.md §2.1
#include <cstdint>

struct RenderSlot {
  char subj[21];
  char prof[13];
  uint8_t sH, sM, eH, eM;
  uint8_t type;
  uint8_t flags;  // bit0 존재함, bit1 변경 배지
};

struct TodaySlot {
  uint8_t sH, sM, eH, eM;
  char subj[21];
  uint8_t type;
};

struct RenderModel {
  uint8_t layout;
  char bld;
  uint16_t room;
  uint8_t unit;
  char nowStr[6];
  uint8_t weekday;
  RenderSlot prev, cur, next;
  uint8_t nToday;
  TodaySlot today[24];
  char qrUrl[48];
  uint16_t battMv;
  uint8_t battPct;
};
