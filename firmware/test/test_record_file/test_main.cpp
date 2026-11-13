#include <unity.h>

#include <cstdint>
#include <cstring>

#include "lora_codec.h"
#include "record_file.h"

using ns::ParseResult;

namespace {

lc::SlotRec makeSlot(uint8_t day, uint8_t sH, uint8_t sM, const char* subj = "과목",
                     const char* prof = "교수") {
  lc::SlotRec r{};
  r.day = day;
  r.sH = sH;
  r.sM = sM;
  r.eH = sH;
  r.eM = static_cast<uint8_t>(sM + 50 > 59 ? 59 : sM + 50);
  r.type = LP_SLOTTYPE_CLASS;
  std::strncpy(r.subj, subj, LP_SUBJ_MAX);
  std::strncpy(r.prof, prof, LP_PROF_MAX);
  return r;
}

lc::ResvRec makeResv(uint16_t id) {
  lc::ResvRec r{};
  r.resvId = id;
  r.y = 26;
  r.m = 11;
  r.d = 5;
  r.sH = 14;
  r.sM = 0;
  r.eH = 15;
  r.eM = 30;
  r.type = LP_SLOTTYPE_CLASS;
  std::strncpy(r.subj, "스터디", LP_SUBJ_MAX);
  std::strncpy(r.prof, "박", LP_PROF_MAX);
  return r;
}

lc::ExamRec makeExam(uint16_t id) {
  lc::ExamRec r{};
  r.examId = id;
  r.y1 = 26;
  r.m1 = 12;
  r.d1 = 14;
  r.y2 = 26;
  r.m2 = 12;
  r.d2 = 20;
  return r;
}

bool sameSlot(const lc::SlotRec& a, const lc::SlotRec& b) {
  return a.day == b.day && a.sH == b.sH && a.sM == b.sM && a.eH == b.eH && a.eM == b.eM && a.type == b.type &&
         std::strcmp(a.subj, b.subj) == 0 && std::strcmp(a.prof, b.prof) == 0;
}

// n 개 슬롯을 7개 요일에 고르게 나눠 파일로 만든다(요일당 ≤ 14). 반환 = 파일 길이.
// writeSlots 는 상한 초과 count 를 거부하므로 96개를 넘는 몫은 레코드를 직접 이어 붙인다.
size_t writeSpread(uint8_t n, uint8_t* buf, size_t cap) {
  static lc::SlotRec recs[LP_SLOT_WEEK_MAX + 1];
  for (uint8_t i = 0; i < n; ++i) {
    recs[i] = makeSlot(static_cast<uint8_t>(i % 7 + 1), static_cast<uint8_t>(6 + i / 7), 0);
  }
  const uint8_t head = n > LP_SLOT_WEEK_MAX ? LP_SLOT_WEEK_MAX : n;
  size_t len = ns::writeSlots(recs, head, buf, cap);
  for (uint8_t i = head; i < n; ++i) {
    buf[len] = LP_TYPE_SLOT_SET;
    const size_t bl = lc::encSlotBody(recs[i], buf + len + 2, cap - len - 2);
    buf[len + 1] = static_cast<uint8_t>(bl);
    len += 2 + bl;
  }
  return len;
}

// UTF-8 바이트 정확히 LP_SUBJ_MAX(32) — 한글 10자(30 B) + ASCII 2자.
constexpr char kLongSubj[] = "가나다라마바사아자차ab";
// UTF-8 바이트 정확히 LP_PROF_MAX(12) — 한글 4자.
constexpr char kLongProf[] = "홍길동님";
static_assert(sizeof(kLongSubj) - 1 == LP_SUBJ_MAX, "과목명 32 B");
static_assert(sizeof(kLongProf) - 1 == LP_PROF_MAX, "교수 12 B");

}  // namespace

void test_slots_roundtrip() {
  lc::SlotRec in[3] = {makeSlot(2, 12, 0, "자료구조", "김"), makeSlot(2, 13, 0, "자료구조", "김"),
                       makeSlot(3, 9, 0, "자료구조", "김")};
  uint8_t buf[ns::kSchedFileMax];
  const size_t len = ns::writeSlots(in, 3, buf, sizeof(buf));
  TEST_ASSERT_GREATER_THAN_UINT(0, len);
  lc::SlotRec out[LP_SLOT_WEEK_MAX];
  uint8_t count = 0;
  TEST_ASSERT_EQUAL(static_cast<int>(ParseResult::Ok),
                    static_cast<int>(ns::parseSlots(buf, static_cast<uint16_t>(len), out, count)));
  TEST_ASSERT_EQUAL_UINT8(3, count);
  for (int i = 0; i < 3; ++i) TEST_ASSERT_TRUE(sameSlot(in[i], out[i]));
}

