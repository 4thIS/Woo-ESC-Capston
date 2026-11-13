#include <unity.h>

#include <cstdint>
#include <vector>

#include "fake_store.h"
#include "store_port.h"

using ns::FakeFile;
using ns::FakeKv;
using ns::ReadResult;

void test_kv_get_missing_false() {
  FakeKv kv;
  uint32_t v = 123;
  TEST_ASSERT_FALSE(kv.get("ver", "schedVer", v));
  TEST_ASSERT_EQUAL_UINT32(123, v);  // 없으면 out 을 건드리지 않는다
}

void test_kv_set_get_roundtrip() {
  FakeKv kv;
  TEST_ASSERT_TRUE(kv.set("ver", "schedVer", 7));
  uint32_t v = 0;
  TEST_ASSERT_TRUE(kv.get("ver", "schedVer", v));
  TEST_ASSERT_EQUAL_UINT32(7, v);
}

// ESP-IDF NVS 키 상한 15자 [추정] — 16자는 거부, 최장 sessionWindowMs(15자)는 통과.
void test_kv_long_key_rejected() {
  FakeKv kv;
  TEST_ASSERT_FALSE(kv.set("cfg", "abcdefghijklmnop", 1));  // 16자
  uint32_t v = 0;
  TEST_ASSERT_FALSE(kv.get("cfg", "abcdefghijklmnop", v));
  TEST_ASSERT_TRUE(kv.set("cfg", "sessionWindowMs", 1));  // 15자
}

void test_kv_fail_injection() {
  FakeKv kv;
  TEST_ASSERT_TRUE(kv.set("ver", "schedVer", 5));
  kv.failSetsAfter = 0;
  TEST_ASSERT_FALSE(kv.set("ver", "schedVer", 9));
  uint32_t v = 0;
  TEST_ASSERT_TRUE(kv.get("ver", "schedVer", v));
  TEST_ASSERT_EQUAL_UINT32(5, v);  // 실패한 set 은 값을 바꾸지 않는다
}

void test_file_missing_notfound() {
  FakeFile f;
  uint8_t buf[8];
  size_t len = 99;
  TEST_ASSERT_EQUAL(static_cast<int>(ReadResult::NotFound),
                    static_cast<int>(f.read("/a", buf, sizeof(buf), len)));
}

void test_file_write_read_roundtrip() {
  FakeFile f;
  const uint8_t data[] = {1, 2, 3, 4};
  TEST_ASSERT_TRUE(f.writeAtomic("/a", data, sizeof(data)));
  uint8_t buf[8] = {};
  size_t len = 0;
  TEST_ASSERT_EQUAL(static_cast<int>(ReadResult::Ok), static_cast<int>(f.read("/a", buf, sizeof(buf), len)));
  TEST_ASSERT_EQUAL_UINT(4, len);
  TEST_ASSERT_EQUAL_UINT8_ARRAY(data, buf, 4);
}

// Review Focus 1 — 쓰기가 실패하면 옛 내용이 그대로여야 한다(원자 쓰기).
void test_file_write_fail_keeps_old() {
  FakeFile f;
  const uint8_t oldData[] = {1, 2, 3};
  TEST_ASSERT_TRUE(f.writeAtomic("/a", oldData, sizeof(oldData)));
  f.failWritesAfter = 0;
  const uint8_t newData[] = {9};
  TEST_ASSERT_FALSE(f.writeAtomic("/a", newData, sizeof(newData)));
  uint8_t buf[8] = {};
  size_t len = 0;
  TEST_ASSERT_EQUAL(static_cast<int>(ReadResult::Ok), static_cast<int>(f.read("/a", buf, sizeof(buf), len)));
  TEST_ASSERT_EQUAL_UINT(3, len);
  TEST_ASSERT_EQUAL_UINT8_ARRAY(oldData, buf, 3);
}

void test_file_read_over_cap_fail() {
  FakeFile f;
  const uint8_t data[] = {1, 2, 3, 4};
  TEST_ASSERT_TRUE(f.writeAtomic("/a", data, sizeof(data)));
  uint8_t buf[3];
  size_t len = 0;
  TEST_ASSERT_EQUAL(static_cast<int>(ReadResult::Fail),
                    static_cast<int>(f.read("/a", buf, sizeof(buf), len)));
}

void test_file_truncate() {
  FakeFile f;
  const uint8_t data[] = {1, 2, 3, 4, 5};
  TEST_ASSERT_TRUE(f.writeAtomic("/a", data, sizeof(data)));
  f.truncate("/a", 2);
  uint8_t buf[8] = {};
  size_t len = 0;
  TEST_ASSERT_EQUAL(static_cast<int>(ReadResult::Ok), static_cast<int>(f.read("/a", buf, sizeof(buf), len)));
  TEST_ASSERT_EQUAL_UINT(2, len);
  TEST_ASSERT_EQUAL_UINT8_ARRAY(data, buf, 2);
}

void test_file_remove_missing_true() {
  FakeFile f;
  TEST_ASSERT_TRUE(f.remove("/nope"));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_kv_get_missing_false);
  RUN_TEST(test_kv_set_get_roundtrip);
  RUN_TEST(test_kv_long_key_rejected);
  RUN_TEST(test_kv_fail_injection);
  RUN_TEST(test_file_missing_notfound);
  RUN_TEST(test_file_write_read_roundtrip);
  RUN_TEST(test_file_write_fail_keeps_old);
  RUN_TEST(test_file_read_over_cap_fail);
  RUN_TEST(test_file_truncate);
  RUN_TEST(test_file_remove_missing_true);
  return UNITY_END();
}
