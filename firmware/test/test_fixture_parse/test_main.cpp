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
  "now_str": "09:30", "date_str": "09.16", "weekday": 3,
  "prev": {"subj": "", "prof": "", "s_h": 0, "s_m": 0, "e_h": 0, "e_m": 0, "type": 0, "flags": 0},
  "cur":  {"subj": "자료구조", "prof": "김교수", "s_h": 9, "s_m": 0, "e_h": 9, "e_m": 50, "type": 1, "flags": 1},
  "next": {"subj": "", "prof": "", "s_h": 0, "s_m": 0, "e_h": 0, "e_m": 0, "type": 0, "flags": 0},
  "n_today": 1,
  "today": [ {"s_h": 9, "s_m": 0, "e_h": 9, "e_m": 50, "subj": "자료구조", "type": 1} ],
  "new_tag": "NEW-1A7F",
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
  TEST_ASSERT_TRUE(parseFixtureFile("t2.json", m, name, sizeof(name)));
  TEST_ASSERT_EQUAL_STRING("자료구조", m.cur.subj);
  TEST_ASSERT_EQUAL(9, m.cur.sH);
  TEST_ASSERT_EQUAL(50, m.cur.eM);
  remove("t2.json");
}

void test_parses_today_array() {
  writeFixture("t3.json", SAMPLE);
  RenderModel m{};
  char name[64];
  TEST_ASSERT_TRUE(parseFixtureFile("t3.json", m, name, sizeof(name)));
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

// 로드맵 §4.1(2026-09-16 추가) — date_str→dateStr·new_tag→newTag 매핑.
// new_tag 는 layout 8 전용이라 대부분의 픽스처에 없다. 없으면 빈 문자열로 떨어져야 한다.
void test_parses_date_str_and_new_tag() {
  writeFixture("t7.json", SAMPLE);
  RenderModel m{};
  char name[64];
  TEST_ASSERT_TRUE(parseFixtureFile("t7.json", m, name, sizeof(name)));
  TEST_ASSERT_EQUAL_STRING("09.16", m.dateStr);
  TEST_ASSERT_EQUAL_STRING("NEW-1A7F", m.newTag);
  remove("t7.json");

  writeFixture("t8.json", OVERSTATED_N_TODAY);  // date_str·new_tag 가 없는 픽스처
  RenderModel m2{};
  TEST_ASSERT_TRUE(parseFixtureFile("t8.json", m2, name, sizeof(name)));
  TEST_ASSERT_EQUAL_STRING("", m2.dateStr);
  TEST_ASSERT_EQUAL_STRING("", m2.newTag);
  remove("t8.json");
}

// 최상위가 객체가 아닌 JSON(배열·스칼라)은 deserializeJson 이 성공으로 처리한다.
// 가드가 없으면 모든 필드 접근이 `| 0`/`| ""` 기본값으로 채워져 전부 0 인 RenderModel 이
// true 와 함께 반환된다 — 망가진 픽스처가 조용히 통과한다. 실패로 떨어져야 한다.
void test_non_object_json_returns_false() {
  writeFixture("t6.json", "[]");
  RenderModel m{};
  char name[64];
  TEST_ASSERT_FALSE(parseFixtureFile("t6.json", m, name, sizeof(name)));
  remove("t6.json");
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
  RUN_TEST(test_parses_date_str_and_new_tag);
  RUN_TEST(test_non_object_json_returns_false);
  RUN_TEST(test_missing_file_returns_false);
  return UNITY_END();
}
