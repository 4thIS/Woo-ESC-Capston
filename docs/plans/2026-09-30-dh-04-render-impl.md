# dh-04 Task 4~6 — `renderLayout` 구현 계획 (요약본)

- 생성일시: 2026-09-30, 최종 갱신: 2026-09-30(구현 완료 후 요약본으로 정리)
- 상위 plan: `docs/plans/2026-09-20-dh-04-render-port.md` — 결정 D1~D7, Task 0~3·H. 이 문서는 그 §6 Task 4~6의 구성과 구현 중 결정을 담는다.
- 상태: **구현 완료.** 코드와 테스트는 렌더 PR에 있다. Step 단위 코드는 실행 중에만 쓰고 이 문서에는 남기지 않는다(코드가 원본).
- 표기: `[확인]` 직접 실행·열람 / `[추정]` 확인 안 함 / ⚠️ 작성자가 고른 값 — 검토 대상.

**Goal:** `RenderModel` 하나를 받아 스펙대로 800×480 3색 화면을 그리는 `renderLayout()`을 `firmware/lib/render/`에 만들고, 레이아웃 8종의 픽스처와 PNG를 뽑는다.

**Architecture:** 세 층. (1) `text` — UTF-8 문자열을 `BitmapFont`로 한 줄 그리기(v1 `ngNextCP`/`ngPrintLine` 대체). (2) `render_logic` — 픽셀을 찍지 않는 순수 판단(상태 띠 색, 상태명 이미지, 보조 문구, 요일, type 칩, 오늘 목록 창). (3) `render` — 스펙 좌표대로 영역을 그리는 `renderLayout()`. 호스트는 `HostGfx`, 실기는 GxEPD2가 같은 `Adafruit_GFX&`로 받는다. v1 `renderLayout`은 JSON·전역 display 기반의 다른 화면이라 코드를 옮기지 않고 UTF-8 해석·`drawBitmap` 방식만 가져왔다.

**Spec:** `docs/design/screens/terminal-epaper.md`(화면 원본), `docs/specs/2026-09-16-s3-render-design.md` §3·§4(인터페이스·제약)

## Global Constraints

- 캔버스 800×480, 가로. 색은 `GxEPD_WHITE`(0xFFFF)·`GxEPD_BLACK`(0x0000)·`GxEPD_RED`(0xF800) 셋뿐. 회색·안티에일리어싱 없음.
- 적색은 상태 띠 바탕에만. 반전(흑 채움 + 흰 글자)은 상태 띠(RED면 적색 면)·목록 현재 행·푸터·칩에만.
- 타입 6단계 고정: 78/800 상태명(이미지) · 62/800 · 32/800 · 28/700 · 20/400 · 16/400(칩류 16/700 이미지).
- 렌더는 `RenderModel` 밖을 읽지 않고, 줄바꿈·말줄임을 하지 않는다(S3 spec §3).
- 시그니처: `void renderLayout(Adafruit_GFX& gfx, const RenderModel& model);`(S3 spec §4.3)
- `lib/render/`는 호스트 전용 `host_gfx.h`를 include하지 않는다. 벤더 `adafruit_gfx_vendor/`는 수정하지 않는다.
- 게이트: `pio test -e native` 전부 통과, `pio run -e native_preview` SUCCESS, `pio check -e native --fail-on-defect medium --fail-on-defect high` HIGH 0 / MEDIUM 0.

## Review Focus (스펙이 말하지 않지만 사람이 기대하는 동작 — 모두 테스트로 고정)

1. 잘린 UTF-8(과목 20B 경계) → 종단 NUL 너머를 읽지 않고 `?` 하나 — `test_truncated_multibyte_stops_at_nul`
2. 글자 목록 밖 글자(예: `똠`) → 그 글자만 빠지고 간격 없이 이어진다 — `test_unknown_glyph_is_skipped`
3. `nToday` > 24(손상) → 24로 자른다 — `test_window_clamps_count_to_24`
4. `cur`가 `today[]`에 없음 → 반전 행 없이 다음 예정 항목 기준으로 창 — `test_window_cur_not_in_today_uses_next`
5. `layout`이 1~8 밖 → 흰 화면만 — `test_out_of_range_layout_is_blank`

## 파일

