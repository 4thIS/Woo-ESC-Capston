#include <ArduinoJson.h>
#include <unity.h>

#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "lora_codec.h"
#include "vectors_path.h"

static JsonDocument g_doc;

static std::vector<uint8_t> fromHex(const char* s) {
  std::vector<uint8_t> out;
  unsigned v;
  while (*s) {
    if (*s == ' ') {
      ++s;
      continue;
    }
    if (sscanf(s, "%2x", &v) != 1) break;
    out.push_back((uint8_t)v);
    s += 2;
  }
  return out;
}

void test_load_vectors() {
  FILE* f = fopen(LC_VECTORS_PATH, "rb");
  TEST_ASSERT_NOT_NULL_MESSAGE(
      f, "test_vectors.json 열기 실패 — lora_proto/ 에서 uv run python -m tools.gen_vectors");
  std::string s;
  char buf[4096];
  size_t n;
  while ((n = fread(buf, 1, sizeof buf, f)) > 0) s.append(buf, n);
  fclose(f);
  TEST_ASSERT_TRUE_MESSAGE(deserializeJson(g_doc, s) == DeserializationError::Ok, "JSON 파싱 실패");
}

// g_doc["vectors"] 를 이름으로 찾는다. 인덱스 고정 참조 대신 이걸 쓰면 벡터셋 순서가 바뀌어도 안전하다.
static JsonObject findVector(const char* name) {
  for (JsonObject v : g_doc["vectors"].as<JsonArray>()) {
    if (strcmp(v["name"], name) == 0) return v;
  }
  TEST_FAIL_MESSAGE(name);
  return JsonObject();
}

void setUp(void) {}
void tearDown(void) {}

static void expectStr(const char* name, const char* expect, const char* got) {
  TEST_ASSERT_EQUAL_STRING_MESSAGE(expect, got, name);
}

static void checkSlot(const char* name, JsonObject j, const lc::SlotRec& s) {
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["day"], s.day, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["s_h"], s.sH, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["s_m"], s.sM, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["e_h"], s.eH, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["e_m"], s.eM, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["type"], s.type, name);
  expectStr(name, j["subject"], s.subj);
  expectStr(name, j["professor"], s.prof);
}

static void checkResv(const char* name, JsonObject j, const lc::ResvRec& r) {
  TEST_ASSERT_EQUAL_UINT16_MESSAGE(j["resv_id"], r.resvId, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE((int)j["year"] - 2000, r.y, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["month"], r.m, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["day"], r.d, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["s_h"], r.sH, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["e_m"], r.eM, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["type"], r.type, name);
  expectStr(name, j["subject"], r.subj);
  expectStr(name, j["professor"], r.prof);
}

static void checkAck(const char* name, JsonObject j, const lc::Ack& a) {
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["status"], a.status, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["detail"], a.detail, name);
  TEST_ASSERT_EQUAL_UINT16_MESSAGE(j["batt_mv"], a.battMv, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["sched_ver"], a.schedVer, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["resv_ver"], a.resvVer, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["exam_ver"], a.examVer, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["ident_ver"], a.identVer, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["fw"], a.fw, name);
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["layout"], a.layout, name);
}

static void checkMac(const char* name, const char* hex, const uint8_t* mac) {
  std::vector<uint8_t> m = fromHex(hex);
  TEST_ASSERT_EQUAL_HEX8_ARRAY_MESSAGE(m.data(), mac, 6, name);
}

