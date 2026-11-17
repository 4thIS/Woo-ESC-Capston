// 노드 순수 로직 — 수신(v2 §3.4·3.5·6.4·6.6)은 ns::NodeStore 위에서, 화면 모델은 RtcState + sch 판정(§5.3).
#include <unity.h>

#include <cstring>
#include <memory>
#include <vector>

#include "fake_store.h"
#include "kst_time.h"
#include "lora_codec.h"
#include "node_core.h"
#include "node_store.h"

using namespace nc;

static const Ident ME{'E', 301, 1};
static std::unique_ptr<ns::FakeKv> KV;
static std::unique_ptr<ns::FakeFile> FS;
static std::unique_ptr<ns::RtcState> R;
static std::unique_ptr<ns::NodeStore> ST;
static std::unique_ptr<FileRx> F;
// 2026-11-19(목) 13:30 KST — 수신 시험의 "지금". 목요일 = 4
static uint32_t NOW;

static uint32_t kstEpoch(int y, int mo, int d, int h, int mi) {
  return sch::kstMidnight((uint16_t)y, (uint8_t)mo, (uint8_t)d) + (uint32_t)(h * 3600 + mi * 60);
}

void setUp() {
  KV.reset(new ns::FakeKv());
  FS.reset(new ns::FakeFile());
  R.reset(new ns::RtcState());
  ns::rtcClear(*R);
  ST.reset(new ns::NodeStore(*KV, *FS, *R));
  ST->load(4);  // 목요일 슬롯을 RTC 에
  F.reset(new FileRx());
  std::memset(F.get(), 0, sizeof(FileRx));
  NOW = kstEpoch(2026, 11, 19, 13, 30);
}
void tearDown() {}

static lc::Header hdr(uint8_t type, uint8_t txn, uint8_t flags = LP_FLAG_ACK_REQ, uint8_t bld = 'E',
                      uint16_t room = 301, uint8_t unit = 1) {
  lc::Header h{};
  h.ver = LP_PROTO_VER;
  h.flags = flags;
  h.netId = RP_NET_ID;
  h.type = type;
  h.bld = bld;
  h.room = room;
  h.unit = unit;
  h.txn = txn;
  return h;
}

static uint8_t g_pl[256];
static Outcome run(lc::Header h, size_t n) {
  h.len = (uint8_t)n;
  return handleFrame(*ST, *F, h, g_pl, NOW);
}

static lc::SlotRec slot(uint8_t day, uint8_t sH, uint8_t sM, uint8_t eH, uint8_t eM, const char* subj,
                        uint8_t type = LP_SLOTTYPE_CLASS) {
  lc::SlotRec s{};
  s.day = day, s.sH = sH, s.sM = sM, s.eH = eH, s.eM = eM, s.type = type;
  std::strncpy(s.subj, subj, LP_SUBJ_MAX);
  std::strncpy(s.prof, "교수", LP_PROF_MAX);
  return s;
}

static Outcome slotSet(uint8_t txn, uint8_t ver, const lc::SlotRec& s) {
  return run(hdr(LP_TYPE_SLOT_SET, txn), lc::encSlotSet(ver, s, g_pl, sizeof g_pl));
}

// ---------------- 대상 필터 §6.6 ----------------
void test_is_for_me() {
  TEST_ASSERT_TRUE(isForMe(ME, hdr(LP_TYPE_SLOT_SET, 1)));
  TEST_ASSERT_TRUE(isForMe(ME, hdr(LP_TYPE_SLOT_SET, 1, LP_FLAG_ACK_REQ, 'E', 301, LP_UNIT_ALL)));
  TEST_ASSERT_TRUE(isForMe(ME, hdr(LP_TYPE_TIME, 0, LP_FLAG_BROADCAST, LP_BLD_ALL, 0xFFFF, 0xFF)));
  TEST_ASSERT_FALSE(isForMe(ME, hdr(LP_TYPE_SLOT_SET, 1, LP_FLAG_ACK_REQ, 'E', 302)));
  TEST_ASSERT_FALSE(isForMe(ME, hdr(LP_TYPE_SLOT_SET, 1, LP_FLAG_ACK_REQ, 'E', 301, 2)));
  TEST_ASSERT_FALSE(isForMe(ME, hdr(LP_TYPE_SLOT_SET, 1, LP_FLAG_ACK_REQ, 'A', 301)));
  TEST_ASSERT_FALSE(isForMe(ME, hdr(LP_TYPE_SET_ROOM, 1, LP_FLAG_ACK_REQ, LP_BLD_UNPROVISIONED, 0, 0)));
}

void test_gap_rule_mod_255() {
  TEST_ASSERT_FALSE(gap(0, 1));
  TEST_ASSERT_FALSE(gap(7, 8));
  TEST_ASSERT_FALSE(gap(255, 1));  // 1~255 롤링
  TEST_ASSERT_TRUE(gap(7, 9));
  TEST_ASSERT_TRUE(gap(7, 7));
}

// ---------------- 수신 적용 §6.4 ----------------
void test_today_of_is_kst_date() {
  ns::Date d = todayOf(kstEpoch(2026, 11, 19, 0, 5));  // KST 자정 직후 = UTC 로는 전날
  TEST_ASSERT_EQUAL_UINT8(26, d.y);
  TEST_ASSERT_EQUAL_UINT8(11, d.m);
  TEST_ASSERT_EQUAL_UINT8(19, d.d);
}

