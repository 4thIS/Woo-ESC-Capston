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

static void loadVectors() {
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

void setUp(void) {}
void tearDown(void) {}

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
  std::vector<uint8_t> f = fromHex(g_doc["vectors"][2]["frame_hex"]);  // slot_set_basic
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
  loadVectors();
  RUN_TEST(test_crc8_known);
  RUN_TEST(test_crc16_known);
  RUN_TEST(test_every_vector_header_decodes_and_reencodes);
  RUN_TEST(test_bad_frames_rejected);
  RUN_TEST(test_matches_ack);
  return UNITY_END();
}