// 각 벡터: 디코드 → JSON 필드 대조 → 재인코딩 → 원 페이로드 바이트와 대조
void test_every_vector_payload_decodes_and_reencodes() {
  if (g_doc["vectors"].isNull()) TEST_FAIL_MESSAGE("vectors not loaded");
  for (JsonObject v : g_doc["vectors"].as<JsonArray>()) {
    const char* name = v["name"];
    std::vector<uint8_t> frame = fromHex(v["frame_hex"]);
    lc::Header h;
    const uint8_t* pl;
    TEST_ASSERT_TRUE(lc::decodeFrame(frame.data(), frame.size(), h, pl));
    JsonObject j = v["payload"];
    uint8_t out[LP_MAX_PAYLOAD];
    size_t n = 0;
    uint8_t nv = 0;
    switch (h.type) {
      case LP_TYPE_TIME: {
        lc::Time t;
        TEST_ASSERT_TRUE_MESSAGE(lc::decTime(pl, h.len, t), name);
        TEST_ASSERT_EQUAL_UINT32_MESSAGE(j["epoch"], t.epoch, name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["flags"], t.flags, name);
        n = lc::encTime(t, out, sizeof out);
        break;
      }
      case LP_TYPE_SLOT_SET: {
        lc::SlotRec s;
        TEST_ASSERT_TRUE_MESSAGE(lc::decSlotSet(pl, h.len, nv, s), name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["new_ver"], nv, name);
        checkSlot(name, j, s);
        n = lc::encSlotSet(nv, s, out, sizeof out);
        break;
      }
      case LP_TYPE_SLOT_DEL: {
        lc::SlotDel s;
        TEST_ASSERT_TRUE_MESSAGE(lc::decSlotDel(pl, h.len, nv, s), name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["day"], s.day, name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["s_m"], s.sM, name);
        n = lc::encSlotDel(nv, s, out, sizeof out);
        break;
      }
      case LP_TYPE_DAY_CLEAR: {
        lc::DayClear d;
        TEST_ASSERT_TRUE_MESSAGE(lc::decDayClear(pl, h.len, nv, d), name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["day"], d.day, name);
        n = lc::encDayClear(nv, d, out, sizeof out);
        break;
      }
      case LP_TYPE_RESV_SET: {
        lc::ResvRec r;
        TEST_ASSERT_TRUE_MESSAGE(lc::decResvSet(pl, h.len, nv, r), name);
        checkResv(name, j, r);
        n = lc::encResvSet(nv, r, out, sizeof out);
        break;
      }
      case LP_TYPE_RESV_DEL: {
        lc::ResvDel r;
        TEST_ASSERT_TRUE_MESSAGE(lc::decResvDel(pl, h.len, nv, r), name);
        TEST_ASSERT_EQUAL_UINT16_MESSAGE(j["resv_id"], r.resvId, name);
        n = lc::encResvDel(nv, r, out, sizeof out);
        break;
      }
      case LP_TYPE_EXAM_SET: {
        lc::ExamRec e;
        TEST_ASSERT_TRUE_MESSAGE(lc::decExamSet(pl, h.len, nv, e), name);
        TEST_ASSERT_EQUAL_UINT16_MESSAGE(j["exam_id"], e.examId, name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE((int)j["y2"] - 2000, e.y2, name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["d2"], e.d2, name);
        n = lc::encExamSet(nv, e, out, sizeof out);
        break;
      }
      case LP_TYPE_EXAM_DEL: {
        lc::ExamDel e;
        TEST_ASSERT_TRUE_MESSAGE(lc::decExamDel(pl, h.len, nv, e), name);
        TEST_ASSERT_EQUAL_UINT16_MESSAGE(j["exam_id"], e.examId, name);
        n = lc::encExamDel(nv, e, out, sizeof out);
        break;
      }
      case LP_TYPE_FILE_BEGIN: {
        lc::FileBegin f;
        TEST_ASSERT_TRUE_MESSAGE(lc::decFileBegin(pl, h.len, nv, f), name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["kind"], f.kind, name);
        TEST_ASSERT_EQUAL_UINT16_MESSAGE(j["total_len"], f.totalLen, name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["n_chunks"], f.nChunks, name);
        n = lc::encFileBegin(nv, f, out, sizeof out);
        break;
      }
      case LP_TYPE_FILE_DATA: {
        lc::FileData f;
        TEST_ASSERT_TRUE_MESSAGE(lc::decFileData(pl, h.len, f), name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["seq"], f.seq, name);
        std::vector<uint8_t> d = fromHex(j["data"]);
        TEST_ASSERT_EQUAL_MESSAGE(d.size(), f.len, name);
        TEST_ASSERT_EQUAL_HEX8_ARRAY_MESSAGE(d.data(), f.data, d.size(), name);
        n = lc::encFileData(f, out, sizeof out);
        break;
      }
      case LP_TYPE_FILE_END: {
        lc::FileEnd f;
        TEST_ASSERT_TRUE_MESSAGE(lc::decFileEnd(pl, h.len, f), name);
        TEST_ASSERT_EQUAL_UINT16_MESSAGE(j["crc16"], f.crc, name);
        n = lc::encFileEnd(f, out, sizeof out);
        break;
      }
      case LP_TYPE_CMD: {
        lc::CmdMsg c;
        TEST_ASSERT_TRUE_MESSAGE(lc::decCmd(pl, h.len, c), name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["cmd"], c.cmd, name);
        std::vector<uint8_t> a = fromHex(j["args"]);
        TEST_ASSERT_EQUAL_MESSAGE(a.size(), c.argsLen, name);
        n = lc::encCmd(c, out, sizeof out);
        break;
      }
      case LP_TYPE_SET_ROOM: {
        lc::SetRoom s;
        TEST_ASSERT_TRUE_MESSAGE(lc::decSetRoom(pl, h.len, nv, s), name);
        checkMac(name, j["mac"], s.mac);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["bld"], s.bld, name);
        TEST_ASSERT_EQUAL_UINT16_MESSAGE(j["room"], s.room, name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["unit"], s.unit, name);
        n = lc::encSetRoom(nv, s, out, sizeof out);
        break;
      }
      case LP_TYPE_ACK: {
        lc::Ack a;
        TEST_ASSERT_TRUE_MESSAGE(lc::decAck(pl, h.len, a), name);
        checkAck(name, j, a);
        n = lc::encAck(a, out, sizeof out);
        break;
      }
      case LP_TYPE_STATUS: {
        lc::Status s;
        TEST_ASSERT_TRUE_MESSAGE(lc::decStatus(pl, h.len, s), name);
        checkAck(name, j["ack"], s.ack);
        TEST_ASSERT_EQUAL_INT8_MESSAGE(j["rssi_last"], s.rssiLast, name);
        TEST_ASSERT_EQUAL_INT8_MESSAGE(j["snr_last_x4"], s.snrLastX4, name);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["flags"], s.flags, name);
        TEST_ASSERT_EQUAL_UINT16_MESSAGE(j["uptime_h"], s.uptimeH, name);
        n = lc::encStatus(s, out, sizeof out);
        break;
      }
      case LP_TYPE_HELLO: {
        lc::Hello hl;
        TEST_ASSERT_TRUE_MESSAGE(lc::decHello(pl, h.len, hl), name);
        checkMac(name, j["mac"], hl.mac);
        TEST_ASSERT_EQUAL_UINT8_MESSAGE(j["fw"], hl.fw, name);
        TEST_ASSERT_EQUAL_UINT16_MESSAGE(j["batt_mv"], hl.battMv, name);
        n = lc::encHello(hl, out, sizeof out);
        break;
      }
      default:
        TEST_FAIL_MESSAGE(name);
    }
    TEST_ASSERT_EQUAL_MESSAGE(h.len, n, name);
    TEST_ASSERT_EQUAL_HEX8_ARRAY_MESSAGE(pl, out, n, name);
  }
}

