#include "kst_time.h"

namespace sch {

namespace {

// H. Hinnant 의 days-from-civil: 1970-01-01 기준 일수 (m: 1..12, d: 1..31).
int32_t daysFromCivil(int32_t y, uint32_t m, uint32_t d) {
  y -= m <= 2;
  const int32_t era = (y >= 0 ? y : y - 399) / 400;
  const uint32_t yoe = static_cast<uint32_t>(y - era * 400);
  const uint32_t doy = (153 * (m > 2 ? m - 3 : m + 9) + 2) / 5 + d - 1;
  const uint32_t doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  return era * 146097 + static_cast<int32_t>(doe) - 719468;
}

// civil-from-days: 일수 → 연·월·일.
void civilFromDays(int32_t z, int32_t& y, uint32_t& m, uint32_t& d) {
  z += 719468;
  const int32_t era = (z >= 0 ? z : z - 146096) / 146097;
  const uint32_t doe = static_cast<uint32_t>(z - era * 146097);
  const uint32_t yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
  y = static_cast<int32_t>(yoe) + era * 400;
  const uint32_t doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
  const uint32_t mp = (5 * doy + 2) / 153;
  d = doy - (153 * mp + 2) / 5 + 1;
  m = mp < 10 ? mp + 3 : mp - 9;
  y += m <= 2;
}

}  // namespace

KstTime toKst(uint32_t epoch) {
  const int64_t local = static_cast<int64_t>(epoch) + kKstOffsetSec;
  const int32_t days = static_cast<int32_t>(local / 86400);
  const uint32_t sod = static_cast<uint32_t>(local % 86400);

  int32_t y;
  uint32_t m, d;
  civilFromDays(days, y, m, d);

  KstTime t;
  t.year = static_cast<uint16_t>(y);
  t.month = static_cast<uint8_t>(m);
  t.day = static_cast<uint8_t>(d);
  // 1970-01-01 은 목요일(4). (days+3) mod 7 → 0=월..6=일.
  t.weekday = static_cast<uint8_t>((days + 3) % 7 + 1);
  t.hour = static_cast<uint8_t>(sod / 3600);
  t.minute = static_cast<uint8_t>(sod % 3600 / 60);
  t.second = static_cast<uint8_t>(sod % 60);
  return t;
}

uint32_t kstMidnight(uint16_t year, uint8_t month, uint8_t day) {
  const int64_t days = daysFromCivil(year, month, day);
  return static_cast<uint32_t>(days * 86400 - kKstOffsetSec);
}

uint16_t minuteOfDay(const KstTime& t) {
  return static_cast<uint16_t>(t.hour * 60 + t.minute);
}

}  // namespace sch
