// 테스트용 메모리 fake. 실패 주입(failSetsAfter·failWritesAfter)과 파일 손상(truncate·putRaw)을 지원한다.
#pragma once

#include <algorithm>
#include <cstring>
#include <map>
#include <string>
#include <utility>
#include <vector>

#include "store_port.h"

namespace ns {

class FakeKv : public KvStore {
 public:
  int failSetsAfter = -1;  // n번째 set부터 실패(0 = 다음 set), -1 = 안 함

  bool get(const char* space, const char* key, uint32_t& out) override {
    auto it = map_.find(compose(space, key));
    if (it == map_.end()) return false;
    out = it->second;
    return true;
  }

  bool set(const char* space, const char* key, uint32_t v) override {
    // ESP-IDF NVS 키 상한 15자 [추정] — 실기 어댑터 작성 때 문서로 확인한다.
    if (std::strlen(key) > kMaxKeyLen) return false;
    if (failSetsAfter == 0) return false;
    if (failSetsAfter > 0) --failSetsAfter;
    map_[compose(space, key)] = v;
    return true;
  }

  bool eraseSpace(const char* space) override {
    const std::string prefix = std::string(space) + "/";
    for (auto it = map_.begin(); it != map_.end();) {
      if (it->first.compare(0, prefix.size(), prefix) == 0) {
        it = map_.erase(it);
      } else {
        ++it;
      }
    }
    return true;
  }

 private:
  static constexpr size_t kMaxKeyLen = 15;
  static std::string compose(const char* space, const char* key) { return std::string(space) + "/" + key; }

  std::map<std::string, uint32_t> map_;
};

class FakeFile : public FileStore {
 public:
  int failWritesAfter = -1;  // n번째 writeAtomic 부터 실패(0 = 다음 쓰기), -1 = 안 함
  int reads = 0;             // read 호출 수(캐시 사용 검증용)

  ReadResult read(const char* path, uint8_t* buf, size_t cap, size_t& len) override {
    ++reads;
    auto it = files_.find(path);
    if (it == files_.end()) return ReadResult::NotFound;
    if (it->second.size() > cap) return ReadResult::Fail;
    len = it->second.size();
    if (len > 0) std::memcpy(buf, it->second.data(), len);
    return ReadResult::Ok;
  }

  bool writeAtomic(const char* path, const uint8_t* data, size_t len) override {
    if (failWritesAfter == 0) return false;  // 실패해도 옛 내용은 그대로
    if (failWritesAfter > 0) --failWritesAfter;
    files_[path] = std::vector<uint8_t>(data, data + len);
    return true;
  }

  bool remove(const char* path) override {
    files_.erase(path);
    return true;
  }

  // 앞 keepBytes 만 남긴다(전원 끊김으로 잘린 파일 흉내). 없는 파일·더 큰 값은 무시.
  void truncate(const char* path, size_t keepBytes) {
    auto it = files_.find(path);
    if (it == files_.end() || keepBytes >= it->second.size()) return;
    it->second.resize(keepBytes);
  }

  void putRaw(const char* path, std::vector<uint8_t> bytes) { files_[path] = std::move(bytes); }

 private:
  std::map<std::string, std::vector<uint8_t>> files_;
};

}  // namespace ns
