#include "rtc_state.h"

#include <cstring>

namespace ns {

namespace {

uint16_t calcCrc(const RtcState& s) {
  return lc::crc16(reinterpret_cast<const uint8_t*>(&s), offsetof(RtcState, crc));
}

}  // namespace

void rtcClear(RtcState& s) {
  std::memset(&s, 0, sizeof(s));
}

void rtcSeal(RtcState& s) {
  s.magic = kRtcMagic;
  s.crc = calcCrc(s);
}

bool rtcValid(const RtcState& s) {
  return s.magic == kRtcMagic && s.crc == calcCrc(s);
}

}  // namespace ns
