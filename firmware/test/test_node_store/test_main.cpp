#include <unity.h>

#include <cstdint>
#include <cstring>
#include <memory>
#include <vector>

#include "fake_store.h"
#include "lora_codec.h"
#include "node_store.h"
#include "record_file.h"
#include "rtc_state.h"

using ns::Date;
using ns::NodeStore;
using ns::StoreStatus;

namespace {

std::unique_ptr<ns::FakeKv> kv;
std::unique_ptr<ns::FakeFile> fs;
std::unique_ptr<ns::RtcState> rtc;
std::unique_ptr<NodeStore> store;

const Date kToday{26, 10, 13};

lc::SlotRec makeSlot(uint8_t day, uint8_t sH, uint8_t sM, const char* subj = "과목") {
  lc::SlotRec r{};
  r.day = day;
  r.sH = sH;
  r.sM = sM;
  r.eH = sH;
  r.eM = static_cast<uint8_t>(sM + 50 > 59 ? 59 : sM + 50);
  r.type = LP_SLOTTYPE_CLASS;
  std::strncpy(r.subj, subj, LP_SUBJ_MAX);
  std::strncpy(r.prof, "교수", LP_PROF_MAX);
  return r;
}

lc::ResvRec makeResv(uint16_t id, uint8_t y, uint8_t m, uint8_t d) {
  lc::ResvRec r{};
  r.resvId = id;
  r.y = y;
  r.m = m;
  r.d = d;
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

uint8_t fileBuf[ns::kSchedFileMax];

// /schedule.bin 을 읽어 out 에 푼다. 반환 = 개수, 파일이 없으면 0, 읽기·파싱 실패면 255.
uint8_t readSlots(lc::SlotRec* out) {
  size_t len = 0;
  const ns::ReadResult rr = fs->read("/schedule.bin", fileBuf, sizeof(fileBuf), len);
  if (rr == ns::ReadResult::NotFound) return 0;
  if (rr != ns::ReadResult::Ok) return 255;
  uint8_t n = 0;
  if (ns::parseSlots(fileBuf, static_cast<uint16_t>(len), out, n) != ns::ParseResult::Ok) return 255;
  return n;
}

uint8_t readResv(lc::ResvRec* out) {
  size_t len = 0;
  const ns::ReadResult rr = fs->read("/resv.bin", fileBuf, sizeof(fileBuf), len);
  if (rr == ns::ReadResult::NotFound) return 0;
  if (rr != ns::ReadResult::Ok) return 255;
  uint8_t n = 0;
  if (ns::parseResv(fileBuf, static_cast<uint16_t>(len), out, n) != ns::ParseResult::Ok) return 255;
  return n;
}

uint8_t readExams(lc::ExamRec* out) {
  size_t len = 0;
  const ns::ReadResult rr = fs->read("/exam.bin", fileBuf, sizeof(fileBuf), len);
  if (rr == ns::ReadResult::NotFound) return 0;
  if (rr != ns::ReadResult::Ok) return 255;
  uint8_t n = 0;
  if (ns::parseExams(fileBuf, static_cast<uint16_t>(len), out, n) != ns::ParseResult::Ok) return 255;
  return n;
}

uint32_t kvVer(const char* key) {
  uint32_t v = 0xFFFFFFFFu;
  kv->get("ver", key, v);
  return v;
}

// 96개를 7개 요일에 고르게(요일당 ≤ 14) 채운다. 시각 = 6 + i/7 시 정각.
void fillWeek96(uint8_t ver) {
  for (uint8_t i = 0; i < LP_SLOT_WEEK_MAX; ++i) {
    const lc::SlotRec s = makeSlot(static_cast<uint8_t>(1 + i % 7), static_cast<uint8_t>(6 + i / 7), 0);
    TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(ver, s));
  }
}

lc::SlotRec gSlots[LP_SLOT_WEEK_MAX];
lc::ResvRec gResv[ns::kResvMax];
lc::ExamRec gExams[ns::kExamMax];
uint8_t body[ns::kSchedFileMax];

}  // namespace

void setUp() {
  kv.reset(new ns::FakeKv());
  fs.reset(new ns::FakeFile());
  rtc.reset(new ns::RtcState());
  ns::rtcClear(*rtc);
  rtc->slotsDay = 2;  // 화요일
  store.reset(new NodeStore(*kv, *fs, *rtc));
}

void tearDown() {
  store.reset();
}

void test_slot_set_writes_file_ver_and_today() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(5, makeSlot(2, 12, 0)));
  TEST_ASSERT_EQUAL_UINT8(1, readSlots(gSlots));
  TEST_ASSERT_EQUAL_UINT32(5, kvVer("schedVer"));
  TEST_ASSERT_EQUAL_UINT8(1, store->state().nSlots);
  TEST_ASSERT_EQUAL_UINT8(12, store->state().slots[0].sH);
  TEST_ASSERT_EQUAL_UINT8(5, store->state().schedVer);
}

void test_slot_set_other_day_not_in_rtc() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(5, makeSlot(3, 12, 0)));
  TEST_ASSERT_EQUAL_UINT8(1, readSlots(gSlots));
  TEST_ASSERT_EQUAL_UINT8(0, store->state().nSlots);
  TEST_ASSERT_EQUAL_UINT8(5, store->state().schedVer);
}

// Review Focus 3 — 같은 SLOT_SET 두 번이면 개수 그대로(같은 키는 교체).
void test_slot_set_idempotent() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(5, makeSlot(2, 12, 0)));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(6, makeSlot(2, 12, 0)));
  TEST_ASSERT_EQUAL_UINT8(1, readSlots(gSlots));
  TEST_ASSERT_EQUAL_UINT8(1, store->state().nSlots);
  TEST_ASSERT_EQUAL_UINT8(6, store->state().schedVer);
  TEST_ASSERT_EQUAL_UINT32(6, kvVer("schedVer"));
}

