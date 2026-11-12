#include <ArduinoJson.h>
#include <unity.h>

#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

#include "lora_codec.h"
#include "schedule.h"

// 리터럴은 Git Bash `TZ=KST-9 date -d @<epoch>` 로 확인한 값.
// PlatformIO native 테스트는 firmware/ 를 CWD 로 실행한다.
#define ROOM_STATE_VECTORS_PATH "../lora_proto/room_state_vectors.json"

static const uint32_t kTue0000 = 1791817200u;  // 화 2026-10-13 00:00 KST
static const uint32_t kWed0000 = 1791903600u;  // 수 2026-10-14 00:00 KST
static const uint32_t kTue0930 = 1791851400u;

static JsonDocument g_doc;

void setUp(void) {}
void tearDown(void) {}

static lc::SlotRec slot(uint8_t day, uint16_t s, uint16_t e, uint8_t type) {
  lc::SlotRec r{};
  r.day = day;
  r.sH = static_cast<uint8_t>(s / 60);
  r.sM = static_cast<uint8_t>(s % 60);
  r.eH = static_cast<uint8_t>(e / 60);
  r.eM = static_cast<uint8_t>(e % 60);
  r.type = type;
  return r;
}

static lc::ResvRec resv(uint8_t y, uint8_t m, uint8_t d, uint16_t s, uint16_t e, uint8_t type) {
  lc::ResvRec r{};
  r.y = y;
  r.m = m;
  r.d = d;
  r.sH = static_cast<uint8_t>(s / 60);
  r.sM = static_cast<uint8_t>(s % 60);
  r.eH = static_cast<uint8_t>(e / 60);
  r.eM = static_cast<uint8_t>(e % 60);
  r.type = type;
  return r;
}

static lc::ExamRec exam(uint8_t y1, uint8_t m1, uint8_t d1, uint8_t y2, uint8_t m2, uint8_t d2) {
  lc::ExamRec r{};
  r.y1 = y1;
  r.m1 = m1;
  r.d1 = d1;
  r.y2 = y2;
  r.m2 = m2;
  r.d2 = d2;
  return r;
}

void test_load_vectors() {
  FILE* f = fopen(ROOM_STATE_VECTORS_PATH, "rb");
  TEST_ASSERT_NOT_NULL_MESSAGE(f, "room_state_vectors.json 열기 실패");
  std::string s;
  char buf[4096];
  size_t n;
  while ((n = fread(buf, 1, sizeof buf, f)) > 0) s.append(buf, n);
  fclose(f);
  TEST_ASSERT_TRUE_MESSAGE(deserializeJson(g_doc, s) == DeserializationError::Ok, "JSON 파싱 실패");
}

static std::vector<lc::SlotRec> vectorSlots() {
  std::vector<lc::SlotRec> out;
  for (JsonObject j : g_doc["slots"].as<JsonArray>()) out.push_back(slot(2, j["s"], j["e"], j["type"]));
  return out;
}

void test_room_state_vectors() {
  const std::vector<lc::SlotRec> slots = vectorSlots();
  TEST_ASSERT_EQUAL_UINT32(12, slots.size());
  const lc::ExamRec todayExam = exam(26, 10, 13, 26, 10, 13);
  size_t count = 0;
  for (JsonObject vec : g_doc["vectors"].as<JsonArray>()) {
    const char* name = vec["name"];
    std::vector<lc::ResvRec> rs;
    const JsonArray resvs = vec["resvs"];
    for (JsonObject j : resvs) rs.push_back(resv(26, 10, 13, j["s"], j["e"], j["type"]));
    const bool inExam = vec["in_exam"];
    const sch::ScheduleView v{slots.data(),
                              static_cast<uint8_t>(slots.size()),
                              rs.data(),
                              static_cast<uint8_t>(rs.size()),
                              inExam ? &todayExam : nullptr,
                              static_cast<uint8_t>(inExam ? 1 : 0)};
    const uint32_t at = vec["at"];
    const uint32_t now = kTue0000 + at * 60;
    const uint8_t layout = vec["layout"];
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(layout, sch::determineLayout(v, now).layout, name);
    const uint32_t want =
        (vec["until"].isNull() ? kWed0000 : kTue0000 + vec["until"].as<uint32_t>() * 60) + 2;
    TEST_ASSERT_EQUAL_UINT32_MESSAGE(want, sch::nextChangeAt(v, now, 0xFFFFFFFFu), name);
    ++count;
  }
  TEST_ASSERT_EQUAL_UINT32(25, count);
}

