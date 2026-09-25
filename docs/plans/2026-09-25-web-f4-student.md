# 웹 F4 — 학생 웹 (건물 · 강의실 · 이번 주 · 예약 · 내 예약) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 학생 앱(`web/index.html`)에 로그인 벽 · `/` 건물 선택 · `/:bld` 강의실 목록 · `/:bld/:room` 강의실 · `/:bld/:room/week` 이번 주 · `/:bld/:room/reserve` 예약 신청 · `/me` 내 예약과 학생 전용 컴포넌트 6종(RoomListRow · FavoriteStar · WeekGrid · ReserveSheet · ResvStatusBadge · MyResvCard)을 만들고, 390×844(+넓은 폭 1280×800) Playwright 로 실제 브라우저에서 확인한다.

**Architecture:** F1·F3·F2 의 `api/client.ts`·`useResource`·`usePolling`·`useStale`·ui 컴포넌트·`components/domain/rules.ts` 위에 올린다. 서버 계약은 `api/student.ts`(`studentApi`) 한 곳, 학생 규칙(상한·체크인 창·시간 고르기·문장)은 `components/student/rules.ts` 한 곳이다. 빈 구간·겹침 합치기는 **서버가 준 `WeekOut.busy`·`free`·`full`(A3)을 그대로** 쓰고 브라우저에서 다시 계산하지 않는다. `/:bld` 는 방 목록을 한 번 불러 자식 화면(강의실·주간·예약)에 `provide` 하는 레이아웃이고, 좁은 폭/넓은 폭은 같은 라우트에서 CSS(목록 340px 상주)와 `useWide()`(격자·예약 버튼 자리)로 가른다.

**Tech Stack:** Vue 3.5 · vue-router 4.5 · Vite 7 · TypeScript 5.9 · Vitest 3 + @vue/test-utils + jsdom · @playwright/test 1.63 · pnpm (새 의존성 없음)