// 주간 표는 (day, sH, sM) 오름차순으로 유지된다.
void test_week_sorted_by_key() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(1, makeSlot(3, 9, 0)));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(2, makeSlot(2, 13, 0)));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(3, makeSlot(2, 9, 30)));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(4, makeSlot(2, 9, 0)));
  TEST_ASSERT_EQUAL_UINT8(4, readSlots(gSlots));
  TEST_ASSERT_EQUAL_UINT8(2, gSlots[0].day);
  TEST_ASSERT_EQUAL_UINT8(9, gSlots[0].sH);
  TEST_ASSERT_EQUAL_UINT8(0, gSlots[0].sM);
  TEST_ASSERT_EQUAL_UINT8(30, gSlots[1].sM);
  TEST_ASSERT_EQUAL_UINT8(13, gSlots[2].sH);
  TEST_ASSERT_EQUAL_UINT8(3, gSlots[3].day);
  TEST_ASSERT_EQUAL_UINT8(3, store->state().nSlots);
}

void test_week_cap_storefail() {
  fillWeek96(5);
  const uint8_t nToday = store->state().nSlots;
  TEST_ASSERT_EQUAL(StoreStatus::StoreFail, store->applySlotSet(6, makeSlot(2, 21, 30)));
  TEST_ASSERT_EQUAL_UINT8(96, readSlots(gSlots));
  TEST_ASSERT_EQUAL_UINT32(5, kvVer("schedVer"));
  TEST_ASSERT_EQUAL_UINT8(5, store->state().schedVer);
  TEST_ASSERT_EQUAL_UINT8(nToday, store->state().nSlots);
}

// Review Focus 4 — 주간 합계는 상한 안이어도 한 요일 25개면 StoreFail.
void test_day_cap_25_storefail() {
  for (uint8_t h = 0; h < LP_SLOT_DAY_MAX; ++h) {
    TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(5, makeSlot(2, h, 0)));
  }
  TEST_ASSERT_EQUAL(StoreStatus::StoreFail, store->applySlotSet(6, makeSlot(2, 23, 30)));
  TEST_ASSERT_EQUAL_UINT8(24, readSlots(gSlots));
  TEST_ASSERT_EQUAL_UINT32(5, kvVer("schedVer"));
  TEST_ASSERT_EQUAL_UINT8(5, store->state().schedVer);
  TEST_ASSERT_EQUAL_UINT8(24, store->state().nSlots);
}

// Review Focus 2 — 상한이 꽉 찬 상태에서 이미 있는 키를 다시 SET 하면 교체라 Ok.
void test_set_existing_key_when_full_is_ok() {
  fillWeek96(5);
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(6, makeSlot(2, 6, 0, "바뀜")));
  TEST_ASSERT_EQUAL_UINT8(96, readSlots(gSlots));
  bool found = false;
  for (uint8_t i = 0; i < 96; ++i) {
    if (gSlots[i].day == 2 && gSlots[i].sH == 6 && gSlots[i].sM == 0)
      found = std::strcmp(gSlots[i].subj, "바뀜") == 0;
  }
  TEST_ASSERT_TRUE(found);
  TEST_ASSERT_EQUAL_UINT8(6, store->state().schedVer);
  TEST_ASSERT_EQUAL_STRING("바뀜", store->state().slots[0].subj);
}

void test_slot_del_missing_ok_ver_bumped() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(3, makeSlot(2, 12, 0)));
  lc::SlotDel del{2, 9, 0};
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotDel(4, del));
  TEST_ASSERT_EQUAL_UINT8(1, readSlots(gSlots));
  TEST_ASSERT_EQUAL_UINT32(4, kvVer("schedVer"));
  TEST_ASSERT_EQUAL_UINT8(4, store->state().schedVer);
  TEST_ASSERT_EQUAL_UINT8(1, store->state().nSlots);
}

void test_slot_del_existing() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(3, makeSlot(2, 12, 0)));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(4, makeSlot(2, 14, 0)));
  lc::SlotDel del{2, 12, 0};
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotDel(5, del));
  TEST_ASSERT_EQUAL_UINT8(1, readSlots(gSlots));
  TEST_ASSERT_EQUAL_UINT8(14, gSlots[0].sH);
  TEST_ASSERT_EQUAL_UINT8(1, store->state().nSlots);
  TEST_ASSERT_EQUAL_UINT8(14, store->state().slots[0].sH);
}

void test_day_clear_only_that_day() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(1, makeSlot(2, 9, 0)));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(2, makeSlot(2, 13, 0)));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(3, makeSlot(3, 9, 0)));
  lc::DayClear dc{2};
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyDayClear(4, dc));
  TEST_ASSERT_EQUAL_UINT8(1, readSlots(gSlots));
  TEST_ASSERT_EQUAL_UINT8(3, gSlots[0].day);
  TEST_ASSERT_EQUAL_UINT8(0, store->state().nSlots);
  TEST_ASSERT_EQUAL_UINT8(4, store->state().schedVer);
  TEST_ASSERT_EQUAL_UINT32(4, kvVer("schedVer"));
}

// Review Focus 1 — 파일 쓰기가 실패하면 StoreFail, 파일·NVS·RTC 모두 그대로.
void test_file_write_fail_storefail_keeps_all() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(5, makeSlot(2, 12, 0)));
  fs->failWritesAfter = 0;
  TEST_ASSERT_EQUAL(StoreStatus::StoreFail, store->applySlotSet(6, makeSlot(2, 14, 0)));
  TEST_ASSERT_EQUAL_UINT8(1, readSlots(gSlots));
  TEST_ASSERT_EQUAL_UINT8(12, gSlots[0].sH);
  TEST_ASSERT_EQUAL_UINT32(5, kvVer("schedVer"));
  TEST_ASSERT_EQUAL_UINT8(5, store->state().schedVer);
  TEST_ASSERT_EQUAL_UINT8(1, store->state().nSlots);

  fs->failWritesAfter = 1;  // 다음 쓰기만 성공
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyResvSet(2, makeResv(1, 26, 10, 14), kToday, true));
  TEST_ASSERT_EQUAL(StoreStatus::StoreFail, store->applyResvSet(3, makeResv(2, 26, 10, 14), kToday, true));
  TEST_ASSERT_EQUAL_UINT8(1, store->state().nResv);
  TEST_ASSERT_EQUAL_UINT8(2, store->state().resvVer);
  TEST_ASSERT_EQUAL_UINT32(2, kvVer("resvVer"));
}