void test_slot_set_ok_then_gap_then_dup() {
  Outcome o = slotSet(10, 1, slot(4, 9, 0, 9, 50, "자료구조"));
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, o.status);
  TEST_ASSERT_TRUE(o.changed);
  TEST_ASSERT_EQUAL_UINT8(1, R->nSlots);
  TEST_ASSERT_EQUAL_UINT8(1, R->schedVer);
  TEST_ASSERT_EQUAL_UINT8(10, R->lastTxn);
  o = slotSet(11, 3, slot(4, 10, 0, 10, 50, "운영체제"));
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_GAP, o.status);  // 2 를 건너뜀 — 적용은 하고 GAP
  TEST_ASSERT_EQUAL_UINT8(2, R->nSlots);
  TEST_ASSERT_EQUAL_UINT8(11, R->lastTxn);  // GAP 도 저장 OK 라 lastTxn 기록(#74 10)
  o = slotSet(11, 3, slot(4, 10, 0, 10, 50, "운영체제"));
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_DUP, o.status);
  TEST_ASSERT_FALSE(o.changed);
}

void test_slot_set_other_day_goes_to_file_not_rtc() {
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, slotSet(1, 1, slot(2, 9, 0, 9, 50, "화요일")).status);
  TEST_ASSERT_EQUAL_UINT8(0, R->nSlots);  // 오늘(목)이 아님
  TEST_ASSERT_EQUAL_UINT8(1, R->schedVer);
  TEST_ASSERT_EQUAL(ns::StoreStatus::Ok, ST->refreshDay(2));
  TEST_ASSERT_EQUAL_UINT8(1, R->nSlots);
  TEST_ASSERT_EQUAL_STRING("화요일", R->slots[0].subj);
}

void test_slot_set_same_key_replaces() {
  slotSet(1, 1, slot(4, 9, 0, 9, 50, "자료구조"));
  slotSet(2, 2, slot(4, 9, 0, 9, 50, "운영체제"));
  TEST_ASSERT_EQUAL_UINT8(1, R->nSlots);
  TEST_ASSERT_EQUAL_STRING("운영체제", R->slots[0].subj);
}

void test_store_fail_keeps_version_and_last_txn() {
  for (uint8_t i = 0; i < LP_SLOT_DAY_MAX; ++i)
    TEST_ASSERT_EQUAL_HEX8(
        LP_ACK_OK, slotSet((uint8_t)(i + 1), (uint8_t)(i + 1),
                           slot(4, (uint8_t)(i % 24), (uint8_t)(i / 24), (uint8_t)(i % 24), 59, "가득"))
                       .status);
  Outcome o = slotSet(100, 25, slot(4, 23, 30, 23, 59, "넘침"));
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_STORE_FAIL, o.status);
  TEST_ASSERT_EQUAL_UINT8(LP_SLOT_DAY_MAX, R->schedVer);  // 실패는 버전을 안 바꾼다
  TEST_ASSERT_EQUAL_UINT8(LP_SLOT_DAY_MAX, R->lastTxn);   // 실패는 lastTxn 을 안 바꾼다(#74 10)
}

void test_file_write_failure_is_store_fail() {
  FS->failWritesAfter = 0;
  Outcome o = slotSet(1, 1, slot(4, 9, 0, 9, 50, "자료구조"));
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_STORE_FAIL, o.status);
  TEST_ASSERT_FALSE(o.changed);
  TEST_ASSERT_EQUAL_UINT8(0, R->nSlots);
  TEST_ASSERT_EQUAL_UINT8(0, R->schedVer);
  TEST_ASSERT_EQUAL_UINT8(0, R->lastTxn);
}

// 저장 실패 뒤 같은 프레임(같은 txn)을 다시 받으면 DUP 이 아니라 정상 적용돼야 한다
void test_retry_after_store_fail_is_not_dup() {
  FS->failWritesAfter = 0;
  Outcome o = slotSet(7, 1, slot(4, 9, 0, 9, 50, "자료구조"));
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_STORE_FAIL, o.status);
  FS->failWritesAfter = -1;
  o = slotSet(7, 1, slot(4, 9, 0, 9, 50, "자료구조"));
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, o.status);
  TEST_ASSERT_EQUAL_UINT8(7, R->lastTxn);
  TEST_ASSERT_EQUAL_UINT8(1, R->nSlots);
}

void test_slot_del_and_day_clear() {
  slotSet(1, 1, slot(4, 9, 0, 9, 50, "a"));
  slotSet(2, 2, slot(4, 10, 0, 10, 50, "b"));
  slotSet(3, 3, slot(2, 9, 0, 9, 50, "c"));
  lc::SlotDel d{4, 9, 0};
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK,
                         run(hdr(LP_TYPE_SLOT_DEL, 4), lc::encSlotDel(4, d, g_pl, sizeof g_pl)).status);
  TEST_ASSERT_EQUAL_UINT8(1, R->nSlots);
  lc::DayClear c{4};
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK,
                         run(hdr(LP_TYPE_DAY_CLEAR, 5), lc::encDayClear(5, c, g_pl, sizeof g_pl)).status);
  TEST_ASSERT_EQUAL_UINT8(0, R->nSlots);
  TEST_ASSERT_EQUAL(ns::StoreStatus::Ok, ST->refreshDay(2));  // 다른 요일은 남아 있다
  TEST_ASSERT_EQUAL_UINT8(1, R->nSlots);
  TEST_ASSERT_EQUAL_UINT8(2, R->slots[0].day);
}

