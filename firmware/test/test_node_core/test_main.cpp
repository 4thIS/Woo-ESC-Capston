// S8 노드 순수 로직 — 판정은 lora_proto/room_state_vectors.json(서버 room_state 와 같은 파일), 수신은 v2
// §3.4·3.5·6.4·6.6.
#include <ArduinoJson.h>
#include <unity.h>

#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "lora_codec.h"
#include "node_core.h"

using namespace nc;

static const Ident ME{'E', 301, 1};
static State* S;
static FileRx* F;

void setUp() {
  S = new State();
  F = new FileRx();
  clear(*S);
}
void tearDown() {
  delete S;
  delete F;
}

// ---------------- 프레임 도우미 ----------------
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
  return handleFrame(*S, *F, h, g_pl);
}

static lc::SlotRec slot(uint8_t day, uint8_t sH, uint8_t sM, uint8_t eH, uint8_t eM, const char* subj,
                        uint8_t type = LP_SLOTTYPE_CLASS) {
  lc::SlotRec s{};
  s.day = day, s.sH = sH, s.sM = sM, s.eH = eH, s.eM = eM, s.type = type;
  strncpy(s.subj, subj, LP_SUBJ_MAX);
  strncpy(s.prof, "교수", LP_PROF_MAX);
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
void test_slot_set_ok_then_gap_then_dup() {
  Outcome o = slotSet(10, 1, slot(1, 9, 0, 9, 50, "자료구조"));
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, o.status);
  TEST_ASSERT_TRUE(o.changed);
  TEST_ASSERT_EQUAL_UINT8(1, S->nSlots);
  TEST_ASSERT_EQUAL_UINT8(1, S->schedVer);
  TEST_ASSERT_EQUAL_UINT8(10, S->lastTxn);

  o = slotSet(11, 3, slot(1, 10, 0, 10, 50, "자료구조"));
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_GAP, o.status);  // 2 를 건너뜀 — 적용은 하고 GAP
  TEST_ASSERT_EQUAL_UINT8(2, S->nSlots);
  TEST_ASSERT_EQUAL_UINT8(11, S->lastTxn);  // GAP 도 저장 OK 라 lastTxn 기록(#74 10)

  o = slotSet(11, 3, slot(1, 10, 0, 10, 50, "자료구조"));
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_DUP, o.status);
  TEST_ASSERT_FALSE(o.changed);
}

void test_slot_set_same_key_replaces() {
  slotSet(1, 1, slot(1, 9, 0, 9, 50, "자료구조"));
  slotSet(2, 2, slot(1, 9, 0, 9, 50, "운영체제"));
  TEST_ASSERT_EQUAL_UINT8(1, S->nSlots);
  TEST_ASSERT_EQUAL_STRING("운영체제", S->slots[0].subj);
}

void test_store_fail_when_full_keeps_last_txn() {
  for (int i = 0; i < LP_SLOT_WEEK_MAX; ++i) {
    S->slots[i] = slot((uint8_t)(i % 7 + 1), (uint8_t)(i / 7), 0, (uint8_t)(i / 7), 50, "x");
  }
  S->nSlots = LP_SLOT_WEEK_MAX;
  S->lastTxn = 5;
  Outcome o = slotSet(6, 1, slot(7, 23, 10, 23, 50, "넘침"));
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_STORE_FAIL, o.status);
  TEST_ASSERT_EQUAL_UINT8(
      5, S->lastTxn);  // 실패는 기록하지 않는다 — 같은 TXN 재송이 DUP 으로 성공 처리되지 않게
  TEST_ASSERT_EQUAL_UINT8(0, S->schedVer);
}