**Spec:** `docs/specs/2026-09-25-web-frontend-design.md` §2.2·§3.3·§4·§5(student-room)·§6(F4)·§8 (+ 화면 원본 `docs/design/screens/student-room.md`(#46)·`auth.md`(로그인 뒤 401), `tokens.md` §room·§치수·§브레이크포인트, `components.md` §Badge·§Checkbox). 서버 계약: `server/app/domain/student_router.py`·`reserve.py`·`room_state.py`·`app/schemas.py` (S10 + web additive A3).

**브랜치:** `feature/web-f4` ← `feature/web-f2` (워크트리는 컨트롤러가 만든다). F2 의 `api/types.ts`(`SlotType`·`SlotOut`·`ExamOut`·`ResvOut`·`ResvStatus`)·`lib/time.ts`(`addDays`·`dayOfDate`·`mondayOf`·`hm`·`md`)·`components/domain/rules.ts`(`DAYS`·`TYPE_LABEL`·`BUSY_TYPES`·`SUBJ_MAX`)·E2E `kstDate`·`ensureModems`, F3 의 `useStale`·E2E `login`·`apiLogin`·`createStudent`·`shot`·`SIZES`·`WEB_URL` 를 그대로 쓴다.

## Global Constraints

- 작업 위치: `web/` 만. 서버·`docs/design/` 은 읽기만 한다.
- pnpm 만. **새 의존성 없음** — 날짜 피커·드롭다운·격자·스와이프 라이브러리 금지. 선택은 네이티브 `<select>`(ui `Select`)·`<input type="radio">`.
- 응답 타입은 `src/api/types.ts` 에 **한 번만**, 서버 스키마 이름 그대로(`RoomStateOut`·`ResvPublicOut`·`FreeRange`·`BusySpan`·`BusyDay`·`FreeDay`·`WeekOut`·`StudentResvIn`·`ResvMineOut`). `*_at` 만 `RESV_MINE_DATES` 로 `Date`, `date`·`week_start` 는 KST 달력 문자열 그대로, `from`·`to`·`until` 은 `'HH:MM'` 그대로.
- **`room_state` 규칙을 브라우저에 복제하지 않는다** — 겹친 블록은 `WeekOut.busy`(서버가 합친 것), 신청 가능한 구간은 `WeekOut.free`, 방 용량은 `WeekOut.full`. 화면은 그것을 배치·표시만 한다. 가용성은 `layout === 4` 만, 색은 RED(1·5·6·7) — 둘을 섞지 않는다.
- 서버 오류 원문을 화면에 내지 않는다 — 학생 문장은 `components/student/rules.ts` 의 상수(`FULL_TEXT`·`CAP_TEXT`·`DAILY_TEXT`·`TAKEN_TEXT`·`STALE_TEXT`·`CHANGED_TEXT`·`CHECKIN_CLOSED_TEXT`), 나머지는 F1 `MESSAGES`.
- 서버 값 그대로: 진행 중 신청 **3건**(`MAX_ACTIVE`), 하루 **10회**(429), 길이 **15~120분**, **5분** 단위, 체크인 **시작 −10 ~ +15분**, 날짜 **KST 오늘~+7**(서버 `free` 8일), 목적 **UTF-8 20 B**(`SUBJ_MAX`).
- 전부 로그인 필요(`require_student`) — 학생 앱의 화면 라우트는 `meta.gate`, 세션이 없으면 그 주소 그대로 **로그인 벽**. 세션 중 401 은 F1 공통 처리(`/login?next=` + `다시 로그인해 주세요`, 입력은 되살리지 않음).
- 학생 터치 타깃 48px 이상(행 56 · 칩·구간 52 · ★ 48). 색만으로 상태를 말하지 않는다(라벨 병기), ★ 은 모양도 바뀐다(`★`/`☆`) + `aria-label`.
- 남의 신원은 어디에도 없다 — 격자·오늘 목록은 서버 `label`(남의 것 `예약됨`)을 그대로 쓴다.
- 자동 새로고침 60초(`POLL_MS`), 탭이 숨으면 멈춤(F1 `usePolling`). 오류여도 이전 데이터를 지우지 않고 danger Banner + `다시 시도`, 갱신 줄은 5분 지나면 danger(F3 `useStale`). **예약 신청 화면은 폴링하지 않는다**(고른 구간이 흔들리지 않게 — 설계 판정).
- `.vue` 의 `<style>`·`<template>` 에 1층 팔레트(`--gray-` 등)·16진 색 금지(F1 `tokens.guard.spec.ts`). 학생 컴포넌트는 `src/components/student/`(학생·관리자 공유 경계 — `@/student/*` import 금지), 화면 계산은 `src/student/*.ts`. 공유 경계 ESLint 패턴 `**/student/**` 가 `'@/components/student/…'` 문자열에도 걸리므로 **`src/components/student/` 안(테스트 포함)에서는 상대 경로(`./rules`·`../ReserveSheet.vue`)로 import** 한다. `src/student/**` 는 `@/components/student/…` 그대로.
- 커밋: `feat(web): …` / `style(web): …`(ui) / `test(web): …`. **Claude·AI 저작 표기와 `Co-Authored-By` 트레일러 금지.**
- 매 Task 끝에 `cd web && pnpm test && pnpm lint && pnpm typecheck && pnpm exec prettier --check .` 통과. 새 파일은 `pnpm exec prettier --write <파일>` 로 정리하고, CRLF 만 바뀐 파일은 커밋하지 않는다.
- **E2E 명령**(PowerShell — 통합 서버 워크트리에 S10 + A1~A3 이 있어야 한다, 컨트롤러가 준비):
  ```powershell
  cd web
  $env:E2E_SERVER_DIR = 'C:/path/to/server'
  $env:E2E_API_PORT = '8100'
  $env:E2E_WEB_PORT = '5273'
  pnpm e2e e2e/student.spec.ts
  ```
  전체(`pnpm e2e`)도 한 번 돌려 F1~F3 spec 이 그대로인지 본다. **KST 23:50~00:10 에는 돌리지 않는다** — 시드가 '지금' 사용 중 예약을 만들고 체크인 흐름이 오늘 예약을 만든다.
- 화면 Task 완료 조건: E2E 통과 + 390×844 스크린샷(넓은 폭은 1280×800 한 장)을 `web/e2e/.shots/` 에 남기고 `student-room.md` 수치와 대조(스크린샷은 커밋하지 않는다 — PR 에 첨부).

## Review Focus

테스트가 직접 겨누지 않으면 사람이 가장 먼저 밟을 입력·상황 다섯. 각 줄의 고정 테스트는 담당 Task 에 있다.

1. 빈 구간을 고르는 사이 다른 학생이 같은 시간을 먼저 신청 → 제출 409 → `방금 다른 사람이 먼저 신청했어요…` + 빈 구간 재조회, 사라진 구간의 선택은 풀려 버튼이 잠긴다(방이 찬 409 는 `이 강의실은 예약이 다 찼어요`). — Task 7 `재조회로 고른 구간이 사라지면 선택이 풀리고…` + Task 13 `409 — 재조회한 full 이 false 면 먼저 신청한 사람…`·`409 — 재조회한 full 이 true 면 방이 찼다` + E2E `경합 — 고르는 사이…`
2. 진행 중 3건 · 하루 10회(429) · 방 가득(`full`) → 제출 전에 버튼 `disabled` + 이유 한 줄, 429 는 Toast 뒤 이 화면에 있는 동안 잠금. — Task 7 `막는 이유 — 가득·3건·하루 상한…` + Task 13 `429 — Toast 뒤 잠금…`·`400 — 재조회해 진행 중이 3건이면 CAP, 아니면 STALE` + E2E `건수 상한…`
3. 체크인 창 밖 → 버튼을 숨기지 않고 `disabled` + `10:50부터 체크인할 수 있어요`, 끝난 승인 예약엔 버튼이 없다, 시작 뒤엔 `취소` 가 없다. 서버와 시계가 어긋나 409 면 문장 + 재조회. — Task 2 `체크인 창 — 시작 −10 ~ +15분…`·`취소 — 신청은 철회…` + Task 8 + Task 12 `취소 경합 — 관리자가 먼저 거절했으면 409…` + E2E `내 예약 — …체크인…`
4. 사생활 보호 모드(localStorage 가 던짐) → 즐겨찾기·최근 건물이 이번 방문 동안 동작하고 화면이 깨지지 않는다. 깨진 값(`{oops`)·모양이 다른 값은 버린다. — Task 3 `localStorage 가 막혀도…`·`깨진 값…`
5. 네트워크가 끊긴 채 목록을 보고 있음 → 이전 목록을 지우지 않고 danger Banner + `다시 시도`, 하단 `… · 10:41 갱신` 줄이 5분 뒤 danger + `갱신이 멈췄어요`. 첫 조회부터 실패하면 빈 목록이 아니라 `다시 시도`. — Task 9 `5분이 지나면 danger…` + Task 10 `조회 실패 — 이전 목록을 지우지 않고…`·`첫 조회가 실패하면…`

## 설계 판정 (디자인 미결·문서끼리 어긋난 곳)

| 항목 | 판정 | 근거 |
|---|---|---|
| 로그인 벽 자리 | 라우트 `meta.gate` + `StudentApp` 이 **그 주소 그대로** `LoginGate` 를 그린다(리다이렉트 없음). `로그인` 은 `/login?next=<원래 주소>` | 주소가 곧 상태다 — 벽에서 새로고침·공유해도 같은 주소. F1 LoginView 가 `next` 로 돌려보낸다 |
| 세션 중 401 | F1 그대로 `/login?next=` + `다시 로그인해 주세요`(벽을 한 번 더 거치지 않는다) | auth.md·spec §4.1 의 공통 처리. 이미 쓰던 사람에게 벽 설명은 필요 없다 |
| 벽의 건물 이름 | 로그인 전엔 이름을 모른다 → 주소의 글자로 `E동의 빈 강의실을…`, 글자가 없으면 `학교의 빈 강의실을…` | 조회 API 가 전부 로그인 필요(S10 §3) |
| `/` 첫 진입(미결 3) | 최근 건물(`esc.lastBld`)이 목록에 있으면 그리로 → 없고 건물이 하나뿐이면 그리로 → 아니면 건물 목록 | 매일 같은 건물을 보는 쓰임. 사라진 최근 건물은 무시 |
| `GET /rooms/free` | 쓰지 않는다 — `GET /rooms` 의 `layout === 4` 가 같은 판정(같은 `state_of`)이고 호출 하나로 개수·목록·건물을 다 만든다 | 폴링 부하(미결 4) |
| 목록 행 둘째 줄 | `until` 은 "다음 상태 변화"라 `10:00 에 비어요` 로 단정하지 않는다 → `10:50 까지`, `until` 이 null 이면 빈 방 `오늘 계속 비어 있어요` · 사용 중 `자정까지`. 과목명은 `RoomStateOut` 에 없어 싣지 않는다 | 수업(1) 뒤는 쉬는시간(2)일 수 있다(room_state `:50`) |
| `reservable = false` 방 | 학생 API 가 주지 않는다 → **404 화면**. `이 강의실은 예약을 받지 않습니다` 줄은 생길 수 없다 | `_rooms_q`·`_student_room` 이 `reservable` 만 |
| 비로그인 `예약하기` → `/login` | 해당 없음 — 벽이 먼저다 | 조회도 로그인(미결 5 확정) |
| 소문자 건물 글자(`/e/401`) | `/E/401` 로 리다이렉트 | "주소를 잘못 친 경우가 흔하다" |
| 넓은 폭 하루 열 `200px 이상` | `minmax(120px, 1fr)` — 1280 에서 목록 340 을 빼면 5열이 200 에 못 미친다. 넘치면 격자만 가로 스크롤. mh 확인 요청 | 목록 340 상주와 200px 이 1280 폭에서 함께 서지 않는다 |
| 넓은 폭 `오늘` 의 교수 | 싣지 않는다(시각 구간 + 과목 + 배지) | `BusySpan` 에 professor 없음 — 필요하면 서버 additive |
| WeekGrid props | spec 의 `days · blocks · rowHeight · todayIndex · nowTop` + `range`(시각 라벨). block 에 `mine`·`requested` 를 더한다 | 시각 열을 그리려면 범위가 필요. 내 신청은 `brand` 점선 테두리 + `대기중` |
| 격자 범위·주말 | 09:00~18:00, 벗어난 블록이 있으면 30분 단위로 편다. 토·일 열은 그 요일에 블록이 있을 때만. `빈강의실`(type 4) 슬롯은 그리지 않는다 | "해당 슬롯이 있으면 자동으로 편다" · "비어있음은 칠하지 않는다" |
| 격자 요일의 '오늘' | 서버 `week_start` 가 오늘의 월요일일 때만(자정 직후 한 번의 폴링 사이 어긋남 방지) | KST 자정 경계 |
| 예약 화면 폴링 | 하지 않는다. 제출 오류 때만 재조회. 지난 시작 시각은 15초마다 화면 시계로 목록에서 지운다 | 60초마다 `free` 가 바뀌면(오늘 칩의 하한이 움직인다) 고른 구간이 풀린다 |
| 409 두 갈래 | 서버 원문을 보지 않고 **재조회한 `full`** 로 가른다 — true 면 `FULL_TEXT`, 아니면 `TAKEN_TEXT` | 겹침·용량 둘 다 409 |
| 400(창 밖·지난 시각·3건) | 내 예약·주간을 재조회해 진행 중이 3건이면 `CAP_TEXT`, 아니면 `STALE_TEXT` | 서버가 셋 다 400 |
| 429(하루 10회) | Toast + **이 화면에 있는 동안** 버튼 잠금(10초 잠금 아님) | 하루 상한 — 10초 뒤 풀어도 또 429 |
| 기본 끝 시각 | 시작 + 60분(구간 끝을 넘지 않게) | 시안의 2시간보다 짧은 쪽 — 상한은 120 그대로 |
| `/me` 조회 범위 | `?status=` 다섯 상태 전부 | 서버 기본은 requested·approved 만 — 거절 사유를 못 본다 |
| `/me` 정렬 | 진행 중(대기 · 안 끝난 승인) 가까운 순 → 나머지 최근 순 | 신청한 뒤 돌아오는 자리 — 할 일이 위 |
| 끝난 승인 예약 | 체크인·취소 둘 다 없음. 창이 지났고 아직 안 끝났으면 `체크인 시간이 지났어요` | 버튼이 영원히 남지 않게 |
| 신청 취소 중 관리자 승인 경합 | 서버가 승인된 예약의 취소로 처리 → 결과는 같은 "취소". 거절·이미 취소·없음(409/404)은 `CHANGED_TEXT` + 재조회. 성공 Toast 는 `취소했어요` 하나 | `cancel_resv` 가 상태를 보고 갈린다 |
| 대기중 개수 배지(미결 8) | 두지 않는다 — 헤더 `내 예약` 링크 | 알림은 S10 비목표 |
| 즐겨찾기 칩 | 다른 건물의 방은 건물 이름을 붙인다. 목록에서 사라진 방은 조용히 빠진다 | `esc.fav` 는 학교 전체 |
| 폴링 대상 | 목록(레이아웃) · 강의실 · 주간 · 내 예약. 모바일 강의실 화면에서도 숨은 목록이 방 상태를 부른다(분당 2회) | ponytail: 레이아웃이 방 id 를 풀어 주는 한 곳 — Pi 부하가 문제되면 숨은 목록 폴링을 끈다 |
| `지금` 배지 | Badge 에 `brand` + `solid` 조합을 더한다 | student-room.md 가 `brand 채움 + 흰 글자` 로 명시 |
| 로그아웃 | `/me` 하단 `로그아웃`(ghost) | 로그아웃 API 없음 — 토큰을 버린다(F1) |

## 파일 지도

```
web/
├── e2e/
│   ├── helpers.ts                 login(…, ready) · STU · seedStudent · kstMinutesNow · hmOf
│   └── student.spec.ts            벽 · 404 · 건물 · 목록 · 강의실 · 이번 주 · 넓은 폭 · 내 예약 · 예약 (학생 UI 로그인 1회)
└── src/
    ├── api/
    │   ├── types.ts               + RoomStateOut … ResvMineOut, RESV_MINE_DATES
    │   ├── student.ts             studentApi — rooms · week · requestResv · mine · cancel · checkin
    │   └── __fixtures__/          week.json · mine.json
    ├── lib/time.ts                + kstMinutes
    ├── components/
    │   ├── ui/Badge.vue           brand + solid ('지금')
    │   └── student/
    │       ├── rules.ts           layout 라벨 · 상한 · 체크인 창 · 시간 고르기 · 문장
    │       ├── grid.ts            격자 범위 · 요일 · 블록 배치 · 지금 선
    │       ├── ResvStatusBadge.vue · FavoriteStar.vue · RoomListRow.vue
    │       ├── WeekGrid.vue
    │       ├── ReserveSheet.vue
    │       └── MyResvCard.vue
    └── student/
        ├── router.ts · StudentApp.vue      gate · 404 · 소문자 글자 · 화면 라우트
        ├── LoginGate.vue · StudentHeader.vue · CtaLink.vue · RefreshedNote.vue
        ├── composables.ts         POLL_MS · useWide · useNow
        ├── favorites.ts           esc.fav · esc.lastBld (막혀도 동작)
        ├── roomView.ts            건물 파생 · 오늘 목록 · 다음 비는 시간 (순수 함수)
        ├── building.ts            BUILDING 주입 · useRoomWeek · useWeekGrid
        └── views/
            ├── HomeView.vue · BuildingLayout.vue · NotFoundView.vue
            ├── RoomView.vue · WeekView.vue
            ├── ReserveView.vue
            └── MyView.vue
```

## Task 순서와 의존

| Task | 내용 | 의존 |
|---|---|---|
| 1 | api — 학생 타입 · `studentApi` | — |
| 2 | 학생 규칙(`rules.ts`) · `kstMinutes` | 1 |
| 3 | 즐겨찾기 · 최근 건물(`favorites.ts`) | — |
| 4 | 격자 배치(`grid.ts`) · 화면 계산(`roomView.ts`) | 1, 2 |
| 5 | Badge `brand` solid · ResvStatusBadge · FavoriteStar · RoomListRow | 2 |
| 6 | WeekGrid | 4 |
| 7 | ReserveSheet | 2 |
| 8 | MyResvCard | 2, 5 |
| 9 | 셸 — 로그인 벽 · 404 · 소문자 글자 · 헤더 · 갱신 줄 + E2E | 3 |
| 10 | `/` 건물 선택 · `/:bld` 강의실 목록 + E2E | 3, 4, 5, 9 |
| 11 | `/:bld/:room` 강의실 · `/week` 이번 주 · 넓은 폭 + E2E | 6, 10 |
| 12 | `/me` 내 예약 + E2E | 8, 10 |
| 13 | `/:bld/:room/reserve` 예약 신청 + E2E | 7, 11, 12 |

---

### Task 1: api — 학생 타입 · `studentApi`

**Files:**
- Modify: `web/src/api/types.ts`
- Create: `web/src/api/student.ts`, `web/src/api/__fixtures__/week.json`, `web/src/api/__fixtures__/mine.json`
- Test: `web/src/api/__tests__/student.spec.ts`

**Interfaces:**
- Consumes: `request<T>`·`ApiError`(F1), `SlotType`·`SlotOut`·`ExamOut`·`ResvOut`·`ResvStatus`(F2 Task 1).
- Produces (`types.ts`): `RoomStateOut` · `ResvPublicOut` · `FreeRange{from,to}` · `BusySpan` · `BusyDay` · `FreeDay` · `WeekOut` · `StudentResvIn` · `ResvMineOut` + `RESV_MINE_DATES`.
- Produces (`student.ts`): `ALL_STATUSES: readonly ResvStatus[]` · `studentApi.rooms(): Promise<RoomStateOut[]>` · `week(roomId: number): Promise<WeekOut>` · `requestResv(roomId: number, body: StudentResvIn): Promise<ResvMineOut>` · `mine(): Promise<ResvMineOut[]>` · `cancel(id: number): Promise<ResvMineOut>` · `checkin(id: number): Promise<ResvMineOut>`.

- [ ] **Step 1: 픽스처 (서버 응답 모양 그대로 — `student_router.week`·`_mine_out`)**

`web/src/api/__fixtures__/week.json` (KST 2026-10-23 금 기준 — 주 시작 10-19 월)
```json
{
  "room": {
    "room_id": 11,
    "building_id": 3,
    "building": "공학관",
    "bld": "E",
    "room": 401,
    "layout": 1,
    "until": "10:50"
  },
  "week_start": "2026-10-19",
  "slots": [
    {
      "id": 1,
      "day": 5,
      "s_h": 10,
      "s_m": 0,
      "e_h": 12,
      "e_m": 0,
      "type": 1,
      "subject": "알고리즘",
      "professor": "김교수",
      "source": 1
    }
  ],
  "reservations": [
    {
      "id": 7,
      "date": "2026-10-23",
      "s_h": 11,
      "s_m": 0,
      "e_h": 13,
      "e_m": 0,
      "mine": false,
      "label": "예약됨"
    }
  ],
  "exams": [],
  "busy": [
    { "day": 1, "spans": [] },
    {
      "day": 2,
      "spans": [
        { "from": "09:00", "to": "10:00", "label": "운영체제", "type": 3, "mine": false, "status": null }
      ]
    },
    { "day": 3, "spans": [] },
    { "day": 4, "spans": [] },
    {
      "day": 5,
      "spans": [
        { "from": "10:00", "to": "13:00", "label": "알고리즘 외 1건", "type": 1, "mine": false, "status": null },
        { "from": "15:00", "to": "16:00", "label": "캡스톤 스터디", "type": 6, "mine": true, "status": "requested" }
      ]
    },
    { "day": 6, "spans": [] },
    { "day": 7, "spans": [] }
  ],
  "free": [
    { "date": "2026-10-23", "spans": [{ "from": "13:00", "to": "15:00" }, { "from": "16:00", "to": "21:00" }] },
    { "date": "2026-10-24", "spans": [] },
    { "date": "2026-10-25", "spans": [{ "from": "09:00", "to": "21:00" }] },
    { "date": "2026-10-26", "spans": [{ "from": "09:00", "to": "21:00" }] },
    { "date": "2026-10-27", "spans": [{ "from": "09:00", "to": "21:00" }] },
    { "date": "2026-10-28", "spans": [{ "from": "09:00", "to": "21:00" }] },
    { "date": "2026-10-29", "spans": [{ "from": "09:00", "to": "21:00" }] },
    { "date": "2026-10-30", "spans": [{ "from": "09:00", "to": "21:00" }] }
  ],
  "full": false
}
```

`web/src/api/__fixtures__/mine.json`
```json
[
  {
    "id": 7,
    "date": "2026-10-24",
    "s_h": 10,
    "s_m": 0,
    "e_h": 12,
    "e_m": 0,
    "type": 6,
    "subject": "캡스톤 스터디",
    "professor": "",
    "status": "approved",
    "requested_at": "2026-10-22T01:00:00",
    "decided_at": "2026-10-22T02:30:00",
    "reject_reason": null,
    "checked_in_at": null,
    "cancelled_at": null,
    "room_id": 11,
    "building": "공학관",
    "room": 401
  },
  {
    "id": 9,
    "date": "2026-10-26",
    "s_h": 14,
    "s_m": 0,
    "e_h": 16,
    "e_m": 0,
    "type": 6,
    "subject": "동아리",
    "professor": "",
    "status": "rejected",
    "requested_at": "2026-10-22T03:00:00",
    "decided_at": "2026-10-22T04:00:00",
    "reject_reason": "학과 행사와 겹칩니다",
    "checked_in_at": null,
    "cancelled_at": null,
    "room_id": 12,
    "building": "공학관",
    "room": 405
  }
]
```

- [ ] **Step 2: 실패 테스트**

`web/src/api/__tests__/student.spec.ts`
```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { studentApi } from '@/api/student'
import { clearSession } from '@/lib/session'
import week from '@/api/__fixtures__/week.json'
import mine from '@/api/__fixtures__/mine.json'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
const fetchMock = vi.fn<typeof fetch>()
const call = (i = 0) => ({ url: fetchMock.mock.calls[i][0], init: fetchMock.mock.calls[i][1]! })

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  clearSession()
})

describe('studentApi', () => {
  it('rooms — 학교의 예약 가능한 방 전부, until 은 문자열 그대로(null = 자정까지)', async () => {
    fetchMock.mockResolvedValue(
      json([
        { room_id: 11, building_id: 3, building: '공학관', bld: 'E', room: 401, layout: 4, until: null },
      ]),
    )
    const out = await studentApi.rooms()
    expect(call().url).toBe('/api/student/rooms')
    expect(out[0].until).toBeNull()
    expect(out[0].layout).toBe(4)
  })

  it('week — busy·free·full 은 서버 계산 그대로, 날짜는 KST 달력 문자열', async () => {
    fetchMock.mockResolvedValue(json(week))
    const out = await studentApi.week(11)
    expect(call().url).toBe('/api/student/rooms/11/week')
    expect(out.week_start).toBe('2026-10-19')
    expect(out.busy[4]).toEqual({
      day: 5,
      spans: [
        { from: '10:00', to: '13:00', label: '알고리즘 외 1건', type: 1, mine: false, status: null },
        { from: '15:00', to: '16:00', label: '캡스톤 스터디', type: 6, mine: true, status: 'requested' },
      ],
    })
    expect(out.free).toHaveLength(8)
    expect(out.free[0]).toEqual({
      date: '2026-10-23',
      spans: [
        { from: '13:00', to: '15:00' },
        { from: '16:00', to: '21:00' },
      ],
    })
    expect(out.full).toBe(false)
  })

  it('mine — 다섯 상태 전부를 묻고, *_at 만 Date', async () => {
    fetchMock.mockResolvedValue(json(mine))
    const out = await studentApi.mine()
    expect(call().url).toBe(
      '/api/student/me/reservations?status=requested,approved,rejected,cancelled,expired',
    )
    expect(out[0].decided_at!.toISOString()).toBe('2026-10-22T02:30:00.000Z')
    expect(out[0].checked_in_at).toBeNull()
    expect(out[0].date).toBe('2026-10-24')
    expect(out[1].reject_reason).toBe('학과 행사와 겹칩니다')
  })

  it('requestResv — 본문 그대로 POST (id·type·professor 는 보내지 않는다 — 서버가 정한다)', async () => {
    fetchMock.mockResolvedValue(json({ ...mine[0], status: 'requested' }, 201))
    const body = { date: '2026-10-24', s_h: 10, s_m: 0, e_h: 12, e_m: 0, subject: '캡스톤 스터디' }
    const out = await studentApi.requestResv(11, body)
    expect(call().url).toBe('/api/student/rooms/11/reservations')
    expect(call().init.method).toBe('POST')
    expect(JSON.parse(call().init.body as string)).toEqual(body)
    expect(out.status).toBe('requested')
    expect(out.requested_at).toBeInstanceOf(Date)
  })

  it('cancel · checkin — 경로', async () => {
    fetchMock.mockImplementation(async () => json(mine[0]))
    await studentApi.cancel(7)
    await studentApi.checkin(7)
    expect(call(0).url).toBe('/api/student/me/reservations/7/cancel')
    expect(call(1).url).toBe('/api/student/me/reservations/7/checkin')
    expect(call(1).init.method).toBe('POST')
  })

  it('409 — ApiError, 원문은 detail 에만 (화면이 문장을 고른다)', async () => {
    fetchMock.mockResolvedValue(json({ detail: '그 시간에는 이미 수업·예약이 있습니다' }, 409))
    const err = await studentApi.requestResv(11, {
      date: '2026-10-24',
      s_h: 10,
      s_m: 0,
      e_h: 11,
      e_m: 0,
      subject: 'x',
    }).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(409)
    expect((err as ApiError).message).not.toContain('수업·예약')
  })
})
```

- [ ] **Step 3: 실패 확인**

Run: `cd web && pnpm test src/api/__tests__/student.spec.ts`
Expected: FAIL — `Failed to resolve import "@/api/student"`

- [ ] **Step 4: 구현**

`web/src/api/types.ts` 끝에 추가
```ts
// ---- F4 학생 웹 — S10 §4.1 + web A3 (busy·free·full) ----

/** 학생 목록의 방 하나 + 지금 상태 (reservable 방만 — S10 §3) */
export interface RoomStateOut {
  room_id: number
  building_id: number
  building: string
  bld: string
  room: number
  /** e-Paper layout 1~8 — 4 만 '비어있음'(예약 가능). 색은 RED(1·5·6·7) */
  layout: number
  /** 다음 상태 변화 'HH:MM' (KST). null = 자정까지 그대로 */
  until: string | null
}
/** 주간 표의 승인 예약 원본 — 남의 학생 예약 label 은 '예약됨' */
export interface ResvPublicOut {
  id: number
  date: string
  s_h: number
  s_m: number
  e_h: number
  e_m: number
  mine: boolean
  label: string
}
/** 'HH:MM' 구간 — 서버 alias 그대로 from/to */
export interface FreeRange {
  from: string
  to: string
}
/** 서버가 room_state 규칙으로 합친 사용 구간 (web A3). 남의 것은 label '예약됨'·status null */
export interface BusySpan extends FreeRange {
  label: string
  type: SlotType
  mine: boolean
  /** 내 예약만 — 격자가 '내 신청(대기)'과 '내 예약'을 가른다 */
  status: 'requested' | 'approved' | null
}
export interface BusyDay {
  /** 1=월 … 7=일 */
  day: number
  spans: BusySpan[]
}
/** 신청 가능한 구간 — KST 오늘~+7 여덟 날. 오늘은 지금 이후만, full 이면 전부 빈 목록 */
export interface FreeDay {
  date: string
  spans: FreeRange[]
}
export interface WeekOut {
  room: RoomStateOut
  week_start: string
  slots: SlotOut[]
  reservations: ResvPublicOut[]
  exams: ExamOut[]
  busy: BusyDay[]
  free: FreeDay[]
  /** 창(오늘~+7) 안 approved+requested 가 노드 용량(24)에 찼다 */
  full: boolean
}
/** 학생 신청 — type(6 대여)·professor('')·id 는 서버가 정한다 */
export interface StudentResvIn {
  date: string
  s_h: number
  s_m: number
  e_h: number
  e_m: number
  subject: string
}
/** 내 예약 (S10 §4.1 _mine_out) */
export interface ResvMineOut extends ResvOut {
  requested_at: Date | null
  decided_at: Date | null
  reject_reason: string | null
  checked_in_at: Date | null
  cancelled_at: Date | null
  room_id: number
  building: string
  room: number
}
export const RESV_MINE_DATES = [
  'requested_at',
  'decided_at',
  'checked_in_at',
  'cancelled_at',
] as const
```

`web/src/api/student.ts`
```ts
import { request } from './client'
import {
  RESV_MINE_DATES,
  type ResvMineOut,
  type ResvStatus,
  type RoomStateOut,
  type StudentResvIn,
  type WeekOut,
} from './types'

const mineOpts = { dates: RESV_MINE_DATES }

/** /me 는 다섯 상태 전부 — 서버 기본(requested·approved)이면 거절 사유·취소 기록을 못 본다 */
export const ALL_STATUSES: readonly ResvStatus[] = [
  'requested',
  'approved',
  'rejected',
  'cancelled',
  'expired',
]

// 전부 require_student + 내 학교의 reservable 방 — 아니면 404 (S10 §3)
export const studentApi = {
  /** 학교 전체 — 건물·개수·목록을 이 하나에서 만든다 */
  rooms: () => request<RoomStateOut[]>('GET', '/api/student/rooms'),
  /** 이번 주(서버 KST 오늘 기준) + 오늘~+7 free + full */
  week: (roomId: number) => request<WeekOut>('GET', `/api/student/rooms/${roomId}/week`),
  /** 201 → requested. 400 창·길이·지난 시각·3건 / 409 겹침·가득 / 429 하루 10회 */
  requestResv: (roomId: number, body: StudentResvIn) =>
    request<ResvMineOut>('POST', `/api/student/rooms/${roomId}/reservations`, body, mineOpts),
  mine: () =>
    request<ResvMineOut[]>(
      'GET',
      `/api/student/me/reservations?status=${ALL_STATUSES.join(',')}`,
      undefined,
      mineOpts,
    ),
  /** requested → 행 삭제(철회), approved → 시작 전 취소. 그 밖 409 */
  cancel: (id: number) =>
    request<ResvMineOut>('POST', `/api/student/me/reservations/${id}/cancel`, undefined, mineOpts),
  /** 시작 −10 ~ +15분 안의 approved 만. 그 밖·이미 함 409 */
  checkin: (id: number) =>
    request<ResvMineOut>('POST', `/api/student/me/reservations/${id}/checkin`, undefined, mineOpts),
}
```

- [ ] **Step 5: 통과 확인**

Run: `cd web && pnpm test src/api && pnpm typecheck && pnpm lint`
Expected: PASS — student.spec 6 tests, 기존 client·monitor·rooms spec 그대로.

- [ ] **Step 6: 커밋**

```bash
git add web/src/api
git commit -m "feat(web): 학생 API 타입과 studentApi — 방 상태·주간(busy·free·full)·신청·내 예약·취소·체크인"
```

---

### Task 2: 학생 규칙(`rules.ts`) · `kstMinutes`

**Files:**
- Modify: `web/src/lib/time.ts`
- Create: `web/src/components/student/rules.ts`
- Test: `web/src/components/student/__tests__/rules.spec.ts`

**Interfaces:**
- Consumes: `FreeRange`·`ResvMineOut`(Task 1), `DAYS`(F2 rules), `dayOfDate`·`hm`·`md`(F2 time), `kstDateStr`·`formatHm`(F1/F3 time).
- Produces (`lib/time.ts`): `kstMinutes(d: Date): number` (KST 자정부터 분, 0..1439).
- Produces (`rules.ts`): `FREE_LAYOUT = 4` · `layoutLabel(layout: number): string` · `isRed(layout: number): boolean` · `untilText(layout: number, until: string | null): string` · `MAX_ACTIVE = 3` · `MIN_MIN = 15` · `MAX_MIN = 120` · `STEP_MIN = 5` · `CHECKIN_BEFORE = 10` · `CHECKIN_AFTER = 15` · 문장 `FULL_TEXT` · `CAP_TEXT` · `DAILY_TEXT` · `TAKEN_TEXT` · `STALE_TEXT` · `CHANGED_TEXT` · `CHECKIN_CLOSED_TEXT` · `DOOR_HINT` · `hmToMin(v: string): number` · `minToHm(m: number): string` · `durationText(min: number): string` · `chipDay(date: string): string` · `dateLabel(date: string): string` · `spanKey(s: FreeRange): string` · `startOptions(span: FreeRange, after: number | null): number[]` · `endOptions(start: number, span: FreeRange): number[]` · `defaultEnd(start: number, span: FreeRange): number` · `activeCount(list: ResvMineOut[], now: Date): number` · `type CheckinState` · `checkinState(r: ResvMineOut, now: Date): CheckinState | null` · `type CancelKind = 'withdraw' | 'cancel'` · `cancelKind(r: ResvMineOut, now: Date): CancelKind | null` · `sortMine(list: ResvMineOut[], now: Date): ResvMineOut[]` · `resvWhen(r: ResvMineOut): string`.

- [ ] **Step 1: 실패 테스트**

`web/src/components/student/__tests__/rules.spec.ts`
```ts
import { describe, expect, it } from 'vitest'
import type { ResvMineOut } from '@/api/types'
import {
  activeCount,
  cancelKind,
  checkinState,
  chipDay,
  dateLabel,
  defaultEnd,
  durationText,
  endOptions,
  hmToMin,
  isRed,
  layoutLabel,
  minToHm,
  resvWhen,
  sortMine,
  spanKey,
  startOptions,
  untilText,
} from '../rules'
import { kstMinutes } from '@/lib/time'

const NOW = new Date('2026-10-23T01:42:00Z') // KST 2026-10-23(금) 10:42
const resv = (over: Partial<ResvMineOut> = {}): ResvMineOut => ({
  id: 1,
  date: '2026-10-23',
  s_h: 10,
  s_m: 50,
  e_h: 12,
  e_m: 0,
  type: 6,
  subject: '캡스톤 스터디',
  professor: '',
  status: 'approved',
  requested_at: null,
  decided_at: null,
  reject_reason: null,
  checked_in_at: null,
  cancelled_at: null,
  room_id: 11,
  building: '공학관',
  room: 401,
  ...over,
})

describe('kstMinutes', () => {
  it('KST 자정 경계 — UTC 15:00 은 KST 다음 날 00:00', () => {
    expect(kstMinutes(NOW)).toBe(642)
    expect(kstMinutes(new Date('2026-10-22T15:00:00Z'))).toBe(0)
    expect(kstMinutes(new Date('2026-10-22T14:59:00Z'))).toBe(1439)
  })
})

describe('상태 줄', () => {
  it('layout → 라벨, 색은 RED(1·5·6·7) 만 — 가용성(4)과 따로', () => {
    expect([1, 2, 3, 4, 5, 6, 7, 8].map(layoutLabel)).toEqual([
      '수업중',
      '쉬는시간',
      '휴강',
      '비어있음',
      '시험중',
      '특강',
      '대여중',
      '설정 대기',
    ])
    expect(layoutLabel(99)).toBe('확인 중')
    expect([1, 2, 3, 4, 5, 6, 7, 8].filter(isRed)).toEqual([1, 5, 6, 7])
  })

  it('until — "비어요"로 단정하지 않는다, null 은 자정까지', () => {
    expect(untilText(1, '10:50')).toBe('10:50 까지')
    expect(untilText(4, '13:00')).toBe('13:00 까지')
    expect(untilText(4, null)).toBe('오늘 계속 비어 있어요')
    expect(untilText(6, null)).toBe('자정까지')
  })
})

describe('시간 고르기', () => {
  it('hm ↔ 분, 길이 문장, 날짜 라벨', () => {
    expect(hmToMin('10:05')).toBe(605)
    expect(minToHm(605)).toBe('10:05')
    expect(durationText(180)).toBe('3시간')
    expect(durationText(90)).toBe('1시간 30분')
    expect(durationText(45)).toBe('45분')
    expect(dateLabel('2026-10-24')).toBe('10월 24일 토')
    expect(chipDay('2026-10-26')).toBe('월')
    expect(spanKey({ from: '10:00', to: '13:00' })).toBe('10:00-13:00')
  })

  it('시작 — 5분 단위, 끝 15분 전까지, 오늘은 지금 이후만', () => {
    const span = { from: '10:00', to: '10:30' }
    expect(startOptions(span, null).map(minToHm)).toEqual(['10:00', '10:05', '10:10', '10:15'])
    expect(startOptions(span, hmToMin('10:07')).map(minToHm)).toEqual(['10:10', '10:15'])
    expect(startOptions(span, hmToMin('10:15'))).toEqual([])
  })

  it('끝 — 시작 +15 ~ +120, 구간 끝을 넘지 않는다. 기본은 +60', () => {
    expect(endOptions(600, { from: '10:00', to: '10:30' }).map(minToHm)).toEqual([
      '10:15',
      '10:20',
      '10:25',
      '10:30',
    ])
    const long = endOptions(600, { from: '10:00', to: '21:00' })
    expect(minToHm(long[0])).toBe('10:15')
    expect(minToHm(long.at(-1)!)).toBe('12:00')
    expect(long).toHaveLength(22)
    expect(defaultEnd(600, { from: '10:00', to: '10:30' })).toBe(630)
    expect(defaultEnd(600, { from: '10:00', to: '21:00' })).toBe(660)
  })
})

describe('내 예약', () => {
  it('진행 중 — 시작 전 신청 + 끝나지 않은 승인만 (서버 MAX_ACTIVE 규칙)', () => {
    const list = [
      resv({ id: 1, status: 'requested', s_h: 11, s_m: 0, e_h: 12 }),
      resv({ id: 2, status: 'requested', s_h: 10, s_m: 0, e_h: 11 }),
      resv({ id: 3, status: 'approved', s_h: 10, s_m: 0, e_h: 11 }),
      resv({ id: 4, status: 'approved', s_h: 9, s_m: 0, e_h: 10 }),
      resv({ id: 5, status: 'rejected', date: '2026-10-25' }),
      resv({ id: 6, status: 'approved', date: '2026-10-22', s_h: 23, s_m: 0, e_h: 23, e_m: 50 }),
    ]
    expect(activeCount(list, NOW)).toBe(2)
  })

  it('체크인 창 — 시작 −10 ~ +15분, 밖이면 언제부터인지, 끝난 예약은 없음', () => {
    expect(checkinState(resv({ s_h: 10, s_m: 50 }), NOW)).toEqual({ kind: 'open' })
    expect(checkinState(resv({ s_h: 11, s_m: 0 }), NOW)).toEqual({ kind: 'before', from: '10:50' })
    expect(checkinState(resv({ s_h: 10, s_m: 20 }), NOW)).toEqual({ kind: 'after' })
    expect(checkinState(resv({ date: '2026-10-24', s_h: 10, s_m: 0 }), NOW)).toEqual({
      kind: 'before',
      from: '09:50',
    })
    expect(
      checkinState(resv({ checked_in_at: new Date('2026-10-23T01:52:00Z') }), NOW),
    ).toEqual({ kind: 'done', at: '10:52' })
    expect(checkinState(resv({ s_h: 9, s_m: 0, e_h: 10, e_m: 0 }), NOW)).toBeNull()
    expect(checkinState(resv({ status: 'requested' }), NOW)).toBeNull()
  })

  it('취소 — 신청은 철회(시작 뒤에도), 승인은 시작 전만, 그 밖엔 없음', () => {
    expect(cancelKind(resv({ status: 'requested', s_h: 9 }), NOW)).toBe('withdraw')
    expect(cancelKind(resv(), NOW)).toBe('cancel')
    expect(cancelKind(resv({ s_h: 10, s_m: 0 }), NOW)).toBeNull()
    expect(cancelKind(resv({ status: 'rejected' }), NOW)).toBeNull()
  })

  it('정렬 — 진행 중은 가까운 순, 나머지는 최근 순', () => {
    const a = resv({ id: 1, date: '2026-10-24', s_h: 10, s_m: 0 })
    const b = resv({ id: 2, status: 'requested', s_h: 11, s_m: 0 })
    const c = resv({ id: 3, status: 'rejected', date: '2026-10-20' })
    const d = resv({ id: 4, status: 'cancelled', date: '2026-10-22' })
    const e = resv({ id: 5, s_h: 9, s_m: 0, e_h: 10, e_m: 0 })
    expect(sortMine([c, a, e, d, b], NOW).map((r) => r.id)).toEqual([2, 1, 5, 4, 3])
  })

  it('카드 한 줄 시각', () => {
    expect(resvWhen(resv({ date: '2026-10-24', s_h: 10, s_m: 0, e_h: 12, e_m: 0 }))).toBe(
      '10/24 토 10:00–12:00',
    )
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/components/student/__tests__/rules.spec.ts`
Expected: FAIL — `Failed to resolve import "../rules"` (그리고 `"kstMinutes" is not exported`)

- [ ] **Step 3: 구현**

`web/src/lib/time.ts` — `formatHm` 함수 **아래**에 추가
```ts
/** KST 자정부터 흐른 분 (0..1439) — 학생 화면의 '지금'·체크인 창·오늘 칩 */
export function kstMinutes(d: Date): number {
  const k = kst(d)
  return Number(k.h) * 60 + Number(k.mi)
}
```

`web/src/components/student/rules.ts`
```ts
// 학생 웹 규칙 한 곳 — 서버 S10 §2.4·§4.1(reserve.py) 과 같은 값.
// 판정(빈 구간·겹침·합치기)은 서버가 하고, 여기는 표시·고르기·문장만 (student-room.md §데이터)
import type { FreeRange, ResvMineOut } from '@/api/types'
import { DAYS } from '@/components/domain/rules'
import { dayOfDate, formatHm, hm, kstDateStr, kstMinutes, md } from '@/lib/time'

/** e-Paper layout (terminal-epaper.md) — 4 만 '비어있음'(예약 가능, 개수·필터) */
export const FREE_LAYOUT = 4
const LAYOUT_LABEL: Record<number, string> = {
  1: '수업중',
  2: '쉬는시간',
  3: '휴강',
  4: '비어있음',
  5: '시험중',
  6: '특강',
  7: '대여중',
  8: '설정 대기',
}
export const layoutLabel = (layout: number) => LAYOUT_LABEL[layout] ?? '확인 중'
/** 색 — RED(1·5·6·7) 만 room.busy (tokens.md). 가용성(FREE_LAYOUT)과 섞지 않는다 */
export const isRed = (layout: number) => [1, 5, 6, 7].includes(layout)
/** until = 다음 상태 변화. '비어요'로 단정하지 않는다 — 수업 뒤는 쉬는시간일 수 있다 */
export function untilText(layout: number, until: string | null): string {
  if (until) return `${until} 까지`
  return layout === FREE_LAYOUT ? '오늘 계속 비어 있어요' : '자정까지'
}

// 서버 reserve.py 와 같은 값
export const MAX_ACTIVE = 3
export const MIN_MIN = 15
export const MAX_MIN = 120
export const STEP_MIN = 5
export const CHECKIN_BEFORE = 10
export const CHECKIN_AFTER = 15

// 서버 원문 대신 (spec §4.1) — student-room.md §화면이 거는 제약
export const FULL_TEXT = '이 강의실은 예약이 다 찼어요'
export const CAP_TEXT = `신청은 ${MAX_ACTIVE}건까지 할 수 있어요`
export const DAILY_TEXT = '오늘은 더 신청할 수 없어요. 내일 다시 시도해 주세요'
export const TAKEN_TEXT = '방금 다른 사람이 먼저 신청했어요. 비어 있는 시간을 새로 불러왔어요.'
export const STALE_TEXT = '선택한 시간으로 신청할 수 없어요. 비어 있는 시간을 새로 불러왔어요.'
export const CHANGED_TEXT = '이미 처리된 예약이에요. 목록을 새로 불러왔어요.'
export const CHECKIN_CLOSED_TEXT = '지금은 체크인할 수 없어요. 목록을 새로 불러왔어요.'
export const DOOR_HINT = '문 앞 화면에는 "학생 예약"으로만 표시돼요'

/** '10:05' → 605 */
export const hmToMin = (v: string) => Number(v.slice(0, 2)) * 60 + Number(v.slice(3, 5))
/** 605 → '10:05' */
export const minToHm = (m: number) => hm(Math.floor(m / 60), m % 60)
export function durationText(min: number): string {
  const h = Math.floor(min / 60)
  const m = min % 60
  if (h && m) return `${h}시간 ${m}분`
  return h ? `${h}시간` : `${m}분`
}
export const chipDay = (date: string) => DAYS[dayOfDate(date) - 1]
/** '2026-10-24' → '10월 24일 토' */
export const dateLabel = (date: string) =>
  `${Number(date.slice(5, 7))}월 ${Number(date.slice(8, 10))}일 ${chipDay(date)}`
export const spanKey = (s: FreeRange) => `${s.from}-${s.to}`

/** 시작 후보 — 5분 단위, 끝 15분 전까지. after(오늘의 지금 분)가 있으면 그보다 뒤만 */
export function startOptions(span: FreeRange, after: number | null): number[] {
  const out: number[] = []
  for (let m = hmToMin(span.from); m + MIN_MIN <= hmToMin(span.to); m += STEP_MIN)
    if (after === null || m > after) out.push(m)
  return out
}
/** 끝 후보 — 시작 +15 ~ +120, 구간 끝을 넘지 않는다 */
export function endOptions(start: number, span: FreeRange): number[] {
  const out: number[] = []
  for (let m = start + MIN_MIN; m <= Math.min(start + MAX_MIN, hmToMin(span.to)); m += STEP_MIN)
    out.push(m)
  return out
}
export const defaultEnd = (start: number, span: FreeRange) =>
  Math.min(start + 60, hmToMin(span.to))

// ---- 내 예약 — 'KST 달력 날짜의 분'으로 비교 (서버 local_dt 와 같은 축) ----
const dayMin = (date: string) => Date.parse(`${date}T00:00:00Z`) / 60_000
const startAt = (r: ResvMineOut) => dayMin(r.date) + r.s_h * 60 + r.s_m
const endAt = (r: ResvMineOut) => dayMin(r.date) + r.e_h * 60 + r.e_m
const nowAt = (now: Date) => dayMin(kstDateStr(now)) + kstMinutes(now)

/** 서버 MAX_ACTIVE 판정과 같다 — 시작 전 신청 + 끝나지 않은 승인 */
export function activeCount(list: ResvMineOut[], now: Date): number {
  const n = nowAt(now)
  return list.filter((r) =>
    r.status === 'requested' ? startAt(r) > n : r.status === 'approved' && endAt(r) > n,
  ).length
}

export type CheckinState =
  | { kind: 'done'; at: string }
  | { kind: 'open' }
  | { kind: 'before'; from: string }
  | { kind: 'after' }
/** 승인 예약만. 끝난 예약은 null(버튼 없음). 서버와 시계가 어긋나면 409 — 화면이 문장+재조회 */
export function checkinState(r: ResvMineOut, now: Date): CheckinState | null {
  if (r.status !== 'approved') return null
  if (r.checked_in_at) return { kind: 'done', at: formatHm(r.checked_in_at) }
  const n = nowAt(now)
  const s = startAt(r)
  if (n > endAt(r)) return null
  if (n < s - CHECKIN_BEFORE)
    return { kind: 'before', from: minToHm((((s - CHECKIN_BEFORE) % 1440) + 1440) % 1440) }
  return n <= s + CHECKIN_AFTER ? { kind: 'open' } : { kind: 'after' }
}

export type CancelKind = 'withdraw' | 'cancel'
/** requested → 철회(행 삭제), approved → 시작 전만 취소 (S10 §2.1) */
export function cancelKind(r: ResvMineOut, now: Date): CancelKind | null {
  if (r.status === 'requested') return 'withdraw'
  return r.status === 'approved' && startAt(r) > nowAt(now) ? 'cancel' : null
}

/** 진행 중(대기 · 안 끝난 승인)은 가까운 순, 나머지는 최근 순 */
export function sortMine(list: ResvMineOut[], now: Date): ResvMineOut[] {
  const n = nowAt(now)
  const live = (r: ResvMineOut) =>
    r.status === 'requested' || (r.status === 'approved' && endAt(r) > n)
  return [
    ...list.filter(live).sort((a, b) => startAt(a) - startAt(b)),
    ...list.filter((r) => !live(r)).sort((a, b) => startAt(b) - startAt(a)),
  ]
}

/** '10/24 토 10:00–12:00' */
export const resvWhen = (r: ResvMineOut) =>
  `${md(r.date)} ${chipDay(r.date)} ${hm(r.s_h, r.s_m)}–${hm(r.e_h, r.e_m)}`
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test src/components/student src/lib && pnpm typecheck && pnpm lint`
Expected: PASS — rules.spec 11 tests, time·calendar spec 그대로.

- [ ] **Step 5: 커밋**

```bash
git add web/src/lib/time.ts web/src/components/student
git commit -m "feat(web): 학생 규칙 한 곳 — layout 라벨·상한·체크인 창·시간 고르기·학생 문장, kstMinutes"
```

---

### Task 3: 즐겨찾기 · 최근 건물 (`favorites.ts`)

**Files:**
- Create: `web/src/student/favorites.ts`
- Test: `web/src/student/__tests__/favorites.spec.ts`

**Interfaces:**
- Produces: `favKey(bld: string, room: number): string`(`'E-401'`) · `favorites: Ref<string[]>`(모듈 상태, 쓰기 가능) · `toggleFavorite(key: string): void` · `lastBld(): string | null` · `rememberBld(bld: string): void`. 저장 키 `esc.fav`(JSON 호수 배열) · `esc.lastBld`(한 글자).

- [ ] **Step 1: 실패 테스트**

`web/src/student/__tests__/favorites.spec.ts`
```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'

// favorites 는 모듈이 뜰 때 한 번 읽는다 — 매 테스트 새로 import
const load = () => import('@/student/favorites')

beforeEach(() => {
  vi.restoreAllMocks()
  vi.resetModules()
  localStorage.clear()
})

describe('즐겨찾기 (student-room.md — localStorage 호수 배열)', () => {
  it('저장된 목록을 읽고, 토글하면 esc.fav 에 호수 배열로 남긴다', async () => {
    localStorage.setItem('esc.fav', JSON.stringify(['E-401']))
    const f = await load()
    expect(f.favorites.value).toEqual(['E-401'])
    f.toggleFavorite(f.favKey('E', 405))
    expect(JSON.parse(localStorage.getItem('esc.fav')!)).toEqual(['E-401', 'E-405'])
    f.toggleFavorite('E-401')
    expect(f.favorites.value).toEqual(['E-405'])
    expect(localStorage.getItem('esc.fav')).toBe('["E-405"]')
  })

  it('깨진 값·모양이 다른 값은 버린다', async () => {
    localStorage.setItem('esc.fav', '{oops')
    expect((await load()).favorites.value).toEqual([])
    vi.resetModules()
    localStorage.setItem('esc.fav', JSON.stringify(['E-401', 3, '<img>', 'e-1', 'K-12345']))
    expect((await load()).favorites.value).toEqual(['E-401'])
    vi.resetModules()
    localStorage.setItem('esc.fav', JSON.stringify({ a: 1 }))
    expect((await load()).favorites.value).toEqual([])
  })

  it('localStorage 가 막혀도(사생활 보호 모드) 이번 방문 동안은 동작한다', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('quota', 'QuotaExceededError')
    })
    const f = await load()
    expect(f.favorites.value).toEqual([])
    expect(() => f.toggleFavorite('E-401')).not.toThrow()
    expect(f.favorites.value).toEqual(['E-401'])
    expect(f.lastBld()).toBeNull()
    expect(() => f.rememberBld('E')).not.toThrow()
  })

  it('마지막 건물 — 대문자 한 글자만 믿는다', async () => {
    const f = await load()
    expect(f.lastBld()).toBeNull()
    f.rememberBld('K')
    expect(f.lastBld()).toBe('K')
    localStorage.setItem('esc.lastBld', '../admin')
    expect(f.lastBld()).toBeNull()
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/student/__tests__/favorites.spec.ts`
Expected: FAIL — `Failed to resolve import "@/student/favorites"`

- [ ] **Step 3: 구현**

`web/src/student/favorites.ts`
```ts
import { ref } from 'vue'

// 즐겨찾기·마지막 건물은 localStorage (student-room.md — 서버 필드 없음, 기기를 바꾸면 사라짐을 감수).
// 자격증명은 여기 두지 않는다(auth.md). 사생활 보호 모드면 읽기·쓰기가 던진다 — 이번 방문 동안만 기억한다.
const FAV = 'esc.fav'
const LAST = 'esc.lastBld'
const KEY_RE = /^[A-Z]-\d{1,4}$/

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* 기억 못 해도 화면은 동작한다 */
  }
}
function parse(raw: string | null): string[] {
  try {
    const v: unknown = JSON.parse(raw ?? '[]')
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string' && KEY_RE.test(x)) : []
  } catch {
    return []
  }
}

/** 'E-401' */
export const favKey = (bld: string, room: number) => `${bld}-${room}`
export const favorites = ref<string[]>(parse(read(FAV)))

export function toggleFavorite(key: string): void {
  favorites.value = favorites.value.includes(key)
    ? favorites.value.filter((k) => k !== key)
    : [...favorites.value, key]
  write(FAV, JSON.stringify(favorites.value))
}

/** `/` 로 들어왔을 때 보낼 건물 — 대문자 한 글자만 믿는다 */
export function lastBld(): string | null {
  const v = read(LAST)
  return v && /^[A-Z]$/.test(v) ? v : null
}
export const rememberBld = (bld: string) => write(LAST, bld)
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test src/student && pnpm typecheck && pnpm lint`
Expected: PASS — favorites.spec 4 tests, F1 router.spec 그대로.

- [ ] **Step 5: 커밋**

```bash
git add web/src/student/favorites.ts web/src/student/__tests__/favorites.spec.ts
git commit -m "feat(web): 학생 즐겨찾기·마지막 건물 — localStorage 가 막혀도 이번 방문 동안 동작"
```

---

### Task 4: 격자 배치(`grid.ts`) · 화면 계산(`roomView.ts`)

**Files:**
- Create: `web/src/components/student/grid.ts`, `web/src/student/roomView.ts`
- Test: `web/src/components/student/__tests__/grid.spec.ts`, `web/src/student/__tests__/roomView.spec.ts`

**Interfaces:**
- Consumes: `BusyDay`·`BusySpan`·`FreeDay`·`FreeRange`·`RoomStateOut`·`SlotType`(Task 1), `FREE_LAYOUT`·`hmToMin`·`minToHm`(Task 2).
- Produces (`grid.ts`): `ROW_MIN = 30` · `interface GridRange { start: number; end: number }`(분) · `interface GridBlock { day: number; top: number; height: number; label: string; extra: string; type: SlotType; mine: boolean; requested: boolean }` · `gridRange(busy: BusyDay[]): GridRange` · `gridRows(r: GridRange): number` · `visibleDays(busy: BusyDay[]): number[]` · `weekBlocks(busy: BusyDay[], range: GridRange, rowPx: number): GridBlock[]` · `nowTop(nowMin: number, range: GridRange, rowPx: number): number | null`.
- Produces (`roomView.ts`): `interface BuildingItem { id: number; name: string; bld: string; rooms: number; free: number }` · `buildingsOf(rooms: RoomStateOut[]): BuildingItem[]` · `OPEN_MIN = 540` · `CLOSE_MIN = 1260` · `interface TodayRow { from: string; to: string; label: string; type: SlotType | null; mine: boolean; requested: boolean; now: boolean }` · `todayRows(spans: BusySpan[], nowMin: number): TodayRow[]` · `nextFree(free: FreeDay[]): FreeRange | null`.

- [ ] **Step 1: 실패 테스트**

`web/src/components/student/__tests__/grid.spec.ts`
```ts
import { describe, expect, it } from 'vitest'
import type { BusySpan } from '@/api/types'
import { gridRange, gridRows, nowTop, visibleDays, weekBlocks } from '../grid'

const span = (from: string, to: string, over: Partial<BusySpan> = {}): BusySpan => ({
  from,
  to,
  label: '수업',
  type: 1,
  mine: false,
  status: null,
  ...over,
})
const BASE = { start: 540, end: 1080 }

describe('grid', () => {
  it('범위 — 기본 09–18, 벗어난 블록이 있으면 30분 단위로 편다, 빈강의실(4)은 무시', () => {
    expect(gridRange([])).toEqual(BASE)
    expect(
      gridRange([{ day: 1, spans: [span('08:10', '09:00'), span('17:00', '19:40')] }]),
    ).toEqual({ start: 480, end: 1200 })
    expect(gridRange([{ day: 1, spans: [span('06:00', '07:00', { type: 4 })] }])).toEqual(BASE)
    expect(gridRows(BASE)).toBe(18)
  })

  it('요일 — 월~금, 토·일은 그 요일에 그릴 블록이 있을 때만', () => {
    expect(visibleDays([{ day: 6, spans: [] }])).toEqual([1, 2, 3, 4, 5])
    expect(visibleDays([{ day: 7, spans: [span('10:00', '11:00')] }])).toEqual([1, 2, 3, 4, 5, 7])
    expect(visibleDays([{ day: 6, spans: [span('10:00', '11:00', { type: 4 })] }])).toEqual([
      1, 2, 3, 4, 5,
    ])
  })

  it('블록 — 30분 행 높이 기준 위치, 서버가 합친 라벨 그대로, 내 신청 표시, 빈강의실은 없음', () => {
    const b = weekBlocks(
      [
        {
          day: 5,
          spans: [
            span('10:00', '13:00', { label: '알고리즘 외 1건' }),
            span('15:00', '16:00', { label: '캡스톤 스터디', type: 6, mine: true, status: 'requested' }),
            span('17:00', '17:30', { type: 4 }),
          ],
        },
      ],
      BASE,
      24,
    )
    expect(b).toEqual([
      {
        day: 5,
        top: 48,
        height: 144,
        label: '알고리즘 외 1건',
        extra: '10:00–13:00',
        type: 1,
        mine: false,
        requested: false,
      },
      {
        day: 5,
        top: 288,
        height: 48,
        label: '캡스톤 스터디',
        extra: '15:00–16:00',
        type: 6,
        mine: true,
        requested: true,
      },
    ])
  })

  it('지금 선 — 범위 안에서만', () => {
    expect(nowTop(642, BASE, 32)).toBeCloseTo(108.8)
    expect(nowTop(500, BASE, 32)).toBeNull()
    expect(nowTop(1080, BASE, 32)).toBeNull()
  })
})
```

`web/src/student/__tests__/roomView.spec.ts`
```ts
import { describe, expect, it } from 'vitest'
import type { BusySpan, RoomStateOut } from '@/api/types'
import { buildingsOf, nextFree, todayRows } from '@/student/roomView'

const room = (over: Partial<RoomStateOut>): RoomStateOut => ({
  room_id: 1,
  building_id: 3,
  building: '공학관',
  bld: 'E',
  room: 401,
  layout: 4,
  until: null,
  ...over,
})
const span = (from: string, to: string, over: Partial<BusySpan> = {}): BusySpan => ({
  from,
  to,
  label: '수업',
  type: 1,
  mine: false,
  status: null,
  ...over,
})

describe('roomView', () => {
  it('건물 — 방 목록에서 파생, 글자 순, 강의실 수·빈 곳 수', () => {
    const out = buildingsOf([
      room({ room_id: 1, building_id: 4, building: '운영관', bld: 'K', room: 101, layout: 1 }),
      room({ room_id: 2, room: 401, layout: 1 }),
      room({ room_id: 3, room: 402 }),
      room({ room_id: 4, room: 403, layout: 2 }),
    ])
    expect(out).toEqual([
      { id: 3, name: '공학관', bld: 'E', rooms: 3, free: 1 },
      { id: 4, name: '운영관', bld: 'K', rooms: 1, free: 0 },
    ])
  })

  it('오늘 목록 — 빈 구간도 행, 지금 행 하나, 내 신청 표시', () => {
    const rows = todayRows(
      [
        span('15:00', '16:00', { label: '캡스톤 스터디', type: 6, mine: true, status: 'requested' }),
        span('10:00', '13:00', { label: '알고리즘 외 1건' }),
      ],
      642,
    )
    expect(rows.map((r) => `${r.from}-${r.to} ${r.label}${r.now ? ' *' : ''}`)).toEqual([
      '09:00-10:00 비어있음',
      '10:00-13:00 알고리즘 외 1건 *',
      '13:00-15:00 비어있음',
      '15:00-16:00 캡스톤 스터디',
      '16:00-21:00 비어있음',
    ])
    expect(rows[0].type).toBeNull()
    expect(rows[3]).toMatchObject({ type: 6, mine: true, requested: true, now: false })
  })

  it('오늘 목록 — 운영 시간 밖 블록이면 창을 넓히고, 블록이 없으면 하루 전체가 빈 행 하나', () => {
    expect(todayRows([], 600)).toEqual([
      {
        from: '09:00',
        to: '21:00',
        label: '비어있음',
        type: null,
        mine: false,
        requested: false,
        now: true,
      },
    ])
    expect(todayRows([span('07:30', '09:30')], 480).map((r) => `${r.from}-${r.to}`)).toEqual([
      '07:30-09:30',
      '09:30-21:00',
    ])
    expect(todayRows([], 480).some((r) => r.now)).toBe(false)
  })

  it('다음 비는 시간 — 오늘(free 첫 날)의 첫 구간, 없으면 null', () => {
    expect(nextFree([{ date: '2026-10-23', spans: [{ from: '13:00', to: '15:00' }] }])).toEqual({
      from: '13:00',
      to: '15:00',
    })
    expect(nextFree([{ date: '2026-10-23', spans: [] }])).toBeNull()
    expect(nextFree([])).toBeNull()
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/components/student/__tests__/grid.spec.ts src/student/__tests__/roomView.spec.ts`
Expected: FAIL — `Failed to resolve import "../grid"` / `"@/student/roomView"`

- [ ] **Step 3: 구현**

`web/src/components/student/grid.ts`
```ts
// 주간 격자 배치 — 겹침 합치기는 서버(WeekOut.busy)가 이미 했다. 여기는 위치만 (student-room.md §겹침)
import type { BusyDay, BusySpan, SlotType } from '@/api/types'
import { hmToMin } from './rules'

export const ROW_MIN = 30
const GRID_START = 9 * 60
const GRID_END = 18 * 60

export interface GridRange {
  start: number
  end: number
}
export interface GridBlock {
  day: number
  top: number
  height: number
  label: string
  /** 'HH:MM–HH:MM' */
  extra: string
  type: SlotType
  mine: boolean
  /** 내 신청(대기) — brand 점선 테두리 */
  requested: boolean
}

/** 빈강의실(4)은 칠하지 않는다 (tokens.md 「비어있음은 칠하지 않는다」) */
const drawn = (s: BusySpan) => s.type !== 4

/** 09–18 이 기본, 벗어난 블록이 있으면 30분 단위로 편다 ("해당 슬롯이 있으면 자동으로 편다") */
export function gridRange(busy: BusyDay[]): GridRange {
  const spans = busy.flatMap((d) => d.spans.filter(drawn))
  return {
    start: Math.min(GRID_START, ...spans.map((s) => Math.floor(hmToMin(s.from) / ROW_MIN) * ROW_MIN)),
    end: Math.max(GRID_END, ...spans.map((s) => Math.ceil(hmToMin(s.to) / ROW_MIN) * ROW_MIN)),
  }
}
export const gridRows = (r: GridRange) => (r.end - r.start) / ROW_MIN

/** 주중 5열 + 그릴 블록이 있는 주말 */
export function visibleDays(busy: BusyDay[]): number[] {
  const weekend = [6, 7].filter((d) => busy.some((b) => b.day === d && b.spans.some(drawn)))
  return [1, 2, 3, 4, 5, ...weekend]
}

export function weekBlocks(busy: BusyDay[], range: GridRange, rowPx: number): GridBlock[] {
  const px = (m: number) => ((m - range.start) / ROW_MIN) * rowPx
  return busy.flatMap((d) =>
    d.spans.filter(drawn).map((s) => ({
      day: d.day,
      top: px(hmToMin(s.from)),
      height: px(hmToMin(s.to)) - px(hmToMin(s.from)),
      label: s.label,
      extra: `${s.from}–${s.to}`,
      type: s.type,
      mine: s.mine,
      requested: s.mine && s.status === 'requested',
    })),
  )
}

/** 오늘 열의 brand 2px 선 — 범위 밖이면 긋지 않는다 */
export function nowTop(nowMin: number, range: GridRange, rowPx: number): number | null {
  if (nowMin < range.start || nowMin >= range.end) return null
  return ((nowMin - range.start) / ROW_MIN) * rowPx
}
```

`web/src/student/roomView.ts`
```ts
// 학생 화면 계산 (순수 함수) — 판정은 서버가 준 값(layout·busy·free)을 쓴다
import type { BusySpan, FreeDay, FreeRange, RoomStateOut, SlotType } from '@/api/types'
import { FREE_LAYOUT, hmToMin, minToHm } from '@/components/student/rules'

export interface BuildingItem {
  id: number
  name: string
  bld: string
  rooms: number
  free: number
}
/** 건물 목록 — 학생용 건물 API 가 없다(spec §5 "rooms 에서 파생") */
export function buildingsOf(rooms: RoomStateOut[]): BuildingItem[] {
  const m = new Map<number, BuildingItem>()
  for (const r of rooms) {
    const b = m.get(r.building_id) ?? {
      id: r.building_id,
      name: r.building,
      bld: r.bld,
      rooms: 0,
      free: 0,
    }
    b.rooms += 1
    if (r.layout === FREE_LAYOUT) b.free += 1
    m.set(r.building_id, b)
  }
  return [...m.values()].sort((a, b) => a.bld.localeCompare(b.bld))
}

/** 운영 시간 (서버 reserve.OPEN_MIN·CLOSE_MIN) — 오늘 목록의 기본 창 */
export const OPEN_MIN = 9 * 60
export const CLOSE_MIN = 21 * 60

export interface TodayRow {
  from: string
  to: string
  label: string
  /** null = 빈 구간 행 */
  type: SlotType | null
  mine: boolean
  requested: boolean
  now: boolean
}
/** 오늘 목록 — 빈 구간도 행으로(학생이 언제 비는지 계산하지 않게). spans 는 서버가 합쳐 겹치지 않는다 */
export function todayRows(spans: BusySpan[], nowMin: number): TodayRow[] {
  const sorted = [...spans].sort((a, b) => hmToMin(a.from) - hmToMin(b.from))
  const start = Math.min(OPEN_MIN, ...sorted.map((s) => hmToMin(s.from)))
  const end = Math.max(CLOSE_MIN, ...sorted.map((s) => hmToMin(s.to)))
  const rows: TodayRow[] = []
  const isNow = (a: number, b: number) => a <= nowMin && nowMin < b
  const gap = (a: number, b: number) =>
    rows.push({
      from: minToHm(a),
      to: minToHm(b),
      label: '비어있음',
      type: null,
      mine: false,
      requested: false,
      now: isNow(a, b),
    })
  let cur = start
  for (const s of sorted) {
    const a = hmToMin(s.from)
    const b = hmToMin(s.to)
    if (a > cur) gap(cur, a)
    rows.push({
      from: s.from,
      to: s.to,
      label: s.label,
      type: s.type,
      mine: s.mine,
      requested: s.mine && s.status === 'requested',
      now: isNow(a, b),
    })
    cur = Math.max(cur, b)
  }
  if (cur < end) gap(cur, end)
  return rows
}

/** 넓은 폭 '다음 비는 시간' 카드 — 서버 free 의 오늘 첫 구간(지금 이후, 신청 가능한 것) */
export const nextFree = (free: FreeDay[]): FreeRange | null => free[0]?.spans[0] ?? null
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test src/components/student src/student && pnpm typecheck && pnpm lint`
Expected: PASS — grid.spec 4 tests, roomView.spec 4 tests.

- [ ] **Step 5: 커밋**

```bash
git add web/src/components/student/grid.ts web/src/components/student/__tests__/grid.spec.ts web/src/student/roomView.ts web/src/student/__tests__/roomView.spec.ts
git commit -m "feat(web): 학생 격자 배치·오늘 목록·건물 파생 — 서버가 합친 busy 를 위치로만 바꾼다"
```

---

### Task 5: Badge `brand` solid · ResvStatusBadge · FavoriteStar · RoomListRow

**Files:**
- Modify: `web/src/components/ui/Badge.vue`
- Create: `web/src/components/student/ResvStatusBadge.vue`, `web/src/components/student/FavoriteStar.vue`, `web/src/components/student/RoomListRow.vue`
- Test: `web/src/components/student/__tests__/rows.spec.ts`

**Interfaces:**
- Consumes: `ResvStatus`(F2), `Badge`(F1).
- Produces: Badge — `tone="brand" variant="solid"` 조합(`brand` 바탕 + `on-brand` 글자).
- Produces: `ResvStatusBadge` props `{ status: ResvStatus }` — requested `대기중`/neutral outline · approved `승인됨`/busy tint · rejected `거절됨` · cancelled `취소됨` · expired `만료됨`(셋 다 neutral outline).
- Produces: `FavoriteStar` props `{ on: boolean }`, emits `toggle: []` — 48×48 `button`, `★`/`☆`, `aria-label` `즐겨찾기 해제`/`즐겨찾기 추가`.
- Produces: `RoomListRow` props `{ to: string; room: number; state: 'busy' | 'free'; label: string; until: string; fav: boolean }`, emits `toggleFav: []` — 루트 `li.row`(부모가 `ul` 을 준다), 왼쪽 `RouterLink.row__link`(56px, `aria-label="401호 수업중 10:50 까지"`, `.row__room`·`.row__state`·`.row__until`), 오른쪽 FavoriteStar(링크 밖).

- [ ] **Step 1: 실패 테스트**

`web/src/components/student/__tests__/rows.spec.ts`
```ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { ResvStatus } from '@/api/types'
import FavoriteStar from '../FavoriteStar.vue'
import ResvStatusBadge from '../ResvStatusBadge.vue'
import RoomListRow from '../RoomListRow.vue'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/:rest(.*)*', component: { render: () => null } }],
})

describe('ResvStatusBadge — 색이 아니라 라벨이 진다, 적색은 승인(방이 쓰인다)만', () => {
  it.each<[ResvStatus, string, string, string]>([
    ['requested', '대기중', 'badge--neutral', 'badge--outline'],
    ['approved', '승인됨', 'badge--busy', 'badge--tint'],
    ['rejected', '거절됨', 'badge--neutral', 'badge--outline'],
    ['cancelled', '취소됨', 'badge--neutral', 'badge--outline'],
    ['expired', '만료됨', 'badge--neutral', 'badge--outline'],
  ])('%s → %s', (status, label, tone, variant) => {
    const b = mount(ResvStatusBadge, { props: { status } }).get('.badge')
    expect(b.text()).toBe(label)
    expect(b.classes()).toEqual(expect.arrayContaining([tone, variant]))
  })
})

describe('FavoriteStar', () => {
  it('모양과 이름이 함께 바뀐다, 누르면 toggle', async () => {
    const w = mount(FavoriteStar, { props: { on: false } })
    const b = w.get('button')
    expect(b.text()).toBe('☆')
    expect(b.attributes('aria-label')).toBe('즐겨찾기 추가')
    await b.trigger('click')
    expect(w.emitted('toggle')).toHaveLength(1)
    await w.setProps({ on: true })
    expect(b.text()).toBe('★')
    expect(b.attributes('aria-label')).toBe('즐겨찾기 해제')
    expect(b.classes()).toContain('star--on')
  })
})

describe('RoomListRow', () => {
  const props = {
    to: '/E/401',
    room: 401,
    state: 'busy' as const,
    label: '수업중',
    until: '10:50 까지',
    fav: false,
  }

  it('왼쪽 대부분이 링크 — 호수·상태·언제, ★ 은 링크 밖 버튼', () => {
    const w = mount(RoomListRow, { props, global: { plugins: [router] } })
    const a = w.get('a.row__link')
    expect(a.attributes('href')).toBe('/E/401')
    // 칸이 붙어 읽히지 않게 링크 이름을 한 문장으로 ("401호수업중" 방지)
    expect(a.attributes('aria-label')).toBe('401호 수업중 10:50 까지')
    expect(a.get('.row__room').text()).toBe('401호')
    expect(a.get('.row__state .badge').text()).toBe('수업중')
    expect(a.get('.row__state .badge').classes()).toContain('badge--busy')
    expect(a.get('.row__until').text()).toBe('10:50 까지')
    expect(a.find('button').exists()).toBe(false)
    expect(w.get('li > button').attributes('aria-label')).toBe('즐겨찾기 추가')
  })

  it('비어 있으면 칠하지 않는다 — 라벨만, ★ 을 누르면 toggleFav', async () => {
    const w = mount(RoomListRow, {
      props: { ...props, state: 'free', label: '비어있음', until: '13:00 까지', fav: true },
      global: { plugins: [router] },
    })
    expect(w.find('.row__state .badge').exists()).toBe(false)
    expect(w.get('.row__free').text()).toBe('비어있음')
    await w.get('li > button').trigger('click')
    expect(w.emitted('toggleFav')).toHaveLength(1)
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/components/student/__tests__/rows.spec.ts`
Expected: FAIL — `Failed to resolve import "../FavoriteStar.vue"`

- [ ] **Step 3: 구현**

`web/src/components/ui/Badge.vue` — `<style scoped>` 의 `.badge--danger.badge--outline { … }` 규칙 **아래**에 추가
```css
/* 학생 강의실 화면의 '지금' 배지 — brand 채움 + 흰 글자 (student-room.md 화면 2). 적색은 쓰지 않는다 */
.badge--brand.badge--solid {
  background: var(--brand);
  color: var(--on-brand);
}
```

`web/src/components/student/ResvStatusBadge.vue`
```vue
<script setup lang="ts">
import { computed } from 'vue'
import type { ResvStatus } from '@/api/types'
import Badge from '@/components/ui/Badge.vue'

const props = defineProps<{ status: ResvStatus }>()
// approved 만 room.busy 틴트 — 적색은 "그 방이 실제로 쓰인다"는 뜻 (student-room.md §상태 다섯)
const LABEL: Record<ResvStatus, string> = {
  requested: '대기중',
  approved: '승인됨',
  rejected: '거절됨',
  cancelled: '취소됨',
  expired: '만료됨',
}
const busy = computed(() => props.status === 'approved')
</script>

<template>
  <Badge :tone="busy ? 'busy' : 'neutral'" :variant="busy ? 'tint' : 'outline'" size="sm">{{
    LABEL[status]
  }}</Badge>
</template>
```

`web/src/components/student/FavoriteStar.vue`
```vue
<script setup lang="ts">
// 저장(localStorage)은 화면이 한다 — 이 컴포넌트는 모양과 이름만 (student-room.md)
defineProps<{ on: boolean }>()
const emit = defineEmits<{ toggle: [] }>()
</script>

<template>
  <button
    type="button"
    class="star"
    :class="{ 'star--on': on }"
    :aria-label="on ? '즐겨찾기 해제' : '즐겨찾기 추가'"
    @click="emit('toggle')"
  >
    {{ on ? '★' : '☆' }}
  </button>
</template>

<style scoped>
.star {
  flex: 0 0 auto;
  width: 48px;
  height: 48px;
  padding: 0;
  border: 0;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-disabled);
  font: inherit;
  font-size: var(--font-size-xl);
  line-height: 1;
  cursor: pointer;
}
.star--on {
  color: var(--brand);
}
.star:hover {
  background: var(--sunken);
}
</style>
```

`web/src/components/student/RoomListRow.vue`
```vue
<script setup lang="ts">
import { RouterLink } from 'vue-router'
import Badge from '@/components/ui/Badge.vue'
import FavoriteStar from './FavoriteStar.vue'

// 링크 안에 버튼을 넣지 않는다 — 어느 쪽이 눌렸는지·스크린리더가 헷갈린다 (student-room.md 화면 1)
defineProps<{
  to: string
  room: number
  state: 'busy' | 'free'
  label: string
  until: string
  fav: boolean
}>()
const emit = defineEmits<{ toggleFav: [] }>()
</script>

<template>
  <li class="row">
    <RouterLink :to="to" class="row__link" :aria-label="`${room}호 ${label} ${until}`">
      <span class="row__room num">{{ room }}호</span>
      <span class="row__state">
        <Badge v-if="state === 'busy'" tone="busy" size="sm">{{ label }}</Badge>
        <span v-else class="row__free">{{ label }}</span>
      </span>
      <span class="row__until num">{{ until }}</span>
      <span class="row__chev" aria-hidden="true">›</span>
    </RouterLink>
    <FavoriteStar :on="fav" @toggle="emit('toggleFav')" />
  </li>
</template>

<style scoped>
.row {
  display: flex;
  align-items: center;
  min-height: 56px;
  padding-right: var(--space-1);
  border-bottom: var(--border-thin) solid var(--line-1);
}
.row:last-child {
  border-bottom: 0;
}
.row__link {
  flex: 1;
  min-width: 0;
  min-height: 56px;
  display: grid;
  grid-template-columns: auto 1fr auto;
  column-gap: var(--space-3);
  align-items: center;
  padding: var(--space-2) 0 var(--space-2) var(--space-4);
  color: var(--text-1);
  text-decoration: none;
}
.row__room {
  grid-column: 1;
  grid-row: 1 / 3;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.row__state {
  grid-column: 2;
  grid-row: 1;
  display: flex;
  align-items: center;
  font-size: var(--font-size-sm);
}
.row__free {
  color: var(--room-free-text);
  font-weight: var(--font-weight-bold);
}
.row__until {
  grid-column: 2;
  grid-row: 2;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.row__chev {
  grid-column: 3;
  grid-row: 1 / 3;
  font-size: var(--font-size-lg);
  color: var(--text-3);
}
</style>
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test src/components && pnpm typecheck && pnpm lint`
Expected: PASS — rows.spec 8 tests(it.each 5 + 3), 토큰 가드 통과(새 `.vue` 3개).

- [ ] **Step 5: 커밋**

```bash
git add web/src/components/ui/Badge.vue web/src/components/student
git commit -m "feat(web): 학생 목록 행·즐겨찾기 별·예약 상태 배지, '지금' 배지용 Badge brand solid"
```

---

### Task 6: WeekGrid

**Files:**
- Create: `web/src/components/student/WeekGrid.vue`
- Test: `web/src/components/student/__tests__/weekGrid.spec.ts`

**Interfaces:**
- Consumes: `GridBlock`·`GridRange`·`ROW_MIN`·`gridRows`(Task 4), `minToHm`(Task 2), `DAYS`·`TYPE_LABEL`·`BUSY_TYPES`(F2).
- Produces: `WeekGrid` props `{ days: number[]; blocks: GridBlock[]; rowHeight: 24 | 32; range: GridRange; todayIndex?: number (-1); nowTop?: number | null }`. DOM: `.wg`(32 이면 `.wg--wide`) · `.wg__day`(오늘 `.wg__day--today`) · `.wg__time` · `.wg__col[role=list][aria-label="금요일"]` · `.wg__blk[role=listitem][aria-label="금 10:00–13:00 알고리즘 외 1건"]`(`--busy`/`--off`/`--plain`, `--mine`, `--requested`, 내 신청이면 이름 끝에 ` 대기중`) · `.wg__now`.

- [ ] **Step 1: 실패 테스트**

`web/src/components/student/__tests__/weekGrid.spec.ts`
```ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import type { GridBlock } from '../grid'
import WeekGrid from '../WeekGrid.vue'

const range = { start: 540, end: 1080 }
const blocks: GridBlock[] = [
  {
    day: 5,
    top: 48,
    height: 144,
    label: '알고리즘 외 1건',
    extra: '10:00–13:00',
    type: 1,
    mine: false,
    requested: false,
  },
  {
    day: 2,
    top: 0,
    height: 48,
    label: '운영체제',
    extra: '09:00–10:00',
    type: 3,
    mine: false,
    requested: false,
  },
  {
    day: 5,
    top: 288,
    height: 48,
    label: '캡스톤 스터디',
    extra: '15:00–16:00',
    type: 6,
    mine: true,
    requested: true,
  },
]
const props = {
  days: [1, 2, 3, 4, 5],
  blocks,
  rowHeight: 24 as const,
  range,
  todayIndex: 4,
  nowTop: 81.6,
}

describe('WeekGrid — 요일 가로 × 시간 세로, 겹침은 서버가 합친 것을 받는다', () => {
  it('요일 머리·오늘 열, 시각 라벨은 정시마다, 지금 선은 오늘 열에만', () => {
    const w = mount(WeekGrid, { props })
    const heads = w.findAll('.wg__day')
    expect(heads.map((d) => d.text())).toEqual(['월', '화', '수', '목', '금'])
    expect(heads[4].classes()).toContain('wg__day--today')
    expect(w.findAll('.wg__col')[4].classes()).toContain('wg__col--today')
    expect(w.findAll('.wg__time').map((t) => t.text())).toEqual([
      '09:00',
      '10:00',
      '11:00',
      '12:00',
      '13:00',
      '14:00',
      '15:00',
      '16:00',
      '17:00',
    ])
    expect(w.findAll('.wg__now')).toHaveLength(1)
    expect(w.findAll('.wg__col')[4].get('.wg__now').attributes('style')).toContain('top: 81.6px')
    expect(w.findAll('.wg__col')[0].attributes('style')).toContain('height: 432px')
  })

  it('블록 — 위치·높이, 읽는 이름, 사용중·휴강·내 신청 모양', () => {
    const w = mount(WeekGrid, { props })
    const algo = w.get('[aria-label="금 10:00–13:00 알고리즘 외 1건"]')
    expect(algo.attributes('role')).toBe('listitem')
    expect(algo.attributes('style')).toContain('top: 48px')
    expect(algo.attributes('style')).toContain('height: 144px')
    expect(algo.classes()).toContain('wg__blk--busy')
    expect(w.get('[aria-label="화 09:00–10:00 운영체제"]').classes()).toContain('wg__blk--off')
    const mine = w.get('[aria-label="금 15:00–16:00 캡스톤 스터디 대기중"]')
    expect(mine.classes()).toEqual(expect.arrayContaining(['wg__blk--mine', 'wg__blk--requested']))
    expect(w.findAll('.wg__col')[4].attributes('aria-label')).toBe('금요일')
  })

  it('좁은 폭(24)은 과목명만, 넓은 폭(32)은 유형 + 과목명 + 시각', async () => {
    const w = mount(WeekGrid, { props })
    const algo = () => w.get('[aria-label="금 10:00–13:00 알고리즘 외 1건"]')
    expect(algo().text()).toBe('알고리즘 외 1건')
    await w.setProps({ rowHeight: 32 })
    expect(w.classes()).toContain('wg--wide')
    expect(algo().get('.wg__type').text()).toBe('수업중')
    expect(algo().get('.wg__extra').text()).toBe('10:00–13:00')
  })

  it('오늘이 이 주에 없으면(todayIndex -1) 오늘 표시·지금 선이 없다', () => {
    const w = mount(WeekGrid, { props: { ...props, todayIndex: -1 } })
    expect(w.find('.wg__day--today').exists()).toBe(false)
    expect(w.find('.wg__now').exists()).toBe(false)
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/components/student/__tests__/weekGrid.spec.ts`
Expected: FAIL — `Failed to resolve import "../WeekGrid.vue"`

- [ ] **Step 3: 구현**

`web/src/components/student/WeekGrid.vue`
```vue
<script setup lang="ts">
import { computed } from 'vue'
import { BUSY_TYPES, DAYS, TYPE_LABEL } from '@/components/domain/rules'
import { ROW_MIN, gridRows, type GridBlock, type GridRange } from './grid'
import { minToHm } from './rules'

// 관리자 페이지2와 형태가 같고 규칙이 하나 다르다 — 겹친 블록을 서버가 합쳐 준다 (student-room.md 화면 3)
const props = withDefaults(
  defineProps<{
    days: number[]
    blocks: GridBlock[]
    rowHeight: 24 | 32
    range: GridRange
    todayIndex?: number
    nowTop?: number | null
  }>(),
  { todayIndex: -1, nowTop: null },
)

const wide = computed(() => props.rowHeight === 32)
const height = computed(() => `${gridRows(props.range) * props.rowHeight}px`)
/** 정시마다 시각 라벨 — 30분 행 두 개에 하나 */
const hours = computed(() => {
  const out: { label: string; top: number }[] = []
  for (let m = Math.ceil(props.range.start / 60) * 60; m < props.range.end; m += 60)
    out.push({ label: minToHm(m), top: ((m - props.range.start) / ROW_MIN) * props.rowHeight })
  return out
})
const byDay = computed(() => props.days.map((d) => props.blocks.filter((b) => b.day === d)))
/** 사용중 넷은 한 색(room.busy), 휴강은 점선 + 취소선, 나머지는 테두리만 */
const kind = (b: GridBlock) =>
  BUSY_TYPES.includes(b.type) ? 'busy' : b.type === 3 ? 'off' : 'plain'
const name = (d: number, b: GridBlock) =>
  `${DAYS[d - 1]} ${b.extra} ${b.label}${b.requested ? ' 대기중' : ''}`
</script>

<template>
  <div class="wg" :class="{ 'wg--wide': wide }" :style="{ '--wg-row': `${rowHeight}px` }">
    <div
      class="wg__grid"
      :style="{
        gridTemplateColumns: `var(--wg-time) repeat(${days.length}, minmax(var(--wg-col), 1fr))`,
      }"
    >
      <span class="wg__corner" aria-hidden="true" />
      <span
        v-for="(d, i) in days"
        :key="`h${d}`"
        class="wg__day"
        :class="{ 'wg__day--today': i === todayIndex }"
        >{{ DAYS[d - 1] }}</span
      >
      <div class="wg__times" :style="{ height }" aria-hidden="true">
        <span
          v-for="h in hours"
          :key="h.label"
          class="wg__time num"
          :style="{ top: `${h.top}px` }"
          >{{ h.label }}</span
        >
      </div>
      <div
        v-for="(d, i) in days"
        :key="`c${d}`"
        class="wg__col"
        :class="{ 'wg__col--today': i === todayIndex }"
        :style="{ height }"
        role="list"
        :aria-label="`${DAYS[d - 1]}요일`"
      >
        <div
          v-for="b in byDay[i]"
          :key="`${b.day}-${b.top}`"
          role="listitem"
          class="wg__blk"
          :class="[
            `wg__blk--${kind(b)}`,
            { 'wg__blk--mine': b.mine, 'wg__blk--requested': b.requested },
          ]"
          :style="{ top: `${b.top}px`, height: `${b.height}px` }"
          :aria-label="name(d, b)"
        >
          <span v-if="wide" class="wg__type">{{ TYPE_LABEL[b.type] }}</span>
          <span class="wg__label">{{ b.label }}</span>
          <span v-if="wide" class="wg__extra num">{{ b.extra }}</span>
        </div>
        <div
          v-if="i === todayIndex && nowTop !== null"
          class="wg__now"
          :style="{ top: `${nowTop}px` }"
          aria-hidden="true"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 눈금만 폭에 따라 줄인다 — 390: 30분 24px · 시각 34px · 하루 64px / 넓은 폭: 32 · 40 · 120 이상 */
.wg {
  --wg-time: 34px;
  --wg-col: 64px;
  overflow-x: auto;
}
.wg--wide {
  --wg-time: 40px;
  --wg-col: 120px;
}
.wg__grid {
  display: grid;
}
.wg__corner {
  border-bottom: var(--border-thin) solid var(--line-2);
}
.wg__day {
  padding: var(--space-1) 0;
  border-bottom: var(--border-thin) solid var(--line-2);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
  text-align: center;
  color: var(--text-2);
}
/* 오늘 — brand 머리 + brand.tint 바탕. 적색은 쓰지 않는다('사용중' 전용) */
.wg__day--today {
  color: var(--brand);
  background: var(--brand-tint);
}
.wg__times {
  position: relative;
}
.wg__time {
  position: absolute;
  right: var(--space-1);
  font-size: var(--font-size-xs);
  line-height: 1;
  color: var(--text-3);
}
.wg__col {
  position: relative;
  border-left: var(--border-thin) solid var(--line-1);
  background-image: repeating-linear-gradient(
    to bottom,
    transparent 0,
    transparent calc(var(--wg-row) - 1px),
    var(--line-1) calc(var(--wg-row) - 1px),
    var(--line-1) var(--wg-row)
  );
}
.wg__col--today {
  background-color: var(--brand-tint);
}
.wg__blk {
  position: absolute;
  left: 2px;
  right: 2px;
  display: flex;
  flex-direction: column;
  padding: 2px var(--space-1);
  overflow: hidden;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-sm);
  background: var(--surface);
  font-size: var(--font-size-xs);
  line-height: var(--leading-tight);
}
.wg__blk--busy {
  background: var(--room-busy-fill);
  border-color: var(--room-busy-line);
  color: var(--room-busy-label);
}
.wg__blk--off {
  border-style: dashed;
  border-color: var(--room-free-line);
  color: var(--room-free-text);
  text-decoration: line-through;
}
/* 내가 잡은 것 — brand 1px, 신청(대기)은 점선 */
.wg__blk--mine {
  outline: var(--border-thin) solid var(--brand);
  outline-offset: -1px;
}
.wg__blk--requested {
  outline-style: dashed;
}
.wg__label {
  font-weight: var(--font-weight-bold);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}
.wg__type,
.wg__extra {
  font-size: var(--font-size-xs);
}
.wg__now {
  position: absolute;
  left: 0;
  right: 0;
  height: var(--border-thick);
  background: var(--brand);
}
</style>
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test src/components && pnpm typecheck && pnpm lint`
Expected: PASS — weekGrid.spec 4 tests, 토큰 가드 통과.

- [ ] **Step 5: 커밋**

```bash
git add web/src/components/student/WeekGrid.vue web/src/components/student/__tests__/weekGrid.spec.ts
git commit -m "feat(web): 학생 주간 격자 — 서버가 합친 블록, 오늘 열·지금 선은 brand, 휴강 점선, 내 신청 점선 테두리"
```

---

### Task 7: ReserveSheet

**Files:**
- Create: `web/src/components/student/ReserveSheet.vue`
- Test: `web/src/components/student/__tests__/reserveSheet.spec.ts`

**Interfaces:**
- Consumes: `FreeDay`·`FreeRange`·`StudentResvIn`(Task 1), rules(Task 2: `MAX_ACTIVE`·`FULL_TEXT`·`CAP_TEXT`·`DAILY_TEXT`·`DOOR_HINT`·`chipDay`·`dateLabel`·`defaultEnd`·`durationText`·`endOptions`·`hmToMin`·`minToHm`·`spanKey`·`startOptions`), `SUBJ_MAX`(F2), `kstDateStr`·`kstMinutes`, ui `Button`·`Input`·`Select`.
- Produces: `ReserveSheet` props `{ days: FreeDay[]; now: Date; myFutureCount: number; full?: boolean; locked?: boolean; submitting?: boolean; maxBytes?: number (SUBJ_MAX) }`, emits `submit: [body: StudentResvIn]`. DOM: `form.rs` · 칩 `button.rs__chip[role=radio]`(8개, `aria-label="10월 24일 토"`, 첫 칩 `오늘`) · 구간 `label.rs__span > input[type=radio]`(이름 `13:00 – 15:00 2시간`) · Select `시작`·`끝` · Input `무엇에 쓰나요` · `.rs__blocker[role=status]` · `.rs__summary` · 제출 `예약하기`.
- 규칙: 날짜는 서버 `free` 8일 그대로(칩 = 창), 구간은 서버 `free` 만, 오늘은 `now` 이후 시작만, 재조회(`days` 교체)로 고른 구간이 사라지면 선택이 풀린다(고른 날은 유지), 막는 이유 우선순위 `full` → 3건 → 하루 상한.

- [ ] **Step 1: 실패 테스트**

`web/src/components/student/__tests__/reserveSheet.spec.ts`
```ts
import { describe, expect, it } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import type { FreeDay } from '@/api/types'
import ReserveSheet from '../ReserveSheet.vue'
import { CAP_TEXT, DAILY_TEXT, FULL_TEXT } from '../rules'

const NOW = new Date('2026-10-23T01:42:00Z') // KST 금 10:42
const all = [{ from: '09:00', to: '21:00' }]
// 오늘의 10:40 구간은 서버가 준 뒤 시간이 흘러 지난 것 — 화면이 지운다
const DAYS: FreeDay[] = [
  {
    date: '2026-10-23',
    spans: [
      { from: '10:40', to: '11:30' },
      { from: '16:00', to: '21:00' },
    ],
  },
  { date: '2026-10-24', spans: [] },
  { date: '2026-10-25', spans: all },
  { date: '2026-10-26', spans: all },
  { date: '2026-10-27', spans: all },
  { date: '2026-10-28', spans: all },
  { date: '2026-10-29', spans: all },
  { date: '2026-10-30', spans: all },
]
const base = { days: DAYS, now: NOW, myFutureCount: 0 }
type W = VueWrapper
const opts = (w: W, i: number) => w.findAll('select')[i].findAll('option').map((o) => o.text())
const value = (w: W, i: number) => (w.findAll('select')[i].element as HTMLSelectElement).value
const submitBtn = (w: W) => w.get<HTMLButtonElement>('button[type="submit"]')

describe('ReserveSheet — 제약은 고를 수 없게 건다 (student-room.md §화면이 거는 제약)', () => {
  it('칩 8개 = 창, 첫 칩은 오늘, 빈 구간이 있는 첫 날이 골라져 있다', () => {
    const w = mount(ReserveSheet, { props: base })
    const chips = w.findAll('button.rs__chip')
    expect(chips).toHaveLength(8)
    expect(chips[0].text()).toContain('오늘')
    expect(chips[0].attributes('aria-checked')).toBe('true')
    expect(chips[1].attributes('aria-label')).toBe('10월 24일 토')
    expect(w.get('legend').text()).toContain('10월 23일 금')
  })

  it('구간을 고르면 시작은 5분 단위(오늘은 지금 이후만), 끝은 +15~+120·구간 끝까지, 기본 +60', async () => {
    const w = mount(ReserveSheet, { props: base })
    expect(w.findAll('label.rs__span .num').map((l) => l.text())).toEqual([
      '10:40 – 11:30',
      '16:00 – 21:00',
    ])
    expect(w.findAll('label.rs__span .rs__dur').map((l) => l.text())).toEqual(['50분', '5시간'])
    await w.findAll('input[type="radio"]')[0].setValue()
    expect(opts(w, 0)).toEqual(['10:45', '10:50', '10:55', '11:00', '11:05', '11:10', '11:15'])
    expect(opts(w, 1)).toEqual(['11:00', '11:05', '11:10', '11:15', '11:20', '11:25', '11:30'])
    expect(value(w, 0)).toBe(String(10 * 60 + 45))
    expect(value(w, 1)).toBe(String(11 * 60 + 30))
  })

  it('시작을 바꾸면 끝이 범위 밖일 때만 다시 잡는다', async () => {
    const w = mount(ReserveSheet, { props: base })
    await w.findAll('input[type="radio"]')[1].setValue()
    expect(value(w, 1)).toBe(String(17 * 60))
    await w.findAll('select')[0].setValue(String(16 * 60 + 30))
    expect(value(w, 1)).toBe(String(17 * 60))
    await w.findAll('select')[0].setValue(String(18 * 60))
    expect(value(w, 1)).toBe(String(19 * 60))
  })

  it('제출 — 서버 모양 그대로 한 번, 목적이 공백이면 못 보낸다', async () => {
    const w = mount(ReserveSheet, { props: base })
    await w.findAll('input[type="radio"]')[1].setValue()
    await w.get('.field__control').setValue('   ')
    expect(submitBtn(w).element.disabled).toBe(true)
    await w.get('.field__control').setValue('캡스톤 스터디')
    expect(submitBtn(w).element.disabled).toBe(false)
    expect(w.get('.rs__summary').text()).toBe('10월 23일 금 16:00–17:00')
    await w.get('form').trigger('submit')
    expect(w.emitted('submit')).toEqual([
      [{ date: '2026-10-23', s_h: 16, s_m: 0, e_h: 17, e_m: 0, subject: '캡스톤 스터디' }],
    ])
  })

  it('막는 이유 — 가득·3건·하루 상한, 버튼은 disabled (다 골라도)', async () => {
    const filled = async (props: Partial<{ myFutureCount: number; locked: boolean }>) => {
      const w = mount(ReserveSheet, { props: { ...base, ...props } })
      await w.findAll('input[type="radio"]')[1].setValue()
      await w.get('.field__control').setValue('스터디')
      return w
    }
    const cap = await filled({ myFutureCount: 3 })
    expect(cap.get('.rs__blocker').text()).toBe(CAP_TEXT)
    expect(submitBtn(cap).element.disabled).toBe(true)
    await cap.get('form').trigger('submit')
    expect(cap.emitted('submit')).toBeUndefined()
    const daily = await filled({ locked: true })
    expect(daily.get('.rs__blocker').text()).toBe(DAILY_TEXT)
    const full = mount(ReserveSheet, {
      props: { ...base, full: true, days: DAYS.map((d) => ({ ...d, spans: [] })) },
    })
    expect(full.get('.rs__blocker').text()).toBe(FULL_TEXT)
    expect(full.get('.rs__empty').text()).toBe(FULL_TEXT)
    expect(mount(ReserveSheet, { props: base }).find('.rs__blocker').exists()).toBe(false)
  })

  it('다른 날 칩 — 그 날의 구간, 빈 날은 문장', async () => {
    const w = mount(ReserveSheet, { props: base })
    await w.findAll('button.rs__chip')[1].trigger('click')
    expect(w.findAll('button.rs__chip')[1].attributes('aria-checked')).toBe('true')
    expect(w.get('.rs__empty').text()).toBe('이 날은 비어 있는 시간이 없어요')
    await w.findAll('button.rs__chip')[2].trigger('click')
    await w.findAll('input[type="radio"]')[0].setValue()
    expect(opts(w, 0)[0]).toBe('09:00')
  })

  it('재조회로 고른 구간이 사라지면 선택이 풀리고, 고른 날·입력은 그대로', async () => {
    const w = mount(ReserveSheet, { props: base })
    await w.findAll('button.rs__chip')[2].trigger('click')
    await w.findAll('input[type="radio"]')[0].setValue()
    await w.get('.field__control').setValue('스터디')
    expect(submitBtn(w).element.disabled).toBe(false)
    const next = DAYS.map((d) =>
      d.date === '2026-10-25' ? { ...d, spans: [{ from: '12:00', to: '21:00' }] } : d,
    )
    await w.setProps({ days: next })
    expect(w.findAll('button.rs__chip')[2].attributes('aria-checked')).toBe('true')
    expect(
      w.findAll('input[type="radio"]').some((r) => (r.element as HTMLInputElement).checked),
    ).toBe(false)
    expect(w.findAll('select')).toHaveLength(0)
    expect(submitBtn(w).element.disabled).toBe(true)
    expect((w.get('.field__control').element as HTMLInputElement).value).toBe('스터디')
  })

  it('submitting 이면 loading — 다시 누를 수 없다', async () => {
    const w = mount(ReserveSheet, { props: base })
    await w.findAll('input[type="radio"]')[1].setValue()
    await w.get('.field__control').setValue('스터디')
    await w.setProps({ submitting: true })
    expect(submitBtn(w).attributes('aria-busy')).toBe('true')
    await w.get('form').trigger('submit')
    expect(w.emitted('submit')).toBeUndefined()
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/components/student/__tests__/reserveSheet.spec.ts`
Expected: FAIL — `Failed to resolve import "../ReserveSheet.vue"`

- [ ] **Step 3: 구현**

`web/src/components/student/ReserveSheet.vue`
```vue
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { FreeDay, FreeRange, StudentResvIn } from '@/api/types'
import { SUBJ_MAX } from '@/components/domain/rules'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'
import { kstDateStr, kstMinutes } from '@/lib/time'
import {
  CAP_TEXT,
  DAILY_TEXT,
  DOOR_HINT,
  FULL_TEXT,
  MAX_ACTIVE,
  chipDay,
  dateLabel,
  defaultEnd,
  durationText,
  endOptions,
  hmToMin,
  minToHm,
  spanKey,
  startOptions,
} from './rules'

// 예약 신청 화면 전체 — 제약을 "고를 수 없게" 건다. 빈 구간은 서버 free 만 (student-room.md §예약)
const props = withDefaults(
  defineProps<{
    days: FreeDay[]
    now: Date
    myFutureCount: number
    full?: boolean
    locked?: boolean
    submitting?: boolean
    maxBytes?: number
  }>(),
  { full: false, locked: false, submitting: false, maxBytes: SUBJ_MAX },
)
const emit = defineEmits<{ submit: [body: StudentResvIn] }>()

const date = ref<string | null>(null)
const spanId = ref<string | null>(null)
const start = ref<number | null>(null)
const end = ref<number | null>(null)
const subject = ref('')

// 처음엔 빈 구간이 있는 첫 날. 재조회로 days 가 바뀌어도 고른 날은 그대로 둔다
watch(
  () => props.days,
  (days) => {
    if (!days.some((d) => d.date === date.value))
      date.value = (days.find((d) => d.spans.length) ?? days[0])?.date ?? null
  },
  { immediate: true },
)

const day = computed(() => props.days.find((d) => d.date === date.value) ?? null)
/** 재조회로 사라진 구간이면 null — 선택이 풀리고 버튼이 잠긴다 */
const span = computed(() => day.value?.spans.find((s) => spanKey(s) === spanId.value) ?? null)
/** 오늘이면 지금 이후만 — 서버가 준 뒤 흐른 시간만큼 지운다 */
const after = computed(() =>
  day.value?.date === kstDateStr(props.now) ? kstMinutes(props.now) : null,
)
const starts = computed(() => (span.value ? startOptions(span.value, after.value) : []))
const ends = computed(() =>
  span.value && start.value !== null ? endOptions(start.value, span.value) : [],
)

function pickDay(d: string) {
  date.value = d
  spanId.value = null
  start.value = null
  end.value = null
}
function pickSpan(s: FreeRange) {
  spanId.value = spanKey(s)
  const first = startOptions(s, after.value)[0] ?? null
  start.value = first
  end.value = first === null ? null : defaultEnd(first, s)
}
function pickStart(v: string | number) {
  start.value = Number(v)
  if (span.value && !endOptions(start.value, span.value).includes(end.value ?? -1))
    end.value = defaultEnd(start.value, span.value)
}
function pickEnd(v: string | number) {
  end.value = Number(v)
}
// 시간이 흘러 고른 시작이 지나면 다음 후보로 (없으면 비운다)
watch(starts, (list) => {
  if (start.value === null || list.includes(start.value)) return
  if (list.length) pickStart(list[0])
  else {
    start.value = null
    end.value = null
  }
})

const blocker = computed(() => {
  if (props.full) return FULL_TEXT
  if (props.myFutureCount >= MAX_ACTIVE) return CAP_TEXT
  return props.locked ? DAILY_TEXT : null
})
const valid = computed(
  () =>
    start.value !== null &&
    starts.value.includes(start.value) &&
    end.value !== null &&
    ends.value.includes(end.value) &&
    subject.value.trim() !== '',
)
const summary = computed(() =>
  day.value && valid.value
    ? `${dateLabel(day.value.date)} ${minToHm(start.value!)}–${minToHm(end.value!)}`
    : '시간을 고르세요',
)
const startOpts = computed(() => starts.value.map((m) => ({ value: m, label: minToHm(m) })))
const endOpts = computed(() => ends.value.map((m) => ({ value: m, label: minToHm(m) })))

function submit() {
  if (!valid.value || blocker.value || props.submitting || !day.value) return
  const s = start.value!
  const e = end.value!
  emit('submit', {
    date: day.value.date,
    s_h: Math.floor(s / 60),
    s_m: s % 60,
    e_h: Math.floor(e / 60),
    e_m: e % 60,
    subject: subject.value.trim(),
  })
}
</script>

<template>
  <form class="rs" @submit.prevent="submit">
    <section class="rs__sec">
      <h2 class="rs__h">날짜 <span class="rs__sub">· 오늘부터 7일까지</span></h2>
      <div class="rs__chips" role="radiogroup" aria-label="날짜">
        <button
          v-for="(d, i) in days"
          :key="d.date"
          type="button"
          role="radio"
          class="rs__chip"
          :class="{ 'rs__chip--on': d.date === date }"
          :aria-checked="d.date === date"
          :aria-label="dateLabel(d.date)"
          @click="pickDay(d.date)"
        >
          <span>{{ i === 0 ? '오늘' : chipDay(d.date) }}</span>
          <span class="rs__chip-num num">{{ Number(d.date.slice(8, 10)) }}</span>
        </button>
      </div>
    </section>

    <fieldset v-if="day" class="rs__sec rs__spans">
      <legend class="rs__h">
        비어 있는 시간 <span class="rs__sub">· {{ dateLabel(day.date) }}</span>
      </legend>
      <p v-if="!day.spans.length" class="rs__empty">
        {{ full ? FULL_TEXT : '이 날은 비어 있는 시간이 없어요' }}
      </p>
      <label
        v-for="s in day.spans"
        :key="spanKey(s)"
        class="rs__span"
        :class="{ 'rs__span--on': spanKey(s) === spanId }"
      >
        <input
          type="radio"
          name="span"
          :value="spanKey(s)"
          :checked="spanKey(s) === spanId"
          @change="pickSpan(s)"
        />
        <span class="num">{{ s.from }} – {{ s.to }}</span>
        <span class="rs__dur">{{ durationText(hmToMin(s.to) - hmToMin(s.from)) }}</span>
      </label>
    </fieldset>

    <div v-if="span" class="rs__sec rs__time">
      <Select
        label="시작"
        :model-value="start ?? undefined"
        :options="startOpts"
        @update:model-value="pickStart"
      />
      <Select
        label="끝"
        :model-value="end ?? undefined"
        :options="endOpts"
        @update:model-value="pickEnd"
      />
    </div>

    <div class="rs__sec">
      <Input
        v-model="subject"
        label="무엇에 쓰나요"
        required
        :max-bytes="maxBytes"
        :hint="DOOR_HINT"
      />
      <p class="rs__note">예약하면 관리자 승인 뒤 확정돼요</p>
    </div>

    <footer class="rs__bar">
      <p v-if="blocker" class="rs__blocker" role="status">{{ blocker }}</p>
      <div class="rs__bar-row">
        <p class="rs__summary num">{{ summary }}</p>
        <Button type="submit" :disabled="!valid || !!blocker" :loading="submitting">예약하기</Button>
      </div>
    </footer>
  </form>
</template>

<style scoped>
.rs {
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 58px);
}
.rs__sec {
  min-width: 0;
  margin: 0;
  padding: var(--space-4) var(--space-4) 0;
  border: 0;
}
.rs__h {
  margin: 0 0 var(--space-2);
  padding: 0;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-bold);
}
.rs__sub {
  font-weight: var(--font-weight-regular);
  color: var(--text-3);
}
.rs__chips {
  display: flex;
  gap: var(--space-2);
  overflow-x: auto;
}
.rs__chip {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-width: 52px;
  height: 52px;
  border: var(--border-thin) solid var(--line-3);
  border-radius: var(--radius-md);
  background: var(--surface);
  color: var(--text-1);
  font: inherit;
  font-size: var(--font-size-sm);
  line-height: var(--leading-tight);
  cursor: pointer;
}
.rs__chip--on {
  border-color: var(--brand);
  background: var(--brand-tint);
  color: var(--brand);
  font-weight: var(--font-weight-bold);
}
.rs__chip-num {
  font-size: var(--font-size-xs);
}
.rs__spans {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.rs__span {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: 52px;
  padding: 0 var(--space-3);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-md);
  background: var(--surface);
  cursor: pointer;
}
.rs__span input {
  accent-color: var(--brand);
}
.rs__span--on {
  border-color: var(--brand);
  background: var(--brand-tint);
}
.rs__dur {
  margin-left: auto;
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
.rs__empty {
  margin: 0;
  color: var(--text-3);
}
.rs__time {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
}
.rs__note {
  margin: var(--space-2) 0 0;
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.rs__bar {
  position: sticky;
  bottom: 0;
  margin-top: auto;
  padding: var(--space-3) var(--space-4);
  border-top: var(--border-thin) solid var(--line-2);
  background: var(--surface);
}
.rs__blocker {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
  color: var(--text-1);
}
.rs__bar-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.rs__summary {
  flex: 1;
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
</style>
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test src/components && pnpm typecheck && pnpm lint`
Expected: PASS — reserveSheet.spec 8 tests.

- [ ] **Step 5: 커밋**

```bash
git add web/src/components/student/ReserveSheet.vue web/src/components/student/__tests__/reserveSheet.spec.ts
git commit -m "feat(web): 예약 신청 시트 — 서버 free 구간만, 5분·15~120분·지난 시각을 고를 수 없게, 막는 이유 한 줄"
```

---

### Task 8: MyResvCard

**Files:**
- Create: `web/src/components/student/MyResvCard.vue`
- Test: `web/src/components/student/__tests__/myResvCard.spec.ts`

**Interfaces:**
- Consumes: `ResvMineOut`(Task 1), `checkinState`·`cancelKind`·`resvWhen`(Task 2), `ResvStatusBadge`(Task 5), ui `Button`.
- Produces: `MyResvCard` props `{ resv: ResvMineOut; now: Date; busy?: 'checkin' | 'cancel' | null }`, emits `checkin: []` · `cancel: []`. DOM: `article.mc`(`aria-label="공학관 401호 10/24 토 10:00–12:00"`) · `.mc__note`(사유·만료) · `.mc__done`(`✓ 10:52 체크인`) · `.mc__hint`(`10:50부터 체크인할 수 있어요` / `체크인 시간이 지났어요`) · 버튼 `체크인`(창 안이면 primary) · `신청 취소`/`취소`(secondary).

- [ ] **Step 1: 실패 테스트**

`web/src/components/student/__tests__/myResvCard.spec.ts`
```ts
import { describe, expect, it } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import type { ResvMineOut } from '@/api/types'
import MyResvCard from '../MyResvCard.vue'

const NOW = new Date('2026-10-23T01:42:00Z') // KST 금 10:42
const resv = (over: Partial<ResvMineOut> = {}): ResvMineOut => ({
  id: 7,
  date: '2026-10-23',
  s_h: 10,
  s_m: 50,
  e_h: 12,
  e_m: 0,
  type: 6,
  subject: '캡스톤 스터디',
  professor: '',
  status: 'approved',
  requested_at: null,
  decided_at: null,
  reject_reason: null,
  checked_in_at: null,
  cancelled_at: null,
  room_id: 11,
  building: '공학관',
  room: 401,
  ...over,
})
const buttons = (w: VueWrapper) => w.findAll('button').map((b) => b.text())

describe('MyResvCard', () => {
  it('승인 · 창 안 — 체크인(primary) + 취소, 읽는 이름에 방·시각', async () => {
    const w = mount(MyResvCard, { props: { resv: resv(), now: NOW } })
    expect(w.get('article').attributes('aria-label')).toBe('공학관 401호 10/23 금 10:50–12:00')
    expect(w.get('.badge').text()).toBe('승인됨')
    expect(buttons(w)).toEqual(['체크인', '취소'])
    expect(w.findAll('button')[0].classes()).toContain('btn--primary')
    await w.findAll('button')[0].trigger('click')
    await w.findAll('button')[1].trigger('click')
    expect(w.emitted('checkin')).toHaveLength(1)
    expect(w.emitted('cancel')).toHaveLength(1)
  })

  it('창 밖 — 숨기지 않고 disabled + 언제부터', () => {
    const w = mount(MyResvCard, { props: { resv: resv({ s_h: 11, s_m: 0 }), now: NOW } })
    const ci = w.findAll('button')[0]
    expect(ci.text()).toBe('체크인')
    expect((ci.element as HTMLButtonElement).disabled).toBe(true)
    expect(ci.classes()).toContain('btn--secondary')
    expect(w.get('.mc__hint').text()).toBe('10:50부터 체크인할 수 있어요')
  })

  it('체크인했으면 버튼 자리가 시각으로, 시작 뒤엔 취소가 없다', () => {
    const w = mount(MyResvCard, {
      props: {
        resv: resv({ s_h: 10, s_m: 30, checked_in_at: new Date('2026-10-23T01:32:00Z') }),
        now: NOW,
      },
    })
    expect(w.get('.mc__done').text()).toBe('✓ 10:32 체크인')
    expect(w.findAll('button')).toHaveLength(0)
  })

  it('대기중 — 신청 취소만, 체크인 없음', () => {
    const w = mount(MyResvCard, { props: { resv: resv({ status: 'requested' }), now: NOW } })
    expect(w.get('.badge').text()).toBe('대기중')
    expect(buttons(w)).toEqual(['신청 취소'])
  })

  it('거절됨 — 사유를 본문에, 만료됨 — 한 줄, 끝난 승인 — 버튼 없음', () => {
    const rej = mount(MyResvCard, {
      props: { resv: resv({ status: 'rejected', reject_reason: '학과 행사와 겹칩니다' }), now: NOW },
    })
    expect(rej.get('.mc__note').text()).toBe('사유: 학과 행사와 겹칩니다')
    expect(rej.findAll('button')).toHaveLength(0)
    const exp = mount(MyResvCard, { props: { resv: resv({ status: 'expired' }), now: NOW } })
    expect(exp.get('.mc__note').text()).toBe('승인 전에 시간이 지났어요')
    const past = mount(MyResvCard, {
      props: { resv: resv({ s_h: 9, s_m: 0, e_h: 10, e_m: 0 }), now: NOW },
    })
    expect(past.findAll('button')).toHaveLength(0)
    expect(past.find('.mc__hint').exists()).toBe(false)
  })

  it('처리 중(busy) — 두 버튼 다 잠기고 누른 쪽만 loading', () => {
    const w = mount(MyResvCard, { props: { resv: resv(), now: NOW, busy: 'cancel' } })
    const [ci, cancel] = w.findAll('button')
    expect((ci.element as HTMLButtonElement).disabled).toBe(true)
    expect(cancel.attributes('aria-busy')).toBe('true')
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/components/student/__tests__/myResvCard.spec.ts`
Expected: FAIL — `Failed to resolve import "../MyResvCard.vue"`

- [ ] **Step 3: 구현**

`web/src/components/student/MyResvCard.vue`
```vue
<script setup lang="ts">
import { computed } from 'vue'
import type { ResvMineOut } from '@/api/types'
import Button from '@/components/ui/Button.vue'
import ResvStatusBadge from './ResvStatusBadge.vue'
import { cancelKind, checkinState, resvWhen } from './rules'

// 체크인 창(시작 −10 ~ +15분)과 취소/철회 구분을 이 카드가 진다 (student-room.md §내 예약)
const props = withDefaults(
  defineProps<{ resv: ResvMineOut; now: Date; busy?: 'checkin' | 'cancel' | null }>(),
  { busy: null },
)
const emit = defineEmits<{ checkin: []; cancel: [] }>()
const ci = computed(() => checkinState(props.resv, props.now))
const cancel = computed(() => cancelKind(props.resv, props.now))
</script>

<template>
  <article
    class="mc"
    :class="`mc--${resv.status}`"
    :aria-label="`${resv.building} ${resv.room}호 ${resvWhen(resv)}`"
  >
    <p class="mc__head">
      <ResvStatusBadge :status="resv.status" />
      <span class="mc__room num">{{ resv.building }} {{ resv.room }}호</span>
    </p>
    <p class="mc__when num">{{ resvWhen(resv) }}</p>
    <p class="mc__subject">{{ resv.subject }}</p>
    <p v-if="resv.status === 'rejected' && resv.reject_reason" class="mc__note">
      사유: {{ resv.reject_reason }}
    </p>
    <p v-if="resv.status === 'expired'" class="mc__note">승인 전에 시간이 지났어요</p>
    <div v-if="ci || cancel" class="mc__actions">
      <p v-if="ci?.kind === 'done'" class="mc__done num">✓ {{ ci.at }} 체크인</p>
      <Button
        v-else-if="ci"
        :variant="ci.kind === 'open' ? 'primary' : 'secondary'"
        :disabled="ci.kind !== 'open' || busy !== null"
        :loading="busy === 'checkin'"
        @click="emit('checkin')"
        >체크인</Button
      >
      <Button
        v-if="cancel"
        variant="secondary"
        :disabled="busy !== null"
        :loading="busy === 'cancel'"
        @click="emit('cancel')"
        >{{ cancel === 'withdraw' ? '신청 취소' : '취소' }}</Button
      >
    </div>
    <!-- 창 밖이면 숨기지 않고 언제부터인지 — 버튼이 사라지면 기능이 있는지 모른다 -->
    <p v-if="ci?.kind === 'before'" class="mc__hint num">{{ ci.from }}부터 체크인할 수 있어요</p>
    <p v-else-if="ci?.kind === 'after'" class="mc__hint">체크인 시간이 지났어요</p>
  </article>
</template>

<style scoped>
.mc {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-4);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.mc p {
  margin: 0;
}
.mc__head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.mc__room {
  font-weight: var(--font-weight-bold);
}
.mc__subject,
.mc__note {
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.mc__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-2);
}
.mc__done {
  display: inline-flex;
  align-items: center;
  min-height: var(--control-height-md);
  font-weight: var(--font-weight-bold);
}
.mc__hint {
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
</style>
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test src/components && pnpm typecheck && pnpm lint`
Expected: PASS — myResvCard.spec 6 tests.

- [ ] **Step 5: 커밋**

```bash
git add web/src/components/student/MyResvCard.vue web/src/components/student/__tests__/myResvCard.spec.ts
git commit -m "feat(web): 내 예약 카드 — 체크인 창 밖은 disabled + 언제부터, 신청 취소와 취소를 가른다"
```

---

### Task 9: 셸 — 로그인 벽 · 404 · 소문자 글자 · 헤더 · 갱신 줄 + E2E

**Files:**
- Modify: `web/src/student/router.ts`, `web/src/student/StudentApp.vue`, `web/src/student/__tests__/router.spec.ts`
- Create: `web/src/student/LoginGate.vue`, `web/src/student/StudentHeader.vue`, `web/src/student/CtaLink.vue`, `web/src/student/RefreshedNote.vue`, `web/src/student/composables.ts`, `web/src/student/views/NotFoundView.vue`, `web/e2e/student.spec.ts`
- Test: `web/src/student/__tests__/gate.spec.ts`, `web/src/student/__tests__/refreshed.spec.ts`

**Interfaces:**
- Consumes: `installAuth`(F1 guard — 세션 중 401/403 → `/login?next=`), `session`·`setSession`·`clearSession`(F1), `useStale`(F3), `formatHm`·`formatKst`, ui `ToastHost`.
- Produces (`router.ts`): `routes` · `makeRouter(history?)` · `upperBld(to): string | true`. 화면 라우트는 `meta: { gate: true }`. 없는 주소는 `/:pathMatch(.*)*` → NotFoundView(벽 없음, `beforeEnter: upperBld`).
- Produces (`StudentApp.vue`): `route.meta.gate && !session` 이면 RouterView 대신 `LoginGate`(`bld` = `route.params.bld`, `next` = `route.fullPath`).
- Produces: `LoginGate` props `{ bld?: string; next: string }` · `StudentHeader` props `{ title: string; back?: string; backLabel?: string ('뒤로'); backText?: string ('‹'); hideBackWide?: boolean; showMe?: boolean }` + 기본 슬롯(오른쪽) — `header.sh` 58px, `h1.sh__title`, `a.sh__back[aria-label]`, `showMe` 면 `a.sh__me` `내 예약` · `CtaLink` props `{ to: RouteLocationRaw; compact?: boolean }` — brand 채움 링크 48px(compact 40px) · `RefreshedNote` props `{ at: Date | null; epaper?: boolean (true) }` — `p.rn[role=status]`, 5분 지나면 `.rn--stale` + ` · 갱신이 멈췄어요` · `NotFoundView` props `{ back?: string ('/'); backLabel?: string ('건물 목록으로') }` — `h2` `찾을 수 없는 주소예요`, `a.nf__link`.
- Produces (`composables.ts`): `POLL_MS = 60_000` · `WIDE_QUERY = '(min-width: 640px)'` · `useWide(): Ref<boolean>` · `useNow(ms = 15_000): Ref<Date>`.

- [ ] **Step 1: 실패 테스트**

`web/src/student/__tests__/router.spec.ts` — 파일 전체를 바꾼다
```ts
import { describe, expect, it } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import { makeRouter } from '@/student/router'

const at = async (path: string) => {
  const r = makeRouter(createMemoryHistory())
  await r.push(path)
  await r.isReady()
  return r.currentRoute.value
}

describe('student router', () => {
  it('/ 는 세션 없이도 그 자리 — 로그인 벽은 앱이 그린다(meta.gate)', async () => {
    const r = await at('/')
    expect(r.path).toBe('/')
    expect(r.meta.gate).toBe(true)
  })

  it('인증 화면은 벽 없이', async () => {
    expect((await at('/login')).meta.gate).toBeUndefined()
    expect((await at('/signup')).meta.gate).toBeUndefined()
  })

  it('모르는 주소는 404 화면 (벽 없이 — 보여줄 데이터가 없다)', async () => {
    const r = await at('/no/such/page')
    expect(r.matched[0].path).toBe('/:pathMatch(.*)*')
    expect(r.meta.gate).toBeUndefined()
  })

  it('소문자 건물 글자는 대문자로 — 폰에서 흔한 오타, 쿼리는 그대로', async () => {
    expect((await at('/e')).path).toBe('/E')
    expect((await at('/e/401?x=1')).fullPath).toBe('/E/401?x=1')
    expect((await at('/no')).path).toBe('/no')
  })
})
```

`web/src/student/__tests__/gate.spec.ts`
```ts
import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import StudentApp from '@/student/StudentApp.vue'
import { clearSession, setSession } from '@/lib/session'

const Page = { render: () => h('p', '강의실 화면') }
async function mountApp(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: Page, meta: { gate: true } },
      { path: '/:bld([A-Z])', component: Page, meta: { gate: true } },
      { path: '/open', component: Page },
      { path: '/login', component: { render: () => h('p', '로그인 폼') } },
    ],
  })
  await router.push(path)
  await router.isReady()
  const w = mount(StudentApp, { global: { plugins: [router] } })
  await flushPromises()
  return { w, router }
}
afterEach(() => clearSession())

describe('로그인 벽 (student-room.md §로그인 벽)', () => {
  it('세션이 없으면 그 주소 그대로 벽 — 건물 글자, 로그인 링크는 원래 주소를 안다', async () => {
    const { w, router } = await mountApp('/E')
    expect(router.currentRoute.value.path).toBe('/E')
    expect(w.get('h1').text()).toBe('E동의 빈 강의실을 확인하고 예약을 신청할 수 있어요.')
    expect(w.get('a.cta').attributes('href')).toBe('/login?next=/E')
    expect(w.get('a[href="/signup"]').text()).toBe('가입 신청')
    expect(w.text()).not.toContain('강의실 화면')
  })

  it('건물 글자가 없는 주소는 학교 문장', async () => {
    const { w } = await mountApp('/')
    expect(w.get('h1').text()).toBe('학교의 빈 강의실을 확인하고 예약을 신청할 수 있어요.')
    expect(w.get('a.cta').attributes('href')).toBe('/login?next=/')
  })

  it('세션이 있으면 화면 그대로, gate 가 아닌 화면은 벽 없이', async () => {
    setSession({ token: 't', role: 'student', school_id: 1, name: '김민준' })
    expect((await mountApp('/E')).w.text()).toContain('강의실 화면')
    clearSession()
    expect((await mountApp('/open')).w.text()).toContain('강의실 화면')
  })
})
```

`web/src/student/__tests__/refreshed.spec.ts`
```ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import RefreshedNote from '@/student/RefreshedNote.vue'

afterEach(() => vi.useRealTimers())

describe('RefreshedNote — 문 앞 e-Paper 와 같은 내용 · 갱신 시각', () => {
  it('갱신 시각과 e-Paper 문구, 5분이 지나면 danger + 문장 (색만으로 말하지 않는다)', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-23T01:42:00Z'))
    const w = mount(RefreshedNote, { props: { at: new Date('2026-10-23T01:41:00Z') } })
    expect(w.attributes('role')).toBe('status')
    expect(w.text()).toContain('문 앞 e-Paper 와 같은 내용')
    expect(w.text()).toContain('10:41 갱신')
    expect(w.classes()).not.toContain('rn--stale')
    vi.advanceTimersByTime(5 * 60_000)
    await nextTick()
    expect(w.classes()).toContain('rn--stale')
    expect(w.text()).toContain('갱신이 멈췄어요')
  })

  it('epaper=false 면 갱신 시각만 (/me), 아직 한 번도 못 받았으면 시각 없음', () => {
    const me = mount(RefreshedNote, {
      props: { at: new Date('2026-10-23T01:41:00Z'), epaper: false },
    })
    expect(me.text()).not.toContain('e-Paper')
    expect(me.text()).toContain('10:41 갱신')
    const none = mount(RefreshedNote, { props: { at: null } })
    expect(none.text()).not.toContain('갱신')
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/student`
Expected: FAIL — `Failed to resolve import "@/student/RefreshedNote.vue"`, gate.spec `h1` 없음(F1 StudentApp 은 벽이 없다), router.spec `/ 는 세션 없이도 그 자리` — `expected '/login' to be '/'`

- [ ] **Step 3: 구현**

`web/src/student/composables.ts`
```ts
import { onScopeDispose, ref } from 'vue'

/** 자동 새로고침 (student-room.md §상태) — 탭이 숨으면 usePolling 이 멈춘다 */
export const POLL_MS = 60_000
/** bp.tablet 이상 (tokens.md 640px) — 넓은 폭은 같은 라우트에서 더 보여준다 */
export const WIDE_QUERY = '(min-width: 640px)'

export function useWide() {
  const mq = window.matchMedia(WIDE_QUERY)
  const wide = ref(mq.matches)
  const on = (e: { matches: boolean }) => {
    wide.value = e.matches
  }
  mq.addEventListener('change', on)
  onScopeDispose(() => mq.removeEventListener('change', on))
  return wide
}

/** 화면 시계 — '지금' 행·체크인 창·지난 시작 시각. 네트워크 없이 흐른다 */
export function useNow(ms = 15_000) {
  const now = ref(new Date())
  const timer = setInterval(() => {
    now.value = new Date()
  }, ms)
  onScopeDispose(() => clearInterval(timer))
  return now
}
```

`web/src/student/StudentHeader.vue`
```vue
<script setup lang="ts">
import { RouterLink } from 'vue-router'

// 58px 상단 — ‹ 는 진짜 링크(뒤로가기와 결과가 같아야 한다, student-room.md 화면 2)
withDefaults(
  defineProps<{
    title: string
    back?: string
    backLabel?: string
    backText?: string
    hideBackWide?: boolean
    showMe?: boolean
  }>(),
  { backLabel: '뒤로', backText: '‹', hideBackWide: false, showMe: false },
)
</script>

<template>
  <header class="sh" :class="{ 'sh--nobackwide': hideBackWide }">
    <RouterLink v-if="back" :to="back" class="sh__back" :aria-label="backLabel">{{
      backText
    }}</RouterLink>
    <h1 class="sh__title">{{ title }}</h1>
    <div v-if="$slots.default || showMe" class="sh__right">
      <slot />
      <RouterLink v-if="showMe" to="/me" class="sh__me">내 예약</RouterLink>
    </div>
  </header>
</template>

<style scoped>
.sh {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  height: 58px;
  padding: 0 var(--space-2) 0 var(--space-4);
  border-bottom: var(--border-thin) solid var(--line-2);
  background: var(--surface);
}
.sh__back {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  margin-left: calc(-1 * var(--space-3));
  font-size: var(--font-size-xl);
  color: var(--text-1);
  text-decoration: none;
}
.sh__title {
  flex: 1;
  min-width: 0;
  margin: 0;
  overflow: hidden;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  white-space: nowrap;
  text-overflow: ellipsis;
}
.sh__right {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.sh__me {
  display: inline-flex;
  align-items: center;
  min-height: 48px;
  padding: 0 var(--space-2);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
  color: var(--text-1);
  white-space: nowrap;
}
@media (min-width: 640px) {
  .sh--nobackwide .sh__back {
    display: none;
  }
}
</style>
```

`web/src/student/CtaLink.vue`
```vue
<script setup lang="ts">
import { RouterLink, type RouteLocationRaw } from 'vue-router'

// 화면의 1차 동작 — brand 채움 링크 (이동이라 button 이 아니라 a). 모바일 48px, 넓은 폭 헤더 40px
withDefaults(defineProps<{ to: RouteLocationRaw; compact?: boolean }>(), { compact: false })
</script>

<template>
  <RouterLink :to="to" class="cta" :class="{ 'cta--compact': compact }"><slot /></RouterLink>
</template>

<style scoped>
.cta {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: var(--control-height-md);
  padding: 0 var(--space-4);
  border-radius: var(--radius-md);
  background: var(--brand);
  color: var(--on-brand);
  font-weight: var(--font-weight-bold);
  text-decoration: none;
  white-space: nowrap;
}
.cta--compact {
  min-height: 40px;
}
.cta:hover {
  filter: brightness(0.9);
}
</style>
```

`web/src/student/LoginGate.vue`
```vue
<script setup lang="ts">
import { RouterLink } from 'vue-router'
import CtaLink from './CtaLink.vue'

// 빈 로그인 폼 대신 — 무엇을 볼 수 있는지 한 문장과 어느 건물인지(주소의 글자)부터 (student-room.md §로그인 벽)
defineProps<{ bld?: string; next: string }>()
</script>

<template>
  <main class="gate">
    <p class="gate__brand">우송 ESC</p>
    <h1 class="gate__title">
      {{ bld ? `${bld}동` : '학교' }}의 빈 강의실을 확인하고 예약을 신청할 수 있어요.
    </h1>
    <p class="gate__text">학교 웹메일로 로그인하세요.</p>
    <CtaLink :to="{ path: '/login', query: { next } }">로그인</CtaLink>
    <p class="gate__text">
      처음이신가요? <RouterLink to="/signup" class="gate__link">가입 신청</RouterLink>
    </p>
  </main>
</template>

<style scoped>
.gate {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  max-width: 400px;
  min-height: 100vh;
  margin: 0 auto;
  padding: var(--space-7) var(--space-4);
  background: var(--surface);
}
.gate__brand {
  margin: 0;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
  color: var(--text-2);
}
.gate__title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  line-height: var(--leading-tight);
}
.gate__text {
  margin: 0;
  color: var(--text-2);
}
.gate__link {
  display: inline-flex;
  align-items: center;
  min-height: 48px;
  color: var(--brand);
  font-weight: var(--font-weight-bold);
}
</style>
```

`web/src/student/RefreshedNote.vue`
```vue
<script setup lang="ts">
import { formatHm, formatKst } from '@/lib/time'
import { useStale } from '@/lib/useStale'

// 오래된 값이라도 지우지 않는다 — 대신 이 줄이 오래됐다고 말한다 (student-room.md §상태)
const props = withDefaults(defineProps<{ at: Date | null; epaper?: boolean }>(), {
  epaper: true,
})
const { stale } = useStale(() => props.at)
</script>

<template>
  <p class="rn num" :class="{ 'rn--stale': stale }" role="status">
    <template v-if="epaper"><span aria-hidden="true">● </span>문 앞 e-Paper 와 같은 내용</template>
    <template v-if="at"
      >{{ epaper ? ' · ' : '' }}<span :title="formatKst(at)">{{ formatHm(at) }} 갱신</span></template
    >
    <template v-if="stale"> · 갱신이 멈췄어요</template>
  </p>
</template>

<style scoped>
.rn {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.rn--stale {
  color: var(--danger);
  font-weight: var(--font-weight-bold);
}
</style>
```

`web/src/student/views/NotFoundView.vue`
```vue
<script setup lang="ts">
import { RouterLink } from 'vue-router'
import StudentHeader from '../StudentHeader.vue'

// 주소를 잘못 친 경우가 흔하다 — 돌아갈 링크를 준다. 없는 방·예약을 안 받는 방·다른 학교 방이 모두 여기
withDefaults(defineProps<{ back?: string; backLabel?: string }>(), {
  back: '/',
  backLabel: '건물 목록으로',
})
</script>

<template>
  <div class="nf">
    <StudentHeader title="우송 ESC" />
    <main class="nf__body">
      <h2 class="nf__title">찾을 수 없는 주소예요</h2>
      <p class="nf__text">주소를 잘못 입력했거나, 예약을 받지 않는 강의실이에요.</p>
      <RouterLink :to="back" class="nf__link">{{ backLabel }}</RouterLink>
    </main>
  </div>
</template>

<style scoped>
.nf__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-6) var(--space-4);
}
.nf__title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
}
.nf__text {
  margin: 0;
  color: var(--text-2);
}
.nf__link {
  display: inline-flex;
  align-items: center;
  min-height: 48px;
  color: var(--brand);
  font-weight: var(--font-weight-bold);
}
</style>
```

`web/src/student/StudentApp.vue` — 파일 전체를 바꾼다
```vue
<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import ToastHost from '@/components/ui/ToastHost.vue'
import { session } from '@/lib/session'
import LoginGate from './LoginGate.vue'

const route = useRoute()
// 조회도 로그인이 필요하다(S10 §3). 리다이렉트 없이 그 주소에서 벽을 그린다 — 주소가 곧 상태
const gated = computed(() => route.meta.gate === true && !session.value)
const gateBld = computed(() =>
  typeof route.params.bld === 'string' ? route.params.bld : undefined,
)
</script>

<template>
  <LoginGate v-if="gated" :bld="gateBld" :next="route.fullPath" />
  <RouterView v-else />
  <ToastHost />
</template>
```

`web/src/student/router.ts` — 파일 전체를 바꾼다
```ts
import {
  createRouter,
  createWebHistory,
  type RouteLocationNormalized,
  type RouteRecordRaw,
  type RouterHistory,
} from 'vue-router'
import { installAuth } from '@/auth/guard'

/** '/e/401' → '/E/401' — 폰에서 소문자로 치는 일이 흔하다 */
export function upperBld(to: RouteLocationNormalized): string | true {
  return /^\/[a-z](\/|$)/.test(to.path)
    ? to.fullPath.replace(/^\/[a-z]/, (c) => c.toUpperCase())
    : true
}

// 학생 화면은 전부 로그인 필요(S10 §3) — meta.gate 면 StudentApp 이 그 주소 그대로 로그인 벽을 그린다.
// 세션 중 401 은 installAuth(F1)가 /login?next= 로 보낸다.
export const routes: RouteRecordRaw[] = [
  { path: '/', component: () => import('./views/HomeView.vue'), meta: { gate: true } },
  { path: '/login', component: () => import('@/auth/LoginView.vue'), props: { app: 'student' } },
  { path: '/signup', component: () => import('@/auth/SignupView.vue') },
  { path: '/verify', component: () => import('@/auth/VerifyView.vue') },
  { path: '/forgot', component: () => import('@/auth/ForgotView.vue') },
  { path: '/reset', component: () => import('@/auth/ResetView.vue') },
  // 없는 주소 — 벽 없이 404 (보여줄 데이터가 없다)
  {
    path: '/:pathMatch(.*)*',
    component: () => import('./views/NotFoundView.vue'),
    beforeEnter: upperBld,
  },
]

export function makeRouter(history: RouterHistory = createWebHistory('/')) {
  const router = createRouter({ history, routes })
  installAuth(router)
  return router
}
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`
Expected: PASS — router.spec 4 · gate.spec 3 · refreshed.spec 2, 토큰 가드 통과(새 `.vue` 6개).

- [ ] **Step 5: E2E — 벽 · 404**

`web/e2e/student.spec.ts`
```ts
import { expect, test, type BrowserContext, type Page } from '@playwright/test'
import { SIZES, WEB_URL, shot } from './helpers'

// 한 파일 = 한 컨텍스트 · 학생 UI 로그인 한 번 — 서버의 IP 당 분당 로그인 30회 상한 (F1 plan Task 13 메모).
// 로그인 뒤 이동은 링크 클릭으로 (page.goto 는 새로고침 = 메모리 세션 소실)
test.describe.configure({ mode: 'serial' })
let ctx: BrowserContext
let page: Page

test.beforeAll(async ({ browser }) => {
  ctx = await browser.newContext({ baseURL: WEB_URL, locale: 'ko-KR', viewport: SIZES.student })
  page = await ctx.newPage()
})
test.afterAll(async () => {
  await ctx.close()
})

test('로그인 벽 — 빈 폼 대신 무엇을 볼 수 있는지, 로그인은 돌아올 주소를 안다', async () => {
  await page.goto('/')
  await expect(
    page.getByRole('heading', {
      level: 1,
      name: '학교의 빈 강의실을 확인하고 예약을 신청할 수 있어요.',
    }),
  ).toBeVisible()
  const login = page.getByRole('link', { name: '로그인' })
  await expect(login).toHaveAttribute('href', '/login?next=/')
  expect((await login.boundingBox())!.height).toBeGreaterThanOrEqual(48)
  await expect(page.getByRole('link', { name: '가입 신청' })).toHaveAttribute('href', '/signup')
  await shot(page, 'student-gate-390')
})

test('없는 주소 — 벽 없이 404 + 건물 목록으로', async () => {
  await page.goto('/no/such/page')
  await expect(page.getByRole('heading', { name: '찾을 수 없는 주소예요' })).toBeVisible()
  await expect(page.getByRole('link', { name: '건물 목록으로' })).toHaveAttribute('href', '/')
  expect((await page.locator('header.sh').boundingBox())!.height).toBe(58)
  await shot(page, 'student-notfound-390')
})
```

Run: E2E 명령(Global Constraints) 끝에 ` e2e/student.spec.ts`
Expected: 2 passed. `web/e2e/.shots/student-gate-390.png`·`student-notfound-390.png` 를 `student-room.md` §로그인 벽 시안과 대조 — 브랜드 한 줄 → 20px bold 문장 → 안내 → 48px `brand` 로그인 → `처음이신가요? 가입 신청`, 바탕 `surface`.

- [ ] **Step 6: 커밋**

```bash
git add web/src/student web/e2e/student.spec.ts
git commit -m "feat(web): 학생 셸 — 그 주소 그대로 로그인 벽, 404, 소문자 건물 글자, 헤더·갱신 줄"
```

---

### Task 10: `/` 건물 선택 · `/:bld` 강의실 목록 + E2E

**Files:**
- Modify: `web/src/student/router.ts`, `web/src/student/views/HomeView.vue`, `web/src/student/__tests__/router.spec.ts`, `web/e2e/helpers.ts`, `web/e2e/student.spec.ts`
- Create: `web/src/student/building.ts`, `web/src/student/views/BuildingLayout.vue`, `web/src/student/__tests__/support.ts`
- Test: `web/src/student/__tests__/home.spec.ts`, `web/src/student/__tests__/building.spec.ts`

**Interfaces:**
- Consumes: `studentApi.rooms`(Task 1), rules(Task 2: `FREE_LAYOUT`·`isRed`·`layoutLabel`·`untilText`), favorites(Task 3), `buildingsOf`(Task 4), `RoomListRow`(Task 5), 셸(Task 9: `StudentHeader`·`RefreshedNote`·`NotFoundView`·`POLL_MS`), F1 `useResource`·`usePolling`, ui `Banner`·`Button`·`Checkbox`·`EmptyState`·`Select`·`Skeleton`.
- Produces (`building.ts`): `interface BuildingCtx { rooms: Readonly<Ref<RoomStateOut[] | undefined>>; loaded: Readonly<Ref<boolean>>; reload: () => Promise<void> }` · `BUILDING: InjectionKey<BuildingCtx>` · `useBuilding(): BuildingCtx`.
- Produces (라우트): `{ path: '/:bld([A-Z])', sensitive: true, component: BuildingLayout, meta: { gate: true } }` — 자식은 Task 11·13 이 더한다.
- Produces (`BuildingLayout`): 방 목록 1회 + 60초 폴링, `provide(BUILDING)`. DOM: `section.split__list[aria-label="강의실 목록"]` · `h2.list__count` · `p.list__sub` · `.fav` / `a.fav__chip[aria-label]` · `ul.rows > li`(RoomListRow) · `section.split__main`(자식 RouterView, 없으면 안내). 좁은 폭은 자식이 있으면 목록을 감추고(`.split--child`), 넓은 폭(≥640)은 목록 340px 상주.
- Produces (`HomeView`): 최근 건물 → 하나뿐인 건물 → 목록. `a.home__row[aria-label]`.
- Produces (테스트 도움 `support.ts`): `blank` · `roomState(over?)` · `mountAt(component, path, pattern, rooms?)` → `{ w, router }` · `stubMedia(wide): { change(matches) }`.
- Produces (`e2e/helpers.ts`): `login(page, email, ready = page.locator('nav'))` · `kstMinutesNow()` · `hmOf(m)` · `STU` · `seedStudent(request): Promise<{ roomIds: Record<number, number>; tomorrowDay: number }>`.

- [ ] **Step 1: 실패 테스트**

`web/src/student/__tests__/support.ts`
```ts
import { vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ref, type Component, type DefineComponent } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { RoomStateOut } from '@/api/types'
import { BUILDING } from '@/student/building'

export const blank = { render: () => null }
export const roomState = (over: Partial<RoomStateOut> = {}): RoomStateOut => ({
  room_id: 11,
  building_id: 3,
  building: '공학관',
  bld: 'E',
  room: 401,
  layout: 4,
  until: '13:00',
  ...over,
})

/** pattern 경로에 component 를 둔 라우터로 path 에 간 뒤 올린다. rooms 를 주면 /:bld 레이아웃처럼 BUILDING 을 준다 */
export async function mountAt(
  component: Component,
  path: string,
  pattern: string,
  rooms?: RoomStateOut[],
) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: pattern, component },
      { path: '/:rest(.*)*', component: blank },
    ],
  })
  await router.push(path)
  await router.isReady()
  const provide = rooms
    ? {
        [BUILDING as symbol]: {
          rooms: ref(rooms),
          loaded: ref(true),
          reload: vi.fn(async () => {}),
        },
      }
    : {}
  const w = mount(component as DefineComponent, {
    global: { plugins: [router], provide, stubs: { teleport: true } },
  })
  await flushPromises()
  return { w, router }
}

/** jsdom 에 matchMedia 가 없다 — 넓은 폭 여부와 바뀜 알림 */
export function stubMedia(wide: boolean) {
  let listener: ((e: { matches: boolean }) => void) | null = null
  vi.stubGlobal('matchMedia', () => ({
    matches: wide,
    addEventListener: (_: string, l: (e: { matches: boolean }) => void) => {
      listener = l
    },
    removeEventListener: () => {},
  }))
  return { change: (matches: boolean) => listener?.({ matches }) }
}
```

`web/src/student/__tests__/home.spec.ts`
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount } from '@vue/test-utils'
import { studentApi } from '@/api/student'
import HomeView from '@/student/views/HomeView.vue'
import { mountAt, roomState } from './support'

vi.mock('@/api/student', () => ({
  studentApi: {
    rooms: vi.fn(),
    week: vi.fn(),
    mine: vi.fn(),
    requestResv: vi.fn(),
    cancel: vi.fn(),
    checkin: vi.fn(),
  },
}))
const api = vi.mocked(studentApi, true)
enableAutoUnmount(afterEach)

const E = [roomState({ room_id: 1, room: 401, layout: 1 }), roomState({ room_id: 2, room: 402 })]
const K = roomState({ room_id: 3, building_id: 4, building: '운영관', bld: 'K', room: 101, layout: 6 })

beforeEach(() => {
  localStorage.clear()
  api.rooms.mockReset()
})

describe('HomeView — / 첫 진입 (student-room.md 미결 3)', () => {
  it('최근 건물이 있으면 그리로', async () => {
    localStorage.setItem('esc.lastBld', 'K')
    api.rooms.mockResolvedValue([...E, K])
    const { router } = await mountAt(HomeView, '/', '/')
    expect(router.currentRoute.value.path).toBe('/K')
  })

  it('건물이 하나뿐이면 바로 그 건물', async () => {
    api.rooms.mockResolvedValue(E)
    const { router } = await mountAt(HomeView, '/', '/')
    expect(router.currentRoute.value.path).toBe('/E')
  })

  it('여럿이면 건물 목록 — 이름·강의실 수·빈 곳, 최근 건물이 사라졌어도 목록', async () => {
    localStorage.setItem('esc.lastBld', 'Z')
    api.rooms.mockResolvedValue([...E, K])
    const { w, router } = await mountAt(HomeView, '/', '/')
    expect(router.currentRoute.value.path).toBe('/')
    const rows = w.findAll('a.home__row')
    expect(rows.map((a) => a.attributes('href'))).toEqual(['/E', '/K'])
    expect(rows.map((a) => a.attributes('aria-label'))).toEqual([
      '공학관 2개 강의실 · 지금 1곳 비어 있어요',
      '운영관 1개 강의실 · 지금 0곳 비어 있어요',
    ])
    expect(w.get('a.sh__me').attributes('href')).toBe('/me')
  })

  it('예약 가능한 방이 없으면 EmptyState, 조회 실패면 다시 시도', async () => {
    api.rooms.mockResolvedValue([])
    const empty = await mountAt(HomeView, '/', '/')
    expect(empty.w.text()).toContain('예약할 수 있는 강의실이 없습니다')
    const { ApiError, MESSAGES } = await import('@/api/client')
    api.rooms.mockRejectedValueOnce(new ApiError(0, MESSAGES[0])).mockResolvedValue(E)
    const failed = await mountAt(HomeView, '/', '/')
    expect(failed.w.text()).toContain('건물 목록을 불러오지 못했어요')
    await failed.w.get('.empty button').trigger('click')
    await vi.waitFor(() => expect(failed.router.currentRoute.value.path).toBe('/E'))
  })
})
```

`web/src/student/__tests__/building.spec.ts`
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { ApiError, MESSAGES } from '@/api/client'
import { studentApi } from '@/api/student'
import { favorites } from '@/student/favorites'
import BuildingLayout from '@/student/views/BuildingLayout.vue'
import { mountAt, roomState } from './support'

vi.mock('@/api/student', () => ({
  studentApi: {
    rooms: vi.fn(),
    week: vi.fn(),
    mine: vi.fn(),
    requestResv: vi.fn(),
    cancel: vi.fn(),
    checkin: vi.fn(),
  },
}))
const api = vi.mocked(studentApi, true)
enableAutoUnmount(afterEach)

const ROOMS = [
  roomState({ room_id: 1, room: 401, layout: 1, until: '10:50' }),
  roomState({ room_id: 2, room: 402, layout: 4, until: '13:00' }),
  roomState({ room_id: 3, room: 403, layout: 4, until: null }),
  roomState({ room_id: 4, building_id: 4, building: '운영관', bld: 'K', room: 101, layout: 6, until: '12:00' }),
]
const roomNames = (w: Awaited<ReturnType<typeof mountAt>>['w']) =>
  w.findAll('ul.rows .row__room').map((r) => r.text())

beforeEach(() => {
  localStorage.clear()
  favorites.value = []
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' })
  api.rooms.mockReset().mockResolvedValue(ROOMS)
})
afterEach(() => vi.useRealTimers())

describe('BuildingLayout — /:bld 강의실 목록', () => {
  it('맨 위는 빈 곳 개수, 빈 강의실만이 기본 — 끄면 전체, 상태를 먼저 말한다', async () => {
    const { w } = await mountAt(BuildingLayout, '/E', '/:bld')
    expect(w.get('.list__count').text()).toBe('2곳이 지금 비어 있어요')
    expect(w.get('.list__sub').text()).toMatch(/^공학관 3개 강의실 · \d\d:\d\d 기준$/)
    expect(roomNames(w)).toEqual(['402호', '403호'])
    expect(w.findAll('ul.rows .row__until').map((u) => u.text())).toEqual([
      '13:00 까지',
      '오늘 계속 비어 있어요',
    ])
    await w.get('input[type="checkbox"]').setValue(false)
    expect(roomNames(w)).toEqual(['401호', '402호', '403호'])
    const busy = w.findAll('ul.rows > li')[0]
    expect(busy.get('.badge').text()).toBe('수업중')
    expect(busy.get('a').attributes('href')).toBe('/E/401')
    expect(w.get('.rn').text()).toContain('갱신')
  })

  it('다른 건물로 — 헤더 Select 가 주소를 바꾸고, 모두 사용 중이면 전체 보기', async () => {
    const { w, router } = await mountAt(BuildingLayout, '/E', '/:bld')
    expect(localStorage.getItem('esc.lastBld')).toBe('E')
    await w.get('select').setValue('K')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/K')
    expect(localStorage.getItem('esc.lastBld')).toBe('K')
    expect(w.get('.list__count').text()).toBe('지금 비어 있는 강의실이 없어요')
    expect(w.text()).toContain('지금은 모든 강의실이 사용 중입니다')
    await w.get('.empty button').trigger('click')
    expect(roomNames(w)).toEqual(['101호'])
  })

  it('즐겨찾기 — 비어 있으면 섹션이 없고, ★ 을 누르면 생기며 esc.fav 에 남는다, 다른 건물은 이름을 붙인다', async () => {
    const { w } = await mountAt(BuildingLayout, '/E', '/:bld')
    expect(w.find('.fav').exists()).toBe(false)
    await w.findAll('ul.rows > li')[0].get('button').trigger('click')
    expect(localStorage.getItem('esc.fav')).toBe('["E-402"]')
    expect(w.findAll('a.fav__chip').map((a) => a.attributes('aria-label'))).toEqual([
      '402호 비어있음',
    ])
    favorites.value = ['K-101', 'E-402']
    await flushPromises()
    expect(w.findAll('a.fav__chip').map((a) => a.attributes('href'))).toEqual(['/E/402', '/K/101'])
    expect(w.findAll('a.fav__chip')[1].attributes('aria-label')).toBe('운영관 101호 특강')
  })

  it('없는 건물 글자면 404 + 건물 목록 링크', async () => {
    const { w } = await mountAt(BuildingLayout, '/Q', '/:bld')
    expect(w.get('h2').text()).toBe('찾을 수 없는 주소예요')
    expect(w.get('a.nf__link').attributes('href')).toBe('/')
    expect(localStorage.getItem('esc.lastBld')).toBeNull()
  })

  it('조회 실패 — 이전 목록을 지우지 않고 danger Banner + 다시 시도', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    const { w } = await mountAt(BuildingLayout, '/E', '/:bld')
    api.rooms.mockRejectedValue(new ApiError(0, MESSAGES[0]))
    await vi.advanceTimersByTimeAsync(60_000)
    await flushPromises()
    expect(w.get('[role="alert"]').text()).toContain(MESSAGES[0])
    expect(roomNames(w)).toEqual(['402호', '403호'])
    api.rooms.mockResolvedValue(ROOMS)
    await w.get('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(w.find('[role="alert"]').exists()).toBe(false)
  })

  it('첫 조회가 실패하면 빈 목록이 아니라 다시 시도', async () => {
    api.rooms.mockRejectedValueOnce(new ApiError(503, MESSAGES[503]))
    const { w } = await mountAt(BuildingLayout, '/E', '/:bld')
    expect(w.text()).toContain('강의실 목록을 불러오지 못했어요')
    expect(w.find('ul.rows').exists()).toBe(false)
    await w.get('.empty button').trigger('click')
    await flushPromises()
    expect(roomNames(w)).toEqual(['402호', '403호'])
  })
})
```

`web/src/student/__tests__/router.spec.ts` — `describe` 안 끝에 추가
```ts
  it('/:bld — 대문자 한 글자만, 소문자는 대문자로 보낸다(대소문자 구분 라우트)', async () => {
    const r = await at('/E')
    expect(r.matched[0].path).toBe('/:bld([A-Z])')
    expect(r.meta.gate).toBe(true)
    expect((await at('/e')).matched[0].path).toBe('/:bld([A-Z])')
    expect((await at('/e')).path).toBe('/E')
    expect((await at('/me')).matched[0].path).not.toBe('/:bld([A-Z])')
  })
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/student`
Expected: FAIL — `Failed to resolve import "@/student/building"`(support.ts), `"@/student/views/BuildingLayout.vue"`, router.spec `/:bld` — `expected '/:pathMatch(.*)*' to be '/:bld([A-Z])'`

- [ ] **Step 3: 구현**

`web/src/student/building.ts`
```ts
import { inject, type InjectionKey, type Ref } from 'vue'
import type { RoomStateOut } from '@/api/types'

/** /:bld 레이아웃이 학교 방 목록을 한 번 불러 자식 화면(강의실·주간·예약)에 준다 — room_id 를 푸는 한 곳 */
export interface BuildingCtx {
  rooms: Readonly<Ref<RoomStateOut[] | undefined>>
  loaded: Readonly<Ref<boolean>>
  reload: () => Promise<void>
}
export const BUILDING: InjectionKey<BuildingCtx> = Symbol('building')

export function useBuilding(): BuildingCtx {
  const ctx = inject(BUILDING)
  if (!ctx) throw new Error('useBuilding 은 /:bld 레이아웃 안에서만 쓴다')
  return ctx
}
```

`web/src/student/views/HomeView.vue` — 파일 전체를 바꾼다
```vue
<script setup lang="ts">
import { computed, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { studentApi } from '@/api/student'
import EmptyState from '@/components/ui/EmptyState.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import { useResource } from '@/lib/useResource'
import StudentHeader from '../StudentHeader.vue'
import { lastBld } from '../favorites'
import { buildingsOf } from '../roomView'

const router = useRouter()
const { data, error, reload } = useResource(() => studentApi.rooms())
const buildings = computed(() => buildingsOf(data.value ?? []))
// 첫 응답 한 번 — 최근 건물 → 건물이 하나뿐이면 그 건물 → 아니면 목록 (student-room.md 미결 3)
watch(
  data,
  (rooms) => {
    if (!rooms) return
    const list = buildingsOf(rooms)
    const target =
      list.find((b) => b.bld === lastBld()) ?? (list.length === 1 ? list[0] : undefined)
    if (target) void router.replace(`/${target.bld}`)
  },
  { once: true },
)
const retry = () => void reload()
</script>

<template>
  <div class="home">
    <StudentHeader title="우송 ESC" show-me />
    <main class="home__body">
      <h2 class="home__h">건물을 고르세요</h2>
      <Skeleton v-if="!data && !error" :rows="5" />
      <EmptyState
        v-else-if="!data"
        message="건물 목록을 불러오지 못했어요"
        :actions="[{ label: '다시 시도', variant: 'primary', onClick: retry }]"
      />
      <EmptyState v-else-if="!buildings.length" message="예약할 수 있는 강의실이 없습니다" />
      <ul v-else class="home__list">
        <li v-for="b in buildings" :key="b.id">
          <RouterLink
            :to="`/${b.bld}`"
            class="home__row"
            :aria-label="`${b.name} ${b.rooms}개 강의실 · 지금 ${b.free}곳 비어 있어요`"
          >
            <span class="home__name">{{ b.name }}</span>
            <span class="home__meta num"
              >{{ b.rooms }}개 강의실 · 지금 {{ b.free }}곳 비어 있어요</span
            >
            <span class="home__chev" aria-hidden="true">›</span>
          </RouterLink>
        </li>
      </ul>
    </main>
  </div>
</template>

<style scoped>
.home__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-width: 640px;
  margin: 0 auto;
  padding: var(--space-4);
}
.home__h {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
}
.home__list {
  margin: 0;
  padding: 0;
  list-style: none;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.home__list li + li {
  border-top: var(--border-thin) solid var(--line-1);
}
.home__row {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  min-height: 56px;
  padding: var(--space-2) var(--space-4);
  color: var(--text-1);
  text-decoration: none;
}
.home__name {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.home__meta {
  grid-row: 2;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.home__chev {
  grid-column: 2;
  grid-row: 1 / 3;
  font-size: var(--font-size-lg);
  color: var(--text-3);
}
</style>
```

`web/src/student/views/BuildingLayout.vue`
```vue
<script setup lang="ts">
import { computed, provide, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { studentApi } from '@/api/student'
import type { RoomStateOut } from '@/api/types'
import RoomListRow from '@/components/student/RoomListRow.vue'
import { FREE_LAYOUT, isRed, layoutLabel, untilText } from '@/components/student/rules'
import Banner from '@/components/ui/Banner.vue'
import Button from '@/components/ui/Button.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Select from '@/components/ui/Select.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import { formatHm } from '@/lib/time'
import { usePolling } from '@/lib/usePolling'
import { useResource } from '@/lib/useResource'
import RefreshedNote from '../RefreshedNote.vue'
import StudentHeader from '../StudentHeader.vue'
import { BUILDING } from '../building'
import { POLL_MS } from '../composables'
import { favKey, favorites, rememberBld, toggleFavorite } from '../favorites'
import { buildingsOf } from '../roomView'
import NotFoundView from './NotFoundView.vue'

const route = useRoute()
const router = useRouter()
// 학교 전체 방 — 개수·목록·건물 Select·자식 화면의 room_id 가 모두 여기서 나온다
const { data, error, refreshedAt, reload } = useResource(() => studentApi.rooms())
usePolling(reload, POLL_MS)
const loaded = computed(() => data.value !== undefined)
provide(BUILDING, { rooms: data, loaded, reload })

const bld = computed(() => String(route.params.bld))
const all = computed(() => data.value ?? [])
const buildings = computed(() => buildingsOf(all.value))
const building = computed(() => buildings.value.find((b) => b.bld === bld.value) ?? null)
watch(
  building,
  (b) => {
    if (b) rememberBld(b.bld)
  },
  { immediate: true },
)
const rooms = computed(() => all.value.filter((r) => r.bld === bld.value))
const freeCount = computed(() => rooms.value.filter((r) => r.layout === FREE_LAYOUT).length)
// '빈 강의실만' 기본 켜짐 — 18개보다 5개가 목적에 맞는다
const freeOnly = ref(true)
const shown = computed(() =>
  freeOnly.value ? rooms.value.filter((r) => r.layout === FREE_LAYOUT) : rooms.value,
)
const favSet = computed(() => new Set(favorites.value))
const favRooms = computed(() => all.value.filter((r) => favSet.value.has(favKey(r.bld, r.room))))
const chipName = (r: RoomStateOut) =>
  `${r.bld === bld.value ? '' : `${r.building} `}${r.room}호`
const options = computed(() => buildings.value.map((b) => ({ value: b.bld, label: b.name })))
/** 좁은 폭에서 자식(강의실·주간·예약)이 있으면 목록을 감춘다 — 넓은 폭은 둘 다 (CSS) */
const hasChild = computed(() => route.matched.length > 1)

const retry = () => void reload()
const showAll = () => {
  freeOnly.value = false
}
const pickBuilding = (v: string | number) => void router.push(`/${v}`)
</script>

<template>
  <NotFoundView v-if="loaded && !building" back="/" back-label="건물 목록으로" />
  <div v-else class="split" :class="{ 'split--child': hasChild }">
    <section class="split__list" aria-label="강의실 목록">
      <StudentHeader title="우송 ESC" show-me>
        <Select
          v-if="options.length > 1"
          class="split__bld"
          label="건물"
          :model-value="bld"
          :options="options"
          @update:model-value="pickBuilding"
        />
      </StudentHeader>
      <!-- 오래된 값이라도 지우지 않는다 — 갱신 줄이 오래됐다고 말한다 -->
      <Banner v-if="error && loaded" tone="danger" :message="error.message" :dismissible="false">
        <Button variant="secondary" @click="retry">다시 시도</Button>
      </Banner>
      <div class="list">
        <template v-if="!loaded">
          <EmptyState
            v-if="error"
            message="강의실 목록을 불러오지 못했어요"
            :actions="[{ label: '다시 시도', variant: 'primary', onClick: retry }]"
          />
          <Skeleton v-else :rows="5" />
        </template>
        <template v-else-if="building">
          <h2 class="list__count">
            <template v-if="freeCount"
              ><span class="num">{{ freeCount }}곳</span>이 지금 비어 있어요</template
            >
            <template v-else>지금 비어 있는 강의실이 없어요</template>
          </h2>
          <p class="list__sub num">
            {{ building.name }} {{ rooms.length }}개 강의실<template v-if="refreshedAt">
              · {{ formatHm(refreshedAt) }} 기준</template
            >
          </p>

          <section v-if="favRooms.length" class="fav" aria-labelledby="fav-h">
            <h3 id="fav-h" class="list__h">
              즐겨찾기 <span class="list__hint">★ 을 눌러 모아둡니다</span>
            </h3>
            <ul class="fav__chips">
              <li v-for="r in favRooms" :key="favKey(r.bld, r.room)">
                <RouterLink
                  :to="`/${r.bld}/${r.room}`"
                  class="fav__chip"
                  :aria-label="`${chipName(r)} ${layoutLabel(r.layout)}`"
                >
                  <span class="fav__star" aria-hidden="true">★</span>
                  <span class="num">{{ chipName(r) }}</span>
                  <span class="fav__state">{{ layoutLabel(r.layout) }}</span>
                </RouterLink>
              </li>
            </ul>
          </section>

          <div class="list__bar">
            <h3 class="list__h">{{ building.name }} 전체</h3>
            <Checkbox v-model="freeOnly" label="빈 강의실만" />
          </div>
          <EmptyState
            v-if="!shown.length"
            message="지금은 모든 강의실이 사용 중입니다"
            :actions="[{ label: '전체 보기', onClick: showAll }]"
          />
          <ul v-else class="rows">
            <RoomListRow
              v-for="r in shown"
              :key="r.room_id"
              :to="`/${r.bld}/${r.room}`"
              :room="r.room"
              :state="isRed(r.layout) ? 'busy' : 'free'"
              :label="layoutLabel(r.layout)"
              :until="untilText(r.layout, r.until)"
              :fav="favSet.has(favKey(r.bld, r.room))"
              @toggle-fav="toggleFavorite(favKey(r.bld, r.room))"
            />
          </ul>
          <RefreshedNote :at="refreshedAt" />
        </template>
      </div>
    </section>
    <section class="split__main">
      <RouterView v-if="hasChild" />
      <EmptyState v-else message="왼쪽 목록에서 강의실을 고르세요" />
    </section>
  </div>
</template>

<style scoped>
.split {
  min-height: 100vh;
}
.split__list,
.split__main {
  min-width: 0;
}
/* 좁은 폭 — 목록과 자식 중 하나만 (뒤로가기로 오간다) */
@media (max-width: 639px) {
  .split--child .split__list {
    display: none;
  }
  .split:not(.split--child) .split__main {
    display: none;
  }
}
/* 넓은 폭 — 목록 340px 상주, 화면을 키우지 않고 더 보여준다 (student-room.md 「넓은 폭」) */
@media (min-width: 640px) {
  .split {
    display: grid;
    grid-template-columns: 340px minmax(0, 1fr);
  }
  .split__list {
    position: sticky;
    top: 0;
    height: 100vh;
    overflow-y: auto;
    border-right: var(--border-thin) solid var(--line-2);
  }
}
.split__bld {
  width: 132px;
}
.split__bld :deep(.sel__label) {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
}
.list__count {
  margin: 0;
  font-size: 24px; /* student-room.md 화면 1 "24px bold" — 치수 토큰에 24 가 없다(xl 20) */
  font-weight: var(--font-weight-bold);
  line-height: var(--leading-tight);
}
.list__sub {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
.list__h {
  margin: 0;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-bold);
}
.list__hint {
  margin-left: var(--space-2);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-regular);
  color: var(--text-3);
}
.list__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}
.fav {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.fav__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}
.fav__chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  min-height: 48px;
  padding: 0 var(--space-3);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-full);
  background: var(--surface);
  color: var(--text-1);
  font-weight: var(--font-weight-bold);
  text-decoration: none;
}
.fav__star {
  color: var(--brand);
}
.fav__state {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-regular);
  color: var(--text-2);
}
.rows {
  margin: 0;
  padding: 0;
  list-style: none;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
</style>
```

`web/src/student/router.ts` — `routes` 에서 `/reset` 줄 **아래**에 추가
```ts
  // 건물 글자는 대문자 한 글자 — sensitive 로 소문자는 여기서 받지 않고 404 라우트가 대문자로 보낸다
  {
    path: '/:bld([A-Z])',
    sensitive: true,
    component: () => import('./views/BuildingLayout.vue'),
    meta: { gate: true },
    children: [],
  },
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`
Expected: PASS — home.spec 4 · building.spec 6 · router.spec 5.

- [ ] **Step 5: E2E — 하네스 + 딥링크 · 건물 · 목록**

`web/e2e/helpers.ts`
- 맨 위 `@playwright/test` import 를 `import { expect, test, type APIRequestContext, type Locator, type Page } from '@playwright/test'` 로 바꾼다.
- `login` 함수를 통째로 바꾼다
```ts
/** 전체 실행에서는 앞 파일들이 IP 당 분당 로그인 30회를 채운 채 넘어온다 — 429 면 창이 지난 뒤 한 번 더.
 * email 은 함수로 받는다 — nextAdmin 처럼 매 시도마다 계정을 돌려 쓸 수 있게.
 * ready = 로그인 뒤 보일 것 (관리자 nav, 학생 header.sh) */
export async function login(page: Page, email: () => string, ready: Locator = page.locator('nav')) {
  await fillLogin(page, email())
  const limited = page.getByText('잠시 후 다시 시도해 주세요')
  await expect(ready.or(limited)).toBeVisible()
  if (await limited.isVisible()) {
    test.setTimeout(120_000)
    await page.waitForTimeout(61_000)
    await fillLogin(page, email())
  }
  await expect(ready).toBeVisible()
}
```
- 파일 끝에 추가
```ts
// ---- F4 학생 웹 ----

/** KST 지금의 분(0..1439) — 날짜처럼 시각도 상대로 만든다 (spec §7.2) */
export const kstMinutesNow = () => {
  const d = new Date(Date.now() + 9 * 3_600_000)
  return d.getUTCHours() * 60 + d.getUTCMinutes()
}
/** 605 → '10:05' */
export const hmOf = (m: number) =>
  `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
/** KST 오늘 + n일의 요일 1=월 … 7=일 */
const kstWeekday = (offsetDays = 0) =>
  ((new Date(Date.now() + 9 * 3_600_000 + offsetDays * 86_400_000).getUTCDay() + 6) % 7) + 1

/** 학생 화면 E2E 용 — 인문관(H) 101~105(105 만 예약 불가) + 자연관(J) 301. 한 모뎀이 두 건물을 맡는다 */
export const STU = {
  building: '인문관',
  bld: 'H',
  modem: 'e2e-m7',
  rooms: [101, 102, 103, 104, 105],
  closed: 105,
  other: { building: '자연관', bld: 'J', room: 301 },
} as const

/** 멱등(건물 H 가 있으면 방 id 만). 101 = 지금 '세미나'(특강, 오늘 −30~+60분) 로 사용 중 +
 * 내일 요일에 겹친 두 슬롯(10–12 캡스톤디자인 수업 · 11–13 동아리 대관 특강 → 서버가 '외 1건'으로 합친다)과
 * 14–15 운영체제 휴강. 102~104 는 비어 있다 */
export async function seedStudent(
  request: APIRequestContext,
): Promise<{ roomIds: Record<number, number>; tomorrowDay: number }> {
  const headers = { authorization: `Bearer ${await apiLogin(request, cfg.ADMINS[0])}` }
  const call = async <T>(method: 'get' | 'post' | 'put', p: string, data?: unknown): Promise<T> => {
    const r = await request[method](p, { headers, data })
    expect(r.status(), `${method} ${p}`).toBe(200)
    return (await r.json()) as T
  }
  const tomorrowDay = kstWeekday(1)
  let h = (await call<{ id: number; bld: string }[]>('get', '/api/buildings')).find(
    (b) => b.bld === STU.bld,
  )
  if (!h) {
    await ensureModems(request, [STU.modem])
    h = await call<{ id: number; bld: string }>('post', '/api/buildings', {
      school_id: 1,
      name: STU.building,
      bld: STU.bld,
      modem_id: STU.modem,
    })
    const j = await call<{ id: number }>('post', '/api/buildings', {
      school_id: 1,
      name: STU.other.building,
      bld: STU.other.bld,
      modem_id: STU.modem,
    })
    const ids: Record<number, number> = {}
    for (const room of STU.rooms) {
      const r = await call<{ id: number }>('post', '/api/rooms', {
        building_id: h.id,
        room,
        units: 1,
        reservable: room !== STU.closed,
      })
      ids[room] = r.id
    }
    await call('post', '/api/rooms', {
      building_id: j.id,
      room: STU.other.room,
      units: 1,
      reservable: true,
    })
    const slot = (from: string, to: string, type: number, subject: string, professor: string) => {
      const [s_h, s_m] = from.split(':').map(Number)
      const [e_h, e_m] = to.split(':').map(Number)
      return call('put', `/api/rooms/${ids[101]}/slots`, {
        day: tomorrowDay,
        s_h,
        s_m,
        e_h,
        e_m,
        type,
        subject,
        professor,
        source: 2,
      })
    }
    await slot('10:00', '12:00', 1, '캡스톤디자인', '김교수')
    await slot('11:00', '13:00', 5, '동아리 대관', '')
    await slot('14:00', '15:00', 3, '운영체제', '이교수')
    const t = kstMinutesNow()
    const s = Math.max(0, Math.floor((t - 30) / 5) * 5)
    const e = Math.min(23 * 60 + 55, Math.ceil((t + 60) / 5) * 5)
    await call('post', `/api/rooms/${ids[101]}/reservations`, {
      date: kstDate(0),
      s_h: Math.floor(s / 60),
      s_m: s % 60,
      e_h: Math.floor(e / 60),
      e_m: e % 60,
      type: 5,
      subject: '세미나',
      professor: '',
    })
  }
  const hid = h.id
  const rooms = await call<{ id: number; building_id: number; room: number }[]>('get', '/api/rooms')
  return {
    roomIds: Object.fromEntries(
      rooms.filter((r) => r.building_id === hid).map((r) => [r.room, r.id]),
    ),
    tomorrowDay,
  }
}
```

`web/e2e/student.spec.ts`
- 맨 위 두 import 줄을 바꾼다
```ts
import {
  expect,
  test,
  type APIRequestContext,
  type BrowserContext,
  type Page,
} from '@playwright/test'
import { STU, SIZES, WEB_URL, createStudent, login, seedStudent, shot } from './helpers'

// e2e 는 node 타입 — page.evaluate 콜백은 브라우저에서 돈다
declare const localStorage: { getItem(k: string): string | null }
```
- `let page: Page` 줄 **아래**에 추가
```ts
let api: APIRequestContext
let A: { email: string }
let seed: Awaited<ReturnType<typeof seedStudent>>
const shownRows = () => page.locator('ul.rows > li')
```
- `beforeAll` 의 `page = await ctx.newPage()` 줄 **위**에 `api = ctx.request` 를 추가한다.
- 파일 끝에 추가
```ts
test('딥링크 — 소문자는 대문자로, 벽 → 로그인 → 원래 주소, 없는 건물은 404 → 건물 목록', async () => {
  test.setTimeout(60_000)
  seed = await seedStudent(api)
  A = await createStudent(api, { approve: true, name: '이학생' })
  await page.goto('/q')
  await expect(page).toHaveURL(/\/Q$/)
  await expect(page.getByRole('heading', { name: /^Q동의 빈 강의실/ })).toBeVisible()
  await page.getByRole('link', { name: '로그인' }).click()
  await login(page, () => A.email, page.locator('header.sh'))
  await expect(page).toHaveURL(/\/Q$/)
  await expect(page.getByRole('heading', { name: '찾을 수 없는 주소예요' })).toBeVisible()
  await page.getByRole('link', { name: '건물 목록으로' }).click()
  await expect(page.getByRole('heading', { name: '건물을 고르세요' })).toBeVisible()
  const h = page.getByRole('link', { name: new RegExp(`^${STU.building} `) })
  await expect(h).toHaveAttribute('aria-label', /4개 강의실 · 지금 3곳 비어 있어요/)
  await expect(page.getByRole('link', { name: new RegExp(`^${STU.other.building} `) })).toBeVisible()
  await shot(page, 'student-home-390')
  await h.click()
  await expect(page).toHaveURL(new RegExp(`/${STU.bld}$`))
})

test('강의실 목록 — 빈 곳 개수가 먼저, 빈 강의실만 기본, 즐겨찾기는 고르면 생긴다', async () => {
  await expect(page.getByRole('heading', { name: '3곳이 지금 비어 있어요' })).toBeVisible()
  await expect(shownRows()).toHaveCount(3)
  await expect(page.getByRole('link', { name: /^101호/ })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: /^즐겨찾기/ })).toHaveCount(0)
  await page.getByLabel('빈 강의실만').uncheck()
  await expect(shownRows()).toHaveCount(4)
  await expect(page.getByRole('link', { name: /^101호 특강 / })).toBeVisible()
  const row102 = shownRows().filter({ hasText: '102호' })
  expect((await row102.boundingBox())!.height).toBeGreaterThanOrEqual(56)
  await row102.getByRole('button', { name: '즐겨찾기 추가' }).click()
  await expect(row102.getByRole('button', { name: '즐겨찾기 해제' })).toBeVisible()
  await expect(page.getByRole('heading', { name: /^즐겨찾기/ })).toBeVisible()
  await expect(page.getByRole('link', { name: '102호 비어있음', exact: true })).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('esc.fav'))).toBe('["H-102"]')
  await expect(page.locator('.rn')).toContainText(/문 앞 e-Paper 와 같은 내용 · \d\d:\d\d 갱신/)
  await shot(page, 'student-list-390')
})
```

Run: E2E 명령 끝에 ` e2e/student.spec.ts`
Expected: 4 passed. `student-home-390.png`·`student-list-390.png` 를 `student-room.md` 화면 1과 대조 — 헤더 58 · 개수 24px bold · 부제 `인문관 4개 강의실 · HH:MM 기준` · 즐겨찾기 칩 48px(★ `brand`) · `인문관 전체 ☑ 빈 강의실만` · 행 56px(왼쪽 링크 + 오른쪽 48px ★) · 사용중은 `room.busy` 틴트 배지, 빈 곳은 칠하지 않음 · 바탕 `bg.student`, 카드 `surface` · 하단 `● 문 앞 e-Paper 와 같은 내용 · HH:MM 갱신`.

- [ ] **Step 6: 커밋**

```bash
git add web/src/student web/e2e/helpers.ts web/e2e/student.spec.ts
git commit -m "feat(web): 학생 건물 선택·강의실 목록 — 빈 곳 개수 먼저, 빈 강의실만 기본, 즐겨찾기, 60초 갱신"
```

---

### Task 11: `/:bld/:room` 강의실 · `/week` 이번 주 · 넓은 폭 + E2E

**Files:**
- Modify: `web/src/student/building.ts`, `web/src/student/router.ts`, `web/e2e/student.spec.ts`
- Create: `web/src/student/views/RoomView.vue`, `web/src/student/views/WeekView.vue`
- Test: `web/src/student/__tests__/room.spec.ts`

**Interfaces:**
- Consumes: `studentApi.week`·`WeekOut`(Task 1), rules(Task 2: `dateLabel`·`durationText`·`hmToMin`), grid(Task 4), `todayRows`·`nextFree`(Task 4), `FavoriteStar`(Task 5), `WeekGrid`(Task 6), 셸(Task 9: `StudentHeader`·`CtaLink`·`RefreshedNote`·`NotFoundView`·`useWide`·`useNow`·`POLL_MS`), `BUILDING`·`useBuilding`(Task 10), favorites(Task 3), F2 `BUSY_TYPES`·`TYPE_LABEL`·`dayOfDate`·`mondayOf`, `kstDateStr`·`kstMinutes`·`formatHm`.
- Produces (`building.ts`): `useRoomWeek(opts: { poll: boolean })` → `{ bld: ComputedRef<string>; roomNo: ComputedRef<number>; room: ComputedRef<RoomStateOut | null>; now: Ref<Date>; notFound: ComputedRef<boolean>; title: ComputedRef<string>; week: ShallowRef<WeekOut | undefined>; weekError: ShallowRef<ApiError | null>; refreshedAt: ShallowRef<Date | null>; reload: () => Promise<void> }` · `useWeekGrid(week, now, rowPx: 24 | 32)` → `{ days; blocks; range; todayIndex; nowY }`(전부 computed).
- Produces (라우트): `/:bld` 의 자식 `:room(\\d+)` → RoomView · `:room(\\d+)/week` → WeekView.
- Produces (`RoomView`): `h1` `공학관 401호` · `a.sh__back[aria-label="강의실 목록"]` → `/{bld}` · 헤더 ★ · `ol.today > li.today__row`(`.today__row--now` 하나, `.today__label`, `.badge`) · 좁은 폭 `a.room__week`·`.room__cta a.cta` / 넓은 폭 `.room__next-v`·WeekGrid(32)·헤더 `a.cta.cta--compact`.
- Produces (`WeekView`): `h1` `공학관 401호 · 이번 주` · WeekGrid(24) · 넓어지면 `/{bld}/{room}` 으로 replace.

- [ ] **Step 1: 실패 테스트**

`web/src/student/__tests__/room.spec.ts`
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { ApiError, MESSAGES } from '@/api/client'
import { studentApi } from '@/api/student'
import type { WeekOut } from '@/api/types'
import week from '@/api/__fixtures__/week.json'
import { favorites } from '@/student/favorites'
import RoomView from '@/student/views/RoomView.vue'
import WeekView from '@/student/views/WeekView.vue'
import { mountAt, roomState, stubMedia } from './support'

vi.mock('@/api/student', () => ({
  studentApi: {
    rooms: vi.fn(),
    week: vi.fn(),
    mine: vi.fn(),
    requestResv: vi.fn(),
    cancel: vi.fn(),
    checkin: vi.fn(),
  },
}))
const api = vi.mocked(studentApi, true)
enableAutoUnmount(afterEach)

const WEEK = week as WeekOut
const ROOMS = [roomState({ room_id: 11, room: 401, layout: 1, until: '10:50' })]

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-23T01:42:00Z')) // KST 금 10:42 — 픽스처의 오늘
  favorites.value = []
  localStorage.clear()
  api.week.mockReset().mockResolvedValue(WEEK)
  stubMedia(false)
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('RoomView — /:bld/:room', () => {
  it('오늘 — 빈 구간도 행, 지금 행에 지금 배지(brand), 내 신청 표시, ‹ 는 목록 링크', async () => {
    const { w } = await mountAt(RoomView, '/E/401', '/:bld/:room', ROOMS)
    expect(api.week).toHaveBeenCalledWith(11)
    expect(w.get('h1').text()).toBe('공학관 401호')
    expect(w.get('#today-h').text()).toContain('10월 23일 금')
    const rows = w.findAll('.today__row')
    expect(rows.map((r) => r.get('.today__label').text())).toEqual([
      '비어있음 —10:00',
      '알고리즘 외 1건',
      '비어있음 —15:00',
      '캡스톤 스터디',
      '비어있음 —21:00',
    ])
    const now = w.get('.today__row--now')
    expect(now.get('.today__label').text()).toBe('알고리즘 외 1건')
    expect(now.findAll('.badge').map((b) => b.text())).toEqual(['수업중', '지금 10:42'])
    expect(now.findAll('.badge')[1].classes()).toEqual(
      expect.arrayContaining(['badge--brand', 'badge--solid']),
    )
    expect(w.findAll('.today__row--now')).toHaveLength(1)
    expect(rows[3].get('.today__label').classes()).toContain('today__label--mine')
    const back = w.get('a.sh__back')
    expect(back.attributes('href')).toBe('/E')
    expect(back.attributes('aria-label')).toBe('강의실 목록')
    expect(w.get('a.room__week').attributes('href')).toBe('/E/401/week')
    expect(w.get('.room__cta a.cta').attributes('href')).toBe('/E/401/reserve')
    expect(w.find('.wg').exists()).toBe(false)
  })

  it('헤더 ★ — 즐겨찾기 토글, esc.fav 에 남는다', async () => {
    const { w } = await mountAt(RoomView, '/E/401', '/:bld/:room', ROOMS)
    await w.get('.sh button').trigger('click')
    expect(localStorage.getItem('esc.fav')).toBe('["E-401"]')
    expect(w.get('.sh button').attributes('aria-label')).toBe('즐겨찾기 해제')
  })

  it('넓은 폭 — 다음 비는 시간 카드, 같은 격자(32, 오늘 금), 예약은 헤더 오른쪽 40px', async () => {
    stubMedia(true)
    const { w } = await mountAt(RoomView, '/E/401', '/:bld/:room', ROOMS)
    expect(w.get('.room__next-v').text()).toBe('13:00 – 15:00 · 2시간')
    expect(w.find('.wg--wide').exists()).toBe(true)
    expect(w.get('.wg__day--today').text()).toBe('금')
    expect(w.find('.room__cta').exists()).toBe(false)
    expect(w.find('a.room__week').exists()).toBe(false)
    const cta = w.get('.sh a.cta')
    expect(cta.attributes('href')).toBe('/E/401/reserve')
    expect(cta.classes()).toContain('cta--compact')
  })

  it('목록에 없는 호수·주간 404 면 404 화면 + 강의실 목록 링크', async () => {
    const missing = await mountAt(RoomView, '/E/499', '/:bld/:room', ROOMS)
    expect(missing.w.get('h2').text()).toBe('찾을 수 없는 주소예요')
    expect(missing.w.get('a.nf__link').attributes('href')).toBe('/E')
    expect(api.week).not.toHaveBeenCalled()
    api.week.mockRejectedValue(new ApiError(404, MESSAGES[404]))
    const gone = await mountAt(RoomView, '/E/401', '/:bld/:room', ROOMS)
    expect(gone.w.get('h2').text()).toBe('찾을 수 없는 주소예요')
  })

  it('주간 첫 조회 실패 — 오늘 목록 자리에 다시 시도', async () => {
    api.week.mockRejectedValueOnce(new ApiError(0, MESSAGES[0]))
    const { w } = await mountAt(RoomView, '/E/401', '/:bld/:room', ROOMS)
    expect(w.text()).toContain('시간표를 불러오지 못했어요')
    await w.get('.empty button').trigger('click')
    await flushPromises()
    expect(w.findAll('.today__row')).toHaveLength(5)
  })
})

describe('WeekView — /:bld/:room/week', () => {
  it('좁은 폭 — 24px 격자, 제목, 강의실로 돌아가는 링크', async () => {
    const { w } = await mountAt(WeekView, '/E/401/week', '/:bld/:room/week', ROOMS)
    expect(w.get('h1').text()).toBe('공학관 401호 · 이번 주')
    expect(w.get('a.sh__back').attributes('href')).toBe('/E/401')
    expect(w.find('.wg--wide').exists()).toBe(false)
    expect(
      w.get('[aria-label="금 10:00–13:00 알고리즘 외 1건"]').attributes('style'),
    ).toContain('height: 144px')
    expect(w.get('.wg__day--today').text()).toBe('금')
  })

  it('넓은 폭이면(처음부터든 바뀌든) /:bld/:room 으로 replace — 이미 그 안에 있다', async () => {
    const media = stubMedia(false)
    const { router } = await mountAt(WeekView, '/E/401/week', '/:bld/:room/week', ROOMS)
    expect(router.currentRoute.value.path).toBe('/E/401/week')
    media.change(true)
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/E/401')
    stubMedia(true)
    const wide = await mountAt(WeekView, '/E/401/week', '/:bld/:room/week', ROOMS)
    expect(wide.router.currentRoute.value.path).toBe('/E/401')
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/student/__tests__/room.spec.ts`
Expected: FAIL — `Failed to resolve import "@/student/views/RoomView.vue"`