void test_resv_and_exam() {
  lc::ResvRec r{};
  r.resvId = 77, r.y = 26, r.m = 11, r.d = 19, r.sH = 15, r.eH = 17, r.type = LP_SLOTTYPE_RENTAL;
  strcpy(r.subj, "스터디");
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK,
                         run(hdr(LP_TYPE_RESV_SET, 1), lc::encResvSet(1, r, g_pl, sizeof g_pl)).status);
  TEST_ASSERT_EQUAL_UINT8(1, R->nResv);
  lc::ResvDel rd{77};
  run(hdr(LP_TYPE_RESV_DEL, 2), lc::encResvDel(2, rd, g_pl, sizeof g_pl));
  TEST_ASSERT_EQUAL_UINT8(0, R->nResv);
  TEST_ASSERT_EQUAL_UINT8(2, R->resvVer);
  lc::ExamRec e{5, 26, 11, 16, 26, 11, 20};
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK,
                         run(hdr(LP_TYPE_EXAM_SET, 3), lc::encExamSet(1, e, g_pl, sizeof g_pl)).status);
  TEST_ASSERT_EQUAL_UINT8(1, R->nExam);
  TEST_ASSERT_EQUAL_UINT8(1, R->examVer);
}

void test_time_broadcast_sets_clock_without_ack() {
  lc::Time t{1793156768, 0};
  Outcome o = run(hdr(LP_TYPE_TIME, 0, LP_FLAG_BROADCAST, LP_BLD_ALL, 0xFFFF, 0xFF),
                  lc::encTime(t, g_pl, sizeof g_pl));
  TEST_ASSERT_EQUAL_HEX8(kNoAck, o.status);
  TEST_ASSERT_TRUE(o.timeSet);
  TEST_ASSERT_EQUAL_UINT32(1793156768u, o.epoch);
}

void test_time_targeted_acks_and_skips_dup() {
  R->lastTxn = 0;
  lc::Time t{1793156768, 0};
  Outcome o = run(hdr(LP_TYPE_TIME, 0), lc::encTime(t, g_pl, sizeof g_pl));
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, o.status);  // txn 0 이어도 DUP 아님(§3.5)
  TEST_ASSERT_TRUE(o.timeSet);
}

void test_no_ack_without_ack_req() {
  Outcome o =
      run(hdr(LP_TYPE_SLOT_SET, 9, 0), lc::encSlotSet(1, slot(4, 9, 0, 9, 50, "a"), g_pl, sizeof g_pl));
  TEST_ASSERT_EQUAL_HEX8(kNoAck, o.status);
  TEST_ASSERT_EQUAL_UINT8(1, R->nSlots);  // 적용은 한다
}

void test_bad_payload_and_unsupported() {
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_BAD_PAYLOAD, run(hdr(LP_TYPE_SLOT_SET, 1), 2).status);
  lc::CmdMsg c{1, nullptr, 0};
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_UNSUPPORTED,
                         run(hdr(LP_TYPE_CMD, 2), lc::encCmd(c, g_pl, sizeof g_pl)).status);
}

// ---------------- STATUS 요청(§3.3 TIME flags·CMD REQUEST_STATUS) ----------------
void test_time_request_status_flag() {
  lc::Time t{1793156768, LP_TIMEFLAG_REQUEST_STATUS};
  Outcome o = run(hdr(LP_TYPE_TIME, 0, LP_FLAG_BROADCAST, LP_BLD_ALL, 0xFFFF, 0xFF),
                  lc::encTime(t, g_pl, sizeof g_pl));
  TEST_ASSERT_TRUE(o.timeSet);
  TEST_ASSERT_TRUE(o.statusReq);
  TEST_ASSERT_EQUAL_UINT32(kReqStatusSpreadMs, o.statusSpreadMs);
  lc::Time t0{1793156768, 0};
  Outcome o0 = run(hdr(LP_TYPE_TIME, 0, LP_FLAG_BROADCAST, LP_BLD_ALL, 0xFFFF, 0xFF),
                   lc::encTime(t0, g_pl, sizeof g_pl));
  TEST_ASSERT_FALSE(o0.statusReq);
}

void test_cmd_request_status_acks_ok() {
  lc::CmdMsg c{LP_CMD_REQUEST_STATUS, nullptr, 0};
  Outcome o = run(hdr(LP_TYPE_CMD, 7), lc::encCmd(c, g_pl, sizeof g_pl));
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, o.status);
  TEST_ASSERT_TRUE(o.statusReq);
  TEST_ASSERT_EQUAL_UINT32(0, o.statusSpreadMs);
  TEST_ASSERT_FALSE(o.changed);  // 화면은 그대로
  // 같은 TXN 재송 = DUP, 다시 요청하지 않는다
  Outcome d = run(hdr(LP_TYPE_CMD, 7), lc::encCmd(c, g_pl, sizeof g_pl));
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_DUP, d.status);
  TEST_ASSERT_FALSE(d.statusReq);
}

// ---------------- STATUS 내용(§3.3·5.2) ----------------
void test_status_flags() {
  R->provisioned = 1;
  R->lastTimeSyncEpoch = NOW - 3600;
  TEST_ASSERT_EQUAL_HEX8(0, statusFlags(*R, NOW, 4000));
  TEST_ASSERT_EQUAL_HEX8(LP_STATUSFLAG_CLOCK_STALE, statusFlags(*R, 1000, 4000));  // 시계 무효
  R->lastTimeSyncEpoch = 0;
  TEST_ASSERT_EQUAL_HEX8(LP_STATUSFLAG_CLOCK_STALE, statusFlags(*R, NOW, 4000));  // TIME 받은 적 없음
  R->lastTimeSyncEpoch = NOW - kClockStaleSec;
  TEST_ASSERT_EQUAL_HEX8(0, statusFlags(*R, NOW, 4000));  // 딱 25 h 는 아직
  R->lastTimeSyncEpoch = NOW - kClockStaleSec - 1;
  TEST_ASSERT_EQUAL_HEX8(LP_STATUSFLAG_CLOCK_STALE, statusFlags(*R, NOW, 4000));
  R->lastTimeSyncEpoch = NOW;
  TEST_ASSERT_EQUAL_HEX8(LP_STATUSFLAG_LOW_BATT, statusFlags(*R, NOW, 3499));
  TEST_ASSERT_EQUAL_HEX8(0, statusFlags(*R, NOW, 3500));
  TEST_ASSERT_EQUAL_HEX8(0, statusFlags(*R, NOW, 0));  // 0 = 측정 못 함
  R->provisioned = 0;
  TEST_ASSERT_EQUAL_HEX8(LP_STATUSFLAG_UNPROVISIONED, statusFlags(*R, NOW, 4000));
}

