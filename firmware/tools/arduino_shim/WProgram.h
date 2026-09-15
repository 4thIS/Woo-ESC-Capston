#pragma once
// 호스트(native) 빌드에서 Adafruit_GFX.h가 요구하는 최소 심볼만 제공한다.
// 실기 빌드([env:terminal])에서는 이 파일이 include 경로에 없어 진짜 Arduino.h가 쓰인다.
//
// 파일명이 WProgram.h인 이유: Adafruit_GFX.h는 `#if ARDUINO >= 100`이 거짓이면 이 파일을 찾는다.
// 일부러 ARDUINO 매크로를 정의하지 않는다 — 정의하면 ArduinoJson 등 다른 라이브러리도
// "진짜 Arduino 환경"으로 오판해 Stream/Print 기반 코드 경로를 추가로 요구하기 시작한다(실측 확인).
#include <cmath>  // sin/cos — Adafruit_GFX::rotatePoint()가 씀
#include <cstddef>
#include <cstdint>
#include <cstdlib>  // malloc/free — 실기에서는 Arduino.h가 전이적으로 제공, 여기선 명시
#include <cstring>  // memset — 위와 동일 이유
#include <string>   // std::string — 아래 String 최소 구현이 씀

#include "Print.h"

// Adafruit_GFX.h는 이 파일이 include된 *뒤에*(파일 안 다른 지점에서) 다시 `#if ARDUINO >= 100`로
// write(uint8_t)의 반환형(size_t vs void)을 고른다. 여기서 정의해야 그 시점엔 보이면서
// WProgram.h를 안 쓰는 ArduinoJson 등 다른 헤더에는 안 보인다(각주 참조).
#define ARDUINO 10812

#define PROGMEM

#ifndef PI
#define PI 3.1415926535897932384626433832795
#endif
#define radians(deg) ((deg) * PI / 180.0)

// PROGMEM이 없는(=일반 RAM 포인터인) 호스트에서, "플래시 읽기" 매크로는 그냥 역참조.
// ArduinoJson의 __FlashStringHelper 관련 코드(FlashReader.hpp)도 이 매크로를 요구한다 —
// Adafruit_GFX.cpp 자신의 #ifndef 폴백과 이름이 같으므로 여기서 먼저 정의해도 충돌 없다.
#ifndef pgm_read_byte
#define pgm_read_byte(addr) (*(const unsigned char*)(addr))
#endif
#ifndef pgm_read_word
#define pgm_read_word(addr) (*(const unsigned short*)(addr))
#endif
#ifndef pgm_read_dword
#define pgm_read_dword(addr) (*(const unsigned long*)(addr))
#endif

class __FlashStringHelper;

// Adafruit_GFX.cpp의 getTextBounds(const String&, ...) 구현이 .length()/.c_str()를
// 실제로 호출한다(선언만이 아니라 정의가 있는 멤버 함수라 컴파일 시점에 타입 체크됨).
// v1 렌더 코드는 이 오버로드를 호출하지 않지만, 벤더 .cpp 자체가 컴파일되려면 필요.
class String {
 public:
  String(const char* s = "") : s_(s ? s : "") {}
  size_t length() const { return s_.size(); }
  const char* c_str() const { return s_.c_str(); }

 private:
  std::string s_;
};
