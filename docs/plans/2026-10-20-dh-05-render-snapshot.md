# dh-05 — 경계 픽스처 15개 + PNG 스냅샷 테스트 + 레이아웃 리뷰 반영 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- 생성일시: 2026-10-20
- 표기: `[확인]` 직접 실행·열람 / `[추정]` 확인 안 함 / ⚠️ 작성자가 고른 값 — 검토 대상

**Goal:** 렌더 화면 전체를 정답 PNG와 픽셀 단위로 비교하는 스냅샷 테스트를 만들고, 경계 케이스 픽스처 15개를 더해, 렌더 PR #89 리뷰(mh·wj·cw) 답을 반영한 뒤 정답을 확정한다.

**Architecture:** 호스트 전용 비교 모듈(`lib/host_gfx/snapshot`)이 `HostGfx` 프레임버퍼와 정답 PNG(stb_image로 디코드)를 비교해 다른 픽셀 수를 세고 차이 이미지를 쓴다. 스냅샷 테스트 하나가 `test/fixtures/render/*.json` 전부를 그려 `test/fixtures/render/snapshots/<이름>.png`와 대조한다. 정답은 `render_preview.py --update-snapshots` 한 명령으로 다시 만든다.

**Tech Stack:** C++17, PlatformIO `[env:native]`·`[env:native_preview]`, Unity, stb_image(디코드, 새 벤더)·stb_image_write v1.16(인코드, 기존), Python(PlatformIO penv)

**Spec:** 진도표 dh-05(`docs/progress.html`: "mh·wj 리뷰 반영, 긴 과목명·오늘 0개·저전압 등 15개 픽스처, Unity PNG 스냅샷 테스트. cw와 RenderModel 최종 ← dh-04, cw-11"), `docs/specs/2026-09-16-s3-render-design.md` §3·§4, `docs/design/screens/terminal-epaper.md`

## 선행·전제

- dh-04 렌더 PR **#89** 위에 쌓는다. 브랜치 `feature/dh-05-snapshot`을 `feature/render-port`에서 딴다. #89가 squash 머지되면 이 브랜치의 dh-05 커밋만 새 `main` 위로 옮겨 PR을 연다(#73·#83·#89와 같은 방식).
- cw-11(RenderModel 동결)은 #77로 끝났다 `[확인]`. 진도표의 "cw와 RenderModel 최종"은 #77로 충족 — 이 plan에서 `RenderModel`은 바꾸지 않는다.
- 진도표 예시 "저전압"은 화면 스펙과 어긋난다: `terminal-epaper.md:211` "`battMv`는 일부러 쓰지 않는다" `[확인]`. 그래서 저전압 픽스처는 **화면이 바뀌지 않음**을 확인하는 용도로 둔다.

## Global Constraints

- 픽스처 경로 `firmware/test/fixtures/render/*.json`(로드맵 §6.3). 형식은 기존 8개와 같다(snake_case, `fixture_parse` 가 읽는 키). 모르는 키는 무시된다 `[확인]`(`test_legacy_now_str_and_prev_keys_are_ignored`).
- 렌더는 `RenderModel` 밖을 읽지 않고 줄바꿈·말줄임을 하지 않는다(S3 spec §3). 시그니처 `void renderLayout(Adafruit_GFX& gfx, const RenderModel& model);`는 그대로.
- `lib/render/`는 `host_gfx.h`를 include하지 않는다. 스냅샷 코드는 호스트 전용(`lib/host_gfx/`)에만 둔다.
- 벤더 코드는 수정하지 않는다. 새 벤더는 `lib/host_gfx/vendor/`에 두면 `check_src_filters`(`-<lib/*/vendor/>`)가 분석에서 뺀다 `[확인]`.
- 테스트 CWD는 `firmware/`(`test_render_preview` 와 같은 전제) `[확인]`.
- 게이트: `pio test -e native` 전부 통과, `pio run -e native_preview` SUCCESS, `pio check -e native --fail-on-defect medium --fail-on-defect high` PASSED. pre-commit 500 KB 파일 훅.
- 정답 PNG 는 커밋한다(CI 가 같은 비교를 돈다). 현재 8장 합계 134,136 B `[확인]` → 23장이면 약 400 KB `[추정]`.