- [ ] **Step 3: 구현**

`web/src/student/building.ts` — 파일 전체를 바꾼다
```ts
import { computed, inject, watch, type InjectionKey, type Ref } from 'vue'
import { useRoute } from 'vue-router'
import { studentApi } from '@/api/student'
import type { RoomStateOut, WeekOut } from '@/api/types'
import { gridRange, nowTop, visibleDays, weekBlocks } from '@/components/student/grid'
import { dayOfDate, kstDateStr, kstMinutes, mondayOf } from '@/lib/time'
import { usePolling } from '@/lib/usePolling'
import { useResource } from '@/lib/useResource'
import { POLL_MS, useNow } from './composables'

/** /:bld 레이아웃이 학교 방 목록을 한 번 불러 자식 화면(강의실·주간·예약)에 준다 — room_id 를 푸는 한 곳 */
export interface BuildingCtx {
  rooms: Readonly<Ref<RoomStateOut[] | undefined>>
  loaded: Readonly<Ref<boolean>>
  reload: () => Promise<void>
}
export const BUILDING: InjectionKey<BuildingCtx> = Symbol('building')

export function useBuilding(): BuildingCtx {
  const ctx = inject(BUILDING)
  if (!ctx) throw new Error('useBuilding 은 /:bld 레이아웃 안에서만 쓴다')
  return ctx
}

/** 자식 화면 공용 — 주소의 글자·호수를 레이아웃 목록에서 room_id 로 풀고 주간을 부른다.
 * 목록에 없으면(없는 호수·예약 안 받는 방·다른 학교) 또는 주간이 404 면 notFound */
export function useRoomWeek(opts: { poll: boolean }) {
  const ctx = useBuilding()
  const route = useRoute()
  const bld = computed(() => String(route.params.bld))
  const roomNo = computed(() => Number(route.params.room))
  const room = computed(
    () => ctx.rooms.value?.find((r) => r.bld === bld.value && r.room === roomNo.value) ?? null,
  )
  const now = useNow()
  // room 이 있을 때만 부른다(아래 watch) — 방을 바꾸면 늦게 온 옛 방 응답은 useResource 가 버린다
  const { data, error, refreshedAt, reload } = useResource(
    () => studentApi.week(room.value!.room_id),
    { immediate: false },
  )
  watch(
    () => room.value?.room_id,
    (id) => {
      if (id !== undefined) void reload()
    },
    { immediate: true },
  )
  if (opts.poll)
    usePolling(async () => {
      if (room.value) await reload()
    }, POLL_MS)
  const notFound = computed(
    () => (ctx.loaded.value && !room.value) || error.value?.status === 404,
  )
  const title = computed(() => `${room.value?.building ?? ''} ${roomNo.value}호`.trim())
  return { bld, roomNo, room, now, notFound, title, week: data, weekError: error, refreshedAt, reload }
}

/** 주간 격자 입력 — '오늘' 표시는 서버 week_start 가 오늘의 월요일일 때만(자정 직후 한 번의 폴링 사이 어긋남) */
export function useWeekGrid(
  week: Readonly<Ref<WeekOut | undefined>>,
  now: Readonly<Ref<Date>>,
  rowPx: 24 | 32,
) {
  const busy = computed(() => week.value?.busy ?? [])
  const range = computed(() => gridRange(busy.value))
  const days = computed(() => visibleDays(busy.value))
  const blocks = computed(() => weekBlocks(busy.value, range.value, rowPx))
  const today = computed(() => kstDateStr(now.value))
  const todayIndex = computed(() =>
    week.value?.week_start === mondayOf(today.value)
      ? days.value.indexOf(dayOfDate(today.value))
      : -1,
  )
  const nowY = computed(() =>
    todayIndex.value < 0 ? null : nowTop(kstMinutes(now.value), range.value, rowPx),
  )
  return { days, blocks, range, todayIndex, nowY }
}
```