void test_build_status_fields() {
  R->provisioned = 1;
  R->schedVer = 12, R->resvVer = 3, R->examVer = 4, R->identVer = 5;
  R->lastTimeSyncEpoch = 0;
  lc::Status s = buildStatus(*R, NOW, 4012, 4, LP_LAYOUT_CLASS, LinkInfo{-56, 44, 7});
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, s.ack.status);
  TEST_ASSERT_EQUAL_UINT8(0, s.ack.detail);
  TEST_ASSERT_EQUAL_UINT16(4012, s.ack.battMv);
  TEST_ASSERT_EQUAL_UINT8(12, s.ack.schedVer);
  TEST_ASSERT_EQUAL_UINT8(3, s.ack.resvVer);
  TEST_ASSERT_EQUAL_UINT8(4, s.ack.examVer);
  TEST_ASSERT_EQUAL_UINT8(5, s.ack.identVer);
  TEST_ASSERT_EQUAL_UINT8(4, s.ack.fw);
  TEST_ASSERT_EQUAL_UINT8(LP_LAYOUT_CLASS, s.ack.layout);
  TEST_ASSERT_EQUAL_INT8(-56, s.rssiLast);
  TEST_ASSERT_EQUAL_INT8(44, s.snrLastX4);
  TEST_ASSERT_EQUAL_UINT16(7, s.uptimeH);
  TEST_ASSERT_EQUAL_HEX8(LP_STATUSFLAG_CLOCK_STALE, s.flags);
  uint8_t out[32];
  TEST_ASSERT_EQUAL(15, lc::encStatus(s, out, sizeof out));  // ACK 10 B + 5 B
}

void test_build_ack_carries_ident_ver() {
  R->schedVer = 9, R->identVer = 2;
  lc::Ack a = buildAck(*R, LP_ACK_GAP, 1, 3900, 4, LP_LAYOUT_EMPTY);
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_GAP, a.status);
  TEST_ASSERT_EQUAL_UINT8(1, a.detail);
  TEST_ASSERT_EQUAL_UINT16(3900, a.battMv);
  TEST_ASSERT_EQUAL_UINT8(9, a.schedVer);
  TEST_ASSERT_EQUAL_UINT8(2, a.identVer);
  TEST_ASSERT_EQUAL_UINT8(LP_LAYOUT_EMPTY, a.layout);
}

// ---------------- STATUS 시각(§6.3) ----------------
void test_next_daily_status() {
  const uint32_t day = 1794873600u;  // 2026-11-17 00:00 UTC
  TEST_ASSERT_EQUAL_UINT32(day + 18 * 3600, nextDailyStatus(day + 4 * 3600, 18, 0));
  TEST_ASSERT_EQUAL_UINT32(day + 86400 + 18 * 3600,
                           nextDailyStatus(day + 18 * 3600, 18, 0));  // 같은 초면 다음 날
  TEST_ASSERT_EQUAL_UINT32(day + 18 * 3600 + 1799, nextDailyStatus(day + 18 * 3600 + 100, 18, 1799));
  TEST_ASSERT_EQUAL_UINT32(day + 86400 + 1000,
                           nextDailyStatus(day + 23 * 3600 + 1800, 23, 3600 + 1000));  // 자정 넘김
}

void test_mac_spread_deterministic() {
  const uint8_t a[6] = {0x3c, 0x0f, 0x02, 0xee, 0x47, 0x10};
  const uint8_t b[6] = {0xac, 0xa7, 0x04, 0x3c, 0x3f, 0x80};
  TEST_ASSERT_EQUAL_UINT32(macSpread(a, 1800), macSpread(a, 1800));
  TEST_ASSERT_TRUE(macSpread(a, 1800) < 1800);
  TEST_ASSERT_TRUE(macSpread(b, 1800) < 1800);
  TEST_ASSERT_NOT_EQUAL(macSpread(a, 1800), macSpread(b, 1800));
  TEST_ASSERT_EQUAL_UINT32(0, macSpread(a, 0));
}

void test_status_plan_request_and_sent() {
  StatusPlan p;
  TEST_ASSERT_FALSE(p.due(1000, false, 0, 0));
  p.request(1000, 2000);
  TEST_ASSERT_FALSE(p.due(2999, false, 0, 0));
  TEST_ASSERT_TRUE(p.due(3000, false, 0, 0));
  p.request(1500, 60000);  // 더 늦은 요청은 이른 예약을 밀지 않는다
  TEST_ASSERT_TRUE(p.due(3000, false, 0, 0));
  p.sent(3000, false, false);  // CAD busy → 5 s 뒤
  TEST_ASSERT_FALSE(p.due(7999, false, 0, 0));
  TEST_ASSERT_TRUE(p.due(8000, false, 0, 0));
  p.sent(8000, true, false);  // 보냈지만 시계 없음 → 10 min 뒤
  TEST_ASSERT_FALSE(p.due(8000 + kStaleRetryMs - 1, false, 0, 0));
  TEST_ASSERT_TRUE(p.due(8000 + kStaleRetryMs, false, 0, 0));
  TEST_ASSERT_FALSE(p.due(8000 + kStaleRetryMs, true, NOW, 0));  // 그 사이 시계가 맞으면 건너뜀
  p.request(9000, 300);                                          // 새 요청은 시계 재시도 예약을 대신한다
  TEST_ASSERT_TRUE(p.due(9300, true, NOW, 0));
  p.sent(9300, true, true);
  TEST_ASSERT_FALSE(p.due(9300 + kStaleRetryMs, true, NOW, 0));
}