void test_string_over_limit_rejected() {
  // 구조체 버퍼(LP_SUBJ_MAX+1)에는 21 B 를 담을 수 없으므로 디코더 쪽 한계만 검사: subjLen=21 인 바이트열
  uint8_t bad[] = {1,   3,   9,   0,   10,  0,   1,   21,  'a', 'a', 'a', 'a', 'a', 'a', 'a', 'a',
                   'a', 'a', 'a', 'a', 'a', 'a', 'a', 'a', 'a', 'a', 'a', 'a', 'a', 1,   'p'};
  uint8_t nv;
  lc::SlotRec d;
  TEST_ASSERT_FALSE(lc::decSlotSet(bad, sizeof bad, nv, d));
  // 인코더 쪽: 범위 밖 필드(day=8)는 0 을 돌려준다
  lc::SlotRec s{8, 9, 0, 10, 0, 1, "s", "p"};
  uint8_t out[LP_MAX_PAYLOAD];
  TEST_ASSERT_EQUAL(0, lc::encSlotSet(1, s, out, sizeof out));
}

void test_file_records_iterate() {
  // file_data_seq0_full_200B 는 file_begin_schedule_3chunks(total_len=504, n_chunks=3)의 첫 청크(200 B,
  // LP_FILE_CHUNK_MAX 로 잘림)다. 42 B 레코드가 4개(168 B) 온전히 들어가고, 5번째 레코드(day=5)는 헤더(2 B)
  // + 30 B만 이 청크에 있고 나머지 10 B는 다음 청크(seq1, 본 벡터셋에 없음)에 있다 — 즉 청크 경계에서 잘린다.
  // nextRecord 는 이 절단을 형식 오류로 보고 false + pos=n 을 반환해야 한다(완전히 재조립된 body에서만
  // 호출하는 것이 정상 사용법이며, 청크 단위 파싱은 지원 대상이 아니다).
  if (g_doc["vectors"].isNull()) TEST_FAIL_MESSAGE("vectors not loaded");
  JsonObject v = findVector("file_data_seq0_full_200B");
  std::vector<uint8_t> body = fromHex(v["payload"]["data"]);
  uint16_t pos = 0;
  uint8_t rt;
  const uint8_t* rec;
  uint8_t rl;
  int count = 0;
  while (lc::nextRecord(body.data(), (uint16_t)body.size(), pos, rt, rec, rl)) {
    TEST_ASSERT_EQUAL_UINT8(LP_TYPE_SLOT_SET, rt);
    lc::SlotRec s;
    TEST_ASSERT_TRUE(lc::decSlotBody(rec, rl, s));
    TEST_ASSERT_EQUAL_UINT8(1 + count % 7, s.day);
    ++count;
  }
  TEST_ASSERT_EQUAL(4, count);
  TEST_ASSERT_EQUAL(body.size(), pos);
}