## Review Focus

1. 정답 PNG가 없는 픽스처 → 테스트가 **실패**하고 "정답 없음 — `render_preview.py --update-snapshots`"를 알린다(조용히 통과하지 않는다) — Task 2 `test_snapshots_match`
2. 정답 크기가 800×480이 아님(누가 편집기로 잘랐음) → 크래시 없이 실패 — Task 1 `test_size_mismatch_is_not_loaded`
3. 픽스처는 지웠는데 정답만 남음 → 실패("짝 없는 정답") — Task 2 `test_no_orphan_snapshots`
4. 정답을 이미지 편집기로 다시 저장해 알파 채널·팔레트 PNG가 됨 → 3채널로 강제 디코드해 같은 픽셀이면 통과 — Task 1 `test_rgba_baseline_compares_by_rgb`
5. Windows·Linux가 다른 픽셀을 그림 → CI(Linux)가 커밋된 정답(Windows에서 생성)과 비교해 잡는다 — Task 2 끝 CI 확인

---

## 파일

| 파일 | 책임 |
|---|---|
| `firmware/lib/host_gfx/vendor/stb_image.h` | (새 벤더) PNG 디코드. stb_image_write v1.16과 같은 nothings/stb 저장소의 릴리스 |
| `firmware/lib/host_gfx/snapshot.h/.cpp` | 정답 PNG 대조·차이 이미지 쓰기 |
| `firmware/test/test_snapshot/test_main.cpp` | 비교 모듈 단위 테스트 |
| `firmware/test/test_render_snapshot/test_main.cpp` | 픽스처 전부 × 정답 PNG |
| `firmware/test/fixtures/render/snapshots/*.png` | 정답(커밋) |
| `firmware/test/fixtures/render/edge_*.json` | 경계 픽스처 15개 |
| `firmware/tools/render_preview.py` | `--update-snapshots` 추가 |

---

### Task 1: 정답 PNG 비교 모듈

**Files:**
- Create: `firmware/lib/host_gfx/vendor/stb_image.h`, `firmware/lib/host_gfx/snapshot.h`, `firmware/lib/host_gfx/snapshot.cpp`
- Test: `firmware/test/test_snapshot/test_main.cpp`

**Interfaces:**
- Consumes: `HostGfx::pixelAt(int16_t, int16_t) const -> HColor`, `hcolorToRGB(HColor, uint8_t&, uint8_t&, uint8_t&)`, `HostGfx::savePNG(const char*) const -> bool`(기존, `host_gfx.h`)
- Produces:

```cpp
// snapshot.h
struct SnapshotDiff {
  bool baselineLoaded;  // 파일 없음·디코드 실패·크기가 gfx 와 다름이면 false
  long diffPixels;      // baselineLoaded 일 때만 의미. RGB 가 하나라도 다르면 1 픽셀
};
SnapshotDiff compareToBaseline(const HostGfx& g, const char* baselinePng);
// 차이 이미지: 같은 픽셀은 흐리게(흰 그대로, 검정 → (160,160,160), 빨강 → (255,180,180)),
// 다른 픽셀은 (0,0,255). 정답을 못 읽으면 false.
bool saveDiffPNG(const HostGfx& g, const char* baselinePng, const char* outPng);
```

- 디코드는 `stbi_load(path, &w, &h, &n, 3)`(채널 3으로 강제). `STB_IMAGE_IMPLEMENTATION`은 `snapshot.cpp`에서만 정의. 쓰기는 기존 `stb_image_write`(구현 정의는 `host_gfx.cpp`에 있음 — 다시 정의하지 않는다).
- `HostGfx`에 픽셀 버퍼 접근자를 새로 만들지 않는다 — `pixelAt` 반복으로 충분(800×480).
- ⚠️ 차이 이미지 색은 작성자가 고른 값(실기와 무관한 호스트 산출물).

