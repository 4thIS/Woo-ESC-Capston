#pragma once
// UTF-8 문자열을 BitmapFont 로 한 줄 그린다(v1 ngNextCP·ngPrintLine 대체). 줄바꿈·자르기는 하지 않는다
// — 렌더 계층은 문자열을 자르지 않는다(S3 spec §3).
#include <cstdint>

#include "bitmap_font.h"

class Adafruit_GFX;

// p 에서 코드포인트 하나를 꺼내고 p 를 다음 글자로 옮긴다. 문자열 끝이면 0.
// 잘린 멀티바이트(연속 바이트가 0x80~0xBF 가 아님)나 단독 연속 바이트는 '?' 하나로 바꾸고,
// 뒤따르는 고아 연속 바이트까지 함께 넘긴다 — 종단 NUL 너머를 읽지 않는다
// (v1 ngNextCP 는 연속 바이트를 확인하지 않고 건너뛰었다).
uint32_t utf8Next(const char*& p);

// 목록 밖 글자는 폭 0(bfDrawGlyph 와 같은 규칙). trackingPx 는 글자 사이에만 더한다.
int16_t textWidth(const BitmapFont& f, const char* utf8, int8_t trackingPx = 0);

// (x, baselineY) 펜 원점에서 그린다. 반환값은 같은 인자의 textWidth 와 같다.
int16_t drawText(Adafruit_GFX& gfx, const BitmapFont& f, const char* utf8, int16_t x, int16_t baselineY,
                 uint16_t color, int8_t trackingPx = 0);