void test_status_plan_resends_after_time_when_stale_sent() {
  StatusPlan p;
  p.request(0, 1000);
  p.sent(1000, true, false, LP_STATUSFLAG_CLOCK_STALE);  // 부팅 보고 — 시계 없음으로 알렸다
  p.onTimeSet(4000);  // 시각을 받았다 → 서버의 "시계 이상" 표시를 지우러 한 번 더
  TEST_ASSERT_FALSE(p.due(4000 + kAfterTimeStatusMs - 1, true, NOW, 0));
  TEST_ASSERT_TRUE(p.due(4000 + kAfterTimeStatusMs, true, NOW, 0));
  p.sent(4000 + kAfterTimeStatusMs, true, true, 0);
  TEST_ASSERT_FALSE(p.due(4000 + kAfterTimeStatusMs + kStaleRetryMs, true, NOW, 0));
  p.onTimeSet(20000);  // 다음 방송 TIME — 이미 알렸으니 다시 보내지 않는다
  TEST_ASSERT_FALSE(p.due(20000 + kAfterTimeStatusMs, true, NOW, 0));
}

void test_status_plan_no_resend_without_stale() {
  StatusPlan p;
  p.onTimeSet(0);
  TEST_ASSERT_FALSE(p.due(kAfterTimeStatusMs, true, NOW, 0));
  p.request(0, 0);
  p.sent(0, true, true, 0);  // 시계 정상으로 알렸다
  p.onTimeSet(100);
  TEST_ASSERT_FALSE(p.due(100 + kAfterTimeStatusMs, true, NOW, 0));
}

void test_status_plan_daily_and_wrap() {
  StatusPlan p;
  TEST_ASSERT_FALSE(p.due(0, true, NOW, 0));  // 하루 시각이 아직 없음
  TEST_ASSERT_FALSE(p.due(0, true, NOW, NOW + 1));
  TEST_ASSERT_TRUE(p.due(0, true, NOW, NOW));
  TEST_ASSERT_FALSE(p.due(0, false, NOW, NOW));  // 시계 무효면 하루 STATUS 없음
  p.request(0xFFFFF000u, 0x2000);                // millis 넘어감
  TEST_ASSERT_FALSE(p.due(0xFFFFFFFFu, false, 0, 0));
  TEST_ASSERT_TRUE(p.due(0x1000u, false, 0, 0));
}

// ---------------- FILE 세션 ----------------
static std::vector<uint8_t> scheduleBody(int n) {
  std::vector<uint8_t> body;
  uint8_t rec[64];
  for (int i = 0; i < n; ++i) {
    size_t k =
        lc::encSlotBody(slot((uint8_t)(i % 5 + 1), (uint8_t)(9 + i / 5), 0, (uint8_t)(9 + i / 5), 50, "과목"),
                        rec, sizeof rec);
    body.push_back(LP_TYPE_SLOT_SET);  // 레코드 머리: recType(kind 의 SET TYPE)·길이
    body.push_back((uint8_t)k);
    body.insert(body.end(), rec, rec + k);
  }
  return body;
}

static void fileSession(const std::vector<uint8_t>& body, uint8_t ver, uint8_t txn0, int skipSeq,
                        Outcome& end) {
  uint8_t chunks = (uint8_t)((body.size() + LP_FILE_CHUNK_MAX - 1) / LP_FILE_CHUNK_MAX);
  lc::FileBegin b{LP_FILEKIND_SCHEDULE, (uint16_t)body.size(), chunks};
  TEST_ASSERT_EQUAL_HEX8(
      LP_ACK_OK, run(hdr(LP_TYPE_FILE_BEGIN, txn0), lc::encFileBegin(ver, b, g_pl, sizeof g_pl)).status);
  uint8_t txn = txn0;
  for (uint8_t s = 0; s < chunks; ++s) {
    if (s == skipSeq) continue;
    size_t off = (size_t)s * LP_FILE_CHUNK_MAX;
    lc::FileData d{s, body.data() + off, (uint8_t)std::min<size_t>(LP_FILE_CHUNK_MAX, body.size() - off)};
    TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK,
                           run(hdr(LP_TYPE_FILE_DATA, ++txn), lc::encFileData(d, g_pl, sizeof g_pl)).status);
  }
  lc::FileEnd e{lc::crc16(body.data(), body.size())};
  end = run(hdr(LP_TYPE_FILE_END, ++txn), lc::encFileEnd(e, g_pl, sizeof g_pl));
}

static std::vector<uint8_t> dayBody(int n, uint8_t day) {
  std::vector<uint8_t> body;
  uint8_t rec[64];
  for (int i = 0; i < n; ++i) {
    size_t k = lc::encSlotBody(
        slot(day, (uint8_t)(i / 2), (uint8_t)(i % 2 * 30), (uint8_t)(i / 2), (uint8_t)(i % 2 * 30 + 20), "x"),
        rec + 2, sizeof rec - 2);
    rec[0] = LP_TYPE_SLOT_SET;
    rec[1] = (uint8_t)k;
    body.insert(body.end(), rec, rec + 2 + k);
  }
  return body;
}