`web/src/student/views/RoomView.vue`
```vue
<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { SlotType } from '@/api/types'
import { BUSY_TYPES, TYPE_LABEL } from '@/components/domain/rules'
import FavoriteStar from '@/components/student/FavoriteStar.vue'
import WeekGrid from '@/components/student/WeekGrid.vue'
import { dateLabel, durationText, hmToMin } from '@/components/student/rules'
import Badge from '@/components/ui/Badge.vue'
import Banner from '@/components/ui/Banner.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import { dayOfDate, formatHm, kstDateStr, kstMinutes } from '@/lib/time'
import CtaLink from '../CtaLink.vue'
import RefreshedNote from '../RefreshedNote.vue'
import StudentHeader from '../StudentHeader.vue'
import { useRoomWeek, useWeekGrid } from '../building'
import { useWide } from '../composables'
import { favKey, favorites, toggleFavorite } from '../favorites'
import { nextFree, todayRows } from '../roomView'
import NotFoundView from './NotFoundView.vue'

const ROW_PX = 32 // 넓은 폭 격자 — 좁은 폭은 /week 별도 화면 (student-room.md 「넓은 폭」)
const wide = useWide()
const { bld, roomNo, now, notFound, title, week, weekError, refreshedAt, reload } = useRoomWeek({
  poll: true,
})
const { days, blocks, range, todayIndex, nowY } = useWeekGrid(week, now, ROW_PX)
const today = computed(() => kstDateStr(now.value))
// '지금' 카드 대신 오늘 목록에서 지금 행을 세운다 — 빈 구간도 행 (student-room.md 화면 2)
const rows = computed(() =>
  todayRows(
    week.value?.busy.find((d) => d.day === dayOfDate(today.value))?.spans ?? [],
    kstMinutes(now.value),
  ),
)
const fav = computed(() => favorites.value.includes(favKey(bld.value, roomNo.value)))
const next = computed(() => nextFree(week.value?.free ?? []))
const reserveTo = computed(() => `/${bld.value}/${roomNo.value}/reserve`)
const isBusy = (t: SlotType | null) => t !== null && BUSY_TYPES.includes(t)
const toggle = () => toggleFavorite(favKey(bld.value, roomNo.value))
const retry = () => void reload()
</script>

<template>
  <NotFoundView v-if="notFound" :back="`/${bld}`" back-label="강의실 목록으로" />
  <div v-else class="room">
    <StudentHeader :title="title" :back="`/${bld}`" back-label="강의실 목록" hide-back-wide>
      <FavoriteStar :on="fav" @toggle="toggle" />
      <CtaLink v-if="wide" :to="reserveTo" compact>이 강의실 예약하기</CtaLink>
    </StudentHeader>
    <Banner v-if="weekError && week" tone="danger" :message="weekError.message" :dismissible="false">
      <Button variant="secondary" @click="retry">다시 시도</Button>
    </Banner>
    <main class="room__body">
      <section class="room__card" aria-labelledby="today-h">
        <h2 id="today-h" class="room__h">
          오늘 <span class="room__date num">{{ dateLabel(today) }}</span>
        </h2>
        <Skeleton v-if="!week && !weekError" :rows="3" />
        <EmptyState
          v-else-if="!week"
          message="시간표를 불러오지 못했어요"
          :actions="[{ label: '다시 시도', variant: 'primary', onClick: retry }]"
        />
        <ol v-else class="today">
          <li
            v-for="r in rows"
            :key="r.from"
            class="today__row"
            :class="{ 'today__row--now': r.now }"
          >
            <span class="today__time num"
              >{{ r.from }}<span class="today__to">–{{ r.to }}</span></span
            >
            <span
              class="today__label"
              :class="{ 'today__label--off': r.type === 3, 'today__label--mine': r.mine }"
              >{{ r.label
              }}<span v-if="r.type === null" class="today__until num"> —{{ r.to }}</span></span
            >
            <Badge v-if="isBusy(r.type)" tone="busy" size="sm">{{
              TYPE_LABEL[r.type as SlotType]
            }}</Badge>
            <Badge v-else-if="r.type === 3" tone="neutral" variant="outline" size="sm">휴강</Badge>
            <!-- '지금'은 brand — 적색은 '사용중' 전용 -->
            <Badge v-if="r.now" tone="brand" variant="solid" size="sm" class="num"
              >지금 {{ formatHm(now) }}</Badge
            >
          </li>
        </ol>
      </section>

      <section v-if="wide" class="room__card" aria-labelledby="next-h">
        <h2 id="next-h" class="room__h">다음 비는 시간</h2>
        <p v-if="next" class="room__next-v num">
          {{ next.from }} – {{ next.to }} · {{ durationText(hmToMin(next.to) - hmToMin(next.from)) }}
        </p>
        <p v-else class="room__muted">오늘은 더 비는 시간이 없어요</p>
      </section>

      <section v-if="wide && week" class="room__card" aria-labelledby="week-h">
        <h2 id="week-h" class="room__h">이번 주</h2>
        <WeekGrid
          :days="days"
          :blocks="blocks"
          :row-height="ROW_PX"
          :range="range"
          :today-index="todayIndex"
          :now-top="nowY"
        />
      </section>

      <RouterLink v-if="!wide" :to="`/${bld}/${roomNo}/week`" class="room__week"
        >이번 주 전체 보기 <span aria-hidden="true">›</span></RouterLink
      >
      <RefreshedNote :at="refreshedAt" />
    </main>
    <!-- 1차 동작은 엄지가 닿는 하단 (student-room.md §예약 · 진입) -->
    <footer v-if="!wide" class="room__cta">
      <CtaLink :to="reserveTo">이 강의실 예약하기</CtaLink>
      <p class="room__muted">비어 있는 시간만 · 7일 이내</p>
    </footer>
  </div>
</template>

<style scoped>
.room {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}
.room__body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-4);
}
.room__card {
  padding: var(--space-4);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.room__h {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-bold);
}
.room__date {
  margin-left: var(--space-2);
  font-weight: var(--font-weight-regular);
  color: var(--text-3);
}
.today {
  margin: 0;
  padding: 0;
  list-style: none;
}
.today__row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 48px;
  padding: 0 var(--space-2);
  border-bottom: var(--border-thin) solid var(--line-1);
}
.today__row:last-child {
  border-bottom: 0;
}
.today__row--now {
  background: var(--brand-tint);
}
.today__row--now .today__time {
  color: var(--brand);
  font-weight: var(--font-weight-bold);
}
.today__time {
  flex: 0 0 auto;
  color: var(--text-2);
}
/* 좁은 폭은 시작 시각만, 넓은 폭은 시각 구간 (student-room.md 「넓은 폭」) */
.today__to {
  display: none;
}
.today__label {
  flex: 1;
  min-width: 0;
}
.today__label--off {
  color: var(--room-free-text);
  text-decoration: line-through;
}
.today__label--mine {
  color: var(--brand);
  font-weight: var(--font-weight-bold);
}
.today__until {
  color: var(--text-3);
}
.room__next-v {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.room__muted {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.room__week {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 48px;
  padding: 0 var(--space-4);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-md);
  background: var(--surface);
  color: var(--text-1);
  font-weight: var(--font-weight-bold);
  text-decoration: none;
}
.room__cta {
  position: sticky;
  bottom: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3) var(--space-4);
  border-top: var(--border-thin) solid var(--line-2);
  background: var(--surface);
  text-align: center;
}
@media (min-width: 640px) {
  .today__to {
    display: inline;
  }
}
</style>
```

