#include <unity.h>

#include <cstdint>

#include "kst_time.h"

// 리터럴은 Git Bash `TZ=KST-9 date -d @<epoch>` 로 확인한 값.
static void expectKst(uint32_t epoch, uint16_t y, uint8_t mo, uint8_t d, uint8_t wd, uint8_t h, uint8_t mi,
                      uint8_t s) {
  const sch::KstTime t = sch::toKst(epoch);
  TEST_ASSERT_EQUAL_UINT16(y, t.year);
  TEST_ASSERT_EQUAL_UINT8(mo, t.month);
  TEST_ASSERT_EQUAL_UINT8(d, t.day);
  TEST_ASSERT_EQUAL_UINT8(wd, t.weekday);
  TEST_ASSERT_EQUAL_UINT8(h, t.hour);
  TEST_ASSERT_EQUAL_UINT8(mi, t.minute);
  TEST_ASSERT_EQUAL_UINT8(s, t.second);
}

void test_midnight_tuesday() {
  expectKst(1791817200u, 2026, 10, 13, 2, 0, 0, 0);
}

void test_afternoon() {
  expectKst(1791866998u, 2026, 10, 13, 2, 13, 49, 58);
}

void test_year_end_last_second() {
  expectKst(1798729199u, 2026, 12, 31, 4, 23, 59, 59);
}

void test_year_rollover() {
  expectKst(1798729200u, 2027, 1, 1, 5, 0, 0, 0);
}

void test_leap_day() {
  expectKst(1835362800u, 2028, 2, 29, 2, 0, 0, 0);
}

void test_round_number() {
  expectKst(1700000000u, 2023, 11, 15, 3, 7, 13, 20);
}

// UTC 15:00 = KST 다음 날 00:00 — 오프셋이 날짜를 넘기는 경계.
void test_utc_evening_is_next_kst_day() {
  expectKst(1791817199u, 2026, 10, 12, 1, 23, 59, 59);
}

void test_kst_midnight_literals() {
  TEST_ASSERT_EQUAL_UINT32(1791817200u, sch::kstMidnight(2026, 10, 13));
  TEST_ASSERT_EQUAL_UINT32(1798729200u, sch::kstMidnight(2027, 1, 1));
  TEST_ASSERT_EQUAL_UINT32(1835362800u, sch::kstMidnight(2028, 2, 29));
}

void test_kst_midnight_roundtrip() {
  const sch::KstTime t = sch::toKst(1791866998u);
  const uint32_t mid = sch::kstMidnight(t.year, t.month, t.day);
  TEST_ASSERT_EQUAL_UINT32(1791817200u, mid);
  TEST_ASSERT_EQUAL_UINT32(1791866998u - mid, 13u * 3600 + 49 * 60 + 58);
}

void test_minute_of_day() {
  TEST_ASSERT_EQUAL_UINT16(0, sch::minuteOfDay(sch::toKst(1791817200u)));
  TEST_ASSERT_EQUAL_UINT16(13 * 60 + 49, sch::minuteOfDay(sch::toKst(1791866998u)));
  TEST_ASSERT_EQUAL_UINT16(23 * 60 + 59, sch::minuteOfDay(sch::toKst(1798729199u)));
  TEST_ASSERT_EQUAL_UINT16(7 * 60 + 13, sch::minuteOfDay(sch::toKst(1700000000u)));
}

void setUp() {}
void tearDown() {}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_midnight_tuesday);
  RUN_TEST(test_afternoon);
  RUN_TEST(test_year_end_last_second);
  RUN_TEST(test_year_rollover);
  RUN_TEST(test_leap_day);
  RUN_TEST(test_round_number);
  RUN_TEST(test_utc_evening_is_next_kst_day);
  RUN_TEST(test_kst_midnight_literals);
  RUN_TEST(test_kst_midnight_roundtrip);
  RUN_TEST(test_minute_of_day);
  return UNITY_END();
}
