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
  return UNITY_END();
}