void test_file_session_replaces_whole_kind() {
  slotSet(1, 1, slot(7, 9, 0, 9, 50, "지워질 것"));  // 일요일 — 파일에만 있다
  auto body = scheduleBody(60);                      // 200 B 청크 여러 개
  Outcome end;
  fileSession(body, 9, 20, -1, end);
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, end.status);
  TEST_ASSERT_TRUE(end.changed);
  TEST_ASSERT_EQUAL_UINT8(12, R->nSlots);  // day = i % 5 + 1 — 목(4)은 i % 5 == 3 인 12개
  TEST_ASSERT_EQUAL_UINT8(9, R->schedVer);
  TEST_ASSERT_EQUAL(ns::StoreStatus::Ok, ST->refreshDay(7));
  TEST_ASSERT_EQUAL_UINT8(0, R->nSlots);  // 옛 일요일 슬롯은 사라졌다
}

void test_file_missing_reports_first_seq() {
  auto body = scheduleBody(30);
  Outcome end;
  fileSession(body, 4, 50, 2, end);
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_FILE_MISSING, end.status);
  TEST_ASSERT_EQUAL_UINT8(2, end.detail);
  TEST_ASSERT_EQUAL_UINT8(0, R->schedVer);
}

void test_file_bad_crc() {
  auto body = scheduleBody(3);
  lc::FileBegin b{LP_FILEKIND_SCHEDULE, (uint16_t)body.size(), 1};
  run(hdr(LP_TYPE_FILE_BEGIN, 1), lc::encFileBegin(2, b, g_pl, sizeof g_pl));
  lc::FileData d{0, body.data(), (uint8_t)body.size()};
  run(hdr(LP_TYPE_FILE_DATA, 2), lc::encFileData(d, g_pl, sizeof g_pl));
  lc::FileEnd e{(uint16_t)(lc::crc16(body.data(), body.size()) ^ 1)};
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_BAD_CRC,
                         run(hdr(LP_TYPE_FILE_END, 3), lc::encFileEnd(e, g_pl, sizeof g_pl)).status);
}

// 하루 상한 LP_SLOT_DAY_MAX(v2 §5.1·§12) — 주간 합계가 96 이하여도 한 요일 25번째는 STORE_FAIL
void test_day_cap_slot_set() {
  for (uint8_t i = 0; i < LP_SLOT_DAY_MAX; ++i)
    TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK,
                           slotSet((uint8_t)(i + 1), (uint8_t)(i + 1), slot(4, i, 0, i, 50, "x")).status);
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_STORE_FAIL, slotSet(100, 25, slot(4, 23, 55, 23, 59, "넘침")).status);
  TEST_ASSERT_EQUAL_UINT8(LP_SLOT_DAY_MAX, R->nSlots);
  TEST_ASSERT_EQUAL_UINT8(LP_SLOT_DAY_MAX, R->lastTxn);
  // 이미 있는 키는 교체라 OK, 다른 요일은 여유가 있으니 OK
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, slotSet(101, 25, slot(4, 3, 0, 3, 50, "교체")).status);
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, slotSet(102, 26, slot(3, 9, 0, 9, 50, "수요일")).status);
  TEST_ASSERT_EQUAL_UINT8(LP_SLOT_DAY_MAX, R->nSlots);
  TEST_ASSERT_EQUAL(ns::StoreStatus::Ok, ST->refreshDay(3));
  TEST_ASSERT_EQUAL_UINT8(1, R->nSlots);
}

void test_day_cap_file_keeps_old() {
  slotSet(1, 1, slot(1, 9, 0, 9, 50, "그대로"));
  auto body = dayBody(LP_SLOT_DAY_MAX + 1, 2);
  Outcome end;
  fileSession(body, 9, 20, -1, end);
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_STORE_FAIL, end.status);
  TEST_ASSERT_EQUAL_UINT8(1, R->schedVer);
  TEST_ASSERT_EQUAL_UINT8(23, R->lastTxn);  // 마지막 FILE_DATA(23)까지만 — 실패한 FILE_END(24)는 안 바꾼다
  TEST_ASSERT_EQUAL(ns::StoreStatus::Ok, ST->refreshDay(1));
  TEST_ASSERT_EQUAL_UINT8(1, R->nSlots);  // 옛 월요일 슬롯이 그대로
}

// ---------------- 화면 모델 ----------------

void test_model_class_fills_cur_next_today() {
  R->bld = 'E', R->room = 301, R->unit = 1;
  slotSet(1, 1, slot(4, 9, 0, 10, 50, "자료구조"));
  slotSet(2, 2, slot(4, 13, 0, 14, 50, "임베디드SW"));
  slotSet(3, 3, slot(4, 16, 0, 18, 50, "캡스톤디자인"));
  slotSet(4, 4, slot(3, 13, 0, 14, 50, "다른 요일"));
  RenderModel m;
  sch::LayoutDecision d = buildModel(*R, kstEpoch(2026, 11, 19, 13, 30), m);
  TEST_ASSERT_EQUAL_UINT8(LP_LAYOUT_CLASS, m.layout);
  TEST_ASSERT_EQUAL_UINT16(13 * 60, d.slotStartMin);
  TEST_ASSERT_EQUAL_STRING("임베디드SW", m.cur.subj);
  TEST_ASSERT_EQUAL_STRING("캡스톤디자인", m.next.subj);
  TEST_ASSERT_EQUAL_UINT8(3, m.nToday);
  TEST_ASSERT_EQUAL_STRING("자료구조", m.today[0].subj);
  TEST_ASSERT_EQUAL_STRING("11.19", m.dateStr);
  TEST_ASSERT_EQUAL_UINT8(4, m.weekday);
  TEST_ASSERT_EQUAL('E', m.bld);
  TEST_ASSERT_EQUAL_UINT16(301, m.room);
}