void test_slot_del_and_day_clear() {
  slotSet(1, 1, slot(1, 9, 0, 9, 50, "a"));
  slotSet(2, 2, slot(1, 10, 0, 10, 50, "b"));
  slotSet(3, 3, slot(2, 9, 0, 9, 50, "c"));
  lc::SlotDel d{1, 9, 0};
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK,
                         run(hdr(LP_TYPE_SLOT_DEL, 4), lc::encSlotDel(4, d, g_pl, sizeof g_pl)).status);
  TEST_ASSERT_EQUAL_UINT8(2, S->nSlots);
  lc::DayClear c{1};
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK,
                         run(hdr(LP_TYPE_DAY_CLEAR, 5), lc::encDayClear(5, c, g_pl, sizeof g_pl)).status);
  TEST_ASSERT_EQUAL_UINT8(1, S->nSlots);
  TEST_ASSERT_EQUAL_UINT8(2, S->slots[0].day);
}

void test_resv_and_exam() {
  lc::ResvRec r{};
  r.resvId = 77, r.y = 26, r.m = 11, r.d = 19, r.sH = 15, r.eH = 17, r.type = LP_SLOTTYPE_RENTAL;
  strcpy(r.subj, "스터디");
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK,
                         run(hdr(LP_TYPE_RESV_SET, 1), lc::encResvSet(1, r, g_pl, sizeof g_pl)).status);
  TEST_ASSERT_EQUAL_UINT8(1, S->nResv);
  lc::ResvDel rd{77};
  run(hdr(LP_TYPE_RESV_DEL, 2), lc::encResvDel(2, rd, g_pl, sizeof g_pl));
  TEST_ASSERT_EQUAL_UINT8(0, S->nResv);
  TEST_ASSERT_EQUAL_UINT8(2, S->resvVer);
  lc::ExamRec e{5, 26, 11, 16, 26, 11, 20};
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK,
                         run(hdr(LP_TYPE_EXAM_SET, 3), lc::encExamSet(1, e, g_pl, sizeof g_pl)).status);
  TEST_ASSERT_EQUAL_UINT8(1, S->nExam);
  TEST_ASSERT_EQUAL_UINT8(1, S->examVer);
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
  S->lastTxn = 0;
  lc::Time t{1793156768, 0};
  Outcome o = run(hdr(LP_TYPE_TIME, 0), lc::encTime(t, g_pl, sizeof g_pl));
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, o.status);  // txn 0 이어도 DUP 아님(§3.5)
  TEST_ASSERT_TRUE(o.timeSet);
}

void test_no_ack_without_ack_req() {
  Outcome o =
      run(hdr(LP_TYPE_SLOT_SET, 9, 0), lc::encSlotSet(1, slot(1, 9, 0, 9, 50, "a"), g_pl, sizeof g_pl));
  TEST_ASSERT_EQUAL_HEX8(kNoAck, o.status);
  TEST_ASSERT_EQUAL_UINT8(1, S->nSlots);  // 적용은 한다
}

void test_bad_payload_and_unsupported() {
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_BAD_PAYLOAD, run(hdr(LP_TYPE_SLOT_SET, 1), 2).status);
  lc::CmdMsg c{1, nullptr, 0};
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_UNSUPPORTED,
                         run(hdr(LP_TYPE_CMD, 2), lc::encCmd(c, g_pl, sizeof g_pl)).status);
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

void test_file_session_replaces_whole_kind() {
  slotSet(1, 1, slot(7, 9, 0, 9, 50, "지워질 것"));
  auto body = scheduleBody(60);  // 200 B 청크 여러 개
  Outcome end;
  fileSession(body, 9, 20, -1, end);
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, end.status);
  TEST_ASSERT_TRUE(end.changed);
  TEST_ASSERT_EQUAL_UINT8(60, S->nSlots);
  TEST_ASSERT_EQUAL_UINT8(9, S->schedVer);
}

void test_file_missing_reports_first_seq() {
  auto body = scheduleBody(30);
  Outcome end;
  fileSession(body, 4, 50, 2, end);
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_FILE_MISSING, end.status);
  TEST_ASSERT_EQUAL_UINT8(2, end.detail);
  TEST_ASSERT_EQUAL_UINT8(0, S->schedVer);
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

