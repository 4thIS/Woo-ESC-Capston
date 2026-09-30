#pragma once
// GxEPD2 색상 상수. 실기는 GxEPD2 헤더가, 호스트는 host_gfx.h 가 같은 이름·같은 값을 정의한다.
// lib/render 는 둘 중 어느 것도 include 하지 않으므로(host_gfx 는 호스트 전용) 여기서 가드와 함께 둔다.
// 같은 토큰으로의 재정의는 합법이라 include 순서와 무관하다. 값이 어긋나면 test_render_layout 의
// HColor 비교가 잡는다.
#ifndef GxEPD_WHITE
#define GxEPD_WHITE 0xFFFF
#endif
#ifndef GxEPD_BLACK
#define GxEPD_BLACK 0x0000
#endif
#ifndef GxEPD_RED
#define GxEPD_RED 0xF800
#endif