void test_model_break_cur_is_next() {
  slotSet(1, 1, slot(4, 9, 0, 9, 50, "1블록"));
  slotSet(2, 2, slot(4, 10, 0, 10, 50, "2블록"));
  RenderModel m;
  buildModel(*R, kstEpoch(2026, 11, 19, 9, 55), m);
  TEST_ASSERT_EQUAL_UINT8(LP_LAYOUT_BREAK, m.layout);
  TEST_ASSERT_EQUAL_STRING("2블록", m.next.subj);
  TEST_ASSERT_EQUAL_STRING("2블록", m.cur.subj);  // cur = next (#89, 2026-10-28)
}

void test_model_resv_today_beats_slot() {
  slotSet(1, 1, slot(4, 15, 0, 16, 50, "정규"));
  lc::ResvRec r{};
  r.resvId = 1, r.y = 26, r.m = 11, r.d = 19, r.sH = 15, r.eH = 17, r.type = LP_SLOTTYPE_RENTAL;
  strcpy(r.subj, "스터디");
  run(hdr(LP_TYPE_RESV_SET, 2), lc::encResvSet(1, r, g_pl, sizeof g_pl));
  RenderModel m;
  buildModel(*R, kstEpoch(2026, 11, 19, 15, 30), m);
  TEST_ASSERT_EQUAL_UINT8(LP_LAYOUT_RENTAL, m.layout);
  TEST_ASSERT_EQUAL_STRING("스터디", m.cur.subj);
  buildModel(*R, kstEpoch(2026, 11, 20, 15, 30), m);  // 다음날(금)은 예약 없음·정규도 없음
  TEST_ASSERT_EQUAL_UINT8(LP_LAYOUT_EMPTY, m.layout);
}

void test_model_exam_period() {
  slotSet(1, 1, slot(4, 9, 0, 9, 50, "자료구조"));
  lc::ExamRec e{5, 26, 11, 16, 26, 11, 20};
  run(hdr(LP_TYPE_EXAM_SET, 2), lc::encExamSet(1, e, g_pl, sizeof g_pl));
  RenderModel m;
  buildModel(*R, kstEpoch(2026, 11, 19, 9, 10), m);
  TEST_ASSERT_EQUAL_UINT8(LP_LAYOUT_EXAM, m.layout);
}

// ---------------- 오늘 목록: 연속 교시 한 행 (terminal-epaper.md 「오늘 목록」, 2026-11-12) ----------------
// 목요일 803호 — 102반 09:00–11:50(3교시) 다음 101반 12:00–14:50(3교시). 과목·교수 같고 반 사이 틈도 10분이라
// 분반(과목명 뒤)만이 두 수업을 가른다.
static void thursdayTwoSections() {
  uint8_t txn = 1;
  for (uint8_t h = 9; h <= 11; ++h) slotSet(txn, txn, slot(4, h, 0, h, 50, "웹실습 102")), ++txn;
  for (uint8_t h = 12; h <= 14; ++h) slotSet(txn, txn, slot(4, h, 0, h, 50, "웹실습 101")), ++txn;
}

void test_today_merges_periods_of_same_section_only() {
  thursdayTwoSections();
  RenderModel m;
  buildModel(*R, kstEpoch(2026, 11, 19, 10, 20), m);
  TEST_ASSERT_EQUAL_UINT8(2, m.nToday);
  TEST_ASSERT_EQUAL_STRING("웹실습 102", m.today[0].subj);
  TEST_ASSERT_EQUAL_UINT8(9, m.today[0].sH);
  TEST_ASSERT_EQUAL_UINT8(0, m.today[0].sM);
  TEST_ASSERT_EQUAL_UINT8(11, m.today[0].eH);
  TEST_ASSERT_EQUAL_UINT8(50, m.today[0].eM);
  TEST_ASSERT_EQUAL_STRING("웹실습 101", m.today[1].subj);
  TEST_ASSERT_EQUAL_UINT8(12, m.today[1].sH);
  TEST_ASSERT_EQUAL_UINT8(14, m.today[1].eH);
  TEST_ASSERT_EQUAL_UINT8(50, m.today[1].eM);
  // 정보 영역은 교시 단위 그대로
  TEST_ASSERT_EQUAL_UINT8(LP_LAYOUT_CLASS, m.layout);
  TEST_ASSERT_EQUAL_UINT8(10, m.cur.sH);
  TEST_ASSERT_EQUAL_UINT8(10, m.cur.eH);
  TEST_ASSERT_EQUAL_UINT8(50, m.cur.eM);
}

void test_today_merge_keeps_break_per_period() {
  thursdayTwoSections();
  RenderModel m;
  buildModel(*R, kstEpoch(2026, 11, 19, 10, 55), m);  // 102반 2·3교시 사이 쉬는시간
  TEST_ASSERT_EQUAL_UINT8(LP_LAYOUT_BREAK, m.layout);
  TEST_ASSERT_EQUAL_UINT8(11, m.cur.sH);  // cur = 곧 시작할 교시
  TEST_ASSERT_EQUAL_UINT8(2, m.nToday);
  buildModel(*R, kstEpoch(2026, 11, 19, 11, 55), m);  // 반이 바뀌는 틈도 쉬는시간(과목·교수 같음)
  TEST_ASSERT_EQUAL_UINT8(LP_LAYOUT_BREAK, m.layout);
  TEST_ASSERT_EQUAL_STRING("웹실습 101", m.cur.subj);
}