`web/src/student/views/WeekView.vue`
```vue
<script setup lang="ts">
import { watch } from 'vue'
import { useRouter } from 'vue-router'
import WeekGrid from '@/components/student/WeekGrid.vue'
import Banner from '@/components/ui/Banner.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import RefreshedNote from '../RefreshedNote.vue'
import StudentHeader from '../StudentHeader.vue'
import { useRoomWeek, useWeekGrid } from '../building'
import { useWide } from '../composables'
import NotFoundView from './NotFoundView.vue'

const ROW_PX = 24 // bp.mobile — 30분 24px, 18행 432px (student-room.md 화면 3)
const router = useRouter()
const wide = useWide()
const { bld, roomNo, now, notFound, title, week, weekError, refreshedAt, reload } = useRoomWeek({
  poll: true,
})
const { days, blocks, range, todayIndex, nowY } = useWeekGrid(week, now, ROW_PX)
// 넓은 폭에서는 이미 강의실 화면 안에 있다 (student-room.md 「넓은 폭」)
watch(
  wide,
  (w) => {
    if (w) void router.replace(`/${bld.value}/${roomNo.value}`)
  },
  { immediate: true },
)
const retry = () => void reload()
</script>

<template>
  <NotFoundView v-if="notFound" :back="`/${bld}`" back-label="강의실 목록으로" />
  <div v-else class="week">
    <StudentHeader :title="`${title} · 이번 주`" :back="`/${bld}/${roomNo}`" back-label="강의실로" />
    <Banner v-if="weekError && week" tone="danger" :message="weekError.message" :dismissible="false">
      <Button variant="secondary" @click="retry">다시 시도</Button>
    </Banner>
    <main class="week__body">
      <Skeleton v-if="!week && !weekError" :rows="6" />
      <EmptyState
        v-else-if="!week"
        message="이번 주 시간표를 불러오지 못했어요"
        :actions="[{ label: '다시 시도', variant: 'primary', onClick: retry }]"
      />
      <template v-else>
        <div class="week__card">
          <WeekGrid
            :days="days"
            :blocks="blocks"
            :row-height="ROW_PX"
            :range="range"
            :today-index="todayIndex"
            :now-top="nowY"
          />
        </div>
        <p class="week__hint">빈 칸이 비어 있는 시간이에요</p>
      </template>
      <RefreshedNote :at="refreshedAt" />
    </main>
  </div>
</template>

<style scoped>
.week__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
}
.week__card {
  padding: var(--space-2);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.week__hint {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
</style>
```

