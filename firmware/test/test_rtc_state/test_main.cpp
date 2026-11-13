#include <unity.h>

#include <cstddef>
#include <cstdint>
#include <cstdio>

#include "rtc_state.h"

using ns::RtcState;

void test_cleared_is_invalid() {
  RtcState s;
  ns::rtcClear(s);
  TEST_ASSERT_FALSE(ns::rtcValid(s));
}

void test_seal_then_valid() {
  RtcState s;
  ns::rtcClear(s);
  s.bld = 3;
  s.room = 101;
  s.slotsDay = 2;
  s.nSlots = 1;
  s.slots[0].sH = 9;
  ns::rtcSeal(s);
  TEST_ASSERT_EQUAL_UINT32(ns::kRtcMagic, s.magic);
  TEST_ASSERT_TRUE(ns::rtcValid(s));
}

// seal 뒤 슬롯 한 바이트라도 바뀌면 CRC 불일치로 무효.
void test_flip_byte_invalid() {
  RtcState s;
  ns::rtcClear(s);
  s.nSlots = 1;
  s.slots[0].sH = 9;
  ns::rtcSeal(s);
  s.slots[0].sH ^= 1;
  TEST_ASSERT_FALSE(ns::rtcValid(s));
}

// 레이아웃 버전이 다른 옛 캐시는 CRC 가 맞아도 무효.
void test_old_layout_magic_invalid() {
  RtcState s;
  ns::rtcClear(s);
  ns::rtcSeal(s);
  s.magic = ns::kRtcMagicBase | (ns::kRtcLayoutVer + 1);
  s.crc = lc::crc16(reinterpret_cast<const uint8_t*>(&s), offsetof(RtcState, crc));
  TEST_ASSERT_FALSE(ns::rtcValid(s));
}

// 직전 레이아웃(#141 이전)으로 봉인된 캐시도 CRC 가 맞아도 무효.
void test_prev_layout_magic_invalid() {
  RtcState s;
  ns::rtcClear(s);
  ns::rtcSeal(s);
  s.magic = ns::kRtcMagicBase | (ns::kRtcLayoutVer - 1);
  s.crc = lc::crc16(reinterpret_cast<const uint8_t*>(&s), offsetof(RtcState, crc));
  TEST_ASSERT_FALSE(ns::rtcValid(s));
}

void test_size_within_budget() {
  char msg[48];
  std::snprintf(msg, sizeof(msg), "sizeof(RtcState) = %u B", static_cast<unsigned>(sizeof(RtcState)));
  TEST_MESSAGE(msg);
  TEST_ASSERT_LESS_OR_EQUAL(4096, sizeof(RtcState));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_cleared_is_invalid);
  RUN_TEST(test_seal_then_valid);
  RUN_TEST(test_flip_byte_invalid);
  RUN_TEST(test_old_layout_magic_invalid);
  RUN_TEST(test_prev_layout_magic_invalid);
  RUN_TEST(test_size_within_budget);
  return UNITY_END();
}
