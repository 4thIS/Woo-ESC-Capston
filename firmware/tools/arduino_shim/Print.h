#pragma once
#include <cstddef>
#include <cstdint>

// Adafruit_GFX가 public 상속하는 최소 Print. v1 렌더 코드는 print()/println()을
// 쓰지 않으므로(한글은 drawBitmap로 직접 blit) 실동작 구현 없이 컴파일만 통과하면 된다.
class Print {
 public:
  virtual ~Print() {}
  virtual size_t write(uint8_t) { return 0; }
  virtual size_t write(const uint8_t* buffer, size_t size) {
    size_t n = 0;
    while (n < size) {
      if (!write(buffer[n])) break;
      ++n;
    }
    return n;
  }
  size_t print(const char* s) {
    return write(reinterpret_cast<const uint8_t*>(s), s ? __builtin_strlen(s) : 0);
  }
  size_t println(const char* s) {
    size_t n = print(s);
    n += write('\n');
    return n;
  }
};
