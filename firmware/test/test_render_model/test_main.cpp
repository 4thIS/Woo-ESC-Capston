#include <unity.h>

#include <cstring>

#include "render_model.h"

void test_today_capacity_is_24() {
  RenderModel m{};
  TEST_ASSERT_EQUAL(24, sizeof(m.today) / sizeof(m.today[0]));
}

void test_fields_are_assignable() {
  RenderModel m{};
  m.layout = 1;
  m.bld = 'E';
  m.room = 301;
  m.unit = 1;
  std::strcpy(m.nowStr, "09:30");
  m.weekday = 3;
  std::strcpy(m.cur.subj, "자료구조");
  std::strcpy(m.cur.prof, "김교수");
  m.cur.sH = 9;
  m.cur.sM = 0;
  m.cur.eH = 9;
  m.cur.eM = 50;
  m.cur.type = 1;
  m.cur.flags = 1;
  m.nToday = 1;
  m.today[0] = {9, 0, 9, 50, "", 1};
  m.battMv = 3900;
  TEST_ASSERT_EQUAL(1, m.layout);
  TEST_ASSERT_EQUAL_STRING("자료구조", m.cur.subj);
  TEST_ASSERT_EQUAL(24, sizeof(m.today) / sizeof(m.today[0]));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_today_capacity_is_24);
  RUN_TEST(test_fields_are_assignable);
  return UNITY_END();
}