void test_crc8_known() {
  const uint8_t d[] = "123456789";
  TEST_ASSERT_EQUAL_HEX8(0xF4, lc::crc8(d, 9));
  TEST_ASSERT_EQUAL_HEX8(0x00, lc::crc8(d, 0));
}

void test_crc16_known() {
  const uint8_t d[] = "123456789";
  TEST_ASSERT_EQUAL_HEX16(0x29B1, lc::crc16(d, 9));
  TEST_ASSERT_EQUAL_HEX16(0xFFFF, lc::crc16(d, 0));
}

void test_every_vector_header_decodes_and_reencodes() {
  if (g_doc["vectors"].isNull()) TEST_FAIL_MESSAGE("vectors not loaded");
  for (JsonObject v : g_doc["vectors"].as<JsonArray>()) {
    const char* name = v["name"];
    std::vector<uint8_t> frame = fromHex(v["frame_hex"]);
    lc::Header h;
    const uint8_t* pl = nullptr;
    TEST_ASSERT_TRUE_MESSAGE(lc::decodeFrame(frame.data(), frame.size(), h, pl), name);
    JsonObject jh = v["header"];
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(jh["type"], h.type, name);
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(jh["bld"], h.bld, name);
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(jh["room"], h.room, name);
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(jh["unit"], h.unit, name);
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(jh["txn"], h.txn, name);
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(jh["flags"], h.flags, name);
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(LP_PROTO_VER, h.ver, name);
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(RP_NET_ID, h.netId, name);
    uint8_t out[LP_MAX_FRAME];
    size_t n = lc::encodeFrame(h, pl, h.len, out, sizeof out);
    TEST_ASSERT_EQUAL_MESSAGE(frame.size(), n, name);
    TEST_ASSERT_EQUAL_HEX8_ARRAY_MESSAGE(frame.data(), out, n, name);
  }
}