void test_today_merge_rules_gap_type_and_contiguous() {
  slotSet(1, 1, slot(4, 9, 0, 9, 50, "자료구조"));
  slotSet(2, 2, slot(4, 10, 6, 10, 56, "자료구조"));  // 틈 16분 → 따로
  slotSet(3, 3, slot(4, 12, 0, 13, 0, "캡스톤"));
  slotSet(4, 4, slot(4, 13, 0, 14, 0, "캡스톤"));  // 틈 0분 → 합침
  slotSet(5, 5, slot(4, 15, 0, 15, 50, "특강"));
  slotSet(6, 6, slot(4, 16, 0, 16, 50, "특강", LP_SLOTTYPE_SPECIAL));  // type 다름 → 따로
  slotSet(7, 7, slot(4, 17, 0, 17, 50, "운영체제"));
  slotSet(8, 8, slot(4, 18, 5, 18, 55, "운영체제"));  // 틈 15분 → 합침(경계 포함)
  RenderModel m;
  buildModel(*R, kstEpoch(2026, 11, 19, 8, 0), m);
  TEST_ASSERT_EQUAL_UINT8(6, m.nToday);
  TEST_ASSERT_EQUAL_UINT8(9, m.today[0].sH);
  TEST_ASSERT_EQUAL_UINT8(10, m.today[1].sH);
  TEST_ASSERT_EQUAL_UINT8(12, m.today[2].sH);
  TEST_ASSERT_EQUAL_UINT8(14, m.today[2].eH);
  TEST_ASSERT_EQUAL_UINT8(LP_SLOTTYPE_CLASS, m.today[3].type);
  TEST_ASSERT_EQUAL_UINT8(LP_SLOTTYPE_SPECIAL, m.today[4].type);
  TEST_ASSERT_EQUAL_UINT8(17, m.today[5].sH);
  TEST_ASSERT_EQUAL_UINT8(18, m.today[5].eH);
  TEST_ASSERT_EQUAL_UINT8(55, m.today[5].eM);
}

void test_model_identity_from_rtc() {
  R->bld = 'E';
  R->room = 803;
  R->unit = 1;
  RenderModel m;
  buildModel(*R, kstEpoch(2026, 11, 19, 13, 30), m);
  TEST_ASSERT_EQUAL('E', m.bld);
  TEST_ASSERT_EQUAL_UINT16(803, m.room);
  TEST_ASSERT_EQUAL_UINT8(1, m.unit);
  TEST_ASSERT_EQUAL_STRING("11.19", m.dateStr);
  TEST_ASSERT_EQUAL_UINT8(4, m.weekday);
}

void test_model_ignores_stale_rtc_day() {
  slotSet(1, 1, slot(4, 13, 0, 14, 50, "목요일 수업"));
  RenderModel m;
  // 금요일 13:30 — RTC 는 아직 목요일 슬롯(어댑터가 refreshDay 하기 전). 목요일 수업을 금요일에 보이면 안
  // 된다
  sch::LayoutDecision d = buildModel(*R, kstEpoch(2026, 11, 20, 13, 30), m);
  TEST_ASSERT_EQUAL_UINT8(LP_LAYOUT_EMPTY, d.layout);
  TEST_ASSERT_EQUAL_UINT8(0, m.nToday);
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_is_for_me);
  RUN_TEST(test_gap_rule_mod_255);
  RUN_TEST(test_today_of_is_kst_date);
  RUN_TEST(test_slot_set_ok_then_gap_then_dup);
  RUN_TEST(test_slot_set_other_day_goes_to_file_not_rtc);
  RUN_TEST(test_slot_set_same_key_replaces);
  RUN_TEST(test_store_fail_keeps_version_and_last_txn);
  RUN_TEST(test_file_write_failure_is_store_fail);
  RUN_TEST(test_retry_after_store_fail_is_not_dup);
  RUN_TEST(test_slot_del_and_day_clear);
  RUN_TEST(test_resv_and_exam);
  RUN_TEST(test_time_broadcast_sets_clock_without_ack);
  RUN_TEST(test_time_targeted_acks_and_skips_dup);
  RUN_TEST(test_no_ack_without_ack_req);
  RUN_TEST(test_bad_payload_and_unsupported);
  RUN_TEST(test_file_session_replaces_whole_kind);
  RUN_TEST(test_file_missing_reports_first_seq);
  RUN_TEST(test_file_bad_crc);
  RUN_TEST(test_day_cap_slot_set);
  RUN_TEST(test_day_cap_file_keeps_old);
  RUN_TEST(test_model_class_fills_cur_next_today);
  RUN_TEST(test_model_break_cur_is_next);
  RUN_TEST(test_model_resv_today_beats_slot);
  RUN_TEST(test_model_exam_period);
  RUN_TEST(test_today_merges_periods_of_same_section_only);
  RUN_TEST(test_today_merge_keeps_break_per_period);
  RUN_TEST(test_today_merge_rules_gap_type_and_contiguous);
  RUN_TEST(test_model_identity_from_rtc);
  RUN_TEST(test_model_ignores_stale_rtc_day);
  RUN_TEST(test_time_request_status_flag);
  RUN_TEST(test_cmd_request_status_acks_ok);
  RUN_TEST(test_status_flags);
  RUN_TEST(test_build_status_fields);
  RUN_TEST(test_build_ack_carries_ident_ver);
  RUN_TEST(test_next_daily_status);
  RUN_TEST(test_mac_spread_deterministic);
  RUN_TEST(test_status_plan_request_and_sent);
  RUN_TEST(test_status_plan_daily_and_wrap);
  RUN_TEST(test_status_plan_resends_after_time_when_stale_sent);
  RUN_TEST(test_status_plan_no_resend_without_stale);
  return UNITY_END();
}