void test_empty_body_ok_zero() {
  lc::SlotRec out[LP_SLOT_WEEK_MAX];
  uint8_t count = 9;
  const uint8_t dummy = 0;
  TEST_ASSERT_EQUAL(static_cast<int>(ParseResult::Ok),
                    static_cast<int>(ns::parseSlots(&dummy, 0, out, count)));
  TEST_ASSERT_EQUAL_UINT8(0, count);
}

void test_truncated_header_corrupt() {
  lc::SlotRec in[1] = {makeSlot(2, 12, 0)};
  uint8_t buf[ns::kSchedFileMax];
  size_t len = ns::writeSlots(in, 1, buf, sizeof(buf));
  buf[len++] = LP_TYPE_SLOT_SET;  // 헤더가 1 B 만 남은 꼬리
  lc::SlotRec out[LP_SLOT_WEEK_MAX];
  uint8_t count = 0;
  TEST_ASSERT_EQUAL(static_cast<int>(ParseResult::Corrupt),
                    static_cast<int>(ns::parseSlots(buf, static_cast<uint16_t>(len), out, count)));
}

void test_truncated_payload_corrupt() {
  lc::SlotRec in[2] = {makeSlot(2, 12, 0), makeSlot(3, 9, 0)};
  uint8_t buf[ns::kSchedFileMax];
  const size_t len = ns::writeSlots(in, 2, buf, sizeof(buf));
  lc::SlotRec out[LP_SLOT_WEEK_MAX];
  uint8_t count = 0;
  TEST_ASSERT_EQUAL(static_cast<int>(ParseResult::Corrupt),
                    static_cast<int>(ns::parseSlots(buf, static_cast<uint16_t>(len - 1), out, count)));
}

void test_wrong_rectype_corrupt() {
  lc::ResvRec in[1] = {makeResv(1)};
  uint8_t buf[ns::kResvFileMax];
  const size_t len = ns::writeResv(in, 1, buf, sizeof(buf));
  TEST_ASSERT_GREATER_THAN_UINT(0, len);
  lc::SlotRec out[LP_SLOT_WEEK_MAX];
  uint8_t count = 0;
  TEST_ASSERT_EQUAL(static_cast<int>(ParseResult::Corrupt),
                    static_cast<int>(ns::parseSlots(buf, static_cast<uint16_t>(len), out, count)));
}

void test_week_cap_97_over() {
  uint8_t buf[ns::kSchedFileMax + 64];
  const size_t len = writeSpread(LP_SLOT_WEEK_MAX + 1, buf, sizeof(buf));
  TEST_ASSERT_GREATER_THAN_UINT(0, len);
  lc::SlotRec out[LP_SLOT_WEEK_MAX + 1];
  uint8_t count = 0;
  TEST_ASSERT_EQUAL(static_cast<int>(ParseResult::OverCapacity),
                    static_cast<int>(ns::parseSlots(buf, static_cast<uint16_t>(len), out, count)));
}

void test_week_96_ok() {
  uint8_t buf[ns::kSchedFileMax + 64];
  const size_t len = writeSpread(LP_SLOT_WEEK_MAX, buf, sizeof(buf));
  TEST_ASSERT_GREATER_THAN_UINT(0, len);
  lc::SlotRec out[LP_SLOT_WEEK_MAX + 1];
  uint8_t count = 0;
  TEST_ASSERT_EQUAL(static_cast<int>(ParseResult::Ok),
                    static_cast<int>(ns::parseSlots(buf, static_cast<uint16_t>(len), out, count)));
  TEST_ASSERT_EQUAL_UINT8(LP_SLOT_WEEK_MAX, count);
}

// Review Focus 4 — 주간 합계는 상한 안이어도 한 요일 25개는 거부한다.
void test_day_cap_25_over() {
  lc::SlotRec in[LP_SLOT_DAY_MAX + 1];
  for (uint8_t i = 0; i < LP_SLOT_DAY_MAX + 1; ++i) {
    in[i] = makeSlot(2, static_cast<uint8_t>(i / 2 + 6), i % 2 ? 30 : 0);
  }
  uint8_t buf[ns::kSchedFileMax];
  const size_t len = ns::writeSlots(in, LP_SLOT_DAY_MAX + 1, buf, sizeof(buf));
  TEST_ASSERT_GREATER_THAN_UINT(0, len);
  lc::SlotRec out[LP_SLOT_WEEK_MAX];
  uint8_t count = 0;
  TEST_ASSERT_EQUAL(static_cast<int>(ParseResult::OverCapacity),
                    static_cast<int>(ns::parseSlots(buf, static_cast<uint16_t>(len), out, count)));
}