// 하루 상한 LP_SLOT_DAY_MAX(v2 §5.1·§12) — 주간 합계가 96 이하여도 한 요일 25번째는 STORE_FAIL
void test_day_cap_slot_set() {
  for (int i = 0; i < LP_SLOT_DAY_MAX; ++i) S->slots[i] = slot(2, (uint8_t)i, 0, (uint8_t)i, 50, "x");
  S->nSlots = LP_SLOT_DAY_MAX;
  S->lastTxn = 5;
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_STORE_FAIL, slotSet(6, 1, slot(2, 23, 55, 23, 59, "넘침")).status);
  TEST_ASSERT_EQUAL_UINT8(LP_SLOT_DAY_MAX, S->nSlots);
  TEST_ASSERT_EQUAL_UINT8(5, S->lastTxn);
  // 이미 있는 키는 교체라 OK, 다른 요일은 여유가 있으니 OK
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, slotSet(7, 1, slot(2, 3, 0, 3, 50, "교체")).status);
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_OK, slotSet(8, 2, slot(3, 9, 0, 9, 50, "수요일")).status);
  TEST_ASSERT_EQUAL_UINT8(LP_SLOT_DAY_MAX + 1, S->nSlots);
}

void test_day_cap_file_keeps_old() {
  slotSet(1, 1, slot(1, 9, 0, 9, 50, "그대로"));
  auto body = dayBody(LP_SLOT_DAY_MAX + 1, 2);
  Outcome end;
  fileSession(body, 9, 20, -1, end);
  TEST_ASSERT_EQUAL_HEX8(LP_ACK_STORE_FAIL, end.status);
  TEST_ASSERT_EQUAL_UINT8(1, S->nSlots);
  TEST_ASSERT_EQUAL_UINT8(1, S->schedVer);
}

// ---------------- 판정 벡터 §5.3 ----------------
void test_room_state_vectors() {
  FILE* f = fopen("../lora_proto/room_state_vectors.json", "rb");
  TEST_ASSERT_NOT_NULL(f);
  std::string s;
  char buf[4096];
  size_t k;
  while ((k = fread(buf, 1, sizeof buf, f)) > 0) s.append(buf, k);
  fclose(f);
  JsonDocument doc;
  TEST_ASSERT_TRUE(deserializeJson(doc, s) == DeserializationError::Ok);
  int checked = 0;
  for (JsonObject v : doc["vectors"].as<JsonArray>()) {
    std::vector<Item> items;
    uint8_t i = 0;
    for (JsonObject sl : doc["slots"].as<JsonArray>())
      items.push_back({(uint16_t)sl["s"], (uint16_t)sl["e"], (uint8_t)sl["type"], false, i++});
    i = 0;
    for (JsonObject r : v["resvs"].as<JsonArray>())
      items.push_back({(uint16_t)r["s"], (uint16_t)r["e"], (uint8_t)r["type"], true, i++});
    Decision d = decide(items.data(), (int)items.size(), v["in_exam"], (uint16_t)v["at"]);
    const char* name = v["name"];
    TEST_ASSERT_EQUAL_UINT8_MESSAGE((uint8_t)v["layout"], d.layout, name);
    int until = v["until"].isNull() ? -1 : (int)v["until"];
    TEST_ASSERT_EQUAL_INT_MESSAGE(until, d.until, name);
    ++checked;
  }
  TEST_ASSERT_TRUE(checked >= 20);
}

// ---------------- 화면 모델 ----------------
static uint32_t kstEpoch(int y, int mo, int d, int h, int mi) {  // 그 KST 시각의 UTC epoch
  // 2026-11-19(목) 00:00 KST = 2026-11-18 15:00 UTC = 1795014000
  (void)y, (void)mo;
  return 1795014000u + (uint32_t)(d - 19) * 86400u + (uint32_t)(h * 3600 + mi * 60);
}