// 버전 쓰기 실패 — StoreFail. 파일은 새 내용, RTC 버전은 옛 값.
void test_ver_write_fail_storefail() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(5, makeSlot(2, 12, 0)));
  kv->failSetsAfter = 0;
  TEST_ASSERT_EQUAL(StoreStatus::StoreFail, store->applySlotSet(6, makeSlot(2, 14, 0)));
  TEST_ASSERT_EQUAL_UINT8(2, readSlots(gSlots));
  TEST_ASSERT_EQUAL_UINT32(5, kvVer("schedVer"));
  TEST_ASSERT_EQUAL_UINT8(5, store->state().schedVer);
}

// 실행 중 /schedule.bin 이 손상되면 버전 0 → 서버가 STATUS 버전 비교로 FILE 재동기를 건다(v2 §5.1).
void test_corrupt_week_file_resets_ver0() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(5, makeSlot(2, 12, 0)));
  TEST_ASSERT_EQUAL_UINT8(1, store->state().nSlots);
  const lc::SlotRec two[2] = {makeSlot(2, 9, 0), makeSlot(2, 10, 0)};
  const size_t full = ns::writeSlots(two, 2, body, sizeof(body));
  TEST_ASSERT_TRUE(full > 0);
  fs->putRaw("/schedule.bin", std::vector<uint8_t>(body, body + full - 1));  // 레코드 중간에서 잘림
  TEST_ASSERT_EQUAL(StoreStatus::StoreFail, store->applySlotSet(6, makeSlot(2, 14, 0)));
  TEST_ASSERT_EQUAL_UINT32(0, kvVer("schedVer"));
  TEST_ASSERT_EQUAL_UINT8(0, store->state().schedVer);
  TEST_ASSERT_EQUAL_UINT8(0, store->state().nSlots);
  TEST_ASSERT_EQUAL_UINT8(0, store->state().slots[0].sH);
  TEST_ASSERT_EQUAL_UINT8(2, store->state().slotsDay);  // 요일은 유지
  size_t len = 0;                                       // 파일은 다시 쓰지도 지우지도 않는다
  TEST_ASSERT_EQUAL(ns::ReadResult::Ok, fs->read("/schedule.bin", fileBuf, sizeof(fileBuf), len));
  TEST_ASSERT_EQUAL(full - 1, len);

  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->replaceKind(LP_FILEKIND_SCHEDULE, 7, body,
                                                        static_cast<uint16_t>(full), kToday, true));
  TEST_ASSERT_EQUAL_UINT8(7, store->state().schedVer);
  TEST_ASSERT_EQUAL_UINT32(7, kvVer("schedVer"));
  TEST_ASSERT_EQUAL_UINT8(2, readSlots(gSlots));
  TEST_ASSERT_EQUAL_UINT8(2, store->state().nSlots);
  TEST_ASSERT_EQUAL_UINT8(9, store->state().slots[0].sH);
}

// 읽기 오류(일시적일 수 있음)는 StoreFail 만 — 버전·RTC 는 그대로.
void test_week_read_fail_keeps_ver() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(5, makeSlot(2, 12, 0)));
  fs->putRaw("/schedule.bin", std::vector<uint8_t>(ns::kSchedFileMax + 1, 0));  // cap 초과 → read Fail
  TEST_ASSERT_EQUAL(StoreStatus::StoreFail, store->applySlotSet(6, makeSlot(2, 14, 0)));
  TEST_ASSERT_EQUAL_UINT32(5, kvVer("schedVer"));
  TEST_ASSERT_EQUAL_UINT8(5, store->state().schedVer);
  TEST_ASSERT_EQUAL_UINT8(1, store->state().nSlots);
}

void test_replace_kind_sets_ver_even_if_lower() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(9, makeSlot(2, 12, 0)));
  const lc::SlotRec in[3] = {makeSlot(3, 9, 0), makeSlot(2, 15, 0), makeSlot(2, 10, 0)};
  const size_t len = ns::writeSlots(in, 3, body, sizeof(body));
  TEST_ASSERT_TRUE(len > 0);
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->replaceKind(LP_FILEKIND_SCHEDULE, 3, body,
                                                        static_cast<uint16_t>(len), kToday, true));
  TEST_ASSERT_EQUAL_UINT8(3, store->state().schedVer);
  TEST_ASSERT_EQUAL_UINT32(3, kvVer("schedVer"));
  TEST_ASSERT_EQUAL_UINT8(3, readSlots(gSlots));
  TEST_ASSERT_EQUAL_UINT8(2, gSlots[0].day);  // 오름차순으로 다시 씀
  TEST_ASSERT_EQUAL_UINT8(10, gSlots[0].sH);
  TEST_ASSERT_EQUAL_UINT8(2, store->state().nSlots);
  TEST_ASSERT_EQUAL_UINT8(10, store->state().slots[0].sH);
}

void test_replace_corrupt_body_badpayload() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(9, makeSlot(2, 12, 0)));
  const lc::SlotRec in[2] = {makeSlot(2, 9, 0), makeSlot(2, 10, 0)};
  const size_t len = ns::writeSlots(in, 2, body, sizeof(body));
  TEST_ASSERT_EQUAL(
      StoreStatus::BadPayload,
      store->replaceKind(LP_FILEKIND_SCHEDULE, 3, body, static_cast<uint16_t>(len - 1), kToday, true));
  TEST_ASSERT_EQUAL_UINT8(1, readSlots(gSlots));
  TEST_ASSERT_EQUAL_UINT8(12, gSlots[0].sH);
  TEST_ASSERT_EQUAL_UINT8(9, store->state().schedVer);
  TEST_ASSERT_EQUAL_UINT32(9, kvVer("schedVer"));
  TEST_ASSERT_EQUAL_UINT8(1, store->state().nSlots);
}