- [ ] **Step 1: 실패 테스트 작성** — 각 테스트는 `HostGfx`를 그려 임시 정답을 `savePNG`로 만든 뒤 대조한다.
  - `test_identical_is_zero`: 같은 그림 저장 → `{true, 0}`
  - `test_one_pixel_differs`: 정답 저장 후 `drawPixel(5,7,GxEPD_RED)` → `{true, 1}`
  - `test_missing_file_is_not_loaded`: 없는 경로 → `baselineLoaded == false`
  - `test_size_mismatch_is_not_loaded`: `HostGfx small(10,10)` 정답 → 800×480 과 대조 → `false`
  - `test_rgba_baseline_compares_by_rgb`: `stbi_write_png(..., 4채널)`로 같은 색 RGBA 정답 → `{true, 0}`
  - `test_diff_png_marks_changed_pixel_blue`: 차이 이미지를 `stbi_load`로 다시 읽어 (5,7) = (0,0,255), (0,0) = (255,255,255)
  - 임시 파일은 각 테스트 끝에 `remove`
- [ ] **Step 2: 실패 확인** — `pio test -e native -f test_snapshot` → 컴파일 실패(`snapshot.h` 없음)
- [ ] **Step 3: 구현** — 위 Interfaces 대로 `snapshot.cpp` 작성, `stb_image.h`(nothings/stb, 공개 도메인/MIT) 벤더링. 파일 머리에 출처 URL·커밋을 주석으로 남긴다(벤더 파일 자체는 무수정).
- [ ] **Step 4: 통과 확인** — `pio test -e native -f test_snapshot` 6/6, 전체 `pio test -e native`, `pio check` PASSED

---

### Task 2: 스냅샷 테스트 + 정답 재생성 명령 + 기존 8장 정답

**Files:**
- Create: `firmware/test/test_render_snapshot/test_main.cpp`, `firmware/test/fixtures/render/snapshots/layout1_class.png` … `layout8_setup.png`
- Modify: `firmware/tools/render_preview.py`

**Interfaces:**
- Consumes: Task 1 `compareToBaseline`, `saveDiffPNG`; 기존 `parseFixtureFile(const char*, RenderModel&, char*, size_t) -> bool`, `renderLayout(Adafruit_GFX&, const RenderModel&)`
- Produces: 정답 경로 규칙 `test/fixtures/render/snapshots/<픽스처 파일 stem>.png`, 차이 출력 `test/fixtures/render/_out/<stem>_diff.png`(gitignore 대상 `_out/` 재사용)

- 픽스처 목록은 `std::filesystem::directory_iterator("test/fixtures/render")`의 `*.json`을 이름순으로 — 새 픽스처를 더하면 테스트 수정 없이 대상이 된다.
- 실패 메시지 한 줄 형식(픽스처마다): `<stem>: <N> px 다름 → _out/<stem>_diff.png` / `<stem>: 정답 없음 — python tools/render_preview.py --update-snapshots` / `<stem>: 픽스처 파싱 실패`. 모든 픽스처를 끝까지 돌고 실패를 모아 `TEST_FAIL_MESSAGE` 한 번.

- [ ] **Step 1: 실패 테스트 작성**
  - `test_snapshots_match`: 위 규칙대로 전 픽스처 대조, 실패 0이어야 통과
  - `test_no_orphan_snapshots`: `snapshots/*.png` 마다 같은 stem 의 `.json` 이 있어야 함
