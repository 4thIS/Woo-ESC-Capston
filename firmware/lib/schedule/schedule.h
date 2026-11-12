#pragma once
#include <cstdint>

#include "lora_codec.h"

// 강의실 상태 판정 (v2 §5.3·§5.4). lora_proto/room_state_vectors.json 으로 서버 room_state 와 대조한다.
namespace sch {

struct ScheduleView {
  const lc::SlotRec* slots;
  uint8_t nSlots;  // 오늘 요일 슬롯(RTC slots[]). 다른 요일은 무시
  const lc::ResvRec* resv;
  uint8_t nResv;  // 전체 — 오늘 날짜만 본다
  const lc::ExamRec* exams;
  uint8_t nExam;
};

enum class Decider : uint8_t { Resv, ExamSlot, Slot, Break, Free };
constexpr uint16_t kNoSlot = 0xFFFF;

struct LayoutDecision {
  uint8_t layout;
  Decider by;
  // Resv: resv[] 위치 · ExamSlot/Slot: slots[] 위치 · Break: 다음 슬롯의 slots[] 위치 · Free: 0xFF
  uint8_t index;
  uint8_t day;  // 상태키 day (1..7)
  // 상태키 curSlotStart — 결정 항목의 시작(분). Break = 다음 슬롯 시작, Free = kNoSlot
  uint16_t slotStartMin;
};

LayoutDecision determineLayout(const ScheduleView& v, uint32_t nowEpoch);
// 화면이 바뀌는 다음 시각(+2 s). 후보: 오늘 상태 경계, 다음 자정, 시험 시작·종료 다음날 00:00,
// nextStatusEpoch.
uint32_t nextChangeAt(const ScheduleView& v, uint32_t nowEpoch, uint32_t nextStatusEpoch);

}  // namespace sch