void test_replace_over_capacity_storefail_keeps_old() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(9, makeSlot(2, 12, 0)));
  lc::SlotRec in[LP_SLOT_DAY_MAX + 1];
  for (uint8_t h = 0; h < LP_SLOT_DAY_MAX; ++h) in[h] = makeSlot(2, h, 0);
  in[LP_SLOT_DAY_MAX] = makeSlot(2, 23, 30);
  const size_t len = ns::writeSlots(in, LP_SLOT_DAY_MAX + 1, body, sizeof(body));
  TEST_ASSERT_TRUE(len > 0);
  TEST_ASSERT_EQUAL(StoreStatus::StoreFail, store->replaceKind(LP_FILEKIND_SCHEDULE, 3, body,
                                                               static_cast<uint16_t>(len), kToday, true));
  TEST_ASSERT_EQUAL_UINT8(1, readSlots(gSlots));
  TEST_ASSERT_EQUAL_UINT8(9, store->state().schedVer);
  TEST_ASSERT_EQUAL_UINT32(9, kvVer("schedVer"));
  TEST_ASSERT_EQUAL_UINT8(1, store->state().nSlots);
}

// 빈 표도 (빈) 파일을 쓰고 버전을 기록한다.
void test_replace_empty_writes_empty_file() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyExamSet(4, makeExam(1)));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->replaceKind(LP_FILEKIND_EXAM, 5, nullptr, 0, kToday, true));
  size_t len = 99;
  TEST_ASSERT_EQUAL(ns::ReadResult::Ok, fs->read("/exam.bin", fileBuf, sizeof(fileBuf), len));
  TEST_ASSERT_EQUAL(0, len);
  TEST_ASSERT_EQUAL_UINT8(0, store->state().nExam);
  TEST_ASSERT_EQUAL_UINT8(5, store->state().examVer);
  TEST_ASSERT_EQUAL_UINT32(5, kvVer("examVer"));
}

// RESV 통째 교체에서도 지난 예약은 정리되고, 버전은 그 명령의 newVer 하나.
void test_replace_resv_purges_past() {
  const lc::ResvRec in[3] = {makeResv(1, 26, 10, 12), makeResv(2, 26, 10, 13), makeResv(3, 26, 10, 14)};
  const size_t len = ns::writeResv(in, 3, body, sizeof(body));
  TEST_ASSERT_EQUAL(StoreStatus::Ok,
                    store->replaceKind(LP_FILEKIND_RESV, 8, body, static_cast<uint16_t>(len), kToday, true));
  TEST_ASSERT_EQUAL_UINT8(2, store->state().nResv);
  TEST_ASSERT_EQUAL_UINT8(2, readResv(gResv));
  TEST_ASSERT_EQUAL_UINT8(8, store->state().resvVer);
  TEST_ASSERT_EQUAL_UINT32(8, kvVer("resvVer"));
}

// 예약 24개 중 3개가 어제 — 정리가 상한 검사보다 먼저라 새 예약이 들어간다.
void test_resv_purge_before_cap() {
  for (uint16_t i = 0; i < ns::kResvMax; ++i) {
    const lc::ResvRec r = i < 3 ? makeResv(i, 26, 10, 12) : makeResv(i, 26, 10, 14);
    TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyResvSet(1, r, kToday, false));
  }
  TEST_ASSERT_EQUAL_UINT8(24, store->state().nResv);
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyResvSet(2, makeResv(100, 26, 10, 15), kToday, true));
  TEST_ASSERT_EQUAL_UINT8(22, store->state().nResv);
  TEST_ASSERT_EQUAL_UINT8(22, readResv(gResv));
  TEST_ASSERT_EQUAL_UINT8(2, store->state().resvVer);
}

void test_resv_purge_skipped_when_clock_invalid() {
  for (uint16_t i = 0; i < ns::kResvMax; ++i) {
    const lc::ResvRec r = i < 3 ? makeResv(i, 26, 10, 12) : makeResv(i, 26, 10, 14);
    TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyResvSet(1, r, kToday, false));
  }
  TEST_ASSERT_EQUAL(StoreStatus::StoreFail, store->applyResvSet(2, makeResv(100, 26, 10, 15), kToday, false));
  TEST_ASSERT_EQUAL_UINT8(24, store->state().nResv);
  TEST_ASSERT_EQUAL_UINT8(24, readResv(gResv));
  TEST_ASSERT_EQUAL_UINT8(1, store->state().resvVer);
  TEST_ASSERT_EQUAL_UINT16(0, store->state().resv[0].resvId);  // 어제 예약 남음
}

void test_resv_set_replace_and_del() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyResvSet(1, makeResv(7, 26, 10, 14), kToday, true));
  lc::ResvRec r = makeResv(7, 26, 10, 15);
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyResvSet(2, r, kToday, true));
  TEST_ASSERT_EQUAL_UINT8(1, store->state().nResv);
  TEST_ASSERT_EQUAL_UINT8(15, store->state().resv[0].d);
  lc::ResvDel missing{99};
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyResvDel(3, missing));
  TEST_ASSERT_EQUAL_UINT8(1, store->state().nResv);
  TEST_ASSERT_EQUAL_UINT8(3, store->state().resvVer);
  lc::ResvDel del{7};
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyResvDel(4, del));
  TEST_ASSERT_EQUAL_UINT8(0, store->state().nResv);
  TEST_ASSERT_EQUAL_UINT8(0, readResv(gResv));
  TEST_ASSERT_EQUAL_UINT32(4, kvVer("resvVer"));
}

void test_purge_past_keeps_today() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyResvSet(1, makeResv(1, 26, 10, 12), kToday, false));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyResvSet(1, makeResv(2, 26, 10, 13), kToday, false));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyResvSet(1, makeResv(3, 25, 12, 31), kToday, false));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->purgePast(kToday, true));
  TEST_ASSERT_EQUAL_UINT8(1, store->state().nResv);
  TEST_ASSERT_EQUAL_UINT16(2, store->state().resv[0].resvId);
}

void test_purge_past_clock_invalid_noop() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyResvSet(1, makeResv(1, 26, 10, 12), kToday, false));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->purgePast(kToday, false));
  TEST_ASSERT_EQUAL_UINT8(1, store->state().nResv);
  TEST_ASSERT_EQUAL_UINT8(1, readResv(gResv));
}

