// 노드 저장 계층의 포트(인터페이스). 실기 어댑터(NVS·LittleFS)와 테스트용 fake 가 이걸 구현한다.
// 표준 C++ 만 쓴다 — Arduino/ESP 헤더 금지(호스트 테스트에서 그대로 빌드되어야 한다).
#pragma once

#include <cstddef>
#include <cstdint>

namespace ns {

enum class ReadResult : uint8_t { Ok, NotFound, Fail };

// NVS. 값은 u32 하나로 담는다(u8·u16·bool 수용).
struct KvStore {
  virtual ~KvStore() = default;
  virtual bool get(const char* space, const char* key, uint32_t& out) = 0;  // 없으면 false
  virtual bool set(const char* space, const char* key, uint32_t v) = 0;     // 실패 false
  virtual bool eraseSpace(const char* space) = 0;
};

// LittleFS. 파일 통째 읽기·원자 쓰기.
struct FileStore {
  virtual ~FileStore() = default;
  virtual ReadResult read(const char* path, uint8_t* buf, size_t cap, size_t& len) = 0;  // cap 초과면 Fail
  virtual bool writeAtomic(const char* path, const uint8_t* data, size_t len) = 0;  // 실패 시 옛 내용 유지
  virtual bool remove(const char* path) = 0;                                        // 없는 파일도 true
};

}  // namespace ns