void test_resv_roundtrip() {
  lc::ResvRec in[2] = {makeResv(7), makeResv(300)};
  uint8_t buf[ns::kResvFileMax];
  const size_t len = ns::writeResv(in, 2, buf, sizeof(buf));
  TEST_ASSERT_GREATER_THAN_UINT(0, len);
  lc::ResvRec out[ns::kResvMax];
  uint8_t count = 0;
  TEST_ASSERT_EQUAL(static_cast<int>(ParseResult::Ok),
                    static_cast<int>(ns::parseResv(buf, static_cast<uint16_t>(len), out, count)));
  TEST_ASSERT_EQUAL_UINT8(2, count);
  for (int i = 0; i < 2; ++i) {
    TEST_ASSERT_EQUAL_UINT16(in[i].resvId, out[i].resvId);
    TEST_ASSERT_EQUAL_UINT8(in[i].y, out[i].y);
    TEST_ASSERT_EQUAL_UINT8(in[i].m, out[i].m);
    TEST_ASSERT_EQUAL_UINT8(in[i].d, out[i].d);
    TEST_ASSERT_EQUAL_UINT8(in[i].sH, out[i].sH);
    TEST_ASSERT_EQUAL_UINT8(in[i].eM, out[i].eM);
    TEST_ASSERT_EQUAL_STRING(in[i].subj, out[i].subj);
    TEST_ASSERT_EQUAL_STRING(in[i].prof, out[i].prof);
  }
}

void test_exam_roundtrip() {
  lc::ExamRec in[2] = {makeExam(1), makeExam(2)};
  uint8_t buf[ns::kExamFileMax];
  const size_t len = ns::writeExams(in, 2, buf, sizeof(buf));
  TEST_ASSERT_GREATER_THAN_UINT(0, len);
  lc::ExamRec out[ns::kExamMax];
  uint8_t count = 0;
  TEST_ASSERT_EQUAL(static_cast<int>(ParseResult::Ok),
                    static_cast<int>(ns::parseExams(buf, static_cast<uint16_t>(len), out, count)));
  TEST_ASSERT_EQUAL_UINT8(2, count);
  for (int i = 0; i < 2; ++i) {
    TEST_ASSERT_EQUAL_UINT16(in[i].examId, out[i].examId);
    TEST_ASSERT_EQUAL_UINT8(in[i].m1, out[i].m1);
    TEST_ASSERT_EQUAL_UINT8(in[i].d2, out[i].d2);
  }
}

void test_resv_25_over() {
  // writeResv 는 25개를 거부하므로, 24개 파일 뒤에 레코드 하나를 직접 이어 붙여 25개짜리 파일을 만든다.
  lc::ResvRec in[ns::kResvMax];
  for (uint8_t i = 0; i < ns::kResvMax; ++i) in[i] = makeResv(static_cast<uint16_t>(i + 1));
  uint8_t buf[ns::kResvFileMax + 64];
  size_t len = ns::writeResv(in, ns::kResvMax, buf, sizeof(buf));
  TEST_ASSERT_GREATER_THAN_UINT(0, len);
  const lc::ResvRec extra = makeResv(99);
  buf[len] = LP_TYPE_RESV_SET;
  const size_t bl = lc::encResvBody(extra, buf + len + 2, sizeof(buf) - len - 2);
  TEST_ASSERT_GREATER_THAN_UINT(0, bl);
  buf[len + 1] = static_cast<uint8_t>(bl);
  len += 2 + bl;
  lc::ResvRec out[ns::kResvMax + 1];
  uint8_t count = 0;
  TEST_ASSERT_EQUAL(static_cast<int>(ParseResult::OverCapacity),
                    static_cast<int>(ns::parseResv(buf, static_cast<uint16_t>(len), out, count)));
}

