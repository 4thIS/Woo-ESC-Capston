#include <unity.h>

#include <cstdio>
#include <cstring>

#include "fixture_parse.h"

static void writeFixture(const char* path, const char* json) {
  FILE* f = fopen(path, "wb");
  fwrite(json, 1, strlen(json), f);
  fclose(f);
}

const char* SAMPLE = R"({
  "name": "layout1_class_basic",
  "layout": 1, "bld": "E", "room": 301, "unit": 1,
  "now_str": "09:30", "weekday": 3,
  "prev": {"subj": "", "prof": "", "s_h": 0, "s_m": 0, "e_h": 0, "e_m": 0, "type": 0, "flags": 0},
  "cur":  {"subj": "자료구조", "prof": "김교수", "s_h": 9, "s_m": 0, "e_h": 9, "e_m": 50, "type": 1, "flags": 1},
  "next": {"subj": "", "prof": "", "s_h": 0, "s_m": 0, "e_h": 0, "e_m": 0, "type": 0, "flags": 0},
  "n_today": 1,
  "today": [ {"s_h": 9, "s_m": 0, "e_h": 9, "e_m": 50, "subj": "자료구조", "type": 1} ],
  "batt_mv": 3900
})";

void test_parses_all_top_level_fields() {
  writeFixture("t1.json", SAMPLE);
  RenderModel m{};
  char name[64] = {0};
  TEST_ASSERT_TRUE(parseFixtureFile("t1.json", m, name, sizeof(name)));
  TEST_ASSERT_EQUAL_STRING("layout1_class_basic", name);
  TEST_ASSERT_EQUAL(1, m.layout);
  TEST_ASSERT_EQUAL('E', m.bld);
  TEST_ASSERT_EQUAL(301, m.room);
  TEST_ASSERT_EQUAL_STRING("09:30", m.nowStr);
  remove("t1.json");
}

void test_parses_nested_slot_snake_case_to_camel() {
  writeFixture("t2.json", SAMPLE);
  RenderModel m{};
  char name[64];
  parseFixtureFile("t2.json", m, name, sizeof(name));
  TEST_ASSERT_EQUAL_STRING("자료구조", m.cur.subj);
  TEST_ASSERT_EQUAL(9, m.cur.sH);
  TEST_ASSERT_EQUAL(50, m.cur.eM);
  remove("t2.json");
}

void test_parses_today_array() {
  writeFixture("t3.json", SAMPLE);
  RenderModel m{};
  char name[64];
  parseFixtureFile("t3.json", m, name, sizeof(name));
  TEST_ASSERT_EQUAL(1, m.nToday);
  TEST_ASSERT_EQUAL(9, m.today[0].sH);
  TEST_ASSERT_EQUAL_STRING("자료구조", m.today[0].subj);
  remove("t3.json");
}

// n_today 가 실제 today[] 길이보다 크면 소비자가 미초기화 슬롯을 읽는다.
// 파서는 실제로 채운 개수로 보정해야 한다.
const char* OVERSTATED_N_TODAY = R"({
  "name": "overstated", "layout": 1, "bld": "E", "room": 301, "unit": 1,
  "now_str": "09:30", "weekday": 3,
  "n_today": 5,
  "today": [ {"s_h": 9, "s_m": 0, "e_h": 9, "e_m": 50, "subj": "자료구조", "type": 1} ],
  "batt_mv": 3900
})";

void test_n_today_clamped_to_actual_array_length() {
  writeFixture("t5.json", OVERSTATED_N_TODAY);
  RenderModel m{};
  char name[64];
  TEST_ASSERT_TRUE(parseFixtureFile("t5.json", m, name, sizeof(name)));
  TEST_ASSERT_EQUAL(1, m.nToday);
  remove("t5.json");
}

void test_missing_file_returns_false() {
  RenderModel m{};
  char name[64];
  TEST_ASSERT_FALSE(parseFixtureFile("does_not_exist.json", m, name, sizeof(name)));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_parses_all_top_level_fields);
  RUN_TEST(test_parses_nested_slot_snake_case_to_camel);
  RUN_TEST(test_parses_today_array);
  RUN_TEST(test_n_today_clamped_to_actual_array_length);
  RUN_TEST(test_missing_file_returns_false);
  return UNITY_END();
}