void test_purge_past_keeps_version() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyResvSet(7, makeResv(1, 26, 10, 11), kToday, false));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyResvSet(7, makeResv(2, 26, 10, 12), kToday, false));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyResvSet(7, makeResv(3, 26, 10, 13), kToday, false));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyResvSet(7, makeResv(4, 26, 10, 14), kToday, false));
  TEST_ASSERT_EQUAL_UINT8(4, readResv(gResv));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->purgePast(kToday, true));
  TEST_ASSERT_EQUAL_UINT8(7, store->state().resvVer);
  TEST_ASSERT_EQUAL_UINT32(7, kvVer("resvVer"));
  TEST_ASSERT_EQUAL_UINT8(2, readResv(gResv));
  TEST_ASSERT_EQUAL_UINT8(2, store->state().nResv);
}

void test_exam_set_del() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyExamSet(1, makeExam(10)));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyExamSet(2, makeExam(11)));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyExamSet(3, makeExam(10)));  // 같은 키 교체
  TEST_ASSERT_EQUAL_UINT8(2, store->state().nExam);
  lc::ExamDel del{10};
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyExamDel(4, del));
  TEST_ASSERT_EQUAL_UINT8(1, store->state().nExam);
  TEST_ASSERT_EQUAL_UINT16(11, store->state().exams[0].examId);
  TEST_ASSERT_EQUAL_UINT8(1, readExams(gExams));
  TEST_ASSERT_EQUAL_UINT8(4, store->state().examVer);
  TEST_ASSERT_EQUAL_UINT32(4, kvVer("examVer"));
  lc::ExamDel missing{99};
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyExamDel(5, missing));
  TEST_ASSERT_EQUAL_UINT8(5, store->state().examVer);
}

void test_exam_cap_storefail() {
  for (uint16_t i = 0; i < ns::kExamMax; ++i)
    TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyExamSet(1, makeExam(i)));
  TEST_ASSERT_EQUAL(StoreStatus::StoreFail, store->applyExamSet(2, makeExam(100)));
  TEST_ASSERT_EQUAL_UINT8(8, store->state().nExam);
  TEST_ASSERT_EQUAL_UINT8(1, store->state().examVer);
}

// ---- Task 5: 부팅 적재·요일 전환·정체성·TXN·파라미터·초기화 ----

// 화요일(2) 12:00 · 수요일(3) 9:00 슬롯, 예약 1, 시험 1, 정체성·TXN 을 넣어 둔다.
void seedStore() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(5, makeSlot(2, 12, 0)));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(5, makeSlot(3, 9, 0)));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyResvSet(3, makeResv(7, 26, 10, 14), kToday, true));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyExamSet(4, makeExam(11)));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->setIdentity(ns::Identity{2, 305, 7}, 6));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->setLastTxn(9));
}

void test_load_uses_valid_rtc() {
  seedStore();
  ns::rtcSeal(*rtc);
  fs->reads = 0;
  TEST_ASSERT_EQUAL(ns::LoadSource::RtcCache, store->load(2));
  TEST_ASSERT_EQUAL(0, fs->reads);
  TEST_ASSERT_EQUAL_UINT8(1, store->state().nSlots);
  TEST_ASSERT_EQUAL_UINT8(12, store->state().slots[0].sH);
}

void test_load_rebuilds_when_invalid() {
  seedStore();
  ns::rtcClear(*rtc);
  TEST_ASSERT_EQUAL(ns::LoadSource::Rebuilt, store->load(2));
  const ns::RtcState& s = store->state();
  TEST_ASSERT_TRUE(ns::rtcValid(s));
  TEST_ASSERT_EQUAL_UINT8(2, s.slotsDay);
  TEST_ASSERT_EQUAL_UINT8(1, s.nSlots);
  TEST_ASSERT_EQUAL_UINT8(12, s.slots[0].sH);
  TEST_ASSERT_EQUAL_UINT8(1, s.nResv);
  TEST_ASSERT_EQUAL_UINT16(7, s.resv[0].resvId);
  TEST_ASSERT_EQUAL_UINT8(1, s.nExam);
  TEST_ASSERT_EQUAL_UINT16(11, s.exams[0].examId);
  TEST_ASSERT_EQUAL_UINT8(5, s.schedVer);
  TEST_ASSERT_EQUAL_UINT8(3, s.resvVer);
  TEST_ASSERT_EQUAL_UINT8(4, s.examVer);
  TEST_ASSERT_EQUAL_UINT8(2, s.bld);
  TEST_ASSERT_EQUAL_UINT16(305, s.room);
  TEST_ASSERT_EQUAL_UINT8(7, s.unit);
  TEST_ASSERT_EQUAL_UINT8(6, s.identVer);
  TEST_ASSERT_EQUAL_UINT8(1, s.provisioned);
  TEST_ASSERT_EQUAL_UINT8(9, s.lastTxn);
}

void test_load_corrupt_schedule_empties_ver0() {
  seedStore();
  const lc::SlotRec two[2] = {makeSlot(2, 9, 0), makeSlot(2, 10, 0)};
  const size_t full = ns::writeSlots(two, 2, body, sizeof(body));
  fs->putRaw("/schedule.bin", std::vector<uint8_t>(body, body + full - 1));
  ns::rtcClear(*rtc);
  TEST_ASSERT_EQUAL(ns::LoadSource::Rebuilt, store->load(2));
  TEST_ASSERT_EQUAL_UINT8(0, store->state().nSlots);
  TEST_ASSERT_EQUAL_UINT8(0, store->state().schedVer);
  TEST_ASSERT_EQUAL_UINT32(0, kvVer("schedVer"));
  TEST_ASSERT_EQUAL_UINT8(1, store->state().nResv);  // 예약은 정상
  TEST_ASSERT_EQUAL_UINT8(3, store->state().resvVer);
  TEST_ASSERT_TRUE(ns::rtcValid(store->state()));
}

