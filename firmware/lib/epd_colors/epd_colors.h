#pragma once
// GxEPD2 색상 상수 — 호스트에서 이 세 값을 정의하는 유일한 곳(헤더 전용).
// lib/render(실기·호스트 공용 렌더)와 lib/host_gfx(호스트 프레임버퍼)가 함께 include 한다. 어느 쪽에도
// 속하지 않는 중립 헤더로 둬, 호스트 인프라가 렌더 계층을 import 하지 않게 한다(firmware/CLAUDE.md 계층
// 책임). 실기는 GxEPD2 헤더도 같은 이름·같은 값을 정의한다 — 먼저 들어오면 가드로 건너뛰고, 나중에 들어와도
// 같은 토큰으로의 재정의는 합법이라 include 순서와 무관하다. 값이 GxEPD2 와 같은지는 test_host_gfx 의
// test_hcolor_values_match_gxepd2_constants 가 지킨다.
#ifndef GxEPD_WHITE
#define GxEPD_WHITE 0xFFFF
#endif
#ifndef GxEPD_BLACK
#define GxEPD_BLACK 0x0000
#endif
#ifndef GxEPD_RED
#define GxEPD_RED 0xF800
#endif
