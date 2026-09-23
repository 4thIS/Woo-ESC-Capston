#pragma once
// 호스트(native) 빌드용 <pgmspace.h> 심.
//
// 존재 이유: v1(esp32_e-paper_syllabus)의 폰트·이미지 헤더 6개
// (AsciiGlyphs.h · LabelImages.h · NanumGothic16.h · NanumGothic20.h ·
//  StatusImages.h · TimeGlyphs.h)가 전부 `#include <pgmspace.h>` 를 직접 쓴다.
// ESP32 툴체인에는 이 헤더가 있지만 호스트에는 없어, 이 이름의 파일이 include 경로에
// 존재하지 않으면 WProgram.h 가 먼저 들어와 매크로를 이미 정의했더라도 컴파일이 깨진다
// (누락되는 것은 매크로가 아니라 '파일'이다).
// 실기 빌드([env:terminal])에서는 tools/arduino_shim 이 include 경로에 없어 진짜 헤더가 쓰인다.
//
// 정의 내용은 WProgram.h 와 같고, 양쪽 다 #ifndef 가드를 쓰므로 어느 쪽이 먼저
// include 되든 재정의 충돌이 없다(test_pgmspace_shim 이 두 순서를 모두 컴파일한다).

#ifndef PROGMEM
#define PROGMEM
#endif

// PROGMEM이 없는(=일반 RAM 포인터인) 호스트에서, "플래시 읽기" 매크로는 그냥 역참조.
#ifndef pgm_read_byte
#define pgm_read_byte(addr) (*(const unsigned char*)(addr))
#endif
#ifndef pgm_read_word
#define pgm_read_word(addr) (*(const unsigned short*)(addr))
#endif
#ifndef pgm_read_dword
#define pgm_read_dword(addr) (*(const unsigned long*)(addr))
#endif