`web/src/student/router.ts` — `/:bld([A-Z])` 레코드의 `children: [],` 줄을 바꾼다
```ts
    children: [
      { path: ':room(\\d+)', component: () => import('./views/RoomView.vue') },
      { path: ':room(\\d+)/week', component: () => import('./views/WeekView.vue') },
    ],
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`
Expected: PASS — room.spec 7 tests, 앞 Task 들 그대로.

- [ ] **Step 5: E2E — 강의실 · 이번 주 · 넓은 폭**

`web/e2e/student.spec.ts`
- `const shownRows = …` 줄 **아래**에 추가
```ts
const DAYS = ['월', '화', '수', '목', '금', '토', '일']
```
- 파일 끝에 추가
```ts
test('강의실 — 오늘 목록은 빈 구간도 행, 지금 행을 세운다, ‹ 는 목록으로 가는 링크', async () => {
  await page.getByRole('link', { name: /^101호 / }).click()
  await expect(page).toHaveURL(new RegExp(`/${STU.bld}/101$`))
  await expect(
    page.getByRole('heading', { level: 1, name: `${STU.building} 101호` }),
  ).toBeVisible()
  const nowRow = page.locator('.today__row--now')
  await expect(nowRow).toContainText('세미나')
  await expect(nowRow).toContainText(/지금 \d\d:\d\d/)
  await expect(page.locator('.today__row').filter({ hasText: '비어있음' }).first()).toBeVisible()
  await expect(page.getByRole('link', { name: '강의실 목록' })).toHaveAttribute(
    'href',
    `/${STU.bld}`,
  )
  const cta = page.getByRole('link', { name: '이 강의실 예약하기' })
  expect((await cta.boundingBox())!.height).toBeGreaterThanOrEqual(48)
  await shot(page, 'student-room-390')
})

test('이번 주 — 겹친 사용 블록은 한 덩어리 "외 1건", 휴강은 점선으로 따로', async () => {
  await page.getByRole('link', { name: '이번 주 전체 보기' }).click()
  await expect(page).toHaveURL(new RegExp(`/${STU.bld}/101/week$`))
  const day = DAYS[seed.tomorrowDay - 1]
  await expect(
    page.getByRole('listitem', { name: `${day} 10:00–13:00 캡스톤디자인 외 1건` }),
  ).toBeVisible()
  await expect(page.getByRole('listitem', { name: `${day} 14:00–15:00 운영체제` })).toHaveClass(
    /wg__blk--off/,
  )
  await shot(page, 'student-week-390')
})

test('넓은 폭 — /week 는 강의실로, 목록 340px 상주, 격자는 같은 모양, 예약은 헤더 오른쪽', async () => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await expect(page).toHaveURL(new RegExp(`/${STU.bld}/101$`))
  const list = page.getByRole('region', { name: '강의실 목록' })
  await expect(list).toBeVisible()
  expect((await list.boundingBox())!.width).toBe(340)
  await expect(page.locator('.sh').getByRole('link', { name: '이 강의실 예약하기' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '다음 비는 시간' })).toBeVisible()
  await expect(page.getByRole('listitem', { name: /캡스톤디자인 외 1건/ })).toBeVisible()
  await shot(page, 'student-wide-1280')
  await page.setViewportSize(SIZES.student)
  await expect(list).toBeHidden()
})
```