- [ ] **Step 2: 실패 확인** — 정답 폴더가 비어 있으므로 `test_snapshots_match` 가 8개 모두 "정답 없음"으로 실패
- [ ] **Step 3: 구현**
  - `render_preview.py`에 `--update-snapshots` 플래그: 출력 폴더를 `_out/` 대신 `snapshots/`로. 다른 동작(바이너리 탐색·실패 집계)은 그대로. 사용법을 모듈 docstring 에 한 줄 추가
  - `pio run -e native_preview` → `python tools/render_preview.py --update-snapshots` 로 8장 생성. 지금 `.superpowers/pr-images/render-pr/`와 바이트 단위로 같은지 `cmp` 로 확인(#89 와 같은 그림)
- [ ] **Step 4: 통과 확인** — `pio test -e native` 전체 통과. 일부러 `snapshots/layout1_class.png` 를 지워 "정답 없음" 실패, 픽셀 하나 바꾼 정답으로 "1 px 다름"과 차이 PNG 생성을 확인한 뒤 원복. push 후 CI firmware(Linux) 통과로 Review Focus 5 확인

---

### Task 3: 리뷰 답과 무관한 경계 픽스처 11개

**Files:**
- Create: 아래 11개 `firmware/test/fixtures/render/edge_*.json`, 같은 이름의 `snapshots/*.png`
- Modify: `firmware/test/test_render_snapshot/test_main.cpp`(저전압 동일성 테스트 1개)

**Interfaces:**
- Consumes: Task 2 스냅샷 테스트(새 픽스처는 자동 포함)
- Produces: 없음

각 픽스처는 무엇을 고정하는지 `"_note"` 키 한 줄로 적는다(파서가 무시). 오늘 목록 항목은 블록 슬롯(정각 시작·50분 수업, #74). ⚠️ 구성은 작성자가 고른 값.

| 파일 | layout | 핵심 입력 | 고정하는 것 |
|---|---|---|---|
| `edge_today_1.json` | 1 | `n_today` 1, cur = 그 항목 | 목록 한 행, 반전 1행 |
| `edge_today_9_exact.json` | 1 | 9개, cur 5번째 | N=9 딱 맞음 — `n개 더` 없음 |
| `edge_today_10_head.json` | 1 | 10개, cur 1번째 | start 0, 위쪽 없음, 끝 행 `↓ 2개 더` |
| `edge_today_12_both.json` | 1 | 12개, cur 4번째 | start 2, 첫 행 `↑ 3개 더`·끝 행 `↓ 2개 더`, 일정 7행 |
| `edge_today_24_tail.json` | 1 | 24개, cur 24번째 | start 15, 첫 행 `↑ 16개 더`, 아래쪽 없음 |

창 계산 근거(`render_logic.cpp:125-128` `[확인]`): `start = clamp(기준−1, 0, count−9)`, `moreAbove = start>0 ? start+1 : 0`, `moreBelow = start+9<count ? count−(start+8) : 0`.
| `edge_cur_not_in_today.json` | 1 | cur 시각이 `today[]` 에 없음 | 반전 행 없음, 다음 예정 기준 창 |
| `edge_all_type_chips.json` | 1 | 목록 type 1·2·3·5·6, cur flags bit1 | 칩 4종 + 정보 형태 A `변경` 칩 |
| `edge_roman_numerals.json` | 1 | 과목명에 `Ⅰ`–`Ⅹ` | Noto 대체 글리프가 정보·목록 양쪽에 그려짐 |
| `edge_glyph_fallbacks.json` | 1 | 목록 밖 글자(`똠`), 20 B 경계에서 잘린 UTF-8 | 없는 글자는 건너뜀, 잘린 시퀀스는 `?` 하나 |
| `edge_low_battery.json` | 1 | `layout1_class.json` 과 같고 `batt_mv` 3300 | 화면이 `layout1_class` 와 픽셀까지 같음 |
| `edge_header_footer_max.json` | 1 | `room` 65535, `unit` 255, `bld` `M` | 헤더 32/800 호수·푸터가 겹치지 않음(눈으로 확인) |

- `edge_glyph_fallbacks` 의 잘린 UTF-8 은 JSON 문자열로 못 쓴다(UTF-8 로 유효하지 않음) — 과목을 20 B 보다 길게 줘서 `fixture_parse` 의 `copyStr`(`strncpy(dest, src, cap-1)`, `subj[21]` → 20 B `[확인]`)가 자르게 한다. 한글 6자(18 B) + `A` + 한글 1자면 20 B 째가 한글 3바이트의 첫 바이트라 잘린 시퀀스가 된다 — Step 1 에서 바이트로 확인.

- [ ] **Step 1: 실패 테스트 작성** — `test_low_battery_screen_identical`: 두 픽스처를 각각 그려 800×480 전 픽셀 `pixelAt` 같음. 그리고 11개 JSON 을 만든다(정답 없음 → `test_snapshots_match` 실패)
- [ ] **Step 2: 실패 확인** — 11개 "정답 없음"
- [ ] **Step 3: 구현** — `--update-snapshots` 로 정답 생성, 11장을 하나씩 열어 `고정하는 것` 칸대로 그려졌는지 눈으로 확인. 기대와 다르면 렌더 버그 — 정답으로 굳히지 말고 멈추고 보고
- [ ] **Step 4: 통과 확인** — 전체 테스트·`native_preview`·`pio check`

---

### Task 4: 리뷰 답 대기 픽스처 4개(임시 정답)

**Files:**
- Create: 아래 4개 `edge_*.json`, 같은 이름의 `snapshots/*.png`

**Interfaces:**
- Consumes: Task 2
- Produces: Task 5 가 정답을 바꿀 대상

지금 동작으로 정답을 만들고, `"_pending"` 키에 무엇을 기다리는지 적는다(파서가 무시). Task 5 에서 답대로 고치고 키를 지운다.

| 파일 | layout | 핵심 입력 | 기다리는 답(#89) |
|---|---|---|---|
| `edge_long_subject.json` | 1 | 정보·목록 과목에 ASCII 20자(`ABCDEFGHIJKLMNOPQRST`), 목록에 칩 | mh: ASCII 과목과 type 칩 겹침 |
| `edge_today_0.json` | 4 | `n_today` 0, next 없음 | mh: 형태 B `오늘 일정 없음` 문구 |
| `edge_day_over.json` | 4 | 오늘 수업 3개 모두 지남, next 없음 | mh: 하루 끝난 뒤 `오늘 일정 없음`과 목록의 모순 |
| `edge_break_no_cur.json` | 2 | 쉬는시간, `cur.flags` 0, next 있음 | cw: 쉬는시간 동안 `cur` 에 싣는 값(지금은 `00:00 – 00:00`) |

- [ ] **Step 1: 실패 테스트 작성** — 4개 JSON(정답 없음 → 실패)
- [ ] **Step 2: 실패 확인** — 4개 "정답 없음"
- [ ] **Step 3: 구현** — `--update-snapshots`, 4장이 "지금 동작"과 같은지 확인(예: `edge_break_no_cur` 는 `00:00 – 00:00` 이 그려져야 지금 동작과 일치)
- [ ] **Step 4: 통과 확인** — 전체 게이트. 픽스처 합계 23(기존 8 + 15)

---

### Task 5: #89 리뷰 답 반영 → 정답 확정

**선행:** #89 의 mh·wj·cw 답. 답이 오기 전에는 시작하지 않는다.

**답 도착(2026-10-28)** — #89 cw 머지 코멘트와 #91(mh 스펙, 머지):
- 현재 행 시각 700: **안 함**. wj 의견: 없음
- `↑`·`↓` → **(a) 채운 삼각형** ▲▼: 밑변 10 · 높이 6, x 518, 세로 행 윗변 +15–20, 뒤 간격 6 + `n개 더`(16/400)
- 형태 B `next` 없음 → **`오늘 남은 수업 없음`**(28/700, 베이스라인 338). 목록 `nToday = 0` 의 `오늘 일정 없음`(20/400)은 그대로
- layout 7 2행 라벨 **`예약자`**(값은 `cur.prof`)
- 목록 과목·약어 겹침: 약어 자리(앞 8 포함)를 **행 높이 전체(36)** 만큼 행 바탕색으로 먼저 덮음
- 정보 행 넘침: 값 영역 x 146–476 을 넘치면 `변경` 칩을 오른쪽 끝 x 476 에 맞춰 붙이고(칩 자리 + 앞 간격 10 을 백으로 덮은 뒤), 정보 행을 다 그린 뒤 x 476–800 을 백으로 덮고 분할선·오늘 목록을 그린다
- **쉬는시간 `cur` = 곧 시작할 수업(다음 슬롯), `cur == next`**(cw). 렌더 코드는 그대로, 픽스처만 바꾼다 — `layout2_break` 의 `cur` 를 14:00 블록으로. `edge_break_no_cur` 는 상태 판단이 만들지 않는 조합이 되므로 "`cur` 없이 오는 경우 방어"로 두거나 지운다(Task 5 에서 판단)

**PR 분리(사용자 결정 2026-11-03)**: cw 가 "작게" 요청한 대로 Task 5 의 렌더 변경은 **별도 후속 PR 을 먼저** 올린다(`main` 에서 분기). 스냅샷 PR(Task 1–4)은 그 PR 이 머지된 뒤 새 화면으로 정답을 다시 만들어 올린다.

**Files:** 답에 따라 아래 표의 위치. 정답 PNG 는 바뀐 화면만 다시 생성.

답 → 고칠 곳(답이 "그대로"면 그 줄은 할 일 없음):

| 질문(#89) | 바꾸자고 하면 고칠 곳 | 영향 받는 정답 |
|---|---|---|
| 현재 행 시각 700 | `gen_fonts.py` FONTS 에 16/700 숫자 서브셋 추가 → 재굽기, `render.cpp` 목록 행 시각 폰트 | 목록이 있는 전부 |
| `↑`·`↓` 판독성 (a)/(b)/(c) | (a) `render.cpp` 에서 삼각형 그리기 (b) `gen_images.py` 에 화살표 이미지 (c) `render.cpp` 문구 | `n개 더` 가 나오는 픽스처 |
| `오늘 일정 없음` 문구 | `render.cpp` 형태 B 문자열 | `layout4_empty`, `edge_today_0`, `edge_day_over` |
| layout 7 예약자 라벨 | `render.cpp` 형태 A 라벨(layout 7 분기) — 새 라벨 글자는 20/400 전체 글자 안 | `layout7_rental` |
| ASCII 과목·칩 겹침 | 말줄임이면 S3 spec §3 "말줄임 안 함" 변경이 먼저 — spec 수정 후 `render.cpp` | `edge_long_subject` |
| 초기값(세로 위치 등) | `render.cpp` 상수 | 해당 영역 |
| wj 의견 | 내용에 따라 | — |
| cw: 쉬는시간 `cur` | 비워 보내면 형태 A 대신 무엇을 그릴지 화면 스펙(mh) 확인 후 `render.cpp` | `layout2_break`, `edge_break_no_cur` |

- [ ] **Step 1: 실패 테스트 작성** — 답마다 바뀌는 동작을 `test_render_layout`(또는 `test_render_logic`)에 단위 테스트로 먼저 고정. 예: 문구가 바뀌면 `statusSubline`/형태 B 문자열 테스트
- [ ] **Step 2: 실패 확인** — 새 단위 테스트 실패 + 스냅샷은 아직 옛 정답이라 통과
- [ ] **Step 3: 구현** — 표의 위치 수정 → 단위 테스트 통과 → 스냅샷이 바뀐 픽스처만 실패하는지 확인 → `--update-snapshots` → 바뀐 PNG 를 하나씩 열어 확인. `_pending` 키 삭제
- [ ] **Step 4: 통과 확인** — 전체 게이트. `git diff --stat snapshots/` 로 바뀐 정답이 표의 "영향 받는 정답"과 맞는지 대조

---

## PR

- 두 PR(사용자 결정 2026-11-03): ① 후속 PR — Task 5 의 렌더 변경 + `layout2_break` + PNG 8장 갱신(mh QA) ② 스냅샷 PR — Task 1–4 + 이 plan, 정답은 ① 머지 뒤 화면으로 다시 생성
- 순서: #89 머지(2026-10-28) → Task 1–4 를 `main` 기준 브랜치로 옮겨 커밋 → ① 후속 PR → ① 머지 → 스냅샷 브랜치를 새 `main` 위로, 정답 재생성 → 게이트·CI → ② PR

## Self-Review

- 스펙 대응: 진도표 dh-05 의 네 요소 — 리뷰 반영(Task 5), 픽스처 15개(Task 3 11개 + Task 4 4개), Unity PNG 스냅샷(Task 1·2), RenderModel 최종(#77 로 충족, 선행 절). 예시 세 개 중 "긴 과목명"은 `edge_long_subject`, "오늘 0개"는 `edge_today_0`, "저전압"은 `edge_low_battery`(화면 무변화로 재해석 — 스펙 근거 `terminal-epaper.md:211`).
- 시그니처: 스펙에 이름이 고정된 함수는 `renderLayout` 하나 — 바꾸지 않는다. 새 함수 2개(`compareToBaseline`, `saveDiffPNG`)는 Task 1 에서 정의하고 Task 2 가 같은 이름으로 쓴다.
- 사용자 확인 항목(⚠️): 차이 이미지 색, 경계 픽스처 15개 구성, `_note`·`_pending` 키 사용, 짝 없는 정답을 실패로 보는 규칙, PR 제목·분할 여부.
- 분량: 약 210줄.
