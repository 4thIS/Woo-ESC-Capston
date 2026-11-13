#pragma once
#include <cstdint>

namespace sch {

constexpr int32_t kKstOffsetSec = 9 * 3600;  // v2 §5.2 — 서머타임 없음

struct KstTime {
  uint16_t year;
  uint8_t month, day;
  uint8_t weekday;  // 1=월..7=일 (SlotRec.day 와 같음)
  uint8_t hour, minute, second;
};

KstTime toKst(uint32_t epoch);
// 그 날 00:00 KST 의 epoch.
uint32_t kstMidnight(uint16_t year, uint8_t month, uint8_t day);
uint16_t minuteOfDay(const KstTime& t);  // hour*60 + minute

}  // namespace sch