| 파일 | 책임 |
|---|---|
| `firmware/lib/render/text.h/.cpp` | UTF-8 → 코드포인트, 문자열 폭, 한 줄 그리기 |
| `firmware/lib/render/render_logic.h/.cpp` | 순수 판단 함수 |
| `firmware/lib/render/render_colors.h` | GxEPD2 색 상수(`#ifndef` 가드) — 실기는 GxEPD2, 호스트는 `host_gfx.h`가 같은 이름·값을 정의 |
| `firmware/lib/render/render.h/.cpp` | `renderLayout()` |
| `firmware/test/test_render_text/`, `test_render_logic/`, `test_render_layout/` | 단위·픽셀 테스트 |
| `firmware/tools/render_preview.cpp`, `test/test_render_preview/` | `smokeRender` → `renderLayout` 교체 |
| `firmware/test/fixtures/render/layout1_class.json` ~ `layout8_setup.json` | 레이아웃 8종 픽스처(`smoke_basic.json` 대체) |

## 인터페이스

`text.h`
- `uint32_t utf8Next(const char*& p);` — 끝이면 0. 잘린 시퀀스·단독 연속 바이트는 `?` 하나, 뒤따르는 고아 연속 바이트까지 넘긴다.
- `int16_t textWidth(const BitmapFont& f, const char* utf8, int8_t trackingPx = 0);` — 목록 밖 글자는 폭 0, 자간은 글자 사이에만.
- `int16_t drawText(Adafruit_GFX& gfx, const BitmapFont& f, const char* utf8, int16_t x, int16_t baselineY, uint16_t color, int8_t trackingPx = 0);` — 반환값 = 같은 인자의 `textWidth`.

`render_logic.h`
- `enum class BandStyle : uint8_t { None, Red, Black };` / `BandStyle bandStyle(uint8_t layout);` — 1·5·6·7 Red, 2·3·4 Black, 그 밖 None
- `const BitmapImage* statusImage(uint8_t layout);` — 1~7 상태명, 그 밖 nullptr
- `const char* weekdayName(uint8_t weekday);` — 1=월요일 ~ 7=일요일, 그 밖 ""
- `const BitmapImage* typeChip(uint8_t type);` — 2 시험·3 휴강·5 특강·6 대여, 그 밖 nullptr
- `void formatHM(uint8_t h, uint8_t m, char* out, size_t cap);` — `"HH:MM"`
- `bool statusSubline(const RenderModel& m, char* out, size_t cap);` — 1·5·6·7 `HH:MM에 끝납니다`(cur 끝), 2 `HH:MM 수업 재개`(next 시작), 3 `오늘 휴강입니다`, 그 밖 false
- `struct TodayWindow { uint8_t count, start, rows, moreAbove, moreBelow; int8_t curIdx; };` / `TodayWindow todayWindow(const RenderModel& m);` — N=9, `start = clamp(기준−1, 0, count−9)`, 기준 = 현재 항목 → 다음 예정 항목 → 0. 잘린 쪽 끝 행을 `↑/↓ n개 더`로 대체.

`render.h`
- `void renderLayout(Adafruit_GFX& gfx, const RenderModel& model);` — layout 8은 전폭 화면, 1~8 밖은 흰 화면.

## 태스크와 결과 (`[확인]` 커밋·테스트 수)

| Task | 내용 | 커밋 | 전체 테스트 |
|---|---|---|---|
| 4.1 | `text` — UTF-8·폭·한 줄 그리기, 테스트 8개 | `262343f`, `7f26566` | 62 |
| 4.2 | `render_logic` — 순수 판단, 테스트 16개 | `a73ce87` | 78 |
| 4.3 | `renderLayout` layout 1 수직 슬라이스(헤더·상태 띠·정보 형태 A·오늘 목록·분할선·푸터), `smokeRender` 교체, 첫 PNG — **검토 지점** | `4d3e0d8` | 87 |
| H | 자산 흑백 힌트 재생성(상위 plan §3.8, 팀 승인 필요) — 첫 PNG 검토 결과로 끼움 | `021471a` | 88 |
| 5.1 | 정보 형태 B(빈강의실)·변경 칩·범위 밖 layout | `7f2dcc6` | 92 |
| 5.2 | layout 8 설정 대기(헤더 `미설정 단말`, 제목, NEW 칩, 안내 2줄) | `eb489df`, `1e27495` | 95 |
| 6.1 | 픽스처 8개 + PNG 8장 | `d3e1dba` | 95 |
| — | 최종 리뷰 반영(주석 정정, 새 파일 줄바꿈 LF 통일) | `3350eef` | 95 |