Run: E2E 명령 끝에 ` e2e/student.spec.ts`
Expected: 7 passed. 스크린샷 대조 — `student-room-390`: 헤더 `‹ 인문관 101호 ★`, `오늘 N월 N일 요일`, 행 48px, 지금 행 `brand.tint` + 시각 `brand` 700 + `지금 HH:MM` brand 채움(적색 아님), 빈 구간 `비어있음 —HH:MM`, `이번 주 전체 보기 ›`, 하단 고정 48px `이 강의실 예약하기` + `비어 있는 시간만 · 7일 이내`. `student-week-390`: 30분 24px · 시각 열 34 · 하루 64 · 09–18(18행 432px, 벗어나면 편다) · 오늘 열 `brand.tint` + 머리 `brand` + 지금 선 2px · 합친 블록 한 덩어리 · 휴강 점선+취소선. `student-wide-1280`: 목록 340 상주 · 격자 30분 32px · `다음 비는 시간` 카드 · 헤더 오른쪽 40px 예약.

- [ ] **Step 6: 커밋**

```bash
git add web/src/student web/e2e/student.spec.ts
git commit -m "feat(web): 학생 강의실·이번 주 — 오늘 목록의 지금 행, 서버가 합친 주간 격자, 넓은 폭 한 화면"
```

---

### Task 12: `/me` 내 예약 + E2E

**Files:**
- Modify: `web/src/student/router.ts`, `web/e2e/student.spec.ts`
- Create: `web/src/student/views/MyView.vue`
- Test: `web/src/student/__tests__/me.spec.ts`

**Interfaces:**
- Consumes: `studentApi.mine`·`cancel`·`checkin`(Task 1), rules(Task 2: `sortMine`·`CHANGED_TEXT`·`CHECKIN_CLOSED_TEXT`), `MyResvCard`(Task 8), 셸(Task 9: `StudentHeader`·`RefreshedNote`·`POLL_MS`·`useNow`), `lastBld`(Task 3), `mountAt`(Task 10 support), F1 `useResource`·`usePolling`·`clearSession`·`showToast`, ui `Banner`·`Button`·`EmptyState`·`Modal`·`Skeleton`.
- Produces (라우트): `{ path: '/me', component: MyView, meta: { gate: true } }`.
- Produces (`MyView`): 헤더 `‹ 내 예약`(뒤로 = 최근 건물 또는 `/`) · 카드 목록(진행 중 가까운 순 → 지난 것 최근 순) · 체크인 · 취소/철회는 확인 Modal(`신청 취소` — "신청을 거두면 기록이 남지 않습니다." / `예약 취소` — "취소하면 문 앞 화면에서도 지워져요.") · 쓰기 중 그 카드 잠금 · 409/404 는 문장 + 재조회 · 60초 폴링 · `로그아웃`(ghost).

- [ ] **Step 1: 실패 테스트**

`web/src/student/__tests__/me.spec.ts`
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { ApiError, MESSAGES } from '@/api/client'
import { studentApi } from '@/api/student'
import type { ResvMineOut } from '@/api/types'
import { CHANGED_TEXT, CHECKIN_CLOSED_TEXT } from '@/components/student/rules'
import { dismissToast, toasts } from '@/components/ui/toast'
import { clearSession, session, setSession } from '@/lib/session'
import MyView from '@/student/views/MyView.vue'
import { mountAt } from './support'

vi.mock('@/api/student', () => ({
  studentApi: {
    rooms: vi.fn(),
    week: vi.fn(),
    mine: vi.fn(),
    requestResv: vi.fn(),
    cancel: vi.fn(),
    checkin: vi.fn(),
  },
}))
const api = vi.mocked(studentApi, true)
enableAutoUnmount(afterEach)

const resv = (over: Partial<ResvMineOut> = {}): ResvMineOut => ({
  id: 7,
  date: '2026-10-23',
  s_h: 10,
  s_m: 50,
  e_h: 12,
  e_m: 0,
  type: 6,
  subject: '캡스톤 스터디',
  professor: '',
  status: 'approved',
  requested_at: null,
  decided_at: null,
  reject_reason: null,
  checked_in_at: null,
  cancelled_at: null,
  room_id: 11,
  building: '공학관',
  room: 401,
  ...over,
})
const texts = () => toasts.value.map((t) => t.message)
const cards = (w: VueWrapper) => w.findAll('article')
const confirm = async (w: VueWrapper) => {
  await w.findAll('[role="dialog"] .modal__footer button')[1].trigger('click')
  await flushPromises()
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-23T01:42:00Z')) // KST 금 10:42
  localStorage.clear()
  toasts.value.forEach((t) => dismissToast(t.id))
  api.mine.mockReset()
  api.cancel.mockReset()
  api.checkin.mockReset()
})
afterEach(() => {
  vi.useRealTimers()
  clearSession()
})