// 읽기 실패(cap 초과)와 상한 초과도 손상과 같게 그 kind 만 비우고 버전 0.
void test_load_read_fail_and_over_capacity_empty_ver0() {
  seedStore();
  fs->putRaw("/resv.bin", std::vector<uint8_t>(ns::kSchedFileMax + 1, 0));  // read Fail
  // 시험 레코드 한 개를 상한+1 번 이어 붙인다 → parse OverCapacity (writeExams 는 상한 초과 count 면 0)
  const lc::ExamRec one = makeExam(1);
  const size_t oneLen = ns::writeExams(&one, 1, body, sizeof(body));
  TEST_ASSERT_TRUE(oneLen > 0);
  std::vector<uint8_t> raw;
  for (int i = 0; i <= ns::kExamMax; ++i) raw.insert(raw.end(), body, body + oneLen);
  fs->putRaw("/exam.bin", raw);
  ns::rtcClear(*rtc);
  TEST_ASSERT_EQUAL(ns::LoadSource::Rebuilt, store->load(2));
  TEST_ASSERT_EQUAL_UINT8(0, store->state().nResv);
  TEST_ASSERT_EQUAL_UINT8(0, store->state().resvVer);
  TEST_ASSERT_EQUAL_UINT32(0, kvVer("resvVer"));
  TEST_ASSERT_EQUAL_UINT8(0, store->state().nExam);
  TEST_ASSERT_EQUAL_UINT8(0, store->state().examVer);
  TEST_ASSERT_EQUAL_UINT32(0, kvVer("examVer"));
  TEST_ASSERT_EQUAL_UINT8(1, store->state().nSlots);  // 시간표는 정상
  TEST_ASSERT_EQUAL_UINT8(5, store->state().schedVer);
}

void test_load_weekday_zero_no_slots() {
  seedStore();
  ns::rtcClear(*rtc);
  TEST_ASSERT_EQUAL(ns::LoadSource::Rebuilt, store->load(0));
  TEST_ASSERT_EQUAL_UINT8(0, store->state().slotsDay);
  TEST_ASSERT_EQUAL_UINT8(0, store->state().nSlots);
  TEST_ASSERT_EQUAL_UINT8(5, store->state().schedVer);  // 파일은 정상이라 버전 그대로
  TEST_ASSERT_EQUAL_UINT8(1, store->state().nResv);
}

// 쓰기는 빈 표도 파일로 남기므로, 버전이 있는데 파일이 없으면 데이터를 잃은 것 — 버전 0(cw 지시, #119).
void test_load_missing_file_with_ver_resets_ver0() {
  TEST_ASSERT_TRUE(kv->set("ver", "schedVer", 5));
  TEST_ASSERT_TRUE(kv->set("ver", "examVer", 2));
  ns::rtcClear(*rtc);
  TEST_ASSERT_EQUAL(ns::LoadSource::Rebuilt, store->load(2));
  TEST_ASSERT_EQUAL_UINT8(0, store->state().nSlots);
  TEST_ASSERT_EQUAL_UINT8(0, store->state().schedVer);
  TEST_ASSERT_EQUAL_UINT32(0, kvVer("schedVer"));
  TEST_ASSERT_EQUAL_UINT8(0, store->state().examVer);
  TEST_ASSERT_EQUAL_UINT32(0, kvVer("examVer"));
}

// 같은 조건에서 버전 0 이면 처음 켠 노드 — 빈 표, NVS 는 건드리지 않는다.
void test_load_missing_file_ver0_is_first_boot() {
  ns::rtcClear(*rtc);
  TEST_ASSERT_EQUAL(ns::LoadSource::Rebuilt, store->load(2));
  TEST_ASSERT_EQUAL_UINT8(0, store->state().nSlots);
  TEST_ASSERT_EQUAL_UINT8(0, store->state().schedVer);
  TEST_ASSERT_EQUAL_UINT8(0, store->state().provisioned);
  uint32_t v = 0;
  TEST_ASSERT_FALSE(kv->get("ver", "schedVer", v));
  TEST_ASSERT_FALSE(kv->get("ver", "resvVer", v));
  TEST_ASSERT_FALSE(kv->get("ver", "examVer", v));
  TEST_ASSERT_TRUE(ns::rtcValid(store->state()));
}

void test_load_valid_rtc_other_day_refreshes() {
  seedStore();
  ns::rtcSeal(*rtc);
  TEST_ASSERT_EQUAL(ns::LoadSource::RtcCache, store->load(3));
  TEST_ASSERT_EQUAL_UINT8(3, store->state().slotsDay);
  TEST_ASSERT_EQUAL_UINT8(1, store->state().nSlots);
  TEST_ASSERT_EQUAL_UINT8(9, store->state().slots[0].sH);
  TEST_ASSERT_EQUAL_UINT8(5, store->state().schedVer);
}

void test_refresh_day_switches() {
  seedStore();
  TEST_ASSERT_EQUAL_UINT8(12, store->state().slots[0].sH);
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->refreshDay(3));
  TEST_ASSERT_EQUAL_UINT8(3, store->state().slotsDay);
  TEST_ASSERT_EQUAL_UINT8(1, store->state().nSlots);
  TEST_ASSERT_EQUAL_UINT8(9, store->state().slots[0].sH);
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->refreshDay(4));  // 슬롯 없는 요일
  TEST_ASSERT_EQUAL_UINT8(4, store->state().slotsDay);
  TEST_ASSERT_EQUAL_UINT8(0, store->state().nSlots);
  TEST_ASSERT_EQUAL_UINT8(0, store->state().slots[0].sH);
}

// 실행 중 /schedule.bin 손상 — Task 4 loadWeek 와 같은 규칙(버전 0·슬롯 비움·StoreFail).
void test_refresh_day_corrupt_resets_ver0() {
  seedStore();
  const lc::SlotRec two[2] = {makeSlot(2, 9, 0), makeSlot(2, 10, 0)};
  const size_t full = ns::writeSlots(two, 2, body, sizeof(body));
  fs->putRaw("/schedule.bin", std::vector<uint8_t>(body, body + full - 1));
  TEST_ASSERT_EQUAL(StoreStatus::StoreFail, store->refreshDay(3));
  TEST_ASSERT_EQUAL_UINT8(0, store->state().schedVer);
  TEST_ASSERT_EQUAL_UINT32(0, kvVer("schedVer"));
  TEST_ASSERT_EQUAL_UINT8(0, store->state().nSlots);
  TEST_ASSERT_EQUAL_UINT8(3, store->state().slotsDay);
}