void test_next_status_wins() {
  const sch::ScheduleView v{nullptr, 0, nullptr, 0, nullptr, 0};
  TEST_ASSERT_EQUAL_UINT32(1791824402u, sch::nextChangeAt(v, 1791820800u, 1791824400u));
}

void test_resv_other_date_ignored() {
  const lc::ResvRec r = resv(26, 10, 14, 540, 600, 6);
  const sch::ScheduleView v{nullptr, 0, &r, 1, nullptr, 0};
  TEST_ASSERT_EQUAL_UINT8(4, sch::determineLayout(v, kTue0930).layout);
  TEST_ASSERT_EQUAL_UINT32(1791903602u, sch::nextChangeAt(v, kTue0930, 0xFFFFFFFFu));
}

void test_exam_starts_tomorrow() {
  const lc::ExamRec x = exam(26, 10, 14, 26, 10, 15);
  const sch::ScheduleView v{nullptr, 0, nullptr, 0, &x, 1};
  TEST_ASSERT_EQUAL_UINT32(1791903602u, sch::nextChangeAt(v, kTue0930, 0xFFFFFFFFu));
}

void test_other_weekday_slot_ignored() {
  const lc::SlotRec s = slot(3, 540, 590, LP_SLOTTYPE_CLASS);
  const sch::ScheduleView v{&s, 1, nullptr, 0, nullptr, 0};
  TEST_ASSERT_EQUAL_UINT8(4, sch::determineLayout(v, kTue0930).layout);
}

void test_break_decider_is_next_slot() {
  const std::vector<lc::SlotRec> slots = vectorSlots();
  const sch::ScheduleView v{slots.data(), static_cast<uint8_t>(slots.size()), nullptr, 0, nullptr, 0};
  const sch::LayoutDecision d = sch::determineLayout(v, kTue0000 + 590 * 60);
  TEST_ASSERT_EQUAL_UINT8(LP_LAYOUT_BREAK, d.layout);
  TEST_ASSERT_TRUE(d.by == sch::Decider::Break);
  TEST_ASSERT_EQUAL_UINT8(1, d.index);  // 10:00 슬롯은 slots[1]
  TEST_ASSERT_EQUAL_UINT8(2, d.day);
  TEST_ASSERT_EQUAL_UINT16(600, d.slotStartMin);
}

void test_sunday_slot_matches() {
  const lc::SlotRec s = slot(7, 540, 590, LP_SLOTTYPE_CLASS);
  const sch::ScheduleView v{&s, 1, nullptr, 0, nullptr, 0};
  const sch::LayoutDecision d = sch::determineLayout(v, 1792283400u);  // 일 2026-10-18 09:30 KST
  TEST_ASSERT_EQUAL_UINT8(1, d.layout);
  TEST_ASSERT_TRUE(d.by == sch::Decider::Slot);
  TEST_ASSERT_EQUAL_UINT8(7, d.day);
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_load_vectors);
  RUN_TEST(test_room_state_vectors);
  RUN_TEST(test_next_status_wins);
  RUN_TEST(test_resv_other_date_ignored);
  RUN_TEST(test_exam_starts_tomorrow);
  RUN_TEST(test_other_weekday_slot_ignored);
  RUN_TEST(test_break_decider_is_next_slot);
  RUN_TEST(test_sunday_slot_matches);
  return UNITY_END();
}
