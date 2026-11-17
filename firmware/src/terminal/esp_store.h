// ns::KvStore·ns::FileStore 의 실기 어댑터 — NVS(Preferences)·LittleFS. 계약은 lib/node_store/store_port.h,
// 동작 기준은 fake_store.h(테스트 fake)와 같다.
#pragma once

#include <LittleFS.h>
#include <Preferences.h>

#include "store_port.h"

class EspKv : public ns::KvStore {
 public:
  bool get(const char* space, const char* key, uint32_t& out) override {
    Preferences p;
    if (!p.begin(space, true)) return false;  // 이름공간이 아직 없으면 false — "없음"과 같다
    const bool has = p.isKey(key);
    if (has) out = p.getUInt(key, 0);
    p.end();
    return has;
  }
  bool set(const char* space, const char* key, uint32_t v) override {
    Preferences p;
    if (!p.begin(space, false)) return false;
    const bool ok = p.putUInt(key, v) == sizeof(uint32_t);
    p.end();
    return ok;
  }
  bool eraseSpace(const char* space) override {
    Preferences p;
    if (!p.begin(space, false)) return false;
    const bool ok = p.clear();
    p.end();
    return ok;
  }
};

class LittleFsFiles : public ns::FileStore {
 public:
  ns::ReadResult read(const char* path, uint8_t* buf, size_t cap, size_t& len) override {
    if (!LittleFS.exists(path)) return ns::ReadResult::NotFound;
    File f = LittleFS.open(path, "r");
    if (!f) return ns::ReadResult::Fail;
    const size_t sz = f.size();
    if (sz > cap) {
      f.close();
      return ns::ReadResult::Fail;
    }
    len = f.read(buf, sz);
    f.close();
    return len == sz ? ns::ReadResult::Ok : ns::ReadResult::Fail;
  }
  // 임시 파일에 쓰고 rename — 중간에 끊기면 옛 파일이 그대로 남는다(LittleFS rename 은 대상을 덮는다)
  bool writeAtomic(const char* path, const uint8_t* data, size_t len) override {
    char tmp[40];
    snprintf(tmp, sizeof tmp, "%s.tmp", path);
    File f = LittleFS.open(tmp, "w");
    if (!f) return false;
    const bool ok = f.write(data, len) == len;
    f.close();
    return ok && LittleFS.rename(tmp, path);
  }
  bool remove(const char* path) override { return !LittleFS.exists(path) || LittleFS.remove(path); }
};
