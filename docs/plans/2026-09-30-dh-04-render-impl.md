# dh-04 Task 4~6 — `renderLayout` 구현 계획 (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- 생성일시: 2026-09-30
- 상위 plan: `docs/plans/2026-09-20-dh-04-render-port.md` — 결정(D1~D7)과 Task 0~3 결과. 이 문서는 그 §6 "남은 것"(Task 4~6)의 Step이다.
- 표기: `[확인]` 직접 실행·열람 / `[추정]` 확인 안 함 / ⚠️ 작성자가 고른 값 — 첫 PNG 검토(Task 4.3) 때 사용자·mh가 확인한다.

**Goal:** `RenderModel` 하나를 받아 스펙대로 800×480 3색 화면을 그리는 `renderLayout()`을 `firmware/lib/render/`에 만들고, 레이아웃 8종의 픽스처와 PNG를 뽑는다.

**Architecture:** 세 층으로 나눈다. (1) `text` — UTF-8 문자열을 `BitmapFont`로 한 줄 그리기(v1 `ngNextCP`/`ngPrintLine` 대체). (2) `render_logic` — 픽셀을 찍지 않는 순수 함수(상태 띠 색, 상태명 이미지, 보조 문구, 요일, type 칩, 오늘 목록 창 계산). (3) `render` — 스펙 좌표대로 영역을 그리는 `renderLayout()`. 호스트는 `HostGfx`, 실기는 GxEPD2가 같은 `Adafruit_GFX&`로 받는다. v1의 `renderLayout`은 JSON·전역 display 기반의 다른 화면이라 코드를 그대로 옮기지 않고, UTF-8 해석·`drawBitmap` 방식만 가져온다.

**Tech Stack:** C++17, PlatformIO `[env:native]`/`[env:native_preview]`, Unity, Adafruit_GFX(벤더), `lib/bitmap_font`·`lib/bitmap_image`(Task 3 산출물)

**Spec:** `docs/design/screens/terminal-epaper.md`(화면 원본), `docs/specs/2026-09-16-s3-render-design.md` §3·§4(인터페이스·제약)

## Global Constraints

- 캔버스 800×480, 가로. 색은 `GxEPD_WHITE`(0xFFFF)·`GxEPD_BLACK`(0x0000)·`GxEPD_RED`(0xF800) 셋뿐. 회색·안티에일리어싱 없음.
- 적색은 **상태 띠 바탕에만** 쓴다. 글자·선에 적색 금지.
- 반전(흑 채움 + 흰 글자)은 상태 띠(RED일 때 적색 면)·오늘 목록 현재 행·푸터·칩에만.
- 타입 6단계 고정: 78/800 상태명(이미지) · 62/800 · 32/800 · 28/700 · 20/400 · 16/400(칩류 16/700 이미지). 새 크기를 만들지 않는다.
- 렌더는 `RenderModel` 밖의 것을 읽지 않는다. 줄바꿈·말줄임을 하지 않는다(S3 spec §3).
- 시그니처: `void renderLayout(Adafruit_GFX& gfx, const RenderModel& model);`(S3 spec §4.3)
- `firmware/lib/adafruit_gfx_vendor/` 수정 금지. `host_gfx.h`는 호스트 전용이라 `lib/render/`에서 include하지 않는다.
- 게이트: `pio test -e native` 전부 통과, `pio run -e native_preview` SUCCESS, `pio check -e native --fail-on-defect medium --fail-on-defect high` HIGH 0 / MEDIUM 0.
- 커밋 메시지: Conventional Commits(`feat(firmware): ...`), 본문은 글머리표, **AI 생성 표기·Co-Authored-By 금지**. pre-commit 훅이 파일 형식을 고치면 다시 `git add` 후 같은 메시지로 커밋한다.

## Review Focus

1. **잘린 UTF-8** — 과목 20B 경계에서 멀티바이트가 잘린 문자열(`fixture_parse`의 알려진 문제, dh-05 이월 M-7). 사람이 기대하는 것: 종단 NUL 너머를 읽지 않고, 잘린 글자 자리에 `?` 하나만 나온다. → Task 4.1 `test_truncated_multibyte_stops_at_nul`
2. **글자 목록 밖 글자**(예: `똠`) — 그 글자만 빠지고 나머지 글자는 간격 없이 이어서 그려진다. → Task 4.1 `test_unknown_glyph_is_skipped`
3. **`nToday`가 24보다 큼**(손상된 모델) — `today[24]` 밖을 읽지 않고 24로 자른다. → Task 4.2 `test_window_clamps_count_to_24`
4. **`cur.flags` bit0=1인데 `today[]`에 같은 시각 항목이 없음** — 반전 행 없이 그리고, 창은 다음 예정 항목 기준. → Task 4.2 `test_window_cur_not_in_today_uses_next`
5. **`layout`이 1~8 밖**(0, 9) — 흰 화면만 그리고 끝낸다(멈추거나 쓰레기를 그리지 않는다). → Task 5.1 `test_out_of_range_layout_is_blank`

## 파일 구조

| 파일 | 책임 | Task |
|---|---|---|
| `firmware/lib/render/text.h`, `text.cpp` | UTF-8 → 코드포인트, 문자열 폭, 한 줄 그리기 | 4.1 |
| `firmware/lib/render/render_logic.h`, `render_logic.cpp` | 상태 띠 스타일·상태명 이미지·요일·type 칩·보조 문구·시각 문자열·오늘 목록 창 | 4.2 |
| `firmware/lib/render/render_colors.h` | GxEPD2 색상 상수(`#ifndef` 가드) — 실기는 GxEPD2, 호스트는 `host_gfx.h`가 같은 이름을 정의한다 | 4.3 |
| `firmware/lib/render/render.h`, `render.cpp` | `renderLayout()` — 스펙 좌표대로 영역 그리기 | 4.3·5.1·5.2 |
| `firmware/test/test_render_text/test_main.cpp` | 4.1 테스트 | 4.1 |
| `firmware/test/test_render_logic/test_main.cpp` | 4.2 테스트 | 4.2 |
| `firmware/test/test_render_layout/test_main.cpp` | 픽셀 단위 화면 테스트 | 4.3·5.1·5.2 |
| `firmware/tools/render_preview.cpp` (수정) | `smokeRender` → `renderLayout` | 4.3 |
| `firmware/test/test_render_preview/test_main.cpp` (수정) | 같은 교체 | 4.3·6.1 |
| `firmware/test/fixtures/render/layout*.json` | 레이아웃 8종 픽스처 | 6.1 |

상위 plan의 Task 번호와의 대응: Task 4 = 4.1~4.3(오늘 목록 전체 포함), Task 5 = 5.1(layout 2~7 차이)·5.2(layout 8), Task 6 = 6.1.

## 공통 명령

모든 명령은 `firmware/`에서 Git Bash로 실행한다.

```bash
cd /c/projects/capstone_loraepaper/Woo-ESC-Capston/firmware
export PATH="/c/msys64/mingw64/bin:$PATH"
PIO=/c/Users/kdohy/.platformio/penv/Scripts/platformio.exe
```

작업 브랜치는 `dh`다(Task 3 폰트·이미지 커밋이 있는 곳). 시작 전 기준선: `$PIO test -e native` → **54 test cases: 54 succeeded**. `[확인]` 2026-09-29

## 참고 수치 (`[확인]` `firmware/src/fonts/*.json`)

| 심벌 | px/굵기 | 셀 w×h | baseline | 글자 |
|---|---|---|---|---|
| `kNanum16Regular` | 16/400 | 16×17 | 14 | ASCII·`·↑↓`·`호개더` 101자 |
| `kNanum20Regular` | 20/400 | 20×21 | 17 | 2,459자 |
| `kNanum20Bold` | 20/700 | 20×21 | 18 | 2,459자 |
| `kNanum28Bold` | 28/700 | 28×29 | 25 | 2,459자 |
| `kNanum32ExtraBold` | 32/800 | 18×26 | 25 | 숫자 10자 |
| `kNanum62ExtraBold` | 62/800 | 64×51 | 49 | `0-9 : - A-F N W` |

이미지(`image_data.h`): 상태명 78/800 `kImgStatusSueopjung`·`Swineunsigan`·`Hyugang`·`Binganguisil`·`Siheomjung`·`Teukgang`·`Daeyeojung`(h 75~76, baseline 66~67), 제목 `kImgTitleSeoljeongdaegi`(230×60, baseline 53), 칩 16/700 `kImgChipOneul`·`Siheom`·`Hyugang`·`Teukgang`·`Daeyeo`·`Byeongyeong`(h 14~17, baseline 13~14).

---

### Task 4.1: 텍스트 한 줄 그리기 (`text`)

**Files:**
- Create: `firmware/lib/render/text.h`
- Create: `firmware/lib/render/text.cpp`
- Test: `firmware/test/test_render_text/test_main.cpp`

**Interfaces:**
- Consumes: `bitmap_font.h`의 `BitmapFont`, `bfFindGlyph(const BitmapFont&, uint32_t)`, `bfDrawGlyph(Adafruit_GFX&, const BitmapFont&, uint32_t cp, int16_t x, int16_t baselineY, uint16_t color)`(반환: 진행폭, 없는 글자면 0)
- Produces:
  - `uint32_t utf8Next(const char*& p);`
  - `int16_t textWidth(const BitmapFont& f, const char* utf8, int8_t trackingPx = 0);`
  - `int16_t drawText(Adafruit_GFX& gfx, const BitmapFont& f, const char* utf8, int16_t x, int16_t baselineY, uint16_t color, int8_t trackingPx = 0);` — 반환값은 `textWidth`와 같다

- [ ] **Step 1: 실패하는 테스트 작성**

`firmware/test/test_render_text/test_main.cpp`:

```cpp
// dh-04 Task 4.1 — UTF-8 해석과 한 줄 그리기.
#include <unity.h>

#include "font_data.h"
#include "host_gfx.h"
#include "text.h"

static int16_t adv(const BitmapFont& f, uint32_t cp) { return f.advances[bfFindGlyph(f, cp)]; }

static int countColor(const HostGfx& g, int x0, int y0, int x1, int y1, HColor c) {
  int n = 0;
  for (int y = y0; y < y1; y++)
    for (int x = x0; x < x1; x++)
      if (g.pixelAt((int16_t)x, (int16_t)y) == c) n++;
  return n;
}

void test_ascii_and_multibyte_decode() {
  const char* p = "A\xC2\xB7\xEA\xB0\x80";  // 'A', '·'(U+00B7), '가'(U+AC00)
  TEST_ASSERT_EQUAL_UINT32('A', utf8Next(p));
  TEST_ASSERT_EQUAL_UINT32(0x00B7, utf8Next(p));
  TEST_ASSERT_EQUAL_UINT32(0xAC00, utf8Next(p));
  TEST_ASSERT_EQUAL_UINT32(0, utf8Next(p));
}

void test_truncated_multibyte_stops_at_nul() {
  // '가'의 앞 2바이트만 있고 NUL. 그 뒤의 'A'를 읽으면 버퍼 밖 접근이다.
  const char buf[] = {(char)0xEA, (char)0xB0, 0, 'A'};
  const char* p = buf;
  TEST_ASSERT_EQUAL_UINT32('?', utf8Next(p));  // 0xEA 뒤가 연속 바이트지만 그다음이 NUL
  TEST_ASSERT_EQUAL_UINT32('?', utf8Next(p));  // 0xB0 은 단독으로 올 수 없는 바이트
  TEST_ASSERT_EQUAL_UINT32(0, utf8Next(p));    // NUL 에서 멈춘다 — 'A'를 읽지 않는다
}

void test_width_is_sum_of_advances() {
  const int16_t expected = adv(kNanum20Regular, 0xAC00) + adv(kNanum20Regular, 0xB098);  // 가, 나
  TEST_ASSERT_EQUAL_INT16(expected, textWidth(kNanum20Regular, "가나"));
}

void test_tracking_applies_between_glyphs_only() {
  const int16_t plain = textWidth(kNanum20Regular, "가나");
  TEST_ASSERT_EQUAL_INT16(plain - 1, textWidth(kNanum20Regular, "가나", -1));
  TEST_ASSERT_EQUAL_INT16(adv(kNanum20Regular, 0xAC00), textWidth(kNanum20Regular, "가", -1));
}

void test_unknown_glyph_is_skipped() {
  // '똠'(U+B620)은 KS X 1001 밖이라 charset.txt 에 없다.
  TEST_ASSERT_EQUAL_INT16(textWidth(kNanum20Regular, "가나"), textWidth(kNanum20Regular, "가똠나"));
}

void test_empty_string_has_zero_width() {
  TEST_ASSERT_EQUAL_INT16(0, textWidth(kNanum20Regular, ""));
}

void test_draw_returns_width_and_paints_from_x() {
  HostGfx g;
  const int16_t w = drawText(g, kNanum20Regular, "가나", 100, 100, GxEPD_BLACK);
  TEST_ASSERT_EQUAL_INT16(textWidth(kNanum20Regular, "가나"), w);
  TEST_ASSERT_GREATER_THAN_INT(20, countColor(g, 100, 80, 100 + w, 104, HColor::BLACK));
  TEST_ASSERT_EQUAL_INT(0, countColor(g, 0, 0, 100, 480, HColor::BLACK));  // x 왼쪽은 건드리지 않는다
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_ascii_and_multibyte_decode);
  RUN_TEST(test_truncated_multibyte_stops_at_nul);
  RUN_TEST(test_width_is_sum_of_advances);
  RUN_TEST(test_tracking_applies_between_glyphs_only);
  RUN_TEST(test_unknown_glyph_is_skipped);
  RUN_TEST(test_empty_string_has_zero_width);
  RUN_TEST(test_draw_returns_width_and_paints_from_x);
  return UNITY_END();
}
```

- [ ] **Step 2: 실패 확인**

Run: `$PIO test -e native -f test_render_text`
Expected: FAIL — `text.h: No such file or directory`

- [ ] **Step 3: 최소 구현**

`firmware/lib/render/text.h`:

```cpp
#pragma once
// UTF-8 문자열을 BitmapFont 로 한 줄 그린다(v1 ngNextCP·ngPrintLine 대체). 줄바꿈·자르기는 하지 않는다
// — 렌더 계층은 문자열을 자르지 않는다(S3 spec §3).
#include <cstdint>

#include "bitmap_font.h"

class Adafruit_GFX;

// p 에서 코드포인트 하나를 꺼내고 p 를 다음 글자로 옮긴다. 문자열 끝이면 0.
// 잘린 멀티바이트(연속 바이트가 0x80~0xBF 가 아님)는 '?' 로 바꾸고 1바이트만 넘긴다 —
// 종단 NUL 너머를 읽지 않는다(v1 ngNextCP 는 연속 바이트를 확인하지 않고 건너뛰었다).
uint32_t utf8Next(const char*& p);

// 목록 밖 글자는 폭 0(bfDrawGlyph 와 같은 규칙). trackingPx 는 글자 사이에만 더한다.
int16_t textWidth(const BitmapFont& f, const char* utf8, int8_t trackingPx = 0);

// (x, baselineY) 펜 원점에서 그린다. 반환값은 같은 인자의 textWidth 와 같다.
int16_t drawText(Adafruit_GFX& gfx, const BitmapFont& f, const char* utf8, int16_t x, int16_t baselineY,
                 uint16_t color, int8_t trackingPx = 0);
```

`firmware/lib/render/text.cpp`:

```cpp
#include "text.h"

uint32_t utf8Next(const char*& p) {
  const uint8_t* s = reinterpret_cast<const uint8_t*>(p);
  const uint8_t c = s[0];
  if (c == 0) return 0;
  if (c < 0x80) {
    p += 1;
    return c;
  }
  int n;
  uint32_t cp;
  if ((c & 0xE0) == 0xC0) {
    n = 1;
    cp = c & 0x1F;
  } else if ((c & 0xF0) == 0xE0) {
    n = 2;
    cp = c & 0x0F;
  } else if ((c & 0xF8) == 0xF0) {
    n = 3;
    cp = c & 0x07;
  } else {
    p += 1;
    return '?';
  }
  // s[i] 는 s[i-1] 이 NUL 이 아닌 연속 바이트임을 확인한 뒤에만 읽는다 — NUL 너머를 읽지 않는다.
  for (int i = 1; i <= n; i++) {
    if ((s[i] & 0xC0) != 0x80) {
      p += 1;
      return '?';
    }
    cp = (cp << 6) | (s[i] & 0x3F);
  }
  p += n + 1;
  return cp;
}

int16_t textWidth(const BitmapFont& f, const char* utf8, int8_t trackingPx) {
  int16_t w = 0;
  bool any = false;
  const char* p = utf8;
  for (uint32_t cp = utf8Next(p); cp != 0; cp = utf8Next(p)) {
    const int32_t idx = bfFindGlyph(f, cp);
    if (idx < 0) continue;
    w = (int16_t)(w + f.advances[idx] + trackingPx);
    any = true;
  }
  return any ? (int16_t)(w - trackingPx) : 0;
}

int16_t drawText(Adafruit_GFX& gfx, const BitmapFont& f, const char* utf8, int16_t x, int16_t baselineY,
                 uint16_t color, int8_t trackingPx) {
  int16_t pen = x;
  bool any = false;
  const char* p = utf8;
  for (uint32_t cp = utf8Next(p); cp != 0; cp = utf8Next(p)) {
    const int16_t a = bfDrawGlyph(gfx, f, cp, pen, baselineY, color);
    if (a == 0) continue;
    pen = (int16_t)(pen + a + trackingPx);
    any = true;
  }
  return any ? (int16_t)(pen - x - trackingPx) : 0;
}
```

- [ ] **Step 4: 통과 확인**

Run: `$PIO test -e native -f test_render_text`
Expected: PASS — `7 test cases: 7 succeeded`

Run: `$PIO test -e native`
Expected: `61 test cases: 61 succeeded`(기준 54 + 7)

- [ ] **Step 5: 커밋**

```bash
git add lib/render/text.h lib/render/text.cpp test/test_render_text/test_main.cpp
git commit -m "$(cat <<'EOF'
feat(firmware): UTF-8 한 줄 그리기 text (dh-04 Task 4.1)

- utf8Next·textWidth·drawText — v1 ngNextCP·ngPrintLine 을 BitmapFont 용으로 대체
- 잘린 멀티바이트는 '?' 로 바꾸고 종단 NUL 너머를 읽지 않는다(v1 은 연속 바이트를 확인하지 않았다)
- 목록 밖 글자는 폭 0 으로 건너뛴다, 자간은 글자 사이에만
EOF
)"
```

---

### Task 4.2: 렌더 로직 순수 함수 (`render_logic`)

**Files:**
- Create: `firmware/lib/render/render_logic.h`
- Create: `firmware/lib/render/render_logic.cpp`
- Test: `firmware/test/test_render_logic/test_main.cpp`

**Interfaces:**
- Consumes: `render_model.h`의 `RenderModel`·`RenderSlot`·`TodaySlot`, `image_data.h`의 이미지 심벌
- Produces:
  - `enum class BandStyle : uint8_t { None, Red, Black };`
  - `BandStyle bandStyle(uint8_t layout);`
  - `const BitmapImage* statusImage(uint8_t layout);`
  - `const char* weekdayName(uint8_t weekday);`
  - `const BitmapImage* typeChip(uint8_t type);`
  - `void formatHM(uint8_t h, uint8_t m, char* out, size_t cap);`
  - `bool statusSubline(const RenderModel& m, char* out, size_t cap);`
  - `struct TodayWindow { uint8_t count, start, rows, moreAbove, moreBelow; int8_t curIdx; };`
  - `TodayWindow todayWindow(const RenderModel& m);` — 표시 행 r(0 ≤ r < rows)의 항목은 `today[start + r]`. `moreAbove > 0`이면 0행을, `moreBelow > 0`이면 마지막 행을 "n개 더"로 대체한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`firmware/test/test_render_logic/test_main.cpp`:

```cpp
// dh-04 Task 4.2 — 픽셀을 찍지 않는 렌더 판단. 근거: terminal-epaper.md "상태 띠"·"레이아웃 8종"·"오늘 목록".
#include <unity.h>

#include <initializer_list>

#include "image_data.h"
#include "render_logic.h"

static void setToday(RenderModel& m, uint8_t n) {
  m.nToday = n;
  for (uint8_t i = 0; i < n && i < 24; i++) {
    m.today[i].sH = (uint8_t)(8 + i / 2);
    m.today[i].sM = (uint8_t)((i % 2) * 30);
    m.today[i].eH = m.today[i].sH;
    m.today[i].eM = (uint8_t)(m.today[i].sM + 25);
  }
}

static void pointAt(RenderSlot& s, const TodaySlot& t) {
  s.sH = t.sH;
  s.sM = t.sM;
  s.eH = t.eH;
  s.eM = t.eM;
  s.flags = 1;
}

void test_band_style_per_layout() {
  TEST_ASSERT_EQUAL(BandStyle::Red, bandStyle(1));
  TEST_ASSERT_EQUAL(BandStyle::Black, bandStyle(2));
  TEST_ASSERT_EQUAL(BandStyle::Black, bandStyle(3));
  TEST_ASSERT_EQUAL(BandStyle::Black, bandStyle(4));
  TEST_ASSERT_EQUAL(BandStyle::Red, bandStyle(5));
  TEST_ASSERT_EQUAL(BandStyle::Red, bandStyle(6));
  TEST_ASSERT_EQUAL(BandStyle::Red, bandStyle(7));
  TEST_ASSERT_EQUAL(BandStyle::None, bandStyle(8));
  TEST_ASSERT_EQUAL(BandStyle::None, bandStyle(0));
}

void test_status_image_per_layout() {
  TEST_ASSERT_EQUAL_PTR(&kImgStatusSueopjung, statusImage(1));
  TEST_ASSERT_EQUAL_PTR(&kImgStatusSwineunsigan, statusImage(2));
  TEST_ASSERT_EQUAL_PTR(&kImgStatusHyugang, statusImage(3));
  TEST_ASSERT_EQUAL_PTR(&kImgStatusBinganguisil, statusImage(4));
  TEST_ASSERT_EQUAL_PTR(&kImgStatusSiheomjung, statusImage(5));
  TEST_ASSERT_EQUAL_PTR(&kImgStatusTeukgang, statusImage(6));
  TEST_ASSERT_EQUAL_PTR(&kImgStatusDaeyeojung, statusImage(7));
  TEST_ASSERT_NULL(statusImage(8));
  TEST_ASSERT_NULL(statusImage(0));
}

void test_weekday_names() {
  TEST_ASSERT_EQUAL_STRING("월요일", weekdayName(1));
  TEST_ASSERT_EQUAL_STRING("일요일", weekdayName(7));
  TEST_ASSERT_EQUAL_STRING("", weekdayName(0));
  TEST_ASSERT_EQUAL_STRING("", weekdayName(8));
}

void test_type_chips() {
  TEST_ASSERT_NULL(typeChip(1));  // 수업은 생략
  TEST_ASSERT_EQUAL_PTR(&kImgChipSiheom, typeChip(2));
  TEST_ASSERT_EQUAL_PTR(&kImgChipHyugang, typeChip(3));
  TEST_ASSERT_NULL(typeChip(4));  // 빈강의실은 today[] 에 오지 않는다
  TEST_ASSERT_EQUAL_PTR(&kImgChipTeukgang, typeChip(5));
  TEST_ASSERT_EQUAL_PTR(&kImgChipDaeyeo, typeChip(6));
}

void test_format_hm_pads_zero() {
  char s[6];
  formatHM(9, 5, s, sizeof s);
  TEST_ASSERT_EQUAL_STRING("09:05", s);
}

void test_subline_in_use_states_uses_cur_end() {
  RenderModel m{};
  m.cur.eH = 15;
  m.cur.eM = 0;
  m.cur.flags = 1;
  char s[32];
  for (uint8_t layout : {1, 5, 6, 7}) {
    m.layout = layout;
    TEST_ASSERT_TRUE(statusSubline(m, s, sizeof s));
    TEST_ASSERT_EQUAL_STRING("15:00에 끝납니다", s);
  }
}

void test_subline_break_uses_next_start() {
  RenderModel m{};
  m.layout = 2;
  m.next.sH = 14;
  m.next.flags = 1;
  char s[32];
  TEST_ASSERT_TRUE(statusSubline(m, s, sizeof s));
  TEST_ASSERT_EQUAL_STRING("14:00 수업 재개", s);
}

void test_subline_cancel_and_empty() {
  RenderModel m{};
  char s[32];
  m.layout = 3;
  TEST_ASSERT_TRUE(statusSubline(m, s, sizeof s));
  TEST_ASSERT_EQUAL_STRING("오늘 휴강입니다", s);
  m.layout = 4;
  TEST_ASSERT_FALSE(statusSubline(m, s, sizeof s));
  TEST_ASSERT_EQUAL_STRING("", s);
}

void test_subline_missing_slot_is_empty() {
  RenderModel m{};
  m.layout = 1;  // cur.flags bit0 = 0
  char s[32];
  TEST_ASSERT_FALSE(statusSubline(m, s, sizeof s));
  TEST_ASSERT_EQUAL_STRING("", s);
}

void test_window_short_list_shows_all() {
  RenderModel m{};
  setToday(m, 5);
  pointAt(m.cur, m.today[2]);
  const TodayWindow w = todayWindow(m);
  TEST_ASSERT_EQUAL_UINT8(5, w.count);
  TEST_ASSERT_EQUAL_UINT8(0, w.start);
  TEST_ASSERT_EQUAL_UINT8(5, w.rows);
  TEST_ASSERT_EQUAL_UINT8(0, w.moreAbove);
  TEST_ASSERT_EQUAL_UINT8(0, w.moreBelow);
  TEST_ASSERT_EQUAL_INT8(2, w.curIdx);
}

void test_window_cur_at_top_hides_below() {
  RenderModel m{};
  setToday(m, 12);
  pointAt(m.cur, m.today[0]);
  const TodayWindow w = todayWindow(m);
  TEST_ASSERT_EQUAL_UINT8(0, w.start);
  TEST_ASSERT_EQUAL_UINT8(9, w.rows);
  TEST_ASSERT_EQUAL_UINT8(0, w.moreAbove);
  TEST_ASSERT_EQUAL_UINT8(4, w.moreBelow);  // 항목 8~11 이 숨는다(8은 "↓ 4개 더" 행 자리)
}

void test_window_clamps_to_end() {
  RenderModel m{};
  setToday(m, 12);
  pointAt(m.cur, m.today[6]);
  const TodayWindow w = todayWindow(m);
  TEST_ASSERT_EQUAL_UINT8(3, w.start);       // clamp(6-1, 0, 12-9) = 3
  TEST_ASSERT_EQUAL_UINT8(4, w.moreAbove);   // 항목 0~3
  TEST_ASSERT_EQUAL_UINT8(0, w.moreBelow);
  TEST_ASSERT_EQUAL_INT8(6, w.curIdx);
}

void test_window_both_sides_cut_shows_seven() {
  RenderModel m{};
  setToday(m, 20);
  pointAt(m.cur, m.today[10]);
  const TodayWindow w = todayWindow(m);
  TEST_ASSERT_EQUAL_UINT8(9, w.start);
  TEST_ASSERT_EQUAL_UINT8(10, w.moreAbove);  // 항목 0~9
  TEST_ASSERT_EQUAL_UINT8(3, w.moreBelow);   // 항목 17~19
}

void test_window_clamps_count_to_24() {
  RenderModel m{};
  setToday(m, 24);
  m.nToday = 30;  // 손상된 값
  const TodayWindow w = todayWindow(m);
  TEST_ASSERT_EQUAL_UINT8(24, w.count);
  TEST_ASSERT_TRUE(w.start + w.rows <= 24);
}

void test_window_cur_not_in_today_uses_next() {
  RenderModel m{};
  setToday(m, 20);
  m.cur.flags = 1;
  m.cur.sH = 23;  // today[] 에 없는 시각
  pointAt(m.next, m.today[15]);
  const TodayWindow w = todayWindow(m);
  TEST_ASSERT_EQUAL_INT8(-1, w.curIdx);  // 반전 행 없음
  TEST_ASSERT_EQUAL_UINT8(11, w.start);  // clamp(15-1, 0, 11) = 11
}

void test_window_no_cur_no_next_starts_at_top() {
  RenderModel m{};
  setToday(m, 12);
  const TodayWindow w = todayWindow(m);
  TEST_ASSERT_EQUAL_UINT8(0, w.start);
  TEST_ASSERT_EQUAL_INT8(-1, w.curIdx);
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_band_style_per_layout);
  RUN_TEST(test_status_image_per_layout);
  RUN_TEST(test_weekday_names);
  RUN_TEST(test_type_chips);
  RUN_TEST(test_format_hm_pads_zero);
  RUN_TEST(test_subline_in_use_states_uses_cur_end);
  RUN_TEST(test_subline_break_uses_next_start);
  RUN_TEST(test_subline_cancel_and_empty);
  RUN_TEST(test_subline_missing_slot_is_empty);
  RUN_TEST(test_window_short_list_shows_all);
  RUN_TEST(test_window_cur_at_top_hides_below);
  RUN_TEST(test_window_clamps_to_end);
  RUN_TEST(test_window_both_sides_cut_shows_seven);
  RUN_TEST(test_window_clamps_count_to_24);
  RUN_TEST(test_window_cur_not_in_today_uses_next);
  RUN_TEST(test_window_no_cur_no_next_starts_at_top);
  return UNITY_END();
}
```

- [ ] **Step 2: 실패 확인**

Run: `$PIO test -e native -f test_render_logic`
Expected: FAIL — `render_logic.h: No such file or directory`

- [ ] **Step 3: 최소 구현**

`firmware/lib/render/render_logic.h`:

```cpp
#pragma once
// 픽셀을 찍지 않는 렌더 판단. 근거: docs/design/screens/terminal-epaper.md
// ("상태 띠", "레이아웃 8종", "오늘 목록 — 창 규칙").
#include <cstddef>
#include <cstdint>

#include "bitmap_image.h"
#include "render_model.h"

enum class BandStyle : uint8_t { None, Red, Black };

// 1·5·6·7 RED, 2·3·4 BLACK, 8·범위 밖 None(상태 띠를 그리지 않는다).
BandStyle bandStyle(uint8_t layout);
// layout 1~7 → 상태명 이미지. 8·범위 밖은 nullptr.
const BitmapImage* statusImage(uint8_t layout);
// 1=월 ~ 7=일 → "월요일" ~ "일요일". 범위 밖은 "".
const char* weekdayName(uint8_t weekday);
// type 2 시험·3 휴강·5 특강·6 대여 → 칩 이미지. 1 수업·그 밖은 nullptr(그리지 않는다).
const BitmapImage* typeChip(uint8_t type);
// "HH:MM"
void formatHM(uint8_t h, uint8_t m, char* out, size_t cap);
// 상태 띠 보조 문구. 쓸 문구가 없으면 false 이고 out 은 "".
bool statusSubline(const RenderModel& m, char* out, size_t cap);

struct TodayWindow {
  uint8_t count;      // 쓸 항목 수 — nToday 를 24 로 자른 값
  uint8_t start;      // 표시 0행의 항목 인덱스
  uint8_t rows;       // 표시 행 수(최대 9, "n개 더" 행 포함)
  uint8_t moreAbove;  // 0 이 아니면 0행을 "↑ n개 더"로 대체
  uint8_t moreBelow;  // 0 이 아니면 마지막 행을 "↓ n개 더"로 대체
  int8_t curIdx;      // 반전할 항목 인덱스, 없으면 -1
};
// 표시 행 r 의 항목은 today[start + r].
TodayWindow todayWindow(const RenderModel& m);
```

`firmware/lib/render/render_logic.cpp`:

```cpp
#include "render_logic.h"

#include <cstdio>

#include "image_data.h"

namespace {
constexpr uint8_t kMaxToday = 24;
constexpr uint8_t kMaxRows = 9;

bool sameTimes(const TodaySlot& t, const RenderSlot& s) {
  return t.sH == s.sH && t.sM == s.sM && t.eH == s.eH && t.eM == s.eM;
}

// s 가 존재(flags bit0)하고 today[0..count) 에 같은 시각 항목이 있으면 그 인덱스, 아니면 -1.
int8_t findSlot(const RenderModel& m, uint8_t count, const RenderSlot& s) {
  if (!(s.flags & 0x01)) return -1;
  for (uint8_t i = 0; i < count; i++)
    if (sameTimes(m.today[i], s)) return (int8_t)i;
  return -1;
}
}  // namespace

BandStyle bandStyle(uint8_t layout) {
  switch (layout) {
    case 1:
    case 5:
    case 6:
    case 7:
      return BandStyle::Red;
    case 2:
    case 3:
    case 4:
      return BandStyle::Black;
    default:
      return BandStyle::None;
  }
}

const BitmapImage* statusImage(uint8_t layout) {
  switch (layout) {
    case 1: return &kImgStatusSueopjung;
    case 2: return &kImgStatusSwineunsigan;
    case 3: return &kImgStatusHyugang;
    case 4: return &kImgStatusBinganguisil;
    case 5: return &kImgStatusSiheomjung;
    case 6: return &kImgStatusTeukgang;
    case 7: return &kImgStatusDaeyeojung;
    default: return nullptr;
  }
}

const char* weekdayName(uint8_t weekday) {
  static const char* const kNames[] = {"월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"};
  if (weekday < 1 || weekday > 7) return "";
  return kNames[weekday - 1];
}

const BitmapImage* typeChip(uint8_t type) {
  switch (type) {
    case 2: return &kImgChipSiheom;
    case 3: return &kImgChipHyugang;
    case 5: return &kImgChipTeukgang;
    case 6: return &kImgChipDaeyeo;
    default: return nullptr;
  }
}

void formatHM(uint8_t h, uint8_t m, char* out, size_t cap) {
  snprintf(out, cap, "%02u:%02u", (unsigned)h, (unsigned)m);
}

bool statusSubline(const RenderModel& m, char* out, size_t cap) {
  out[0] = '\0';
  char hm[6];
  switch (m.layout) {
    case 1:
    case 5:
    case 6:
    case 7:
      if (!(m.cur.flags & 0x01)) return false;
      formatHM(m.cur.eH, m.cur.eM, hm, sizeof hm);
      snprintf(out, cap, "%s에 끝납니다", hm);
      return true;
    case 2:
      if (!(m.next.flags & 0x01)) return false;
      formatHM(m.next.sH, m.next.sM, hm, sizeof hm);
      snprintf(out, cap, "%s 수업 재개", hm);
      return true;
    case 3:
      snprintf(out, cap, "%s", "오늘 휴강입니다");
      return true;
    default:
      return false;
  }
}

TodayWindow todayWindow(const RenderModel& m) {
  TodayWindow w{};
  w.count = m.nToday > kMaxToday ? kMaxToday : m.nToday;
  w.curIdx = findSlot(m, w.count, m.cur);
  if (w.count <= kMaxRows) {
    w.rows = w.count;
    return w;
  }
  // 창 기준: 현재 항목, 없으면 다음 예정 항목, 둘 다 없으면 처음(⚠️ 계획서 "열린 질문" 2).
  int anchor = w.curIdx >= 0 ? w.curIdx : findSlot(m, w.count, m.next);
  if (anchor < 0) anchor = 0;
  int s = anchor - 1;
  if (s < 0) s = 0;
  if (s > w.count - kMaxRows) s = w.count - kMaxRows;
  w.start = (uint8_t)s;
  w.rows = kMaxRows;
  w.moreAbove = w.start > 0 ? (uint8_t)(w.start + 1) : 0;
  w.moreBelow = (w.start + kMaxRows < w.count) ? (uint8_t)(w.count - (w.start + kMaxRows - 1)) : 0;
  return w;
}
```