// 일시적 읽기 오류 — 버전은 그대로, slotsDay 0 이라 다음 load(weekday) 가 다시 시도한다.
void test_refresh_day_read_fail_retries_on_load() {
  seedStore();
  const lc::SlotRec wed = makeSlot(3, 9, 0);
  const size_t wedLen = ns::writeSlots(&wed, 1, body, sizeof(body));
  TEST_ASSERT_TRUE(wedLen > 0);
  const std::vector<uint8_t> good(body, body + wedLen);
  ns::rtcSeal(*rtc);  // 화요일(slotsDay 2), schedVer 5
  fs->putRaw("/schedule.bin", std::vector<uint8_t>(ns::kSchedFileMax + 1, 0));  // read Fail
  TEST_ASSERT_EQUAL(StoreStatus::StoreFail, store->refreshDay(3));
  TEST_ASSERT_EQUAL_UINT8(0, store->state().slotsDay);
  TEST_ASSERT_EQUAL_UINT8(0, store->state().nSlots);
  TEST_ASSERT_EQUAL_UINT8(0, store->state().slots[0].sH);
  TEST_ASSERT_EQUAL_UINT32(5, kvVer("schedVer"));
  TEST_ASSERT_EQUAL_UINT8(5, store->state().schedVer);

  fs->putRaw("/schedule.bin", good);  // 복구
  ns::rtcSeal(*rtc);
  TEST_ASSERT_EQUAL(ns::LoadSource::RtcCache, store->load(3));
  TEST_ASSERT_EQUAL_UINT8(3, store->state().slotsDay);
  TEST_ASSERT_EQUAL_UINT8(1, store->state().nSlots);
  TEST_ASSERT_EQUAL_UINT8(3, store->state().slots[0].day);
  TEST_ASSERT_EQUAL_UINT8(5, store->state().schedVer);
}

// slotsDay 0 상태에서 쓰기가 와도 파일·버전은 정상이고 RTC 슬롯 캐시만 빈 채로 둔다.
void test_write_with_slots_day_zero_keeps_cache_empty() {
  seedStore();
  fs->putRaw("/schedule.bin", std::vector<uint8_t>(ns::kSchedFileMax + 1, 0));  // read Fail
  TEST_ASSERT_EQUAL(StoreStatus::StoreFail, store->refreshDay(3));
  const lc::SlotRec wed = makeSlot(3, 9, 0);
  const size_t wedLen = ns::writeSlots(&wed, 1, body, sizeof(body));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->replaceKind(LP_FILEKIND_SCHEDULE, 6, body,
                                                        static_cast<uint16_t>(wedLen), kToday, true));
  TEST_ASSERT_EQUAL_UINT8(0, store->state().slotsDay);
  TEST_ASSERT_EQUAL_UINT8(0, store->state().nSlots);
  TEST_ASSERT_EQUAL_UINT8(6, store->state().schedVer);
  TEST_ASSERT_EQUAL_UINT32(6, kvVer("schedVer"));
  TEST_ASSERT_EQUAL_UINT8(1, readSlots(gSlots));
}

void test_identity_persists() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->setIdentity(ns::Identity{4, 1201, 2}, 8));
  uint32_t v = 0;
  TEST_ASSERT_TRUE(kv->get("cfg", "bld", v));
  TEST_ASSERT_EQUAL_UINT32(4, v);
  TEST_ASSERT_TRUE(kv->get("cfg", "room", v));
  TEST_ASSERT_EQUAL_UINT32(1201, v);
  TEST_ASSERT_TRUE(kv->get("cfg", "unit", v));
  TEST_ASSERT_EQUAL_UINT32(2, v);
  TEST_ASSERT_TRUE(kv->get("cfg", "identVer", v));
  TEST_ASSERT_EQUAL_UINT32(8, v);
  TEST_ASSERT_TRUE(kv->get("cfg", "provisioned", v));
  TEST_ASSERT_EQUAL_UINT32(1, v);
  TEST_ASSERT_EQUAL_UINT8(4, store->state().bld);
  TEST_ASSERT_EQUAL_UINT16(1201, store->state().room);
  TEST_ASSERT_EQUAL_UINT8(2, store->state().unit);
  TEST_ASSERT_EQUAL_UINT8(8, store->state().identVer);
  TEST_ASSERT_EQUAL_UINT8(1, store->state().provisioned);
}

// 저장 실패면 StoreFail, RTC 는 그대로.
void test_identity_and_txn_store_fail_keep_rtc() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->setIdentity(ns::Identity{4, 1201, 2}, 8));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->setLastTxn(3));
  kv->failSetsAfter = 0;
  TEST_ASSERT_EQUAL(StoreStatus::StoreFail, store->setIdentity(ns::Identity{9, 999, 9}, 9));
  TEST_ASSERT_EQUAL(StoreStatus::StoreFail, store->setLastTxn(4));
  TEST_ASSERT_EQUAL_UINT8(4, store->state().bld);
  TEST_ASSERT_EQUAL_UINT16(1201, store->state().room);
  TEST_ASSERT_EQUAL_UINT8(8, store->state().identVer);
  TEST_ASSERT_EQUAL_UINT8(3, store->state().lastTxn);
}

void test_last_txn_persists() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->setLastTxn(42));
  TEST_ASSERT_EQUAL_UINT32(42, kvVer("lastTxn"));
  TEST_ASSERT_EQUAL_UINT8(42, store->state().lastTxn);
}

void test_set_param_known_and_unknown() {
  uint32_t out = 0;
  TEST_ASSERT_FALSE(store->param(1, out));  // 아직 안 씀
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->setParam(1, 7));
  TEST_ASSERT_TRUE(store->param(1, out));
  TEST_ASSERT_EQUAL_UINT32(7, out);
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->setParam(2, 600000));
  TEST_ASSERT_TRUE(store->param(2, out));
  TEST_ASSERT_EQUAL_UINT32(600000, out);
  TEST_ASSERT_TRUE(kv->get("cfg", "statusHourUtc", out));
  TEST_ASSERT_EQUAL_UINT32(7, out);
  TEST_ASSERT_TRUE(kv->get("cfg", "sessionWindowMs", out));
  TEST_ASSERT_EQUAL_UINT32(600000, out);
  TEST_ASSERT_EQUAL(StoreStatus::Unsupported, store->setParam(9, 1));
  TEST_ASSERT_FALSE(store->param(9, out));
  kv->failSetsAfter = 0;
  TEST_ASSERT_EQUAL(StoreStatus::StoreFail, store->setParam(1, 8));
}