마지막 커밋 기준 `native_preview` SUCCESS, `pio check` HIGH 0 / MEDIUM 0. 태스크마다 명세·품질 리뷰, 끝에 브랜치 전체 리뷰(Critical 0).

## 구현 중 결정 (틀렸을 때의 비용)

1. 잘린 UTF-8은 `?` 하나로 표시(처음 계획은 바이트마다 `?`) — Review Focus 1과 맞춤. 틀리면 `?` 개수 차이뿐.
2. Task H를 Task 5.1 앞에 끼움 — `renderLayout`이 폰트 셀·베이스라인을 쓰므로 자산을 먼저 확정. 틀리면 순서만 바뀜.
3. 20px Regular·Bold 셀이 같다는 테스트 단언 삭제 — 옛 자산의 우연한 사실이었다. 렌더는 폰트별 베이스라인으로 정렬한다.
4. 형태 B의 "구분선 없음" 검사를 점 하나에서 행 전체로 — 자산 재생성 후 과목 글자가 검사 점을 덮었다. 의도는 같다.
5. layout 2 픽스처의 `next`(재개 시각)가 `today[]`에 없음을 그대로 둠 — v2 §5.3 쉬는시간 정의(슬롯 안 & 분≥50)와 맞다. 화면 스펙 문장과의 어긋남은 cw 질문(상위 plan §7-4).
6. 구현자가 `'\0'`을 실제 NUL 바이트로 쓴 두 곳을 이스케이프로 고침 — 동작은 같았지만 git이 파일을 바이너리로 취급.

## 열린 질문 (⚠️ 검토 대상)

1. 목록 현재 행의 시각 굵기 — 스펙대로 16/400으로 구현. 700으로 하려면 16px/700 숫자 자산 필요(mh).
2. 창 기준 항목이 없을 때(`cur`·`next` 둘 다 없고 `nToday` > 9) 처음부터 보여 준다. 마지막 쪽이 더 자연스러울 수도 있다.
3. 정보 형태 B는 행 구분선(y 291·365)을 그리지 않는다 — 두 줄 한 덩어리라 구분선이 글자를 가른다.
4. 글자 목록 밖 글자는 빈칸 없이 건너뛴다 — 서버가 입력 단계에서 막는다(#34).
5. `layout`이 1~8 밖이면 흰 화면.
6. 스펙에 없는 초기값: 세로 위치(헤더 베이스라인 37, 정보 행 263/338/413, 목록 행 +25, 푸터 466), 칩 좌우 여백 6·글자 베이스라인 17, 변경 칩 간격 10·들어올림 18, layout 8 안내 2줄 간격 8. PNG 검토로 정한다.
7. layout 8에서 `newTag`가 비면 칩과 안내 2줄을 생략한다.
8. 색 상수가 두 곳(`host_gfx.h`, `render_colors.h`)에 있다 — `lib/render`가 호스트 전용 헤더를 include할 수 없어서다. 값이 어긋나면 `test_render_layout`의 색 비교가 실패한다.

## 알려진 문제 (렌더 PR 최종 리뷰)

- 16px `↑`·`↓`가 폭 1px 막대 + 머리 3px라 멀리서 `↑ 4개 더`가 `14개 더`로 읽힐 수 있다 — mh 결정 대상(상위 plan §7-3).
- 목록 과목이 20B ASCII면 약 200px로 type 칩과 겹칠 수 있다 — 스펙 "문자열 한계"는 한글 6자만 계산.
- 정보 형태 A에서 `cur.flags` bit0=0이면 `00:00 – 00:00`을 그린다 — 정상 흐름에서는 생기지 않는 조합으로 본다 `[추정]`.
- 실기 GxEPD2의 색 매크로 값·3색 `drawPixel` 동작은 확인하지 못했다(espressif32 미설치) — S7 실기 빌드에서 확인.