- [ ] **Step 4: 통과 확인**

Run: `$PIO test -e native -f test_render_logic`
Expected: PASS — `16 test cases: 16 succeeded`

Run: `$PIO test -e native`
Expected: `77 test cases: 77 succeeded`

- [ ] **Step 5: 커밋**

```bash
git add lib/render/render_logic.h lib/render/render_logic.cpp test/test_render_logic/test_main.cpp
git commit -m "$(cat <<'EOF'
feat(firmware): 렌더 판단 순수 함수 render_logic (dh-04 Task 4.2)

- 상태 띠 스타일·상태명 이미지·요일·type 칩·보조 문구·시각 문자열
- 오늘 목록 창 규칙(N=9, clamp(curIdx-1), ↑/↓ n개 더) — terminal-epaper.md 그대로
- nToday 24 초과는 24 로 자르고, cur 가 today[] 에 없으면 next 기준으로 창을 잡는다
EOF
)"
```

---

### Task 4.3: `renderLayout` — layout 1 수직 슬라이스 + 첫 PNG (**mh 검토 지점**)

layout 1(수업중)에 필요한 전부를 그린다: 헤더, RED·BLACK 상태 띠, 정보 형태 A(변경 칩 제외), 오늘 목록 전체(창 규칙·`n개 더`·type 칩·빈 목록), 좌우 분할선, 푸터. `render_preview`와 기존 테스트의 `smokeRender`를 `renderLayout`으로 바꾼다.

**세로 위치 상수는 초기값이다.** ⚠️ 스펙은 "세로 중앙 정렬"만 정하고 베이스라인 좌표는 정하지 않았다. 아래 값은 셀 높이·베이스라인으로 계산한 출발점이고, 이 Task 끝의 첫 PNG를 보고 조정한다.

**Files:**
- Create: `firmware/lib/render/render_colors.h`
- Create: `firmware/lib/render/render.h`
- Create: `firmware/lib/render/render.cpp`
- Create: `firmware/test/test_render_layout/test_main.cpp`
- Modify: `firmware/tools/render_preview.cpp`(전체 교체)
- Modify: `firmware/test/test_render_preview/test_main.cpp`(전체 교체)

**Interfaces:**
- Consumes: Task 4.1 `drawText`·`textWidth`, Task 4.2 전부, `font_data.h`·`image_data.h` 심벌, `Adafruit_GFX::fillScreen/fillRect/drawFastHLine/drawBitmap`
- Produces: `void renderLayout(Adafruit_GFX& gfx, const RenderModel& model);`(`render.h`)

- [ ] **Step 1: 실패하는 테스트 작성**

`firmware/test/test_render_layout/test_main.cpp`:

```cpp
// dh-04 Task 4.3 — 화면 픽셀 테스트. 좌표 근거: terminal-epaper.md "골격"·"영역별 규격".
#include <unity.h>

#include <cstring>
#include <initializer_list>

#include "host_gfx.h"
#include "render.h"

static int countColor(const HostGfx& g, int x0, int y0, int x1, int y1, HColor c) {
  int n = 0;
  for (int y = y0; y < y1; y++)
    for (int x = x0; x < x1; x++)
      if (g.pixelAt((int16_t)x, (int16_t)y) == c) n++;
  return n;
}

static void setSlot(TodaySlot& t, uint8_t sH, uint8_t eH, const char* subj, uint8_t type) {
  t.sH = sH;
  t.sM = 0;
  t.eH = eH;
  t.eM = 50;
  strcpy(t.subj, subj);
  t.type = type;
}

// layout 1 기본 모델: 오늘 3개, 현재 = 1번(13:00 캡스톤디자인), 2번은 시험.
static RenderModel layout1Model() {
  RenderModel m{};
  m.layout = 1;
  m.bld = 'E';
  m.room = 301;
  m.unit = 1;
  m.weekday = 2;
  strcpy(m.cur.subj, "캡스톤디자인");
  strcpy(m.cur.prof, "김교수");
  m.cur.sH = 13;
  m.cur.eH = 14;
  m.cur.eM = 50;
  m.cur.type = 1;
  m.cur.flags = 1;
  m.nToday = 3;
  setSlot(m.today[0], 9, 10, "자료구조", 1);
  setSlot(m.today[1], 13, 14, "캡스톤디자인", 1);
  setSlot(m.today[2], 15, 16, "웹프로그래밍", 2);
  return m;
}

void test_skeleton_lines_and_footer() {
  HostGfx g;
  renderLayout(g, layout1Model());
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(400, 50));   // 헤더 하단선 y 50–51
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(400, 51));
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(498, 300));  // 좌우 분할 x 498–499
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(499, 300));
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(790, 470));  // 푸터 흑 바탕
  TEST_ASSERT_GREATER_THAN_INT(30, countColor(g, 24, 445, 200, 478, HColor::WHITE));  // 푸터 흰 글자
}

void test_header_room_and_weekday() {
  HostGfx g;
  renderLayout(g, layout1Model());
  TEST_ASSERT_GREATER_THAN_INT(50, countColor(g, 24, 5, 120, 48, HColor::BLACK));   // "301 호"
  TEST_ASSERT_GREATER_THAN_INT(20, countColor(g, 690, 5, 777, 48, HColor::BLACK));  // "화요일"
}

void test_red_band_with_white_text() {
  HostGfx g;
  renderLayout(g, layout1Model());
  TEST_ASSERT_EQUAL(HColor::RED, g.pixelAt(10, 60));
  TEST_ASSERT_EQUAL(HColor::RED, g.pixelAt(490, 210));
  TEST_ASSERT_GREATER_THAN_INT(500, countColor(g, 0, 52, 498, 216, HColor::WHITE));  // 상태명 + 보조 문구
  TEST_ASSERT_EQUAL_INT(0, countColor(g, 0, 52, 498, 216, HColor::BLACK));          // RED 띠에는 흑 글자·하단선 없음
}

void test_black_band_has_bottom_line() {
  RenderModel m = layout1Model();
  m.layout = 2;  // 쉬는시간 — BLACK
  m.next.sH = 14;
  m.next.flags = 1;
  HostGfx g;
  renderLayout(g, m);
  TEST_ASSERT_EQUAL(HColor::WHITE, g.pixelAt(10, 60));
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(10, 214));
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(10, 215));
  TEST_ASSERT_EQUAL_INT(0, countColor(g, 0, 0, 800, 480, HColor::RED));
}

void test_info_form_a_dividers_and_values() {
  HostGfx g;
  renderLayout(g, layout1Model());
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(300, 291));
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(300, 365));
  TEST_ASSERT_GREATER_THAN_INT(40, countColor(g, 24, 240, 128, 290, HColor::BLACK));   // 라벨 "과목명"
  TEST_ASSERT_GREATER_THAN_INT(80, countColor(g, 146, 235, 480, 290, HColor::BLACK));  // 값 "캡스톤디자인"
}

void test_today_current_row_inverted() {
  HostGfx g;
  renderLayout(g, layout1Model());
  // 목록 행: y 100 + 36·r. 1행(13:00)이 현재 행.
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(795, 137));
  TEST_ASSERT_EQUAL(HColor::WHITE, g.pixelAt(795, 101));
  TEST_ASSERT_GREATER_THAN_INT(30, countColor(g, 518, 136, 780, 172, HColor::WHITE));  // 반전 행 흰 글자
}

void test_today_type_chip_right_aligned() {
  HostGfx g;
  renderLayout(g, layout1Model());
  // 2행(15:00, 시험) 오른쪽 끝(x 782 이전)에 칩 글자.
  TEST_ASSERT_GREATER_THAN_INT(10, countColor(g, 740, 172, 782, 208, HColor::BLACK));
}

void test_today_empty_message() {
  RenderModel m = layout1Model();
  m.nToday = 0;
  HostGfx g;
  renderLayout(g, m);
  TEST_ASSERT_GREATER_THAN_INT(30, countColor(g, 518, 100, 760, 136, HColor::BLACK));  // "오늘 일정 없음"
  TEST_ASSERT_EQUAL(HColor::WHITE, g.pixelAt(795, 137));                              // 반전 행 없음
}

void test_today_overflow_shows_more_rows() {
  RenderModel m = layout1Model();
  m.nToday = 12;
  for (uint8_t i = 0; i < 12; i++) setSlot(m.today[i], (uint8_t)(8 + i), (uint8_t)(8 + i), "자료구조", 1);
  m.cur.sH = 14;  // today[6] = 14:00
  m.cur.eH = 14;
  HostGfx g;
  renderLayout(g, m);
  // start = clamp(6-1, 0, 3) = 3 → 0행 "↑ 4개 더", 현재 항목 6 은 3행(y 208).
  TEST_ASSERT_GREATER_THAN_INT(10, countColor(g, 518, 100, 640, 136, HColor::BLACK));
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(795, 209));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_skeleton_lines_and_footer);
  RUN_TEST(test_header_room_and_weekday);
  RUN_TEST(test_red_band_with_white_text);
  RUN_TEST(test_black_band_has_bottom_line);
  RUN_TEST(test_info_form_a_dividers_and_values);
  RUN_TEST(test_today_current_row_inverted);
  RUN_TEST(test_today_type_chip_right_aligned);
  RUN_TEST(test_today_empty_message);
  RUN_TEST(test_today_overflow_shows_more_rows);
  return UNITY_END();
}
```

- [ ] **Step 2: 실패 확인**

Run: `$PIO test -e native -f test_render_layout`
Expected: FAIL — `render.h: No such file or directory`

- [ ] **Step 3: 구현**

`firmware/lib/render/render_colors.h`:

```cpp
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
```

`firmware/lib/render/render.h`:

```cpp
#pragma once
// S3 spec §4.3 — 실기(GxEPD2)·호스트(HostGfx) 공용 렌더 진입점.
// 화면 규격 원본: docs/design/screens/terminal-epaper.md
#include <Adafruit_GFX.h>

#include "render_model.h"

void renderLayout(Adafruit_GFX& gfx, const RenderModel& model);
```

`firmware/lib/render/render.cpp`:

```cpp
#include "render.h"

#include <cstdio>

#include "font_data.h"
#include "image_data.h"
#include "render_colors.h"
#include "render_logic.h"
#include "text.h"

namespace {

// 골격 — terminal-epaper.md "골격 — 고정 좌표"
constexpr int16_t kW = 800;
constexpr int16_t kH = 480;
constexpr int16_t kPad = 24;
constexpr int16_t kHeaderLineY = 50;
constexpr int16_t kBandY = 52;
constexpr int16_t kBandW = 500;
constexpr int16_t kBandH = 164;
constexpr int16_t kBandLineY = 214;
constexpr int16_t kInfoY = 216;
constexpr int16_t kInfoH = 224;
constexpr int16_t kDivider1Y = 291;
constexpr int16_t kDivider2Y = 365;
constexpr int16_t kSplitX = 498;
constexpr int16_t kListX = 500;
constexpr int16_t kListW = 300;
constexpr int16_t kListPadX = 18;
constexpr int16_t kListPadY = 16;
constexpr int16_t kFooterY = 440;
constexpr int16_t kFooterH = 40;

// 영역별 규격
constexpr int16_t kRoomToHoGap = 10;
constexpr int16_t kBandGap = 8;      // 상태명 ↔ 보조 문구
constexpr int16_t kLabelX = 24;      // 정보 라벨열 x 24–128
constexpr int16_t kValueX = 146;
constexpr int16_t kRowH = 36;        // 오늘 목록 행 높이
constexpr int16_t kTimeW = 46;       // 목록 시작 시각 폭
constexpr int16_t kTimeGap = 8;
constexpr int16_t kChipH = 22;       // "오늘" 칩
constexpr int16_t kChipGap = 10;
constexpr int16_t kChipPadX = 6;     // ⚠️ 스펙에 없음 — 칩 좌우 여백
constexpr int16_t kChipTextBase = 17;  // ⚠️ 칩 윗변 → 칩 글자 베이스라인

// 자간(px) — 78·62·32 px -0.03~-0.04 em, 28 px -0.02 em. 반올림한 정수.
constexpr int8_t kTrack28 = -1;
constexpr int8_t kTrack32 = -1;
constexpr int8_t kTrack62 = -2;

// ⚠️ 세로 위치 초기값(베이스라인) — 첫 PNG 검토에서 조정한다.
constexpr int16_t kHeaderBase = 37;
constexpr int16_t kInfoRowBase[3] = {263, 338, 413};
constexpr int16_t kRowTextBase = 25;  // 목록 행 윗변 → 글자 베이스라인
constexpr int16_t kFooterBase = kFooterY + 26;

void drawImage(Adafruit_GFX& g, const BitmapImage& img, int16_t x, int16_t top, uint16_t color) {
  g.drawBitmap(x, top, img.bitmap, (int16_t)img.w, (int16_t)img.h, color);
}

// 흑 채움 칩 + 흰 글자 마스크. 반환: 칩 폭.
int16_t drawChip(Adafruit_GFX& g, const BitmapImage& img, int16_t x, int16_t boxTop) {
  const int16_t w = (int16_t)(img.w + 2 * kChipPadX);
  g.fillRect(x, boxTop, w, kChipH, GxEPD_BLACK);
  drawImage(g, img, (int16_t)(x + kChipPadX), (int16_t)(boxTop + kChipTextBase - img.baseline), GxEPD_WHITE);
  return w;
}

void drawHeader(Adafruit_GFX& g, const RenderModel& m) {
  g.fillRect(0, kHeaderLineY, kW, 2, GxEPD_BLACK);
  char room[6];
  snprintf(room, sizeof room, "%u", (unsigned)m.room);
  const int16_t w = drawText(g, kNanum32ExtraBold, room, kPad, kHeaderBase, GxEPD_BLACK, kTrack32);
  drawText(g, kNanum16Regular, "호", (int16_t)(kPad + w + kRoomToHoGap), kHeaderBase, GxEPD_BLACK);
  const char* wd = weekdayName(m.weekday);
  drawText(g, kNanum20Regular, wd, (int16_t)(kW - kPad - textWidth(kNanum20Regular, wd)), kHeaderBase,
           GxEPD_BLACK);
}

void drawStatusBand(Adafruit_GFX& g, const RenderModel& m) {
  const BandStyle style = bandStyle(m.layout);
  const uint16_t fg = style == BandStyle::Red ? GxEPD_WHITE : GxEPD_BLACK;
  if (style == BandStyle::Red)
    g.fillRect(0, kBandY, kBandW, kBandH, GxEPD_RED);
  else
    g.fillRect(0, kBandLineY, kBandW, 2, GxEPD_BLACK);
  const BitmapImage* img = statusImage(m.layout);
  if (img == nullptr) return;
  char sub[32];
  const bool hasSub = statusSubline(m, sub, sizeof sub);
  const int16_t blockH = (int16_t)(img->h + (hasSub ? kBandGap + kNanum20Regular.cellH : 0));
  const int16_t top = (int16_t)(kBandY + (kBandH - blockH) / 2);
  drawImage(g, *img, kPad, top, fg);
  if (hasSub)
    drawText(g, kNanum20Regular, sub, kPad, (int16_t)(top + img->h + kBandGap + kNanum20Regular.baseline), fg);
}

void drawInfoRow(Adafruit_GFX& g, int row, const char* label, const char* value) {
  drawText(g, kNanum20Regular, label, kLabelX, kInfoRowBase[row], GxEPD_BLACK);
  drawText(g, kNanum28Bold, value, kValueX, kInfoRowBase[row], GxEPD_BLACK, kTrack28);
}

void drawInfoA(Adafruit_GFX& g, const RenderModel& m) {
  g.drawFastHLine(0, kDivider1Y, kSplitX, GxEPD_BLACK);
  g.drawFastHLine(0, kDivider2Y, kSplitX, GxEPD_BLACK);
  drawInfoRow(g, 0, "과목명", m.cur.subj);
  drawInfoRow(g, 1, "담당교수", m.cur.prof);
  char s[6], e[6], range[24];
  formatHM(m.cur.sH, m.cur.sM, s, sizeof s);
  formatHM(m.cur.eH, m.cur.eM, e, sizeof e);
  snprintf(range, sizeof range, "%s \xE2\x80\x93 %s", s, e);  // U+2013 en dash
  drawInfoRow(g, 2, "강의시간", range);
}

void drawTodayList(Adafruit_GFX& g, const RenderModel& m) {
  const int16_t x0 = kListX + kListPadX;
  const int16_t chipTop = kBandY + kListPadY;
  drawChip(g, kImgChipOneul, x0, chipTop);
  const int16_t rowsTop = chipTop + kChipH + kChipGap;
  const TodayWindow w = todayWindow(m);
  if (w.count == 0) {
    drawText(g, kNanum20Regular, "오늘 일정 없음", x0, (int16_t)(rowsTop + kRowTextBase), GxEPD_BLACK);
    return;
  }
  for (uint8_t r = 0; r < w.rows; r++) {
    const int16_t top = (int16_t)(rowsTop + r * kRowH);
    const int16_t base = (int16_t)(top + kRowTextBase);
    char more[24];
    if (r == 0 && w.moreAbove > 0) {
      snprintf(more, sizeof more, "\xE2\x86\x91 %u개 더", (unsigned)w.moreAbove);  // ↑
      drawText(g, kNanum16Regular, more, x0, base, GxEPD_BLACK);
      continue;
    }
    if (r == w.rows - 1 && w.moreBelow > 0) {
      snprintf(more, sizeof more, "\xE2\x86\x93 %u개 더", (unsigned)w.moreBelow);  // ↓
      drawText(g, kNanum16Regular, more, x0, base, GxEPD_BLACK);
      continue;
    }
    const uint8_t i = (uint8_t)(w.start + r);
    const TodaySlot& t = m.today[i];
    const bool isCur = (int)i == (int)w.curIdx;
    const uint16_t fg = isCur ? GxEPD_WHITE : GxEPD_BLACK;
    if (isCur) g.fillRect(kListX, top, kListW, kRowH, GxEPD_BLACK);
    char hm[6];
    formatHM(t.sH, t.sM, hm, sizeof hm);
    drawText(g, kNanum16Regular, hm, x0, base, fg);
    drawText(g, isCur ? kNanum20Bold : kNanum20Regular, t.subj, (int16_t)(x0 + kTimeW + kTimeGap), base, fg);
    const BitmapImage* chip = typeChip(t.type);
    if (chip != nullptr)
      drawImage(g, *chip, (int16_t)(kListX + kListW - kListPadX - chip->w), (int16_t)(base - chip->baseline), fg);
  }
}

void drawFooter(Adafruit_GFX& g, const RenderModel& m) {
  g.fillRect(0, kFooterY, kW, kFooterH, GxEPD_BLACK);
  char s[32];
  const char bld = (m.bld >= 0x21 && m.bld <= 0x7E) ? m.bld : '?';
  snprintf(s, sizeof s, "%c \xC2\xB7 %u \xC2\xB7 U%u", bld, (unsigned)m.room, (unsigned)m.unit);  // U+00B7
  drawText(g, kNanum16Regular, s, kPad, kFooterBase, GxEPD_WHITE);
}

}  // namespace

void renderLayout(Adafruit_GFX& gfx, const RenderModel& m) {
  gfx.fillScreen(GxEPD_WHITE);
  drawHeader(gfx, m);
  drawStatusBand(gfx, m);
  drawInfoA(gfx, m);
  drawTodayList(gfx, m);
  gfx.fillRect(kSplitX, kBandY, 2, (int16_t)(kFooterY - kBandY), GxEPD_BLACK);
  drawFooter(gfx, m);
}
```

`firmware/tools/render_preview.cpp` 전체 교체:

```cpp
// 픽스처 JSON 1개 → PNG 1장. renderLayout()(lib/render/)으로 그린다.
// main() 을 가진 실행파일 진입점이라 test/ 밖(tools/)에 둔다 — pio test 가 링크하면
// Unity 의 main() 과 충돌한다. 빌드는 [env:native_preview].
#include <cstdio>

#include "fixture_parse.h"
#include "host_gfx.h"
#include "render.h"

int main(int argc, char** argv) {
  if (argc < 3) {
    fprintf(stderr, "usage: render_preview <fixture.json> <out.png>\n");
    return 1;
  }
  RenderModel model{};
  char name[64];
  if (!parseFixtureFile(argv[1], model, name, sizeof(name))) {
    fprintf(stderr, "fixture parse failed: %s\n", argv[1]);
    return 1;
  }
  HostGfx gfx;
  renderLayout(gfx, model);
  if (!gfx.savePNG(argv[2])) {
    fprintf(stderr, "PNG 저장 실패: %s\n", argv[2]);
    return 1;
  }
  printf("wrote %s (%s)\n", argv[2], name);
  return 0;
}
```

`firmware/test/test_render_preview/test_main.cpp` 전체 교체:

```cpp
#include <unity.h>

#include <cstdio>

#include "fixture_parse.h"
#include "host_gfx.h"
#include "render.h"

// 픽스처 → renderLayout → PNG 파이프라인 전체. 화면 세부는 test_render_layout 이 본다.
void test_pipeline_end_to_end() {
  RenderModel m{};
  char name[64];
  // PlatformIO native 테스트의 CWD 는 firmware/ (test_codec/vectors_path.h 와 같은 전제).
  TEST_ASSERT_TRUE(parseFixtureFile("test/fixtures/render/smoke_basic.json", m, name, sizeof(name)));
  HostGfx g;
  renderLayout(g, m);
  TEST_ASSERT_EQUAL(HColor::RED, g.pixelAt(10, 60));     // layout 1 = RED 상태 띠
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(400, 50));  // 헤더 하단선
  TEST_ASSERT_TRUE(g.savePNG("smoke_basic_out.png"));
  FILE* f = fopen("smoke_basic_out.png", "rb");
  TEST_ASSERT_NOT_NULL(f);
  fclose(f);
  remove("smoke_basic_out.png");
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_pipeline_end_to_end);
  return UNITY_END();
}
```

- [ ] **Step 4: 통과 확인**

Run: `$PIO test -e native -f test_render_layout`
Expected: PASS — `9 test cases: 9 succeeded`

Run: `$PIO test -e native`
Expected: `86 test cases: 86 succeeded`

Run: `$PIO run -e native_preview`
Expected: `SUCCESS`

Run: `$PIO check -e native --fail-on-defect medium --fail-on-defect high`
Expected: `PASSED`, HIGH 0 / MEDIUM 0

- [ ] **Step 5: 첫 PNG 뽑기**

```bash
python tools/render_preview.py
```
Expected: `wrote .../test/fixtures/render/_out/smoke_basic.png (layout1_class_basic)`. `_out/`은 gitignore 대상이다.

- [ ] **Step 6: 커밋**

```bash
git add lib/render/render_colors.h lib/render/render.h lib/render/render.cpp test/test_render_layout/test_main.cpp tools/render_preview.cpp test/test_render_preview/test_main.cpp
git commit -m "$(cat <<'EOF'
feat(firmware): renderLayout — layout 1 수직 슬라이스 (dh-04 Task 4.3)

- 헤더·RED/BLACK 상태 띠·정보 형태 A·오늘 목록(창 규칙·n개 더·type 칩·빈 목록)·좌우 분할·푸터
- render_preview·test_render_preview 의 smokeRender 를 renderLayout 으로 교체(중복 정의 해소)
- 세로 위치 상수는 초기값 — 첫 PNG 검토 후 조정
EOF
)"
```

- [ ] **Step 7: 멈추고 검토 요청(실행자는 여기서 다음 Task로 넘어가지 않는다)**

`test/fixtures/render/_out/smoke_basic.png`를 사용자에게 보여 준다. 사용자가 mh에게 전달해 확인받는다. 확인할 것: 세로 위치 상수(`kHeaderBase`, `kInfoRowBase`, `kRowTextBase`, `kFooterBase`, `kChipPadX`, `kChipTextBase`), 자간, 전체 인상. 조정이 나오면 상수만 고치고 테스트를 다시 돌려 별도 커밋한다(`fix(firmware): 렌더 세로 위치 조정 — 첫 PNG 검토 반영`).

---

### Task 5.1: layout 2~7 차이 — 정보 형태 B, 변경 칩, 범위 밖 layout

**Files:**
- Modify: `firmware/lib/render/render.cpp`
- Modify: `firmware/test/test_render_layout/test_main.cpp`

**Interfaces:**
- Consumes: Task 4.3의 `render.cpp` 내부 함수
- Produces: 변화 없음(`renderLayout` 시그니처 그대로)

- [ ] **Step 1: 실패하는 테스트 추가**

`test_render_layout/test_main.cpp`의 `int main()` 위에 추가:

```cpp
static RenderModel layout4Model() {
  RenderModel m = layout1Model();
  m.layout = 4;  // 빈강의실 — 형태 B
  m.cur = RenderSlot{};
  strcpy(m.next.subj, "캡스톤디자인");
  m.next.sH = 13;
  m.next.flags = 1;
  return m;
}

void test_form_b_has_no_dividers_and_big_time() {
  HostGfx g;
  renderLayout(g, layout4Model());
  TEST_ASSERT_EQUAL(HColor::WHITE, g.pixelAt(300, 291));  // 형태 B 는 행 구분선이 없다(⚠️ 열린 질문 3)
  TEST_ASSERT_EQUAL(HColor::WHITE, g.pixelAt(300, 365));
  TEST_ASSERT_GREATER_THAN_INT(300, countColor(g, 24, 310, 200, 372, HColor::BLACK));  // "13:00" 62/800
}

void test_form_b_without_next_says_no_schedule() {
  RenderModel m = layout4Model();
  m.next.flags = 0;
  HostGfx g;
  renderLayout(g, m);
  TEST_ASSERT_EQUAL(HColor::WHITE, g.pixelAt(300, 291));  // 형태 A 로 그려지지 않았다
  TEST_ASSERT_GREATER_THAN_INT(80, countColor(g, 24, 310, 400, 345, HColor::BLACK));  // "오늘 일정 없음" 28/700
}

void test_change_chip_after_subject() {
  RenderModel m = layout1Model();
  m.cur.flags = 0x03;  // 존재 + 변경 배지
  HostGfx g;
  renderLayout(g, m);
  const int16_t x = (int16_t)(146 + textWidthForTest(m.cur.subj) + 10);
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt((int16_t)(x + 1), (int16_t)(263 - 18 + 1)));  // 칩 흑 바탕 모서리
}

void test_out_of_range_layout_is_blank() {
  RenderModel m = layout1Model();
  for (uint8_t layout : {0, 9, 255}) {
    m.layout = layout;
    HostGfx g;
    renderLayout(g, m);
    TEST_ASSERT_EQUAL_INT(800 * 480, countColor(g, 0, 0, 800, 480, HColor::WHITE));
  }
}
```

`#include "render.h"` 아래에 추가(28px 값 폭을 테스트에서 계산하기 위함):

```cpp
#include "font_data.h"
#include "text.h"

static int16_t textWidthForTest(const char* s) { return textWidth(kNanum28Bold, s, -1); }
```

`main()`에 등록:

```cpp
  RUN_TEST(test_form_b_has_no_dividers_and_big_time);
  RUN_TEST(test_form_b_without_next_says_no_schedule);
  RUN_TEST(test_change_chip_after_subject);
  RUN_TEST(test_out_of_range_layout_is_blank);
```

- [ ] **Step 2: 실패 확인**

Run: `$PIO test -e native -f test_render_layout`
Expected: FAIL 4개 — 형태 B는 아직 형태 A로 그려져 구분선이 있고(`Expected WHITE Was BLACK`), 변경 칩이 없고, 범위 밖 layout에도 헤더·푸터가 그려진다.

- [ ] **Step 3: 구현**

`render.cpp`의 익명 namespace 안, `drawInfoA` 앞에 추가:

```cpp
constexpr int16_t kInfoChipLift = 18;  // ⚠️ 값 베이스라인 → 변경 칩 윗변
constexpr int16_t kNextLabelGap = 10;  // "다음 수업" ↔ 아래 줄
constexpr int16_t kNextTimeGap = 16;   // 시작 시각 ↔ 과목명
constexpr int16_t kNoScheduleBase = 338;  // ⚠️ 정보 영역 세로 중앙
```

`drawInfoRow`를 폭을 돌려주도록 바꾼다(교체):

```cpp
int16_t drawInfoRow(Adafruit_GFX& g, int row, const char* label, const char* value) {
  drawText(g, kNanum20Regular, label, kLabelX, kInfoRowBase[row], GxEPD_BLACK);
  return drawText(g, kNanum28Bold, value, kValueX, kInfoRowBase[row], GxEPD_BLACK, kTrack28);
}
```

`drawInfoA`의 과목명 줄을 교체:

```cpp
  const int16_t subjW = drawInfoRow(g, 0, "과목명", m.cur.subj);
  if (m.cur.flags & 0x02)
    drawChip(g, kImgChipByeongyeong, (int16_t)(kValueX + subjW + 10), (int16_t)(kInfoRowBase[0] - kInfoChipLift));
```

`drawInfoA` 뒤에 추가:

```cpp
void drawInfoB(Adafruit_GFX& g, const RenderModel& m) {
  if (!(m.next.flags & 0x01)) {
    drawText(g, kNanum28Bold, "오늘 일정 없음", kPad, kNoScheduleBase, GxEPD_BLACK, kTrack28);
    return;
  }
  const int16_t blockH = (int16_t)(kNanum20Regular.cellH + kNextLabelGap + kNanum62ExtraBold.cellH);
  const int16_t top = (int16_t)(kInfoY + (kInfoH - blockH) / 2);
  drawText(g, kNanum20Regular, "다음 수업", kPad, (int16_t)(top + kNanum20Regular.baseline), GxEPD_BLACK);
  const int16_t base =
      (int16_t)(top + kNanum20Regular.cellH + kNextLabelGap + kNanum62ExtraBold.baseline);
  char hm[6];
  formatHM(m.next.sH, m.next.sM, hm, sizeof hm);
  const int16_t tw = drawText(g, kNanum62ExtraBold, hm, kPad, base, GxEPD_BLACK, kTrack62);
  drawText(g, kNanum28Bold, m.next.subj, (int16_t)(kPad + tw + kNextTimeGap), base, GxEPD_BLACK, kTrack28);
}
```

`renderLayout`을 교체:

```cpp
void renderLayout(Adafruit_GFX& gfx, const RenderModel& m) {
  gfx.fillScreen(GxEPD_WHITE);
  if (m.layout < 1 || m.layout > 7) return;  // 8 은 Task 5.2, 그 밖은 흰 화면(⚠️ 열린 질문 5)
  drawHeader(gfx, m);
  drawStatusBand(gfx, m);
  if (m.layout == 4)
    drawInfoB(gfx, m);
  else
    drawInfoA(gfx, m);
  drawTodayList(gfx, m);
  gfx.fillRect(kSplitX, kBandY, 2, (int16_t)(kFooterY - kBandY), GxEPD_BLACK);
  drawFooter(gfx, m);
}
```

- [ ] **Step 4: 통과 확인**

Run: `$PIO test -e native -f test_render_layout`
Expected: PASS — `13 test cases: 13 succeeded`

Run: `$PIO test -e native` → `90 test cases: 90 succeeded` / `$PIO run -e native_preview` → SUCCESS / `$PIO check ...` → HIGH 0·MEDIUM 0

- [ ] **Step 5: 커밋**

```bash
git add lib/render/render.cpp test/test_render_layout/test_main.cpp
git commit -m "$(cat <<'EOF'
feat(firmware): 정보 형태 B·변경 칩·범위 밖 layout (dh-04 Task 5.1)

- layout 4(빈강의실): 다음 수업 시작 시각 62/800 + 과목명 28/700, 다음 수업이 없으면 "오늘 일정 없음"
- cur.flags bit1 이면 과목명 뒤에 변경 칩
- layout 이 1~8 밖이면 흰 화면만 그린다
EOF
)"
```

---

### Task 5.2: layout 8 — 설정 대기(전폭)

**Files:**
- Modify: `firmware/lib/render/render.cpp`
- Modify: `firmware/test/test_render_layout/test_main.cpp`

**Interfaces:**
- Consumes: `kImgTitleSeoljeongdaegi`, `kNanum62ExtraBold`, `kNanum20Bold`, `RenderModel::newTag`
- Produces: 변화 없음

- [ ] **Step 1: 실패하는 테스트 추가**

