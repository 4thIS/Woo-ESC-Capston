// RTC 메모리 캐시 구조체 — v2 §5.1 rtc_state_t. 표준 C++ 만 쓴다 — Arduino/ESP 헤더 금지.
// 딥슬립을 건너 살아남는 4 KB 캐시. 매직·CRC 가 맞지 않으면 콜드부트로 보고 flash 에서 다시 채운다.
#pragma once

#include <cstddef>
#include <cstdint>

#include "lora_codec.h"
#include "record_file.h"

namespace ns {

constexpr uint32_t kRtcMagicBase = 0x52544300u;  // 'R''T''C' + 하위 바이트 = 레이아웃 버전
constexpr uint32_t kRtcLayoutVer = 1;            // 구조를 바꾸면 +1 → 옛 캐시 자동 무효화
constexpr uint32_t kRtcMagic = kRtcMagicBase | kRtcLayoutVer;

struct RtcState {
  uint32_t magic;
  uint8_t bld;
  uint16_t room;
  uint8_t unit;
  uint8_t provisioned;
  uint8_t schedVer, resvVer, examVer, identVer, lastTxn;
  uint8_t lastLayout;
  uint8_t lastDay;
  uint16_t lastSlotStartMin;  // 상태키 — cw-14
  uint32_t lastTimeSyncEpoch;
  uint32_t nextStatusEpoch;  // cw-14
  uint8_t slotsDay;          // slots[] 의 요일, 0 = 비어 있음
  uint8_t nSlots;
  lc::SlotRec slots[LP_SLOT_DAY_MAX];  // 오늘 슬롯만
  uint8_t nResv;
  lc::ResvRec resv[kResvMax];
  uint8_t nExam;
  lc::ExamRec exams[kExamMax];
  uint16_t crc;  // lc::crc16, [0, offsetof(crc)) 범위
};
static_assert(sizeof(RtcState) <= 4096, "RTC 캐시 4 KB 예산(#74)");

void rtcClear(RtcState& s);        // memset 0 — 패딩까지 0이라야 CRC가 결정적
void rtcSeal(RtcState& s);         // magic·crc 기록. cw가 잠들기 직전 호출
bool rtcValid(const RtcState& s);  // magic == kRtcMagic && crc 일치

}  // namespace ns