// #141 — 과목명·교수가 모두 상한(32·12 B)인 슬롯 96개가 kSchedFileMax 안에 들어간다.
void test_full_week_long_subjects_roundtrip() {
  static lc::SlotRec in[LP_SLOT_WEEK_MAX];
  for (uint8_t i = 0; i < LP_SLOT_WEEK_MAX; ++i) {
    in[i] =
        makeSlot(static_cast<uint8_t>(i % 7 + 1), static_cast<uint8_t>(6 + i / 7), 0, kLongSubj, kLongProf);
  }
  uint8_t buf[ns::kSchedFileMax];
  const size_t len = ns::writeSlots(in, LP_SLOT_WEEK_MAX, buf, sizeof(buf));
  TEST_ASSERT_GREATER_THAN_UINT(0, len);
  TEST_ASSERT_LESS_OR_EQUAL_UINT(ns::kSchedFileMax, len);
  static lc::SlotRec out[LP_SLOT_WEEK_MAX];
  uint8_t count = 0;
  TEST_ASSERT_EQUAL(static_cast<int>(ParseResult::Ok),
                    static_cast<int>(ns::parseSlots(buf, static_cast<uint16_t>(len), out, count)));
  TEST_ASSERT_EQUAL_UINT8(LP_SLOT_WEEK_MAX, count);
  for (uint8_t i = 0; i < LP_SLOT_WEEK_MAX; ++i) TEST_ASSERT_TRUE(sameSlot(in[i], out[i]));
}

void test_full_resv_long_subjects_roundtrip() {
  lc::ResvRec in[ns::kResvMax];
  for (uint8_t i = 0; i < ns::kResvMax; ++i) {
    in[i] = makeResv(static_cast<uint16_t>(i + 1));
    std::strncpy(in[i].subj, kLongSubj, LP_SUBJ_MAX);
    std::strncpy(in[i].prof, kLongProf, LP_PROF_MAX);
  }
  uint8_t buf[ns::kResvFileMax];
  const size_t len = ns::writeResv(in, ns::kResvMax, buf, sizeof(buf));
  TEST_ASSERT_GREATER_THAN_UINT(0, len);
  TEST_ASSERT_LESS_OR_EQUAL_UINT(ns::kResvFileMax, len);
  lc::ResvRec out[ns::kResvMax];
  uint8_t count = 0;
  TEST_ASSERT_EQUAL(static_cast<int>(ParseResult::Ok),
                    static_cast<int>(ns::parseResv(buf, static_cast<uint16_t>(len), out, count)));
  TEST_ASSERT_EQUAL_UINT8(ns::kResvMax, count);
  for (uint8_t i = 0; i < ns::kResvMax; ++i) {
    TEST_ASSERT_EQUAL_UINT16(in[i].resvId, out[i].resvId);
    TEST_ASSERT_EQUAL_STRING(kLongSubj, out[i].subj);
    TEST_ASSERT_EQUAL_STRING(kLongProf, out[i].prof);
  }
}

void test_write_cap_too_small_zero() {
  lc::SlotRec in[2] = {makeSlot(2, 12, 0), makeSlot(3, 9, 0)};
  uint8_t buf[ns::kSchedFileMax];
  const size_t full = ns::writeSlots(in, 2, buf, sizeof(buf));
  TEST_ASSERT_GREATER_THAN_UINT(0, full);
  TEST_ASSERT_EQUAL_UINT(0, ns::writeSlots(in, 2, buf, full - 1));
}

void test_slots_of_day_sorted() {
  lc::SlotRec week[3] = {makeSlot(3, 9, 0), makeSlot(2, 13, 0), makeSlot(2, 12, 0)};
  lc::SlotRec out[LP_SLOT_DAY_MAX];
  const uint8_t n = ns::slotsOfDay(week, 3, 2, out);
  TEST_ASSERT_EQUAL_UINT8(2, n);
  TEST_ASSERT_EQUAL_UINT8(12, out[0].sH);
  TEST_ASSERT_EQUAL_UINT8(13, out[1].sH);
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_slots_roundtrip);
  RUN_TEST(test_empty_body_ok_zero);
  RUN_TEST(test_truncated_header_corrupt);
  RUN_TEST(test_truncated_payload_corrupt);
  RUN_TEST(test_wrong_rectype_corrupt);
  RUN_TEST(test_week_cap_97_over);
  RUN_TEST(test_week_96_ok);
  RUN_TEST(test_day_cap_25_over);
  RUN_TEST(test_resv_roundtrip);
  RUN_TEST(test_exam_roundtrip);
  RUN_TEST(test_resv_25_over);
  RUN_TEST(test_full_week_long_subjects_roundtrip);
  RUN_TEST(test_full_resv_long_subjects_roundtrip);
  RUN_TEST(test_write_cap_too_small_zero);
  RUN_TEST(test_slots_of_day_sorted);
  return UNITY_END();
}