```cpp
static RenderModel layout8Model() {
  RenderModel m{};
  m.layout = 8;
  strcpy(m.newTag, "NEW-1A7F");
  return m;
}

void test_layout8_has_no_split_list_footer() {
  HostGfx g;
  renderLayout(g, layout8Model());
  TEST_ASSERT_EQUAL(HColor::BLACK, g.pixelAt(400, 50));   // 헤더 하단선은 있다
  TEST_ASSERT_EQUAL(HColor::WHITE, g.pixelAt(498, 100));  // 좌우 분할 없음
  TEST_ASSERT_EQUAL(HColor::WHITE, g.pixelAt(790, 470));  // 푸터 없음
  TEST_ASSERT_EQUAL_INT(0, countColor(g, 0, 0, 800, 480, HColor::RED));
  TEST_ASSERT_GREATER_THAN_INT(30, countColor(g, 24, 5, 200, 48, HColor::BLACK));  // "미설정 단말"
}

void test_layout8_title_and_new_tag_chip() {
  HostGfx g;
  renderLayout(g, layout8Model());
  TEST_ASSERT_GREATER_THAN_INT(1000, countColor(g, 48, 150, 300, 240, HColor::BLACK));  // "설정 대기" 62/800
  TEST_ASSERT_GREATER_THAN_INT(3000, countColor(g, 48, 260, 400, 380, HColor::BLACK));  // NEW 칩 흑 바탕
  TEST_ASSERT_GREATER_THAN_INT(500, countColor(g, 48, 260, 400, 380, HColor::WHITE));   // 칩 안 흰 글자
}

void test_layout8_empty_tag_omits_chip() {
  RenderModel m = layout8Model();
  m.newTag[0] = '\0';
  HostGfx g;
  renderLayout(g, m);
  // 태그가 없으면 제목·부제 두 덩어리만 세로 중앙(y 221~310)에 온다.
  TEST_ASSERT_GREATER_THAN_INT(1000, countColor(g, 48, 200, 300, 290, HColor::BLACK));  // 제목은 그린다
  TEST_ASSERT_EQUAL_INT(0, countColor(g, 48, 320, 800, 480, HColor::BLACK));  // 칩·안내 2줄 없음(⚠️ 열린 질문 7)
}
```

`main()`에 등록:

```cpp
  RUN_TEST(test_layout8_has_no_split_list_footer);
  RUN_TEST(test_layout8_title_and_new_tag_chip);
  RUN_TEST(test_layout8_empty_tag_omits_chip);
```

`test_out_of_range_layout_is_blank`는 그대로 둔다(0·9·255).

- [ ] **Step 2: 실패 확인**

Run: `$PIO test -e native -f test_render_layout`
Expected: FAIL 3개 — layout 8은 지금 흰 화면이라 헤더선·제목·칩이 없다.

- [ ] **Step 3: 구현**

`render.cpp` 익명 namespace 안, `drawFooter` 뒤에 추가:

```cpp
// layout 8 — terminal-epaper.md "layout 8 — 설정 대기 (전폭)"
constexpr int16_t kSetupPad = 48;
constexpr int16_t kSetupTitleGap = 8;   // 제목 ↔ 부제
constexpr int16_t kSetupBlockGap = 22;  // 부제 ↔ NEW 칩
constexpr int16_t kSetupChipPadY = 14;
constexpr int16_t kSetupChipPadX = 24;
constexpr int16_t kSetupChipTextGap = 20;  // NEW 칩 ↔ 안내 2줄
constexpr int16_t kSetupLineGap = 8;       // ⚠️ 안내 2줄 사이

void drawSetup(Adafruit_GFX& g, const RenderModel& m) {
  g.fillRect(0, kHeaderLineY, kW, 2, GxEPD_BLACK);
  drawText(g, kNanum20Bold, "미설정 단말", kPad, kHeaderBase, GxEPD_BLACK);

  const BitmapImage& title = kImgTitleSeoljeongdaegi;
  const bool hasTag = m.newTag[0] != '\0';
  const int16_t chipH = (int16_t)(2 * kSetupChipPadY + kNanum62ExtraBold.cellH);
  const int16_t blockH = (int16_t)(title.h + kSetupTitleGap + kNanum20Regular.cellH +
                                   (hasTag ? kSetupBlockGap + chipH : 0));
  const int16_t top = (int16_t)(kBandY + (kH - kBandY - blockH) / 2);
  drawImage(g, title, kSetupPad, top, GxEPD_BLACK);
  drawText(g, kNanum20Regular, "아직 어느 강의실에도 배정되지 않았습니다", kSetupPad,
           (int16_t)(top + title.h + kSetupTitleGap + kNanum20Regular.baseline), GxEPD_BLACK);
  if (!hasTag) return;

  const int16_t chipTop = (int16_t)(top + title.h + kSetupTitleGap + kNanum20Regular.cellH + kSetupBlockGap);
  const int16_t chipW = (int16_t)(textWidth(kNanum62ExtraBold, m.newTag, kTrack62) + 2 * kSetupChipPadX);
  g.fillRect(kSetupPad, chipTop, chipW, chipH, GxEPD_BLACK);
  drawText(g, kNanum62ExtraBold, m.newTag, (int16_t)(kSetupPad + kSetupChipPadX),
           (int16_t)(chipTop + kSetupChipPadY + kNanum62ExtraBold.baseline), GxEPD_WHITE, kTrack62);

  const int16_t tx = (int16_t)(kSetupPad + chipW + kSetupChipTextGap);
  const int16_t linesTop = (int16_t)(chipTop + (chipH - (2 * kNanum20Regular.cellH + kSetupLineGap)) / 2);
  drawText(g, kNanum20Regular, "관리자 화면에서", tx, (int16_t)(linesTop + kNanum20Regular.baseline), GxEPD_BLACK);
  drawText(g, kNanum20Regular, "이 번호를 강의실에 배정하세요", tx,
           (int16_t)(linesTop + kNanum20Regular.cellH + kSetupLineGap + kNanum20Regular.baseline), GxEPD_BLACK);
}
```

`renderLayout`의 범위 검사 줄을 교체:

```cpp
  if (m.layout == 8) {
    drawSetup(gfx, m);
    return;
  }
  if (m.layout < 1 || m.layout > 7) return;  // 범위 밖은 흰 화면(⚠️ 열린 질문 5)
```

- [ ] **Step 4: 통과 확인**

Run: `$PIO test -e native -f test_render_layout` → `16 test cases: 16 succeeded`
Run: `$PIO test -e native` → `93 test cases: 93 succeeded` / `native_preview` SUCCESS / `pio check` HIGH 0·MEDIUM 0

- [ ] **Step 5: 커밋**

```bash
git add lib/render/render.cpp test/test_render_layout/test_main.cpp
git commit -m "$(cat <<'EOF'
feat(firmware): layout 8 설정 대기 전폭 화면 (dh-04 Task 5.2)

- 헤더 "미설정 단말" 20/700, 제목 62/800 이미지, NEW 칩(흑 바탕·흰 글자 62/800) + 안내 2줄
- 좌우 분할·상태 띠·오늘 목록·푸터를 그리지 않는다
- newTag 가 비면 칩과 안내 2줄을 생략한다
EOF
)"
```

---

### Task 6.1: 픽스처 8개 + PNG 8장 + 게이트

**Files:**
- Create: `firmware/test/fixtures/render/layout1_class.json` ~ `layout8_setup.json`(8개)
- Delete: `firmware/test/fixtures/render/smoke_basic.json`
- Modify: `firmware/test/test_render_preview/test_main.cpp`(픽스처 경로)

**Interfaces:**
- Consumes: `parseFixtureFile`(S3 spec §4.4 스키마 — snake_case), `render_preview.py`
- Produces: `test/fixtures/render/_out/layout*.png` 8장(gitignore, 검토용)

- [ ] **Step 1: 픽스처 8개 작성**

공통: 필드는 S3 spec §4.4 그대로. `now_str`·`date_str`·`batt_mv`는 화면에 쓰지 않지만 스키마 예시에 맞춰 넣는다.

`layout1_class.json`(수업중, 변경 없음):

```json
{
  "name": "layout1_class",
  "layout": 1, "bld": "E", "room": 301, "unit": 1,
  "now_str": "13:20", "date_str": "09.30", "weekday": 3,
  "prev": {"subj": "자료구조", "prof": "이교수", "s_h": 9, "s_m": 0, "e_h": 10, "e_m": 50, "type": 1, "flags": 1},
  "cur":  {"subj": "캡스톤디자인", "prof": "김교수", "s_h": 13, "s_m": 0, "e_h": 14, "e_m": 50, "type": 1, "flags": 1},
  "next": {"subj": "웹프로그래밍", "prof": "박교수", "s_h": 15, "s_m": 0, "e_h": 16, "e_m": 50, "type": 1, "flags": 1},
  "n_today": 4,
  "today": [
    {"s_h": 9, "s_m": 0, "e_h": 10, "e_m": 50, "subj": "자료구조", "type": 1},
    {"s_h": 13, "s_m": 0, "e_h": 14, "e_m": 50, "subj": "캡스톤디자인", "type": 1},
    {"s_h": 15, "s_m": 0, "e_h": 16, "e_m": 50, "subj": "웹프로그래밍", "type": 1},
    {"s_h": 18, "s_m": 0, "e_h": 18, "e_m": 45, "subj": "영어회화", "type": 1}
  ],
  "new_tag": "",
  "batt_mv": 3900
}
```

`layout2_break.json`(쉬는시간 — BLACK, 보조 문구는 `next.sH:sM`):

```json
{
  "name": "layout2_break",
  "layout": 2, "bld": "E", "room": 301, "unit": 1,
  "now_str": "13:55", "date_str": "09.30", "weekday": 3,
  "prev": {"subj": "", "prof": "", "s_h": 0, "s_m": 0, "e_h": 0, "e_m": 0, "type": 0, "flags": 0},
  "cur":  {"subj": "캡스톤디자인", "prof": "김교수", "s_h": 13, "s_m": 0, "e_h": 15, "e_m": 50, "type": 1, "flags": 1},
  "next": {"subj": "캡스톤디자인", "prof": "김교수", "s_h": 14, "s_m": 0, "e_h": 15, "e_m": 50, "type": 1, "flags": 1},
  "n_today": 2,
  "today": [
    {"s_h": 9, "s_m": 0, "e_h": 10, "e_m": 50, "subj": "자료구조", "type": 1},
    {"s_h": 13, "s_m": 0, "e_h": 15, "e_m": 50, "subj": "캡스톤디자인", "type": 1}
  ],
  "new_tag": "",
  "batt_mv": 3900
}
```

`layout3_cancel.json`(휴강 — BLACK):

```json
{
  "name": "layout3_cancel",
  "layout": 3, "bld": "E", "room": 301, "unit": 1,
  "now_str": "10:10", "date_str": "09.30", "weekday": 3,
  "prev": {"subj": "", "prof": "", "s_h": 0, "s_m": 0, "e_h": 0, "e_m": 0, "type": 0, "flags": 0},
  "cur":  {"subj": "데이터베이스", "prof": "최교수", "s_h": 10, "s_m": 0, "e_h": 11, "e_m": 50, "type": 3, "flags": 1},
  "next": {"subj": "", "prof": "", "s_h": 0, "s_m": 0, "e_h": 0, "e_m": 0, "type": 0, "flags": 0},
  "n_today": 1,
  "today": [
    {"s_h": 10, "s_m": 0, "e_h": 11, "e_m": 50, "subj": "데이터베이스", "type": 3}
  ],
  "new_tag": "",
  "batt_mv": 3900
}
```