void test_factory_reset_clears_all() {
  seedStore();
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->setParam(1, 7));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->factoryReset());
  uint32_t v = 0;
  TEST_ASSERT_FALSE(kv->get("cfg", "bld", v));
  TEST_ASSERT_FALSE(kv->get("cfg", "provisioned", v));
  TEST_ASSERT_FALSE(kv->get("ver", "schedVer", v));
  TEST_ASSERT_FALSE(kv->get("ver", "lastTxn", v));
  TEST_ASSERT_FALSE(store->param(1, v));
  size_t len = 0;
  TEST_ASSERT_EQUAL(ns::ReadResult::NotFound, fs->read("/schedule.bin", fileBuf, sizeof(fileBuf), len));
  TEST_ASSERT_EQUAL(ns::ReadResult::NotFound, fs->read("/resv.bin", fileBuf, sizeof(fileBuf), len));
  TEST_ASSERT_EQUAL(ns::ReadResult::NotFound, fs->read("/exam.bin", fileBuf, sizeof(fileBuf), len));
  TEST_ASSERT_EQUAL_UINT8(0, store->state().provisioned);
  TEST_ASSERT_EQUAL_UINT8(0, store->state().nSlots);
  TEST_ASSERT_EQUAL_UINT8(0, store->state().nResv);
  TEST_ASSERT_FALSE(ns::rtcValid(store->state()));
  // 초기화 뒤 부팅은 처음 켠 노드와 같다.
  TEST_ASSERT_EQUAL(ns::LoadSource::Rebuilt, store->load(2));
  TEST_ASSERT_EQUAL_UINT8(0, store->state().provisioned);
  TEST_ASSERT_EQUAL_UINT8(0, store->state().schedVer);
}

// 임의 적용 10회 뒤: write-through 로 쌓인 RTC 와, RTC 를 비우고 NVS·파일에서 다시 적재한 RTC 가
// seal 뒤 바이트까지 같아야 한다(패딩 포함 CRC).
void test_write_through_matches_rebuild() {
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->setIdentity(ns::Identity{1, 204, 3}, 2));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(1, makeSlot(2, 13, 0)));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(2, makeSlot(2, 9, 30, "자료구조")));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotSet(3, makeSlot(4, 10, 0)));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyResvSet(1, makeResv(1, 26, 10, 14), kToday, true));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyResvSet(2, makeResv(2, 26, 10, 15), kToday, true));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyExamSet(1, makeExam(5)));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applySlotDel(4, lc::SlotDel{2, 13, 0}));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->applyResvDel(3, lc::ResvDel{1}));
  TEST_ASSERT_EQUAL(StoreStatus::Ok, store->setLastTxn(17));
  ns::RtcState want;
  std::memcpy(&want, rtc.get(), sizeof(want));
  ns::rtcSeal(want);
  ns::rtcClear(*rtc);
  TEST_ASSERT_EQUAL(ns::LoadSource::Rebuilt, store->load(2));
  TEST_ASSERT_EQUAL_MEMORY(&want, rtc.get(), sizeof(want));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_slot_set_writes_file_ver_and_today);
  RUN_TEST(test_slot_set_other_day_not_in_rtc);
  RUN_TEST(test_slot_set_idempotent);
  RUN_TEST(test_week_sorted_by_key);
  RUN_TEST(test_week_cap_storefail);
  RUN_TEST(test_day_cap_25_storefail);
  RUN_TEST(test_set_existing_key_when_full_is_ok);
  RUN_TEST(test_slot_del_missing_ok_ver_bumped);
  RUN_TEST(test_slot_del_existing);
  RUN_TEST(test_day_clear_only_that_day);
  RUN_TEST(test_file_write_fail_storefail_keeps_all);
  RUN_TEST(test_ver_write_fail_storefail);
  RUN_TEST(test_corrupt_week_file_resets_ver0);
  RUN_TEST(test_week_read_fail_keeps_ver);
  RUN_TEST(test_replace_kind_sets_ver_even_if_lower);
  RUN_TEST(test_replace_corrupt_body_badpayload);
  RUN_TEST(test_replace_over_capacity_storefail_keeps_old);
  RUN_TEST(test_replace_empty_writes_empty_file);
  RUN_TEST(test_replace_resv_purges_past);
  RUN_TEST(test_resv_purge_before_cap);
  RUN_TEST(test_resv_purge_skipped_when_clock_invalid);
  RUN_TEST(test_resv_set_replace_and_del);
  RUN_TEST(test_purge_past_keeps_today);
  RUN_TEST(test_purge_past_clock_invalid_noop);
  RUN_TEST(test_purge_past_keeps_version);
  RUN_TEST(test_exam_set_del);
  RUN_TEST(test_exam_cap_storefail);
  RUN_TEST(test_load_uses_valid_rtc);
  RUN_TEST(test_load_rebuilds_when_invalid);
  RUN_TEST(test_load_corrupt_schedule_empties_ver0);
  RUN_TEST(test_load_read_fail_and_over_capacity_empty_ver0);
  RUN_TEST(test_load_weekday_zero_no_slots);
  RUN_TEST(test_load_missing_file_with_ver_resets_ver0);
  RUN_TEST(test_load_missing_file_ver0_is_first_boot);
  RUN_TEST(test_load_valid_rtc_other_day_refreshes);
  RUN_TEST(test_refresh_day_switches);
  RUN_TEST(test_refresh_day_corrupt_resets_ver0);
  RUN_TEST(test_refresh_day_read_fail_retries_on_load);
  RUN_TEST(test_write_with_slots_day_zero_keeps_cache_empty);
  RUN_TEST(test_identity_persists);
  RUN_TEST(test_identity_and_txn_store_fail_keep_rtc);
  RUN_TEST(test_last_txn_persists);
  RUN_TEST(test_set_param_known_and_unknown);
  RUN_TEST(test_factory_reset_clears_all);
  RUN_TEST(test_write_through_matches_rebuild);
  return UNITY_END();
}
