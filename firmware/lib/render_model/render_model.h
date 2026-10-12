#pragma once
// 로드맵 §4.1(확정) — cw(상태판단) → dh(렌더)로 넘기는 유일한 데이터. 렌더는 이 구조체 밖의 것을 읽지 않는다.
// today[24] 산정 근거: docs/specs/2026-09-16-s3-render-design.md §2.1
// qrUrl·battPct 없음: 2026-09-16 팀 결정(QR 미사용, PR #15) — 로드맵 r4 §4.1 그대로.
// 동결(cw-11, 이슈 #27, 2026-10-12): nowStr·prev 제거 — 화면이 현재 시각·이전 수업을 그리지 않는다(화면 스펙
// #19,
//   쉬는시간은 next 의 시작 시각만, #74). 필드를 바꾸려면 cw·dh 협의 후 로드맵 §4.1 과 같이 고친다.
// type 값 = lora_proto SlotType: 1 수업 · 2 시험 · 3 휴강 · 4 빈강의실 · 5 특강 · 6 대여 (0 = 비어 있음).
#include <cstdint>

struct RenderSlot {
  char subj[21];
  char prof[13];
  uint8_t sH, sM, eH, eM;
  uint8_t type;   // lora_proto SlotType (위 주석)
  uint8_t flags;  // bit0 존재함, bit1 변경 배지
};

struct TodaySlot {
  uint8_t sH, sM, eH, eM;
  char subj[21];
  uint8_t type;  // lora_proto SlotType
};

struct RenderModel {
  uint8_t layout;
  char bld;
  uint16_t room;
  uint8_t unit;
  char dateStr[6];  // "MM.DD" (2026-09-16 추가, mh 화면 스펙 미결 1)
  uint8_t weekday;
  RenderSlot cur, next;
  uint8_t nToday;
  TodaySlot today[24];  // 하루 최대 24 로 동결(#27). 넘치면 상태 판단이 시작 순 앞 24개만 싣는다
  char newTag[9];       // "NEW-1A7F" — layout 8 전용, MAC 하위 2 B (2026-09-16 추가, mh 화면 스펙 미결 2)
  uint16_t battMv;
};