`layout4_empty.json`(빈강의실 — 형태 B):

```json
{
  "name": "layout4_empty",
  "layout": 4, "bld": "E", "room": 301, "unit": 1,
  "now_str": "12:20", "date_str": "09.30", "weekday": 3,
  "prev": {"subj": "자료구조", "prof": "이교수", "s_h": 9, "s_m": 0, "e_h": 10, "e_m": 50, "type": 1, "flags": 1},
  "cur":  {"subj": "", "prof": "", "s_h": 0, "s_m": 0, "e_h": 0, "e_m": 0, "type": 0, "flags": 0},
  "next": {"subj": "캡스톤디자인", "prof": "김교수", "s_h": 13, "s_m": 0, "e_h": 14, "e_m": 50, "type": 1, "flags": 1},
  "n_today": 2,
  "today": [
    {"s_h": 9, "s_m": 0, "e_h": 10, "e_m": 50, "subj": "자료구조", "type": 1},
    {"s_h": 13, "s_m": 0, "e_h": 14, "e_m": 50, "subj": "캡스톤디자인", "type": 1}
  ],
  "new_tag": "",
  "batt_mv": 3900
}
```

`layout5_exam.json`(시험중 — RED, 변경 배지):

```json
{
  "name": "layout5_exam",
  "layout": 5, "bld": "E", "room": 301, "unit": 1,
  "now_str": "14:30", "date_str": "09.30", "weekday": 3,
  "prev": {"subj": "", "prof": "", "s_h": 0, "s_m": 0, "e_h": 0, "e_m": 0, "type": 0, "flags": 0},
  "cur":  {"subj": "운영체제", "prof": "정교수", "s_h": 14, "s_m": 0, "e_h": 15, "e_m": 50, "type": 2, "flags": 3},
  "next": {"subj": "", "prof": "", "s_h": 0, "s_m": 0, "e_h": 0, "e_m": 0, "type": 0, "flags": 0},
  "n_today": 2,
  "today": [
    {"s_h": 9, "s_m": 0, "e_h": 10, "e_m": 50, "subj": "자료구조", "type": 1},
    {"s_h": 14, "s_m": 0, "e_h": 15, "e_m": 50, "subj": "운영체제", "type": 2}
  ],
  "new_tag": "",
  "batt_mv": 3900
}
```

`layout6_special.json`(특강 — RED, 목록 12개로 `n개 더` 확인):

```json
{
  "name": "layout6_special",
  "layout": 6, "bld": "E", "room": 301, "unit": 1,
  "now_str": "14:10", "date_str": "09.30", "weekday": 3,
  "prev": {"subj": "", "prof": "", "s_h": 0, "s_m": 0, "e_h": 0, "e_m": 0, "type": 0, "flags": 0},
  "cur":  {"subj": "AI 특강", "prof": "외부강사", "s_h": 14, "s_m": 0, "e_h": 14, "e_m": 50, "type": 5, "flags": 1},
  "next": {"subj": "알고리즘", "prof": "한교수", "s_h": 15, "s_m": 0, "e_h": 15, "e_m": 50, "type": 1, "flags": 1},
  "n_today": 12,
  "today": [
    {"s_h": 8, "s_m": 0, "e_h": 8, "e_m": 50, "subj": "자료구조", "type": 1},
    {"s_h": 9, "s_m": 0, "e_h": 9, "e_m": 50, "subj": "운영체제", "type": 1},
    {"s_h": 10, "s_m": 0, "e_h": 10, "e_m": 50, "subj": "데이터베이스", "type": 1},
    {"s_h": 11, "s_m": 0, "e_h": 11, "e_m": 50, "subj": "네트워크", "type": 1},
    {"s_h": 12, "s_m": 0, "e_h": 12, "e_m": 50, "subj": "웹프로그래밍", "type": 1},
    {"s_h": 13, "s_m": 0, "e_h": 13, "e_m": 50, "subj": "캡스톤디자인", "type": 1},
    {"s_h": 14, "s_m": 0, "e_h": 14, "e_m": 50, "subj": "AI 특강", "type": 5},
    {"s_h": 15, "s_m": 0, "e_h": 15, "e_m": 50, "subj": "알고리즘", "type": 1},
    {"s_h": 16, "s_m": 0, "e_h": 16, "e_m": 50, "subj": "임베디드", "type": 1},
    {"s_h": 17, "s_m": 0, "e_h": 17, "e_m": 50, "subj": "스터디", "type": 6},
    {"s_h": 18, "s_m": 0, "e_h": 18, "e_m": 45, "subj": "영어회화", "type": 1},
    {"s_h": 19, "s_m": 0, "e_h": 19, "e_m": 45, "subj": "자료구조Ⅱ", "type": 2}
  ],
  "new_tag": "",
  "batt_mv": 3900
}
```

`layout7_rental.json`(대여중 — RED):

```json
{
  "name": "layout7_rental",
  "layout": 7, "bld": "E", "room": 301, "unit": 1,
  "now_str": "17:20", "date_str": "09.30", "weekday": 3,
  "prev": {"subj": "", "prof": "", "s_h": 0, "s_m": 0, "e_h": 0, "e_m": 0, "type": 0, "flags": 0},
  "cur":  {"subj": "스터디 대여", "prof": "홍길동", "s_h": 17, "s_m": 0, "e_h": 18, "e_m": 30, "type": 6, "flags": 1},
  "next": {"subj": "", "prof": "", "s_h": 0, "s_m": 0, "e_h": 0, "e_m": 0, "type": 0, "flags": 0},
  "n_today": 2,
  "today": [
    {"s_h": 13, "s_m": 0, "e_h": 14, "e_m": 50, "subj": "캡스톤디자인", "type": 1},
    {"s_h": 17, "s_m": 0, "e_h": 18, "e_m": 30, "subj": "스터디 대여", "type": 6}
  ],
  "new_tag": "",
  "batt_mv": 3900
}
```

`layout8_setup.json`(설정 대기):

```json
{
  "name": "layout8_setup",
  "layout": 8, "bld": " ", "room": 0, "unit": 0,
  "now_str": "", "date_str": "", "weekday": 0,
  "prev": {"subj": "", "prof": "", "s_h": 0, "s_m": 0, "e_h": 0, "e_m": 0, "type": 0, "flags": 0},
  "cur":  {"subj": "", "prof": "", "s_h": 0, "s_m": 0, "e_h": 0, "e_m": 0, "type": 0, "flags": 0},
  "next": {"subj": "", "prof": "", "s_h": 0, "s_m": 0, "e_h": 0, "e_m": 0, "type": 0, "flags": 0},
  "n_today": 0,
  "today": [],
  "new_tag": "NEW-1A7F",
  "batt_mv": 3900
}
```

`subj` 바이트 수 확인: 가장 긴 `캡스톤디자인`·`웹프로그래밍`·`데이터베이스`가 18B, `자료구조Ⅱ`가 15B로 모두 20B 이하다.

- [ ] **Step 2: `smoke_basic.json` 삭제, 테스트 경로 교체**

```bash
git rm test/fixtures/render/smoke_basic.json
```

`test/test_render_preview/test_main.cpp`에서 두 줄을 바꾼다:

```cpp
  TEST_ASSERT_TRUE(parseFixtureFile("test/fixtures/render/layout1_class.json", m, name, sizeof(name)));
```
```cpp
  TEST_ASSERT_TRUE(g.savePNG("layout1_class_out.png"));
  FILE* f = fopen("layout1_class_out.png", "rb");
```
```cpp
  remove("layout1_class_out.png");
```

- [ ] **Step 3: 게이트 전체 실행**

Run: `$PIO test -e native` → `93 test cases: 93 succeeded`
Run: `$PIO run -e native_preview` → SUCCESS
Run: `$PIO check -e native --fail-on-defect medium --fail-on-defect high` → PASSED, HIGH 0 / MEDIUM 0

- [ ] **Step 4: PNG 8장 생성**

```bash
python tools/render_preview.py
```
Expected: `wrote ... layout1_class.png` ~ `layout8_setup.png` 8줄, 실패 0.

8장을 사용자에게 보여 준다(mh 검토).

- [ ] **Step 5: 커밋**

```bash
git add test/fixtures/render/ test/test_render_preview/test_main.cpp
git commit -m "$(cat <<'EOF'
test(firmware): 레이아웃 8종 픽스처 + 프리뷰 파이프라인 경로 교체 (dh-04 Task 6)

- layout1_class ~ layout8_setup — 변경 배지(5), 목록 12개 n개 더(6), 로마 숫자 과목(6), 설정 대기(8) 포함
- smoke_basic.json 을 layout1_class.json 으로 대체
EOF
)"
```

- [ ] **Step 6: PR 초안(생성하지 않는다)**

PR 본문 초안을 출처표와 함께 사용자에게 보여 준다. 이 PR은 폰트·이미지 자산 PR(Task 3)이 `main`에 머지된 뒤에 올린다 — `lib/render/`가 `font_data.h`·`image_data.h`에 기댄다.

---

## 열린 질문 (⚠️ 사용자·mh 확인 필요)

1. **현재 행의 시간도 700으로?** 상위 plan §3.6에서 "시간·과목 모두 700"으로 정했지만, 그때 쓴 목업은 시간을 **20px**로 그렸다. 스펙의 목록 시각은 **16px/400**(`terminal-epaper.md:146`)이다. 시간을 700으로 하려면 16px/700 숫자 자산(숫자 10자 + `:`)이 따로 필요하고 아직 없다. 이 계획은 **스펙대로 시각 16/400, 과목만 20/700**으로 구현한다. mh 요청 묶음(상위 plan §7-4)에 이 사실을 함께 올린다.
2. **창 기준 항목이 없을 때**(`cur`·`next` 둘 다 없음, 예: 하루 일정이 끝난 뒤 `nToday > 9`) — 처음부터 보여 준다(`start = 0`). 마지막 쪽을 보여 주는 것이 더 자연스러울 수도 있다.
3. **정보 형태 B에서 행 구분선(y 291·365)을 그리지 않는다.** 스펙 선 표는 형태를 구분하지 않지만, 형태 B는 두 줄 한 덩어리라 구분선이 글자를 가른다.
4. **글자 목록 밖 글자는 빈칸 없이 건너뛴다.** 서버가 입력 단계에서 막기로 했으므로(#34) 렌더에 도착하면 안 되는 경우다.
5. **`layout`이 1~8 밖이면 흰 화면만 그린다.**
6. **세로 위치·칩 여백 상수**(`kHeaderBase` 등 ⚠️ 표시한 값) — Task 4.3 첫 PNG 검토로 정한다.
7. **layout 8에서 `newTag`가 비면** NEW 칩과 안내 2줄을 생략한다.
8. **색상 상수가 두 곳에 있다** — `host_gfx.h`(호스트)와 `render_colors.h`(`lib/render`). `lib/render`가 호스트 전용 헤더를 include할 수 없어서다. 값이 어긋나면 `test_render_layout`의 색 비교가 실패한다.

## 실행

- 브랜치 `dh`. Task 4.3 Step 7에서 **반드시 멈추고** 첫 PNG 검토를 받는다.
- 테스트 수 기대값은 4.1 61 → 4.2 77 → 4.3 86 → 5.1 90 → 5.2 93 → 6.1 93이다. 다르면 멈추고 원인을 보고한다.
- PR 순서: #66(`render_model.h` 이동) → #69(호스트 심) → 자산 PR(Task 3) → 이 계획의 PR(Task 4~6).