describe('MyView — /me', () => {
  it('진행 중이 위 — 창 안이면 체크인, 누르면 다시 불러와 시각이 뜬다', async () => {
    const open = resv({ id: 7 })
    const rejected = resv({
      id: 9,
      date: '2026-10-20',
      status: 'rejected',
      reject_reason: '학과 행사와 겹칩니다',
    })
    const done = { ...open, checked_in_at: new Date('2026-10-23T01:42:00Z') }
    api.mine.mockResolvedValueOnce([rejected, open]).mockResolvedValue([done, rejected])
    api.checkin.mockResolvedValue(done)
    const { w } = await mountAt(MyView, '/me', '/me')
    expect(cards(w).map((c) => c.get('.badge').text())).toEqual(['승인됨', '거절됨'])
    expect(cards(w)[1].get('.mc__note').text()).toBe('사유: 학과 행사와 겹칩니다')
    await cards(w)[0].get('button').trigger('click')
    await flushPromises()
    expect(api.checkin).toHaveBeenCalledWith(7)
    expect(api.mine).toHaveBeenCalledTimes(2)
    expect(texts()).toContain('체크인했어요')
    expect(cards(w)[0].get('.mc__done').text()).toBe('✓ 10:42 체크인')
  })

  it('신청 취소 — 확인 Modal 에 "기록이 남지 않습니다", 확인하면 cancel + 재조회로 사라진다', async () => {
    const req = resv({ id: 5, status: 'requested', s_h: 14, s_m: 0, e_h: 15 })
    api.mine.mockResolvedValueOnce([req]).mockResolvedValue([])
    api.cancel.mockResolvedValue({ ...req, status: 'cancelled' })
    const { w } = await mountAt(MyView, '/me', '/me')
    await cards(w)[0].get('button').trigger('click')
    const dlg = w.get('[role="dialog"]')
    expect(dlg.get('h2').text()).toBe('신청 취소')
    expect(dlg.text()).toContain('신청을 거두면 기록이 남지 않습니다.')
    expect(api.cancel).not.toHaveBeenCalled()
    await confirm(w)
    expect(api.cancel).toHaveBeenCalledWith(5)
    expect(cards(w)).toHaveLength(0)
    expect(w.text()).toContain('아직 신청한 예약이 없어요')
  })

  it('승인 예약 취소 — 제목·문구가 다르고, 닫기면 아무것도 보내지 않는다', async () => {
    api.mine.mockResolvedValue([resv({ s_h: 11, s_m: 0 })])
    const { w } = await mountAt(MyView, '/me', '/me')
    const cancel = cards(w)[0].findAll('button').find((b) => b.text() === '취소')!
    await cancel.trigger('click')
    const dlg = w.get('[role="dialog"]')
    expect(dlg.get('h2').text()).toBe('예약 취소')
    expect(dlg.text()).toContain('취소하면 문 앞 화면에서도 지워져요.')
    await dlg.findAll('.modal__footer button')[0].trigger('click')
    expect(w.find('[role="dialog"]').exists()).toBe(false)
    expect(api.cancel).not.toHaveBeenCalled()
  })

  it('취소 경합 — 관리자가 먼저 거절했으면 409: 이유 문장 + 재조회, 버튼이 잠긴 채 남지 않는다', async () => {
    const req = resv({ id: 5, status: 'requested', s_h: 14, s_m: 0, e_h: 15 })
    api.mine
      .mockResolvedValueOnce([req])
      .mockResolvedValue([{ ...req, status: 'rejected', reject_reason: '정원 초과' }])
    api.cancel.mockRejectedValue(new ApiError(409, MESSAGES[409]))
    const { w } = await mountAt(MyView, '/me', '/me')
    await cards(w)[0].get('button').trigger('click')
    await confirm(w)
    expect(texts()).toContain(CHANGED_TEXT)
    expect(texts()).not.toContain(MESSAGES[409])
    expect(api.mine).toHaveBeenCalledTimes(2)
    expect(cards(w)[0].get('.badge').text()).toBe('거절됨')
    expect(cards(w)[0].findAll('button')).toHaveLength(0)
  })

  it('체크인 409(서버와 시계가 어긋남) — 문장 + 재조회, 버튼이 다시 눌린다', async () => {
    api.mine.mockResolvedValue([resv()])
    api.checkin.mockRejectedValue(new ApiError(409, MESSAGES[409]))
    const { w } = await mountAt(MyView, '/me', '/me')
    await cards(w)[0].get('button').trigger('click')
    await flushPromises()
    expect(texts()).toContain(CHECKIN_CLOSED_TEXT)
    expect(api.mine).toHaveBeenCalledTimes(2)
    expect((cards(w)[0].get('button').element as HTMLButtonElement).disabled).toBe(false)
  })

  it('비어 있으면 강의실 보러 가기(최근 건물로), 로그아웃은 토큰을 버린다', async () => {
    localStorage.setItem('esc.lastBld', 'E')
    setSession({ token: 't', role: 'student', school_id: 1, name: '김민준' })
    api.mine.mockResolvedValue([])
    const { w, router } = await mountAt(MyView, '/me', '/me')
    expect(w.get('a.sh__back').attributes('href')).toBe('/E')
    await w.get('.empty button').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/E')
    const logout = w.findAll('button').find((b) => b.text() === '로그아웃')!
    await logout.trigger('click')
    await flushPromises()
    expect(session.value).toBeNull()
    expect(router.currentRoute.value.path).toBe('/login')
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/student/__tests__/me.spec.ts`
Expected: FAIL — `Failed to resolve import "@/student/views/MyView.vue"`

- [ ] **Step 3: 구현**

`web/src/student/views/MyView.vue`
```vue
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError } from '@/api/client'
import { studentApi } from '@/api/student'
import type { ResvMineOut } from '@/api/types'
import MyResvCard from '@/components/student/MyResvCard.vue'
import { CHANGED_TEXT, CHECKIN_CLOSED_TEXT, sortMine } from '@/components/student/rules'
import Banner from '@/components/ui/Banner.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Modal from '@/components/ui/Modal.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import { showToast } from '@/components/ui/toast'
import { clearSession } from '@/lib/session'
import { usePolling } from '@/lib/usePolling'
import { useResource } from '@/lib/useResource'
import RefreshedNote from '../RefreshedNote.vue'
import StudentHeader from '../StudentHeader.vue'
import { POLL_MS, useNow } from '../composables'
import { lastBld } from '../favorites'

type Kind = 'checkin' | 'cancel'
const router = useRouter()
// 신청한 뒤 학생이 돌아오는 자리 — 승인·거절 알림이 없어(S10 비목표) 60초마다 다시 본다
const { data, error, refreshedAt, reload } = useResource(() => studentApi.mine())
usePolling(reload, POLL_MS)
const now = useNow()
const list = computed(() => sortMine(data.value ?? [], now.value))
const last = lastBld()
const back = last ? `/${last}` : '/'
const busy = ref<{ id: number; kind: Kind } | null>(null)
const confirming = ref<ResvMineOut | null>(null)
const withdraw = computed(() => confirming.value?.status === 'requested')

/** 쓰기 한 건 — 이중 제출 금지(busy). 409·404(그새 관리자가 처리·이미 취소)는 문장 + 재조회 */
async function run(
  r: ResvMineOut,
  kind: Kind,
  call: () => Promise<unknown>,
  ok: string,
  conflict: string,
) {
  if (busy.value) return
  busy.value = { id: r.id, kind }
  let refresh = true
  try {
    await call()
    showToast({ message: ok })
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    // 401·403 은 client 가 로그인으로 보낸다 — 부를 것이 없다
    if (e.status === 401 || e.status === 403) refresh = false
    else
      showToast({
        tone: 'danger',
        message: e.status === 409 || e.status === 404 ? conflict : e.message,
      })
  } finally {
    busy.value = null
  }
  if (refresh) await reload()
}

const checkin = (r: ResvMineOut) =>
  run(r, 'checkin', () => studentApi.checkin(r.id), '체크인했어요', CHECKIN_CLOSED_TEXT)
const askCancel = (r: ResvMineOut) => {
  confirming.value = r
}
const closeModal = () => {
  confirming.value = null
}
// 신청 취소 중 관리자가 승인했으면 서버가 승인 예약의 취소로 처리한다 — 결과가 같아 문장은 하나
async function confirmCancel() {
  const r = confirming.value
  if (!r) return
  confirming.value = null
  await run(r, 'cancel', () => studentApi.cancel(r.id), '취소했어요', CHANGED_TEXT)
}
const retry = () => void reload()
const goBack = () => void router.push(back)
function logout() {
  clearSession()
  void router.replace('/login')
}
</script>

<template>
  <div class="me">
    <StudentHeader title="내 예약" :back="back" />
    <Banner v-if="error && data" tone="danger" :message="error.message" :dismissible="false">
      <Button variant="secondary" @click="retry">다시 시도</Button>
    </Banner>
    <main class="me__body">
      <Skeleton v-if="!data && !error" :rows="4" />
      <EmptyState
        v-else-if="!data"
        message="내 예약을 불러오지 못했어요"
        :actions="[{ label: '다시 시도', variant: 'primary', onClick: retry }]"
      />
      <EmptyState
        v-else-if="!list.length"
        message="아직 신청한 예약이 없어요"
        :actions="[{ label: '강의실 보러 가기', variant: 'primary', onClick: goBack }]"
      />
      <div v-else class="me__list">
        <MyResvCard
          v-for="r in list"
          :key="r.id"
          :resv="r"
          :now="now"
          :busy="busy?.id === r.id ? busy.kind : null"
          @checkin="checkin(r)"
          @cancel="askCancel(r)"
        />
      </div>
      <RefreshedNote v-if="data" :at="refreshedAt" :epaper="false" />
      <Button variant="ghost" class="me__logout" @click="logout">로그아웃</Button>
    </main>
    <!-- 둘 다 확인을 거친다 — 신청 취소는 행이 지워진다는 것을 적는다 (student-room.md §취소와 철회) -->
    <Modal
      :open="confirming !== null"
      :title="withdraw ? '신청 취소' : '예약 취소'"
      size="sm"
      @close="closeModal"
    >
      <p class="me__confirm">
        {{ withdraw ? '신청을 거두면 기록이 남지 않습니다.' : '취소하면 문 앞 화면에서도 지워져요.' }}
      </p>
      <template #footer>
        <Button variant="secondary" @click="closeModal">닫기</Button>
        <Button variant="danger" @click="confirmCancel">{{
          withdraw ? '신청 취소' : '예약 취소'
        }}</Button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.me__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-width: 640px;
  margin: 0 auto;
  padding: var(--space-4);
}
.me__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.me__confirm {
  margin: 0;
}
.me__logout {
  align-self: center;
}
</style>
```

`web/src/student/router.ts` — `routes` 에서 `/reset` 줄 **아래**에 추가
```ts
  { path: '/me', component: () => import('./views/MyView.vue'), meta: { gate: true } },
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`
Expected: PASS — me.spec 6 tests.

- [ ] **Step 5: E2E — 내 예약**

`web/e2e/student.spec.ts`
- helpers import 줄을 바꾼다
```ts
import {
  STU,
  SIZES,
  WEB_URL,
  apiLogin,
  createStudent,
  hmOf,
  kstDate,
  kstMinutesNow,
  login,
  seedStudent,
  shot,
} from './helpers'
import cfg from './env.json' with { type: 'json' }
```
- `@playwright/test` import 에 `type APIResponse` 를 더한다.
- `const DAYS = …` 줄 **아래**에 추가
```ts
const room = (n: number) => seed.roomIds[n]
const card = (text: string) => page.getByRole('article').filter({ hasText: text })

/** 학생으로 신청 (API — 화면 밖 준비). 응답을 그대로 돌려 호출한 쪽이 상태를 본다 */
async function requestAs(
  email: string,
  roomId: number,
  date: string,
  from: string,
  to: string,
  subject: string,
) {
  const [s_h, s_m] = from.split(':').map(Number)
  const [e_h, e_m] = to.split(':').map(Number)
  return api.post(`/api/student/rooms/${roomId}/reservations`, {
    headers: { authorization: `Bearer ${await apiLogin(api, email)}` },
    data: { date, s_h, s_m, e_h, e_m, subject },
  })
}
async function created(r: APIResponse) {
  expect(r.status()).toBe(201)
  return (await r.json()) as { id: number }
}
/** 관리자 승인·거절 (F2 신청 대기 화면이 부르는 것과 같은 API) */
async function adminPost(path: string, data?: unknown) {
  const r = await api.post(path, {
    headers: { authorization: `Bearer ${await apiLogin(api, cfg.ADMINS[0])}` },
    data,
  })
  expect(r.status(), path).toBe(200)
}
```
- 파일 끝에 추가
```ts
test('내 예약 — 승인됨·대기중·거절됨, 창 안이면 체크인, 신청 취소는 기록이 남지 않는다', async () => {
  const r1 = await created(
    await requestAs(A.email, room(103), kstDate(2), '10:00', '11:00', '팀 회의'),
  )
  const r3 = await created(
    await requestAs(A.email, room(104), kstDate(3), '14:00', '15:00', '동아리'),
  )
  await adminPost(`/api/admin/reservations/${r3.id}/reject`, { reason: '학과 행사와 겹칩니다' })
  // 체크인 창 안에서 곧 시작하는 오늘 예약 — 자정 가까이는 만들 수 없어 건너뛴다(Global Constraints 시간대)
  const start = Math.ceil((kstMinutesNow() + 2) / 5) * 5
  const canCheckin = start + 15 <= 23 * 60 + 55
  if (canCheckin) {
    const r2 = await created(
      await requestAs(A.email, room(104), kstDate(0), hmOf(start), hmOf(start + 15), '스터디'),
    )
    await adminPost(`/api/admin/reservations/${r2.id}/approve`)
  }
  expect(r1.id).toBeGreaterThan(0)
  await page.getByRole('link', { name: '강의실 목록' }).click()
  await page.getByRole('link', { name: '내 예약' }).click()
  await expect(page).toHaveURL(/\/me$/)
  await expect(card('팀 회의').getByText('대기중')).toBeVisible()
  await expect(card('동아리').getByText('거절됨')).toBeVisible()
  await expect(card('동아리')).toContainText('사유: 학과 행사와 겹칩니다')
  if (canCheckin) {
    await card('스터디').getByRole('button', { name: '체크인' }).click()
    await expect(card('스터디')).toContainText(/✓ \d\d:\d\d 체크인/)
  }
  await shot(page, 'student-me-390')
  await card('팀 회의').getByRole('button', { name: '신청 취소' }).click()
  const dlg = page.getByRole('dialog', { name: '신청 취소' })
  await expect(dlg).toContainText('신청을 거두면 기록이 남지 않습니다')
  await dlg.getByRole('button', { name: '신청 취소' }).click()
  await expect(card('팀 회의')).toHaveCount(0)
})

test('승인된 예약 취소 — 확인 뒤 취소됨으로 남는다 (신청 취소와 다르다)', async () => {
  const r4 = await created(
    await requestAs(A.email, room(103), kstDate(4), '10:00', '11:00', '발표 연습'),
  )
  await adminPost(`/api/admin/reservations/${r4.id}/approve`)
  // /me 는 60초마다 — 기다리지 않고 한 번 나갔다 온다
  await page.getByRole('link', { name: '뒤로' }).click()
  await expect(page).toHaveURL(new RegExp(`/${STU.bld}$`))
  await page.getByRole('link', { name: '내 예약' }).click()
  await expect(card('발표 연습').getByText('승인됨')).toBeVisible()
  await expect(card('발표 연습').getByRole('button', { name: '체크인' })).toBeDisabled()
  await expect(card('발표 연습')).toContainText('09:50부터 체크인할 수 있어요')
  await card('발표 연습').getByRole('button', { name: '취소', exact: true }).click()
  const dlg = page.getByRole('dialog', { name: '예약 취소' })
  await expect(dlg).toContainText('취소하면 문 앞 화면에서도 지워져요')
  await dlg.getByRole('button', { name: '예약 취소' }).click()
  await expect(card('발표 연습').getByText('취소됨')).toBeVisible()
  await expect(card('발표 연습').getByRole('button')).toHaveCount(0)
})
```

Run: E2E 명령 끝에 ` e2e/student.spec.ts`
Expected: 9 passed. `student-me-390.png` 를 `student-room.md` §내 예약과 대조 — 카드마다 상태 배지(승인됨만 `room.busy` 틴트, 대기중·거절됨은 무채색 outline) · `인문관 NNN호` · `M/D 요일 HH:MM–HH:MM` · 목적 · 거절 사유 본문 · 체크인은 창 안에서만 채워진 버튼, 창 밖은 disabled + `HH:MM부터 체크인할 수 있어요` · `✓ HH:MM 체크인` · 버튼 48px.

- [ ] **Step 6: 커밋**

```bash
git add web/src/student web/e2e/student.spec.ts
git commit -m "feat(web): 학생 내 예약 — 상태 다섯, 체크인 창, 신청 취소와 취소를 확인 뒤, 경합은 문장+재조회"
```

---

### Task 13: `/:bld/:room/reserve` 예약 신청 + E2E

**Files:**
- Modify: `web/src/student/router.ts`, `web/e2e/student.spec.ts`
- Create: `web/src/student/views/ReserveView.vue`
- Test: `web/src/student/__tests__/reserve.spec.ts`

**Interfaces:**
- Consumes: `studentApi.requestResv`·`mine`(Task 1), rules(Task 2: `activeCount`·`MAX_ACTIVE`·`FULL_TEXT`·`CAP_TEXT`·`DAILY_TEXT`·`TAKEN_TEXT`·`STALE_TEXT`), `ReserveSheet`(Task 7), `useRoomWeek`(Task 11), 셸(Task 9: `StudentHeader`·`NotFoundView`), `mountAt`·`roomState`(Task 10 support), F1 `useResource`·`showToast`·`ApiError`.
- Produces (라우트): `/:bld` 의 자식 `:room(\\d+)/reserve` → ReserveView.
- Produces (`ReserveView`): 헤더 `✕ 공학관 401호 예약`(`aria-label="닫기"` → `/{bld}/{room}`) · ReserveSheet(`days` = `week.free`, `full` = `week.full`, `myFutureCount` = 진행 중 수) · 제출 성공 → Toast + `/me` · 409 → 주간 재조회 후 `full` 이면 `FULL_TEXT`, 아니면 `TAKEN_TEXT` · 429 → `DAILY_TEXT` + 이 화면에서 잠금 · 400 → 주간·내 예약 재조회 후 3건이면 `CAP_TEXT`, 아니면 `STALE_TEXT` · 404 → 재조회(404 화면) · 그 밖 `MESSAGES` · 폴링 없음.

- [ ] **Step 1: 실패 테스트**

`web/src/student/__tests__/reserve.spec.ts`
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { ApiError, MESSAGES } from '@/api/client'
import { studentApi } from '@/api/student'
import type { ResvMineOut, WeekOut } from '@/api/types'
import week from '@/api/__fixtures__/week.json'
import {
  CAP_TEXT,
  DAILY_TEXT,
  FULL_TEXT,
  STALE_TEXT,
  TAKEN_TEXT,
} from '@/components/student/rules'
import { dismissToast, toasts } from '@/components/ui/toast'
import ReserveView from '@/student/views/ReserveView.vue'
import { mountAt, roomState } from './support'

vi.mock('@/api/student', () => ({
  studentApi: {
    rooms: vi.fn(),
    week: vi.fn(),
    mine: vi.fn(),
    requestResv: vi.fn(),
    cancel: vi.fn(),
    checkin: vi.fn(),
  },
}))
const api = vi.mocked(studentApi, true)
enableAutoUnmount(afterEach)

const WEEK = week as WeekOut
const ROOMS = [roomState({ room_id: 11, room: 401 })]
const PATH = ['/E/401/reserve', '/:bld/:room/reserve'] as const
const mineResv = (over: Partial<ResvMineOut>): ResvMineOut => ({
  id: 1,
  date: '2026-10-24',
  s_h: 10,
  s_m: 0,
  e_h: 11,
  e_m: 0,
  type: 6,
  subject: '스터디',
  professor: '',
  status: 'requested',
  requested_at: null,
  decided_at: null,
  reject_reason: null,
  checked_in_at: null,
  cancelled_at: null,
  room_id: 11,
  building: '공학관',
  room: 401,
  ...over,
})
const THREE = [
  mineResv({ id: 1 }),
  mineResv({ id: 2, s_h: 12, e_h: 13 }),
  mineResv({ id: 3, s_h: 14, e_h: 15 }),
]
const texts = () => toasts.value.map((t) => t.message)
const submitBtn = (w: VueWrapper) => w.get<HTMLButtonElement>('button[type="submit"]')
/** 오늘(10-23) 첫 구간 13:00–15:00 → 13:00–14:00, 목적 '스터디' 로 제출 */
async function fillAndSubmit(w: VueWrapper) {
  await w.findAll('input[type="radio"]')[0].setValue()
  await w.get('.field__control').setValue('스터디')
  await w.get('form').trigger('submit')
  await flushPromises()
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-23T01:42:00Z')) // KST 금 10:42
  toasts.value.forEach((t) => dismissToast(t.id))
  api.week.mockReset().mockResolvedValue(WEEK)
  api.mine.mockReset().mockResolvedValue([])
  api.requestResv.mockReset()
})
afterEach(() => vi.useRealTimers())

describe('ReserveView — /:bld/:room/reserve', () => {
  it('신청 — 서버 모양으로 한 번, 성공하면 Toast 와 /me', async () => {
    api.requestResv.mockResolvedValue(mineResv({ date: '2026-10-23', s_h: 13, e_h: 14 }))
    const { w, router } = await mountAt(ReserveView, ...PATH, ROOMS)
    expect(w.get('h1').text()).toBe('공학관 401호 예약')
    const close = w.get('a.sh__back')
    expect(close.attributes('aria-label')).toBe('닫기')
    expect(close.attributes('href')).toBe('/E/401')
    await fillAndSubmit(w)
    expect(api.requestResv).toHaveBeenCalledWith(11, {
      date: '2026-10-23',
      s_h: 13,
      s_m: 0,
      e_h: 14,
      e_m: 0,
      subject: '스터디',
    })
    expect(texts()).toContain('예약을 신청했어요. 관리자 승인 뒤 확정돼요.')
    expect(router.currentRoute.value.path).toBe('/me')
  })

  it('409 — 재조회한 full 이 false 면 먼저 신청한 사람, 사라진 구간은 선택이 풀린다', async () => {
    api.requestResv.mockRejectedValue(new ApiError(409, MESSAGES[409]))
    const taken: WeekOut = {
      ...WEEK,
      free: WEEK.free.map((d) =>
        d.date === '2026-10-23' ? { ...d, spans: [{ from: '16:00', to: '21:00' }] } : d,
      ),
    }
    api.week.mockResolvedValueOnce(WEEK).mockResolvedValue(taken)
    const { w, router } = await mountAt(ReserveView, ...PATH, ROOMS)
    await fillAndSubmit(w)
    expect(texts()).toEqual([TAKEN_TEXT])
    expect(api.week).toHaveBeenCalledTimes(2)
    expect(router.currentRoute.value.path).toBe('/E/401/reserve')
    expect(w.findAll('.rs__span .num').map((s) => s.text())).toEqual(['16:00 – 21:00'])
    expect(submitBtn(w).element.disabled).toBe(true)
  })

  it('409 — 재조회한 full 이 true 면 방이 찼다', async () => {
    api.requestResv.mockRejectedValue(new ApiError(409, MESSAGES[409]))
    api.week
      .mockResolvedValueOnce(WEEK)
      .mockResolvedValue({ ...WEEK, full: true, free: WEEK.free.map((d) => ({ ...d, spans: [] })) })
    const { w } = await mountAt(ReserveView, ...PATH, ROOMS)
    await fillAndSubmit(w)
    expect(texts()).toEqual([FULL_TEXT])
    expect(w.get('.rs__blocker').text()).toBe(FULL_TEXT)
  })

  it('429 — Toast 뒤 이 화면에 있는 동안 잠금 (하루 상한 — 10초 뒤 풀어도 또 429)', async () => {
    api.requestResv.mockRejectedValue(new ApiError(429, MESSAGES[429]))
    const { w } = await mountAt(ReserveView, ...PATH, ROOMS)
    await fillAndSubmit(w)
    expect(texts()).toEqual([DAILY_TEXT])
    expect(w.get('.rs__blocker').text()).toBe(DAILY_TEXT)
    expect(submitBtn(w).element.disabled).toBe(true)
  })

  it('400 — 재조회해 진행 중이 3건이면 CAP, 아니면 STALE', async () => {
    api.requestResv.mockRejectedValue(new ApiError(400, MESSAGES[400]))
    api.mine.mockResolvedValueOnce([]).mockResolvedValue(THREE)
    const cap = await mountAt(ReserveView, ...PATH, ROOMS)
    await fillAndSubmit(cap.w)
    expect(texts()).toEqual([CAP_TEXT])
    expect(cap.w.get('.rs__blocker').text()).toBe(CAP_TEXT)
    toasts.value.forEach((t) => dismissToast(t.id))
    api.mine.mockReset().mockResolvedValue([])
    const stale = await mountAt(ReserveView, ...PATH, ROOMS)
    await fillAndSubmit(stale.w)
    expect(texts()).toEqual([STALE_TEXT])
  })

  it('이미 진행 중 3건이면 처음부터 잠겨 있다', async () => {
    api.mine.mockResolvedValue(THREE)
    const { w } = await mountAt(ReserveView, ...PATH, ROOMS)
    expect(w.get('.rs__blocker').text()).toBe(CAP_TEXT)
  })

  it('두 번 눌러도 한 번 — 응답을 기다리는 동안 loading', async () => {
    let resolve!: (v: ResvMineOut) => void
    api.requestResv.mockReturnValue(
      new Promise<ResvMineOut>((r) => {
        resolve = r
      }),
    )
    const { w } = await mountAt(ReserveView, ...PATH, ROOMS)
    await fillAndSubmit(w)
    await w.get('form').trigger('submit')
    expect(api.requestResv).toHaveBeenCalledTimes(1)
    expect(submitBtn(w).attributes('aria-busy')).toBe('true')
    resolve(mineResv({}))
    await flushPromises()
  })

  it('그새 예약을 받지 않게 된 방(404) — 404 화면', async () => {
    api.requestResv.mockRejectedValue(new ApiError(404, MESSAGES[404]))
    api.week.mockResolvedValueOnce(WEEK).mockRejectedValue(new ApiError(404, MESSAGES[404]))
    const { w } = await mountAt(ReserveView, ...PATH, ROOMS)
    await fillAndSubmit(w)
    expect(w.get('h2').text()).toBe('찾을 수 없는 주소예요')
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/student/__tests__/reserve.spec.ts`
Expected: FAIL — `Failed to resolve import "@/student/views/ReserveView.vue"`

- [ ] **Step 3: 구현**

`web/src/student/views/ReserveView.vue`
```vue
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError } from '@/api/client'
import { studentApi } from '@/api/student'
import type { StudentResvIn } from '@/api/types'
import ReserveSheet from '@/components/student/ReserveSheet.vue'
import {
  CAP_TEXT,
  DAILY_TEXT,
  FULL_TEXT,
  MAX_ACTIVE,
  STALE_TEXT,
  TAKEN_TEXT,
  activeCount,
} from '@/components/student/rules'
import EmptyState from '@/components/ui/EmptyState.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import { showToast } from '@/components/ui/toast'
import { useResource } from '@/lib/useResource'
import StudentHeader from '../StudentHeader.vue'
import { useRoomWeek } from '../building'
import NotFoundView from './NotFoundView.vue'

const router = useRouter()
// 신청 화면은 폴링하지 않는다 — 고른 구간이 60초마다 흔들리지 않게. 제출 오류 때만 재조회 (설계 판정)
const { bld, roomNo, room, now, notFound, title, week, weekError, reload } = useRoomWeek({
  poll: false,
})
const { data: mine, reload: reloadMine } = useResource(() => studentApi.mine())
const count = computed(() => activeCount(mine.value ?? [], now.value))
const submitting = ref(false)
/** 하루 10회(429) — 이 화면에 있는 동안 잠근다 */
const locked = ref(false)

async function submit(body: StudentResvIn) {
  if (submitting.value || !room.value) return // 이중 제출 — 버튼 loading 과 같은 선
  submitting.value = true
  try {
    await studentApi.requestResv(room.value.room_id, body)
    showToast({ message: '예약을 신청했어요. 관리자 승인 뒤 확정돼요.' })
    await router.push('/me')
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    await explain(e)
  } finally {
    submitting.value = false
  }
}

/** 서버 원문 대신 이유를 말하고, 고를 거리를 새로 불러온다 (student-room.md §화면이 거는 제약) */
async function explain(e: ApiError) {
  // 401·403 은 client 가 로그인으로 보낸다 — 입력은 되살리지 않는다(F1·auth.md)
  if (e.status === 401 || e.status === 403) return
  if (e.status === 429) {
    locked.value = true
    showToast({ tone: 'danger', message: DAILY_TEXT })
  } else if (e.status === 409) {
    // 겹침(누가 먼저)과 가득(24건)이 둘 다 409 — 원문 대신 재조회한 full 로 가른다
    await reload()
    showToast({ tone: 'danger', message: week.value?.full ? FULL_TEXT : TAKEN_TEXT })
  } else if (e.status === 400) {
    // 창 밖·지난 시각·진행 중 3건이 400 — 3건인지는 내 예약으로 안다
    await Promise.all([reload(), reloadMine()])
    showToast({ tone: 'danger', message: count.value >= MAX_ACTIVE ? CAP_TEXT : STALE_TEXT })
  } else if (e.status === 404) {
    await reload() // 그새 예약을 받지 않게 된 방 — 주간도 404 → 404 화면
  } else {
    showToast({ tone: 'danger', message: e.message })
  }
}
const retry = () => void reload()
</script>

<template>
  <NotFoundView v-if="notFound" :back="`/${bld}`" back-label="강의실 목록으로" />
  <div v-else class="reserve">
    <StudentHeader
      :title="`${title} 예약`"
      :back="`/${bld}/${roomNo}`"
      back-label="닫기"
      back-text="✕"
    />
    <Skeleton v-if="!week && !weekError" :rows="4" />
    <EmptyState
      v-else-if="!week"
      message="비어 있는 시간을 불러오지 못했어요"
      :actions="[{ label: '다시 시도', variant: 'primary', onClick: retry }]"
    />
    <ReserveSheet
      v-else
      :days="week.free"
      :now="now"
      :my-future-count="count"
      :full="week.full"
      :locked="locked"
      :submitting="submitting"
      @submit="submit"
    />
  </div>
</template>

<style scoped>
.reserve {
  min-height: 100vh;
  background: var(--surface);
}
</style>
```

`web/src/student/router.ts` — `/:bld([A-Z])` 의 `children` 배열 끝에 추가
```ts
      { path: ':room(\\d+)/reserve', component: () => import('./views/ReserveView.vue') },
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint && pnpm exec prettier --check . && pnpm build`
Expected: PASS — reserve.spec 8 tests, 전체 테스트·빌드 통과.

- [ ] **Step 5: E2E — 예약 신청 · 경합 · 상한**

`web/e2e/student.spec.ts`
- `let seed: …` 줄 **아래**에 추가
```ts
let B: { email: string }
```
- 파일 끝에 추가
```ts
test('예약 — 날짜 칩 8개, 서버가 준 빈 구간만, 신청하면 내 예약에 대기중', async () => {
  await page.getByRole('link', { name: '뒤로' }).click()
  await shownRows().filter({ hasText: '102호' }).getByRole('link').click() // ★ 칩(102호)과 겹치지 않게 목록 행으로
  await page.getByRole('link', { name: '이 강의실 예약하기' }).click()
  await expect(page).toHaveURL(new RegExp(`/${STU.bld}/102/reserve$`))
  await expect(page.getByRole('link', { name: '닫기' })).toHaveAttribute('href', `/${STU.bld}/102`)
  const chips = page.getByRole('radiogroup', { name: '날짜' }).getByRole('radio')
  await expect(chips).toHaveCount(8)
  await expect(chips.first()).toContainText('오늘')
  expect((await chips.nth(1).boundingBox())!.height).toBeGreaterThanOrEqual(48)
  await chips.nth(1).click()
  await expect(chips.nth(1)).toHaveAttribute('aria-checked', 'true')
  await page.getByRole('radio', { name: /^09:00 – 21:00/ }).check()
  await page.getByLabel('시작', { exact: true }).selectOption({ label: '10:00' })
  await page.getByLabel('끝', { exact: true }).selectOption({ label: '11:00' })
  await page.getByLabel(/무엇에 쓰나요/).fill('캡스톤 스터디')
  await expect(page.getByText('19 / 20 B')).toBeVisible()
  await expect(page.getByText('문 앞 화면에는 "학생 예약"으로만 표시돼요')).toBeVisible()
  await shot(page, 'student-reserve-390')
  await page.getByRole('button', { name: '예약하기' }).click()
  await expect(page).toHaveURL(/\/me$/)
  await expect(card('캡스톤 스터디').getByText('대기중')).toBeVisible()
})

test('경합 — 고르는 사이 남이 먼저 신청하면 409 문장 + 빈 구간 새로 고침, 남의 이름은 없다', async () => {
  B = await createStudent(api, { approve: true, name: '박학생' })
  await page.getByRole('link', { name: '뒤로' }).click()
  await shownRows().filter({ hasText: '102호' }).getByRole('link').click() // ★ 칩(102호)과 겹치지 않게 목록 행으로
  await page.getByRole('link', { name: '이 강의실 예약하기' }).click()
  await page.getByRole('radiogroup', { name: '날짜' }).getByRole('radio').nth(1).click()
  await page.getByRole('radio', { name: /^11:00 – 21:00/ }).check()
  await page.getByLabel('시작', { exact: true }).selectOption({ label: '11:00' })
  await page.getByLabel('끝', { exact: true }).selectOption({ label: '12:00' })
  await page.getByLabel(/무엇에 쓰나요/).fill('세미나 준비')
  await created(await requestAs(B.email, room(102), kstDate(1), '11:00', '12:00', '먼저 온 사람'))
  await page.getByRole('button', { name: '예약하기' }).click()
  await expect(
    page.getByText('방금 다른 사람이 먼저 신청했어요. 비어 있는 시간을 새로 불러왔어요.'),
  ).toBeVisible()
  await expect(page).toHaveURL(/\/reserve$/)
  await expect(page.getByRole('radio', { name: /^12:00 – 21:00/ })).toBeVisible()
  await expect(page.getByRole('radio', { name: /^11:00 – 21:00/ })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '예약하기' })).toBeDisabled()
  await expect(page.getByText('먼저 온 사람')).toHaveCount(0)
  await expect(page.getByText('박학생')).toHaveCount(0)
  await shot(page, 'student-reserve-taken-390')
})

test('건수 상한 — 진행 중 신청 3건이면 버튼을 잠그고 이유를 말한다', async () => {
  // 서버가 3건째 뒤를 400 으로 막을 때까지 채운다 — 체크인 예약을 건너뛴 날에도 같은 결과
  for (let i = 5; i <= 7; i++) {
    const r = await requestAs(A.email, room(103), kstDate(i), '10:00', '11:00', `연습 ${i}`)
    if (r.status() === 400) break
    expect(r.status()).toBe(201)
  }
  // 신청 화면은 폴링하지 않는다 — 한 번 닫았다 연다
  await page.getByRole('link', { name: '닫기' }).click()
  await page.getByRole('link', { name: '이 강의실 예약하기' }).click()
  await expect(page.getByText('신청은 3건까지 할 수 있어요')).toBeVisible()
  await expect(page.getByRole('button', { name: '예약하기' })).toBeDisabled()
})
```

Run: E2E 명령 끝에 ` e2e/student.spec.ts`, 이어서 전체 `pnpm e2e`
Expected: student.spec 12 passed, 전체 통과(F1~F3 spec 그대로 — `login` 의 ready 기본값이 `nav`). 스크린샷 대조 — `student-reserve-390`: 헤더 `✕ 인문관 102호 예약` · `날짜 · 오늘부터 7일까지` + 52px 칩 8개(오늘 포함, 고른 칩 `brand`) · `비어 있는 시간 · M월 D일 요일` + 52px 구간 행(시간 길이 오른쪽) · `시작`/`끝` Select 48px · `무엇에 쓰나요 *` + `19 / 20 B` · `예약하면 관리자 승인 뒤 확정돼요` · 하단 고정 `M월 D일 요일 10:00–11:00 [예약하기]`. `student-reserve-taken-390`: danger Toast 문장 · 사라진 구간 없음 · 버튼 disabled.

- [ ] **Step 6: 커밋**

```bash
git add web/src/student web/e2e/student.spec.ts
git commit -m "feat(web): 학생 예약 신청 — 서버 빈 구간만, 409 는 재조회한 full 로 문장을 가르고 429 는 이 화면에서 잠금"
```

---

## 자체 점검 (plan 작성 뒤)

1. **spec 범위 → Task**: student-room.md 라우트 여섯(`/{bld}` T10 · `/{bld}/{room}` T11 · `/week` T11 · `/reserve` T13 · `/me` T12 · 인증 F1) + `/` 첫 진입(T10) · 404·소문자(T9) · 즐겨찾기·최근 건물(T3·T10·T11) · 로그인 벽(T9) · 컴포넌트 여섯(T5·T6·T7·T8) · 넓은 폭(T10 CSS·T11) · 상태(로딩 Skeleton·빈 상태·에러 Banner·갱신 줄·60초·숨김 정지 — T9·T10~T12) · 겹침 합치기(서버 A3 → T4·T6) · 남의 예약 `예약됨`(서버 label 그대로 T4·T6, E2E T13) · 제약 여덟(T7·T13) · 상태 다섯·체크인·취소/철회(T2·T8·T12). spec §8 예외: 토큰 만료(F1 공통 + T13 `401·403 은 되살리지 않는다`) · 새로고침(메모리 세션 → 벽 → `next`) · 늦은 응답(`useResource`) · 숨김(`usePolling`) · 끊김(T10) · 연타(T7·T13) · 예약 가능한 방 0(T10 HomeView).
2. **금지 패턴**: "TBD"·"TODO"·"나중에"·"적절한"·"Task N 과 같이" 없음(검색). 모든 코드 단계는 전체 코드.
3. **이름·시그니처 일치**: `studentApi.{rooms,week,requestResv,mine,cancel,checkin}`(T1) · `RESV_MINE_DATES` · rules 이름(T2 Produces 목록 = T5~T13 import) · `GridBlock`·`GridRange`(T4 → T6·T11) · `BUILDING`·`useBuilding`(T10) → `useRoomWeek`·`useWeekGrid`(T11 파일 교체 — T10 의 세 이름 유지) · `mountAt(component, path, pattern, rooms?)`·`roomState`·`stubMedia`(T10 support → T11~T13) · E2E `login(page, email, ready)`·`seedStudent`·`STU`·`kstMinutesNow`·`hmOf`(T10) · `requestAs`·`created`·`adminPost`·`card`·`room`(T12 → T13).
4. **Review Focus 고정 테스트**: 1 → T7 `재조회로 고른 구간이…`·T13 `409 — 재조회한 full…`·E2E `경합` / 2 → T7 `막는 이유…`·T13 `429…`·`400…`·E2E `건수 상한` / 3 → T2 `체크인 창…`·`취소…`·T8·T12 `취소 경합…`·`체크인 409…` / 4 → T3 `localStorage 가 막혀도…`·`깨진 값…` / 5 → T9 `5분이 지나면…`·T10 `조회 실패…`·`첫 조회가 실패하면…`.
5. **열린 질문(mh·서버)**: 넓은 폭 하루 열 200px 이상 → 120px(판정 표) · Badge `brand` solid 조합(student-room.md 근거) · 학생 컴포넌트 여섯의 `components.md` 이관(spec §3.3) · 넓은 폭 `오늘` 교수 열에 필요한 `BusySpan.professor`(서버 additive, 필요 시).