void test_bad_frames_rejected() {
  if (g_doc["vectors"].isNull()) TEST_FAIL_MESSAGE("vectors not loaded");
  std::vector<uint8_t> f = fromHex(findVector("slot_set_basic")["frame_hex"]);
  lc::Header h;
  const uint8_t* pl;
  std::vector<uint8_t> a = f;
  a.back() ^= 0xFF;  // CRC
  TEST_ASSERT_FALSE(lc::decodeFrame(a.data(), a.size(), h, pl));
  std::vector<uint8_t> b = f;
  b[1] = 0x00;  // NET_ID
  TEST_ASSERT_FALSE(lc::decodeFrame(b.data(), b.size(), h, pl));
  std::vector<uint8_t> c = f;
  c[0] = 0x31;  // ver 3
  TEST_ASSERT_FALSE(lc::decodeFrame(c.data(), c.size(), h, pl));
  std::vector<uint8_t> d = f;
  d[8] = 9;  // LEN 불일치
  TEST_ASSERT_FALSE(lc::decodeFrame(d.data(), d.size(), h, pl));
  TEST_ASSERT_FALSE(lc::decodeFrame(f.data(), 5, h, pl));  // 짧음
}

void test_len_over_max_payload_rejected() {
  // 9-B 헤더 + LEN=246(LP_MAX_PAYLOAD=245 초과) + 246 B 페이로드 + 유효 CRC8
  std::vector<uint8_t> f(9 + 246 + 1, 0);
  f[0] = (uint8_t)(LP_PROTO_VER << 4);  // flags=0
  f[1] = RP_NET_ID;
  f[2] = LP_TYPE_TIME;
  f[3] = 0;    // bld
  f[4] = 0;    // room hi
  f[5] = 0;    // room lo
  f[6] = 0;    // unit
  f[7] = 1;    // txn
  f[8] = 246;  // LEN
  f.back() = lc::crc8(f.data(), f.size() - 1);
  lc::Header h;
  const uint8_t* pl;
  TEST_ASSERT_FALSE(lc::decodeFrame(f.data(), f.size(), h, pl));
}

void test_matches_ack() {
  lc::Header req{LP_PROTO_VER, LP_FLAG_ACK_REQ, RP_NET_ID, LP_TYPE_SLOT_SET, 'E', 301, 1, 7, 0};
  lc::Header ack{LP_PROTO_VER, 0, RP_NET_ID, LP_TYPE_ACK, 'E', 301, 1, 7, 0};
  TEST_ASSERT_TRUE(lc::matchesAck(req, ack));
  ack.txn = 8;
  TEST_ASSERT_FALSE(lc::matchesAck(req, ack));
  ack.txn = 7;
  ack.type = LP_TYPE_STATUS;
  TEST_ASSERT_FALSE(lc::matchesAck(req, ack));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_load_vectors);
  RUN_TEST(test_crc8_known);
  RUN_TEST(test_crc16_known);
  RUN_TEST(test_every_vector_header_decodes_and_reencodes);
  RUN_TEST(test_bad_frames_rejected);
  RUN_TEST(test_matches_ack);
  RUN_TEST(test_every_vector_payload_decodes_and_reencodes);
  RUN_TEST(test_string_over_limit_rejected);
  RUN_TEST(test_file_records_iterate);
  RUN_TEST(test_len_over_max_payload_rejected);
  return UNITY_END();
}