void test_kst_conversion() {
  Kst k = toKst(kstEpoch(2026, 11, 19, 13, 5));
  TEST_ASSERT_EQUAL_UINT8(26, k.y2k);
  TEST_ASSERT_EQUAL_UINT8(11, k.mon);
  TEST_ASSERT_EQUAL_UINT8(19, k.mday);
  TEST_ASSERT_EQUAL_UINT8(4, k.wday);  // 목
  TEST_ASSERT_EQUAL_UINT16(13 * 60 + 5, k.min);
}

void test_model_class_fills_cur_next_today() {
  slotSet(1, 1, slot(4, 9, 0, 10, 50, "자료구조"));
  slotSet(2, 2, slot(4, 13, 0, 14, 50, "임베디드SW"));
  slotSet(3, 3, slot(4, 16, 0, 18, 50, "캡스톤디자인"));
  slotSet(4, 4, slot(3, 13, 0, 14, 50, "다른 요일"));
  RenderModel m;
  Decision d = buildModel(ME, *S, kstEpoch(2026, 11, 19, 13, 30), m);
  TEST_ASSERT_EQUAL_UINT8(LP_LAYOUT_CLASS, m.layout);
  TEST_ASSERT_EQUAL_INT16(14 * 60 + 50, d.until);
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
  buildModel(ME, *S, kstEpoch(2026, 11, 19, 9, 55), m);
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
  buildModel(ME, *S, kstEpoch(2026, 11, 19, 15, 30), m);
  TEST_ASSERT_EQUAL_UINT8(LP_LAYOUT_RENTAL, m.layout);
  TEST_ASSERT_EQUAL_STRING("스터디", m.cur.subj);
  buildModel(ME, *S, kstEpoch(2026, 11, 20, 15, 30), m);  // 다음날(금)은 예약 없음·정규도 없음
  TEST_ASSERT_EQUAL_UINT8(LP_LAYOUT_EMPTY, m.layout);
}

void test_model_exam_period() {
  slotSet(1, 1, slot(4, 9, 0, 9, 50, "자료구조"));
  lc::ExamRec e{5, 26, 11, 16, 26, 11, 20};
  run(hdr(LP_TYPE_EXAM_SET, 2), lc::encExamSet(1, e, g_pl, sizeof g_pl));
  RenderModel m;
  buildModel(ME, *S, kstEpoch(2026, 11, 19, 9, 10), m);
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
  buildModel(ME, *S, kstEpoch(2026, 11, 19, 10, 20), m);
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
  buildModel(ME, *S, kstEpoch(2026, 11, 19, 10, 55), m);  // 102반 2·3교시 사이 쉬는시간
  TEST_ASSERT_EQUAL_UINT8(LP_LAYOUT_BREAK, m.layout);
  TEST_ASSERT_EQUAL_UINT8(11, m.cur.sH);  // cur = 곧 시작할 교시
  TEST_ASSERT_EQUAL_UINT8(2, m.nToday);
  buildModel(ME, *S, kstEpoch(2026, 11, 19, 11, 55), m);  // 반이 바뀌는 틈도 쉬는시간(과목·교수 같음)
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
  buildModel(ME, *S, kstEpoch(2026, 11, 19, 8, 0), m);
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

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_is_for_me);
  RUN_TEST(test_gap_rule_mod_255);
  RUN_TEST(test_slot_set_ok_then_gap_then_dup);
  RUN_TEST(test_slot_set_same_key_replaces);
  RUN_TEST(test_store_fail_when_full_keeps_last_txn);
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
  RUN_TEST(test_room_state_vectors);
  RUN_TEST(test_kst_conversion);
  RUN_TEST(test_model_class_fills_cur_next_today);
  RUN_TEST(test_model_break_cur_is_next);
  RUN_TEST(test_model_resv_today_beats_slot);
  RUN_TEST(test_model_exam_period);
  RUN_TEST(test_today_merges_periods_of_same_section_only);
  RUN_TEST(test_today_merge_keeps_break_per_period);
  RUN_TEST(test_today_merge_rules_gap_type_and_contiguous);
  return UNITY_END();
}
