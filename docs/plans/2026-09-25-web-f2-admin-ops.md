# 웹 F2 — 관리자 운영 (건물·강의실 · 강의실 설정 · 주간 시간표) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 관리자 `건물 · 강의실`(`/admin/master`), `강의실 설정`(`/admin/rooms` — 시간표·예약·신청 대기·시험기간·CSV·동기화), `주간 시간표`(`/admin/rooms/:roomId/week`) 세 화면과 그 도메인 컴포넌트(TypeBadge·SourceBadge·RoomTree·SlotForm·ResvForm·ExamForm)를 만들고, 저장 뒤 OutboxDot 30초 추적과 F1 이월 두 건(거절 사유 툴팁·Button 진행 라벨 폭)을 더해 Playwright 로 실제 브라우저에서 확인한다.

**Architecture:** F1·F3 의 `api/client.ts`·`useResource`·`usePolling`·ui 컴포넌트 위에 올린다. 서버 계약은 `api/rooms.ts`(`roomsApi`) 한 곳, 도메인 규칙(바이트 상한·7일 창·겹침·층·409 문장)은 `components/domain/rules.ts` 한 곳이다 — 폼 세 개(SlotForm·ResvForm·ExamForm)가 검증과 저장 호출을 스스로 지고, 표(페이지1)와 격자(페이지2)는 같은 폼을 연다. 화면 계산(트리·배치·묶기)은 `*.ts` 순수 함수로 떼어 단위 테스트하고, `.vue` 는 그리기와 이벤트만 한다.

**Tech Stack:** Vue 3.5 · vue-router 4.5 · Vite 7 · TypeScript 5.9 · Vitest 3 + @vue/test-utils + jsdom · @playwright/test 1.63 · pnpm (새 의존성 없음)

**Spec:** `docs/specs/2026-09-25-web-frontend-design.md` §3.3·§4·§5·§6(F2)·§8 (+ 화면 원본 `docs/design/screens/admin-master.md`(#46 — 사이드 메뉴 순서)·`admin-rooms.md`·`admin-schedule.md`, `components.md` §Button·§Table·§OutboxDot·§TypeBadge·§SourceBadge·§RoomTree·§SlotForm·§ResvForm·§ExamForm, `tokens.md` §outbox·§room). 서버 계약: `server/app/domain/router.py`·`admin_resv_router.py`·`app/schemas.py` (S2·S4b·S10 + web additive A1·A2).

**브랜치:** `feature/web-f2` ← `feature/web-f3` (워크트리는 컨트롤러가 만든다). F3 의 `api/admin.ts`·`api/lora.ts`·`OutboxDot`·`NodeStateBadge`·`nodesView.ts`·`kstDateStr`·E2E 하네스(`WEB_URL`·`sql()`·`OTHER_ADMIN`)를 그대로 쓴다.

## Global Constraints

- 작업 위치: `web/` 만. 서버·`docs/design/` 은 읽기만 한다.
- pnpm 만. **새 의존성 없음** — 날짜 피커·드롭다운·폼·격자 라이브러리 금지. 날짜는 `<input type="date">`, 시각은 `<input type="time">`, 선택은 네이티브 `<select>`.
- 응답 타입은 `src/api/types.ts` 에 **한 번만**, 서버 스키마 이름 그대로(`SchoolOut`·`BuildingOut`·`RoomOut`·`SlotOut`·`SlotWithRoom`·`ResvWithRoom`·`ResvAdminOut`·`ExamOut`·`ExamWithRoom`·`ImportSummary`·`ImportErrors`). `*_at` 만 `*_DATES` 로 `Date` 변환, `date`·`date_start`·`date_end` 는 KST 달력 문자열 `'YYYY-MM-DD'` 그대로.
- 서버 오류 원문을 화면에 내지 않는다 — 409 는 `conflictMessage`(Task 2), 나머지는 `MESSAGES`(F1) 또는 이 plan 의 한국어 문장. **예외 하나:** CSV 검증 실패 표의 `errors[].error`(행 단위 검증 사유 — `admin-rooms.md` "행 번호와 사유").
- 판정을 화면이 다시 하지 않는다: 노드 상태는 `NodeOut.warnings`, 층은 `room // 100`(100 미만 `기타`), 7일 창은 KST 오늘 기준 `오늘 ≤ date ≤ 오늘+7`.
- `subject`·`professor` 는 **UTF-8 바이트** 상한 20·12 (`lora_proto` `LP_SUBJ_MAX`/`LP_PROF_MAX`) — Input `maxBytes` 로.
- 예약·시험기간 `id` 는 **서버가 채번**한다(S4b §2.5) — 추가할 때 `id` 를 보내지 않고, 수정만 기존 `id` 로 다시 POST.
- 위험 동작(삭제·거절·유닛 축소)은 확인 Modal 안에서만 `danger` Button. 표의 행 동작은 `ghost`.
- `.vue` 의 `<style>`·`<template>` 에 1층 팔레트(`--gray-` 등)·16진 색 금지(F1 `tokens.guard.spec.ts`).
- 사이드 메뉴 순서(#46): `건물 · 강의실` · `강의실 설정` · `주간 시간표` · `노드 상태` · `전송 현황` · `회원`. 관리자 기본 라우트는 `/dashboard` 그대로(F3·spec §5).
- 커밋: `feat(web): …` / `style(web): …`(ui) / `test(web): …`. **Claude·AI 저작 표기와 `Co-Authored-By` 트레일러 금지.**
- 매 Task 끝에 `cd web && pnpm test && pnpm lint && pnpm typecheck && pnpm exec prettier --check .` 통과. 새 파일은 `pnpm exec prettier --write <파일>` 로 정리하고, CRLF 만 바뀐 파일은 커밋하지 않는다.
- **E2E 명령**(PowerShell — 통합 서버 워크트리에 A1~A3 이 머지돼 있어야 한다, 컨트롤러가 준비):
  ```powershell
  cd web
  $env:E2E_SERVER_DIR = 'C:\Users\Monta\AppData\Local\Temp\claude\C--Users-Monta-Desktop-Woo-ESC-Capston\4e11f262-c2d8-493c-87cf-4b4412c9a3ef\scratchpad\srv-wt\server'
  $env:E2E_API_PORT = '8100'
  $env:E2E_WEB_PORT = '5273'
  pnpm e2e
  ```
  파일 하나만 돌릴 때는 끝에 ` e2e/admin-ops.spec.ts`.
- 화면 Task 완료 조건: E2E 통과 + 1440×900 스크린샷을 `web/e2e/.shots/` 에 남기고 화면 스펙 수치와 대조(스크린샷은 커밋하지 않는다 — PR 에 첨부).

## Review Focus

테스트가 직접 겨누지 않으면 사람이 가장 먼저 밟을 입력·상황 다섯. 각 줄의 고정 테스트는 담당 Task 에 있다.

1. 건물 이름만 고치러 들어와 모뎀 드롭다운을 잘못 건드림 → 저장 전에 확인 Modal, 본문에 **대기 건수 숫자**. 이름만 바꾸면 묻지 않는다. — Task 11 `모뎀이 바뀌면 대기 건수로 확인…`·`이름만 바꾸면 묻지 않는다` + E2E `모뎀을 바꾸면…`
2. 시간표 슬롯의 시작 시각을 09:00 → 13:00 으로 고쳐 저장 → 옛 09:00 행이 남지 않는다(PUT 은 키로 찾는다). 옛 행 지우기가 실패해도 새 행은 남는다. — Task 6 `키가 바뀌면 새 행을 먼저 넣고 옛 행을 지운다`·`옛 행 지우기 실패…` + Task 14 E2E
3. 8일 뒤 예약 저장 → 실패가 아니라 `예정` 배지(툴팁 "7일 이내로 들어오면 자동 전송됩니다"), 폼에서도 저장 전에 같은 문구. — Task 7 `7일 밖이면 저장 전에 hint 로 알리고 막지 않는다…` + Task 15 `resvDot — 창 밖이고 노드에 안 간 것…`·E2E `예약 — 7일 안은 대기 점, 7일 밖은 예정 배지…`
4. 두 관리자가 같은 학생 신청을 동시에 승인 → 늦은 쪽은 409 문장 "이미 처리된 신청입니다." + 목록 새로 고침, 행 버튼이 잠긴 채 남지 않는다. — Task 15 `409 — 다른 관리자가 먼저 처리: 문장·재조회, 버튼이 잠긴 채 남지 않는다` + E2E `신청 대기 — 오래된 순, … 다른 관리자가 먼저 처리하면 409 문장 …`
5. 시험기간 7곳 적용 중 2곳 실패 → 되돌리지 않고 Toast "7개 중 5개 적용 · 402호, 405호 실패" + 실패분만 `재시도`. 진행 라벨("3/7 적용 중")이 바뀌어도 버튼 폭이 흔들리지 않는다. — Task 8 `일부 실패 — 되돌리지 않고…`·`진행 라벨 — 한 곳이 끝날 때마다 n/3…` + Task 3 Button `loadingLabel — 진행도를 보이고…`

## 설계 판정 (디자인 미결·문서끼리 어긋난 곳)

| 항목 | 판정 | 근거 |
|---|---|---|
| ResvForm·ExamForm 의 id 채번(`components.md` "화면이 채번") | **서버 채번** — 추가는 `id` 없이, 수정만 기존 `id` | `admin-rooms.md` §3(S4b §2.5)이 나중 결정. `components.md` 가 옛 판 |
| ExamForm 의 강의실 다중 선택 Checkbox(`components.md`) | 폼에 강의실 목록 없음 — **트리에서 고른 방이 대상**(`rooms` prop), 폼은 시작일·종료일만 | `admin-rooms.md` §시험기간("폼 안에 강의실 목록을 따로 두지 않는다") |
| 시험기간 일부 실패의 `재시도` 자리("표에서") | **Toast 의 `재시도`**(실패한 방만 다시) | 실패한 방은 표에 행이 없다 — 행에 붙일 곳이 없다 |
| 슬롯 키 변경 "삭제 후 추가" | **새 행 PUT 먼저, 그다음 옛 행 DELETE** — 사용자에게 알리지 않는 것은 그대로 | 삭제 먼저면 추가 실패 시 데이터가 사라진다. 순서를 바꾸면 최악이 "중복 한 줄"(보이고 지울 수 있다) |
| 슬롯 수정 시 `source` | `max(2, 원래 source)` — 포털(1)→수동(2), **긴급(3)은 3 유지** | 3 슬롯에 2 를 보내면 서버 409 |
| 예약 폼 겹침 | 같은 방·같은 날 `approved`·`requested` 예약과 겹치면 막는다. **슬롯과의 겹침은 막지 않는다** | 휴강 위 특강처럼 의도된 겹침이 있고, 페이지2가 겹침을 보여 주려고 있는 화면이다 |
| 오늘 이전 날짜 예약 | 막는다 | 노드로 가지 않고 04:00 작업이 지운다 — 만들 이유가 없다 |
| 예약 수정에서 강의실 변경 | 잠금(hint "다른 강의실로 옮기려면 지우고 다시 만드세요") | 서버가 다른 방 id 는 409 |
| 학생이 신청해 승인된 예약의 행 동작 | `수정`·`삭제` 대신 **`취소`**(`POST /api/admin/reservations/{id}/cancel`) | DELETE 는 흔적 없이 지워 학생 화면에서 예약이 그냥 사라진다. 취소는 학생에게 `취소됨`으로 보인다 |
| 신청 대기 블록의 범위 | **학교 전체**(트리 선택과 무관), 호수 칸에 `공학관 401` | 처리해야 할 일 목록이다. 트리 밖 신청이 숨으면 방치된다 |
| 페이지1 첫 진입 선택 | 선택이 비어 있으면 **첫 건물의 첫 층** | 빈 화면보다 낫고, 건물 전체(142행)보다 가볍다(`admin-rooms.md` "층이나 강의실 몇 개만 고르는 것이 기본") |
| 여러 건물에 걸친 선택 | 호수 칸·폼 강의실 목록에 건물 글자(`K 101`) | 같은 호수가 두 건물에 있으면 구분이 안 된다 |
| 건물 `미배정` 배지(`danger` 틴트) | `danger` + `outline` | Badge 에 `danger`+`tint` 조합이 없다(F1 — 표의 네 조합만). mh 확인 요청 |
| 강의실 행 42px(`admin-master.md`) | Table `tall`(44px) | Table 의 높이는 32·44 둘(`components.md` "두 줄 셀이 있으면 44px"). 건물 행 44 와 맞춘다. mh 확인 요청 |
| 건물 삭제 잠금 이유 "옆에 적는다" | 비활성 `삭제` 버튼을 감싼 `title` 툴팁 | 작업 칸 92px 에 문장이 안 들어간다 |
| 사이드바 학교 표시 `우송대 · net_id 75 · wsu.ac.kr` | `우송대 · net_id 75` + `학교는 CLI 에서만 만든다` | `SchoolOut` 에 `email_domain` 이 없다. 필요하면 서버 additive |
| 마스터 노드 컬럼 `48시간 넘게 보고 없음` | `응답 없음`(F3 `WARNING_LABEL.unseen`) | F3: 48 h 를 화면에 적지 않는다(판정은 서버). 같은 상태를 화면마다 다른 말로 부르지 않는다 |
| 유닛 입력(`components.md` 목록은 Checkbox) | Select(1 · 2) | 값이 1/2 둘이다 |
| 다른 건물이 쓰는 모뎀 | 고를 수 있다, 라벨 `m1 · 공학관 사용 중` | 서버가 막지 않고, 모뎀Pi 하나가 이웃 건물을 맡을 수 있다. 라벨이 실수를 막는다 |
| 범위로 추가 상한 | 한 번에 100곳 | `1–9999` 를 잘못 넣으면 9999번 POST 가 나간다 |
| 페이지2 열 구분선 `gray.50` | `line.1` | 토큰 가드(1층 금지), `gray.50` 을 가리키는 선 토큰이 없다 |
| 페이지2 격자 시작 | 09:00, 단 그보다 이른 블록이 있으면 그 시각(30분 내림)부터 | 07:30 수업이 화면에 없으면 편집할 길이 없다 |
| 페이지2 편집 범위 | 슬롯(SlotForm) + **승인 예약 클릭 → ResvForm**. 시험기간 편집·`하루 비우기` 버튼은 두지 않는다 | 화면 스펙에 없다. 같은 폼 컴포넌트라 비용이 없는 예약만 더했다 |
| 페이지2 겹침 표시 | 같은 무리의 블록을 lane 으로 균등 분할(1/n). `danger` 막대는 **둘 다 점유**(사용중 슬롯·approved)일 때만 | 휴강 위 예약·신청과의 겹침은 충돌이 아니다. 3개 이상(미결 1)은 1/3 폭으로 그대로 그린다 |
| OutboxDot `cancelled` 툴팁 | `취소됨` → `취소됨 — 노드에 반영 안 됨` | `admin-rooms.md`·`admin-schedule.md` |
| OutboxDot 추적 | 저장 응답 `outbox_ids` 를 건물 outbox(`limit=500`)에서 3초마다 찾아 30초 동안. 끝나면 마지막 상태로 둔다 | spec §4.3. 새로고침하면 끊긴다(합의) |
| `예정` 배지 | 추적 중이 아니고 `pushed_at == null` 이고 날짜가 오늘+7 뒤 | A2 `pushed_at`. 지난 날짜는 아무것도 그리지 않는다 |
| CSV 가져오기 뒤 OutboxDot | 행 단위로 추적하지 않는다 — Toast 에 강의실 수 | 서버가 방마다 FILE 하나를 보낸다(행과 1:1 이 아니다) |
| `선택한 곳 동기화` | 확인 없이 보내고 결과 Toast | 파괴적이지 않다. 라벨이 범위를 말한다 |
| `주간 시간표` 메뉴 링크 | 마지막으로 본 강의실. 없으면 `/week` → 트리 선택의 첫 방 → 첫 강의실 | 메뉴 항목에 `:roomId` 를 둘 수 없다 |
| 버튼 색 — "화면당 채워진 brand 하나" | 마스터: `+ 강의실` 만 primary. 페이지1: 화면 스펙대로 각 블록의 추가 버튼 primary | 화면 스펙이 컴포넌트 일반 규칙보다 구체적이다. mh 확인 요청 |

## 파일 지도

```
web/
├── e2e/
│   ├── helpers.ts                 + ensureModems · OPS · seedOps · kstDate
│   ├── admin-ops.spec.ts          건물·강의실 · 강의실 설정 · 주간 시간표 · 다른 학교 (우리·다른 학교 로그인 각 1회)
│   └── admin-users.spec.ts        거절 사유 툴팁 한 줄 (Task 19)
└── src/
    ├── api/
    │   ├── types.ts               + SchoolOut … ImportErrors, UserOut.reject_reason
    │   ├── client.ts              + RequestOpts.contentType (CSV 본문 그대로)
    │   ├── rooms.ts               roomsApi — 건물·강의실·시간표·예약·시험기간·건물 단위 조회·CSV
    │   ├── admin.ts               + pendingResv · approveResv · rejectResv · cancelResv
    │   └── __fixtures__/          building-resv · pending-resv · import-errors (.json)
    ├── lib/time.ts                + addDays · dayOfDate · mondayOf · hm · md
    ├── components/
    │   ├── ui/Button.vue          loadingLabel 폭 미리 잡기
    │   ├── ui/Table.vue           tall (행 44px)
    │   └── domain/
    │       ├── rules.ts           상한·요일·유형·출처·겹침·7일 창·층·키·409 문장
    │       ├── TypeBadge.vue · SourceBadge.vue
    │       ├── roomTree.ts · RoomTree.vue
    │       ├── slotForm.ts · SlotForm.vue
    │       ├── resvForm.ts · ResvForm.vue
    │       ├── ExamForm.vue
    │       └── OutboxDot.vue      취소 문구
    └── admin/
        ├── router.ts · AdminShell.vue   라우트 4 · 메뉴 3 · 학교 표시
        ├── selection.ts           트리 선택 · 주간 보기 상태 (모듈 메모리 — 새로고침이면 사라짐)
        ├── outboxTrack.ts         저장 뒤 30초 추적
        ├── ConfirmModal.vue
        ├── masterView.ts · roomsView.ts · weekView.ts   (순수 함수)
        └── views/
            ├── MasterView.vue · master/{BuildingPanel,RoomPanel,RangeAddModal}.vue
            ├── RoomsView.vue · rooms/{RowDot,SlotBlock,ResvBlock,PendingBlock,ExamBlock,CsvImport}.vue
            ├── WeekView.vue
            └── UsersView.vue      거절 사유 툴팁
```

## Task 순서와 의존

| Task | 내용 | 의존 |
|---|---|---|
| 1 | api — F2 타입 · `roomsApi` · 신청 API · CSV 본문 | — |
| 2 | 달력 헬퍼 · 도메인 규칙(`rules.ts`) | 1 |
| 3 | ui — Button 진행 라벨 폭 · Table `tall` · OutboxDot 취소 문구 | — |
| 4 | domain — TypeBadge · SourceBadge | 2 |
| 5 | domain — RoomTree | 2 |
| 6 | domain — SlotForm | 1, 2 |
| 7 | domain — ResvForm | 1, 2 |
| 8 | domain — ExamForm | 1, 2, 3 |
| 9 | admin — 저장 뒤 OutboxDot 추적 · 선택 상태 | 1, 2 |
| 10 | admin — ConfirmModal · 마스터 순수 함수 | 1 |
| 11 | 건물 · 강의실 A — 화면 · 건물 패널 · 메뉴 · 학교 표시 + E2E | 3, 10 |
| 12 | 건물 · 강의실 B — 강의실 표 · 학생 예약 즉시 저장 · 유닛 축소 · 삭제 개수 + E2E | 11 |
| 13 | 건물 · 강의실 C — 범위로 추가 + E2E | 12 |
| 14 | 강의실 설정 A — 트리 바 · 시간표 블록 · 추적 · 재전송 + E2E | 4, 5, 6, 9 |
| 15 | 강의실 설정 B — 예약 블록 · 신청 대기 + E2E | 7, 14 |
| 16 | 강의실 설정 C — 시험기간 · CSV · 선택한 곳 동기화 + E2E | 8, 15 |
| 17 | 주간 시간표 — 배치 계산(`weekView.ts`) | 2 |
| 18 | 주간 시간표 — 화면 · 편집 · 메뉴 + E2E | 5, 6, 7, 9, 14, 17 |
| 19 | 회원 거절 사유 툴팁 (F1 Task 14 이월, 서버 A1) | 1 |

---

### Task 1: api — F2 타입 · `roomsApi` · 신청 API · CSV 본문

**Files:**
- Modify: `web/src/api/types.ts`, `web/src/api/client.ts`, `web/src/api/admin.ts`
- Create: `web/src/api/rooms.ts`, `web/src/api/__fixtures__/{building-resv,pending-resv,import-errors}.json`
- Test: `web/src/api/__tests__/rooms.spec.ts`

**Interfaces:**
- Consumes: `request<T>(method, path, body?, opts?)`·`ApiError`(F1), `OUTBOX_DATES`·`FailedOut`·`Enqueued`·`OutboxState`(F3 Task 2).
- Produces (`types.ts`): `SchoolOut` · `BuildingIn` · `BuildingOut` · `BuildingPatch` · `RoomIn` · `RoomOut` · `RoomPatch` · `SlotType = 1|2|3|4|5|6` · `SlotSource = 1|2|3` · `SlotIn` · `SlotOut` · `SlotWithRoom` · `ResvStatus` · `ResvIn` · `ResvOut` · `RequesterOut` · `ResvWithRoom` + `RESV_DATES` · `ResvAdminOut` + `RESV_ADMIN_DATES` · `ExamIn` · `ExamOut` · `ExamWithRoom` · `ImportSkipped` · `ImportSummary` · `ImportRowError` · `ImportErrors`.
- Produces (`client.ts`): `RequestOpts.contentType?: string` — 있으면 본문을 JSON 으로 바꾸지 않고 그대로, 그 content-type 으로.
- Produces (`rooms.ts`): `IMPORT_MAX_BYTES = 1_048_576` · `roomsApi.{schools, buildings, createBuilding, patchBuilding, deleteBuilding, rooms, createRoom, patchRoom, deleteRoom, buildingSlots, buildingResv, buildingExams, buildingOutbox, slots, putSlot, deleteSlot, reservations, saveResv, deleteResv, exams, saveExam, deleteExam, importSlots}` (시그니처는 아래 코드).
- Produces (`admin.ts`): `adminApi.pendingResv(): Promise<ResvAdminOut[]>` · `approveResv(id: number)` · `rejectResv(id: number, reason: string)` · `cancelResv(id: number)` — 셋 다 `Promise<ResvAdminOut>`.

- [ ] **Step 1: 픽스처 (서버 응답 모양 그대로)**

`web/src/api/__fixtures__/building-resv.json`
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
    "room_id": 11,
    "requester": { "email": "s1@wsu.ac.kr", "name": "김민준", "student_no": "20231234" },
    "pushed_at": "2026-10-20T01:00:00.500000"
  },
  {
    "id": 8,
    "date": "2026-11-20",
    "s_h": 13,
    "s_m": 0,
    "e_h": 15,
    "e_m": 0,
    "type": 5,
    "subject": "신입생 오리엔테이션",
    "professor": "학생처",
    "status": "approved",
    "room_id": 12,
    "requester": null,
    "pushed_at": null
  }
]
```

`web/src/api/__fixtures__/pending-resv.json`
```json
[
  {
    "id": 9,
    "date": "2026-10-24",
    "s_h": 14,
    "s_m": 0,
    "e_h": 16,
    "e_m": 0,
    "type": 6,
    "subject": "스터디",
    "professor": "",
    "status": "requested",
    "requested_at": "2026-10-23T05:00:00",
    "decided_at": null,
    "reject_reason": null,
    "checked_in_at": null,
    "cancelled_at": null,
    "room_id": 11,
    "building": "공학관",
    "room": 401,
    "requester": { "email": "s1@wsu.ac.kr", "name": "김민준", "student_no": "20231234" },
    "pushed_at": null
  }
]
```

`web/src/api/__fixtures__/import-errors.json`
```json
{ "errors": [{ "row": 2, "error": "room: 999 없음 (우송대 K)" }] }
```

- [ ] **Step 2: 실패 테스트**

`web/src/api/__tests__/rooms.spec.ts`
```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { roomsApi } from '@/api/rooms'
import { adminApi } from '@/api/admin'
import { ApiError } from '@/api/client'
import { clearSession } from '@/lib/session'
import buildingResv from '@/api/__fixtures__/building-resv.json'
import pendingResv from '@/api/__fixtures__/pending-resv.json'
import importErrors from '@/api/__fixtures__/import-errors.json'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
const fetchMock = vi.fn<typeof fetch>()
const call = (i = 0) => ({ url: fetchMock.mock.calls[i][0], init: fetchMock.mock.calls[i][1]! })
const header = (i: number, k: string) => (call(i).init.headers as Record<string, string>)[k]

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  clearSession()
})

describe('roomsApi', () => {
  it('건물 추가는 BuildingIn 그대로, 수정은 보낸 필드만 (modem_id null = 배정 해제)', async () => {
    fetchMock.mockImplementation(async () =>
      json({ id: 3, school_id: 1, name: '공학관', bld: 'E', modem_id: null }),
    )
    await roomsApi.createBuilding({ school_id: 1, name: '공학관', bld: 'E', modem_id: null })
    await roomsApi.patchBuilding(3, { modem_id: null })
    expect(call(0).url).toBe('/api/buildings')
    expect(call(0).init.body).toBe('{"school_id":1,"name":"공학관","bld":"E","modem_id":null}')
    expect(call(1).url).toBe('/api/buildings/3')
    expect(call(1).init.method).toBe('PATCH')
    expect(call(1).init.body).toBe('{"modem_id":null}')
  })

  it('강의실 부분 수정 — reservable 만 보낸다 (다른 탭의 units 를 덮지 않게)', async () => {
    fetchMock.mockResolvedValue(json({ id: 11, building_id: 3, room: 401, units: 2, reservable: true }))
    await roomsApi.patchRoom(11, { reservable: true })
    expect(call().url).toBe('/api/rooms/11')
    expect(call().init.body).toBe('{"reservable":true}')
  })

  it('건물 예약 — pushed_at 만 Date, date 는 달력 문자열 그대로, requester null 그대로', async () => {
    fetchMock.mockResolvedValue(json(buildingResv))
    const out = await roomsApi.buildingResv(3)
    expect(call().url).toBe('/api/buildings/3/reservations')
    expect(out[0].pushed_at!.toISOString()).toBe('2026-10-20T01:00:00.500Z')
    expect(out[0].date).toBe('2026-10-24')
    expect(out[0].requester?.name).toBe('김민준')
    expect(out[1].pushed_at).toBeNull()
    expect(out[1].requester).toBeNull()
  })

  it('건물 outbox — state·limit 쿼리', async () => {
    fetchMock.mockImplementation(async () => json([]))
    await roomsApi.buildingOutbox(3, 'queued')
    await roomsApi.buildingOutbox(3)
    expect(call(0).url).toBe('/api/buildings/3/outbox?state=queued&limit=500')
    expect(call(1).url).toBe('/api/buildings/3/outbox?limit=500')
  })

  it('슬롯 삭제는 키 경로, 예약 추가는 id 없이 (서버 채번) — 응답 id 를 돌려준다', async () => {
    fetchMock.mockImplementation(async () => json({ outbox_ids: [5], id: 12 }))
    await roomsApi.deleteSlot(11, { day: 1, s_h: 9, s_m: 0 })
    const out = await roomsApi.saveResv(11, {
      date: '2026-10-24',
      s_h: 10,
      s_m: 0,
      e_h: 12,
      e_m: 0,
      type: 5,
      subject: 'OT',
      professor: '학생처',
    })
    expect(call(0).url).toBe('/api/rooms/11/slots/1/9/0')
    expect(call(0).init.method).toBe('DELETE')
    expect(call(1).url).toBe('/api/rooms/11/reservations')
    expect(JSON.parse(call(1).init.body as string)).not.toHaveProperty('id')
    expect(out.id).toBe(12)
  })

  it('CSV — 본문을 바이트 그대로 text/csv, dry_run 쿼리', async () => {
    fetchMock.mockResolvedValue(
      json({ rooms: 1, added: 2, updated: 0, deleted: 0, skipped: [], outbox_ids: [] }),
    )
    const bytes = new TextEncoder().encode('school,building\n').buffer
    await roomsApi.importSlots(bytes, true)
    expect(call().url).toBe('/api/import/slots?dry_run=true')
    expect(call().init.method).toBe('POST')
    expect(header(0, 'content-type')).toBe('text/csv')
    expect(call().init.body).toBe(bytes)
  })

  it('CSV 검증 실패 400 — errors[] 는 ApiError.detail 로 온다 (화면이 표로 그린다)', async () => {
    fetchMock.mockResolvedValue(json(importErrors, 400))
    const e = (await roomsApi.importSlots(new ArrayBuffer(0), false).catch((x) => x)) as ApiError
    expect(e).toBeInstanceOf(ApiError)
    expect(e.status).toBe(400)
    expect((e.detail as typeof importErrors).errors[0]).toEqual({
      row: 2,
      error: 'room: 999 없음 (우송대 K)',
    })
  })
})

describe('adminApi — 신청', () => {
  it('신청 대기 — status=requested, requested_at Date', async () => {
    fetchMock.mockResolvedValue(json(pendingResv))
    const out = await adminApi.pendingResv()
    expect(call().url).toBe('/api/admin/reservations?status=requested')
    expect(out[0].requested_at!.toISOString()).toBe('2026-10-23T05:00:00.000Z')
    expect(out[0].building).toBe('공학관')
    expect(out[0].room).toBe(401)
  })

  it('승인·거절·취소 — 경로와 본문', async () => {
    fetchMock.mockImplementation(async () => json(pendingResv[0]))
    await adminApi.approveResv(9)
    await adminApi.rejectResv(9, '겹치는 수업이 있습니다')
    await adminApi.cancelResv(9)
    expect(call(0).url).toBe('/api/admin/reservations/9/approve')
    expect(call(0).init.body).toBeUndefined()
    expect(call(1).url).toBe('/api/admin/reservations/9/reject')
    expect(call(1).init.body).toBe('{"reason":"겹치는 수업이 있습니다"}')
    expect(call(2).url).toBe('/api/admin/reservations/9/cancel')
  })
})
```

- [ ] **Step 3: 실패 확인**

Run: `cd web && pnpm test src/api/__tests__/rooms.spec.ts`
Expected: FAIL — `Failed to resolve import "@/api/rooms"`

- [ ] **Step 4: 구현**

`web/src/api/types.ts` 끝에 추가
```ts
// ---- F2 관리자 운영 — S2(건물·강의실·시간표), S4b(건물 단위 조회·서버 채번), S10(신청), web A2 ----

export interface SchoolOut {
  id: number
  name: string
  net_id: number
}
export interface BuildingIn {
  school_id: number
  name: string
  /** 대문자 한 글자 — 무선 주소라 학교가 달라도 겹칠 수 없다 (409) */
  bld: string
  modem_id: string | null
}
export interface BuildingOut extends BuildingIn {
  id: number
}
/** 부분 수정 — 보낸 필드만 바뀐다. modem_id: null = 배정 해제 */
export interface BuildingPatch {
  name?: string
  bld?: string
  modem_id?: string | null
}
export interface RoomIn {
  building_id: number
  room: number
  units: number
  reservable: boolean
}
export interface RoomOut extends RoomIn {
  id: number
}
/** 호수(room)는 무선 주소라 화면이 보내지 않는다 (admin-master.md — 수정 폼에서 잠금) */
export interface RoomPatch {
  units?: number
  reservable?: boolean
}
/** 1 수업 · 2 시험 · 3 휴강 · 4 빈강의실 · 5 특강 · 6 대여 (lora_proto LP_SLOTTYPE_*) */
export type SlotType = 1 | 2 | 3 | 4 | 5 | 6
/** 1 포털(CSV) · 2 수동(웹) · 3 긴급 — 낮은 출처는 높은 출처를 덮지 못한다 (409) */
export type SlotSource = 1 | 2 | 3
export interface SlotIn {
  day: number
  s_h: number
  s_m: number
  e_h: number
  e_m: number
  type: SlotType
  subject: string
  professor: string
  source: SlotSource
}
export interface SlotOut extends SlotIn {
  id: number
}
export interface SlotWithRoom extends SlotOut {
  room_id: number
}
export type ResvStatus = 'requested' | 'approved' | 'rejected' | 'cancelled' | 'expired'
/** id 를 빼면 서버가 채번한다 (S4b §2.5). date 는 KST 달력 'YYYY-MM-DD' — Date 로 바꾸지 않는다 */
export interface ResvIn {
  id?: number
  date: string
  s_h: number
  s_m: number
  e_h: number
  e_m: number
  type: SlotType
  subject: string
  professor: string
}
export interface ResvOut extends ResvIn {
  id: number
  status: ResvStatus
}
export interface RequesterOut {
  email: string
  name: string
  student_no: string | null
}
/** 건물·방 예약 목록 (web A2) — requester 는 학생 신청만, pushed_at null = 노드에 없음 */
export interface ResvWithRoom extends ResvOut {
  room_id: number
  requester: RequesterOut | null
  pushed_at: Date | null
}
export const RESV_DATES = ['pushed_at'] as const
/** 관리자 신청 목록·승인·거절·취소 응답 (S10 §4.2 + web A2) */
export interface ResvAdminOut extends ResvOut {
  requested_at: Date | null
  decided_at: Date | null
  reject_reason: string | null
  checked_in_at: Date | null
  cancelled_at: Date | null
  room_id: number
  building: string
  room: number
  requester: RequesterOut | null
  pushed_at: Date | null
}
export const RESV_ADMIN_DATES = [
  'requested_at',
  'decided_at',
  'checked_in_at',
  'cancelled_at',
  'pushed_at',
] as const
export interface ExamIn {
  id?: number
  date_start: string
  date_end: string
}
export interface ExamOut extends ExamIn {
  id: number
}
export interface ExamWithRoom extends ExamOut {
  room_id: number
}
export interface ImportSkipped {
  row: number
  reason: string
}
export interface ImportSummary {
  rooms: number
  added: number
  updated: number
  deleted: number
  skipped: ImportSkipped[]
  outbox_ids: number[]
}
export interface ImportRowError {
  row: number
  error: string
}
export interface ImportErrors {
  errors: ImportRowError[]
}
```

`web/src/api/client.ts` — `RequestOpts` 를 통째로 바꾼다
```ts
export interface RequestOpts {
  auth?: boolean
  dates?: readonly string[]
  signal?: AbortSignal
  /** 본문을 JSON 으로 바꾸지 않고 그대로 보낸다 — CSV 업로드(`text/csv`) */
  contentType?: string
}
```
`request` 안의 `if (body !== undefined) headers['content-type'] = 'application/json'` 줄을 바꾼다
```ts
  if (body !== undefined) headers['content-type'] = opts.contentType ?? 'application/json'
```
`fetch(path, { … })` 안의 `body: body === undefined ? undefined : JSON.stringify(body),` 줄을 바꾼다
```ts
        body:
          body === undefined
            ? undefined
            : opts.contentType
              ? (body as BodyInit)
              : JSON.stringify(body),
```

`web/src/api/rooms.ts`
```ts
import { request } from './client'
import {
  OUTBOX_DATES,
  RESV_DATES,
  type BuildingIn,
  type BuildingOut,
  type BuildingPatch,
  type Enqueued,
  type ExamIn,
  type ExamOut,
  type ExamWithRoom,
  type FailedOut,
  type ImportSummary,
  type OutboxState,
  type ResvIn,
  type ResvWithRoom,
  type RoomIn,
  type RoomOut,
  type RoomPatch,
  type SchoolOut,
  type SlotIn,
  type SlotOut,
  type SlotWithRoom,
} from './types'

/** 서버 IMPORT_MAX_BYTES — 넘으면 413. 화면이 먼저 막는다 */
export const IMPORT_MAX_BYTES = 1024 * 1024

type SlotKeyParts = { day: number; s_h: number; s_m: number }
const resv = { dates: RESV_DATES }

// 전부 관리자 + 학교 스코프 (S4a §3.2) — 다른 학교 자원은 403 이 아니라 404
export const roomsApi = {
  /** 내 학교 하나 — 생성·삭제는 CLI 전용 */
  schools: () => request<SchoolOut[]>('GET', '/api/schools'),

  buildings: () => request<BuildingOut[]>('GET', '/api/buildings'),
  createBuilding: (b: BuildingIn) => request<BuildingOut>('POST', '/api/buildings', b),
  patchBuilding: (id: number, p: BuildingPatch) =>
    request<BuildingOut>('PATCH', `/api/buildings/${id}`, p),
  /** 강의실이 남아 있으면 409 (CASCADE 없음) */
  deleteBuilding: (id: number) => request<{ ok: boolean }>('DELETE', `/api/buildings/${id}`),

  /** 필터 파라미터가 없다 — 전체를 받아 building_id 로 거른다 */
  rooms: () => request<RoomOut[]>('GET', '/api/rooms'),
  createRoom: (r: RoomIn) => request<RoomOut>('POST', '/api/rooms', r),
  patchRoom: (id: number, p: RoomPatch) => request<RoomOut>('PATCH', `/api/rooms/${id}`, p),
  /** 시간표·예약·시험기간이 CASCADE 로 함께 지워진다 */
  deleteRoom: (id: number) => request<{ ok: boolean }>('DELETE', `/api/rooms/${id}`),

  // 건물 단위 조회 (S4b §2.6) — 쓰기는 /rooms/{id}/… 그대로
  buildingSlots: (id: number) => request<SlotWithRoom[]>('GET', `/api/buildings/${id}/slots`),
  buildingResv: (id: number) =>
    request<ResvWithRoom[]>('GET', `/api/buildings/${id}/reservations`, undefined, resv),
  buildingExams: (id: number) => request<ExamWithRoom[]>('GET', `/api/buildings/${id}/exams`),
  /** 최신 순 500건 — 저장 뒤 OutboxDot 추적과 모뎀 변경 확인(대기 건수)이 쓴다 */
  buildingOutbox: (id: number, state?: OutboxState) =>
    request<FailedOut[]>(
      'GET',
      `/api/buildings/${id}/outbox?${state ? `state=${state}&` : ''}limit=500`,
      undefined,
      { dates: OUTBOX_DATES },
    ),

  slots: (roomId: number) => request<SlotOut[]>('GET', `/api/rooms/${roomId}/slots`),
  /** 키 = day+s_h+s_m. 같은 키면 수정, 아니면 추가 — 벌크가 아니다 */
  putSlot: (roomId: number, s: SlotIn) => request<Enqueued>('PUT', `/api/rooms/${roomId}/slots`, s),
  deleteSlot: (roomId: number, k: SlotKeyParts) =>
    request<Enqueued>('DELETE', `/api/rooms/${roomId}/slots/${k.day}/${k.s_h}/${k.s_m}`),

  reservations: (roomId: number) =>
    request<ResvWithRoom[]>('GET', `/api/rooms/${roomId}/reservations`, undefined, resv),
  /** id 없음 = 추가(서버 채번, 응답 id), id 있음 = 같은 방이면 수정 · 다른 방이면 409 */
  saveResv: (roomId: number, r: ResvIn) =>
    request<Enqueued>('POST', `/api/rooms/${roomId}/reservations`, r),
  deleteResv: (roomId: number, id: number) =>
    request<Enqueued>('DELETE', `/api/rooms/${roomId}/reservations/${id}`),

  exams: (roomId: number) => request<ExamOut[]>('GET', `/api/rooms/${roomId}/exams`),
  saveExam: (roomId: number, e: ExamIn) =>
    request<Enqueued>('POST', `/api/rooms/${roomId}/exams`, e),
  deleteExam: (roomId: number, id: number) =>
    request<Enqueued>('DELETE', `/api/rooms/${roomId}/exams/${id}`),

  /** 본문 = CSV 파일 바이트 그대로 (UTF-8 이 아니면 서버가 400 — 화면에서 디코딩하지 않는다) */
  importSlots: (csv: ArrayBuffer, dryRun: boolean) =>
    request<ImportSummary>('POST', `/api/import/slots?dry_run=${dryRun}`, csv, {
      contentType: 'text/csv',
    }),
}
```

`web/src/api/admin.ts` — import 목록에 `RESV_ADMIN_DATES` 와 `type ResvAdminOut` 을 더하고, `adminApi` 객체의 `latency` 항목 **뒤**에 추가
```ts
  /** 학생 신청 대기 — 학교 전체. 서버는 날짜순, '오래된 신청 먼저' 정렬은 화면이 */
  pendingResv: () =>
    request<ResvAdminOut[]>('GET', '/api/admin/reservations?status=requested', undefined, {
      dates: RESV_ADMIN_DATES,
    }),
  /** 겹침·용량(24)·시작 시각을 다시 본다 — 어긋나면 409 */
  approveResv: (id: number) =>
    request<ResvAdminOut>('POST', `/api/admin/reservations/${id}/approve`, undefined, {
      dates: RESV_ADMIN_DATES,
    }),
  /** 사유(1~200자)는 학생에게 그대로 보인다 */
  rejectResv: (id: number, reason: string) =>
    request<ResvAdminOut>(
      'POST',
      `/api/admin/reservations/${id}/reject`,
      { reason },
      { dates: RESV_ADMIN_DATES },
    ),
  /** 승인된 예약을 cancelled 로 — 행을 지우지 않아 학생 화면에 '취소됨'으로 남는다 */
  cancelResv: (id: number) =>
    request<ResvAdminOut>('POST', `/api/admin/reservations/${id}/cancel`, undefined, {
      dates: RESV_ADMIN_DATES,
    }),
```

- [ ] **Step 5: 통과 확인**

Run: `cd web && pnpm test src/api && pnpm typecheck && pnpm lint`
Expected: PASS — rooms.spec 9 tests, F1 `client.spec`·F3 `monitor.spec` 그대로(`contentType` 이 없으면 동작이 같다).

- [ ] **Step 6: 커밋**

```bash
git add web/src/api
git commit -m "feat(web): F2 응답 타입과 roomsApi — 건물·강의실·시간표·예약·시험기간·건물 단위 조회·CSV, 관리자 신청 승인·거절·취소"
```

---

### Task 2: 달력 헬퍼 · 도메인 규칙(`rules.ts`)

**Files:**
- Modify: `web/src/lib/time.ts`
- Create: `web/src/components/domain/rules.ts`
- Test: `web/src/lib/__tests__/calendar.spec.ts`, `web/src/components/domain/__tests__/rules.spec.ts`

**Interfaces:**
- Consumes: `ApiError`·`MESSAGES`(F1), `SlotType`·`SlotSource`(Task 1).
- Produces (`lib/time.ts`): `addDays(d: string, n: number): string` · `dayOfDate(d: string): number`(1=월…7=일) · `mondayOf(d: string): string` · `hm(h: number, m: number): string`(`'09:05'`) · `md(d: string): string`(`'10/5'`).
- Produces (`rules.ts`): `SUBJ_MAX = 20` · `PROF_MAX = 12` · `RESV_HORIZON_DAYS = 7` · `DAYS` · `DAY_OPTIONS` · `TYPE_LABEL` · `TYPE_OPTIONS` · `BUSY_TYPES` · `SOURCE_LABEL` · `interface Span` · `toMin(h, m)` · `spansOverlap(a: Span, b: Span): boolean` · `type ResvWindow = 'past'|'in'|'later'` · `resvWindow(date: string, today: string): ResvWindow` · `LATER_HINT` · `floorOf(room: number): number | null` · `floorLabel(room: number): string` · `interface SavedRow { roomId: number; key: string; outboxIds: number[] }` · `slotKey(s: { room_id; day; s_h; s_m }): string` · `resvKey(id: number)` · `examKey(id: number)` · `detailText(e: ApiError): string` · `conflictMessage(e: ApiError): string`.

- [ ] **Step 1: 실패 테스트**

`web/src/lib/__tests__/calendar.spec.ts`
```ts
import { describe, expect, it } from 'vitest'
import { addDays, dayOfDate, hm, md, mondayOf } from '@/lib/time'

describe('달력 날짜 (서버 date 필드 — KST 달력 문자열, 시간대 없이 센다)', () => {
  it('addDays — 달·해·윤년 경계', () => {
    expect(addDays('2026-09-28', 7)).toBe('2026-10-05')
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01')
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28')
    expect(addDays('2028-02-28', 1)).toBe('2028-02-29')
  })
  it('dayOfDate — 1=월 … 7=일 (SlotIn.day 와 같다)', () => {
    expect(dayOfDate('2026-09-21')).toBe(1)
    expect(dayOfDate('2026-09-25')).toBe(5)
    expect(dayOfDate('2026-09-27')).toBe(7)
  })
  it('mondayOf — 일요일은 그 전 월요일, 주가 달을 넘어도', () => {
    expect(mondayOf('2026-09-27')).toBe('2026-09-21')
    expect(mondayOf('2026-10-01')).toBe('2026-09-28')
    expect(mondayOf('2026-09-21')).toBe('2026-09-21')
  })
  it('hm · md', () => {
    expect(hm(9, 5)).toBe('09:05')
    expect(hm(21, 30)).toBe('21:30')
    expect(md('2026-10-05')).toBe('10/5')
  })
})
```

`web/src/components/domain/__tests__/rules.spec.ts`
```ts
import { describe, expect, it } from 'vitest'
import { ApiError, MESSAGES } from '@/api/client'
import {
  conflictMessage,
  examKey,
  floorLabel,
  floorOf,
  resvKey,
  resvWindow,
  slotKey,
  spansOverlap,
} from '@/components/domain/rules'

const span = (s: string, e: string) => {
  const [sh, sm] = s.split(':').map(Number)
  const [eh, em] = e.split(':').map(Number)
  return { s_h: sh, s_m: sm, e_h: eh, e_m: em }
}
const e409 = (detail: string) => new ApiError(409, MESSAGES[409], [], { detail })

describe('rules', () => {
  it('spansOverlap — 걸치면 겹침, 끝이 맞닿으면 아님', () => {
    expect(spansOverlap(span('09:00', '11:00'), span('10:00', '12:00'))).toBe(true)
    expect(spansOverlap(span('09:00', '12:00'), span('10:00', '11:00'))).toBe(true)
    expect(spansOverlap(span('09:00', '10:00'), span('10:00', '11:00'))).toBe(false)
  })

  it('resvWindow — 오늘~+7 은 in, 그 뒤 later(창 밖 — 실패 아님), 어제는 past', () => {
    expect(resvWindow('2026-09-24', '2026-09-25')).toBe('past')
    expect(resvWindow('2026-09-25', '2026-09-25')).toBe('in')
    expect(resvWindow('2026-10-02', '2026-09-25')).toBe('in')
    expect(resvWindow('2026-10-03', '2026-09-25')).toBe('later')
  })

  it('층은 호수 ÷ 100, 100 미만은 기타', () => {
    expect(floorOf(401)).toBe(4)
    expect(floorLabel(401)).toBe('4층')
    expect(floorLabel(1203)).toBe('12층')
    expect(floorOf(5)).toBeNull()
    expect(floorLabel(5)).toBe('기타')
  })

  it('행 키 — 슬롯은 방+요일+시작, 예약·시험기간은 서버 id', () => {
    expect(slotKey({ room_id: 11, day: 1, s_h: 9, s_m: 0 })).toBe('s11-1-9-0')
    expect(resvKey(7)).toBe('r7')
    expect(examKey(7)).toBe('x7')
  })

  it('409 원문을 사람 문장으로 — 모르는 409 는 공통 문장', () => {
    expect(conflictMessage(e409('source 2 슬롯은 source ≥ 2 로만 수정'))).toBe(
      '이 슬롯은 웹에서 수정된 행입니다. CSV로 덮어쓸 수 없습니다.',
    )
    expect(conflictMessage(e409('이 강의실은 이번 주 예약이 가득 찼습니다(노드 용량 24)'))).toBe(
      '이 강의실은 7일 안 예약이 가득 찼습니다(24건). 지난 예약을 정리하세요.',
    )
    expect(conflictMessage(e409('id 소진 — 지난 예약·시험기간을 정리하세요'))).toBe(
      'id 소진 — 지난 예약·시험기간을 정리하세요',
    )
    expect(
      conflictMessage(e409('id 가 다른 방의 것입니다 — 방을 옮기려면 삭제 후 다시 만드세요')),
    ).toBe('다른 강의실의 항목입니다. 목록을 새로 불러옵니다.')
    expect(conflictMessage(e409('신청 상태 예약은 승인 절차로 처리하세요'))).toBe(
      '학생 신청은 신청 대기에서 승인·거절로 처리하세요.',
    )
    expect(conflictMessage(e409('이미 시작 시각이 지난 신청입니다'))).toBe(
      '이미 시작 시각이 지난 신청입니다.',
    )
    expect(conflictMessage(e409('그 시간에 다른 예약·수업이 생겼습니다'))).toBe(
      '그 시간에 다른 예약이나 수업이 생겨 승인할 수 없습니다.',
    )
    expect(conflictMessage(e409('approved 상태에서는 불가'))).toBe('이미 처리된 신청입니다.')
    expect(conflictMessage(e409('constraint violation'))).toBe(MESSAGES[409])
    expect(conflictMessage(new ApiError(409, MESSAGES[409]))).toBe(MESSAGES[409])
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/lib/__tests__/calendar.spec.ts src/components/domain/__tests__/rules.spec.ts`
Expected: FAIL — `"addDays" is not exported` / `Failed to resolve import "@/components/domain/rules"`

- [ ] **Step 3: 구현**

`web/src/lib/time.ts` 끝에 추가
```ts
// ---- 달력 날짜 'YYYY-MM-DD' — 서버 date 필드(KST 달력)를 시간대 없이 센다 (F2) ----
const DAY_MS = 86_400_000
const asUtc = (d: string) => Date.parse(`${d}T00:00:00Z`)

/** 'YYYY-MM-DD' + n일 — 달·해 경계를 넘는다 */
export function addDays(d: string, n: number): string {
  return new Date(asUtc(d) + n * DAY_MS).toISOString().slice(0, 10)
}

/** 요일 1=월 … 7=일 (SlotIn.day 와 같다) */
export function dayOfDate(d: string): number {
  return ((new Date(asUtc(d)).getUTCDay() + 6) % 7) + 1
}

/** 그 주의 월요일 */
export const mondayOf = (d: string) => addDays(d, 1 - dayOfDate(d))

/** 9, 5 → '09:05' */
export const hm = (h: number, m: number) =>
  `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`

/** '2026-10-05' → '10/5' */
export const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`
```

`web/src/components/domain/rules.ts`
```ts
// 도메인 규칙 한 곳 — 폼·표·격자가 같은 값을 쓴다 (components.md: 편집 경로마다 검증이 갈라지지 않게)
import type { ApiError } from '@/api/client'
import type { SlotSource, SlotType } from '@/api/types'
import { addDays } from '@/lib/time'

/** UTF-8 바이트 상한 — lora_proto LP_SUBJ_MAX / LP_PROF_MAX (서버 schemas._Span 과 같다) */
export const SUBJ_MAX = 20
export const PROF_MAX = 12
/** 예약은 오늘~+7 일만 노드로 간다 (서버 RESV_HORIZON_DAYS) */
export const RESV_HORIZON_DAYS = 7

export const DAYS = ['월', '화', '수', '목', '금', '토', '일'] as const
export const DAY_OPTIONS = DAYS.map((label, i) => ({ value: i + 1, label }))

/** 배지 라벨 (components.md TypeBadge) */
export const TYPE_LABEL: Record<SlotType, string> = {
  1: '수업중',
  2: '시험중',
  3: '휴강',
  4: '빈강의실',
  5: '특강',
  6: '대여중',
}
/** 폼 Select — CSV 의 type 이름과 같은 말 */
export const TYPE_OPTIONS: { value: SlotType; label: string }[] = [
  { value: 1, label: '수업' },
  { value: 2, label: '시험' },
  { value: 3, label: '휴강' },
  { value: 4, label: '빈강의실' },
  { value: 5, label: '특강' },
  { value: 6, label: '대여' },
]
/** 사용중 — 문 앞 e-Paper 의 RED. 넷을 색으로 나누지 않고 라벨로 가른다 */
export const BUSY_TYPES: readonly SlotType[] = [1, 2, 5, 6]
export const SOURCE_LABEL: Record<SlotSource, string> = { 1: '포털', 2: '수동', 3: '긴급' }

export interface Span {
  s_h: number
  s_m: number
  e_h: number
  e_m: number
}
export const toMin = (h: number, m: number) => h * 60 + m
/** 끝이 맞닿는 것(09–10 · 10–11)은 겹침이 아니다 */
export const spansOverlap = (a: Span, b: Span) =>
  toMin(a.s_h, a.s_m) < toMin(b.e_h, b.e_m) && toMin(b.s_h, b.s_m) < toMin(a.e_h, a.e_m)

export type ResvWindow = 'past' | 'in' | 'later'
/** later = 창 밖 — 저장은 되고 outbox_ids 가 빈 배열로 온다(실패 아님). 창에 들어오는 날 자동 전송 */
export function resvWindow(date: string, today: string): ResvWindow {
  if (date < today) return 'past'
  return date <= addDays(today, RESV_HORIZON_DAYS) ? 'in' : 'later'
}
export const LATER_HINT = '7일 이내로 들어오면 자동 전송됩니다'

/** 층은 서버에 없다 — 401 → 4, 1203 → 12, 100 미만은 null('기타'). 트리·마스터 표가 같은 규칙 */
export const floorOf = (room: number) => (room < 100 ? null : Math.floor(room / 100))
export function floorLabel(room: number): string {
  const f = floorOf(room)
  return f === null ? '기타' : `${f}층`
}

/** 저장한 행 — 화면이 이 key 의 OutboxDot 을 30초 따라간다 */
export interface SavedRow {
  roomId: number
  key: string
  outboxIds: number[]
}
export const slotKey = (s: { room_id: number; day: number; s_h: number; s_m: number }) =>
  `s${s.room_id}-${s.day}-${s.s_h}-${s.s_m}`
export const resvKey = (id: number) => `r${id}`
export const examKey = (id: number) => `x${id}`

/** 서버 오류 본문의 detail 문자열 (없으면 '') — 화면에 내지 않고 분기에만 쓴다 */
export function detailText(e: ApiError): string {
  const d = (e.detail as { detail?: unknown } | null)?.detail
  return typeof d === 'string' ? d : ''
}

// 409 원문 → 사람 문장 (spec §4.1 — 원문은 화면에 내지 않는다). 위에서부터 첫 일치
const CONFLICTS: [RegExp, string][] = [
  [/^source \d/, '이 슬롯은 웹에서 수정된 행입니다. CSV로 덮어쓸 수 없습니다.'],
  [/가득/, '이 강의실은 7일 안 예약이 가득 찼습니다(24건). 지난 예약을 정리하세요.'],
  [/id 소진/, 'id 소진 — 지난 예약·시험기간을 정리하세요'],
  [/다른 방/, '다른 강의실의 항목입니다. 목록을 새로 불러옵니다.'],
  [/신청 상태/, '학생 신청은 신청 대기에서 승인·거절로 처리하세요.'],
  [/시작 시각이 지난/, '이미 시작 시각이 지난 신청입니다.'],
  [/다른 예약·수업이 생겼/, '그 시간에 다른 예약이나 수업이 생겨 승인할 수 없습니다.'],
  [/상태에서는 불가/, '이미 처리된 신청입니다.'],
]
export function conflictMessage(e: ApiError): string {
  const t = detailText(e)
  return CONFLICTS.find(([re]) => re.test(t))?.[1] ?? e.message
}
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test src/lib src/components/domain && pnpm typecheck && pnpm lint`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add web/src/lib/time.ts web/src/lib/__tests__/calendar.spec.ts web/src/components/domain/rules.ts web/src/components/domain/__tests__/rules.spec.ts
git commit -m "feat(web): 도메인 규칙 한 곳 — 바이트 상한·요일·유형·출처·겹침·7일 창·층·행 키·409 문장, 달력 날짜 헬퍼"
```

---

### Task 3: ui — Button 진행 라벨 폭 · Table `tall` · OutboxDot 취소 문구

F1 이월: `components.md` Button — "진행도가 있으면 `loadingLabel`로 바꾼다. 이때 너비는 가장 긴 문자열 기준으로 미리 잡는다." ExamForm 의 "3/7 적용 중"과 범위 추가의 "5 / 12 만드는 중"이 첫 소비자다.

**Files:**
- Modify: `web/src/components/ui/Button.vue`, `web/src/components/ui/Table.vue`, `web/src/components/domain/OutboxDot.vue`
- Test: `web/src/components/ui/__tests__/basic.spec.ts`, `web/src/components/ui/__tests__/table.spec.ts`, `web/src/components/domain/__tests__/domain.spec.ts`

**Interfaces:**
- Produces: Button — `loadingLabel` 이 있으면 **평소에도** 폭을 `max(기본 라벨, loadingLabel 의 숫자를 가장 긴 자릿수의 0 으로 채운 문자열)` 로 잡는다. DOM: `.btn__label`(inline-grid) 안에 기본 슬롯 `span` · 숨은 폭 잡이 `.btn__ghost` · 로딩 중 `.btn__progress`. 호출 쪽은 로딩 전에도 `loadingLabel` 을 넘긴다(예: `0/7 적용 중`).
- Produces: Table prop `tall?: boolean` — `table.tbl--tall`, 행 44px.
- Produces: `DOT_LABEL.cancelled = '취소됨 — 노드에 반영 안 됨'`.

- [ ] **Step 1: 실패 테스트**

`web/src/components/ui/__tests__/basic.spec.ts` 의 `it('loadingLabel 이 있으면 진행도로 바꾼다', …)` 를 통째로 바꾼다
```ts
  it('loadingLabel — 진행도를 보이고, 숫자를 가장 긴 자릿수로 채운 문자열로 폭을 미리 잡는다', async () => {
    const w = mount(Button, {
      props: { loading: false, loadingLabel: '0/12 적용 중' },
      slots: { default: '선택한 12곳에 기간 추가' },
    })
    // 평소 — 기본 라벨이 보이고, 폭 잡이만 숨어 있다
    expect(w.find('.btn__progress').exists()).toBe(false)
    expect(w.findAll('.btn__ghost').map((g) => g.text())).toEqual(['00/00 적용 중'])
    // 진행 중 — 진행도가 보이고 기본 라벨은 숨은 채 폭을 지킨다 ("3/12" 와 "10/12" 폭이 같다)
    await w.setProps({ loading: true, loadingLabel: '3/12 적용 중' })
    expect(w.get('.btn__progress').text()).toBe('3/12 적용 중')
    expect(w.findAll('.btn__ghost').map((g) => g.text())).toEqual([
      '선택한 12곳에 기간 추가',
      '00/00 적용 중',
    ])
    expect(w.get('button').element.disabled).toBe(true)
  })
```

`web/src/components/ui/__tests__/table.spec.ts` 의 `describe('Table', …)` 안 끝에 추가
```ts
  it('tall — 두 줄 셀이 있는 표는 행 44px', () => {
    const w = mount(Table, { props: { columns, rows, tall: true } })
    expect(w.get('table').classes()).toContain('tbl--tall')
    const plain = mount(Table, { props: { columns, rows } })
    expect(plain.get('table').classes()).not.toContain('tbl--tall')
  })
```

`web/src/components/domain/__tests__/domain.spec.ts` 의 `['cancelled', '취소됨'],` 줄을 바꾼다
```ts
    ['cancelled', '취소됨 — 노드에 반영 안 됨'],
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/components`
Expected: FAIL — Button `Cannot call text on an empty DOMWrapper`(`.btn__progress` 없음), Table `expected [ 'tbl' ] to include 'tbl--tall'`, OutboxDot `expected '취소됨' to be '취소됨 — 노드에 반영 안 됨'`

- [ ] **Step 3: 구현**

`web/src/components/ui/Button.vue` 의 `<script setup>` 과 `<template>` 을 통째로 바꾸고(`<script lang="ts">` 의 `export type ButtonVariant` 블록은 그대로), `<style>` 끝에 규칙 넷을 더한다
```vue
<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    variant?: ButtonVariant
    size?: 'sm' | 'md'
    disabled?: boolean
    loading?: boolean
    loadingLabel?: string
    type?: 'button' | 'submit'
  }>(),
  { variant: 'primary', size: 'md', disabled: false, loading: false, type: 'button' },
)
// 진행 라벨("3/12 적용 중")은 숫자가 바뀌어도 폭이 흔들리면 안 된다 (components.md) — 숫자를 가장 긴
// 자릿수의 0 으로 채운 문자열을 숨겨 두어 폭을 미리 잡는다. .num(tabular-nums)이라 숫자 폭은 0 과 같다
const sizer = computed(() => {
  const label = props.loadingLabel
  if (!label) return ''
  const width = Math.max(...(label.match(/\d+/g) ?? ['']).map((s) => s.length))
  return label.replace(/\d+/g, '0'.repeat(width))
})
</script>

<template>
  <button
    :type="type"
    class="btn"
    :class="[`btn--${variant}`, `btn--${size}`]"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
  >
    <span v-if="loading" class="btn__spin" aria-hidden="true" />
    <span class="btn__label">
      <span :class="{ btn__ghost: loading && loadingLabel }"><slot /></span>
      <span v-if="loadingLabel" class="btn__ghost num" aria-hidden="true">{{ sizer }}</span>
      <span v-if="loading && loadingLabel" class="btn__progress num">{{ loadingLabel }}</span>
    </span>
  </button>
</template>
```
```css
/* 기본 라벨·폭 잡이·진행 라벨을 한 칸에 겹친다 — 폭은 셋 중 가장 넓은 것 */
.btn__label {
  display: inline-grid;
}
.btn__label > * {
  grid-area: 1 / 1;
  text-align: center;
}
.btn__ghost {
  visibility: hidden;
}
```

`web/src/components/ui/Table.vue`
- `defineProps` 에 `tall?: boolean` 을 더하고 `withDefaults` 기본값 객체에 `tall: false` 를 더한다.
- `<table class="tbl">` 를 `<table class="tbl" :class="{ 'tbl--tall': tall }">` 로 바꾼다.
- `<style>` 의 `td { … }` 규칙 **바로 아래**에 추가:
```css
/* 두 줄 셀이 있는 표 (components.md — 행 32px, 두 줄이면 44px) */
.tbl--tall td {
  height: 44px;
}
```

`web/src/components/domain/OutboxDot.vue` 의 `DOT_LABEL` 에서 `cancelled: '취소됨',` 을 바꾼다
```ts
  // 관리자가 의도한 일이라 경고색은 아니지만, 웹 DB 는 새 값인데 문 앞은 옛 값이다 (admin-rooms.md)
  cancelled: '취소됨 — 노드에 반영 안 됨',
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`
Expected: PASS (F1 Button `'loading 은 라벨을 유지하고 잠근다'` — `loadingLabel` 이 없으면 폭 잡이도 없어 `text()` 가 `'저장'` 그대로)

- [ ] **Step 5: 커밋**

```bash
git add web/src/components
git commit -m "style(web): Button 진행 라벨 폭을 미리 잡는다(숫자 자리 고정), Table 두 줄 행 44px, OutboxDot 취소 툴팁 '노드에 반영 안 됨'"
```

---

### Task 4: domain — TypeBadge · SourceBadge

**Files:**
- Create: `web/src/components/domain/TypeBadge.vue`, `web/src/components/domain/SourceBadge.vue`
- Test: `web/src/components/domain/__tests__/badges.spec.ts`

**Interfaces:**
- Consumes: `Badge`(F1), `TYPE_LABEL`·`BUSY_TYPES`·`SOURCE_LABEL`(Task 2).
- Produces: `TypeBadge` props `{ type: SlotType }` · `SourceBadge` props `{ source: SlotSource }` — 루트는 Badge 의 `span.badge`.

- [ ] **Step 1: 실패 테스트**

`web/src/components/domain/__tests__/badges.spec.ts`
```ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TypeBadge from '@/components/domain/TypeBadge.vue'
import SourceBadge from '@/components/domain/SourceBadge.vue'

describe('TypeBadge', () => {
  it.each([
    [1, '수업중'],
    [2, '시험중'],
    [5, '특강'],
    [6, '대여중'],
  ] as const)('%s — 사용중은 전부 같은 busy 틴트, 구분은 라벨 %s', (type, label) => {
    const w = mount(TypeBadge, { props: { type } })
    expect(w.text()).toBe(label)
    expect(w.classes()).toEqual(expect.arrayContaining(['badge--busy', 'badge--tint']))
  })
  it.each([
    [3, '휴강'],
    [4, '빈강의실'],
  ] as const)('%s — 테두리만 (%s)', (type, label) => {
    const w = mount(TypeBadge, { props: { type } })
    expect(w.text()).toBe(label)
    expect(w.classes()).toEqual(expect.arrayContaining(['badge--neutral', 'badge--outline']))
  })
})

describe('SourceBadge', () => {
  it.each([
    [1, '포털', 'badge--neutral', 'badge--outline'],
    [2, '수동', 'badge--neutral', 'badge--solid'],
    [3, '긴급', 'badge--danger', 'badge--outline'],
  ] as const)('%s → %s (색만이 아니라 라벨로)', (source, label, tone, variant) => {
    const w = mount(SourceBadge, { props: { source } })
    expect(w.text()).toBe(label)
    expect(w.classes()).toEqual(expect.arrayContaining([tone, variant]))
  })
  it('툴팁이 CSV 와의 관계를 말한다', () => {
    expect(mount(SourceBadge, { props: { source: 1 } }).attributes('title')).toBe(
      'CSV 로 들어온 행 — 다음 CSV 가 덮는다',
    )
    expect(mount(SourceBadge, { props: { source: 2 } }).attributes('title')).toBe(
      '웹에서 고친 행 — CSV 가 덮지 않는다',
    )
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/components/domain/__tests__/badges.spec.ts`
Expected: FAIL — `Failed to resolve import "@/components/domain/TypeBadge.vue"`

- [ ] **Step 3: 구현**

`web/src/components/domain/TypeBadge.vue`
```vue
<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/components/ui/Badge.vue'
import type { SlotType } from '@/api/types'
import { BUSY_TYPES, TYPE_LABEL } from './rules'

const props = defineProps<{ type: SlotType }>()
const busy = computed(() => BUSY_TYPES.includes(props.type))
</script>

<template>
  <!-- 1·2·5·6 은 같은 busy — 구분은 라벨 (e-Paper RED 이분법과 1:1). 매핑을 화면마다 다시 쓰지 않는다 -->
  <Badge :tone="busy ? 'busy' : 'neutral'" :variant="busy ? 'tint' : 'outline'">{{
    TYPE_LABEL[type]
  }}</Badge>
</template>
```

`web/src/components/domain/SourceBadge.vue`
```vue
<script setup lang="ts">
import Badge from '@/components/ui/Badge.vue'
import type { SlotSource } from '@/api/types'
import { SOURCE_LABEL } from './rules'

defineProps<{ source: SlotSource }>()
const STYLE = {
  1: { tone: 'neutral', variant: 'outline' },
  2: { tone: 'neutral', variant: 'solid' },
  3: { tone: 'danger', variant: 'outline' },
} as const
</script>

<template>
  <!-- 이게 없으면 CSV 임포트 뒤 "왜 이 행만 안 바뀌지"를 설명할 수 없다 (admin-rooms.md §1) -->
  <Badge
    :tone="STYLE[source].tone"
    :variant="STYLE[source].variant"
    :title="
      source === 1 ? 'CSV 로 들어온 행 — 다음 CSV 가 덮는다' : '웹에서 고친 행 — CSV 가 덮지 않는다'
    "
    >{{ SOURCE_LABEL[source] }}</Badge
  >
</template>
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`
Expected: PASS (토큰 가드가 새 `.vue` 둘도 검사)

- [ ] **Step 5: 커밋**

```bash
git add web/src/components/domain
git commit -m "feat(web): TypeBadge(사용중 넷은 같은 틴트·라벨로 구분)·SourceBadge(포털·수동·긴급)"
```

---

### Task 5: domain — RoomTree

**Files:**
- Create: `web/src/components/domain/roomTree.ts`, `web/src/components/domain/RoomTree.vue`
- Test: `web/src/components/domain/__tests__/roomTree.spec.ts`

**Interfaces:**
- Consumes: `Checkbox`·`Badge`(F1), `floorOf`·`floorLabel`(Task 2), `BuildingOut`·`RoomOut`(Task 1).
- Produces (`roomTree.ts`): `interface FloorNode { key: string; label: string; rooms: RoomOut[] }` · `interface BuildingNode { key: string; building: BuildingOut; floors: FloorNode[]; ids: number[] }` · `buildTree(buildings, rooms, query?): BuildingNode[]` · `type Check = 'all'|'some'|'none'` · `checkOf(ids, selected): Check` · `toggleGroup(ids, selected): number[]` · `selectionLabel(buildings, rooms, selected, mode): string`.
- Produces (`RoomTree.vue`): props `{ mode?: 'multi'|'single'; buildings: BuildingOut[]; rooms: RoomOut[]; selected?: number[] }`, emits `update:selected: [ids: number[]]` (`v-model:selected`). DOM: 트리거 `button.tree__trigger`(라벨 = 현재 선택), 패널 `div.tree__panel[role=group][aria-label=강의실 선택]`, 검색 `input[type=search][aria-label=호수 검색]`, 행 `.tree__row--b`·`--f`·`--r`, `전체 해제`(multi). `expanded`·`query` 는 컴포넌트 안 상태(설계 판정 — 바깥에서 쓰는 곳이 없다).

- [ ] **Step 1: 실패 테스트**

`web/src/components/domain/__tests__/roomTree.spec.ts`
```ts
import { afterEach, describe, expect, it } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import RoomTree from '@/components/domain/RoomTree.vue'
import { buildTree, checkOf, selectionLabel, toggleGroup } from '@/components/domain/roomTree'
import type { BuildingOut, RoomOut } from '@/api/types'

const B = (id: number, name: string, bld: string): BuildingOut => ({
  id,
  school_id: 1,
  name,
  bld,
  modem_id: null,
})
const R = (id: number, building_id: number, room: number): RoomOut => ({
  id,
  building_id,
  room,
  units: 1,
  reservable: false,
})
const buildings = [B(1, '공학관', 'E'), B(2, '사회관', 'S')]
const rooms = [R(13, 1, 501), R(11, 1, 401), R(12, 1, 402), R(14, 1, 5), R(21, 2, 101)]

describe('roomTree', () => {
  it('건물 → 층(호수 ÷ 100, 100 미만 기타) → 호수 오름차순', () => {
    const t = buildTree(buildings, rooms)
    expect(t[0].floors.map((f) => [f.label, f.rooms.map((r) => r.room)])).toEqual([
      ['기타', [5]],
      ['4층', [401, 402]],
      ['5층', [501]],
    ])
    expect(t[0].ids).toEqual([14, 11, 12, 13])
    expect(t[1].floors[0].label).toBe('1층')
  })

  it('검색은 호수 숫자만 — 맞는 방이 없는 건물은 빠진다', () => {
    const t = buildTree(buildings, rooms, '40')
    expect(t).toHaveLength(1)
    expect(t[0].ids).toEqual([11, 12])
  })

  it('부모 체크 — 일부면 some, 누르면 전부, 전부면 전부 해제 (다른 선택은 그대로)', () => {
    expect(checkOf([11, 12], [11])).toBe('some')
    expect(checkOf([11, 12], [])).toBe('none')
    expect(checkOf([11, 12], [12, 11])).toBe('all')
    expect(toggleGroup([11, 12], [21, 11])).toEqual([21, 11, 12])
    expect(toggleGroup([11, 12], [21, 11, 12])).toEqual([21])
  })

  it('버튼 라벨 — 셋까지 나열, 넷 이상·여러 건물은 "외 N곳", single 은 호', () => {
    expect(selectionLabel(buildings, rooms, [], 'multi')).toBe('강의실 선택')
    expect(selectionLabel(buildings, rooms, [12, 11, 13], 'multi')).toBe('공학관 401 · 402 · 501')
    expect(selectionLabel(buildings, rooms, [14, 11, 12, 13], 'multi')).toBe('공학관 5 외 3곳')
    expect(selectionLabel(buildings, rooms, [21, 11], 'multi')).toBe('공학관 401 외 1곳')
    expect(selectionLabel(buildings, rooms, [21], 'single')).toBe('사회관 101호')
  })
})

describe('RoomTree', () => {
  let w: VueWrapper
  afterEach(() => w?.unmount())
  async function open(props: Record<string, unknown> = {}) {
    w = mount(RoomTree, {
      props: { buildings, rooms, selected: [11], ...props },
      attachTo: document.body,
    })
    await w.get('.tree__trigger').trigger('click')
  }
  const last = () => w.emitted('update:selected')?.at(-1)?.[0]
  const roomRows = () => w.findAll('.tree__row--r').map((r) => r.text())

  it('닫혀 있어도 버튼이 선택을 말한다 — 열면 고른 방의 건물·층이 펼쳐져 있다', async () => {
    await open()
    expect(w.get('.tree__trigger').text()).toContain('공학관 401')
    expect(w.get('.tree__trigger').attributes('aria-expanded')).toBe('true')
    expect(roomRows()).toEqual(['401호', '402호'])
  })

  it('건물을 누르면 그 건물 전체 — 일부만 골라졌으면 indeterminate', async () => {
    await open()
    const b = w.get('.tree__row--b input[type=checkbox]')
    expect((b.element as HTMLInputElement).indeterminate).toBe(true)
    await b.setValue(true)
    expect(last()).toEqual([11, 14, 12, 13])
  })

  it('검색해도 선택은 그대로 — 트리만 줄고, 호수를 누르면 즉시 반영 (확인 버튼 없음)', async () => {
    await open()
    await w.get('input[type=search]').setValue('50')
    expect(roomRows()).toEqual(['501호'])
    expect(w.emitted('update:selected')).toBeUndefined()
    await w.get('.tree__row--r input[type=checkbox]').setValue(true)
    expect(last()).toEqual([11, 13])
    expect(w.find('.tree__panel').exists()).toBe(true)
  })

  it('전체 해제', async () => {
    await open()
    await w.get('.tree__clear').trigger('click')
    expect(last()).toEqual([])
  })

  it('single — 체크박스 없이 호수를 누르면 그 방 하나, 드롭다운이 닫힌다', async () => {
    await open({ mode: 'single' })
    expect(w.find('.tree__panel input[type=checkbox]').exists()).toBe(false)
    await w.findAll('.tree__row--r').find((r) => r.text() === '402호')!.trigger('click')
    expect(last()).toEqual([12])
    expect(w.find('.tree__panel').exists()).toBe(false)
  })

  it('Esc·바깥 누르기로 닫힌다', async () => {
    await open()
    await w.get('input[type=search]').trigger('keydown', { key: 'Escape' })
    expect(w.find('.tree__panel').exists()).toBe(false)
    await w.get('.tree__trigger').trigger('click')
    document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    await w.vm.$nextTick()
    expect(w.find('.tree__panel').exists()).toBe(false)
  })

  it('방이 많아도(300곳) 검색으로 하나를 찾는다', async () => {
    const many = Array.from({ length: 300 }, (_, i) => R(1000 + i, 1, 100 + i * 4))
    await open({ rooms: many, selected: [] })
    await w.get('input[type=search]').setValue('1196')
    expect(roomRows()).toEqual(['1196호'])
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/components/domain/__tests__/roomTree.spec.ts`
Expected: FAIL — `Failed to resolve import "@/components/domain/RoomTree.vue"`

- [ ] **Step 3: 구현**

`web/src/components/domain/roomTree.ts`
```ts
import type { BuildingOut, RoomOut } from '@/api/types'
import { floorLabel, floorOf } from './rules'

export interface FloorNode {
  key: string
  label: string
  rooms: RoomOut[]
}
export interface BuildingNode {
  key: string
  building: BuildingOut
  floors: FloorNode[]
  ids: number[]
}

/** 건물 → 층 → 호수. 층은 서버에 없어 호수에서 파생한다. query 는 호수 숫자만 거른다 (components.md RoomTree) */
export function buildTree(buildings: BuildingOut[], rooms: RoomOut[], query = ''): BuildingNode[] {
  const q = query.trim()
  const out: BuildingNode[] = []
  for (const b of buildings) {
    const mine = rooms
      .filter((r) => r.building_id === b.id && String(r.room).includes(q))
      .sort((x, y) => x.room - y.room)
    if (q && !mine.length) continue
    const floors: FloorNode[] = []
    for (const r of mine) {
      const key = `${b.id}:${floorOf(r.room) ?? 'etc'}`
      let f = floors.find((x) => x.key === key)
      if (!f) {
        f = { key, label: floorLabel(r.room), rooms: [] }
        floors.push(f)
      }
      f.rooms.push(r)
    }
    out.push({ key: `b${b.id}`, building: b, floors, ids: mine.map((r) => r.id) })
  }
  return out
}

export type Check = 'all' | 'some' | 'none'
export function checkOf(ids: number[], selected: readonly number[]): Check {
  const n = ids.filter((i) => selected.includes(i)).length
  if (n === 0) return 'none'
  return n === ids.length ? 'all' : 'some'
}

/** 건물·층을 누르면 — 전부 골라져 있으면 전부 해제, 아니면 전부 선택 */
export function toggleGroup(ids: number[], selected: readonly number[]): number[] {
  if (checkOf(ids, selected) === 'all') return selected.filter((i) => !ids.includes(i))
  return [...selected, ...ids.filter((i) => !selected.includes(i))]
}

/** 버튼 라벨이 곧 현재 선택 — 닫혀 있어도 읽힌다 (admin-rooms.md) */
export function selectionLabel(
  buildings: BuildingOut[],
  rooms: RoomOut[],
  selected: readonly number[],
  mode: 'multi' | 'single',
): string {
  const order = (r: RoomOut) => buildings.findIndex((b) => b.id === r.building_id)
  const picked = rooms
    .filter((r) => selected.includes(r.id))
    .sort((a, b) => order(a) - order(b) || a.room - b.room)
  if (!picked.length) return '강의실 선택'
  const name = buildings.find((b) => b.id === picked[0].building_id)?.name ?? ''
  if (mode === 'single') return `${name} ${picked[0].room}호`
  const oneBuilding = picked.every((r) => r.building_id === picked[0].building_id)
  if (oneBuilding && picked.length <= 3) return `${name} ${picked.map((r) => r.room).join(' · ')}`
  return `${name} ${picked[0].room} 외 ${picked.length - 1}곳`
}
```

`web/src/components/domain/RoomTree.vue`
```vue
<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import Badge from '@/components/ui/Badge.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import type { BuildingOut, RoomOut } from '@/api/types'
import { buildTree, checkOf, selectionLabel, toggleGroup } from './roomTree'

const props = withDefaults(
  defineProps<{
    mode?: 'multi' | 'single'
    buildings: BuildingOut[]
    rooms: RoomOut[]
    selected?: number[]
  }>(),
  { mode: 'multi', selected: () => [] },
)
const emit = defineEmits<{ 'update:selected': [ids: number[]] }>()

const open = ref(false)
const query = ref('')
const expanded = ref(new Set<string>())
const root = ref<HTMLElement>()
const tree = computed(() => buildTree(props.buildings, props.rooms, query.value))
const label = computed(() =>
  selectionLabel(props.buildings, props.rooms, props.selected, props.mode),
)
const multi = computed(() => props.mode === 'multi')
// 검색 중이면 전부 펼친다 — 맞는 호수가 접힌 층 안에 숨지 않게
const isOpen = (key: string) => !!query.value.trim() || expanded.value.has(key)
function toggleExpand(key: string) {
  const s = new Set(expanded.value)
  if (s.has(key)) s.delete(key)
  else s.add(key)
  expanded.value = s
}
// 선택은 닫을 때가 아니라 누르는 즉시 반영 — 확인 버튼을 두지 않는다
const set = (ids: number[]) => emit('update:selected', ids)
function pick(id: number) {
  if (!multi.value) {
    set([id])
    open.value = false
    return
  }
  set(props.selected.includes(id) ? props.selected.filter((i) => i !== id) : [...props.selected, id])
}

// 열 때 — 고른 방이 있는 건물·층을 펼친다 (아무것도 안 골랐으면 첫 건물)
watch(open, (o) => {
  if (!o) return
  const s = new Set(expanded.value)
  for (const b of buildTree(props.buildings, props.rooms))
    for (const f of b.floors)
      if (f.rooms.some((r) => props.selected.includes(r.id))) {
        s.add(b.key)
        s.add(f.key)
      }
  if (!s.size && props.buildings.length) s.add(`b${props.buildings[0].id}`)
  expanded.value = s
})

// 바깥 클릭·Esc 로 닫힌다
function onDocDown(e: MouseEvent) {
  if (open.value && root.value && !root.value.contains(e.target as Node)) open.value = false
}
document.addEventListener('mousedown', onDocDown)
onScopeDispose(() => document.removeEventListener('mousedown', onDocDown))
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && open.value) {
    e.stopPropagation()
    open.value = false
  }
}
</script>

<template>
  <div ref="root" class="tree" :class="`tree--${mode}`" @keydown="onKey">
    <button
      type="button"
      class="tree__trigger"
      :aria-expanded="open ? 'true' : 'false'"
      aria-haspopup="true"
      @click="open = !open"
    >
      <span class="tree__label">{{ label }}</span>
      <Badge v-if="multi && selected.length" variant="solid" class="num">{{ selected.length }}</Badge>
      <span aria-hidden="true">▾</span>
    </button>
    <div v-if="open" class="tree__panel" role="group" aria-label="강의실 선택">
      <div class="tree__head">
        <span>강의실 선택</span>
        <span v-if="multi" class="num">{{ selected.length }}개 선택</span>
      </div>
      <input
        v-model="query"
        class="tree__search"
        type="search"
        inputmode="numeric"
        placeholder="호수 검색"
        aria-label="호수 검색"
      />
      <ul class="tree__list">
        <li v-for="b in tree" :key="b.key">
          <div class="tree__row tree__row--b">
            <button
              type="button"
              class="tree__caret"
              :aria-expanded="isOpen(b.key) ? 'true' : 'false'"
              :aria-label="`${b.building.name} 펼치기`"
              @click="toggleExpand(b.key)"
            >
              {{ isOpen(b.key) ? '▾' : '▸' }}
            </button>
            <Checkbox
              v-if="multi"
              :model-value="checkOf(b.ids, selected) === 'all'"
              :indeterminate="checkOf(b.ids, selected) === 'some'"
              :disabled="!b.ids.length"
              :label="b.building.name"
              @update:model-value="set(toggleGroup(b.ids, selected))"
            />
            <button v-else type="button" class="tree__name" @click="toggleExpand(b.key)">
              {{ b.building.name }}
            </button>
            <span class="tree__count num">{{ b.ids.length }}</span>
          </div>
          <ul v-if="isOpen(b.key)">
            <li v-for="f in b.floors" :key="f.key">
              <div class="tree__row tree__row--f">
                <button
                  type="button"
                  class="tree__caret"
                  :aria-expanded="isOpen(f.key) ? 'true' : 'false'"
                  :aria-label="`${f.label} 펼치기`"
                  @click="toggleExpand(f.key)"
                >
                  {{ isOpen(f.key) ? '▾' : '▸' }}
                </button>
                <Checkbox
                  v-if="multi"
                  :model-value="checkOf(f.rooms.map((r) => r.id), selected) === 'all'"
                  :indeterminate="checkOf(f.rooms.map((r) => r.id), selected) === 'some'"
                  :label="f.label"
                  @update:model-value="
                    set(
                      toggleGroup(
                        f.rooms.map((r) => r.id),
                        selected,
                      ),
                    )
                  "
                />
                <button v-else type="button" class="tree__name" @click="toggleExpand(f.key)">
                  {{ f.label }}
                </button>
                <span class="tree__count num">{{ f.rooms.length }}</span>
              </div>
              <ul v-if="isOpen(f.key)">
                <li v-for="r in f.rooms" :key="r.id">
                  <div
                    v-if="multi"
                    class="tree__row tree__row--r"
                    :class="{ 'tree__row--on': selected.includes(r.id) }"
                  >
                    <Checkbox
                      :model-value="selected.includes(r.id)"
                      :label="`${r.room}호`"
                      @update:model-value="pick(r.id)"
                    />
                  </div>
                  <button
                    v-else
                    type="button"
                    class="tree__row tree__row--r tree__room num"
                    :class="{ 'tree__row--on': selected.includes(r.id) }"
                    :aria-current="selected.includes(r.id) ? 'true' : undefined"
                    @click="pick(r.id)"
                  >
                    {{ r.room }}호
                  </button>
                </li>
              </ul>
            </li>
          </ul>
        </li>
        <li v-if="!tree.length" class="tree__empty">
          {{ query.trim() ? '맞는 호수가 없습니다' : '강의실이 없습니다' }}
        </li>
      </ul>
      <div class="tree__foot">
        <button v-if="multi" type="button" class="tree__clear" @click="set([])">전체 해제</button>
        <!-- 층은 서버에 없는 값 — 규칙을 관리자에게도 알린다 -->
        <span>층 = 호수 ÷ 100</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tree {
  position: relative;
}
.tree__trigger {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  max-width: 420px;
  height: var(--control-height-md);
  padding: 0 var(--space-3);
  border: var(--border-thin) solid var(--line-3);
  border-radius: var(--radius-md);
  background: var(--surface);
  color: var(--text-1);
  font: inherit;
  font-weight: var(--font-weight-medium);
  cursor: pointer;
}
.tree__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tree__panel {
  position: absolute;
  z-index: 20;
  top: calc(100% + var(--space-1));
  left: 0;
  width: 320px;
  padding: var(--space-2);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.tree__head {
  display: flex;
  justify-content: space-between;
  padding: var(--space-1) var(--space-2);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
}
.tree__search {
  width: 100%;
  height: var(--control-height-sm);
  margin: var(--space-1) 0 var(--space-2);
  padding: 0 var(--space-2);
  border: var(--border-thin) solid var(--line-3);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-1);
  font: inherit;
}
.tree__list,
.tree__list ul {
  margin: 0;
  padding: 0;
  list-style: none;
}
.tree__list {
  max-height: 420px;
  overflow-y: auto;
}
.tree__row {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  height: 32px;
  padding-right: var(--space-2);
}
/* 들여쓰기 — 건물 8 / 층 26 / 호수 62(multi)·48(single) (components.md) */
.tree__row--b {
  padding-left: 8px;
}
.tree__row--f {
  padding-left: 26px;
}
.tree__row--r {
  padding-left: 62px;
}
.tree--single .tree__row--r {
  padding-left: 48px;
}
.tree__row--on {
  background: var(--brand-tint);
  color: var(--brand);
}
.tree__caret,
.tree__name,
.tree__room,
.tree__clear {
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  cursor: pointer;
}
.tree__caret {
  width: 18px;
  padding: 0;
  color: var(--text-2);
}
.tree__room {
  width: 100%;
  text-align: left;
}
.tree__count {
  margin-left: auto;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.tree__empty {
  padding: var(--space-3) var(--space-2);
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.tree__foot {
  display: flex;
  justify-content: space-between;
  margin-top: var(--space-2);
  padding: var(--space-2) var(--space-2) 0;
  border-top: var(--border-thin) solid var(--line-1);
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.tree__clear {
  padding: 0;
  color: var(--text-1);
}
</style>
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add web/src/components/domain
git commit -m "feat(web): RoomTree — 건물→층(호수÷100)→호수 드롭다운, multi(부분 선택 표시·즉시 반영)·single(누르면 닫힘), 호수 검색은 선택을 지키고 바깥·Esc 로 닫힘"
```

---

### Task 6: domain — SlotForm

**Files:**
- Create: `web/src/components/domain/slotForm.ts`, `web/src/components/domain/SlotForm.vue`
- Test: `web/src/components/domain/__tests__/slotForm.spec.ts`

**Interfaces:**
- Consumes: `roomsApi.putSlot`·`deleteSlot`(Task 1), rules(Task 2), `Modal`·`Input`·`Select`·`Button`·`showToast`(F1), `ApiError`·`MESSAGES`.
- Produces (`slotForm.ts`): `interface SlotDraft { roomId: number; day: number; start: string; end: string; type: SlotType; subject: string; professor: string }` · `parseHm(v: string): [number, number] | null` · `slotErrors(d: SlotDraft, existing: SlotWithRoom[], original: SlotWithRoom | null): { start?: string; end?: string }`.
- Produces (`SlotForm.vue`): props `{ open: boolean; mode?: 'create'|'edit'; rooms: RoomOut[]; roomLabel?: (r: RoomOut) => string; value?: SlotWithRoom | null; preset?: { room_id: number; day?: number; s_h?: number; s_m?: number } | null; existing?: SlotWithRoom[]; removable?: boolean }`, emits `close: []` · `saved: [row: SavedRow]` · `stale: []`(목록을 새로 불러와야 함) · `remove: []`(edit + removable 일 때 `삭제`). **저장 호출을 폼이 한다** — 페이지1 표와 페이지2 격자가 같은 규칙으로 저장되게.

- [ ] **Step 1: 실패 테스트**

`web/src/components/domain/__tests__/slotForm.spec.ts`
```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import SlotForm from '@/components/domain/SlotForm.vue'
import Modal from '@/components/ui/Modal.vue'
import { slotErrors, type SlotDraft } from '@/components/domain/slotForm'
import { roomsApi } from '@/api/rooms'
import { ApiError, MESSAGES } from '@/api/client'
import type { RoomOut, SlotWithRoom } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/rooms', () => ({ roomsApi: { putSlot: vi.fn(), deleteSlot: vi.fn() } }))
const api = vi.mocked(roomsApi)

const R = (id: number, room: number): RoomOut => ({
  id,
  building_id: 1,
  room,
  units: 1,
  reservable: false,
})
const rooms = [R(11, 401), R(12, 402)]
const slot = (o: Partial<SlotWithRoom> = {}): SlotWithRoom => ({
  id: 1,
  room_id: 11,
  day: 1,
  s_h: 9,
  s_m: 0,
  e_h: 11,
  e_m: 0,
  type: 1,
  subject: '캡스톤디자인',
  professor: '김교수',
  source: 2,
  ...o,
})
const draft = (o: Partial<SlotDraft> = {}): SlotDraft => ({
  roomId: 11,
  day: 1,
  start: '10:00',
  end: '12:00',
  type: 1,
  subject: '',
  professor: '',
  ...o,
})

let w: VueWrapper
async function mountForm(props: Record<string, unknown> = {}) {
  w = mount(SlotForm, {
    props: { open: true, rooms, ...props },
    global: { stubs: { teleport: true } },
  })
  await flushPromises()
}
const control = (label: string) =>
  w
    .findAll('.field, .sel')
    .find((f) => f.find('label').exists() && f.get('label').text().replace('*', '').trim() === label)!
    .get('input, select')
const save = () => w.findAll('button').find((b) => b.text() === '저장')!.trigger('click')

beforeEach(() => {
  api.putSlot.mockReset().mockResolvedValue({ outbox_ids: [7], id: null })
  api.deleteSlot.mockReset().mockResolvedValue({ outbox_ids: [8], id: null })
  for (const t of [...toasts.value]) dismissToast(t.id)
})

describe('slotErrors', () => {
  it('종료 ≤ 시작이면 막는다 (자정을 넘기는 슬롯은 없다)', () => {
    expect(slotErrors(draft({ start: '10:00', end: '10:00' }), [], null).end).toBe(
      '종료는 시작보다 늦어야 합니다 (자정을 넘기지 않습니다)',
    )
  })
  it('같은 방·같은 요일 구간이 겹치면 막는다 — 서버는 같은 키만 막는다', () => {
    expect(slotErrors(draft(), [slot()], null).end).toBe('겹칩니다: 09:00–11:00 캡스톤디자인')
  })
  it('자기 자신·다른 방·다른 요일·맞닿음은 겹침이 아니다', () => {
    expect(slotErrors(draft(), [slot()], slot())).toEqual({})
    expect(slotErrors(draft({ roomId: 12 }), [slot()], null)).toEqual({})
    expect(slotErrors(draft({ day: 2 }), [slot()], null)).toEqual({})
    expect(slotErrors(draft({ start: '11:00', end: '12:00' }), [slot()], null)).toEqual({})
  })
})

describe('SlotForm', () => {
  it('추가 — 누른 자리로 채우고(종료 +1시간), source 2 로 저장, 행 키를 알린다', async () => {
    await mountForm({ preset: { room_id: 12, day: 3, s_h: 14, s_m: 0 } })
    expect((control('요일').element as HTMLSelectElement).value).toBe('3')
    expect((control('시작').element as HTMLInputElement).value).toBe('14:00')
    expect((control('종료').element as HTMLInputElement).value).toBe('15:00')
    await control('과목명').setValue('캡스톤디자인')
    await save()
    await flushPromises()
    expect(api.putSlot).toHaveBeenCalledWith(12, {
      day: 3,
      s_h: 14,
      s_m: 0,
      e_h: 15,
      e_m: 0,
      type: 1,
      subject: '캡스톤디자인',
      professor: '',
      source: 2,
    })
    expect(api.deleteSlot).not.toHaveBeenCalled()
    expect(w.emitted('saved')![0]).toEqual([{ roomId: 12, key: 's12-3-14-0', outboxIds: [7] }])
    expect(w.emitted('close')).toHaveLength(1)
  })

  it('키가 바뀌면 새 행을 먼저 넣고 옛 행을 지운다 (PUT 은 키로 찾는다 — 옛 행이 남지 않게)', async () => {
    await mountForm({ mode: 'edit', value: slot() })
    await control('시작').setValue('13:00')
    await control('종료').setValue('15:00')
    await save()
    await flushPromises()
    expect(api.putSlot).toHaveBeenCalledWith(11, expect.objectContaining({ s_h: 13, e_h: 15 }))
    expect(api.deleteSlot).toHaveBeenCalledWith(11, expect.objectContaining({ day: 1, s_h: 9, s_m: 0 }))
    expect(api.putSlot.mock.invocationCallOrder[0]).toBeLessThan(
      api.deleteSlot.mock.invocationCallOrder[0],
    )
    expect(w.emitted('saved')![0]).toEqual([{ roomId: 11, key: 's11-1-13-0', outboxIds: [7] }])
  })

  it('키가 같으면 지우지 않는다', async () => {
    await mountForm({ mode: 'edit', value: slot() })
    await control('과목명').setValue('캡스톤디자인2')
    await save()
    await flushPromises()
    expect(api.deleteSlot).not.toHaveBeenCalled()
  })

  it('옛 행 지우기 실패 — 새 행은 두고, 알리고, 목록을 새로 부르게 한다', async () => {
    api.deleteSlot.mockRejectedValue(new ApiError(500, MESSAGES[500]))
    await mountForm({ mode: 'edit', value: slot() })
    await control('시작').setValue('13:00')
    await control('종료').setValue('15:00')
    await save()
    await flushPromises()
    expect(w.emitted('saved')).toHaveLength(1)
    expect(w.emitted('stale')).toHaveLength(1)
    expect(toasts.value.at(-1)).toMatchObject({
      tone: 'danger',
      message: '새 슬롯은 저장했지만 옛 슬롯을 지우지 못했습니다. 표에서 지워 주세요.',
    })
  })

  it('포털(1) 슬롯은 수동(2)으로 올린다고 알리고, 긴급(3)은 3 그대로 보낸다', async () => {
    await mountForm({ mode: 'edit', value: slot({ source: 1 }) })
    expect(w.text()).toContain(
      '저장하면 이 슬롯은 수동 편집으로 바뀌어 CSV 임포트에 덮이지 않습니다.',
    )
    await save()
    await flushPromises()
    expect(api.putSlot.mock.calls[0][1].source).toBe(2)
    w.unmount()
    await mountForm({ mode: 'edit', value: slot({ source: 3 }) })
    await save()
    await flushPromises()
    expect(api.putSlot.mock.calls[1][1].source).toBe(3)
  })

  it('겹치면 저장 전에 막는다 — 서버를 부르지 않는다', async () => {
    await mountForm({ existing: [slot()], preset: { room_id: 11, day: 1, s_h: 10, s_m: 0 } })
    await save()
    await flushPromises()
    expect(api.putSlot).not.toHaveBeenCalled()
    expect(w.text()).toContain('겹칩니다: 09:00–11:00 캡스톤디자인')
  })

  it('409 — 사람 문장 Toast, 목록 새로 고침, 폼은 열어 둔다', async () => {
    api.putSlot.mockRejectedValue(
      new ApiError(409, MESSAGES[409], [], { detail: 'source 3 슬롯은 source ≥ 3 로만 수정' }),
    )
    await mountForm({ preset: { room_id: 11 } })
    await save()
    await flushPromises()
    expect(toasts.value.at(-1)).toMatchObject({
      tone: 'danger',
      message: '이 슬롯은 웹에서 수정된 행입니다. CSV로 덮어쓸 수 없습니다.',
    })
    expect(w.emitted('stale')).toHaveLength(1)
    expect(w.emitted('close')).toBeUndefined()
  })

  it('연타해도 한 번만 보낸다', async () => {
    api.putSlot.mockReturnValue(new Promise(() => {}))
    await mountForm({ preset: { room_id: 11 } })
    await save()
    await save()
    await flushPromises()
    expect(api.putSlot).toHaveBeenCalledTimes(1)
  })

  it('입력을 바꾸면 배경 클릭으로 닫히지 않는다', async () => {
    await mountForm({ preset: { room_id: 11 } })
    expect(w.findComponent(Modal).props('closeOnBackdrop')).toBe(true)
    await control('과목명').setValue('x')
    expect(w.findComponent(Modal).props('closeOnBackdrop')).toBe(false)
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/components/domain/__tests__/slotForm.spec.ts`
Expected: FAIL — `Failed to resolve import "@/components/domain/SlotForm.vue"`

- [ ] **Step 3: 구현**

`web/src/components/domain/slotForm.ts`
```ts
import type { SlotType, SlotWithRoom } from '@/api/types'
import { hm } from '@/lib/time'
import { slotKey, spansOverlap, toMin } from './rules'

export interface SlotDraft {
  roomId: number
  day: number
  /** <input type="time"> 값 'HH:MM' */
  start: string
  end: string
  type: SlotType
  subject: string
  professor: string
}

const HM = /^(\d{2}):(\d{2})$/
export function parseHm(v: string): [number, number] | null {
  const m = HM.exec(v)
  return m ? [Number(m[1]), Number(m[2])] : null
}

/** 저장 전 검사 — 서버는 같은 키(요일+시작)만 막는다. 09–11 과 10–12 가 둘 다 들어가지 않게 여기서 (components.md) */
export function slotErrors(
  d: SlotDraft,
  existing: SlotWithRoom[],
  original: SlotWithRoom | null,
): { start?: string; end?: string } {
  const s = parseHm(d.start)
  if (!s) return { start: '시작 시각을 넣으세요' }
  const e = parseHm(d.end)
  if (!e) return { end: '종료 시각을 넣으세요' }
  if (toMin(...e) <= toMin(...s))
    return { end: '종료는 시작보다 늦어야 합니다 (자정을 넘기지 않습니다)' }
  const span = { s_h: s[0], s_m: s[1], e_h: e[0], e_m: e[1] }
  const self = original ? slotKey(original) : null
  const hit = existing.find(
    (x) =>
      x.room_id === d.roomId && x.day === d.day && slotKey(x) !== self && spansOverlap(x, span),
  )
  return hit ? { end: `겹칩니다: ${hm(hit.s_h, hit.s_m)}–${hm(hit.e_h, hit.e_m)} ${hit.subject}` } : {}
}
```

`web/src/components/domain/SlotForm.vue`
```vue
<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Modal from '@/components/ui/Modal.vue'
import Select from '@/components/ui/Select.vue'
import { showToast } from '@/components/ui/toast'
import { ApiError, MESSAGES } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { RoomOut, SlotIn, SlotSource, SlotWithRoom } from '@/api/types'
import { hm } from '@/lib/time'
import {
  DAY_OPTIONS,
  PROF_MAX,
  SUBJ_MAX,
  TYPE_OPTIONS,
  conflictMessage,
  slotKey,
  type SavedRow,
} from './rules'
import { parseHm, slotErrors, type SlotDraft } from './slotForm'

const props = withDefaults(
  defineProps<{
    open: boolean
    mode?: 'create' | 'edit'
    rooms: RoomOut[]
    roomLabel?: (r: RoomOut) => string
    /** edit — 고칠 슬롯 */
    value?: SlotWithRoom | null
    /** create — 기본 강의실, 격자에서 누른 요일·시각 */
    preset?: { room_id: number; day?: number; s_h?: number; s_m?: number } | null
    /** 겹침 검사 대상 (같은 방·같은 요일만 본다) */
    existing?: SlotWithRoom[]
    removable?: boolean
  }>(),
  {
    mode: 'create',
    roomLabel: (r: RoomOut) => `${r.room}호`,
    value: null,
    preset: null,
    existing: () => [],
    removable: false,
  },
)
const emit = defineEmits<{ close: []; saved: [row: SavedRow]; stale: []; remove: [] }>()

const draft = reactive<SlotDraft>({
  roomId: 0,
  day: 1,
  start: '09:00',
  end: '10:00',
  type: 1,
  subject: '',
  professor: '',
})
const errors = ref<{ start?: string; end?: string }>({})
const formError = ref('')
const saving = ref(false)
const initial = ref('')
const dirty = computed(() => JSON.stringify(draft) !== initial.value)
const roomOptions = computed(() => props.rooms.map((r) => ({ value: r.id, label: props.roomLabel(r) })))

watch(
  () => props.open,
  (open) => {
    if (!open) return
    const v = props.value
    const p = props.preset
    const sh = p?.s_h ?? 9
    const sm = p?.s_m ?? 0
    Object.assign(
      draft,
      v
        ? {
            roomId: v.room_id,
            day: v.day,
            start: hm(v.s_h, v.s_m),
            end: hm(v.e_h, v.e_m),
            type: v.type,
            subject: v.subject,
            professor: v.professor,
          }
        : {
            roomId: p?.room_id ?? props.rooms[0]?.id ?? 0,
            day: p?.day ?? 1,
            start: hm(sh, sm),
            end: hm(Math.min(sh + 1, 23), sm), // 종료 기본값은 +1시간 (admin-schedule.md)
            type: 1,
            subject: '',
            professor: '',
          },
    )
    errors.value = {}
    formError.value = ''
    initial.value = JSON.stringify(draft)
  },
  { immediate: true },
)

async function save() {
  if (saving.value) return
  errors.value = slotErrors(draft, props.existing, props.value)
  if (errors.value.start || errors.value.end) return
  const [s_h, s_m] = parseHm(draft.start)!
  const [e_h, e_m] = parseHm(draft.end)!
  const slot: SlotIn = {
    day: draft.day,
    s_h,
    s_m,
    e_h,
    e_m,
    type: draft.type,
    subject: draft.subject,
    professor: draft.professor,
    // 웹에서 고친 행은 수동(2) — 포털(1)은 올라가고 긴급(3)은 그대로 (3 에 2 를 보내면 409)
    source: Math.max(2, props.value?.source ?? 2) as SlotSource,
  }
  const key = slotKey({ room_id: draft.roomId, ...slot })
  const old = props.value
  saving.value = true
  formError.value = ''
  try {
    const r = await roomsApi.putSlot(draft.roomId, slot)
    const saved: SavedRow = { roomId: draft.roomId, key, outboxIds: r.outbox_ids }
    // 키(요일·시작)나 방이 바뀌면 PUT 은 새 행을 만든다 — 옛 행을 지운다. 새 행을 먼저 넣어
    // 지우기가 실패해도 데이터가 사라지지 않게 한다 (최악이 중복 한 줄 — 보이고 지울 수 있다)
    if (old && slotKey(old) !== key) {
      try {
        await roomsApi.deleteSlot(old.room_id, old)
      } catch (e) {
        if (!(e instanceof ApiError)) throw e
        if (e.status === 401 || e.status === 403) return
        emit('saved', saved)
        emit('stale')
        showToast({
          tone: 'danger',
          message: '새 슬롯은 저장했지만 옛 슬롯을 지우지 못했습니다. 표에서 지워 주세요.',
        })
        emit('close')
        return
      }
    }
    emit('saved', saved)
    showToast({ message: '저장했습니다.' })
    emit('close')
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 422) formError.value = MESSAGES[422]
    else if (e.status === 409) {
      showToast({ tone: 'danger', message: conflictMessage(e) })
      emit('stale')
    } else if (e.status === 404) {
      showToast({ tone: 'danger', message: '강의실을 찾을 수 없습니다. 목록을 새로 불러옵니다.' })
      emit('stale')
      emit('close')
    } else if (e.status !== 401 && e.status !== 403) formError.value = e.message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Modal
    :open="open"
    :title="mode === 'edit' ? '슬롯 수정' : '슬롯 추가'"
    :close-on-backdrop="!dirty"
    @close="emit('close')"
  >
    <form class="form" novalidate @submit.prevent="save">
      <p v-if="formError" class="form__error" role="alert">{{ formError }}</p>
      <div class="form__grid">
        <Select v-model="draft.roomId" label="강의실" :options="roomOptions" />
        <Select v-model="draft.day" label="요일" :options="DAY_OPTIONS" />
        <Input
          v-model="draft.start"
          label="시작"
          type="time"
          class="num"
          required
          :error="errors.start"
        />
        <Input v-model="draft.end" label="종료" type="time" class="num" required :error="errors.end" />
        <Input v-model="draft.subject" label="과목명" :max-bytes="SUBJ_MAX" />
        <Input v-model="draft.professor" label="교수" :max-bytes="PROF_MAX" />
        <Select v-model="draft.type" label="유형" :options="TYPE_OPTIONS" />
      </div>
      <p v-if="value?.source === 1" class="form__hint">
        저장하면 이 슬롯은 수동 편집으로 바뀌어 CSV 임포트에 덮이지 않습니다.
      </p>
    </form>
    <template #footer>
      <Button
        v-if="removable && mode === 'edit'"
        variant="ghost"
        class="form__remove"
        @click="emit('remove')"
        >삭제</Button
      >
      <Button variant="secondary" @click="emit('close')">취소</Button>
      <Button :loading="saving" @click="save">저장</Button>
    </template>
  </Modal>
</template>

<style scoped>
.form__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3) var(--space-4);
}
.form__error {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-sm);
  color: var(--danger);
}
.form__hint {
  margin: var(--space-3) 0 0;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.form__remove {
  margin-right: auto;
}
</style>
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add web/src/components/domain
git commit -m "feat(web): SlotForm — 겹침·종료>시작·바이트 상한 검사, 키가 바뀌면 새 행 먼저 넣고 옛 행 삭제, 포털→수동 안내·긴급 유지, 409 문장"
```

---

### Task 7: domain — ResvForm

**Files:**
- Create: `web/src/components/domain/resvForm.ts`, `web/src/components/domain/ResvForm.vue`
- Test: `web/src/components/domain/__tests__/resvForm.spec.ts`

**Interfaces:**
- Consumes: `roomsApi.saveResv`(Task 1), rules(Task 2), `parseHm`(Task 6), `kstDateStr`(F3)·`dayOfDate`(Task 2).
- Produces (`resvForm.ts`): `interface ResvDraft { roomId: number; date: string; start: string; end: string; type: SlotType; subject: string; professor: string }` · `resvErrors(d: ResvDraft, existing: ResvWithRoom[], originalId: number | null, today: string): { date?: string; start?: string; end?: string }`.
- Produces (`ResvForm.vue`): props `{ open: boolean; mode?: 'create'|'edit'; rooms: RoomOut[]; roomLabel?: (r: RoomOut) => string; value?: ResvWithRoom | null; preset?: { room_id: number } | null; existing?: ResvWithRoom[] }`, emits `close` · `saved: [row: SavedRow]`(key `r{id}`) · `stale`. 추가는 `id` 없이(서버 채번, 응답 `id` 로 key), 수정은 그 `id` 로.

- [ ] **Step 1: 실패 테스트**

`web/src/components/domain/__tests__/resvForm.spec.ts`
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ResvForm from '@/components/domain/ResvForm.vue'
import { resvErrors, type ResvDraft } from '@/components/domain/resvForm'
import { roomsApi } from '@/api/rooms'
import { ApiError, MESSAGES } from '@/api/client'
import type { ResvWithRoom, RoomOut } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/rooms', () => ({ roomsApi: { saveResv: vi.fn() } }))
const api = vi.mocked(roomsApi)

const rooms: RoomOut[] = [{ id: 11, building_id: 1, room: 401, units: 1, reservable: true }]
const resv = (o: Partial<ResvWithRoom> = {}): ResvWithRoom => ({
  id: 7,
  room_id: 11,
  date: '2026-09-26',
  s_h: 10,
  s_m: 0,
  e_h: 12,
  e_m: 0,
  type: 5,
  subject: '신입생 OT',
  professor: '학생처',
  status: 'approved',
  requester: null,
  pushed_at: null,
  ...o,
})
const draft = (o: Partial<ResvDraft> = {}): ResvDraft => ({
  roomId: 11,
  date: '2026-09-26',
  start: '11:00',
  end: '12:00',
  type: 5,
  subject: '',
  professor: '',
  ...o,
})

let w: VueWrapper
async function mountForm(props: Record<string, unknown> = {}) {
  w = mount(ResvForm, {
    props: { open: true, rooms, preset: { room_id: 11 }, ...props },
    global: { stubs: { teleport: true } },
  })
  await flushPromises()
}
const field = (label: string) =>
  w
    .findAll('.field, .sel')
    .find((f) => f.find('label').exists() && f.get('label').text().replace('*', '').trim() === label)!
const control = (label: string) => field(label).get('input, select')
const save = () => w.findAll('button').find((b) => b.text() === '저장')!.trigger('click')

beforeEach(() => {
  // KST 2026-09-25(금) 12:00
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-09-25T03:00:00Z'))
  api.saveResv.mockReset().mockResolvedValue({ outbox_ids: [5], id: 12 })
  for (const t of [...toasts.value]) dismissToast(t.id)
})
afterEach(() => vi.useRealTimers())

describe('resvErrors', () => {
  it('오늘 이전 날짜·종료 ≤ 시작은 막는다', () => {
    expect(resvErrors(draft({ date: '2026-09-24' }), [], null, '2026-09-25').date).toBe(
      '오늘 이전 날짜에는 만들 수 없습니다',
    )
    expect(resvErrors(draft({ end: '11:00' }), [], null, '2026-09-25').end).toBe(
      '종료는 시작보다 늦어야 합니다 (자정을 넘기지 않습니다)',
    )
  })
  it('같은 방·같은 날 승인·신청 예약과 겹치면 막는다 — 거절·취소·자기 자신은 아니다', () => {
    expect(resvErrors(draft(), [resv()], null, '2026-09-25').end).toBe(
      '겹칩니다: 10:00–12:00 신입생 OT',
    )
    expect(resvErrors(draft(), [resv({ status: 'requested' })], null, '2026-09-25').end).toBe(
      '겹칩니다: 10:00–12:00 신청 · 신입생 OT',
    )
    expect(resvErrors(draft(), [resv({ status: 'rejected' })], null, '2026-09-25')).toEqual({})
    expect(resvErrors(draft(), [resv()], 7, '2026-09-25')).toEqual({})
  })
})

describe('ResvForm', () => {
  it('추가 — id 없이 보내고(서버 채번), 응답 id 로 행 키, 요일은 날짜에서 읽기 전용', async () => {
    await mountForm()
    await control('날짜').setValue('2026-09-26')
    expect((control('요일').element as HTMLInputElement).value).toBe('토')
    expect(control('요일').attributes('readonly')).toBeDefined()
    await control('시작').setValue('16:00')
    await control('종료').setValue('17:00')
    await control('사용 목적').setValue('신입생 OT')
    await save()
    await flushPromises()
    const body = api.saveResv.mock.calls[0][1]
    expect(api.saveResv.mock.calls[0][0]).toBe(11)
    expect(body).not.toHaveProperty('id')
    expect(body).toMatchObject({ date: '2026-09-26', s_h: 16, e_h: 17, subject: '신입생 OT', type: 5 })
    expect(w.emitted('saved')![0]).toEqual([{ roomId: 11, key: 'r12', outboxIds: [5] }])
    expect(toasts.value.at(-1)?.message).toBe('저장했습니다.')
  })

  it('7일 밖이면 저장 전에 hint 로 알리고 막지 않는다 — 빈 outbox_ids 는 실패가 아니다', async () => {
    api.saveResv.mockResolvedValue({ outbox_ids: [], id: 13 })
    await mountForm()
    await control('날짜').setValue('2026-10-05')
    expect(field('날짜').text()).toContain('7일 이내로 들어오면 자동 전송됩니다')
    await save()
    await flushPromises()
    expect(api.saveResv).toHaveBeenCalledTimes(1)
    expect(toasts.value.at(-1)).toMatchObject({
      tone: 'neutral',
      message: '저장했습니다. 7일 이내로 들어오면 자동 전송됩니다.',
    })
  })

  it('지난 날짜는 막는다', async () => {
    await mountForm()
    await control('날짜').setValue('2026-09-24')
    await save()
    await flushPromises()
    expect(api.saveResv).not.toHaveBeenCalled()
    expect(field('날짜').text()).toContain('오늘 이전 날짜에는 만들 수 없습니다')
  })

  it('수정 — 그 id 로, 강의실은 잠근다 (다른 방은 409)', async () => {
    await mountForm({ mode: 'edit', value: resv() })
    expect((control('강의실').element as HTMLSelectElement).disabled).toBe(true)
    expect(w.text()).toContain('다른 강의실로 옮기려면 지우고 다시 만드세요')
    await control('사용 목적').setValue('신입생 OT 2부')
    await save()
    await flushPromises()
    expect(api.saveResv.mock.calls[0][1]).toMatchObject({ id: 7, subject: '신입생 OT 2부' })
  })

  it('409 가득 참 — 사람 문장, 목록 새로 고침, 폼은 열어 둔다', async () => {
    api.saveResv.mockRejectedValue(
      new ApiError(409, MESSAGES[409], [], {
        detail: '이 강의실은 이번 주 예약이 가득 찼습니다(노드 용량 24)',
      }),
    )
    await mountForm()
    await control('날짜').setValue('2026-09-26')
    await save()
    await flushPromises()
    expect(toasts.value.at(-1)).toMatchObject({
      tone: 'danger',
      message: '이 강의실은 7일 안 예약이 가득 찼습니다(24건). 지난 예약을 정리하세요.',
    })
    expect(w.emitted('stale')).toHaveLength(1)
    expect(w.emitted('close')).toBeUndefined()
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/components/domain/__tests__/resvForm.spec.ts`
Expected: FAIL — `Failed to resolve import "@/components/domain/ResvForm.vue"`

- [ ] **Step 3: 구현**

`web/src/components/domain/resvForm.ts`
```ts
import type { ResvWithRoom, SlotType } from '@/api/types'
import { hm } from '@/lib/time'
import { spansOverlap, toMin } from './rules'
import { parseHm } from './slotForm'

export interface ResvDraft {
  roomId: number
  /** <input type="date"> 값 'YYYY-MM-DD' (KST 달력) */
  date: string
  start: string
  end: string
  type: SlotType
  subject: string
  professor: string
}

/** 예약끼리의 겹침만 막는다 — 슬롯과의 겹침은 의도(휴강 위 특강)일 수 있어 페이지2가 보여 준다 (설계 판정) */
export function resvErrors(
  d: ResvDraft,
  existing: ResvWithRoom[],
  originalId: number | null,
  today: string,
): { date?: string; start?: string; end?: string } {
  if (!d.date) return { date: '날짜를 고르세요' }
  if (d.date < today) return { date: '오늘 이전 날짜에는 만들 수 없습니다' }
  const s = parseHm(d.start)
  if (!s) return { start: '시작 시각을 넣으세요' }
  const e = parseHm(d.end)
  if (!e) return { end: '종료 시각을 넣으세요' }
  if (toMin(...e) <= toMin(...s))
    return { end: '종료는 시작보다 늦어야 합니다 (자정을 넘기지 않습니다)' }
  const span = { s_h: s[0], s_m: s[1], e_h: e[0], e_m: e[1] }
  const hit = existing.find(
    (x) =>
      x.room_id === d.roomId &&
      x.date === d.date &&
      x.id !== originalId &&
      (x.status === 'approved' || x.status === 'requested') &&
      spansOverlap(x, span),
  )
  if (!hit) return {}
  const tag = hit.status === 'requested' ? '신청 · ' : ''
  return { end: `겹칩니다: ${hm(hit.s_h, hit.s_m)}–${hm(hit.e_h, hit.e_m)} ${tag}${hit.subject}` }
}
```

`web/src/components/domain/ResvForm.vue`
```vue
<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Modal from '@/components/ui/Modal.vue'
import Select from '@/components/ui/Select.vue'
import { showToast } from '@/components/ui/toast'
import { ApiError, MESSAGES } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { ResvIn, ResvWithRoom, RoomOut } from '@/api/types'
import { dayOfDate, hm, kstDateStr } from '@/lib/time'
import {
  DAYS,
  LATER_HINT,
  PROF_MAX,
  SUBJ_MAX,
  TYPE_OPTIONS,
  conflictMessage,
  resvKey,
  resvWindow,
  type SavedRow,
} from './rules'
import { resvErrors, type ResvDraft } from './resvForm'
import { parseHm } from './slotForm'

const props = withDefaults(
  defineProps<{
    open: boolean
    mode?: 'create' | 'edit'
    rooms: RoomOut[]
    roomLabel?: (r: RoomOut) => string
    value?: ResvWithRoom | null
    preset?: { room_id: number } | null
    existing?: ResvWithRoom[]
  }>(),
  {
    mode: 'create',
    roomLabel: (r: RoomOut) => `${r.room}호`,
    value: null,
    preset: null,
    existing: () => [],
  },
)
const emit = defineEmits<{ close: []; saved: [row: SavedRow]; stale: [] }>()

const draft = reactive<ResvDraft>({
  roomId: 0,
  date: '',
  start: '10:00',
  end: '11:00',
  type: 5,
  subject: '',
  professor: '',
})
const errors = ref<{ date?: string; start?: string; end?: string }>({})
const formError = ref('')
const saving = ref(false)
const initial = ref('')
const today = ref(kstDateStr(new Date()))
const dirty = computed(() => JSON.stringify(draft) !== initial.value)
const roomOptions = computed(() => props.rooms.map((r) => ({ value: r.id, label: props.roomLabel(r) })))
// 요일은 서버 필드가 아니다 — 날짜에서 계산해 읽기 전용으로 보인다
const weekday = computed(() => (draft.date ? DAYS[dayOfDate(draft.date) - 1] : ''))
const later = computed(() => !!draft.date && resvWindow(draft.date, today.value) === 'later')

watch(
  () => props.open,
  (open) => {
    if (!open) return
    today.value = kstDateStr(new Date())
    const v = props.value
    Object.assign(
      draft,
      v
        ? {
            roomId: v.room_id,
            date: v.date,
            start: hm(v.s_h, v.s_m),
            end: hm(v.e_h, v.e_m),
            type: v.type,
            subject: v.subject,
            professor: v.professor,
          }
        : {
            roomId: props.preset?.room_id ?? props.rooms[0]?.id ?? 0,
            date: '',
            start: '10:00',
            end: '11:00',
            type: 5,
            subject: '',
            professor: '',
          },
    )
    errors.value = {}
    formError.value = ''
    initial.value = JSON.stringify(draft)
  },
  { immediate: true },
)

async function save() {
  if (saving.value) return
  errors.value = resvErrors(draft, props.existing, props.value?.id ?? null, today.value)
  if (errors.value.date || errors.value.start || errors.value.end) return
  const [s_h, s_m] = parseHm(draft.start)!
  const [e_h, e_m] = parseHm(draft.end)!
  const body: ResvIn = {
    date: draft.date,
    s_h,
    s_m,
    e_h,
    e_m,
    type: draft.type,
    subject: draft.subject,
    professor: draft.professor,
  }
  // 채번하지 않는다 — 추가는 id 없이, 수정만 그 id 로 (S4b §2.5)
  if (props.value) body.id = props.value.id
  saving.value = true
  formError.value = ''
  try {
    const r = await roomsApi.saveResv(draft.roomId, body)
    const id = r.id ?? props.value!.id
    emit('saved', { roomId: draft.roomId, key: resvKey(id), outboxIds: r.outbox_ids })
    // 빈 outbox_ids 는 창 밖(7일) — 실패가 아니다
    showToast({
      message: !r.outbox_ids.length && later.value ? `저장했습니다. ${LATER_HINT}.` : '저장했습니다.',
    })
    emit('close')
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 422) formError.value = MESSAGES[422]
    else if (e.status === 409) {
      showToast({ tone: 'danger', message: conflictMessage(e) })
      emit('stale')
    } else if (e.status === 404) {
      showToast({ tone: 'danger', message: '강의실을 찾을 수 없습니다. 목록을 새로 불러옵니다.' })
      emit('stale')
      emit('close')
    } else if (e.status !== 401 && e.status !== 403) formError.value = e.message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Modal
    :open="open"
    :title="mode === 'edit' ? '예약 수정' : '예약 추가'"
    :close-on-backdrop="!dirty"
    @close="emit('close')"
  >
    <form class="form" novalidate @submit.prevent="save">
      <p v-if="formError" class="form__error" role="alert">{{ formError }}</p>
      <div class="form__grid">
        <Select
          v-model="draft.roomId"
          label="강의실"
          :options="roomOptions"
          :disabled="mode === 'edit'"
        />
        <Select v-model="draft.type" label="유형" :options="TYPE_OPTIONS" />
        <Input
          v-model="draft.date"
          label="날짜"
          type="date"
          class="num"
          required
          :error="errors.date"
          :hint="later ? LATER_HINT : undefined"
        />
        <Input :model-value="weekday" label="요일" readonly tabindex="-1" />
        <Input
          v-model="draft.start"
          label="시작"
          type="time"
          class="num"
          required
          :error="errors.start"
        />
        <Input v-model="draft.end" label="종료" type="time" class="num" required :error="errors.end" />
        <Input v-model="draft.subject" label="사용 목적" :max-bytes="SUBJ_MAX" />
        <Input v-model="draft.professor" label="주관 부서" :max-bytes="PROF_MAX" />
      </div>
      <p v-if="mode === 'edit'" class="form__hint">다른 강의실로 옮기려면 지우고 다시 만드세요.</p>
    </form>
    <template #footer>
      <Button variant="secondary" @click="emit('close')">취소</Button>
      <Button :loading="saving" @click="save">저장</Button>
    </template>
  </Modal>
</template>

<style scoped>
.form__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3) var(--space-4);
}
.form__error {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-sm);
  color: var(--danger);
}
.form__hint {
  margin: var(--space-3) 0 0;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
</style>
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add web/src/components/domain
git commit -m "feat(web): ResvForm — 서버 채번(추가는 id 없이), 7일 밖은 막지 않고 미리 안내, 예약끼리 겹침·지난 날짜 차단, 수정 시 강의실 잠금"
```

---

### Task 8: domain — ExamForm

**Files:**
- Create: `web/src/components/domain/ExamForm.vue`
- Test: `web/src/components/domain/__tests__/examForm.spec.ts`

**Interfaces:**
- Consumes: `roomsApi.saveExam`(Task 1), `examKey`·`SavedRow`(Task 2), Button `loadingLabel`(Task 3).
- Produces: props `{ open: boolean; rooms: RoomOut[]; value?: ExamWithRoom | null; roomLabel?: (r: RoomOut) => string }` — `rooms` 가 **대상**(추가: 트리에서 고른 방 전부, 수정: 그 방 하나 — 부르는 쪽이 넘긴다). emits `close` · `saved: [row: SavedRow]`(방마다, key `x{id}`) · `done: []`(한 번의 적용이 끝남 — 목록 새로 고침).

- [ ] **Step 1: 실패 테스트**

`web/src/components/domain/__tests__/examForm.spec.ts`
```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ExamForm from '@/components/domain/ExamForm.vue'
import Modal from '@/components/ui/Modal.vue'
import { roomsApi } from '@/api/rooms'
import { ApiError, MESSAGES } from '@/api/client'
import type { Enqueued, RoomOut } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/rooms', () => ({ roomsApi: { saveExam: vi.fn() } }))
const api = vi.mocked(roomsApi)

const R = (id: number, room: number): RoomOut => ({
  id,
  building_id: 1,
  room,
  units: 1,
  reservable: false,
})
const rooms = [R(11, 401), R(12, 402), R(13, 405)]
const body = { date_start: '2026-10-19', date_end: '2026-10-23' }

let w: VueWrapper
async function mountForm(props: Record<string, unknown> = {}) {
  w = mount(ExamForm, {
    props: { open: true, rooms, ...props },
    global: { stubs: { teleport: true } },
  })
  await flushPromises()
}
const control = (label: string) =>
  w
    .findAll('.field')
    .find((f) => f.get('label').text().replace('*', '').trim() === label)!
    .get('input')
const submit = () => w.get('.form__submit').trigger('click')
async function fill() {
  await control('시작일').setValue(body.date_start)
  await control('종료일').setValue(body.date_end)
}

beforeEach(() => {
  api.saveExam
    .mockReset()
    .mockImplementation(async (roomId: number) => ({ outbox_ids: [roomId * 10], id: roomId + 100 }))
  for (const t of [...toasts.value]) dismissToast(t.id)
})

describe('ExamForm', () => {
  it('고른 방마다 id 없이 POST (서버 채번) — 방마다 saved, 끝나면 done·close·Toast', async () => {
    await mountForm()
    expect(w.get('.form__submit').text()).toContain('선택한 3곳에 기간 추가')
    await fill()
    await submit()
    await flushPromises()
    expect(api.saveExam.mock.calls).toEqual([
      [11, body],
      [12, body],
      [13, body],
    ])
    expect(w.emitted('saved')!.map((e) => e[0])).toEqual([
      { roomId: 11, key: 'x111', outboxIds: [110] },
      { roomId: 12, key: 'x112', outboxIds: [120] },
      { roomId: 13, key: 'x113', outboxIds: [130] },
    ])
    expect(w.emitted('done')).toHaveLength(1)
    expect(w.emitted('close')).toHaveLength(1)
    expect(toasts.value.at(-1)?.message).toBe('3곳에 시험기간을 넣었습니다.')
  })

  it('진행 라벨 — 한 곳이 끝날 때마다 n/3, 진행 중에는 닫히지 않는다', async () => {
    const release: (() => void)[] = []
    api.saveExam.mockImplementation(
      () => new Promise<Enqueued>((res) => release.push(() => res({ outbox_ids: [1], id: 5 }))),
    )
    await mountForm()
    await fill()
    await submit()
    await flushPromises()
    expect(w.get('.btn__progress').text()).toBe('0/3 적용 중')
    expect(w.findComponent(Modal).props('closeOnBackdrop')).toBe(false)
    release[0]()
    await flushPromises()
    expect(w.get('.btn__progress').text()).toBe('1/3 적용 중')
  })

  it('일부 실패 — 되돌리지 않고 실패한 방을 말하고, 재시도는 실패한 방만', async () => {
    api.saveExam.mockImplementation(async (roomId: number) => {
      if (roomId === 12) throw new ApiError(500, MESSAGES[500])
      return { outbox_ids: [1], id: roomId + 100 }
    })
    await mountForm()
    await fill()
    await submit()
    await flushPromises()
    const t = toasts.value.at(-1)!
    expect(t).toMatchObject({ tone: 'danger', message: '3개 중 2개 적용 · 402호 실패' })
    api.saveExam.mockClear()
    api.saveExam.mockResolvedValue({ outbox_ids: [1], id: 112 })
    t.action!.onClick()
    await flushPromises()
    expect(api.saveExam.mock.calls).toEqual([[12, body]])
    expect(toasts.value.at(-1)?.message).toBe('저장했습니다.')
  })

  it('수정 — 그 id 로, 넘겨받은 그 방 하나만', async () => {
    await mountForm({
      rooms: [rooms[1]],
      value: { id: 40, room_id: 12, date_start: '2026-10-19', date_end: '2026-10-20' },
    })
    expect(w.get('.form__submit').text()).toContain('저장')
    await control('종료일').setValue('2026-10-23')
    await submit()
    await flushPromises()
    expect(api.saveExam.mock.calls).toEqual([
      [12, { id: 40, date_start: '2026-10-19', date_end: '2026-10-23' }],
    ])
  })

  it('종료일이 시작일보다 앞이면 막는다', async () => {
    await mountForm()
    await control('시작일').setValue('2026-10-23')
    await control('종료일').setValue('2026-10-19')
    await submit()
    await flushPromises()
    expect(api.saveExam).not.toHaveBeenCalled()
    expect(w.text()).toContain('종료일은 시작일과 같거나 뒤여야 합니다')
  })

  it('고른 방이 없으면 버튼이 잠긴다', async () => {
    await mountForm({ rooms: [] })
    expect((w.get('.form__submit').element as HTMLButtonElement).disabled).toBe(true)
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/components/domain/__tests__/examForm.spec.ts`
Expected: FAIL — `Failed to resolve import "@/components/domain/ExamForm.vue"`

- [ ] **Step 3: 구현**

`web/src/components/domain/ExamForm.vue`
```vue
<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Modal from '@/components/ui/Modal.vue'
import { showToast } from '@/components/ui/toast'
import { ApiError } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { ExamIn, ExamWithRoom, RoomOut } from '@/api/types'
import { examKey, type SavedRow } from './rules'

const props = withDefaults(
  defineProps<{
    open: boolean
    /** 대상 — 추가는 트리에서 고른 방 전부, 수정은 그 방 하나 (폼 안에 강의실 목록을 두지 않는다) */
    rooms: RoomOut[]
    value?: ExamWithRoom | null
    roomLabel?: (r: RoomOut) => string
  }>(),
  { value: null, roomLabel: (r: RoomOut) => `${r.room}호` },
)
const emit = defineEmits<{ close: []; saved: [row: SavedRow]; done: [] }>()

const form = reactive({ start: '', end: '' })
const error = ref('')
const running = ref(false)
const done = ref(0)
const total = ref(0)
const initial = ref('')
const dirty = computed(() => JSON.stringify(form) !== initial.value)
const label = computed(() => (props.value ? '저장' : `선택한 ${props.rooms.length}곳에 기간 추가`))
const progress = computed(() => `${done.value}/${total.value || props.rooms.length} 적용 중`)
const targetText = computed(() => {
  const names = props.rooms.map((r) => props.roomLabel(r))
  return names.length <= 5 ? names.join(', ') : `${names.slice(0, 5).join(', ')} 외 ${names.length - 5}곳`
})

watch(
  () => props.open,
  (open) => {
    if (!open) return
    form.start = props.value?.date_start ?? ''
    form.end = props.value?.date_end ?? ''
    error.value = ''
    initial.value = JSON.stringify(form)
  },
  { immediate: true },
)

function close() {
  if (!running.value) emit('close')
}

async function submit() {
  if (running.value || !props.rooms.length) return
  if (!form.start || !form.end) {
    error.value = '시작일과 종료일을 고르세요'
    return
  }
  if (form.end < form.start) {
    error.value = '종료일은 시작일과 같거나 뒤여야 합니다'
    return
  }
  error.value = ''
  if (await run([...props.rooms], { date_start: form.start, date_end: form.end }, props.value?.id))
    emit('close')
}

/** 방마다 POST — 벌크 엔드포인트가 없다. 일부 실패해도 되돌리지 않는다: 되돌리는 DELETE 도 실패할 수 있어
 * 상태가 더 불분명해진다. 성공분은 두고 실패한 방만 재시도로 남긴다 (admin-rooms.md 시험기간) */
async function run(list: RoomOut[], body: ExamIn, id?: number): Promise<boolean> {
  running.value = true
  total.value = list.length
  done.value = 0
  const failed: RoomOut[] = []
  try {
    for (const r of list) {
      try {
        const res = await roomsApi.saveExam(r.id, id ? { ...body, id } : body)
        emit('saved', { roomId: r.id, key: examKey(res.id ?? id!), outboxIds: res.outbox_ids })
      } catch (e) {
        if (!(e instanceof ApiError)) throw e
        if (e.status === 401 || e.status === 403) return false // 로그인 화면으로 간다
        failed.push(r)
      }
      done.value++
    }
  } finally {
    running.value = false
    emit('done')
  }
  if (!failed.length)
    showToast({ message: list.length > 1 ? `${list.length}곳에 시험기간을 넣었습니다.` : '저장했습니다.' })
  else
    showToast({
      tone: 'danger',
      message: `${list.length}개 중 ${list.length - failed.length}개 적용 · ${failed.map((r) => props.roomLabel(r)).join(', ')} 실패`,
      action: { label: '재시도', onClick: () => void run(failed, body, id) },
    })
  return true
}
</script>

<template>
  <Modal
    :open="open"
    :title="value ? '시험기간 수정' : '시험기간 추가'"
    :close-on-backdrop="!dirty && !running"
    @close="close"
  >
    <form class="form" novalidate @submit.prevent="submit">
      <p class="form__target">
        대상 <span class="num">{{ rooms.length }}</span>곳 · {{ targetText || '없음' }}
      </p>
      <div class="form__grid">
        <Input v-model="form.start" label="시작일" type="date" class="num" required />
        <Input
          v-model="form.end"
          label="종료일"
          type="date"
          class="num"
          required
          :error="error || undefined"
        />
      </div>
    </form>
    <template #footer>
      <Button variant="secondary" :disabled="running" @click="close">취소</Button>
      <!-- 진행 라벨 폭은 Button 이 가장 긴 자리로 미리 잡는다 (Task 3) -->
      <Button
        class="form__submit"
        :loading="running"
        :loading-label="progress"
        :disabled="!rooms.length"
        @click="submit"
        >{{ label }}</Button
      >
    </template>
  </Modal>
</template>

<style scoped>
.form__target {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.form__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3) var(--space-4);
}
</style>
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add web/src/components/domain
git commit -m "feat(web): ExamForm — 트리에서 고른 방마다 순서대로 적용(서버 채번), 진행 라벨 n/N, 일부 실패는 되돌리지 않고 실패한 방만 재시도"
```

---

### Task 9: admin — 저장 뒤 OutboxDot 추적 · 선택 상태

**Files:**
- Create: `web/src/admin/outboxTrack.ts`, `web/src/admin/selection.ts`
- Test: `web/src/admin/__tests__/outboxTrack.spec.ts`

**Interfaces:**
- Consumes: `roomsApi.buildingOutbox`(Task 1), `loraApi.syncRoom`(F3), `usePolling`(F1), `DotState`(F3 OutboxDot), `showToast`·`ApiError`.
- Produces (`outboxTrack.ts`): `TRACK_MS = 30_000` · `TRACK_EVERY_MS = 3_000` · `dotOf(o: Pick<OutboxOut, 'state' | 'last_error'>): DotState` · `worst(states: DotState[]): DotState` · `useOutboxTracker(): { states: Map<string, DotState>(reactive); track(key: string, buildingId: number, ids: number[]): void; resync(key: string, roomId: number, buildingId: number): Promise<void> }`.
- Produces (`selection.ts`): `picked: Ref<number[]>`(페이지1 트리 선택) · `weekRoom: Ref<number | null>` · `weekMonday: Ref<string | null>` · `nightPref: Ref<boolean | null>` · `weekendPref: Ref<boolean | null>` — 모듈 메모리(화면을 오가도 남고 새로고침이면 사라진다 — 메모리 세션과 같은 수명). Task 14·18 이 쓰고 그 테스트가 고정한다.

- [ ] **Step 1: 실패 테스트**

`web/src/admin/__tests__/outboxTrack.spec.ts`
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import { dotOf, useOutboxTracker, worst } from '@/admin/outboxTrack'
import { roomsApi } from '@/api/rooms'
import { loraApi } from '@/api/lora'
import { ApiError, MESSAGES } from '@/api/client'
import type { FailedOut } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/rooms', () => ({ roomsApi: { buildingOutbox: vi.fn() } }))
vi.mock('@/api/lora', () => ({ loraApi: { syncRoom: vi.fn() } }))
const api = vi.mocked(roomsApi)
const lora = vi.mocked(loraApi)
const row = (id: number, state: string, last_error: string | null = null) =>
  ({ id, state, last_error }) as unknown as FailedOut

let scope: ReturnType<typeof effectScope>
function start() {
  scope = effectScope()
  return scope.run(() => useOutboxTracker())!
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
  api.buildingOutbox.mockReset()
  lora.syncRoom.mockReset()
  for (const t of [...toasts.value]) dismissToast(t.id)
})
afterEach(() => {
  scope?.stop()
  vi.useRealTimers()
})

describe('dotOf · worst', () => {
  it('관리자 취소는 두 모양(queued→cancelled, dispatched 뒤 failed+cancelled)을 같게 그린다', () => {
    expect(dotOf(row(1, 'cancelled'))).toBe('cancelled')
    expect(dotOf(row(1, 'failed', 'cancelled'))).toBe('cancelled')
    expect(dotOf(row(1, 'failed', 'max_retries'))).toBe('failed')
  })
  it('한 저장이 작업 여럿이면 — 실패 > 취소 > 대기 > 전송 중 > 반영됨', () => {
    expect(worst(['acked', 'queued'])).toBe('queued')
    expect(worst(['acked', 'dispatched'])).toBe('dispatched')
    expect(worst(['acked', 'failed', 'queued'])).toBe('failed')
    expect(worst(['acked', 'acked'])).toBe('acked')
  })
})

describe('useOutboxTracker', () => {
  it('track → 대기로 시작, 3초마다 건물 outbox 에서 찾고, 끝난 상태면 더 묻지 않는다', async () => {
    const t = start()
    api.buildingOutbox.mockResolvedValue([row(7, 'dispatched')])
    t.track('s11-1-9-0', 3, [7])
    expect(t.states.get('s11-1-9-0')).toBe('queued')
    await vi.advanceTimersByTimeAsync(3_000)
    expect(api.buildingOutbox).toHaveBeenCalledWith(3)
    expect(t.states.get('s11-1-9-0')).toBe('dispatched')
    api.buildingOutbox.mockResolvedValue([row(7, 'acked')])
    await vi.advanceTimersByTimeAsync(3_000)
    expect(t.states.get('s11-1-9-0')).toBe('acked')
    api.buildingOutbox.mockClear()
    await vi.advanceTimersByTimeAsync(9_000)
    expect(api.buildingOutbox).not.toHaveBeenCalled()
  })

  it('30초가 지나면 멈추고 점은 마지막 상태로 남는다', async () => {
    const t = start()
    api.buildingOutbox.mockResolvedValue([row(7, 'queued')])
    t.track('r7', 3, [7])
    await vi.advanceTimersByTimeAsync(33_000)
    expect(api.buildingOutbox).toHaveBeenCalledTimes(10)
    api.buildingOutbox.mockClear()
    await vi.advanceTimersByTimeAsync(9_000)
    expect(api.buildingOutbox).not.toHaveBeenCalled()
    expect(t.states.get('r7')).toBe('queued')
  })

  it('빈 outbox_ids 는 추적하지 않는다 — 예정 판정은 화면이 (pushed_at·날짜)', async () => {
    const t = start()
    t.track('r8', 3, [])
    expect(t.states.has('r8')).toBe(false)
    await vi.advanceTimersByTimeAsync(3_000)
    expect(api.buildingOutbox).not.toHaveBeenCalled()
  })

  it('조회가 실패하면 다음 틱에 다시', async () => {
    const t = start()
    api.buildingOutbox
      .mockRejectedValueOnce(new ApiError(0, MESSAGES[0]))
      .mockResolvedValue([row(7, 'failed', 'max_retries')])
    t.track('x7', 3, [7])
    await vi.advanceTimersByTimeAsync(3_000)
    expect(t.states.get('x7')).toBe('queued')
    await vi.advanceTimersByTimeAsync(3_000)
    expect(t.states.get('x7')).toBe('failed')
  })

  it('재전송 — 방 단위 sync 뒤 새 작업을 대기부터 다시 따라간다', async () => {
    const t = start()
    lora.syncRoom.mockResolvedValue({ outbox_ids: [9, 10], id: null })
    await t.resync('s11-1-9-0', 11, 3)
    expect(lora.syncRoom).toHaveBeenCalledWith(11)
    expect(t.states.get('s11-1-9-0')).toBe('queued')
    expect(toasts.value.at(-1)?.message).toBe('다시 보냈습니다.')
    lora.syncRoom.mockRejectedValue(new ApiError(500, MESSAGES[500]))
    await t.resync('s11-1-9-0', 11, 3)
    expect(toasts.value.at(-1)).toMatchObject({ tone: 'danger', message: MESSAGES[500] })
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin/__tests__/outboxTrack.spec.ts`
Expected: FAIL — `Failed to resolve import "@/admin/outboxTrack"`

- [ ] **Step 3: 구현**

`web/src/admin/outboxTrack.ts`
```ts
import { reactive } from 'vue'
import { ApiError } from '@/api/client'
import { loraApi } from '@/api/lora'
import { roomsApi } from '@/api/rooms'
import type { OutboxOut } from '@/api/types'
import type { DotState } from '@/components/domain/OutboxDot.vue'
import { showToast } from '@/components/ui/toast'
import { usePolling } from '@/lib/usePolling'

/** 저장 뒤 이만큼 따라간다 (spec §4.3). 새로고침하면 끊긴다 — 합의 */
export const TRACK_MS = 30_000
export const TRACK_EVERY_MS = 3_000

/** 관리자 취소는 두 모양 — queued 에서 'cancelled', dispatched 뒤엔 'failed' + last_error 'cancelled'. 같게 그린다 */
export const dotOf = (o: Pick<OutboxOut, 'state' | 'last_error'>): DotState =>
  o.state === 'failed' && o.last_error === 'cancelled' ? 'cancelled' : o.state

const RANK: DotState[] = ['failed', 'cancelled', 'queued', 'dispatched', 'acked']
/** 한 저장이 여러 작업(유닛 둘 등)을 만들면 가장 덜 끝난 것 — 실패가 하나라도 있으면 실패 */
export const worst = (states: DotState[]): DotState => RANK.find((s) => states.includes(s)) ?? 'queued'

/** 화면 하나가 쓰는 추적기 — 행 key 마다 점 상태. 건물 outbox(최신 500)를 3초마다 읽는다 */
export function useOutboxTracker() {
  const states = reactive(new Map<string, DotState>())
  const live = new Map<string, { buildingId: number; ids: number[]; until: number }>()

  /** 빈 ids(7일 창 밖 예약)는 추적하지 않는다 — '예정'은 화면이 pushed_at·날짜로 그린다 */
  function track(key: string, buildingId: number, ids: number[]) {
    live.delete(key)
    states.delete(key)
    if (!ids.length) return
    states.set(key, 'queued')
    live.set(key, { buildingId, ids, until: Date.now() + TRACK_MS })
  }

  async function poll() {
    for (const [k, t] of live) if (Date.now() > t.until) live.delete(k) // 점은 마지막 상태로 남는다
    if (!live.size) return
    const byId = new Map<number, OutboxOut>()
    for (const b of new Set([...live.values()].map((t) => t.buildingId))) {
      try {
        for (const o of await roomsApi.buildingOutbox(b)) byId.set(o.id, o)
      } catch (e) {
        if (!(e instanceof ApiError)) throw e // 끊김 — 다음 틱에 다시
      }
    }
    for (const [k, t] of live) {
      const rows = t.ids.map((i) => byId.get(i)).filter((o): o is OutboxOut => !!o)
      if (!rows.length) continue
      const s = worst(rows.map(dotOf))
      states.set(k, s)
      if (s !== 'queued' && s !== 'dispatched') live.delete(k)
    }
  }
  usePolling(poll, TRACK_EVERY_MS)

  /** 실패·취소 행의 재전송 — 방 단위 (POST /rooms/{id}/sync: 시간표·예약·시험기간 전부) */
  async function resync(key: string, roomId: number, buildingId: number) {
    try {
      const r = await loraApi.syncRoom(roomId)
      track(key, buildingId, r.outbox_ids)
      showToast({ message: '다시 보냈습니다.' })
    } catch (e) {
      if (!(e instanceof ApiError)) throw e
      if (e.status !== 401 && e.status !== 403) showToast({ tone: 'danger', message: e.message })
    }
  }

  return { states, track, resync }
}
```

`web/src/admin/selection.ts`
```ts
import { ref } from 'vue'

// 관리자 화면 사이에서 이어지는 선택 — 모듈 메모리라 다른 화면을 다녀와도 남고, 새로고침이면 사라진다
// (JWT 가 메모리에만 있어 새로고침 = 재로그인이라 같은 수명이다)

/** 페이지1 트리에서 고른 강의실 id — 비면 첫 건물의 첫 층으로 채운다 */
export const picked = ref<number[]>([])
/** 페이지2 — 마지막으로 본 강의실(메뉴 링크), 보고 있는 주의 월요일(강의실을 바꿔도 유지) */
export const weekRoom = ref<number | null>(null)
export const weekMonday = ref<string | null>(null)
/** 야간·주말 보기 — null 이면 자동(필요한 블록이 있으면 켬), 사용자가 누르면 그 선택을 유지 */
export const nightPref = ref<boolean | null>(null)
export const weekendPref = ref<boolean | null>(null)
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add web/src/admin/outboxTrack.ts web/src/admin/selection.ts web/src/admin/__tests__/outboxTrack.spec.ts
git commit -m "feat(web): 저장 뒤 OutboxDot 30초 추적(건물 outbox 3초 간격, 취소 두 모양 통일, 방 단위 재전송)과 화면 간 선택 상태"
```

---

### Task 10: admin — ConfirmModal · 마스터 순수 함수

**Files:**
- Create: `web/src/admin/ConfirmModal.vue`, `web/src/admin/masterView.ts`
- Test: `web/src/admin/__tests__/masterView.spec.ts`

**Interfaces:**
- Consumes: `Modal`·`Button`(F1), `volts`(F3 `admin/nodesView.ts`), `WARNING_LABEL`(F3 `NodeStateBadge.vue`), `BuildingOut`·`ModemOut`·`NodeOut`·`RoomOut`·`SlotWithRoom`·`ResvWithRoom`·`ExamWithRoom`.
- Produces (`ConfirmModal.vue`): props `{ open: boolean; title: string; lines: string[]; confirmLabel?: string(='삭제'); danger?: boolean(=true); loading?: boolean }`, emits `confirm` · `close`. 푸터 = `secondary 취소` + (`danger`면 danger, 아니면 primary) 확인.
- Produces (`masterView.ts`): `BLD_MAX = 26` · `RANGE_MAX = 100` · `UNIT_OPTIONS` · `OTHER_SCHOOL_BLD` · `normalizeBld(v: string): string` · `bldProblem(bld, buildings, selfId): string | null` · `usedBlds(buildings): string` · `modemOptions(modems, buildings, selfId): { value: string; label: string }[]` · `modemChangeText(queued: number | null, from: string | null, to: string | null): string` · `roomNodeText(room, nodes): string` · `interface RangeChip { room: number; exists: boolean }` · `rangeProblem(start: string, end: string): string | null` · `rangeRooms(start: number, end: number, existing: number[]): RangeChip[]` · `interface RoomCounts { slots: number; resv: number; exams: number }` · `countFor(roomId, slots, resv, exams): RoomCounts` · `roomDeleteLines(buildingName, room, counts: RoomCounts | null, nodes): string[]`.

- [ ] **Step 1: 실패 테스트**

`web/src/admin/__tests__/masterView.spec.ts`
```ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ConfirmModal from '@/admin/ConfirmModal.vue'
import {
  bldProblem,
  countFor,
  modemChangeText,
  modemOptions,
  normalizeBld,
  rangeProblem,
  rangeRooms,
  roomDeleteLines,
  roomNodeText,
  usedBlds,
} from '@/admin/masterView'
import type { BuildingOut, ModemOut, NodeOut, RoomOut } from '@/api/types'

const B = (id: number, name: string, bld: string, modem_id: string | null = null): BuildingOut => ({
  id,
  school_id: 1,
  name,
  bld,
  modem_id,
})
const R = (id: number, room: number, units = 1): RoomOut => ({
  id,
  building_id: 1,
  room,
  units,
  reservable: false,
})
const M = (modem_id: string): ModemOut => ({
  modem_id,
  agent_ver: null,
  modem_fw: null,
  last_seen_at: null,
  connected: false,
  school_id: 1,
})
const N = (room_id: number, room: number, unit: number, o: Partial<NodeOut> = {}): NodeOut => ({
  room_id,
  building_id: 1,
  building: '공학관',
  bld: 'E',
  room,
  unit,
  modem_id: 'm1',
  mac: null,
  fw: null,
  batt_mv: null,
  rssi: null,
  snr: null,
  sched_ver: null,
  resv_ver: null,
  exam_ver: null,
  ident_ver: null,
  layout: null,
  clock_stale: false,
  low_batt: false,
  uptime_h: null,
  last_seen_at: null,
  last_ack_at: null,
  last_status_at: null,
  sync_state: 'unknown',
  warnings: [],
  ...o,
})
const buildings = [B(1, '공학관', 'E', 'm1'), B(2, '사회관', 'S')]

describe('건물 글자', () => {
  it('친 글자는 대문자 한 글자로 — 영문이 아니면 비운다', () => {
    expect(normalizeBld('e')).toBe('E')
    expect(normalizeBld('ez')).toBe('E')
    expect(normalizeBld('1')).toBe('')
  })
  it('내 학교가 쓰는 글자는 저장 전에 막는다 (자기 자신은 제외)', () => {
    expect(bldProblem('', buildings, null)).toBe('영문 대문자 한 글자를 넣으세요.')
    expect(bldProblem('E', buildings, null)).toBe('이 학교가 이미 쓰는 글자입니다.')
    expect(bldProblem('E', buildings, 1)).toBeNull()
    expect(bldProblem('L', buildings, null)).toBeNull()
    expect(usedBlds(buildings)).toBe('E S')
  })
})

describe('모뎀', () => {
  it('미배정 + 학교 모뎀, 다른 건물이 쓰는 모뎀은 라벨로 알린다', () => {
    expect(modemOptions([M('m1'), M('m2')], buildings, 2)).toEqual([
      { value: '', label: '미배정' },
      { value: 'm1', label: 'm1 · 공학관 사용 중' },
      { value: 'm2', label: 'm2' },
    ])
    expect(modemOptions([M('m1')], buildings, 1)[1].label).toBe('m1')
  })
  it('바꿀 때 문장 — 대기 건수를 숫자로, 옛·새 모뎀 둘 다', () => {
    expect(modemChangeText(7, 'm1', 'm2')).toBe(
      '대기 중 7건이 m2 로 옮겨집니다. 옛 모뎀(m1)과 새 모뎀 양쪽이 설정을 다시 받습니다.',
    )
    expect(modemChangeText(null, null, 'm2')).toBe(
      '대기 중 전송이 m2 로 옮겨집니다. 새 모뎀(m2)이 설정을 받습니다.',
    )
    expect(modemChangeText(500, 'm1', null)).toBe(
      '대기 중 500건 이상이 보낼 모뎀 없이 남습니다. 옛 모뎀(m1)이 설정을 다시 받고, 이 건물 강의실은 갱신을 받지 못합니다.',
    )
  })
})

describe('강의실', () => {
  it('노드 칸 — 단말 없음 / 응답 없음(서버 unseen) / 연결됨 · 가장 낮은 배터리', () => {
    expect(roomNodeText(R(11, 401), [])).toBe('단말 없음')
    expect(roomNodeText(R(11, 401), [N(11, 401, 1, { warnings: ['unseen'] })])).toBe('단말 없음')
    const seen = new Date()
    expect(
      roomNodeText(R(12, 402, 2), [
        N(12, 402, 1, { last_seen_at: seen, batt_mv: 3980 }),
        N(12, 402, 2, { warnings: ['unseen'] }),
      ]),
    ).toBe('응답 없음')
    expect(
      roomNodeText(R(12, 402, 2), [
        N(12, 402, 1, { last_seen_at: seen, batt_mv: 3980 }),
        N(12, 402, 2, { last_seen_at: seen, batt_mv: 3620 }),
      ]),
    ).toBe('연결됨 · 3.62 V')
  })

  it('범위 — 이미 있는 호수는 표시만, 100곳 상한, 거꾸로·빈 값은 문장', () => {
    expect(rangeRooms(501, 505, [503])).toEqual([
      { room: 501, exists: false },
      { room: 502, exists: false },
      { room: 503, exists: true },
      { room: 504, exists: false },
      { room: 505, exists: false },
    ])
    expect(rangeProblem('501', '515')).toBeNull()
    expect(rangeProblem('515', '501')).toBe('끝 호수가 시작 호수보다 작습니다')
    expect(rangeProblem('1', '101')).toBe('한 번에 100곳까지 만들 수 있습니다')
    expect(rangeProblem('0', '5')).toBe('시작·끝 호수를 1~9999 로 넣으세요')
    expect(rangeProblem('5a', '9')).toBe('시작·끝 호수를 1~9999 로 넣으세요')
  })

  it('삭제 문장 — 딸린 개수(살아 있는 예약만), 단말이 붙은 유닛', () => {
    const counts = countFor(
      11,
      [{ room_id: 11 }, { room_id: 11 }, { room_id: 12 }] as never,
      [
        { room_id: 11, status: 'approved' },
        { room_id: 11, status: 'rejected' },
      ] as never,
      [],
    )
    expect(counts).toEqual({ slots: 2, resv: 1, exams: 0 })
    expect(roomDeleteLines('공학관', R(11, 401), counts, [N(11, 401, 1, { mac: 'AA' })])).toEqual([
      '공학관 401호를 지웁니다.',
      '시간표 2건 · 예약 1건이 함께 지워집니다.',
      '문 앞 단말(unit 1)은 갱신을 받지 못하게 됩니다.',
    ])
    expect(roomDeleteLines('공학관', R(11, 401), { slots: 0, resv: 0, exams: 0 }, [])).toEqual([
      '공학관 401호를 지웁니다.',
      '딸린 시간표·예약·시험기간이 없습니다.',
    ])
    expect(roomDeleteLines('공학관', R(11, 401), null, [])[1]).toBe(
      '딸린 시간표·예약 수를 불러오지 못했습니다. 있으면 함께 지워집니다.',
    )
  })
})

describe('ConfirmModal', () => {
  it('지울 대상을 그대로 적고, 확인 버튼은 danger (danger=false 면 primary)', async () => {
    const w = mount(ConfirmModal, {
      props: { open: true, title: '건물 삭제', lines: ['공학관(E) 건물을 지웁니다.'] },
      global: { stubs: { teleport: true } },
    })
    expect(w.text()).toContain('공학관(E) 건물을 지웁니다.')
    const ok = w.findAll('button').find((b) => b.text() === '삭제')!
    expect(ok.classes()).toContain('btn--danger')
    await ok.trigger('click')
    expect(w.emitted('confirm')).toHaveLength(1)
    await w.setProps({ danger: false, confirmLabel: '바꾸기' })
    expect(w.findAll('button').find((b) => b.text() === '바꾸기')!.classes()).toContain(
      'btn--primary',
    )
    await w.findAll('button').find((b) => b.text() === '취소')!.trigger('click')
    expect(w.emitted('close')).toHaveLength(1)
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin/__tests__/masterView.spec.ts`
Expected: FAIL — `Failed to resolve import "@/admin/ConfirmModal.vue"`

- [ ] **Step 3: 구현**

`web/src/admin/ConfirmModal.vue`
```vue
<script setup lang="ts">
import Button from '@/components/ui/Button.vue'
import Modal from '@/components/ui/Modal.vue'

// 확인 모달 — 본문에 지울 대상을 그대로 적는다. danger 는 여기서만 (components.md Modal·Button)
withDefaults(
  defineProps<{
    open: boolean
    title: string
    lines: string[]
    confirmLabel?: string
    danger?: boolean
    loading?: boolean
  }>(),
  { confirmLabel: '삭제', danger: true, loading: false },
)
const emit = defineEmits<{ confirm: []; close: [] }>()
</script>

<template>
  <Modal :open="open" :title="title" size="sm" @close="emit('close')">
    <p v-for="(line, i) in lines" :key="i" class="confirm__line">{{ line }}</p>
    <template #footer>
      <Button variant="secondary" @click="emit('close')">취소</Button>
      <Button :variant="danger ? 'danger' : 'primary'" :loading="loading" @click="emit('confirm')">{{
        confirmLabel
      }}</Button>
    </template>
  </Modal>
</template>

<style scoped>
.confirm__line {
  margin: 0 0 var(--space-2);
}
</style>
```

`web/src/admin/masterView.ts`
```ts
import type {
  BuildingOut,
  ExamWithRoom,
  ModemOut,
  NodeOut,
  ResvWithRoom,
  RoomOut,
  SlotWithRoom,
} from '@/api/types'
import { WARNING_LABEL } from '@/components/domain/NodeStateBadge.vue'
import { volts } from './nodesView'

/** bld 는 대문자 한 글자이고 학교가 달라도 겹칠 수 없다 — 건물은 26개가 상한 (admin-master.md) */
export const BLD_MAX = 26
/** 범위로 추가 한 번에 — 1–9999 를 잘못 넣어 9999번 POST 가 나가지 않게 (설계 판정) */
export const RANGE_MAX = 100
export const UNIT_OPTIONS = [
  { value: 1, label: '1 (문 하나)' },
  { value: 2, label: '2 (문 둘)' },
]
export const OTHER_SCHOOL_BLD = '다른 학교가 이미 쓰는 글자입니다. 다른 글자를 고르세요.'

/** 입력 칸은 친 글자를 대문자로 — 대소문자가 섞이면 CSV·e-Paper 푸터에서 헷갈린다 */
export const normalizeBld = (v: string) =>
  v
    .toUpperCase()
    .replace(/[^A-Z]/g, '')
    .slice(0, 1)

/** 내 학교 것만 미리 막는다 — 다른 학교 글자는 저장할 때 409 로만 안다 */
export function bldProblem(bld: string, buildings: BuildingOut[], selfId: number | null): string | null {
  if (!/^[A-Z]$/.test(bld)) return '영문 대문자 한 글자를 넣으세요.'
  if (buildings.some((b) => b.id !== selfId && b.bld.toUpperCase() === bld))
    return '이 학교가 이미 쓰는 글자입니다.'
  return null
}
export const usedBlds = (buildings: BuildingOut[]) => buildings.map((b) => b.bld).join(' ')

/** 그 학교 모뎀만 (서버가 이미 거른다). 다른 건물이 쓰는 모뎀도 고를 수 있지만 라벨로 알린다 */
export function modemOptions(modems: ModemOut[], buildings: BuildingOut[], selfId: number | null) {
  return [
    { value: '', label: '미배정' },
    ...modems.map((m) => {
      const other = buildings.find((b) => b.id !== selfId && b.modem_id === m.modem_id)
      return { value: m.modem_id, label: other ? `${m.modem_id} · ${other.name} 사용 중` : m.modem_id }
    }),
  ]
}

/** 모뎀을 바꾸면 서버가 대기 전송을 옮기고 양쪽에 config 를 다시 내린다 — 건수를 숫자로 적는다 */
export function modemChangeText(queued: number | null, from: string | null, to: string | null): string {
  const n = queued === null ? '전송' : queued >= 500 ? '500건 이상' : `${queued}건`
  const move = to ? `대기 중 ${n}이 ${to} 로 옮겨집니다.` : `대기 중 ${n}이 보낼 모뎀 없이 남습니다.`
  const config =
    from && to
      ? `옛 모뎀(${from})과 새 모뎀 양쪽이 설정을 다시 받습니다.`
      : from
        ? `옛 모뎀(${from})이 설정을 다시 받고, 이 건물 강의실은 갱신을 받지 못합니다.`
        : `새 모뎀(${to})이 설정을 받습니다.`
  return `${move} ${config}`
}

/** 마스터 표의 노드 칸 — 판정은 서버(warnings), 문구는 노드 화면과 같다 */
export function roomNodeText(room: RoomOut, nodes: NodeOut[]): string {
  const mine = nodes.filter((n) => n.room_id === room.id)
  if (!mine.some((n) => n.last_seen_at)) return '단말 없음'
  if (mine.some((n) => n.warnings.includes('unseen'))) return WARNING_LABEL.unseen
  const mv = mine.map((n) => n.batt_mv).filter((v): v is number => v !== null)
  return mv.length ? `연결됨 · ${volts(Math.min(...mv))}` : '연결됨'
}

export interface RangeChip {
  room: number
  exists: boolean
}
export function rangeProblem(start: string, end: string): string | null {
  const ok = (v: string) => /^\d+$/.test(v) && Number(v) >= 1 && Number(v) <= 9999
  if (!ok(start) || !ok(end)) return '시작·끝 호수를 1~9999 로 넣으세요'
  if (Number(end) < Number(start)) return '끝 호수가 시작 호수보다 작습니다'
  if (Number(end) - Number(start) + 1 > RANGE_MAX) return `한 번에 ${RANGE_MAX}곳까지 만들 수 있습니다`
  return null
}
/** 범위 문법을 늘리지 않는다 — 칩으로 보이고 눌러서 뺀다. 이미 있는 호수는 표시만 (admin-master.md) */
export function rangeRooms(start: number, end: number, existing: number[]): RangeChip[] {
  return Array.from({ length: end - start + 1 }, (_, i) => ({
    room: start + i,
    exists: existing.includes(start + i),
  }))
}

export interface RoomCounts {
  slots: number
  resv: number
  exams: number
}
/** 강의실 삭제 확인에 적을 개수 — 건물 단위 조회를 room_id 로 센다 (admin-master.md 미결 3). 예약은 살아 있는 것만 */
export function countFor(
  roomId: number,
  slots: SlotWithRoom[],
  resv: ResvWithRoom[],
  exams: ExamWithRoom[],
): RoomCounts {
  return {
    slots: slots.filter((s) => s.room_id === roomId).length,
    resv: resv.filter(
      (r) => r.room_id === roomId && (r.status === 'approved' || r.status === 'requested'),
    ).length,
    exams: exams.filter((x) => x.room_id === roomId).length,
  }
}
export function roomDeleteLines(
  buildingName: string,
  room: RoomOut,
  counts: RoomCounts | null,
  nodes: NodeOut[],
): string[] {
  const lines = [`${buildingName} ${room.room}호를 지웁니다.`]
  if (!counts) lines.push('딸린 시간표·예약 수를 불러오지 못했습니다. 있으면 함께 지워집니다.')
  else {
    const parts = [
      counts.slots ? `시간표 ${counts.slots}건` : '',
      counts.resv ? `예약 ${counts.resv}건` : '',
      counts.exams ? `시험기간 ${counts.exams}건` : '',
    ].filter((x) => x)
    lines.push(
      parts.length ? `${parts.join(' · ')}이 함께 지워집니다.` : '딸린 시간표·예약·시험기간이 없습니다.',
    )
  }
  const units = nodes.filter((n) => n.room_id === room.id && n.mac).map((n) => n.unit)
  if (units.length) lines.push(`문 앞 단말(unit ${units.join(', ')})은 갱신을 받지 못하게 됩니다.`)
  return lines
}
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add web/src/admin/ConfirmModal.vue web/src/admin/masterView.ts web/src/admin/__tests__/masterView.spec.ts
git commit -m "feat(web): 확인 모달과 건물·강의실 규칙 — 대문자 bld·내 학교 중복, 모뎀 변경 문장(대기 건수), 노드 칸, 범위 칩(100곳 상한), 삭제 개수 문장"
```

---

### Task 11: 건물 · 강의실 A — 화면 · 건물 패널 · 메뉴 · 학교 표시 + E2E

**Files:**
- Create: `web/src/admin/views/MasterView.vue`, `web/src/admin/views/master/BuildingPanel.vue`, `web/e2e/admin-ops.spec.ts`
- Modify: `web/src/admin/router.ts`, `web/src/admin/AdminShell.vue`, `web/src/admin/__tests__/shell.spec.ts`, `web/e2e/helpers.ts`, `web/e2e/admin-shell.spec.ts`
- Test: `web/src/admin/__tests__/master.spec.ts`

**Interfaces:**
- Consumes: `roomsApi.{schools, buildings, rooms, createBuilding, patchBuilding, deleteBuilding, buildingOutbox}`(Task 1) · `loraApi.modems`·`adminApi.nodes`(F3) · `ConfirmModal`·`masterView.ts`(Task 10) · `detailText`(Task 2) · Table `tall`(Task 3) · `session`(F1 — `school_id`) · `useResource`·`Banner`·`EmptyState`·`Badge`·`Input`·`Select`·`Modal`·`showToast`(F1). E2E: `WEB_URL`·`SIZES`·`apiLogin`·`fillLogin`·`nextAdmin`·`shot`(F1·F3 helpers), `cfg.OTHER_ADMIN`(F3).
- Produces: 라우트 `/master`. 메뉴 맨 위 `건물 · 강의실`. 사이드바 아래 `{학교} · net_id {n}` + `학교는 CLI 에서만 만든다`.
- Produces (`MasterView.vue`): 리소스 `{ buildings, rooms, modems, nodes }` 하나, `selectedId`. Task 12·13 이 오른쪽 패널을 끼운다.
- Produces (`BuildingPanel.vue`): props `{ buildings?: BuildingOut[]; rooms: RoomOut[]; modems: ModemOut[]; loading: boolean; selectedId: number | null }`, emits `select: [id: number]` · `changed: []`. 루트 `<section aria-labelledby="master-bld">`(h2 `건물`). Modal 제목 `건물 추가`·`건물 수정`, 확인 `모뎀 변경`·`건물 삭제`. 입력 라벨 `이름`·`글자`·`모뎀`.
- Produces (`e2e/helpers.ts`): `kstDate(offsetDays?: number): string` · `ensureModems(request, ids: string[]): Promise<void>`.
- Produces (`e2e/admin-ops.spec.ts`): 공유 `page`(우리 학교, `/admin/master` 에서 로그인)·`otherPage`(다른 학교)·`api`. Task 12~18 이 파일 끝에 테스트를 더한다.

- [ ] **Step 1: 실패 테스트**

`web/src/admin/__tests__/master.spec.ts`
```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import MasterView from '@/admin/views/MasterView.vue'
import { roomsApi } from '@/api/rooms'
import { loraApi } from '@/api/lora'
import { adminApi } from '@/api/admin'
import { ApiError, MESSAGES } from '@/api/client'
import type { BuildingOut, FailedOut, ModemOut, RoomOut } from '@/api/types'
import { setSession } from '@/lib/session'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/rooms', () => ({
  roomsApi: {
    buildings: vi.fn(),
    rooms: vi.fn(),
    createBuilding: vi.fn(),
    patchBuilding: vi.fn(),
    deleteBuilding: vi.fn(),
    buildingOutbox: vi.fn(),
    createRoom: vi.fn(),
    patchRoom: vi.fn(),
    deleteRoom: vi.fn(),
    buildingSlots: vi.fn(),
    buildingResv: vi.fn(),
    buildingExams: vi.fn(),
  },
}))
vi.mock('@/api/lora', () => ({ loraApi: { modems: vi.fn() } }))
vi.mock('@/api/admin', () => ({ adminApi: { nodes: vi.fn() } }))
const rooms = vi.mocked(roomsApi)
const lora = vi.mocked(loraApi)
const admin = vi.mocked(adminApi)

const B = (id: number, name: string, bld: string, modem_id: string | null = null): BuildingOut => ({
  id,
  school_id: 1,
  name,
  bld,
  modem_id,
})
const R = (id: number, building_id: number, room: number): RoomOut => ({
  id,
  building_id,
  room,
  units: 1,
  reservable: true,
})
const M = (modem_id: string): ModemOut => ({
  modem_id,
  agent_ver: null,
  modem_fw: null,
  last_seen_at: null,
  connected: false,
  school_id: 1,
})

let w: VueWrapper
async function mountView() {
  w = mount(MasterView, { global: { stubs: { teleport: true } } })
  await flushPromises()
}
type Root = VueWrapper | DOMWrapper<Element>
const btn = (root: Root, text: string) => root.findAll('button').find((b) => b.text() === text)!
const dialog = (title: string) =>
  w.findAll('[role=dialog]').find((d) => d.get('h2').text() === title)
const control = (root: Root, label: string) =>
  root
    .findAll('.field, .sel')
    .find((f) => f.find('label').exists() && f.get('label').text().replace('*', '').trim() === label)!
    .get('input, select')
const row = (name: string) => w.findAll('tbody tr').find((r) => r.text().includes(name))!

beforeEach(() => {
  Object.values(rooms).forEach((f) => f.mockReset())
  rooms.buildings.mockResolvedValue([B(1, '공학관', 'E', 'm1'), B(2, '사회관', 'S')])
  rooms.rooms.mockResolvedValue([R(11, 1, 401), R(12, 1, 402)])
  rooms.createBuilding.mockResolvedValue(B(3, '도서관', 'L'))
  rooms.patchBuilding.mockResolvedValue(B(1, '공학관', 'E', 'm2'))
  rooms.deleteBuilding.mockResolvedValue({ ok: true })
  lora.modems.mockResolvedValue([M('m1'), M('m2')])
  admin.nodes.mockResolvedValue([])
  setSession({ token: 't', role: 'admin', school_id: 1, name: '관리자1' })
  for (const t of [...toasts.value]) dismissToast(t.id)
})

describe('건물 패널', () => {
  it('n / 26, 미배정은 적색 테두리 배지, 첫 건물이 골라져 있다', async () => {
    await mountView()
    expect(w.get('#master-bld').text()).toBe('건물')
    expect(w.text()).toContain('2 / 26')
    const badge = row('사회관').get('.badge')
    expect(badge.text()).toBe('미배정')
    expect(badge.classes()).toEqual(expect.arrayContaining(['badge--danger', 'badge--outline']))
    expect(btn(row('공학관'), '공학관').attributes('aria-pressed')).toBe('true')
  })

  it('추가 — 친 글자는 대문자로, school_id 는 로그인 응답의 것', async () => {
    await mountView()
    await btn(w, '+ 건물').trigger('click')
    const d = dialog('건물 추가')!
    await control(d, '이름').setValue('도서관')
    await control(d, '글자').setValue('l')
    expect((control(d, '글자').element as HTMLInputElement).value).toBe('L')
    await btn(d, '저장').trigger('click')
    await flushPromises()
    expect(rooms.createBuilding).toHaveBeenCalledWith({
      school_id: 1,
      name: '도서관',
      bld: 'L',
      modem_id: null,
    })
    expect(dialog('건물 추가')).toBeUndefined()
    expect(rooms.buildings).toHaveBeenCalledTimes(2)
  })

  it('이 학교가 쓰는 글자는 저장 전에 막는다 — 쓰는 중 글자를 적어 둔다', async () => {
    await mountView()
    await btn(w, '+ 건물').trigger('click')
    const d = dialog('건물 추가')!
    expect(d.text()).toContain('쓰는 중: E S')
    await control(d, '이름').setValue('별관')
    await control(d, '글자').setValue('e')
    await btn(d, '저장').trigger('click')
    await flushPromises()
    expect(rooms.createBuilding).not.toHaveBeenCalled()
    expect(d.text()).toContain('이 학교가 이미 쓰는 글자입니다.')
  })

  it('다른 학교가 쓰는 글자는 409 — Toast 가 아니라 글자 칸에, 나머지 입력은 그대로', async () => {
    rooms.createBuilding.mockRejectedValue(
      new ApiError(409, MESSAGES[409], [], {
        detail: "bld 'Z' 는 다른 학교가 쓰고 있습니다 (공중 주소는 전역)",
      }),
    )
    await mountView()
    await btn(w, '+ 건물').trigger('click')
    const d = dialog('건물 추가')!
    await control(d, '이름').setValue('타학교관')
    await control(d, '글자').setValue('z')
    await btn(d, '저장').trigger('click')
    await flushPromises()
    expect(dialog('건물 추가')!.text()).toContain(
      '다른 학교가 이미 쓰는 글자입니다. 다른 글자를 고르세요.',
    )
    expect((control(dialog('건물 추가')!, '이름').element as HTMLInputElement).value).toBe('타학교관')
    expect(toasts.value).toHaveLength(0)
  })

  it('강의실이 있는 건물은 글자 칸이 읽기 전용 — 바꾸는 길을 적는다', async () => {
    await mountView()
    await btn(row('공학관'), '수정').trigger('click')
    const d = dialog('건물 수정')!
    expect(control(d, '글자').attributes('readonly')).toBeDefined()
    expect(d.text()).toContain('강의실이 있는 건물은 글자를 바꿀 수 없습니다.')
  })

  it('모뎀이 바뀌면 대기 건수로 확인 — 확인해야 modem_id 만 보낸다', async () => {
    rooms.buildingOutbox.mockResolvedValue(Array.from({ length: 7 }, () => ({}) as FailedOut))
    await mountView()
    await btn(row('공학관'), '수정').trigger('click')
    const d = dialog('건물 수정')!
    await control(d, '모뎀').setValue('m2')
    await btn(d, '저장').trigger('click')
    await flushPromises()
    expect(rooms.buildingOutbox).toHaveBeenCalledWith(1, 'queued')
    const c = dialog('모뎀 변경')!
    expect(c.text()).toContain(
      '대기 중 7건이 m2 로 옮겨집니다. 옛 모뎀(m1)과 새 모뎀 양쪽이 설정을 다시 받습니다.',
    )
    expect(rooms.patchBuilding).not.toHaveBeenCalled()
    await btn(c, '바꾸기').trigger('click')
    await flushPromises()
    expect(rooms.patchBuilding).toHaveBeenCalledWith(1, { modem_id: 'm2' })
    expect(dialog('모뎀 변경')).toBeUndefined()
    expect(dialog('건물 수정')).toBeUndefined()
  })

  it('이름만 바꾸면 묻지 않는다', async () => {
    await mountView()
    await btn(row('공학관'), '수정').trigger('click')
    const d = dialog('건물 수정')!
    await control(d, '이름').setValue('공학1관')
    await btn(d, '저장').trigger('click')
    await flushPromises()
    expect(dialog('모뎀 변경')).toBeUndefined()
    expect(rooms.buildingOutbox).not.toHaveBeenCalled()
    expect(rooms.patchBuilding).toHaveBeenCalledWith(1, { name: '공학1관' })
  })

  it('삭제 — 강의실이 있으면 잠기고 이유는 툴팁, 없으면 확인 뒤 지운다', async () => {
    await mountView()
    const locked = btn(row('공학관'), '삭제')
    expect((locked.element as HTMLButtonElement).disabled).toBe(true)
    expect(locked.element.parentElement!.getAttribute('title')).toBe('강의실을 먼저 지우세요 (2곳)')
    await btn(row('사회관'), '삭제').trigger('click')
    const c = dialog('건물 삭제')!
    expect(c.text()).toContain('사회관(S) 건물을 지웁니다.')
    await btn(c, '삭제').trigger('click')
    await flushPromises()
    expect(rooms.deleteBuilding).toHaveBeenCalledWith(2)
  })

  it('26개면 + 건물 잠금, 0개면 설치 순서 안내', async () => {
    rooms.buildings.mockResolvedValue(
      Array.from({ length: 26 }, (_, i) => B(i + 1, `건물${i}`, String.fromCharCode(65 + i))),
    )
    await mountView()
    expect((btn(w, '+ 건물').element as HTMLButtonElement).disabled).toBe(true)
    w.unmount()
    rooms.buildings.mockResolvedValue([])
    rooms.rooms.mockResolvedValue([])
    await mountView()
    expect(w.text()).toContain('건물을 먼저 만드세요')
    expect(w.text()).toContain('강의실을 범위로 추가합니다.')
  })
})
```

`web/src/admin/__tests__/shell.spec.ts`
1. `vi.mock('@/api/users', …)` 줄 **아래**에 추가:
```ts
vi.mock('@/api/rooms', () => ({
  roomsApi: { schools: vi.fn(async () => [{ id: 1, name: '우송대', net_id: 75 }]) },
}))
```
2. 첫 `it`(F3 Task 9 에서 바꾼 `'/ 는 /dashboard 로, 메뉴 순서(#46) · 전송 현황 활성 · 회원 대기 건수'`)를 통째로 바꾼다:
```ts
  it('/ 는 /dashboard 로, 메뉴 순서(#46) · 전송 현황 활성 · 회원 대기 건수 · 학교 읽기 전용', async () => {
    const { w, router } = await mountApp('/')
    expect(router.currentRoute.value.path).toBe('/dashboard')
    expect(list).toHaveBeenCalledWith('pending_approval')
    const links = w.findAll('nav a')
    expect(links.map((a) => a.text().replace(/\d+/g, '').trim())).toEqual([
      '건물 · 강의실',
      '노드 상태',
      '전송 현황',
      '회원',
    ])
    expect(links[2].attributes('aria-current')).toBe('page')
    expect(links[3].text()).toContain('2')
    expect(w.text()).toContain('우송대 · net_id 75')
    expect(w.text()).toContain('학교는 CLI 에서만 만든다')
    expect(w.text()).toContain('관리자1')
  })
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin`
Expected: FAIL — `Failed to resolve import "@/admin/views/MasterView.vue"`, shell.spec `expected [ '노드 상태', '전송 현황', '회원' ] to deeply equal [ '건물 · 강의실', … ]`

- [ ] **Step 3: 구현**

`web/src/admin/views/master/BuildingPanel.vue`
```vue
<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Input from '@/components/ui/Input.vue'
import Modal from '@/components/ui/Modal.vue'
import Select from '@/components/ui/Select.vue'
import Table from '@/components/ui/Table.vue'
import { showToast } from '@/components/ui/toast'
import { detailText } from '@/components/domain/rules'
import { ApiError, MESSAGES } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { BuildingOut, BuildingPatch, ModemOut, RoomOut } from '@/api/types'
import { session } from '@/lib/session'
import ConfirmModal from '../../ConfirmModal.vue'
import {
  BLD_MAX,
  OTHER_SCHOOL_BLD,
  bldProblem,
  modemChangeText,
  modemOptions,
  normalizeBld,
  usedBlds,
} from '../../masterView'

const props = defineProps<{
  buildings?: BuildingOut[]
  rooms: RoomOut[]
  modems: ModemOut[]
  loading: boolean
  selectedId: number | null
}>()
const emit = defineEmits<{ select: [id: number]; changed: [] }>()

const list = computed(() => props.buildings ?? [])
const full = computed(() => list.value.length >= BLD_MAX)
const roomCount = (id: number) => props.rooms.filter((r) => r.building_id === id).length
const rows = computed(() => list.value.map((b) => ({ ...b, rooms: roomCount(b.id) })))
const COLUMNS = [
  { key: 'bld', label: '글자', width: '52px' },
  { key: 'name', label: '이름' },
  { key: 'modem_id', label: '모뎀', width: '104px' },
  { key: 'rooms', label: '방', width: '48px', align: 'right' as const },
  { key: 'actions', label: '작업', width: '92px' },
]
const asB = (row: Record<string, unknown>) => row as unknown as BuildingOut & { rooms: number }

// ---- 추가·수정 폼 ----
const editing = ref<BuildingOut | null>(null)
const formOpen = ref(false)
const form = reactive({ name: '', bld: '', modem: '' })
const errors = reactive<{ name?: string; bld?: string; form?: string }>({})
const saving = ref(false)
const initial = ref('')
const dirty = computed(() => JSON.stringify(form) !== initial.value)
// bld 는 무선 주소 — 강의실이 생기면 잠긴다 (노드 NVS 가 (bld, room, unit) 을 들고 있다)
const bldLocked = computed(() => !!editing.value && roomCount(editing.value.id) > 0)
const others = computed(() => list.value.filter((b) => b.id !== editing.value?.id))
const bldHint = computed(() =>
  bldLocked.value
    ? '강의실이 있는 건물은 글자를 바꿀 수 없습니다. 바꾸려면 강의실을 모두 지우고 다시 만들어야 합니다.'
    : `대문자 한 글자 · 쓰는 중: ${usedBlds(others.value) || '없음'}`,
)

function clearErrors() {
  delete errors.name
  delete errors.bld
  delete errors.form
}
function openForm(b: BuildingOut | null) {
  editing.value = b
  Object.assign(form, { name: b?.name ?? '', bld: b?.bld ?? '', modem: b?.modem_id ?? '' })
  clearErrors()
  initial.value = JSON.stringify(form)
  formOpen.value = true
}
function validate(): boolean {
  clearErrors()
  if (!form.name.trim()) errors.name = '이름을 넣으세요'
  const p = bldLocked.value ? null : bldProblem(form.bld, list.value, editing.value?.id ?? null)
  if (p) errors.bld = p
  return !errors.name && !errors.bld
}

// 모뎀을 바꾸면 서버가 대기 전송을 새 모뎀으로 옮기고 양쪽 모뎀에 config 를 다시 내린다 —
// 이름만 고치러 온 관리자가 드롭다운을 잘못 건드릴 수 있어, 바뀐 경우에만 대기 건수로 묻는다
const modemAsk = ref<string[] | null>(null)
async function submit() {
  if (saving.value || !validate()) return
  const b = editing.value
  if (b && (b.modem_id ?? '') !== form.modem) {
    saving.value = true
    let queued: number | null = null
    try {
      queued = (await roomsApi.buildingOutbox(b.id, 'queued')).length
    } catch (e) {
      if (!(e instanceof ApiError)) throw e // 건수를 못 세도 묻기는 한다
    } finally {
      saving.value = false
    }
    modemAsk.value = [modemChangeText(queued, b.modem_id, form.modem || null)]
    return
  }
  await save()
}

async function save() {
  const b = editing.value
  saving.value = true
  try {
    if (b) {
      // 부분 수정 — 바뀐 필드만 보낸다
      const patch: BuildingPatch = {}
      if (form.name.trim() !== b.name) patch.name = form.name.trim()
      if (!bldLocked.value && form.bld !== b.bld) patch.bld = form.bld
      if (form.modem !== (b.modem_id ?? '')) patch.modem_id = form.modem || null
      if (Object.keys(patch).length) await roomsApi.patchBuilding(b.id, patch)
    } else {
      const created = await roomsApi.createBuilding({
        school_id: session.value!.school_id, // 내 학교가 아니면 서버가 404
        name: form.name.trim(),
        bld: form.bld,
        modem_id: form.modem || null,
      })
      emit('select', created.id)
    }
    modemAsk.value = null
    formOpen.value = false
    showToast({ message: '저장했습니다.' })
    emit('changed')
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    modemAsk.value = null
    // 다른 학교가 쓰는 글자는 화면이 미리 알 수 없다 — Toast 가 아니라 글자 칸에 붙인다
    if (e.status === 409 && /다른 학교/.test(detailText(e))) errors.bld = OTHER_SCHOOL_BLD
    else if (e.status === 409) {
      errors.bld = '이미 쓰는 글자입니다. 목록을 새로 불러옵니다.'
      emit('changed')
    } else if (e.status === 404) {
      showToast({ tone: 'danger', message: '건물이나 모뎀을 찾을 수 없습니다. 목록을 새로 불러옵니다.' })
      formOpen.value = false
      emit('changed')
    } else if (e.status === 422) errors.form = MESSAGES[422]
    else if (e.status !== 401 && e.status !== 403) errors.form = e.message
  } finally {
    saving.value = false
  }
}

// ---- 삭제 — 강의실 0곳일 때만 (방이 있으면 서버 409, 버튼을 잠가 둔다) ----
const removing = ref<BuildingOut | null>(null)
const removingBusy = ref(false)
async function remove() {
  const b = removing.value
  if (!b || removingBusy.value) return
  removingBusy.value = true
  try {
    await roomsApi.deleteBuilding(b.id)
    showToast({ message: `${b.name}(${b.bld}) 건물을 지웠습니다.` })
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 409)
      showToast({ tone: 'danger', message: '강의실이 남아 있어 지울 수 없습니다. 목록을 새로 불러옵니다.' })
    else if (e.status !== 404 && e.status !== 401 && e.status !== 403)
      showToast({ tone: 'danger', message: e.message })
  } finally {
    removingBusy.value = false
    removing.value = null
    emit('changed')
  }
}
</script>

<template>
  <section class="panel" aria-labelledby="master-bld">
    <header class="panel__head">
      <h2 id="master-bld" class="panel__title">건물</h2>
      <!-- 26개가 상한 — 남은 수를 모르면 26번째에서야 안다 -->
      <span class="panel__count num">{{ list.length }} / {{ BLD_MAX }}</span>
      <span class="panel__tools" :title="full ? '건물은 26개까지입니다' : undefined">
        <Button variant="secondary" size="sm" :disabled="full" @click="openForm(null)">+ 건물</Button>
      </span>
    </header>
    <div v-if="!loading && !list.length" class="panel__empty">
      <EmptyState
        message="건물을 먼저 만드세요"
        :actions="[{ label: '+ 건물', variant: 'primary', onClick: () => openForm(null) }]"
      />
      <!-- 이 시스템의 첫 화면 — 설치 순서가 곧 화면 순서다 -->
      <ol class="panel__steps">
        <li>건물을 만들고 모뎀Pi 를 배정합니다.</li>
        <li>강의실을 범위로 추가합니다.</li>
        <li>노드 상태에서 단말을 배정하고, 강의실 설정에서 시간표를 넣습니다.</li>
      </ol>
    </div>
    <Table
      v-else
      tall
      :columns="COLUMNS"
      :rows="rows as unknown as Record<string, unknown>[]"
      :loading="loading"
      :selected="selectedId === null ? [] : [String(selectedId)]"
    >
      <template #cell-bld="{ row }"
        ><span class="panel__bld">{{ asB(row).bld }}</span></template
      >
      <template #cell-name="{ row }">
        <button
          type="button"
          class="panel__pick"
          :aria-pressed="asB(row).id === selectedId ? 'true' : 'false'"
          @click="emit('select', asB(row).id)"
        >
          {{ asB(row).name }}
        </button>
      </template>
      <template #cell-modem_id="{ row }">
        <span v-if="asB(row).modem_id" class="num">{{ asB(row).modem_id }}</span>
        <!-- 모뎀이 없으면 이 건물 강의실은 갱신을 못 받는다 — 기능이 죽어 있어 적색 -->
        <Badge v-else tone="danger" variant="outline" title="이 건물 강의실은 갱신을 받지 못합니다"
          >미배정</Badge
        >
      </template>
      <template #cell-rooms="{ row }"
        ><span class="num">{{ asB(row).rooms }}</span></template
      >
      <template #cell-actions="{ row }">
        <div class="panel__actions">
          <Button variant="ghost" size="sm" @click="openForm(asB(row))">수정</Button>
          <!-- 비활성 버튼은 마우스 이벤트가 없어 툴팁을 감싼 칸에 단다 -->
          <span :title="asB(row).rooms ? `강의실을 먼저 지우세요 (${asB(row).rooms}곳)` : undefined">
            <Button
              variant="ghost"
              size="sm"
              :disabled="asB(row).rooms > 0"
              @click="removing = asB(row)"
              >삭제</Button
            >
          </span>
        </div>
      </template>
    </Table>

    <Modal
      :open="formOpen"
      :title="editing ? '건물 수정' : '건물 추가'"
      :close-on-backdrop="!dirty"
      @close="formOpen = false"
    >
      <form class="form" novalidate @submit.prevent="submit">
        <p v-if="errors.form" class="form__error" role="alert">{{ errors.form }}</p>
        <Input v-model="form.name" label="이름" required :error="errors.name" />
        <Input
          :model-value="form.bld"
          label="글자"
          required
          maxlength="1"
          autocomplete="off"
          :readonly="bldLocked"
          :error="errors.bld"
          :hint="bldHint"
          @update:model-value="(v: string) => (form.bld = normalizeBld(v))"
        />
        <Select
          v-model="form.modem"
          label="모뎀"
          :options="modemOptions(modems, list, editing?.id ?? null)"
        />
      </form>
      <template #footer>
        <Button variant="secondary" @click="formOpen = false">취소</Button>
        <Button :loading="saving" @click="submit">저장</Button>
      </template>
    </Modal>
    <ConfirmModal
      :open="!!modemAsk"
      title="모뎀 변경"
      :lines="modemAsk ?? []"
      confirm-label="바꾸기"
      :danger="false"
      :loading="saving"
      @confirm="save"
      @close="modemAsk = null"
    />
    <ConfirmModal
      :open="!!removing"
      title="건물 삭제"
      :lines="removing ? [`${removing.name}(${removing.bld}) 건물을 지웁니다.`] : []"
      :loading="removingBusy"
      @confirm="remove"
      @close="removing = null"
    />
  </section>
</template>

<style scoped>
.panel {
  overflow: hidden;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.panel__head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
}
.panel__title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.panel__count {
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
.panel__tools {
  margin-left: auto;
}
.panel__empty {
  padding: var(--space-4);
}
.panel__steps {
  margin: 0;
  padding-left: var(--space-5);
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.panel__bld {
  font-weight: var(--font-weight-bold);
}
.panel__pick {
  padding: 0;
  border: 0;
  background: none;
  color: var(--text-1);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.panel__pick[aria-pressed='true'] {
  color: var(--brand);
  font-weight: var(--font-weight-medium);
}
.panel__actions {
  display: flex;
  gap: var(--space-1);
}
/* 선택된 건물 행 — brand.tint(Table) + 왼쪽 3px brand 막대 (admin-master.md) */
.panel :deep(.tbl__row--selected td:first-child) {
  box-shadow: inset 3px 0 0 var(--brand);
}
.form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.form__error {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--danger);
}
</style>
```

`web/src/admin/views/MasterView.vue`
```vue
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Banner from '@/components/ui/Banner.vue'
import { showToast } from '@/components/ui/toast'
import { adminApi } from '@/api/admin'
import { loraApi } from '@/api/lora'
import { roomsApi } from '@/api/rooms'
import { useResource } from '@/lib/useResource'
import BuildingPanel from './master/BuildingPanel.vue'

// 마스터 데이터는 관리자가 바꿀 때만 바뀐다 — 자동 새로고침 없음 (admin-master.md)
const { data, error, loading, reload } = useResource(async () => {
  const [buildings, rooms, modems, nodes] = await Promise.all([
    roomsApi.buildings(),
    roomsApi.rooms(),
    loraApi.modems(),
    adminApi.nodes(),
  ])
  return { buildings, rooms, modems, nodes }
})
const selectedId = ref<number | null>(null)
watch(data, (d) => {
  if (d && !d.buildings.some((b) => b.id === selectedId.value))
    selectedId.value = d.buildings[0]?.id ?? null
})
// reservable 기본값이 꺼짐 — 켜는 것을 잊으면 학생 웹이 빈 채로 남는다
const noReservable = computed(
  () => !!data.value?.rooms.length && !data.value.rooms.some((r) => r.reservable),
)
watch(error, (e) => {
  if (e && e.status !== 401 && e.status !== 403)
    showToast({ tone: 'danger', message: e.message, action: { label: '재시도', onClick: reload } })
})
</script>

<template>
  <main class="master">
    <header class="master__head">
      <h1 class="master__title">건물 · 강의실</h1>
      <p class="master__sub">여기서 만든 방만 다른 화면에 나온다</p>
    </header>
    <Banner
      v-if="noReservable"
      message="학생 예약을 받는 강의실이 없습니다. 학생 웹 목록이 비어 있습니다."
      :dismissible="false"
    />
    <div class="master__body">
      <BuildingPanel
        :buildings="data?.buildings"
        :rooms="data?.rooms ?? []"
        :modems="data?.modems ?? []"
        :loading="loading && !data"
        :selected-id="selectedId"
        @select="selectedId = $event"
        @changed="reload"
      />
    </div>
  </main>
</template>

<style scoped>
.master {
  padding: var(--space-5);
}
.master__head {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}
.master__title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
}
.master__sub {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
/* 좌우 2단 — 건물 패널 396px 고정, 강의실 표가 남는 폭 */
.master__body {
  display: grid;
  grid-template-columns: 396px minmax(0, 1fr);
  gap: var(--space-5);
  align-items: start;
  margin-top: var(--space-4);
}
</style>
```

`web/src/admin/router.ts` 의 `children` 을 바꾼다
```ts
    children: [
      // 관리자 기본 화면은 전송 현황 (spec §5)
      { path: '', redirect: '/dashboard' },
      { path: 'master', component: () => import('./views/MasterView.vue') },
      { path: 'nodes', component: () => import('./views/NodesView.vue') },
      { path: 'dashboard', component: () => import('./views/DashboardView.vue') },
      { path: 'users', component: () => import('./views/UsersView.vue') },
    ],
```

`web/src/admin/AdminShell.vue`
- import 에 `import { ApiError } from '@/api/client'`, `import { roomsApi } from '@/api/rooms'`, `import type { SchoolOut } from '@/api/types'` 를 더한다.
- `nav` 를 바꾼다:
```ts
// #46 admin-master.md 순서: 건물 · 강의실 · 강의실 설정 · 주간 시간표 · 노드 상태 · 전송 현황 · 회원
const nav = computed(() => [
  { to: '/master', label: '건물 · 강의실' },
  { to: '/nodes', label: '노드 상태' },
  { to: '/dashboard', label: '전송 현황' },
  { to: '/users', label: '회원', badge: pendingCount.value },
])
```
- `onMounted(refreshPending)` 줄 **아래**에 추가:
```ts
// 학교는 CLI 에서만 만든다 — 지금 학교를 읽기 전용으로 (admin-master.md). 버튼을 두고 405 를 받게 하지 않는다
const school = ref<SchoolOut | null>(null)
onMounted(async () => {
  try {
    school.value = (await roomsApi.schools())[0] ?? null
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
  }
})
```
- `<template #footer>` 안, `<p class="shell__user">` **앞**에 추가:
```vue
        <p v-if="school" class="shell__school num">{{ school.name }} · net_id {{ school.net_id }}</p>
        <p class="shell__cli">학교는 CLI 에서만 만든다</p>
```
- `<style>` 끝에 추가:
```css
.shell__school {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.shell__cli {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint && pnpm exec prettier --check .`
Expected: PASS

- [ ] **Step 5: E2E — 하네스 + 건물**

`web/e2e/helpers.ts` 끝에 추가
```ts
// ---- F2 관리자 운영 ----

/** KST 오늘 + n일 'YYYY-MM-DD' — 날짜 흐름은 상대 날짜로 (서버 시계를 고정할 수 없다, spec §7.2) */
export const kstDate = (offsetDays = 0) =>
  new Date(Date.now() + 9 * 3_600_000 + offsetDays * 86_400_000).toISOString().slice(0, 10)

/** 우리 학교 모뎀 등록 (이미 있으면 건너뛴다 — 같은 실행 안에서 여러 spec 이 부른다) */
export async function ensureModems(request: APIRequestContext, ids: string[]) {
  const headers = { authorization: `Bearer ${await apiLogin(request, cfg.ADMINS[0])}` }
  const r = await request.get('/api/lora/modems', { headers })
  expect(r.status()).toBe(200)
  const have = ((await r.json()) as { modem_id: string }[]).map((m) => m.modem_id)
  for (const modem_id of ids.filter((i) => !have.includes(i))) {
    const m = await request.post('/api/lora/modems', { headers, data: { modem_id } })
    expect(m.status(), modem_id).toBe(200)
  }
}
```

`web/e2e/admin-ops.spec.ts`
```ts
import { expect, test, type APIRequestContext, type BrowserContext, type Page } from '@playwright/test'
import cfg from './env.json' with { type: 'json' }
import { SIZES, WEB_URL, ensureModems, fillLogin, nextAdmin, shot } from './helpers'

// 한 파일 = 컨텍스트 둘(우리 학교·다른 학교), 로그인 각 한 번 — 서버의 IP 당 분당 로그인 30회 상한.
// 화면 이동은 사이드 메뉴 클릭으로 (page.goto 는 새로고침 = 메모리 세션 소실)
test.describe.configure({ mode: 'serial' })
let ctx: BrowserContext
let other: BrowserContext
let api: APIRequestContext
let page: Page
let otherPage: Page

test.beforeAll(async ({ browser }) => {
  ctx = await browser.newContext({ baseURL: WEB_URL, locale: 'ko-KR', viewport: SIZES.admin })
  api = ctx.request
  await ensureModems(api, ['e2e-m4', 'e2e-m5'])
  page = await ctx.newPage()
  await page.goto('/admin/master')
  await fillLogin(page, nextAdmin())
  await expect(page).toHaveURL(/\/admin\/master$/)
  other = await browser.newContext({ baseURL: WEB_URL, locale: 'ko-KR', viewport: SIZES.admin })
  otherPage = await other.newPage()
  await otherPage.goto('/admin/master')
  await fillLogin(otherPage, cfg.OTHER_ADMIN)
  await expect(otherPage).toHaveURL(/\/admin\/master$/)
})
test.afterAll(async () => {
  await ctx.close()
  await other.close()
})

const buildingPanel = (p: Page) => p.getByRole('region', { name: '건물', exact: true })
const buildingRow = (name: string) => buildingPanel(page).getByRole('row').filter({ hasText: name })

// ---- 건물 · 강의실 ----
test('다른 학교 — 건물 0개면 설치 순서 안내, 소문자 z 를 치면 Z 로 만든다', async () => {
  const p = otherPage
  await expect(p.getByText('건물을 먼저 만드세요')).toBeVisible()
  await expect(p.getByText('학교는 CLI 에서만 만든다')).toBeVisible()
  await expect(p.getByText('타학교 · net_id 76')).toBeVisible()
  await shot(p, 'admin-master-empty-1440')
  await p.getByRole('button', { name: '+ 건물' }).first().click()
  const d = p.getByRole('dialog', { name: '건물 추가' })
  await d.getByLabel('이름').fill('타학교관')
  await d.getByLabel('글자').fill('z')
  await expect(d.getByLabel('글자')).toHaveValue('Z')
  await d.getByRole('button', { name: '저장' }).click()
  await expect(d).toHaveCount(0)
  await expect(buildingPanel(p).getByRole('button', { name: '타학교관' })).toBeVisible()
})

test('우리 학교 — 다른 학교가 쓰는 Z 는 글자 칸 오류, 나머지 입력은 그대로 두고 고쳐서 만든다', async () => {
  await page.getByRole('button', { name: '+ 건물' }).first().click()
  const d = page.getByRole('dialog', { name: '건물 추가' })
  await d.getByLabel('이름').fill('마스터관')
  await d.getByLabel('글자').fill('z')
  await d.getByLabel('모뎀').selectOption('e2e-m4')
  await d.getByRole('button', { name: '저장' }).click()
  await expect(d.getByText('다른 학교가 이미 쓰는 글자입니다. 다른 글자를 고르세요.')).toBeVisible()
  await expect(d.getByLabel('이름')).toHaveValue('마스터관')
  await d.getByLabel('글자').fill('m')
  await d.getByRole('button', { name: '저장' }).click()
  await expect(d).toHaveCount(0)
  await expect(buildingPanel(page).getByRole('button', { name: '마스터관' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await expect(buildingRow('마스터관')).toContainText('e2e-m4')
})

test('모뎀을 바꾸면 대기 건수와 함께 확인 — 이름만 바꾸면 묻지 않는다', async () => {
  await buildingRow('마스터관').getByRole('button', { name: '수정' }).click()
  const d = page.getByRole('dialog', { name: '건물 수정' })
  await d.getByLabel('모뎀').selectOption('e2e-m5')
  await d.getByRole('button', { name: '저장' }).click()
  const c = page.getByRole('dialog', { name: '모뎀 변경' })
  await expect(c).toContainText(
    '대기 중 0건이 e2e-m5 로 옮겨집니다. 옛 모뎀(e2e-m4)과 새 모뎀 양쪽이 설정을 다시 받습니다.',
  )
  await c.getByRole('button', { name: '바꾸기' }).click()
  await expect(c).toHaveCount(0)
  await expect(d).toHaveCount(0)
  await expect(buildingRow('마스터관')).toContainText('e2e-m5')
  await buildingRow('마스터관').getByRole('button', { name: '수정' }).click()
  await d.getByLabel('이름').fill('마스터관2')
  await d.getByRole('button', { name: '저장' }).click()
  await expect(d).toHaveCount(0)
  await expect(c).toHaveCount(0)
  await expect(buildingPanel(page).getByRole('button', { name: '마스터관2' })).toBeVisible()
  await shot(page, 'admin-master-building-1440')
})
```

`web/e2e/admin-shell.spec.ts` 첫 테스트의 메뉴 기대값 줄을 바꾼다
```ts
  await expect(page.locator('nav a')).toHaveText([
    /^건물 · 강의실$/,
    /^노드 상태$/,
    /^전송 현황$/,
    /^회원\s*\d+$/,
  ])
```

Run: **E2E 명령** + ` e2e/admin-ops.spec.ts e2e/admin-shell.spec.ts`
Expected: `5 passed`

- [ ] **Step 6: 스크린샷 대조**

`admin-master-empty-1440.png`·`admin-master-building-1440.png` 를 `admin-master.md` 와 대조:
- 사이드바 220px, 메뉴 맨 위 `건물 · 강의실`(활성: brand.tint + brand 글자). 사이드바 아래 `우송대 · net_id 75` / `학교는 CLI 에서만 만든다` / 관리자 이름 / 로그아웃. `설정` 항목 없음.
- 제목 `건물 · 강의실` + 부제 `여기서 만든 방만 다른 화면에 나온다`.
- 좌 건물 패널 **396px**(카드: line.2 1px + radius.lg), 헤더 `건물 1 / 26` + `+ 건물`(secondary). 행 **44px**, 선택 행 brand.tint + 왼쪽 3px brand 막대. `미배정` 은 danger 테두리 배지(모뎀이 있으면 모뎀 id).
- 빈 상태(다른 학교): `건물을 먼저 만드세요` + `+ 건물`(primary) + 설치 순서 3줄.
어긋나면 고치고 다시 찍는다.

- [ ] **Step 7: 커밋**

```bash
git add web/src/admin web/e2e
git commit -m "feat(web): 건물·강의실 화면 A — 건물 패널(26 상한·대문자 bld·다른 학교 409 는 글자 칸에·강의실 있으면 bld 잠금·모뎀 변경 확인·삭제 잠금), 메뉴 맨 위, 사이드바 학교 표시 + E2E"
```

---

### Task 12: 건물 · 강의실 B — 강의실 표 · 학생 예약 즉시 저장 · 유닛 축소 · 삭제 개수 + E2E

**Files:**
- Create: `web/src/admin/views/master/RoomPanel.vue`
- Modify: `web/src/admin/views/MasterView.vue`, `web/e2e/admin-ops.spec.ts`
- Test: `web/src/admin/__tests__/masterRooms.spec.ts`

**Interfaces:**
- Consumes: `roomsApi.{createRoom, patchRoom, deleteRoom, buildingSlots, buildingResv, buildingExams}`(Task 1) · `countFor`·`roomDeleteLines`·`roomNodeText`·`UNIT_OPTIONS`(Task 10) · `floorLabel`(Task 2) · `Checkbox`(F1).
- Produces (`RoomPanel.vue`): props `{ building: BuildingOut; rooms: RoomOut[]; nodes: NodeOut[]; loading: boolean }`(rooms 는 학교 전체 — 패널이 건물로 거른다), emits `changed: []`. 루트 `<section aria-labelledby="master-room">`(h2 `{건물} 강의실`). Modal `강의실 추가`·`강의실 수정`, 확인 `유닛 줄이기`·`강의실 삭제`. 입력 라벨 `호수`·`유닛`·`학생 예약을 받는다`.

- [ ] **Step 1: 실패 테스트**

`web/src/admin/__tests__/masterRooms.spec.ts`
```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import MasterView from '@/admin/views/MasterView.vue'
import { roomsApi } from '@/api/rooms'
import { loraApi } from '@/api/lora'
import { adminApi } from '@/api/admin'
import { ApiError, MESSAGES } from '@/api/client'
import type { NodeOut, ResvWithRoom, RoomOut, SlotWithRoom } from '@/api/types'
import { setSession } from '@/lib/session'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/rooms', () => ({
  roomsApi: {
    buildings: vi.fn(),
    rooms: vi.fn(),
    createBuilding: vi.fn(),
    patchBuilding: vi.fn(),
    deleteBuilding: vi.fn(),
    buildingOutbox: vi.fn(),
    createRoom: vi.fn(),
    patchRoom: vi.fn(),
    deleteRoom: vi.fn(),
    buildingSlots: vi.fn(),
    buildingResv: vi.fn(),
    buildingExams: vi.fn(),
  },
}))
vi.mock('@/api/lora', () => ({ loraApi: { modems: vi.fn() } }))
vi.mock('@/api/admin', () => ({ adminApi: { nodes: vi.fn() } }))
const rooms = vi.mocked(roomsApi)
const lora = vi.mocked(loraApi)
const admin = vi.mocked(adminApi)

const R = (id: number, room: number, o: Partial<RoomOut> = {}): RoomOut => ({
  id,
  building_id: 1,
  room,
  units: 1,
  reservable: false,
  ...o,
})
const N = (room_id: number, room: number, unit: number, o: Partial<NodeOut> = {}): NodeOut => ({
  room_id,
  building_id: 1,
  building: '공학관',
  bld: 'E',
  room,
  unit,
  modem_id: 'm1',
  mac: null,
  fw: null,
  batt_mv: null,
  rssi: null,
  snr: null,
  sched_ver: null,
  resv_ver: null,
  exam_ver: null,
  ident_ver: null,
  layout: null,
  clock_stale: false,
  low_batt: false,
  uptime_h: null,
  last_seen_at: null,
  last_ack_at: null,
  last_status_at: null,
  sync_state: 'unknown',
  warnings: [],
  ...o,
})

let w: VueWrapper
async function mountView() {
  w = mount(MasterView, { global: { stubs: { teleport: true } } })
  await flushPromises()
}
type Root = VueWrapper | DOMWrapper<Element>
const btn = (root: Root, text: string) => root.findAll('button').find((b) => b.text() === text)!
const dialog = (title: string) =>
  w.findAll('[role=dialog]').find((d) => d.get('h2').text() === title)
const control = (root: Root, label: string) =>
  root
    .findAll('.field, .sel')
    .find((f) => f.find('label').exists() && f.get('label').text().replace('*', '').trim() === label)!
    .get('input, select')
const panel = () => w.get('[aria-labelledby=master-room]')
const row = (room: number) =>
  panel()
    .findAll('tbody tr')
    .find((r) => r.find('td').text() === String(room))!

beforeEach(() => {
  Object.values(rooms).forEach((f) => f.mockReset())
  rooms.buildings.mockResolvedValue([{ id: 1, school_id: 1, name: '공학관', bld: 'E', modem_id: 'm1' }])
  rooms.rooms.mockResolvedValue([
    R(11, 401, { reservable: true }),
    R(12, 402, { units: 2 }),
    R(13, 5),
  ])
  rooms.createRoom.mockResolvedValue(R(14, 403))
  rooms.patchRoom.mockResolvedValue(R(12, 402))
  rooms.deleteRoom.mockResolvedValue({ ok: true })
  lora.modems.mockResolvedValue([])
  const seen = new Date()
  admin.nodes.mockResolvedValue([
    N(11, 401, 1, { mac: 'AA', last_seen_at: seen, batt_mv: 3980 }),
    N(12, 402, 1, { mac: 'BB', last_seen_at: seen, batt_mv: 3700 }),
    N(12, 402, 2, { warnings: ['unseen'] }),
    N(13, 5, 1, { warnings: ['unseen'] }),
  ])
  setSession({ token: 't', role: 'admin', school_id: 1, name: '관리자1' })
  for (const t of [...toasts.value]) dismissToast(t.id)
})

describe('강의실 패널', () => {
  it('헤더에 곳 수·학생 웹에 보이는 곳, 층은 호수 ÷ 100, 노드 칸은 서버 판정 문구', async () => {
    await mountView()
    expect(panel().get('h2').text()).toBe('공학관 강의실')
    expect(panel().text()).toContain('3곳 · 학생 웹에 보이는 곳 1')
    expect(row(401).text()).toContain('4층')
    expect(row(401).text()).toContain('연결됨 · 3.98 V')
    expect(row(402).text()).toContain('응답 없음')
    expect(row(5).text()).toContain('기타')
    expect(row(5).text()).toContain('단말 없음')
  })

  it('학생 예약 체크박스는 누르는 즉시 부분 PATCH — 응답 전에도 누른 값을 보인다', async () => {
    rooms.patchRoom.mockReturnValue(new Promise(() => {}))
    await mountView()
    await row(402).get('input[type=checkbox]').setValue(true)
    expect(rooms.patchRoom).toHaveBeenCalledWith(12, { reservable: true })
    expect(row(402).text()).toContain('받음')
    expect(panel().text()).toContain('학생 웹에 보이는 곳 2')
    expect((row(402).get('input[type=checkbox]').element as HTMLInputElement).disabled).toBe(true)
  })

  it('실패하면 체크를 되돌리고 Toast', async () => {
    rooms.patchRoom.mockRejectedValue(new ApiError(500, MESSAGES[500]))
    await mountView()
    await row(402).get('input[type=checkbox]').setValue(true)
    await flushPromises()
    expect(row(402).text()).toContain('안 받음')
    expect(toasts.value.at(-1)).toMatchObject({
      tone: 'danger',
      message: '402호 학생 예약 설정을 바꾸지 못했습니다.',
    })
  })

  it('학교 전체에 받는 방이 0곳이면 Banner', async () => {
    rooms.rooms.mockResolvedValue([R(11, 401), R(12, 402)])
    await mountView()
    expect(w.text()).toContain('학생 예약을 받는 강의실이 없습니다. 학생 웹 목록이 비어 있습니다.')
  })

  it('한 곳 추가 — 호수 범위·중복은 저장 전에, 층 입력 칸은 없다', async () => {
    await mountView()
    await btn(panel(), '+ 강의실').trigger('click')
    const d = dialog('강의실 추가')!
    expect(d.text()).not.toContain('층')
    await control(d, '호수').setValue('401')
    await btn(d, '저장').trigger('click')
    expect(d.text()).toContain('이미 있는 호수입니다')
    await control(d, '호수').setValue('10000')
    await btn(d, '저장').trigger('click')
    expect(d.text()).toContain('호수는 1~9999 정수입니다')
    expect(rooms.createRoom).not.toHaveBeenCalled()
    await control(d, '호수').setValue('403')
    await btn(d, '저장').trigger('click')
    await flushPromises()
    expect(rooms.createRoom).toHaveBeenCalledWith({
      building_id: 1,
      room: 403,
      units: 1,
      reservable: false,
    })
  })

  it('수정 — 호수는 읽기 전용, 유닛 2→1 만 묻고(단말을 떼라), 늘리는 쪽은 묻지 않는다', async () => {
    await mountView()
    await btn(row(402), '수정').trigger('click')
    const d = dialog('강의실 수정')!
    expect(control(d, '호수').attributes('readonly')).toBeDefined()
    expect(d.text()).toContain('호수를 바꾸려면 강의실을 지우고 다시 만든 뒤, 문 앞 단말을 다시 등록하세요.')
    await control(d, '유닛').setValue('1')
    await btn(d, '저장').trigger('click')
    const c = dialog('유닛 줄이기')!
    expect(c.text()).toContain('402호의 2번 단말이 목록에서 사라집니다. 벽에서 떼어 주세요.')
    expect(rooms.patchRoom).not.toHaveBeenCalled()
    await btn(c, '줄이기').trigger('click')
    await flushPromises()
    expect(rooms.patchRoom).toHaveBeenCalledWith(12, { units: 1 })
    rooms.patchRoom.mockClear()
    await btn(row(401), '수정').trigger('click')
    await control(dialog('강의실 수정')!, '유닛').setValue('2')
    await btn(dialog('강의실 수정')!, '저장').trigger('click')
    await flushPromises()
    expect(dialog('유닛 줄이기')).toBeUndefined()
    expect(rooms.patchRoom).toHaveBeenCalledWith(11, { units: 2 })
  })

  it('삭제 — 함께 지워질 개수와 단말을 적는다 (이름 입력은 요구하지 않는다)', async () => {
    rooms.buildingSlots.mockResolvedValue([{ room_id: 11 }, { room_id: 11 }] as SlotWithRoom[])
    rooms.buildingResv.mockResolvedValue([
      { room_id: 11, status: 'approved' },
      { room_id: 11, status: 'cancelled' },
    ] as ResvWithRoom[])
    rooms.buildingExams.mockResolvedValue([])
    await mountView()
    await btn(row(401), '삭제').trigger('click')
    await flushPromises()
    const c = dialog('강의실 삭제')!
    expect(c.findAll('p').map((p) => p.text())).toEqual([
      '공학관 401호를 지웁니다.',
      '시간표 2건 · 예약 1건이 함께 지워집니다.',
      '문 앞 단말(unit 1)은 갱신을 받지 못하게 됩니다.',
    ])
    expect(c.find('input').exists()).toBe(false)
    await btn(c, '삭제').trigger('click')
    await flushPromises()
    expect(rooms.deleteRoom).toHaveBeenCalledWith(11)
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin/__tests__/masterRooms.spec.ts`
Expected: FAIL — `Cannot call get on an empty DOMWrapper`(`[aria-labelledby=master-room]` 없음)

- [ ] **Step 3: 구현**

`web/src/admin/views/master/RoomPanel.vue`
```vue
<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Input from '@/components/ui/Input.vue'
import Modal from '@/components/ui/Modal.vue'
import Select from '@/components/ui/Select.vue'
import Table from '@/components/ui/Table.vue'
import { showToast } from '@/components/ui/toast'
import { floorLabel } from '@/components/domain/rules'
import { ApiError, MESSAGES } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { BuildingOut, NodeOut, RoomOut, RoomPatch } from '@/api/types'
import ConfirmModal from '../../ConfirmModal.vue'
import {
  UNIT_OPTIONS,
  countFor,
  roomDeleteLines,
  roomNodeText,
  type RoomCounts,
} from '../../masterView'

const props = defineProps<{
  building: BuildingOut
  rooms: RoomOut[]
  nodes: NodeOut[]
  loading: boolean
}>()
const emit = defineEmits<{ changed: [] }>()

const mine = computed(() =>
  props.rooms.filter((r) => r.building_id === props.building.id).sort((a, b) => a.room - b.room),
)
const COLUMNS = [
  { key: 'room', label: '호수', width: '72px' },
  { key: 'floor', label: '층', width: '52px' },
  { key: 'units', label: '유닛', width: '64px', align: 'right' as const },
  { key: 'reservable', label: '학생 예약', width: '128px' },
  { key: 'node', label: '노드' },
  { key: 'actions', label: '작업', width: '92px' },
]
const asR = (row: Record<string, unknown>) => row as unknown as RoomOut

// ---- reservable — 이 화면의 요점. 끄면 학생 웹에서 그 방이 사라진다(문 앞 e-Paper 는 그대로) ----
// 즉시 저장. 응답·새 목록이 오기 전까지 누른 값을 보이고, 실패하면 되돌린다
const flipped = reactive(new Map<number, boolean>())
const flipping = reactive(new Set<number>())
watch(
  () => props.rooms,
  () => flipped.clear(),
)
const reservableOf = (r: RoomOut) => flipped.get(r.id) ?? r.reservable
const visible = computed(() => mine.value.filter(reservableOf).length)
async function flip(r: RoomOut, on: boolean) {
  if (flipping.has(r.id)) return
  flipping.add(r.id)
  flipped.set(r.id, on)
  try {
    // 부분 PATCH — 전체 바디를 보내면 다른 탭에서 바뀐 units 를 덮는다
    await roomsApi.patchRoom(r.id, { reservable: on })
    emit('changed')
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    flipped.delete(r.id)
    if (e.status !== 401 && e.status !== 403)
      showToast({ tone: 'danger', message: `${r.room}호 학생 예약 설정을 바꾸지 못했습니다.` })
    if (e.status === 404) emit('changed')
  } finally {
    flipping.delete(r.id)
  }
}

// ---- 추가·수정 폼 — 층 입력 칸은 없다(파생값), 호수는 새로 만들 때만 ----
const editing = ref<RoomOut | null>(null)
const formOpen = ref(false)
const form = reactive({ room: '', units: 1, reservable: false })
const errors = reactive<{ room?: string; form?: string }>({})
const saving = ref(false)
const initial = ref('')
const dirty = computed(() => JSON.stringify(form) !== initial.value)
function openForm(r: RoomOut | null) {
  editing.value = r
  Object.assign(form, {
    room: r ? String(r.room) : '',
    units: r?.units ?? 1,
    reservable: r?.reservable ?? false,
  })
  delete errors.room
  delete errors.form
  initial.value = JSON.stringify(form)
  formOpen.value = true
}

const shrinkAsk = ref<string[] | null>(null)
function submit() {
  if (saving.value) return
  delete errors.room
  delete errors.form
  const r = editing.value
  if (!r) {
    const n = Number(form.room)
    if (!/^\d+$/.test(form.room) || n < 1 || n > 9999) {
      errors.room = '호수는 1~9999 정수입니다'
      return
    }
    if (mine.value.some((x) => x.room === n)) {
      errors.room = '이미 있는 호수입니다'
      return
    }
  } else if (form.units < r.units) {
    // 2 → 1: unit 2 가 기대 노드에서 빠지는데 단말은 벽에 붙어 있다. 늘리는 쪽은 묻지 않는다
    // (새 자리가 노드 화면에 '응답 없음'으로 뜨는 것이 곧 "여기에 단말을 달아라")
    shrinkAsk.value = [`${r.room}호의 2번 단말이 목록에서 사라집니다. 벽에서 떼어 주세요.`]
    return
  }
  void save()
}

async function save() {
  const r = editing.value
  saving.value = true
  try {
    if (r) {
      const patch: RoomPatch = {}
      if (form.units !== r.units) patch.units = form.units
      if (form.reservable !== r.reservable) patch.reservable = form.reservable
      if (Object.keys(patch).length) await roomsApi.patchRoom(r.id, patch)
      showToast({ message: '저장했습니다.' })
    } else {
      await roomsApi.createRoom({
        building_id: props.building.id,
        room: Number(form.room),
        units: form.units,
        reservable: form.reservable,
      })
      showToast({ message: `${form.room}호를 만들었습니다.` })
    }
    shrinkAsk.value = null
    formOpen.value = false
    emit('changed')
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    shrinkAsk.value = null
    if (e.status === 409) {
      errors.room = '이미 있는 호수입니다. 목록을 새로 불러옵니다.'
      emit('changed')
    } else if (e.status === 404) {
      showToast({ tone: 'danger', message: '강의실이나 건물을 찾을 수 없습니다. 목록을 새로 불러옵니다.' })
      formOpen.value = false
      emit('changed')
    } else if (e.status === 422) errors.form = MESSAGES[422]
    else if (e.status !== 401 && e.status !== 403) errors.form = e.message
  } finally {
    saving.value = false
  }
}

// ---- 삭제 — 시간표·예약·시험기간이 CASCADE 로 함께 사라진다. 개수를 적는다(이름 입력은 요구하지 않는다) ----
const removing = ref<RoomOut | null>(null)
const removeLines = ref<string[]>([])
const counting = ref(false)
const removingBusy = ref(false)
async function askRemove(r: RoomOut) {
  removing.value = r
  removeLines.value = [`${props.building.name} ${r.room}호를 지웁니다.`, '딸린 항목 수를 세는 중…']
  counting.value = true
  let counts: RoomCounts | null = null
  try {
    const [slots, resv, exams] = await Promise.all([
      roomsApi.buildingSlots(props.building.id),
      roomsApi.buildingResv(props.building.id),
      roomsApi.buildingExams(props.building.id),
    ])
    counts = countFor(r.id, slots, resv, exams)
  } catch (e) {
    if (!(e instanceof ApiError)) throw e // 못 세도 지울 수는 있다 — 문장이 그렇게 말한다
  } finally {
    counting.value = false
  }
  if (removing.value?.id === r.id)
    removeLines.value = roomDeleteLines(props.building.name, r, counts, props.nodes)
}
async function remove() {
  const r = removing.value
  if (!r || removingBusy.value || counting.value) return
  removingBusy.value = true
  try {
    await roomsApi.deleteRoom(r.id)
    showToast({ message: `${r.room}호를 지웠습니다.` })
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status !== 404 && e.status !== 401 && e.status !== 403)
      showToast({ tone: 'danger', message: e.message })
  } finally {
    removingBusy.value = false
    removing.value = null
    emit('changed')
  }
}
</script>

<template>
  <section class="panel" aria-labelledby="master-room">
    <header class="panel__head">
      <h2 id="master-room" class="panel__title">{{ building.name }} 강의실</h2>
      <span class="panel__count num">{{ mine.length }}곳 · 학생 웹에 보이는 곳 {{ visible }}</span>
      <span class="panel__note">층 = 호수 ÷ 100</span>
      <div class="panel__tools">
        <Button size="sm" @click="openForm(null)">+ 강의실</Button>
      </div>
    </header>
    <Table
      tall
      :columns="COLUMNS"
      :rows="mine as unknown as Record<string, unknown>[]"
      :loading="loading"
    >
      <template #empty>
        <EmptyState
          message="이 건물에 강의실이 없습니다"
          :actions="[{ label: '+ 강의실', variant: 'primary', onClick: () => openForm(null) }]"
        />
      </template>
      <template #cell-room="{ row }"
        ><span class="num">{{ asR(row).room }}</span></template
      >
      <template #cell-floor="{ row }">{{ floorLabel(asR(row).room) }}</template>
      <template #cell-units="{ row }"
        ><span class="num">{{ asR(row).units }}</span></template
      >
      <template #cell-reservable="{ row }">
        <Checkbox
          :model-value="reservableOf(asR(row))"
          :disabled="flipping.has(asR(row).id)"
          :label="reservableOf(asR(row)) ? '받음' : '안 받음'"
          @update:model-value="(v) => flip(asR(row), v === true)"
        />
      </template>
      <template #cell-node="{ row }">{{ roomNodeText(asR(row), nodes) }}</template>
      <template #cell-actions="{ row }">
        <div class="panel__actions">
          <Button variant="ghost" size="sm" @click="openForm(asR(row))">수정</Button>
          <Button variant="ghost" size="sm" @click="askRemove(asR(row))">삭제</Button>
        </div>
      </template>
    </Table>

    <Modal
      :open="formOpen"
      :title="editing ? '강의실 수정' : '강의실 추가'"
      :close-on-backdrop="!dirty"
      @close="formOpen = false"
    >
      <form class="form" novalidate @submit.prevent="submit">
        <p v-if="errors.form" class="form__error" role="alert">{{ errors.form }}</p>
        <!-- 호수는 bld 와 함께 무선 주소 — 수정 폼에서 잠근다 -->
        <Input
          v-model="form.room"
          label="호수"
          inputmode="numeric"
          class="num"
          required
          :readonly="!!editing"
          :error="errors.room"
          :hint="
            editing
              ? '호수를 바꾸려면 강의실을 지우고 다시 만든 뒤, 문 앞 단말을 다시 등록하세요.'
              : undefined
          "
        />
        <Select v-model="form.units" label="유닛" :options="UNIT_OPTIONS" />
        <Checkbox v-model="form.reservable" label="학생 예약을 받는다" />
      </form>
      <template #footer>
        <Button variant="secondary" @click="formOpen = false">취소</Button>
        <Button :loading="saving" @click="submit">저장</Button>
      </template>
    </Modal>
    <ConfirmModal
      :open="!!shrinkAsk"
      title="유닛 줄이기"
      :lines="shrinkAsk ?? []"
      confirm-label="줄이기"
      :loading="saving"
      @confirm="save"
      @close="shrinkAsk = null"
    />
    <ConfirmModal
      :open="!!removing"
      title="강의실 삭제"
      :lines="removeLines"
      :loading="counting || removingBusy"
      @confirm="remove"
      @close="removing = null"
    />
  </section>
</template>

<style scoped>
.panel {
  overflow: hidden;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.panel__head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
}
.panel__title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.panel__count {
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.panel__note {
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.panel__tools {
  display: flex;
  gap: var(--space-2);
  margin-left: auto;
}
.panel__actions {
  display: flex;
  gap: var(--space-1);
}
.form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.form__error {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--danger);
}
</style>
```

`web/src/admin/views/MasterView.vue`
- import 에 `import RoomPanel from './master/RoomPanel.vue'` 를 더하고, `watch(data, …)` 블록 **아래**에 추가:
```ts
const selected = computed(() => data.value?.buildings.find((b) => b.id === selectedId.value) ?? null)
```
- `<div class="master__body">…</div>` 를 통째로 바꾼다:
```vue
    <div class="master__body">
      <BuildingPanel
        :buildings="data?.buildings"
        :rooms="data?.rooms ?? []"
        :modems="data?.modems ?? []"
        :loading="loading && !data"
        :selected-id="selectedId"
        @select="selectedId = $event"
        @changed="reload"
      />
      <RoomPanel
        v-if="selected"
        :building="selected"
        :rooms="data?.rooms ?? []"
        :nodes="data?.nodes ?? []"
        :loading="loading && !data"
        @changed="reload"
      />
    </div>
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`
Expected: PASS

- [ ] **Step 5: E2E**

`web/e2e/admin-ops.spec.ts` 끝에 추가
```ts
const roomPanel = () => page.getByRole('region', { name: '마스터관2 강의실' })

test('강의실 — 한 곳 추가(유닛 2), 학생 예약은 누르는 즉시 저장, 수정 폼의 호수 잠김 · 2→1 확인', async () => {
  const panel = roomPanel()
  await panel.getByRole('button', { name: '+ 강의실' }).first().click()
  const d = page.getByRole('dialog', { name: '강의실 추가' })
  await d.getByLabel('호수').fill('401')
  await d.getByLabel('유닛').selectOption('2')
  await d.getByRole('button', { name: '저장' }).click()
  await expect(d).toHaveCount(0)
  const row = panel.getByRole('row').filter({ hasText: '401' })
  await expect(row).toContainText('4층')
  await expect(row).toContainText('단말 없음')
  await expect(panel).toContainText('1곳 · 학생 웹에 보이는 곳 0')
  await row.getByRole('checkbox').check()
  await expect(row.getByText('받음', { exact: true })).toBeVisible()
  await expect(panel).toContainText('학생 웹에 보이는 곳 1')
  await row.getByRole('button', { name: '수정' }).click()
  const e = page.getByRole('dialog', { name: '강의실 수정' })
  await expect(e.getByLabel('호수')).toHaveAttribute('readonly', '')
  await e.getByLabel('유닛').selectOption('1')
  await e.getByRole('button', { name: '저장' }).click()
  const c = page.getByRole('dialog', { name: '유닛 줄이기' })
  await expect(c).toContainText('401호의 2번 단말이 목록에서 사라집니다. 벽에서 떼어 주세요.')
  await c.getByRole('button', { name: '줄이기' }).click()
  await expect(e).toHaveCount(0)
  await expect(row.getByRole('cell').nth(2)).toHaveText('1')
  await shot(page, 'admin-master-room-1440')
})

test('삭제 — 강의실이 있으면 건물 삭제 잠김(툴팁), 강의실 삭제는 딸린 개수를 적는다', async () => {
  const b = buildingRow('마스터관2')
  await expect(b.getByRole('button', { name: '삭제' })).toBeDisabled()
  await expect(b.locator('[title="강의실을 먼저 지우세요 (1곳)"]')).toHaveCount(1)
  const panel = roomPanel()
  await panel.getByRole('row').filter({ hasText: '401' }).getByRole('button', { name: '삭제' }).click()
  const c = page.getByRole('dialog', { name: '강의실 삭제' })
  await expect(c).toContainText('마스터관2 401호를 지웁니다.')
  await expect(c).toContainText('딸린 시간표·예약·시험기간이 없습니다.')
  await c.getByRole('button', { name: '삭제' }).click()
  await expect(c).toHaveCount(0)
  await expect(panel.getByText('이 건물에 강의실이 없습니다')).toBeVisible()
  await expect(b.getByRole('button', { name: '삭제' })).toBeEnabled()
})
```

Run: **E2E 명령** + ` e2e/admin-ops.spec.ts`
Expected: `5 passed`

- [ ] **Step 6: 스크린샷 대조**

`admin-master-room-1440.png` 를 `admin-master.md` 와 대조:
- 오른쪽 강의실 표가 남는 폭(좌 396px 건물 패널 옆, 간격 space.5). 헤더 `마스터관2 강의실` + `1곳 · 학생 웹에 보이는 곳 1` + `층 = 호수 ÷ 100` + `+ 강의실`(primary — 이 화면의 채운 brand 버튼은 이것 하나).
- 컬럼 호수 72 · 층 52 · 유닛 64 · 학생 예약 128 · 노드 남는 폭 · 작업 92, 행 44px(설계 판정 — 스펙 42). 세로선 없음.
- 학생 예약 칸: Checkbox 16px + `받음`/`안 받음` 라벨(색만으로 말하지 않는다).
어긋나면 고치고 다시 찍는다.

- [ ] **Step 7: 커밋**

```bash
git add web/src/admin web/e2e
git commit -m "feat(web): 건물·강의실 화면 B — 강의실 표(층 파생·노드 칸), 학생 예약 즉시 부분 PATCH·실패 시 되돌림·0곳 Banner, 호수 잠금, 유닛 2→1 확인, 삭제 시 딸린 개수 + E2E"
```

---

### Task 13: 건물 · 강의실 C — 범위로 추가 + E2E

**Files:**
- Create: `web/src/admin/views/master/RangeAddModal.vue`
- Modify: `web/src/admin/views/master/RoomPanel.vue`, `web/src/admin/views/MasterView.vue`, `web/e2e/admin-ops.spec.ts`
- Test: `web/src/admin/__tests__/range.spec.ts`

**Interfaces:**
- Consumes: `roomsApi.createRoom`(Task 1) · `rangeProblem`·`rangeRooms`·`UNIT_OPTIONS`(Task 10) · Button `loadingLabel`(Task 3).
- Produces (`RangeAddModal.vue`): props `{ open: boolean; building: BuildingOut; rooms: RoomOut[] }`, emits `close` · `changed`. Modal 제목 `{건물} 범위로 추가`, 입력 `시작 호수`·`끝 호수`·`유닛`·`학생 예약을 받는다`, 칩 `button.chip`(`aria-pressed` = 만들 대상).
- Produces: RoomPanel emits `range: []` — 헤더 `범위로 추가`(secondary)와 빈 상태의 1차 액션.

- [ ] **Step 1: 실패 테스트**

`web/src/admin/__tests__/range.spec.ts`
```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import RangeAddModal from '@/admin/views/master/RangeAddModal.vue'
import { roomsApi } from '@/api/rooms'
import { ApiError, MESSAGES } from '@/api/client'
import type { BuildingOut, RoomOut } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/rooms', () => ({ roomsApi: { createRoom: vi.fn() } }))
const api = vi.mocked(roomsApi)

const building: BuildingOut = { id: 1, school_id: 1, name: '공학관', bld: 'E', modem_id: 'm1' }
const existing: RoomOut[] = [{ id: 13, building_id: 1, room: 503, units: 1, reservable: true }]

let w: VueWrapper
async function mountModal(rooms = existing) {
  w = mount(RangeAddModal, {
    props: { open: true, building, rooms },
    global: { stubs: { teleport: true } },
  })
  await flushPromises()
}
const control = (label: string) =>
  w
    .findAll('.field')
    .find((f) => f.get('label').text().replace('*', '').trim() === label)!
    .get('input')
const chip = (room: number) => w.findAll('button.chip').find((c) => c.text() === String(room))!
const submit = () => w.get('.range__submit')
async function range(a: string, b: string) {
  await control('시작 호수').setValue(a)
  await control('끝 호수').setValue(b)
}

beforeEach(() => {
  api.createRoom.mockReset().mockImplementation(async (r) => ({ id: r.room, ...r }))
  for (const t of [...toasts.value]) dismissToast(t.id)
})

describe('범위로 추가', () => {
  it('이미 있는 호수는 점선·잠김으로 보이고 빠진다 — 칩을 눌러 빼면 라벨이 실제 개수를 말한다', async () => {
    await mountModal()
    await range('501', '505')
    expect(w.text()).toContain('만들어질 방 5곳 중 4곳 · 이미 있는 1곳은 건너뛴다')
    expect(chip(503).classes()).toContain('chip--exists')
    expect((chip(503).element as HTMLButtonElement).disabled).toBe(true)
    expect(submit().text()).toContain('4곳 만들기')
    await chip(505).trigger('click')
    expect(chip(505).attributes('aria-pressed')).toBe('false')
    expect(submit().text()).toContain('3곳 만들기')
  })

  it('한 곳씩 POST(벌크 없음) — 끝나면 모뎀에 설정이 다시 내려갔다고 알리고 닫는다', async () => {
    await mountModal()
    await range('501', '504')
    await submit().trigger('click')
    await flushPromises()
    expect(api.createRoom.mock.calls.map((c) => c[0].room)).toEqual([501, 502, 504])
    expect(api.createRoom.mock.calls[0][0]).toEqual({
      building_id: 1,
      room: 501,
      units: 1,
      reservable: true,
    })
    expect(toasts.value.at(-1)?.message).toBe(
      '3곳을 만들었습니다. 공학관 모뎀Pi 에 설정이 다시 내려갔습니다.',
    )
    expect(w.emitted('changed')).toHaveLength(1)
    expect(w.emitted('close')).toHaveLength(1)
  })

  it('진행 라벨 — n / N 만드는 중', async () => {
    const release: (() => void)[] = []
    api.createRoom.mockImplementation(
      (r) => new Promise((res) => release.push(() => res({ id: r.room, ...r }))),
    )
    await mountModal()
    await range('501', '502')
    await submit().trigger('click')
    await flushPromises()
    expect(w.get('.btn__progress').text()).toBe('0 / 2 만드는 중')
    release[0]()
    await flushPromises()
    expect(w.get('.btn__progress').text()).toBe('1 / 2 만드는 중')
  })

  it('일부 실패 — 되돌리지 않고 실패한 호수만 남겨 재시도, 409(그사이 생김)는 실패가 아니다', async () => {
    api.createRoom.mockImplementation(async (r) => {
      if (r.room === 502) throw new ApiError(500, MESSAGES[500])
      if (r.room === 504) throw new ApiError(409, MESSAGES[409])
      return { id: r.room, ...r }
    })
    await mountModal()
    await range('501', '504')
    await submit().trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)).toMatchObject({
      tone: 'danger',
      message: '3곳 중 2곳 만듦 · 502호 실패',
    })
    expect(w.emitted('close')).toBeUndefined()
    expect(chip(502).classes()).toContain('chip--failed')
    expect(submit().text()).toContain('실패한 1곳 재시도')
    api.createRoom.mockClear()
    api.createRoom.mockImplementation(async (r) => ({ id: r.room, ...r }))
    await submit().trigger('click')
    await flushPromises()
    expect(api.createRoom.mock.calls.map((c) => c[0].room)).toEqual([502])
    expect(w.emitted('close')).toHaveLength(1)
  })

  it('100곳 넘게·거꾸로는 칩 없이 문장, 버튼 잠김', async () => {
    await mountModal()
    await range('101', '201')
    expect(w.text()).toContain('한 번에 100곳까지 만들 수 있습니다')
    expect(w.findAll('button.chip')).toHaveLength(0)
    expect((submit().element as HTMLButtonElement).disabled).toBe(true)
    await range('505', '501')
    expect(w.text()).toContain('끝 호수가 시작 호수보다 작습니다')
  })

  it('모뎀Pi 가 없는 건물 — 문 앞 화면은 갱신되지 않는다고 알린다', async () => {
    w = mount(RangeAddModal, {
      props: { open: true, building: { ...building, modem_id: null }, rooms: [] },
      global: { stubs: { teleport: true } },
    })
    await range('101', '101')
    await submit().trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe(
      '1곳을 만들었습니다. 모뎀Pi 가 배정되지 않아 문 앞 화면은 갱신되지 않습니다.',
    )
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin/__tests__/range.spec.ts`
Expected: FAIL — `Failed to resolve import "@/admin/views/master/RangeAddModal.vue"`

- [ ] **Step 3: 구현**

`web/src/admin/views/master/RangeAddModal.vue`
```vue
<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import Input from '@/components/ui/Input.vue'
import Modal from '@/components/ui/Modal.vue'
import Select from '@/components/ui/Select.vue'
import { showToast } from '@/components/ui/toast'
import { ApiError } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { BuildingOut, RoomOut } from '@/api/types'
import { UNIT_OPTIONS, rangeProblem, rangeRooms } from '../../masterView'

const props = defineProps<{ open: boolean; building: BuildingOut; rooms: RoomOut[] }>()
const emit = defineEmits<{ close: []; changed: [] }>()

const form = reactive({ start: '', end: '', units: 1, reservable: true })
const excluded = ref<number[]>([])
const failed = ref<number[]>([])
const running = ref(false)
const done = ref(0)
const total = ref(0)
watch(
  () => props.open,
  (open) => {
    if (!open) return
    Object.assign(form, { start: '', end: '', units: 1, reservable: true })
    excluded.value = []
    failed.value = []
    done.value = 0
    total.value = 0
  },
  { immediate: true },
)

const existing = computed(() =>
  props.rooms.filter((r) => r.building_id === props.building.id).map((r) => r.room),
)
const filled = computed(() => !!form.start.trim() && !!form.end.trim())
const problem = computed(() => (filled.value ? rangeProblem(form.start.trim(), form.end.trim()) : null))
const chips = computed(() =>
  filled.value && !problem.value
    ? rangeRooms(Number(form.start), Number(form.end), existing.value)
    : [],
)
// 실패한 것이 있으면 그것만 다시 — 아니면 이미 있는 것·뺀 것을 제외한 칩
const targets = computed(() =>
  failed.value.length
    ? failed.value
    : chips.value.filter((c) => !c.exists && !excluded.value.includes(c.room)).map((c) => c.room),
)
const skipped = computed(() => chips.value.filter((c) => c.exists).length)
const locked = computed(() => running.value || failed.value.length > 0)
// 버튼 라벨이 실제로 만들 개수를 말한다 — '추가'가 아니다
const label = computed(() =>
  failed.value.length ? `실패한 ${failed.value.length}곳 재시도` : `${targets.value.length}곳 만들기`,
)
const progress = computed(() => `${done.value} / ${total.value || targets.value.length} 만드는 중`)

function toggle(room: number) {
  excluded.value = excluded.value.includes(room)
    ? excluded.value.filter((r) => r !== room)
    : [...excluded.value, room]
}
function close() {
  if (!running.value) emit('close')
}

// 벌크 엔드포인트가 없다 — 한 곳씩 POST. 일부 실패해도 되돌리지 않는다: 되돌리는 DELETE 도 실패할 수 있다
async function run() {
  if (running.value || !targets.value.length) return
  const list = [...targets.value]
  running.value = true
  total.value = list.length
  done.value = 0
  const bad: number[] = []
  try {
    for (const room of list) {
      try {
        await roomsApi.createRoom({
          building_id: props.building.id,
          room,
          units: form.units,
          reservable: form.reservable,
        })
      } catch (e) {
        if (!(e instanceof ApiError)) throw e
        if (e.status === 401 || e.status === 403) return
        if (e.status !== 409) bad.push(room) // 409 = 그사이 누가 만들었다 — 있는 것으로 친다
      }
      done.value++
    }
  } finally {
    running.value = false
    emit('changed')
  }
  failed.value = bad
  const made = list.length - bad.length
  if (!bad.length) {
    // 방 하나마다 모뎀에 config 가 한 번씩 나간다 — 노드 화면의 변화를 예상하게
    const tail = props.building.modem_id
      ? `${props.building.name} 모뎀Pi 에 설정이 다시 내려갔습니다.`
      : '모뎀Pi 가 배정되지 않아 문 앞 화면은 갱신되지 않습니다.'
    showToast({ message: `${made}곳을 만들었습니다. ${tail}` })
    emit('close')
  } else
    showToast({
      tone: 'danger',
      message: `${list.length}곳 중 ${made}곳 만듦 · ${bad.map((r) => `${r}호`).join(', ')} 실패`,
    })
}
</script>

<template>
  <Modal
    :open="open"
    :title="`${building.name} 범위로 추가`"
    size="lg"
    :close-on-backdrop="!filled && !running"
    @close="close"
  >
    <div class="range">
      <div class="range__fields">
        <Input
          v-model="form.start"
          label="시작 호수"
          inputmode="numeric"
          class="num"
          :disabled="locked"
        />
        <Input
          v-model="form.end"
          label="끝 호수"
          inputmode="numeric"
          class="num"
          :disabled="locked"
          :error="problem ?? undefined"
        />
        <Select v-model="form.units" label="유닛" :options="UNIT_OPTIONS" :disabled="locked" />
        <Checkbox v-model="form.reservable" label="학생 예약을 받는다" :disabled="locked" />
      </div>
      <template v-if="chips.length">
        <p class="range__sum num">
          만들어질 방 {{ chips.length }}곳 중 {{ targets.length }}곳<template v-if="skipped">
            · 이미 있는 {{ skipped }}곳은 건너뛴다</template
          >
        </p>
        <!-- 범위 문법을 늘리지 않는다 — 보고 눌러서 뺀다. 이미 있는 호수는 조용히 지우지 않고 점선+취소선 -->
        <ul class="range__chips" aria-label="만들 호수">
          <li v-for="c in chips" :key="c.room">
            <button
              type="button"
              class="chip num"
              :class="{ 'chip--exists': c.exists, 'chip--failed': failed.includes(c.room) }"
              :disabled="c.exists || locked"
              :aria-pressed="!c.exists && !excluded.includes(c.room) ? 'true' : 'false'"
              :title="c.exists ? '이미 있음' : undefined"
              @click="toggle(c.room)"
            >
              {{ c.room }}
            </button>
          </li>
        </ul>
      </template>
    </div>
    <template #footer>
      <Button variant="secondary" :disabled="running" @click="close">취소</Button>
      <Button
        class="range__submit"
        :loading="running"
        :loading-label="progress"
        :disabled="!targets.length"
        @click="run"
        >{{ label }}</Button
      >
    </template>
  </Modal>
</template>

<style scoped>
.range__fields {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-3);
  align-items: end;
}
.range__sum {
  margin: var(--space-4) 0 var(--space-2);
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.range__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  max-height: 240px;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  list-style: none;
}
.chip {
  min-width: 52px;
  height: var(--control-height-sm);
  padding: 0 var(--space-2);
  border: var(--border-thin) solid var(--line-3);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-2);
  font: inherit;
  cursor: pointer;
}
.chip[aria-pressed='true'] {
  border-color: var(--brand);
  background: var(--brand-tint);
  color: var(--brand);
}
.chip--exists {
  border-style: dashed;
  color: var(--text-3);
  text-decoration: line-through;
  cursor: not-allowed;
}
.chip--failed {
  border: var(--border-thick) solid var(--danger);
  color: var(--danger);
}
</style>
```

`web/src/admin/views/master/RoomPanel.vue`
- `defineEmits` 를 `defineEmits<{ changed: []; range: [] }>()` 로 바꾼다.
- 헤더의 `<div class="panel__tools">…</div>` 를 바꾼다:
```vue
      <div class="panel__tools">
        <!-- 방 30개를 하나씩 넣는 것은 실사용이 안 된다 — 범위가 정상 경로 -->
        <Button variant="secondary" size="sm" @click="emit('range')">범위로 추가</Button>
        <Button size="sm" @click="openForm(null)">+ 강의실</Button>
      </div>
```
- `#empty` 의 EmptyState `actions` 를 바꾼다:
```vue
          :actions="[{ label: '범위로 추가', variant: 'primary', onClick: () => emit('range') }]"
```

`web/src/admin/views/MasterView.vue`
- import 에 `import RangeAddModal from './master/RangeAddModal.vue'` 를 더하고, `selected` 정의 **아래**에 `const ranging = ref(false)` 를 더한다.
- `<RoomPanel … @changed="reload" />` 에 `@range="ranging = true"` 를 더하고, `</div>`(master__body) **바로 뒤**에 추가:
```vue
    <RangeAddModal
      v-if="selected"
      :open="ranging"
      :building="selected"
      :rooms="data?.rooms ?? []"
      @close="ranging = false"
      @changed="reload"
    />
```

`web/src/admin/__tests__/masterRooms.spec.ts` 의 `'한 곳 추가 — …'` 테스트는 그대로 통과한다(`+ 강의실` 은 헤더에 남는다).

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`
Expected: PASS

- [ ] **Step 5: E2E**

`web/e2e/admin-ops.spec.ts` 끝에 추가
```ts
test('범위로 추가 — 이미 있는 호수는 점선·취소선, 눌러서 빼고, 라벨이 실제 개수를 말한다', async () => {
  const panel = roomPanel()
  await panel.getByRole('button', { name: '범위로 추가' }).first().click()
  const d = page.getByRole('dialog', { name: '마스터관2 범위로 추가' })
  await d.getByLabel('시작 호수').fill('101')
  await d.getByLabel('끝 호수').fill('105')
  await d.getByRole('button', { name: '5곳 만들기' }).click()
  await expect(d).toHaveCount(0)
  await expect(
    page.getByText('5곳을 만들었습니다. 마스터관2 모뎀Pi 에 설정이 다시 내려갔습니다.'),
  ).toBeVisible()
  await panel.getByRole('button', { name: '범위로 추가' }).first().click()
  await d.getByLabel('시작 호수').fill('101')
  await d.getByLabel('끝 호수').fill('112')
  await expect(d).toContainText('만들어질 방 12곳 중 7곳 · 이미 있는 5곳은 건너뛴다')
  await expect(d.getByRole('button', { name: '103', exact: true })).toBeDisabled()
  await d.getByRole('button', { name: '106', exact: true }).click()
  await expect(d.getByRole('button', { name: '6곳 만들기' })).toBeVisible()
  await shot(page, 'admin-master-range-1440')
  await d.getByRole('button', { name: '6곳 만들기' }).click()
  await expect(d).toHaveCount(0)
  await expect(panel).toContainText('11곳 · 학생 웹에 보이는 곳 11')
  await expect(panel.getByRole('row').filter({ hasText: '106' })).toHaveCount(0)
  await shot(page, 'admin-master-1440')
})
```

Run: **E2E 명령** + ` e2e/admin-ops.spec.ts`
Expected: `6 passed`

- [ ] **Step 6: 스크린샷 대조**

`admin-master-range-1440.png`·`admin-master-1440.png` 를 `admin-master.md` 와 대조:
- 범위 Modal(lg 800px): `시작 호수 [101] 끝 호수 [112] 유닛 [1 (문 하나)] ☑ 학생 예약을 받는다`, `만들어질 방 12곳 중 6곳 · 이미 있는 5곳은 건너뛴다`, 칩 줄 — 이미 있는 101~105 는 점선+취소선(고를 수 없음), 뺀 106 은 테두리만, 나머지는 brand.tint. 버튼 `6곳 만들기`(primary), 폭은 `0 / 0 만드는 중` 보다 좁지 않다(진행 중 흔들림 없음).
- 완료 후 표: 11행, 헤더 `11곳 · 학생 웹에 보이는 곳 11`, 층 칸 `1층`.
어긋나면 고치고 다시 찍는다.

- [ ] **Step 7: 커밋**

```bash
git add web/src/admin web/e2e
git commit -m "feat(web): 건물·강의실 화면 C — 범위로 추가(칩 미리보기·이미 있는 호수 표시·눌러서 빼기·100곳 상한), 한 곳씩 POST·진행 라벨·일부 실패는 실패분만 재시도 + E2E"
```

---

### Task 14: 강의실 설정 A — 트리 바 · 시간표 블록 · 추적 · 재전송 + E2E

**Files:**
- Create: `web/src/admin/roomsView.ts`, `web/src/admin/views/RoomsView.vue`, `web/src/admin/views/rooms/RowDot.vue`, `web/src/admin/views/rooms/SlotBlock.vue`
- Modify: `web/src/admin/router.ts`, `web/src/admin/AdminShell.vue`, `web/src/admin/__tests__/shell.spec.ts`, `web/e2e/helpers.ts`, `web/e2e/admin-ops.spec.ts`, `web/e2e/admin-shell.spec.ts`
- Test: `web/src/admin/__tests__/roomsView.spec.ts`, `web/src/admin/__tests__/rooms.spec.ts`

**Interfaces:**
- Consumes: `RoomTree`(Task 5) · `SlotForm`(Task 6) · `TypeBadge`·`SourceBadge`(Task 4) · `useOutboxTracker`·`picked`(Task 9) · `ConfirmModal`(Task 10) · `buildTree`(Task 5) · `roomsApi.{buildings, rooms, buildingSlots, buildingResv, buildingExams, deleteSlot}`(Task 1) · `OutboxDot`·`DotState`(F3) · E2E `sql()`(F3).
- Produces (`roomsView.ts`): `defaultPick(buildings, rooms): number[]`(첫 건물의 첫 층) · `roomLabeler(buildings, pickedRooms): (roomId: number) => string`(여러 건물이면 `K 101`, 아니면 `101`).
- Produces (`RowDot.vue`): props `{ state?: DotState }`, emits `resync: []` — 점 + 실패·취소면 `재전송`(ghost).
- Produces (`SlotBlock.vue`): props `{ rooms: RoomOut[]; label: (roomId: number) => string; slots: SlotWithRoom[]; states: Map<string, DotState>; loading: boolean }`, emits `saved: [SavedRow]` · `changed: []` · `resync: [roomId: number, key: string]`. 루트 `<section aria-labelledby="blk-slots">`(h2 `시간표`).
- Produces (`RoomsView.vue`): 라우트 `/rooms`. 상단 sticky 바 = RoomTree(multi, `v-model:selected` ↔ `picked`). 리소스 `master`(buildings·rooms)·`scope`(건물 단위 3개, 고른 방의 건물 id 가 바뀔 때만 다시). Task 15·16 이 블록을 더한다(파일 전체 교체).
- Produces (`e2e/helpers.ts`): `OPS = { building: '운영관', bld: 'K', modem: 'e2e-m6', rooms: [101, 102, 201, 202] }` · `seedOps(request): Promise<{ buildingId: number; roomIds: Record<number, number> }>`(멱등, 101 만 reservable).

- [ ] **Step 1: 실패 테스트**

`web/src/admin/__tests__/roomsView.spec.ts`
```ts
import { describe, expect, it } from 'vitest'
import { defaultPick, roomLabeler } from '@/admin/roomsView'
import type { BuildingOut, RoomOut } from '@/api/types'

const B = (id: number, name: string, bld: string): BuildingOut => ({
  id,
  school_id: 1,
  name,
  bld,
  modem_id: null,
})
const R = (id: number, building_id: number, room: number): RoomOut => ({
  id,
  building_id,
  room,
  units: 1,
  reservable: false,
})
const buildings = [B(1, '공학관', 'E'), B(2, '사회관', 'S')]
const rooms = [R(13, 1, 501), R(11, 1, 401), R(12, 1, 402), R(21, 2, 101)]

describe('roomsView', () => {
  it('첫 진입 — 첫 건물의 첫 층 (방이 없는 건물은 건너뛴다)', () => {
    expect(defaultPick(buildings, rooms)).toEqual([11, 12])
    expect(defaultPick([B(9, '빈 건물', 'Z'), ...buildings], rooms)).toEqual([11, 12])
    expect(defaultPick(buildings, [])).toEqual([])
  })
  it('호수 칸 — 한 건물이면 호수만, 여러 건물이면 건물 글자를 붙인다', () => {
    expect(roomLabeler(buildings, [rooms[1]])(11)).toBe('401')
    const many = roomLabeler(buildings, [rooms[1], rooms[3]])
    expect(many(11)).toBe('E 401')
    expect(many(21)).toBe('S 101')
    expect(many(99)).toBe('—')
  })
})
```

`web/src/admin/__tests__/rooms.spec.ts`
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import RoomsView from '@/admin/views/RoomsView.vue'
import { picked } from '@/admin/selection'
import { roomsApi } from '@/api/rooms'
import { loraApi } from '@/api/lora'
import type { BuildingOut, FailedOut, RoomOut, SlotWithRoom } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/rooms', () => ({
  IMPORT_MAX_BYTES: 1024 * 1024,
  roomsApi: {
    buildings: vi.fn(),
    rooms: vi.fn(),
    buildingSlots: vi.fn(),
    buildingResv: vi.fn(),
    buildingExams: vi.fn(),
    buildingOutbox: vi.fn(),
    putSlot: vi.fn(),
    deleteSlot: vi.fn(),
    saveResv: vi.fn(),
    deleteResv: vi.fn(),
    saveExam: vi.fn(),
    deleteExam: vi.fn(),
    importSlots: vi.fn(),
  },
}))
vi.mock('@/api/lora', () => ({ loraApi: { syncRoom: vi.fn() } }))
vi.mock('@/api/admin', () => ({
  adminApi: {
    pendingResv: vi.fn(async () => []),
    approveResv: vi.fn(),
    rejectResv: vi.fn(),
    cancelResv: vi.fn(),
  },
}))
const api = vi.mocked(roomsApi)
const lora = vi.mocked(loraApi)

const B = (id: number, name: string, bld: string): BuildingOut => ({
  id,
  school_id: 1,
  name,
  bld,
  modem_id: 'm1',
})
const R = (id: number, building_id: number, room: number): RoomOut => ({
  id,
  building_id,
  room,
  units: 1,
  reservable: false,
})
const S = (room_id: number, day: number, s_h: number, subject: string): SlotWithRoom => ({
  id: room_id * 100 + day * 10 + s_h,
  room_id,
  day,
  s_h,
  s_m: 0,
  e_h: s_h + 1,
  e_m: 0,
  type: 1,
  subject,
  professor: '',
  source: 2,
})

let w: VueWrapper
async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:p(.*)*', component: { render: () => null } }],
  })
  await router.push('/rooms')
  w = mount(RoomsView, { global: { plugins: [router], stubs: { teleport: true } } })
  await flushPromises()
}
type Root = VueWrapper | DOMWrapper<Element>
const btn = (root: Root, text: string) => root.findAll('button').find((b) => b.text() === text)!
const dialog = (title: string) =>
  w.findAll('[role=dialog]').find((d) => d.get('h2').text() === title)!
const control = (root: Root, label: string) =>
  root
    .findAll('.field, .sel')
    .find((f) => f.find('label').exists() && f.get('label').text().replace('*', '').trim() === label)!
    .get('input, select')
const slotRows = () => w.get('[aria-labelledby=blk-slots]').findAll('tbody tr')

beforeEach(() => {
  picked.value = []
  Object.values(api).forEach((f) => f.mockReset())
  lora.syncRoom.mockReset()
  api.buildings.mockResolvedValue([B(1, '공학관', 'E'), B(2, '사회관', 'S')])
  api.rooms.mockResolvedValue([R(11, 1, 401), R(12, 1, 402), R(13, 1, 501), R(21, 2, 101)])
  api.buildingSlots.mockImplementation(async (b: number) =>
    b === 1 ? [S(11, 1, 9, '캡스톤디자인'), S(13, 2, 10, '운영체제')] : [S(21, 3, 9, '사회학개론')],
  )
  api.buildingResv.mockResolvedValue([])
  api.buildingExams.mockResolvedValue([])
  api.buildingOutbox.mockResolvedValue([])
  for (const t of [...toasts.value]) dismissToast(t.id)
})
afterEach(() => vi.useRealTimers())

describe('강의실 설정 — 트리와 시간표', () => {
  it('첫 진입 — 첫 건물의 첫 층을 고르고 그 방들 슬롯만, 건물 단위로 한 번', async () => {
    await mountView()
    expect(picked.value).toEqual([11, 12])
    expect(w.get('.tree__trigger').text()).toContain('공학관 401 · 402')
    expect(slotRows()).toHaveLength(1)
    expect(slotRows()[0].text()).toContain('캡스톤디자인')
    expect(api.buildingSlots.mock.calls).toEqual([[1]])
  })

  it('같은 건물 안에서 바꾸면 다시 부르지 않고, 다른 건물을 더하면 호수에 건물 글자', async () => {
    await mountView()
    picked.value = [11, 13]
    await flushPromises()
    expect(slotRows()).toHaveLength(2)
    expect(api.buildingSlots).toHaveBeenCalledTimes(1)
    picked.value = [11, 21]
    await flushPromises()
    expect(api.buildingSlots.mock.calls.slice(1)).toEqual([[1], [2]])
    expect(slotRows().map((r) => r.find('td').text())).toEqual(['E 401', 'S 101'])
  })

  it('다 해제하면 "위에서 강의실을 고르세요"', async () => {
    await mountView()
    picked.value = []
    await flushPromises()
    expect(w.get('[aria-labelledby=blk-slots]').text()).toContain('위에서 강의실을 고르세요')
  })

  it('저장하면 대기 점 → 실패로 바뀌면 재전송(방 단위) → 다시 대기', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
    api.putSlot.mockResolvedValue({ outbox_ids: [7], id: null })
    await mountView()
    await btn(w.get('[aria-labelledby=blk-slots]'), '+ 슬롯 추가').trigger('click')
    const d = dialog('슬롯 추가')
    await control(d, '요일').setValue('3')
    await control(d, '시작').setValue('14:00')
    await control(d, '종료').setValue('15:00')
    await control(d, '과목명').setValue('자료구조')
    api.buildingSlots.mockImplementation(async () => [
      S(11, 1, 9, '캡스톤디자인'),
      S(11, 3, 14, '자료구조'),
    ])
    await btn(d, '저장').trigger('click')
    await flushPromises()
    const row = () => slotRows().find((r) => r.text().includes('자료구조'))!
    expect(row().get('.dot').attributes('title')).toBe('대기')
    api.buildingOutbox.mockResolvedValue([
      { id: 7, state: 'failed', last_error: 'max_retries' } as unknown as FailedOut,
    ])
    await vi.advanceTimersByTimeAsync(3_000)
    expect(row().get('.dot').attributes('title')).toBe('실패')
    lora.syncRoom.mockResolvedValue({ outbox_ids: [9], id: null })
    api.buildingOutbox.mockResolvedValue([])
    await btn(row(), '재전송').trigger('click')
    await flushPromises()
    expect(lora.syncRoom).toHaveBeenCalledWith(11)
    expect(row().get('.dot').attributes('title')).toBe('대기')
  })

  it('강의실이 하나도 없으면 건물 · 강의실로 보낸다', async () => {
    api.rooms.mockResolvedValue([])
    await mountView()
    expect(w.text()).toContain('강의실이 없습니다. 건물 · 강의실 화면에서 먼저 만드세요.')
  })
})
```

`web/src/admin/__tests__/shell.spec.ts` 첫 `it`(Task 11 에서 바꾼 것)의 메뉴 기대값과 인덱스를 바꾼다
```ts
    expect(links.map((a) => a.text().replace(/\d+/g, '').trim())).toEqual([
      '건물 · 강의실',
      '강의실 설정',
      '노드 상태',
      '전송 현황',
      '회원',
    ])
    expect(links[3].attributes('aria-current')).toBe('page')
    expect(links[4].text()).toContain('2')
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin`
Expected: FAIL — `Failed to resolve import "@/admin/roomsView"` / `"@/admin/views/RoomsView.vue"`, shell.spec 메뉴 배열 불일치

- [ ] **Step 3: 구현**

`web/src/admin/roomsView.ts`
```ts
import type { BuildingOut, RoomOut } from '@/api/types'
import { buildTree } from '@/components/domain/roomTree'

/** 첫 진입 — 첫 건물의 첫 층. 건물 전체는 행이 너무 많다 (admin-rooms.md "층이나 강의실 몇 개만 고르는 것이 기본") */
export function defaultPick(buildings: BuildingOut[], rooms: RoomOut[]): number[] {
  const first = buildTree(buildings, rooms).find((b) => b.ids.length)
  return first ? first.floors[0].rooms.map((r) => r.id) : []
}

/** 호수 칸 — 고른 방이 여러 건물에 걸치면 건물 글자를 붙인다 (같은 호수가 두 건물에 있을 수 있다) */
export function roomLabeler(buildings: BuildingOut[], rooms: RoomOut[]): (roomId: number) => string {
  const many = new Set(rooms.map((r) => r.building_id)).size > 1
  return (roomId) => {
    const r = rooms.find((x) => x.id === roomId)
    if (!r) return '—'
    const b = buildings.find((x) => x.id === r.building_id)
    return many && b ? `${b.bld} ${r.room}` : String(r.room)
  }
}
```

`web/src/admin/views/rooms/RowDot.vue`
```vue
<script setup lang="ts">
import Button from '@/components/ui/Button.vue'
import OutboxDot, { type DotState } from '@/components/domain/OutboxDot.vue'

defineProps<{ state?: DotState }>()
const emit = defineEmits<{ resync: [] }>()
</script>

<template>
  <span v-if="state" class="rowdot">
    <OutboxDot :state="state" />
    <!-- 실패·관리자 취소는 노드에 가지 않았다 — 방 단위 재전송 (POST /rooms/{id}/sync) -->
    <Button
      v-if="state === 'failed' || state === 'cancelled'"
      variant="ghost"
      size="sm"
      @click="emit('resync')"
      >재전송</Button
    >
  </span>
</template>

<style scoped>
.rowdot {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
}
</style>
```

`web/src/admin/views/rooms/SlotBlock.vue`
```vue
<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Select from '@/components/ui/Select.vue'
import Table from '@/components/ui/Table.vue'
import { showToast } from '@/components/ui/toast'
import SlotForm from '@/components/domain/SlotForm.vue'
import SourceBadge from '@/components/domain/SourceBadge.vue'
import TypeBadge from '@/components/domain/TypeBadge.vue'
import type { DotState } from '@/components/domain/OutboxDot.vue'
import { DAYS, DAY_OPTIONS, TYPE_OPTIONS, slotKey, type SavedRow } from '@/components/domain/rules'
import { ApiError } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { RoomOut, SlotWithRoom } from '@/api/types'
import { hm } from '@/lib/time'
import ConfirmModal from '../../ConfirmModal.vue'
import RowDot from './RowDot.vue'

const props = defineProps<{
  rooms: RoomOut[]
  label: (roomId: number) => string
  slots: SlotWithRoom[]
  states: Map<string, DotState>
  loading: boolean
}>()
const emit = defineEmits<{
  saved: [row: SavedRow]
  changed: []
  resync: [roomId: number, key: string]
}>()

// 호수 필터는 트리가 한다 — 블록에는 요일·유형만 (admin-rooms.md)
const ALL = { value: 0, label: '전체' }
const day = ref(0)
const type = ref(0)
const order = (roomId: number) => props.rooms.findIndex((r) => r.id === roomId)
const rows = computed(() =>
  props.slots
    .filter((s) => (!day.value || s.day === day.value) && (!type.value || s.type === type.value))
    .sort(
      (a, b) =>
        order(a.room_id) - order(b.room_id) || a.day - b.day || a.s_h - b.s_h || a.s_m - b.s_m,
    )
    .map((s) => ({ ...s, key: slotKey(s) })),
)
const COLUMNS = [
  { key: 'room', label: '호수', width: '72px' },
  { key: 'day', label: '요일', width: '56px' },
  { key: 'start', label: '시작', width: '64px' },
  { key: 'end', label: '종료', width: '64px' },
  { key: 'subject', label: '과목명' },
  { key: 'professor', label: '교수', width: '96px' },
  { key: 'type', label: '유형', width: '80px' },
  { key: 'source', label: '출처', width: '64px' },
  { key: 'actions', label: '작업', width: '104px', align: 'right' as const },
]
const asS = (row: Record<string, unknown>) => row as unknown as SlotWithRoom & { key: string }
const roomLabel = (r: RoomOut) => `${props.label(r.id)}호`

// 추가·수정은 같은 폼 — 페이지2 셀 편집도 이 폼이다 (검증이 경로마다 갈라지지 않게)
const formOpen = ref(false)
const editing = ref<SlotWithRoom | null>(null)
function openForm(s: SlotWithRoom | null) {
  editing.value = s
  formOpen.value = true
}
function onSaved(r: SavedRow) {
  emit('saved', r)
  emit('changed')
}

const removing = ref<SlotWithRoom | null>(null)
const busy = ref(false)
async function remove() {
  const s = removing.value
  if (!s || busy.value) return
  busy.value = true
  try {
    await roomsApi.deleteSlot(s.room_id, s) // 없는 키는 서버가 조용히 넘긴다(멱등)
    showToast({ message: '지웠습니다.' })
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status !== 401 && e.status !== 403) showToast({ tone: 'danger', message: e.message })
  } finally {
    busy.value = false
    removing.value = null
    emit('changed')
  }
}
</script>

<template>
  <section class="blk" aria-labelledby="blk-slots">
    <header class="blk__head">
      <h2 id="blk-slots" class="blk__title">시간표</h2>
      <Select v-model="day" label="요일" size="sm" :options="[ALL, ...DAY_OPTIONS]" class="blk__filter" />
      <Select v-model="type" label="유형" size="sm" :options="[ALL, ...TYPE_OPTIONS]" class="blk__filter" />
      <Button class="blk__add" :disabled="!rooms.length" @click="openForm(null)">+ 슬롯 추가</Button>
    </header>
    <Table
      :columns="COLUMNS"
      :rows="rows as unknown as Record<string, unknown>[]"
      row-key="key"
      :loading="loading"
    >
      <template #empty>
        <EmptyState v-if="!rooms.length" message="위에서 강의실을 고르세요" />
        <EmptyState v-else-if="day || type" message="조건에 맞는 슬롯이 없습니다" />
        <EmptyState
          v-else
          message="이 건물에 등록된 시간표가 없습니다"
          :actions="[{ label: '슬롯 추가', variant: 'primary', onClick: () => openForm(null) }]"
        />
      </template>
      <template #cell-room="{ row }">
        <!-- 호수를 누르면 그 강의실의 한 주 (페이지2) -->
        <RouterLink class="blk__room num" :to="`/rooms/${asS(row).room_id}/week`">{{
          label(asS(row).room_id)
        }}</RouterLink>
      </template>
      <template #cell-day="{ row }">{{ DAYS[asS(row).day - 1] }}</template>
      <template #cell-start="{ row }"
        ><span class="num">{{ hm(asS(row).s_h, asS(row).s_m) }}</span></template
      >
      <template #cell-end="{ row }"
        ><span class="num">{{ hm(asS(row).e_h, asS(row).e_m) }}</span></template
      >
      <template #cell-professor="{ row }">{{ asS(row).professor || '—' }}</template>
      <template #cell-type="{ row }"><TypeBadge :type="asS(row).type" /></template>
      <template #cell-source="{ row }"><SourceBadge :source="asS(row).source" /></template>
      <template #cell-actions="{ row }">
        <div class="blk__actions">
          <RowDot
            :state="states.get(asS(row).key)"
            @resync="emit('resync', asS(row).room_id, asS(row).key)"
          />
          <Button variant="ghost" size="sm" @click="openForm(asS(row))">수정</Button>
          <Button variant="ghost" size="sm" @click="removing = asS(row)">삭제</Button>
        </div>
      </template>
    </Table>
    <SlotForm
      :open="formOpen"
      :mode="editing ? 'edit' : 'create'"
      :rooms="rooms"
      :room-label="roomLabel"
      :value="editing"
      :preset="rooms[0] ? { room_id: rooms[0].id } : null"
      :existing="slots"
      @close="formOpen = false"
      @saved="onSaved"
      @stale="emit('changed')"
    />
    <ConfirmModal
      :open="!!removing"
      title="슬롯 삭제"
      :lines="
        removing
          ? [
              `${label(removing.room_id)}호 ${DAYS[removing.day - 1]} ${hm(removing.s_h, removing.s_m)} ${removing.subject}`,
            ]
          : []
      "
      :loading="busy"
      @confirm="remove"
      @close="removing = null"
    />
  </section>
</template>

<style scoped>
.blk {
  overflow: hidden;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.blk__head {
  display: flex;
  align-items: flex-end;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
}
.blk__title {
  align-self: center;
  margin: 0 var(--space-2) 0 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.blk__filter {
  width: 120px;
}
.blk__add {
  margin-left: auto;
}
.blk__room {
  color: var(--text-1);
  font-weight: var(--font-weight-medium);
}
.blk__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-1);
}
</style>
```

`web/src/admin/views/RoomsView.vue`
```vue
<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import EmptyState from '@/components/ui/EmptyState.vue'
import { showToast } from '@/components/ui/toast'
import RoomTree from '@/components/domain/RoomTree.vue'
import type { SavedRow } from '@/components/domain/rules'
import { roomsApi } from '@/api/rooms'
import type { RoomOut } from '@/api/types'
import { useResource } from '@/lib/useResource'
import { useOutboxTracker } from '../outboxTrack'
import { defaultPick, roomLabeler } from '../roomsView'
import { picked } from '../selection'
import SlotBlock from './rooms/SlotBlock.vue'

const router = useRouter()
const master = useResource(async () => {
  const [buildings, rooms] = await Promise.all([roomsApi.buildings(), roomsApi.rooms()])
  return { buildings, rooms }
})
const buildings = computed(() => master.data.value?.buildings ?? [])
const allRooms = computed(() => master.data.value?.rooms ?? [])
const hasNoRooms = computed(() => !!master.data.value && !allRooms.value.length)

// 트리 선택은 모듈 상태 — 다른 화면을 다녀와도 남는다. 지워진 방은 빼고, 비었으면 첫 건물의 첫 층
watch(master.data, (d) => {
  if (!d) return
  const alive = picked.value.filter((id) => d.rooms.some((r) => r.id === id))
  picked.value = alive.length ? alive : defaultPick(d.buildings, d.rooms)
})
const selection = computed({
  get: () => picked.value,
  set: (ids: number[]) => (picked.value = ids),
})
const order = (r: RoomOut) => buildings.value.findIndex((b) => b.id === r.building_id)
const pickedRooms = computed(() =>
  allRooms.value
    .filter((r) => picked.value.includes(r.id))
    .sort((a, b) => order(a) - order(b) || a.room - b.room),
)
const label = computed(() => roomLabeler(buildings.value, pickedRooms.value))

// 건물 단위 조회 3개 (S4b §2.6) — 같은 건물 안에서 고른 방을 바꿔도 다시 부르지 않고 걸러서 보인다
const bids = computed(() =>
  [...new Set(pickedRooms.value.map((r) => r.building_id))].sort((a, b) => a - b),
)
const scope = useResource(
  async () => {
    const per = await Promise.all(
      bids.value.map((b) =>
        Promise.all([roomsApi.buildingSlots(b), roomsApi.buildingResv(b), roomsApi.buildingExams(b)]),
      ),
    )
    return {
      slots: per.flatMap((p) => p[0]),
      resv: per.flatMap((p) => p[1]),
      exams: per.flatMap((p) => p[2]),
    }
  },
  { deps: () => bids.value.join(',') },
)
const inPick = <T extends { room_id: number }>(xs: T[] | undefined) =>
  (xs ?? []).filter((x) => picked.value.includes(x.room_id))
const slots = computed(() => inPick(scope.data.value?.slots))
const scopeLoading = computed(() => scope.loading.value && !scope.data.value)

// 오류 — Toast + 재시도. 표는 이전 내용을 지우지 않는다 (useResource 가 data 를 지킨다)
for (const r of [master, scope])
  watch(r.error, (e) => {
    if (e && e.status !== 401 && e.status !== 403)
      showToast({
        tone: 'danger',
        message: e.message,
        action: { label: '재시도', onClick: () => void r.reload() },
      })
  })

// 저장 뒤 OutboxDot — 행 key 로 30초 (새로고침하면 끊긴다)
const tracker = useOutboxTracker()
const buildingOf = (roomId: number) => allRooms.value.find((r) => r.id === roomId)?.building_id
function onSaved(s: SavedRow) {
  const b = buildingOf(s.roomId)
  if (b !== undefined) tracker.track(s.key, b, s.outboxIds)
}
function resync(roomId: number, key: string) {
  const b = buildingOf(roomId)
  if (b !== undefined) void tracker.resync(key, roomId, b)
}
</script>

<template>
  <main class="rooms">
    <!-- 상단 바는 스크롤해도 붙어 있다 — 트리에서 고른 것이 아래 표들의 범위다 -->
    <header class="rooms__bar">
      <RoomTree v-model:selected="selection" :buildings="buildings" :rooms="allRooms" />
      <span class="rooms__hint">강의실 선택</span>
    </header>
    <EmptyState
      v-if="hasNoRooms"
      message="강의실이 없습니다. 건물 · 강의실 화면에서 먼저 만드세요."
      :actions="[{ label: '건물 · 강의실로', variant: 'primary', onClick: () => router.push('/master') }]"
    />
    <div v-else class="rooms__blocks">
      <SlotBlock
        :rooms="pickedRooms"
        :label="label"
        :slots="slots"
        :states="tracker.states"
        :loading="scopeLoading"
        @saved="onSaved"
        @changed="scope.reload"
        @resync="resync"
      />
    </div>
  </main>
</template>

<style scoped>
.rooms {
  padding: 0 var(--space-5) var(--space-5);
}
.rooms__bar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) 0;
  background: var(--bg);
}
.rooms__hint {
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
/* 탭이 아니라 세로 스택 — 셋이 같은 강의실의 다른 시간 축이라 함께 보여야 한다 */
.rooms__blocks {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}
</style>
```

`web/src/admin/router.ts` 의 `children` 에서 `{ path: 'master', … }` 줄 **아래**에 추가
```ts
      { path: 'rooms', component: () => import('./views/RoomsView.vue') },
```

`web/src/admin/AdminShell.vue` 의 `nav` 에서 `{ to: '/master', label: '건물 · 강의실' },` 줄 **아래**에 추가
```ts
  { to: '/rooms', label: '강의실 설정' },
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`
Expected: PASS

- [ ] **Step 5: E2E — 시드 + 트리 + 시간표**

`web/e2e/helpers.ts` 끝에 추가
```ts
/** 강의실 설정·주간 시간표 E2E 용 — 운영관(K) 101·102·201·202, 학생 예약은 101 만.
 * 모뎀은 등록만 한다(연결 없음) → outbox 는 대기로 남고, 무선 결과는 테스트가 sql() 로 흉내 낸다 */
export const OPS = {
  building: '운영관',
  bld: 'K',
  modem: 'e2e-m6',
  rooms: [101, 102, 201, 202],
} as const

export async function seedOps(
  request: APIRequestContext,
): Promise<{ buildingId: number; roomIds: Record<number, number> }> {
  const headers = { authorization: `Bearer ${await apiLogin(request, cfg.ADMINS[0])}` }
  const get = async <T>(p: string): Promise<T> => {
    const r = await request.get(p, { headers })
    expect(r.status(), p).toBe(200)
    return (await r.json()) as T
  }
  let b = (await get<{ id: number; bld: string }[]>('/api/buildings')).find((x) => x.bld === OPS.bld)
  if (!b) {
    await ensureModems(request, [OPS.modem])
    const r = await request.post('/api/buildings', {
      headers,
      data: { school_id: 1, name: OPS.building, bld: OPS.bld, modem_id: OPS.modem },
    })
    expect(r.status()).toBe(200)
    b = (await r.json()) as { id: number; bld: string }
    for (const room of OPS.rooms) {
      const rr = await request.post('/api/rooms', {
        headers,
        data: { building_id: b.id, room, units: 1, reservable: room === 101 },
      })
      expect(rr.status(), String(room)).toBe(200)
    }
  }
  const buildingId = b.id
  const rooms = await get<{ id: number; building_id: number; room: number }[]>('/api/rooms')
  return {
    buildingId,
    roomIds: Object.fromEntries(
      rooms.filter((r) => r.building_id === buildingId).map((r) => [r.room, r.id]),
    ),
  }
}
```

`web/e2e/admin-ops.spec.ts`
- helpers import 를 `import { OPS, SIZES, WEB_URL, ensureModems, fillLogin, nextAdmin, seedOps, shot, sql } from './helpers'` 로 바꾼다.
- 파일 끝에 추가:
```ts
// ---- 강의실 설정 ----
let ops: Awaited<ReturnType<typeof seedOps>>
const slotsBlock = () => page.getByRole('region', { name: '시간표' })
/** 테스트 전용 — 모뎀이 연결되지 않은 E2E 에서 무선 결과(ACK·실패·취소)를 흉내 낸다 */
const setOutbox = (room: number, state: string, lastError: string | null = null) =>
  sql(
    `UPDATE outbox SET state = '${state}', last_error = ${lastError ? `'${lastError}'` : 'NULL'}, ` +
      `finished_at = strftime('%Y-%m-%d %H:%M:%S', 'now') ` +
      `WHERE bld = '${OPS.bld}' AND room = ${room} AND state IN ('queued', 'dispatched')`,
  )

test('강의실 설정 — 트리: 건물 전체, 검색해도 선택 유지, 버튼 라벨이 선택을 말한다', async () => {
  ops = await seedOps(api)
  await page.getByRole('link', { name: '강의실 설정' }).click()
  await expect(page).toHaveURL(/\/admin\/rooms$/)
  const trigger = page.locator('.tree__trigger')
  await trigger.click()
  const tree = page.getByRole('group', { name: '강의실 선택' })
  await tree.getByRole('button', { name: '전체 해제' }).click()
  await expect(trigger).toContainText('강의실 선택')
  await expect(slotsBlock().getByText('위에서 강의실을 고르세요')).toBeVisible()
  await tree.getByRole('checkbox', { name: OPS.building }).check()
  await expect(trigger).toContainText(`${OPS.building} 101 외 3곳`)
  await tree.getByLabel('호수 검색').fill('201')
  await expect(tree.getByRole('checkbox', { name: '101호' })).toHaveCount(0)
  await tree.getByRole('checkbox', { name: '201호' }).uncheck()
  await tree.getByLabel('호수 검색').fill('')
  await expect(trigger).toContainText(`${OPS.building} 101 · 102 · 202`)
  await page.keyboard.press('Escape')
  await expect(tree).toHaveCount(0)
  await expect(slotsBlock().getByText('이 건물에 등록된 시간표가 없습니다')).toBeVisible()
})

test('시간표 — 추가, 겹침은 저장 전에 막음, 시작을 바꾸면 옛 행이 남지 않음, 점 대기 → 반영됨', async () => {
  const slots = slotsBlock()
  await slots.getByRole('button', { name: '+ 슬롯 추가' }).click()
  const d = page.getByRole('dialog', { name: '슬롯 추가' })
  await d.getByLabel('강의실').selectOption({ label: '101호' })
  await d.getByLabel('요일').selectOption({ label: '월' })
  await d.getByLabel('시작').fill('09:00')
  await d.getByLabel('종료').fill('11:00')
  await d.getByLabel('과목명').fill('캡스톤디자인')
  await d.getByLabel('교수').fill('김교수')
  await d.getByRole('button', { name: '저장' }).click()
  await expect(d).toHaveCount(0)
  const row = slots.getByRole('row').filter({ hasText: '캡스톤디자인' })
  await expect(row).toContainText('수동')
  await expect(row.getByRole('img', { name: '대기' })).toBeVisible()
  // 겹침 — 서버는 같은 키만 막는다. 폼이 먼저 막는다
  await slots.getByRole('button', { name: '+ 슬롯 추가' }).click()
  await d.getByLabel('강의실').selectOption({ label: '101호' })
  await d.getByLabel('요일').selectOption({ label: '월' })
  await d.getByLabel('시작').fill('10:00')
  await d.getByLabel('종료').fill('12:00')
  await d.getByRole('button', { name: '저장' }).click()
  await expect(d.getByText('겹칩니다: 09:00–11:00 캡스톤디자인')).toBeVisible()
  await d.getByRole('button', { name: '취소' }).click()
  // 시작을 바꾸면 새 행을 넣고 옛 행을 지운다 — 한 줄만 남는다
  await row.getByRole('button', { name: '수정' }).click()
  const e = page.getByRole('dialog', { name: '슬롯 수정' })
  await e.getByLabel('시작').fill('13:00')
  await e.getByLabel('종료').fill('15:00')
  await e.getByRole('button', { name: '저장' }).click()
  await expect(e).toHaveCount(0)
  await expect(row).toHaveCount(1)
  await expect(row).toContainText('13:00')
  setOutbox(101, 'acked')
  await expect(row.getByRole('img', { name: '반영됨' })).toBeVisible({ timeout: 10_000 })
})

test('전송 실패 — 점이 실패 + 재전송(방 단위), 관리자 취소는 취소됨', async () => {
  const slots = slotsBlock()
  await slots.getByRole('button', { name: '+ 슬롯 추가' }).click()
  const d = page.getByRole('dialog', { name: '슬롯 추가' })
  await d.getByLabel('강의실').selectOption({ label: '102호' })
  await d.getByLabel('요일').selectOption({ label: '화' })
  await d.getByLabel('과목명').fill('임베디드')
  await d.getByRole('button', { name: '저장' }).click()
  const row = slots.getByRole('row').filter({ hasText: '임베디드' })
  await expect(row.getByRole('img', { name: '대기' })).toBeVisible()
  setOutbox(102, 'failed', 'max_retries')
  await expect(row.getByRole('img', { name: '실패' })).toBeVisible({ timeout: 10_000 })
  await row.getByRole('button', { name: '재전송' }).click()
  await expect(page.getByText('다시 보냈습니다.')).toBeVisible()
  await expect(row.getByRole('img', { name: '대기' })).toBeVisible()
  setOutbox(102, 'failed', 'cancelled')
  await expect(row.getByRole('img', { name: '취소됨 — 노드에 반영 안 됨' })).toBeVisible({
    timeout: 10_000,
  })
  await expect(row.getByRole('button', { name: '재전송' })).toBeVisible()
  await shot(page, 'admin-rooms-slots-1440')
})
```

`web/e2e/admin-shell.spec.ts` 첫 테스트의 메뉴 기대값을 바꾼다
```ts
  await expect(page.locator('nav a')).toHaveText([
    /^건물 · 강의실$/,
    /^강의실 설정$/,
    /^노드 상태$/,
    /^전송 현황$/,
    /^회원\s*\d+$/,
  ])
```

Run: **E2E 명령** + ` e2e/admin-ops.spec.ts e2e/admin-shell.spec.ts`
Expected: `11 passed`

- [ ] **Step 6: 스크린샷 대조**

`admin-rooms-slots-1440.png` 를 `admin-rooms.md` 와 대조:
- 상단 sticky 바: `[운영관 101 · 102 · 202 [3] ▾] 강의실 선택`. 좌측 세로 트리 패널 없음(드롭다운).
- 시간표 블록(카드: surface + line.2 1px + radius.lg): 헤더 `시간표` + `요일[전체▾]` `유형[전체▾]` + `+ 슬롯 추가`. 컬럼 호수 72 · 요일 56 · 시작 64 · 종료 64 · 과목명 남는 폭(≈490px) · 교수 96 · 유형 80 · 출처 64 · 작업 104(우측). 세로선 없음, 헤더 아래 line.2 2px.
- 호수는 링크, 시각은 tabular-nums. 유형 `수업중`(busy 틴트), 출처 `수동`(채움). 작업 칸: 점 + `수정`·`삭제`(ghost), 실패·취소 행은 `재전송` 이 더 붙는다. 취소 점은 테두리 + 사선(회색, 적색 아님).
어긋나면 고치고 다시 찍는다.

- [ ] **Step 7: 커밋**

```bash
git add web/src/admin web/e2e
git commit -m "feat(web): 강의실 설정 A — 상단 트리 바(선택 유지·첫 층 기본), 시간표 블록(요일·유형 필터·출처·호수→주간), 저장 뒤 점 추적·실패/취소 재전송 + E2E"
```

---

### Task 15: 강의실 설정 B — 예약 블록 · 신청 대기 + E2E

**Files:**
- Create: `web/src/admin/views/rooms/ResvBlock.vue`, `web/src/admin/views/rooms/PendingBlock.vue`
- Modify: `web/src/admin/roomsView.ts`, `web/src/admin/views/RoomsView.vue`(전체 교체), `web/e2e/admin-ops.spec.ts`
- Test: `web/src/admin/__tests__/roomsView.spec.ts`, `web/src/admin/__tests__/resv.spec.ts`

**Interfaces:**
- Consumes: `ResvForm`(Task 7) · `adminApi.{pendingResv, approveResv, rejectResv, cancelResv}`·`roomsApi.deleteResv`(Task 1) · `conflictMessage`·`resvWindow`·`LATER_HINT`·`resvKey`(Task 2) · `Textarea`(F1) · `createStudent`·`apiLogin`(F1 helpers).
- Produces (`roomsView.ts`): `resvDot(r: ResvWithRoom, tracked: DotState | undefined, today: string): DotState | undefined` — 추적 중이면 그 상태, 아니면 `pushed_at == null` 이고 창 밖(later)일 때만 `'scheduled'`.
- Produces (`ResvBlock.vue`): props `{ rooms; label; resv: ResvWithRoom[]; states; loading }`, emits `saved`·`changed`·`resync`. 루트 `<section aria-labelledby="blk-resv">`(h2 `예약`). approved 만 그린다. 학생 신청이던 행은 `취소`(확인 `예약 취소`), 관리자가 넣은 행은 `수정`·`삭제`.
- Produces (`PendingBlock.vue`): props `{ pending?: ResvAdminOut[] }`, emits `changed`. 루트 `<section aria-labelledby="blk-pending">`(h2 `신청 대기`) — 0건이면 섹션 자체가 없다. 거절 Modal `예약 신청 거절`, 입력 `거절 사유`.

- [ ] **Step 1: 실패 테스트**

`web/src/admin/__tests__/roomsView.spec.ts` 끝에 추가 (import 에 `resvDot` 과 `import type { ResvWithRoom } from '@/api/types'` 를 더한다)
```ts
describe('resvDot — 예약 행의 점', () => {
  const r = (o: Partial<ResvWithRoom>): ResvWithRoom => ({
    id: 7,
    room_id: 11,
    date: '2026-10-05',
    s_h: 10,
    s_m: 0,
    e_h: 11,
    e_m: 0,
    type: 5,
    subject: 'OT',
    professor: '',
    status: 'approved',
    requester: null,
    pushed_at: null,
    ...o,
  })
  it('창 밖이고 노드에 안 간 것(pushed_at null)만 예정 — 실패로 그리지 않는다', () => {
    expect(resvDot(r({}), undefined, '2026-09-25')).toBe('scheduled')
    expect(resvDot(r({ date: '2026-09-30' }), undefined, '2026-09-25')).toBeUndefined()
    expect(resvDot(r({ pushed_at: new Date() }), undefined, '2026-09-25')).toBeUndefined()
    expect(resvDot(r({ date: '2026-09-20' }), undefined, '2026-09-25')).toBeUndefined()
  })
  it('추적 중이면 그 상태가 먼저', () => {
    expect(resvDot(r({}), 'queued', '2026-09-25')).toBe('queued')
  })
})
```

`web/src/admin/__tests__/resv.spec.ts`
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import PendingBlock from '@/admin/views/rooms/PendingBlock.vue'
import ResvBlock from '@/admin/views/rooms/ResvBlock.vue'
import { adminApi } from '@/api/admin'
import { roomsApi } from '@/api/rooms'
import { ApiError, MESSAGES } from '@/api/client'
import type { ResvAdminOut, ResvWithRoom, RoomOut } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/admin', () => ({
  adminApi: { approveResv: vi.fn(), rejectResv: vi.fn(), cancelResv: vi.fn() },
}))
vi.mock('@/api/rooms', () => ({ roomsApi: { deleteResv: vi.fn(), saveResv: vi.fn() } }))
const admin = vi.mocked(adminApi)
const rooms = vi.mocked(roomsApi)

const requester = { email: 's1@wsu.ac.kr', name: '김민준', student_no: '20231234' }
const P = (id: number, subject: string, requestedAt: string, date = '2026-09-27'): ResvAdminOut => ({
  id,
  date,
  s_h: 10,
  s_m: 0,
  e_h: 12,
  e_m: 0,
  type: 6,
  subject,
  professor: '',
  status: 'requested',
  requested_at: new Date(requestedAt),
  decided_at: null,
  reject_reason: null,
  checked_in_at: null,
  cancelled_at: null,
  room_id: 11,
  building: '공학관',
  room: 401,
  requester,
  pushed_at: null,
})
const V = (o: Partial<ResvWithRoom>): ResvWithRoom => ({
  id: 7,
  room_id: 11,
  date: '2026-09-27',
  s_h: 16,
  s_m: 0,
  e_h: 17,
  e_m: 0,
  type: 5,
  subject: '신입생 OT',
  professor: '학생처',
  status: 'approved',
  requester: null,
  pushed_at: new Date(),
  ...o,
})
const roomList: RoomOut[] = [{ id: 11, building_id: 1, room: 401, units: 1, reservable: true }]

type Root = VueWrapper | DOMWrapper<Element>
const btn = (root: Root, text: string) => root.findAll('button').find((b) => b.text() === text)!
let w: VueWrapper
const dialog = (title: string) =>
  w.findAll('[role=dialog]').find((d) => d.get('h2').text() === title)

beforeEach(() => {
  // KST 2026-09-25(금) 12:00
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-09-25T03:00:00Z'))
  Object.values(admin).forEach((f) => f.mockReset())
  Object.values(rooms).forEach((f) => f.mockReset())
  for (const t of [...toasts.value]) dismissToast(t.id)
})
afterEach(() => vi.useRealTimers())

describe('신청 대기', () => {
  it('0건이면 블록 자체를 감춘다', () => {
    w = mount(PendingBlock, { props: { pending: [] } })
    expect(w.find('section').exists()).toBe(false)
  })

  it('오래된 신청 먼저, 신청자는 이름만 — 학번·메일은 툴팁', () => {
    w = mount(PendingBlock, {
      props: {
        pending: [
          P(2, '나중 신청', '2026-09-24T05:00:00Z'),
          P(1, '먼저 신청', '2026-09-24T01:00:00Z'),
        ],
      },
    })
    const rows = w.findAll('tbody tr')
    expect(rows[0].text()).toContain('먼저 신청')
    expect(rows[0].text()).toContain('공학관 401')
    expect(rows[0].get('[title]').attributes('title')).toBe('20231234 · s1@wsu.ac.kr')
    expect(w.text()).toContain('2건')
  })

  it('승인 — 문장 Toast 와 목록 새로 고침', async () => {
    admin.approveResv.mockResolvedValue(P(1, 'x', '2026-09-24T01:00:00Z'))
    w = mount(PendingBlock, { props: { pending: [P(1, '스터디', '2026-09-24T01:00:00Z')] } })
    await btn(w, '승인').trigger('click')
    await flushPromises()
    expect(admin.approveResv).toHaveBeenCalledWith(1)
    expect(toasts.value.at(-1)?.message).toBe('승인했습니다. 문 앞 화면에 나갑니다.')
    expect(w.emitted('changed')).toHaveLength(1)
  })

  it('409 — 다른 관리자가 먼저 처리: 문장·재조회, 버튼이 잠긴 채 남지 않는다', async () => {
    admin.approveResv.mockRejectedValue(
      new ApiError(409, MESSAGES[409], [], { detail: 'approved 상태에서는 불가' }),
    )
    w = mount(PendingBlock, {
      props: {
        pending: [P(1, '스터디', '2026-09-24T01:00:00Z'), P(2, '회의', '2026-09-24T02:00:00Z')],
      },
    })
    await btn(w.findAll('tbody tr')[0], '승인').trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)).toMatchObject({ tone: 'danger', message: '이미 처리된 신청입니다.' })
    expect(w.emitted('changed')).toHaveLength(1)
    expect(w.findAll('button').every((b) => !(b.element as HTMLButtonElement).disabled)).toBe(true)
  })

  it('승인 시 겹침·용량 409 는 그 이유를 말한다', async () => {
    admin.approveResv.mockRejectedValue(
      new ApiError(409, MESSAGES[409], [], {
        detail: '이 강의실은 이번 주 예약이 가득 찼습니다(노드 용량 24)',
      }),
    )
    w = mount(PendingBlock, { props: { pending: [P(1, '스터디', '2026-09-24T01:00:00Z')] } })
    await btn(w, '승인').trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe(
      '이 강의실은 7일 안 예약이 가득 찼습니다(24건). 지난 예약을 정리하세요.',
    )
  })

  it('거절 — 사유가 없으면 잠기고, 사유를 보내면 닫힌다', async () => {
    admin.rejectResv.mockResolvedValue(P(1, 'x', '2026-09-24T01:00:00Z'))
    w = mount(PendingBlock, {
      props: { pending: [P(1, '스터디', '2026-09-24T01:00:00Z')] },
      global: { stubs: { teleport: true } },
    })
    await btn(w.get('tbody'), '거절').trigger('click')
    const d = dialog('예약 신청 거절')!
    expect((btn(d, '거절').element as HTMLButtonElement).disabled).toBe(true)
    await d.get('textarea').setValue('시험 기간입니다')
    await btn(d, '거절').trigger('click')
    await flushPromises()
    expect(admin.rejectResv).toHaveBeenCalledWith(1, '시험 기간입니다')
    expect(dialog('예약 신청 거절')).toBeUndefined()
    expect(toasts.value.at(-1)?.message).toBe('거절했습니다. 사유가 학생에게 보입니다.')
  })
})

describe('예약 블록', () => {
  async function mountBlock(resv: ResvWithRoom[], states = new Map()) {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/:p(.*)*', component: { render: () => null } }],
    })
    w = mount(ResvBlock, {
      props: { rooms: roomList, label: () => '401', resv, states, loading: false },
      global: { plugins: [router], stubs: { teleport: true } },
    })
    await flushPromises()
  }

  it('approved 만 — 신청자·학번은 학생 신청만, 관리자가 넣은 것은 —', async () => {
    await mountBlock([
      V({ id: 1 }),
      V({ id: 2, subject: '스터디', requester, professor: '' }),
      V({ id: 3, subject: '대기중', status: 'requested', requester }),
      V({ id: 4, subject: '거절됨', status: 'rejected', requester }),
    ])
    const rows = w.findAll('tbody tr')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('신입생 OT')
    expect(rows[0].findAll('td')[6].text()).toBe('—')
    expect(rows[1].findAll('td')[6].text()).toBe('김민준')
    expect(rows[1].findAll('td')[7].text()).toBe('20231234')
  })

  it('창 밖·노드에 안 간 예약은 예정 배지 (툴팁) — 추적 중이면 그 점', async () => {
    await mountBlock(
      [V({ id: 1, date: '2026-10-05', pushed_at: null }), V({ id: 2, subject: '방금 저장' })],
      new Map([['r2', 'queued']]),
    )
    // 날짜순 — 9/27(방금 저장) 이 10/5 보다 먼저
    const rows = w.findAll('tbody tr')
    expect(rows[0].get('.dot').attributes('title')).toBe('대기')
    expect(rows[1].get('.badge').text()).toBe('예정')
    expect(rows[1].get('.badge').attributes('title')).toBe('7일 이내로 들어오면 자동 전송됩니다')
  })

  it('학생 예약은 지우지 않고 취소 — 관리자 예약은 삭제', async () => {
    admin.cancelResv.mockResolvedValue(P(2, 'x', '2026-09-24T01:00:00Z'))
    rooms.deleteResv.mockResolvedValue({ outbox_ids: [], id: null })
    await mountBlock([V({ id: 1 }), V({ id: 2, subject: '스터디', requester })])
    const rows = w.findAll('tbody tr')
    expect(rows[1].findAll('button').map((b) => b.text())).toEqual(['취소'])
    await btn(rows[1], '취소').trigger('click')
    const c = dialog('예약 취소')!
    expect(c.text()).toContain('김민준 학생 화면에 취소됨으로 보입니다.')
    await btn(c, '예약 취소').trigger('click')
    await flushPromises()
    expect(admin.cancelResv).toHaveBeenCalledWith(2)
    await btn(w.findAll('tbody tr')[0], '삭제').trigger('click')
    await btn(dialog('예약 삭제')!, '삭제').trigger('click')
    await flushPromises()
    expect(rooms.deleteResv).toHaveBeenCalledWith(11, 1)
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin/__tests__/roomsView.spec.ts src/admin/__tests__/resv.spec.ts`
Expected: FAIL — `"resvDot" is not exported` / `Failed to resolve import "@/admin/views/rooms/PendingBlock.vue"`

- [ ] **Step 3: 구현**

`web/src/admin/roomsView.ts` — import 를 바꾸고 끝에 추가
```ts
import type { BuildingOut, ResvWithRoom, RoomOut } from '@/api/types'
import type { DotState } from '@/components/domain/OutboxDot.vue'
import { buildTree } from '@/components/domain/roomTree'
import { resvWindow } from '@/components/domain/rules'
```
```ts
/** 예약 행의 점 — 추적 중이면 그 상태, 아니면 창 밖이고 노드에 안 간 것만 '예정'. 빈 outbox_ids 는 실패가 아니다 */
export function resvDot(
  r: ResvWithRoom,
  tracked: DotState | undefined,
  today: string,
): DotState | undefined {
  if (tracked) return tracked
  return r.pushed_at === null && resvWindow(r.date, today) === 'later' ? 'scheduled' : undefined
}
```

`web/src/admin/views/rooms/PendingBlock.vue`
```vue
<script setup lang="ts">
import { computed, ref } from 'vue'
import Button from '@/components/ui/Button.vue'
import Modal from '@/components/ui/Modal.vue'
import Table from '@/components/ui/Table.vue'
import Textarea from '@/components/ui/Textarea.vue'
import { showToast } from '@/components/ui/toast'
import { DAYS, LATER_HINT, conflictMessage, resvWindow } from '@/components/domain/rules'
import { ApiError } from '@/api/client'
import { adminApi } from '@/api/admin'
import type { ResvAdminOut } from '@/api/types'
import { dayOfDate, formatKst, hm, kstDateStr, md, relativeKo } from '@/lib/time'

const props = defineProps<{ pending?: ResvAdminOut[] }>()
const emit = defineEmits<{ changed: [] }>()

// 오래된 신청 먼저 — 먼저 온 것을 먼저 본다 (서버는 날짜순)
const rows = computed(() =>
  [...(props.pending ?? [])].sort(
    (a, b) => (a.requested_at?.getTime() ?? 0) - (b.requested_at?.getTime() ?? 0),
  ),
)
const COLUMNS = [
  { key: 'who', label: '신청자', width: '96px' },
  { key: 'room', label: '호수', width: '120px' },
  { key: 'date', label: '날짜', width: '96px' },
  { key: 'time', label: '시간', width: '112px' },
  { key: 'subject', label: '용도' },
  { key: 'requested_at', label: '신청 시각', width: '96px' },
  { key: 'actions', label: '작업', width: '136px', align: 'right' as const },
]
const asP = (row: Record<string, unknown>) => row as unknown as ResvAdminOut

const busy = ref<number | null>(null)
/** 승인·거절 공통. 409·404 면 true(대상이 이미 바뀌었다 — 모달을 닫는다) */
async function act(r: ResvAdminOut, call: () => Promise<unknown>, ok: string): Promise<boolean> {
  if (busy.value !== null) return false
  busy.value = r.id
  try {
    await call()
    showToast({ message: ok })
    return true
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    // 두 관리자가 동시에 · 그사이 직접 예약이 겹침 · 이미 시작 · 용량 24 — 이유를 말하고 새로 부른다
    if (e.status === 409) showToast({ tone: 'danger', message: conflictMessage(e) })
    else if (e.status === 404) showToast({ tone: 'danger', message: '이미 처리된 신청입니다.' })
    else if (e.status !== 401 && e.status !== 403) showToast({ tone: 'danger', message: e.message })
    return e.status === 409 || e.status === 404
  } finally {
    busy.value = null
    emit('changed')
  }
}
function approve(r: ResvAdminOut) {
  const later = resvWindow(r.date, kstDateStr(new Date())) === 'later'
  void act(
    r,
    () => adminApi.approveResv(r.id),
    later ? `승인했습니다. ${LATER_HINT}.` : '승인했습니다. 문 앞 화면에 나갑니다.',
  )
}

// 거절 — 사유가 필수이고 학생에게 그대로 보인다
const rejecting = ref<ResvAdminOut | null>(null)
const reason = ref('')
function openReject(r: ResvAdminOut) {
  reason.value = ''
  rejecting.value = r
}
async function submitReject() {
  const r = rejecting.value
  const text = reason.value.trim()
  if (!r || !text) return
  if (await act(r, () => adminApi.rejectResv(r.id, text), '거절했습니다. 사유가 학생에게 보입니다.'))
    rejecting.value = null
}
</script>

<template>
  <!-- 0건이면 블록을 감춘다 — 평소 비어 있는 블록이 자리를 차지하면 다른 표를 밀어낸다 -->
  <section v-if="rows.length" class="blk" aria-labelledby="blk-pending">
    <header class="blk__head">
      <h2 id="blk-pending" class="blk__title">신청 대기</h2>
      <span class="blk__count num">{{ rows.length }}건</span>
    </header>
    <Table :columns="COLUMNS" :rows="rows as unknown as Record<string, unknown>[]">
      <template #cell-who="{ row }">
        <!-- 이름만 — 학번·메일은 툴팁 (목록을 넓히지 않으면서 본인 확인) -->
        <span
          :title="`${asP(row).requester?.student_no ?? '학번 없음'} · ${asP(row).requester?.email ?? ''}`"
          >{{ asP(row).requester?.name ?? '—' }}</span
        >
      </template>
      <template #cell-room="{ row }">{{ asP(row).building }} {{ asP(row).room }}</template>
      <template #cell-date="{ row }"
        ><span class="num"
          >{{ md(asP(row).date) }} ({{ DAYS[dayOfDate(asP(row).date) - 1] }})</span
        ></template
      >
      <template #cell-time="{ row }"
        ><span class="num"
          >{{ hm(asP(row).s_h, asP(row).s_m) }}–{{ hm(asP(row).e_h, asP(row).e_m) }}</span
        ></template
      >
      <template #cell-requested_at="{ row }">
        <span v-if="asP(row).requested_at" :title="formatKst(asP(row).requested_at!)">{{
          relativeKo(asP(row).requested_at!)
        }}</span>
        <span v-else>—</span>
      </template>
      <template #cell-actions="{ row }">
        <div class="blk__actions">
          <Button
            size="sm"
            :loading="busy === asP(row).id"
            :disabled="busy !== null && busy !== asP(row).id"
            @click="approve(asP(row))"
            >승인</Button
          >
          <Button variant="ghost" size="sm" :disabled="busy !== null" @click="openReject(asP(row))"
            >거절</Button
          >
        </div>
      </template>
    </Table>
    <Modal
      :open="!!rejecting"
      title="예약 신청 거절"
      size="sm"
      :close-on-backdrop="!reason"
      @close="rejecting = null"
    >
      <p class="blk__modal-text">
        {{ rejecting?.requester?.name }} 의 {{ rejecting?.building }} {{ rejecting?.room }}호
        {{ rejecting?.date }} 신청을 거절합니다. 사유는 학생에게 그대로 보입니다.
      </p>
      <Textarea
        v-model="reason"
        label="거절 사유"
        placeholder="같은 시간에 학과 행사가 있습니다"
        maxlength="200"
        rows="3"
        required
      />
      <template #footer>
        <Button variant="secondary" @click="rejecting = null">취소</Button>
        <Button
          variant="danger"
          :loading="busy === rejecting?.id"
          :disabled="!reason.trim()"
          @click="submitReject"
          >거절</Button
        >
      </template>
    </Modal>
  </section>
</template>

<style scoped>
.blk {
  overflow: hidden;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.blk__head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
}
.blk__title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.blk__count {
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.blk__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-1);
}
.blk__modal-text {
  margin: 0 0 var(--space-4);
}
</style>
```

`web/src/admin/views/rooms/ResvBlock.vue`
```vue
<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Table from '@/components/ui/Table.vue'
import { showToast } from '@/components/ui/toast'
import ResvForm from '@/components/domain/ResvForm.vue'
import TypeBadge from '@/components/domain/TypeBadge.vue'
import type { DotState } from '@/components/domain/OutboxDot.vue'
import { DAYS, resvKey, type SavedRow } from '@/components/domain/rules'
import { ApiError } from '@/api/client'
import { adminApi } from '@/api/admin'
import { roomsApi } from '@/api/rooms'
import type { ResvWithRoom, RoomOut } from '@/api/types'
import { dayOfDate, hm, kstDateStr } from '@/lib/time'
import ConfirmModal from '../../ConfirmModal.vue'
import { resvDot } from '../../roomsView'
import RowDot from './RowDot.vue'

const props = defineProps<{
  rooms: RoomOut[]
  label: (roomId: number) => string
  resv: ResvWithRoom[]
  states: Map<string, DotState>
  loading: boolean
}>()
const emit = defineEmits<{
  saved: [row: SavedRow]
  changed: []
  resync: [roomId: number, key: string]
}>()

const today = kstDateStr(new Date())
// 예약 블록은 approved 만 — 신청은 위의 신청 대기, 거절·취소·만료는 그리지 않는다 (admin-rooms.md)
const rows = computed(() =>
  props.resv
    .filter((r) => r.status === 'approved')
    .sort(
      (a, b) =>
        a.date.localeCompare(b.date) || a.s_h - b.s_h || a.s_m - b.s_m || a.room_id - b.room_id,
    )
    .map((r) => ({ ...r, key: resvKey(r.id) })),
)
const COLUMNS = [
  { key: 'room', label: '호수', width: '72px' },
  { key: 'date', label: '날짜', width: '104px' },
  { key: 'day', label: '요일', width: '56px' },
  { key: 'start', label: '시작', width: '64px' },
  { key: 'end', label: '종료', width: '64px' },
  { key: 'subject', label: '사용 목적' },
  { key: 'who', label: '신청자', width: '96px' },
  { key: 'no', label: '학번', width: '88px' },
  { key: 'type', label: '유형', width: '80px' },
  { key: 'actions', label: '작업', width: '104px', align: 'right' as const },
]
const asV = (row: Record<string, unknown>) => row as unknown as ResvWithRoom & { key: string }
const roomLabel = (r: RoomOut) => `${props.label(r.id)}호`

const formOpen = ref(false)
const editing = ref<ResvWithRoom | null>(null)
function openForm(r: ResvWithRoom | null) {
  editing.value = r
  formOpen.value = true
}
function onSaved(r: SavedRow) {
  emit('saved', r)
  emit('changed')
}

// 학생 예약은 지우지 않고 취소한다 — 학생 화면에 '취소됨'으로 남는다. 관리자 예약은 삭제 (설계 판정)
const removing = ref<ResvWithRoom | null>(null)
const busy = ref(false)
const removeLines = computed(() => {
  const r = removing.value
  if (!r) return []
  const what = `${props.label(r.room_id)}호 ${r.date} ${hm(r.s_h, r.s_m)}–${hm(r.e_h, r.e_m)} ${r.subject}`
  return r.requester
    ? [what, `${r.requester.name} 학생 화면에 취소됨으로 보입니다.`]
    : [what]
})
async function remove() {
  const r = removing.value
  if (!r || busy.value) return
  busy.value = true
  try {
    if (r.requester) await adminApi.cancelResv(r.id)
    else await roomsApi.deleteResv(r.room_id, r.id)
    showToast({ message: r.requester ? '예약을 취소했습니다.' : '지웠습니다.' })
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 409 || e.status === 404)
      showToast({ tone: 'danger', message: '이미 바뀐 예약입니다. 목록을 새로 불러옵니다.' })
    else if (e.status !== 401 && e.status !== 403) showToast({ tone: 'danger', message: e.message })
  } finally {
    busy.value = false
    removing.value = null
    emit('changed')
  }
}
</script>

<template>
  <section class="blk" aria-labelledby="blk-resv">
    <header class="blk__head">
      <h2 id="blk-resv" class="blk__title">예약</h2>
      <Button class="blk__add" :disabled="!rooms.length" @click="openForm(null)">+ 예약 추가</Button>
    </header>
    <Table
      :columns="COLUMNS"
      :rows="rows as unknown as Record<string, unknown>[]"
      row-key="key"
      :loading="loading"
    >
      <template #empty>
        <EmptyState v-if="!rooms.length" message="위에서 강의실을 고르세요" />
        <EmptyState
          v-else
          message="등록된 항목이 없습니다"
          :actions="[{ label: '예약 추가', variant: 'primary', onClick: () => openForm(null) }]"
        />
      </template>
      <template #cell-room="{ row }">
        <RouterLink class="blk__room num" :to="`/rooms/${asV(row).room_id}/week`">{{
          label(asV(row).room_id)
        }}</RouterLink>
      </template>
      <template #cell-date="{ row }"
        ><span class="num">{{ asV(row).date }}</span></template
      >
      <!-- 요일은 날짜에서 계산한 읽기 전용 값 -->
      <template #cell-day="{ row }">{{ DAYS[dayOfDate(asV(row).date) - 1] }}</template>
      <template #cell-start="{ row }"
        ><span class="num">{{ hm(asV(row).s_h, asV(row).s_m) }}</span></template
      >
      <template #cell-end="{ row }"
        ><span class="num">{{ hm(asV(row).e_h, asV(row).e_m) }}</span></template
      >
      <!-- 신청자는 requested_by 에서 서버가 풀어 준 이름 — professor 를 쓰지 않는다 -->
      <template #cell-who="{ row }">{{ asV(row).requester?.name ?? '—' }}</template>
      <template #cell-no="{ row }"
        ><span class="num">{{ asV(row).requester?.student_no ?? '—' }}</span></template
      >
      <template #cell-type="{ row }"><TypeBadge :type="asV(row).type" /></template>
      <template #cell-actions="{ row }">
        <div class="blk__actions">
          <RowDot
            :state="resvDot(asV(row), states.get(asV(row).key), today)"
            @resync="emit('resync', asV(row).room_id, asV(row).key)"
          />
          <Button
            v-if="asV(row).requester"
            variant="ghost"
            size="sm"
            @click="removing = asV(row)"
            >취소</Button
          >
          <template v-else>
            <Button variant="ghost" size="sm" @click="openForm(asV(row))">수정</Button>
            <Button variant="ghost" size="sm" @click="removing = asV(row)">삭제</Button>
          </template>
        </div>
      </template>
    </Table>
    <ResvForm
      :open="formOpen"
      :mode="editing ? 'edit' : 'create'"
      :rooms="rooms"
      :room-label="roomLabel"
      :value="editing"
      :preset="rooms[0] ? { room_id: rooms[0].id } : null"
      :existing="resv"
      @close="formOpen = false"
      @saved="onSaved"
      @stale="emit('changed')"
    />
    <ConfirmModal
      :open="!!removing"
      :title="removing?.requester ? '예약 취소' : '예약 삭제'"
      :lines="removeLines"
      :confirm-label="removing?.requester ? '예약 취소' : '삭제'"
      :loading="busy"
      @confirm="remove"
      @close="removing = null"
    />
  </section>
</template>

<style scoped>
.blk {
  overflow: hidden;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.blk__head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
}
.blk__title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.blk__add {
  margin-left: auto;
}
.blk__room {
  color: var(--text-1);
  font-weight: var(--font-weight-medium);
}
.blk__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-1);
}
</style>
```

`web/src/admin/views/RoomsView.vue` 를 통째로 바꾼다 (Task 14 판 + 신청 대기·예약)
```vue
<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import EmptyState from '@/components/ui/EmptyState.vue'
import { showToast } from '@/components/ui/toast'
import RoomTree from '@/components/domain/RoomTree.vue'
import type { SavedRow } from '@/components/domain/rules'
import { adminApi } from '@/api/admin'
import { roomsApi } from '@/api/rooms'
import type { RoomOut } from '@/api/types'
import { useResource } from '@/lib/useResource'
import { useOutboxTracker } from '../outboxTrack'
import { defaultPick, roomLabeler } from '../roomsView'
import { picked } from '../selection'
import PendingBlock from './rooms/PendingBlock.vue'
import ResvBlock from './rooms/ResvBlock.vue'
import SlotBlock from './rooms/SlotBlock.vue'

const router = useRouter()
const master = useResource(async () => {
  const [buildings, rooms] = await Promise.all([roomsApi.buildings(), roomsApi.rooms()])
  return { buildings, rooms }
})
const buildings = computed(() => master.data.value?.buildings ?? [])
const allRooms = computed(() => master.data.value?.rooms ?? [])
const hasNoRooms = computed(() => !!master.data.value && !allRooms.value.length)

// 트리 선택은 모듈 상태 — 다른 화면을 다녀와도 남는다. 지워진 방은 빼고, 비었으면 첫 건물의 첫 층
watch(master.data, (d) => {
  if (!d) return
  const alive = picked.value.filter((id) => d.rooms.some((r) => r.id === id))
  picked.value = alive.length ? alive : defaultPick(d.buildings, d.rooms)
})
const selection = computed({
  get: () => picked.value,
  set: (ids: number[]) => (picked.value = ids),
})
const order = (r: RoomOut) => buildings.value.findIndex((b) => b.id === r.building_id)
const pickedRooms = computed(() =>
  allRooms.value
    .filter((r) => picked.value.includes(r.id))
    .sort((a, b) => order(a) - order(b) || a.room - b.room),
)
const label = computed(() => roomLabeler(buildings.value, pickedRooms.value))

// 건물 단위 조회 3개 (S4b §2.6) — 같은 건물 안에서 고른 방을 바꿔도 다시 부르지 않고 걸러서 보인다
const bids = computed(() =>
  [...new Set(pickedRooms.value.map((r) => r.building_id))].sort((a, b) => a - b),
)
const scope = useResource(
  async () => {
    const per = await Promise.all(
      bids.value.map((b) =>
        Promise.all([roomsApi.buildingSlots(b), roomsApi.buildingResv(b), roomsApi.buildingExams(b)]),
      ),
    )
    return {
      slots: per.flatMap((p) => p[0]),
      resv: per.flatMap((p) => p[1]),
      exams: per.flatMap((p) => p[2]),
    }
  },
  { deps: () => bids.value.join(',') },
)
// 신청 대기는 학교 전체 — 처리해야 할 일이라 트리 밖 신청도 숨기지 않는다 (설계 판정)
const pending = useResource(() => adminApi.pendingResv())
const inPick = <T extends { room_id: number }>(xs: T[] | undefined) =>
  (xs ?? []).filter((x) => picked.value.includes(x.room_id))
const slots = computed(() => inPick(scope.data.value?.slots))
const resv = computed(() => inPick(scope.data.value?.resv))
const scopeLoading = computed(() => scope.loading.value && !scope.data.value)
function reloadAll() {
  void scope.reload()
  void pending.reload()
}

// 오류 — Toast + 재시도. 표는 이전 내용을 지우지 않는다 (useResource 가 data 를 지킨다)
for (const r of [master, scope, pending])
  watch(r.error, (e) => {
    if (e && e.status !== 401 && e.status !== 403)
      showToast({
        tone: 'danger',
        message: e.message,
        action: { label: '재시도', onClick: () => void r.reload() },
      })
  })

// 저장 뒤 OutboxDot — 행 key 로 30초 (새로고침하면 끊긴다)
const tracker = useOutboxTracker()
const buildingOf = (roomId: number) => allRooms.value.find((r) => r.id === roomId)?.building_id
function onSaved(s: SavedRow) {
  const b = buildingOf(s.roomId)
  if (b !== undefined) tracker.track(s.key, b, s.outboxIds)
}
function resync(roomId: number, key: string) {
  const b = buildingOf(roomId)
  if (b !== undefined) void tracker.resync(key, roomId, b)
}
</script>

<template>
  <main class="rooms">
    <!-- 상단 바는 스크롤해도 붙어 있다 — 트리에서 고른 것이 아래 표들의 범위다 -->
    <header class="rooms__bar">
      <RoomTree v-model:selected="selection" :buildings="buildings" :rooms="allRooms" />
      <span class="rooms__hint">강의실 선택</span>
    </header>
    <EmptyState
      v-if="hasNoRooms"
      message="강의실이 없습니다. 건물 · 강의실 화면에서 먼저 만드세요."
      :actions="[{ label: '건물 · 강의실로', variant: 'primary', onClick: () => router.push('/master') }]"
    />
    <div v-else class="rooms__blocks">
      <SlotBlock
        :rooms="pickedRooms"
        :label="label"
        :slots="slots"
        :states="tracker.states"
        :loading="scopeLoading"
        @saved="onSaved"
        @changed="scope.reload"
        @resync="resync"
      />
      <!-- 신청 대기는 예약 블록 위에 선다 — 승인해야 approved 가 되어 노드로 나간다 -->
      <PendingBlock :pending="pending.data.value" @changed="reloadAll" />
      <ResvBlock
        :rooms="pickedRooms"
        :label="label"
        :resv="resv"
        :states="tracker.states"
        :loading="scopeLoading"
        @saved="onSaved"
        @changed="reloadAll"
        @resync="resync"
      />
    </div>
  </main>
</template>

<style scoped>
.rooms {
  padding: 0 var(--space-5) var(--space-5);
}
.rooms__bar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) 0;
  background: var(--bg);
}
.rooms__hint {
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
/* 탭이 아니라 세로 스택 — 셋이 같은 강의실의 다른 시간 축이라 함께 보여야 한다 */
.rooms__blocks {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}
</style>
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`
Expected: PASS (Task 14 의 `rooms.spec.ts` 는 `adminApi.pendingResv` 를 이미 모의한다)

- [ ] **Step 5: E2E — 예약 · 신청 대기**

`web/e2e/admin-ops.spec.ts`
- helpers import 에 `apiLogin`·`createStudent`·`kstDate` 를 더한다.
- 파일 끝에 추가:
```ts
const resvBlock = () => page.getByRole('region', { name: '예약', exact: true })

test('예약 — 7일 안은 대기 점, 7일 밖은 예정 배지 (폼에서도 저장 전에 같은 문구)', async () => {
  const resv = resvBlock()
  await resv.getByRole('button', { name: '+ 예약 추가' }).click()
  const d = page.getByRole('dialog', { name: '예약 추가' })
  await d.getByLabel('강의실').selectOption({ label: '101호' })
  await d.getByLabel('날짜').fill(kstDate(1))
  await d.getByLabel('시작').fill('16:00')
  await d.getByLabel('종료').fill('17:00')
  await d.getByLabel('사용 목적').fill('신입생 OT')
  await d.getByLabel('주관 부서').fill('학생처')
  await d.getByRole('button', { name: '저장' }).click()
  await expect(d).toHaveCount(0)
  const near = resv.getByRole('row').filter({ hasText: '신입생 OT' })
  await expect(near.getByRole('img', { name: '대기' })).toBeVisible()
  await expect(near).toContainText('—')
  await resv.getByRole('button', { name: '+ 예약 추가' }).click()
  await d.getByLabel('날짜').fill(kstDate(10))
  await expect(d.getByText('7일 이내로 들어오면 자동 전송됩니다')).toBeVisible()
  await d.getByLabel('사용 목적').fill('동문회')
  await d.getByRole('button', { name: '저장' }).click()
  await expect(d).toHaveCount(0)
  const far = resv.getByRole('row').filter({ hasText: '동문회' })
  await expect(far.getByText('예정')).toHaveAttribute('title', '7일 이내로 들어오면 자동 전송됩니다')
})

test('신청 대기 — 오래된 순, 승인하면 예약 표로, 다른 관리자가 먼저 처리하면 409 문장, 거절은 사유 필수', async () => {
  const no = `P${Date.now().toString(36).toUpperCase()}`
  const s = await createStudent(api, { approve: true, name: '김신청', studentNo: no })
  const st = { authorization: `Bearer ${await apiLogin(api, s.email)}` }
  const ask = async (s_h: number, subject: string) => {
    const r = await api.post(`/api/student/rooms/${ops.roomIds[101]}/reservations`, {
      headers: st,
      data: { date: kstDate(2), s_h, s_m: 0, e_h: s_h + 1, e_m: 0, subject },
    })
    expect(r.status(), subject).toBe(201)
    return ((await r.json()) as { id: number }).id
  }
  await ask(9, '캡스톤 스터디')
  const second = await ask(10, '동아리 회의')
  await ask(11, '밴드 연습')
  // 신청 대기는 자동 새로고침이 없다 — 화면을 다시 연다
  await page.getByRole('link', { name: '건물 · 강의실' }).click()
  await page.getByRole('link', { name: '강의실 설정' }).click()
  const pend = page.getByRole('region', { name: '신청 대기' })
  await expect(pend).toContainText('3건')
  await expect(pend.locator('tbody tr').nth(0)).toContainText('캡스톤 스터디')
  await expect(pend.getByText('김신청').first()).toHaveAttribute('title', `${no} · ${s.email}`)
  await shot(page, 'admin-rooms-pending-1440')
  await pend.getByRole('row').filter({ hasText: '캡스톤 스터디' }).getByRole('button', { name: '승인' }).click()
  await expect(page.getByText('승인했습니다. 문 앞 화면에 나갑니다.')).toBeVisible()
  const approved = resvBlock().getByRole('row').filter({ hasText: '캡스톤 스터디' })
  await expect(approved).toContainText('김신청')
  await expect(approved).toContainText(no)
  // 다른 관리자가 먼저 승인
  const other = { authorization: `Bearer ${await apiLogin(api, cfg.ADMINS[1])}` }
  const r = await api.post(`/api/admin/reservations/${second}/approve`, { headers: other })
  expect(r.status()).toBe(200)
  await pend.getByRole('row').filter({ hasText: '동아리 회의' }).getByRole('button', { name: '승인' }).click()
  await expect(page.getByText('이미 처리된 신청입니다.')).toBeVisible()
  await expect(pend.getByRole('row').filter({ hasText: '동아리 회의' })).toHaveCount(0)
  // 거절 — 사유 필수, 0건이 되면 블록이 사라진다
  await pend.getByRole('row').filter({ hasText: '밴드 연습' }).getByRole('button', { name: '거절' }).click()
  const d = page.getByRole('dialog', { name: '예약 신청 거절' })
  await expect(d.getByRole('button', { name: '거절' })).toBeDisabled()
  await d.getByLabel('거절 사유').fill('시험 기간입니다')
  await d.getByRole('button', { name: '거절' }).click()
  await expect(page.getByText('거절했습니다. 사유가 학생에게 보입니다.')).toBeVisible()
  await expect(pend).toHaveCount(0)
})
```

Run: **E2E 명령** + ` e2e/admin-ops.spec.ts`
Expected: `11 passed`

- [ ] **Step 6: 스크린샷 대조**

`admin-rooms-pending-1440.png` 를 `admin-rooms.md` 와 대조:
- 순서: 시간표 → **신청 대기**(`3건`) → 예약. 블록 사이 space.5.
- 신청 대기 컬럼: 신청자(이름만) · 호수 `운영관 101` · 날짜 `M/D (요일)` · 시간 `09:00–10:00` · 용도 · 신청 시각(`방금`·`N분 전`) · 작업 `[승인]`(primary) `[거절]`(ghost). 오래된 순.
- 예약 컬럼: 호수 · 날짜 104 · 요일 56 · 시작 · 종료 · 사용 목적 · 신청자 96 · 학번 88 · 유형 80 · 작업 104. 관리자 예약은 신청자·학번 `—`. 8일 뒤 예약은 점 대신 `예정` 배지(테두리).
어긋나면 고치고 다시 찍는다.

- [ ] **Step 7: 커밋**

```bash
git add web/src/admin web/e2e
git commit -m "feat(web): 강의실 설정 B — 예약 블록(approved 만·신청자/학번·7일 밖 예정 배지·학생 예약은 취소), 신청 대기(오래된 순·승인·사유 필수 거절·409 이유와 재조회·0건이면 숨김) + E2E"
```

---

### Task 16: 강의실 설정 C — 시험기간 · CSV · 선택한 곳 동기화 + E2E

**Files:**
- Create: `web/src/admin/views/rooms/ExamBlock.vue`, `web/src/admin/views/rooms/CsvImport.vue`
- Modify: `web/src/admin/roomsView.ts`, `web/src/admin/views/rooms/SlotBlock.vue`, `web/src/admin/views/RoomsView.vue`(전체 교체), `web/e2e/admin-ops.spec.ts`
- Test: `web/src/admin/__tests__/roomsView.spec.ts`, `web/src/admin/__tests__/exams.spec.ts`, `web/src/admin/__tests__/csv.spec.ts`, `web/src/admin/__tests__/rooms.spec.ts`

**Interfaces:**
- Consumes: `ExamForm`(Task 8) · Table `expandable`(F1) · `roomsApi.{deleteExam, importSlots}`·`IMPORT_MAX_BYTES`(Task 1) · `loraApi.syncRoom`(F3).
- Produces (`roomsView.ts`): `interface ExamGroup { id: string; date_start: string; date_end: string; items: ExamWithRoom[] }` · `groupExams(exams, order: (roomId: number) => number): ExamGroup[]` · `roomsLabel(labels: string[]): string`(`'401, 402, 405 외 4곳'`).
- Produces (`ExamBlock.vue`): props `{ rooms; label; exams: ExamWithRoom[]; states; loading }`, emits `saved`·`changed`·`resync`. 루트 `<section aria-labelledby="blk-exams">`(h2 `시험기간`). 펼친 방 행 `li.blk__item`.
- Produces (`CsvImport.vue`): emits `applied: []`, `defineExpose({ pick })` — 숨은 `input[type=file]` 을 연다. Modal `CSV 가져오기 — {파일명}`·`CSV 오류 — 아무것도 적용되지 않았습니다`.
- Produces: SlotBlock emits `csv: []`(빈 상태의 `CSV 가져오기`). RoomsView 상단 바 오른쪽 `CSV 가져오기`·`선택한 곳 동기화`(secondary).

- [ ] **Step 1: 실패 테스트**

`web/src/admin/__tests__/roomsView.spec.ts` 끝에 추가 (import 에 `groupExams`·`roomsLabel` 과 `ExamWithRoom` 타입을 더한다)
```ts
describe('시험기간 묶기', () => {
  const X = (id: number, room_id: number, ds: string, de: string): ExamWithRoom => ({
    id,
    room_id,
    date_start: ds,
    date_end: de,
  })
  it('같은 시작일·종료일은 한 행 — 날짜순, 행 안은 트리 순서', () => {
    const order = (roomId: number) => [12, 11, 13].indexOf(roomId)
    const g = groupExams(
      [
        X(1, 11, '2026-10-19', '2026-10-23'),
        X(2, 12, '2026-10-19', '2026-10-23'),
        X(3, 13, '2026-10-12', '2026-10-16'),
      ],
      order,
    )
    expect(g.map((x) => x.id)).toEqual(['2026-10-12~2026-10-16', '2026-10-19~2026-10-23'])
    expect(g[1].items.map((x) => x.room_id)).toEqual([12, 11])
  })
  it('셋까지 나열, 넘으면 외 N곳', () => {
    expect(roomsLabel(['401', '402'])).toBe('401, 402')
    expect(roomsLabel(['401', '402', '405', '406', '407'])).toBe('401, 402, 405 외 2곳')
  })
})
```

`web/src/admin/__tests__/exams.spec.ts`
```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import ExamBlock from '@/admin/views/rooms/ExamBlock.vue'
import { roomsApi } from '@/api/rooms'
import type { ExamWithRoom, RoomOut } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/rooms', () => ({ roomsApi: { saveExam: vi.fn(), deleteExam: vi.fn() } }))
const api = vi.mocked(roomsApi)

const R = (id: number, room: number): RoomOut => ({
  id,
  building_id: 1,
  room,
  units: 1,
  reservable: false,
})
const rooms = [R(11, 401), R(12, 402), R(13, 405), R(14, 406)]
const X = (id: number, room_id: number): ExamWithRoom => ({
  id,
  room_id,
  date_start: '2026-10-19',
  date_end: '2026-10-23',
})
type Root = VueWrapper | DOMWrapper<Element>
const btn = (root: Root, text: string) =>
  root.findAll('button').find((b) => b.text().startsWith(text))!
let w: VueWrapper
const dialog = (title: string) =>
  w.findAll('[role=dialog]').find((d) => d.get('h2').text() === title)
async function mountBlock(exams: ExamWithRoom[]) {
  w = mount(ExamBlock, {
    props: {
      rooms,
      label: (id: number) => String(rooms.find((r) => r.id === id)!.room),
      exams,
      states: new Map(),
      loading: false,
    },
    global: { stubs: { teleport: true } },
  })
  await flushPromises()
}

beforeEach(() => {
  api.saveExam.mockReset()
  api.deleteExam.mockReset().mockResolvedValue({ outbox_ids: [3], id: null })
  for (const t of [...toasts.value]) dismissToast(t.id)
})

describe('시험기간 블록', () => {
  it('같은 기간은 한 행으로 접는다 — 호수 셋까지, 넘으면 외 N곳', async () => {
    await mountBlock([X(1, 11), X(2, 12), X(3, 13), X(4, 14)])
    const row = w.findAll('tbody tr')[0]
    expect(row.text()).toContain('401, 402, 405 외 1곳')
    expect(row.text()).toContain('4곳')
  })

  it('펼치면 방마다 수정·삭제 — 삭제는 확인 뒤 그 방의 그 id', async () => {
    await mountBlock([X(1, 11), X(2, 12)])
    await w.get('.tbl__toggle').trigger('click')
    const items = w.findAll('.blk__item')
    expect(items.map((i) => i.find('.num').text())).toEqual(['401호', '402호'])
    await btn(items[1], '삭제').trigger('click')
    const c = dialog('시험기간 삭제')!
    expect(c.text()).toContain('402호 시험기간 2026-10-19 ~ 2026-10-23')
    await btn(c, '삭제').trigger('click')
    await flushPromises()
    expect(api.deleteExam).toHaveBeenCalledWith(12, 2)
    expect(w.emitted('changed')).toHaveLength(1)
  })

  it('추가 버튼이 대상 수를 말하고, 폼은 고른 방 전부를 대상으로 연다', async () => {
    await mountBlock([])
    const add = btn(w, '+ 선택한 4곳에 기간 추가')
    await add.trigger('click')
    const d = dialog('시험기간 추가')!
    expect(d.text()).toContain('대상 4곳 · 401호, 402호, 405호, 406호')
  })
})
```

`web/src/admin/__tests__/csv.spec.ts`
```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import CsvImport from '@/admin/views/rooms/CsvImport.vue'
import { roomsApi } from '@/api/rooms'
import { ApiError, MESSAGES } from '@/api/client'
import type { ImportSummary } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/rooms', () => ({ IMPORT_MAX_BYTES: 1024 * 1024, roomsApi: { importSlots: vi.fn() } }))
const api = vi.mocked(roomsApi)

const summary = (o: Partial<ImportSummary> = {}): ImportSummary => ({
  rooms: 1,
  added: 1,
  updated: 0,
  deleted: 0,
  skipped: [{ row: 2, reason: '수동 슬롯 있음 (source=2)' }],
  outbox_ids: [],
  ...o,
})
let w: VueWrapper
const dialog = (title: string) =>
  w.findAll('[role=dialog]').find((d) => d.get('h2').text() === title)
const btn = (root: VueWrapper | DOMWrapper<Element>, text: string) =>
  root.findAll('button').find((b) => b.text() === text)!
/** jsdom 의 File 은 arrayBuffer 가 없을 수 있어 같은 모양의 객체로 넘긴다 (코드가 쓰는 것은 name·size·arrayBuffer) */
async function choose(size = 20) {
  const input = w.get('input[type=file]')
  const file = { name: 'slots.csv', size, arrayBuffer: async () => new ArrayBuffer(size) }
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
  await flushPromises()
}

beforeEach(() => {
  api.importSlots.mockReset()
  for (const t of [...toasts.value]) dismissToast(t.id)
  w = mount(CsvImport, { global: { stubs: { teleport: true } } })
})

describe('CSV 가져오기', () => {
  it('먼저 dry_run 요약 — 건너뛸 행(웹에서 고친 행)을 표로, 적용하면 실제로 보낸다', async () => {
    api.importSlots.mockResolvedValueOnce(summary()).mockResolvedValueOnce(summary({ outbox_ids: [3] }))
    await choose()
    expect(api.importSlots.mock.calls[0][1]).toBe(true)
    const d = dialog('CSV 가져오기 — slots.csv')!
    expect(d.text()).toContain('강의실 1곳 · 추가 1 · 수정 0 · 삭제 0')
    expect(d.text()).toContain('수동 슬롯 있음 (source=2)')
    await btn(d, '적용').trigger('click')
    await flushPromises()
    expect(api.importSlots.mock.calls[1][1]).toBe(false)
    expect(toasts.value.at(-1)?.message).toBe(
      '시간표를 가져왔습니다 — 강의실 1곳에 보냅니다. 웹에서 고친 1행은 건너뛰었습니다.',
    )
    expect(w.emitted('applied')).toHaveLength(1)
    expect(dialog('CSV 가져오기 — slots.csv')).toBeUndefined()
  })

  it('행 오류 400 — 아무것도 적용되지 않았다고 말하고 행 번호·사유를 표로 (0행은 —)', async () => {
    api.importSlots.mockRejectedValue(
      new ApiError(400, MESSAGES[400], [], {
        errors: [
          { row: 2, error: 'room: 999 없음 (우송대 K)' },
          { row: 0, error: '헤더에 없는 컬럼: professor' },
        ],
      }),
    )
    await choose()
    const d = dialog('CSV 오류 — 아무것도 적용되지 않았습니다')!
    const rows = d.findAll('tbody tr').map((r) => r.findAll('td').map((c) => c.text()))
    expect(rows).toEqual([
      ['2', 'room: 999 없음 (우송대 K)'],
      ['—', '헤더에 없는 컬럼: professor'],
    ])
  })

  it('UTF-8 이 아니면(400, errors 없음) 저장 형식을 말한다', async () => {
    api.importSlots.mockRejectedValue(
      new ApiError(400, MESSAGES[400], [], { detail: 'UTF-8 로 저장하세요 (엑셀: CSV UTF-8)' }),
    )
    await choose()
    expect(toasts.value.at(-1)).toMatchObject({
      tone: 'danger',
      message: 'CSV 를 UTF-8 로 저장해 주세요 (엑셀: CSV UTF-8).',
    })
  })

  it('1 MB 가 넘으면 보내지 않는다', async () => {
    await choose(1024 * 1024 + 1)
    expect(api.importSlots).not.toHaveBeenCalled()
    expect(toasts.value.at(-1)?.message).toBe('1 MB 를 넘는 파일은 가져올 수 없습니다.')
  })

  it('바뀌는 것이 없으면 적용 버튼이 잠긴다', async () => {
    api.importSlots.mockResolvedValue(summary({ added: 0, rooms: 0 }))
    await choose()
    const d = dialog('CSV 가져오기 — slots.csv')!
    expect(d.text()).toContain('바뀌는 것이 없습니다.')
    expect((btn(d, '적용').element as HTMLButtonElement).disabled).toBe(true)
  })
})
```

`web/src/admin/__tests__/rooms.spec.ts` 의 `describe('강의실 설정 — 트리와 시간표', …)` 안 끝에 추가
```ts
  it('선택한 곳 동기화 — 고른 방마다 보내고, 일부 실패는 그 방을 말한다', async () => {
    lora.syncRoom.mockImplementation(async (roomId: number) => {
      if (roomId === 12) throw new ApiError(500, MESSAGES[500])
      return { outbox_ids: [1], id: null }
    })
    await mountView()
    await btn(w, '선택한 곳 동기화').trigger('click')
    await flushPromises()
    expect(lora.syncRoom.mock.calls).toEqual([[11], [12]])
    expect(toasts.value.at(-1)).toMatchObject({ tone: 'danger', message: '2곳 중 1곳 보냄 · 402호 실패' })
  })
```
(같은 파일 import 에 `import { ApiError, MESSAGES } from '@/api/client'` 를 더한다.)

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin`
Expected: FAIL — `"groupExams" is not exported`, `Failed to resolve import "@/admin/views/rooms/ExamBlock.vue"`·`CsvImport.vue`, rooms.spec `Cannot call trigger on an empty DOMWrapper`(동기화 버튼 없음)

- [ ] **Step 3: 구현**

`web/src/admin/roomsView.ts` — import 의 타입 줄을 `import type { BuildingOut, ExamWithRoom, ResvWithRoom, RoomOut } from '@/api/types'` 로 바꾸고 끝에 추가
```ts
export interface ExamGroup {
  id: string
  date_start: string
  date_end: string
  items: ExamWithRoom[]
}
/** 같은 시작일·종료일은 한 행으로 접는다 — 펼치면 방마다 (admin-rooms.md 시험기간). 수정·삭제는 펼친 행에서 */
export function groupExams(exams: ExamWithRoom[], order: (roomId: number) => number): ExamGroup[] {
  const map = new Map<string, ExamGroup>()
  for (const x of exams) {
    const id = `${x.date_start}~${x.date_end}`
    const g = map.get(id) ?? { id, date_start: x.date_start, date_end: x.date_end, items: [] }
    g.items.push(x)
    map.set(id, g)
  }
  const groups = [...map.values()].sort(
    (a, b) => a.date_start.localeCompare(b.date_start) || a.date_end.localeCompare(b.date_end),
  )
  for (const g of groups) g.items.sort((a, b) => order(a.room_id) - order(b.room_id))
  return groups
}

/** '401, 402, 405 외 4곳' */
export const roomsLabel = (labels: string[]) =>
  labels.length <= 3 ? labels.join(', ') : `${labels.slice(0, 3).join(', ')} 외 ${labels.length - 3}곳`
```

`web/src/admin/views/rooms/ExamBlock.vue`
```vue
<script setup lang="ts">
import { computed, ref } from 'vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Table from '@/components/ui/Table.vue'
import { showToast } from '@/components/ui/toast'
import ExamForm from '@/components/domain/ExamForm.vue'
import type { DotState } from '@/components/domain/OutboxDot.vue'
import { examKey, type SavedRow } from '@/components/domain/rules'
import { ApiError } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { ExamWithRoom, RoomOut } from '@/api/types'
import ConfirmModal from '../../ConfirmModal.vue'
import { groupExams, roomsLabel, type ExamGroup } from '../../roomsView'
import RowDot from './RowDot.vue'

const props = defineProps<{
  rooms: RoomOut[]
  label: (roomId: number) => string
  exams: ExamWithRoom[]
  states: Map<string, DotState>
  loading: boolean
}>()
const emit = defineEmits<{
  saved: [row: SavedRow]
  changed: []
  resync: [roomId: number, key: string]
}>()

const order = (roomId: number) => props.rooms.findIndex((r) => r.id === roomId)
const groups = computed(() => groupExams(props.exams, order))
const COLUMNS = [
  { key: 'rooms', label: '호수' },
  { key: 'date_start', label: '시작일', width: '120px' },
  { key: 'date_end', label: '종료일', width: '120px' },
  { key: 'count', label: '강의실', width: '80px', align: 'right' as const },
]
const asG = (row: Record<string, unknown>) => row as unknown as ExamGroup
const roomLabel = (r: RoomOut) => `${props.label(r.id)}호`

// 추가 — 강의실을 고르는 것은 트리. 폼에는 날짜만, 대상은 고른 방 전부 (admin-rooms.md 시험기간)
const formOpen = ref(false)
const editing = ref<ExamWithRoom | null>(null)
const formRooms = computed(() =>
  editing.value ? props.rooms.filter((r) => r.id === editing.value!.room_id) : props.rooms,
)
function openForm(x: ExamWithRoom | null) {
  editing.value = x
  formOpen.value = true
}

const removing = ref<ExamWithRoom | null>(null)
const busy = ref(false)
async function remove() {
  const x = removing.value
  if (!x || busy.value) return
  busy.value = true
  try {
    await roomsApi.deleteExam(x.room_id, x.id)
    showToast({ message: '지웠습니다.' })
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status !== 401 && e.status !== 403) showToast({ tone: 'danger', message: e.message })
  } finally {
    busy.value = false
    removing.value = null
    emit('changed')
  }
}
</script>

<template>
  <section class="blk" aria-labelledby="blk-exams">
    <header class="blk__head">
      <h2 id="blk-exams" class="blk__title">시험기간</h2>
      <!-- 버튼이 대상 수를 말한다 — 트리에서 4층을 누르면 그 층 전체가 대상 -->
      <Button class="blk__add" :disabled="!rooms.length" @click="openForm(null)"
        >+ 선택한 {{ rooms.length }}곳에 기간 추가</Button
      >
    </header>
    <Table
      expandable
      :columns="COLUMNS"
      :rows="groups as unknown as Record<string, unknown>[]"
      :loading="loading"
    >
      <template #empty>
        <EmptyState v-if="!rooms.length" message="위에서 강의실을 고르세요" />
        <EmptyState
          v-else
          message="등록된 항목이 없습니다"
          :actions="[
            { label: '기간 추가', variant: 'primary', onClick: () => openForm(null) },
          ]"
        />
      </template>
      <template #cell-rooms="{ row }"
        ><span class="num">{{
          roomsLabel(asG(row).items.map((x) => label(x.room_id)))
        }}</span></template
      >
      <template #cell-date_start="{ row }"
        ><span class="num">{{ asG(row).date_start }}</span></template
      >
      <template #cell-date_end="{ row }"
        ><span class="num">{{ asG(row).date_end }}</span></template
      >
      <template #cell-count="{ row }"
        ><span class="num">{{ asG(row).items.length }}곳</span></template
      >
      <template #expanded="{ row }">
        <ul class="blk__items">
          <li v-for="x in asG(row).items" :key="x.id" class="blk__item">
            <span class="num">{{ label(x.room_id) }}호</span>
            <RowDot
              :state="states.get(examKey(x.id))"
              @resync="emit('resync', x.room_id, examKey(x.id))"
            />
            <Button variant="ghost" size="sm" @click="openForm(x)">수정</Button>
            <Button variant="ghost" size="sm" @click="removing = x">삭제</Button>
          </li>
        </ul>
      </template>
    </Table>
    <ExamForm
      :open="formOpen"
      :rooms="formRooms"
      :value="editing"
      :room-label="roomLabel"
      @close="formOpen = false"
      @saved="(r) => emit('saved', r)"
      @done="emit('changed')"
    />
    <ConfirmModal
      :open="!!removing"
      title="시험기간 삭제"
      :lines="
        removing
          ? [`${label(removing.room_id)}호 시험기간 ${removing.date_start} ~ ${removing.date_end}`]
          : []
      "
      :loading="busy"
      @confirm="remove"
      @close="removing = null"
    />
  </section>
</template>

<style scoped>
.blk {
  overflow: hidden;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.blk__head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
}
.blk__title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.blk__add {
  margin-left: auto;
}
.blk__items {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-5);
  margin: 0;
  padding: 0;
  list-style: none;
}
.blk__item {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}
</style>
```

`web/src/admin/views/rooms/CsvImport.vue`
```vue
<script setup lang="ts">
import { computed, ref, shallowRef } from 'vue'
import Button from '@/components/ui/Button.vue'
import Modal from '@/components/ui/Modal.vue'
import Table from '@/components/ui/Table.vue'
import { showToast } from '@/components/ui/toast'
import { ApiError } from '@/api/client'
import { IMPORT_MAX_BYTES, roomsApi } from '@/api/rooms'
import type { ImportErrors, ImportRowError, ImportSummary } from '@/api/types'

const emit = defineEmits<{ applied: [] }>()
const input = ref<HTMLInputElement>()
const name = ref('')
let bytes: ArrayBuffer | null = null
const preview = shallowRef<ImportSummary | null>(null)
const rowErrors = shallowRef<ImportRowError[] | null>(null)
const busy = ref(false)
const TOO_BIG = '1 MB 를 넘는 파일은 가져올 수 없습니다.'
defineExpose({ pick: () => input.value?.click() })

async function onFile() {
  const el = input.value!
  const f = el.files?.[0]
  el.value = '' // 같은 파일을 고쳐 다시 올려도 change 가 나게
  if (!f) return
  if (f.size > IMPORT_MAX_BYTES) {
    showToast({ tone: 'danger', message: TOO_BIG })
    return
  }
  name.value = f.name
  // 바이트 그대로 보낸다 — UTF-8 이 아니면 서버가 400 으로 알려 준다(화면에서 디코딩하면 깨진 채 들어간다)
  bytes = await f.arrayBuffer()
  await send(true)
}

/** 먼저 dry_run 으로 요약만 — 관리자가 보고 적용한다. 서버는 전체 검증 뒤 적용이라 부분 적용이 없다 */
async function send(dryRun: boolean) {
  if (!bytes || busy.value) return
  busy.value = true
  try {
    const r = await roomsApi.importSlots(bytes, dryRun)
    if (dryRun) {
      preview.value = r
      return
    }
    preview.value = null
    const skipped = r.skipped.length ? ` 웹에서 고친 ${r.skipped.length}행은 건너뛰었습니다.` : ''
    showToast({ message: `시간표를 가져왔습니다 — 강의실 ${r.rooms}곳에 보냅니다.${skipped}` })
    emit('applied')
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    preview.value = null
    const errs = (e.detail as Partial<ImportErrors> | null)?.errors
    if (e.status === 400 && errs) rowErrors.value = errs
    else if (e.status === 400)
      showToast({ tone: 'danger', message: 'CSV 를 UTF-8 로 저장해 주세요 (엑셀: CSV UTF-8).' })
    else if (e.status === 413) showToast({ tone: 'danger', message: TOO_BIG })
    else if (e.status === 500 && !dryRun) {
      // DB 는 반영됐고 FILE 큐잉만 실패 — 동기화로 다시 보낼 수 있다
      showToast({
        tone: 'danger',
        message: '시간표는 저장됐지만 전송 준비에 실패했습니다. 선택한 곳 동기화로 다시 보내세요.',
      })
      emit('applied')
    } else if (e.status !== 401 && e.status !== 403) showToast({ tone: 'danger', message: e.message })
  } finally {
    busy.value = false
  }
}

const changes = computed(() =>
  preview.value ? preview.value.added + preview.value.updated + preview.value.deleted : 0,
)
const SKIP_COLS = [
  { key: 'row', label: '행', width: '64px', align: 'right' as const },
  { key: 'reason', label: '사유' },
]
const ERR_COLS = [
  { key: 'row', label: '행', width: '64px', align: 'right' as const },
  { key: 'error', label: '사유' },
]
/** 행 0 은 파일 전체(헤더·노드 상한) 오류 — 칸에 — */
const rowsOf = (xs: { row: number }[]) =>
  xs.map((x, i) => ({ ...x, id: i, row: x.row || '—' })) as unknown as Record<string, unknown>[]
</script>

<template>
  <input
    ref="input"
    type="file"
    accept=".csv,text/csv"
    class="csv__file"
    aria-label="CSV 파일"
    @change="onFile"
  />
  <Modal :open="!!preview" :title="`CSV 가져오기 — ${name}`" size="lg" @close="preview = null">
    <template v-if="preview">
      <p class="csv__sum num">
        강의실 {{ preview.rooms }}곳 · 추가 {{ preview.added }} · 수정 {{ preview.updated }} · 삭제
        {{ preview.deleted }}
      </p>
      <p v-if="preview.deleted" class="csv__note">삭제는 파일에 없는 포털(CSV) 행입니다.</p>
      <p v-if="!changes" class="csv__note">바뀌는 것이 없습니다.</p>
      <template v-if="preview.skipped.length">
        <!-- source 보호 — 기능이지 버그가 아니다 (admin-rooms.md §1) -->
        <p class="csv__note">
          웹에서 고친 행(출처 수동·긴급)은 CSV 가 덮지 않습니다 — 아래
          {{ preview.skipped.length }}행은 건너뜁니다.
        </p>
        <Table :columns="SKIP_COLS" :rows="rowsOf(preview.skipped)" />
      </template>
    </template>
    <template #footer>
      <Button variant="secondary" @click="preview = null">취소</Button>
      <Button :loading="busy" :disabled="!changes" @click="send(false)">적용</Button>
    </template>
  </Modal>
  <Modal
    :open="!!rowErrors"
    title="CSV 오류 — 아무것도 적용되지 않았습니다"
    size="lg"
    @close="rowErrors = null"
  >
    <p class="csv__note">
      전체를 검사한 뒤에 적용하므로 일부만 들어가지 않았습니다. 고쳐서 다시 올리세요.
    </p>
    <Table :columns="ERR_COLS" :rows="rowsOf(rowErrors ?? [])" />
    <template #footer>
      <Button variant="secondary" @click="rowErrors = null">닫기</Button>
    </template>
  </Modal>
</template>

<style scoped>
.csv__file {
  display: none;
}
.csv__sum {
  margin: 0 0 var(--space-3);
  font-weight: var(--font-weight-bold);
}
.csv__note {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
</style>
```

`web/src/admin/views/rooms/SlotBlock.vue`
- `defineEmits` 에 `csv: []` 를 더한다.
- `#empty` 의 마지막 EmptyState `actions` 를 바꾼다:
```vue
          :actions="[
            { label: 'CSV 가져오기', onClick: () => emit('csv') },
            { label: '슬롯 추가', variant: 'primary', onClick: () => openForm(null) },
          ]"
```

`web/src/admin/views/RoomsView.vue` 를 통째로 바꾼다 (Task 15 판 + 시험기간·CSV·동기화)
```vue
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { showToast } from '@/components/ui/toast'
import RoomTree from '@/components/domain/RoomTree.vue'
import type { SavedRow } from '@/components/domain/rules'
import { ApiError } from '@/api/client'
import { adminApi } from '@/api/admin'
import { loraApi } from '@/api/lora'
import { roomsApi } from '@/api/rooms'
import type { RoomOut } from '@/api/types'
import { useResource } from '@/lib/useResource'
import { useOutboxTracker } from '../outboxTrack'
import { defaultPick, roomLabeler } from '../roomsView'
import { picked } from '../selection'
import CsvImport from './rooms/CsvImport.vue'
import ExamBlock from './rooms/ExamBlock.vue'
import PendingBlock from './rooms/PendingBlock.vue'
import ResvBlock from './rooms/ResvBlock.vue'
import SlotBlock from './rooms/SlotBlock.vue'

const router = useRouter()
const master = useResource(async () => {
  const [buildings, rooms] = await Promise.all([roomsApi.buildings(), roomsApi.rooms()])
  return { buildings, rooms }
})
const buildings = computed(() => master.data.value?.buildings ?? [])
const allRooms = computed(() => master.data.value?.rooms ?? [])
const hasNoRooms = computed(() => !!master.data.value && !allRooms.value.length)

// 트리 선택은 모듈 상태 — 다른 화면을 다녀와도 남는다. 지워진 방은 빼고, 비었으면 첫 건물의 첫 층
watch(master.data, (d) => {
  if (!d) return
  const alive = picked.value.filter((id) => d.rooms.some((r) => r.id === id))
  picked.value = alive.length ? alive : defaultPick(d.buildings, d.rooms)
})
const selection = computed({
  get: () => picked.value,
  set: (ids: number[]) => (picked.value = ids),
})
const order = (r: RoomOut) => buildings.value.findIndex((b) => b.id === r.building_id)
const pickedRooms = computed(() =>
  allRooms.value
    .filter((r) => picked.value.includes(r.id))
    .sort((a, b) => order(a) - order(b) || a.room - b.room),
)
const label = computed(() => roomLabeler(buildings.value, pickedRooms.value))

// 건물 단위 조회 3개 (S4b §2.6) — 같은 건물 안에서 고른 방을 바꿔도 다시 부르지 않고 걸러서 보인다
const bids = computed(() =>
  [...new Set(pickedRooms.value.map((r) => r.building_id))].sort((a, b) => a - b),
)
const scope = useResource(
  async () => {
    const per = await Promise.all(
      bids.value.map((b) =>
        Promise.all([roomsApi.buildingSlots(b), roomsApi.buildingResv(b), roomsApi.buildingExams(b)]),
      ),
    )
    return {
      slots: per.flatMap((p) => p[0]),
      resv: per.flatMap((p) => p[1]),
      exams: per.flatMap((p) => p[2]),
    }
  },
  { deps: () => bids.value.join(',') },
)
// 신청 대기는 학교 전체 — 처리해야 할 일이라 트리 밖 신청도 숨기지 않는다 (설계 판정)
const pending = useResource(() => adminApi.pendingResv())
const inPick = <T extends { room_id: number }>(xs: T[] | undefined) =>
  (xs ?? []).filter((x) => picked.value.includes(x.room_id))
const slots = computed(() => inPick(scope.data.value?.slots))
const resv = computed(() => inPick(scope.data.value?.resv))
const exams = computed(() => inPick(scope.data.value?.exams))
const scopeLoading = computed(() => scope.loading.value && !scope.data.value)
function reloadAll() {
  void scope.reload()
  void pending.reload()
}

// 오류 — Toast + 재시도. 표는 이전 내용을 지우지 않는다 (useResource 가 data 를 지킨다)
for (const r of [master, scope, pending])
  watch(r.error, (e) => {
    if (e && e.status !== 401 && e.status !== 403)
      showToast({
        tone: 'danger',
        message: e.message,
        action: { label: '재시도', onClick: () => void r.reload() },
      })
  })

// 저장 뒤 OutboxDot — 행 key 로 30초 (새로고침하면 끊긴다)
const tracker = useOutboxTracker()
const buildingOf = (roomId: number) => allRooms.value.find((r) => r.id === roomId)?.building_id
function onSaved(s: SavedRow) {
  const b = buildingOf(s.roomId)
  if (b !== undefined) tracker.track(s.key, b, s.outboxIds)
}
function resync(roomId: number, key: string) {
  const b = buildingOf(roomId)
  if (b !== undefined) void tracker.resync(key, roomId, b)
}

// CSV — 파일 선택은 숨은 input, 흐름(미리보기→적용)은 CsvImport 가 진다
const csv = ref<InstanceType<typeof CsvImport>>()
// 선택한 곳 동기화 — '전체 동기화'를 범위로 좁혔다. 건물 전체를 실수로 재전송하지 않게
const syncing = ref(false)
async function syncPicked() {
  const list = [...pickedRooms.value]
  if (syncing.value || !list.length) return
  syncing.value = true
  const bad: string[] = []
  try {
    for (const r of list) {
      try {
        await loraApi.syncRoom(r.id)
      } catch (e) {
        if (!(e instanceof ApiError)) throw e
        if (e.status === 401 || e.status === 403) return
        bad.push(`${label.value(r.id)}호`)
      }
    }
  } finally {
    syncing.value = false
  }
  showToast(
    bad.length
      ? {
          tone: 'danger',
          message: `${list.length}곳 중 ${list.length - bad.length}곳 보냄 · ${bad.join(', ')} 실패`,
        }
      : { message: `${list.length}곳에 다시 보냈습니다.` },
  )
}
</script>

<template>
  <main class="rooms">
    <!-- 상단 바는 스크롤해도 붙어 있다 — 트리에서 고른 것이 아래 표들의 범위다 -->
    <header class="rooms__bar">
      <RoomTree v-model:selected="selection" :buildings="buildings" :rooms="allRooms" />
      <span class="rooms__hint">강의실 선택</span>
      <div class="rooms__tools">
        <Button variant="secondary" @click="csv?.pick()">CSV 가져오기</Button>
        <Button
          variant="secondary"
          :loading="syncing"
          :disabled="!pickedRooms.length"
          @click="syncPicked"
          >선택한 곳 동기화</Button
        >
      </div>
    </header>
    <CsvImport ref="csv" @applied="scope.reload" />
    <EmptyState
      v-if="hasNoRooms"
      message="강의실이 없습니다. 건물 · 강의실 화면에서 먼저 만드세요."
      :actions="[{ label: '건물 · 강의실로', variant: 'primary', onClick: () => router.push('/master') }]"
    />
    <div v-else class="rooms__blocks">
      <SlotBlock
        :rooms="pickedRooms"
        :label="label"
        :slots="slots"
        :states="tracker.states"
        :loading="scopeLoading"
        @saved="onSaved"
        @changed="scope.reload"
        @resync="resync"
        @csv="csv?.pick()"
      />
      <!-- 신청 대기는 예약 블록 위에 선다 — 승인해야 approved 가 되어 노드로 나간다 -->
      <PendingBlock :pending="pending.data.value" @changed="reloadAll" />
      <ResvBlock
        :rooms="pickedRooms"
        :label="label"
        :resv="resv"
        :states="tracker.states"
        :loading="scopeLoading"
        @saved="onSaved"
        @changed="reloadAll"
        @resync="resync"
      />
      <ExamBlock
        :rooms="pickedRooms"
        :label="label"
        :exams="exams"
        :states="tracker.states"
        :loading="scopeLoading"
        @saved="onSaved"
        @changed="scope.reload"
        @resync="resync"
      />
    </div>
  </main>
</template>

<style scoped>
.rooms {
  padding: 0 var(--space-5) var(--space-5);
}
.rooms__bar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) 0;
  background: var(--bg);
}
.rooms__hint {
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
.rooms__tools {
  display: flex;
  gap: var(--space-2);
  margin-left: auto;
}
/* 탭이 아니라 세로 스택 — 셋이 같은 강의실의 다른 시간 축이라 함께 보여야 한다 */
.rooms__blocks {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}
</style>
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`
Expected: PASS

- [ ] **Step 5: E2E — 시험기간 · CSV · 동기화**

`web/e2e/admin-ops.spec.ts` 끝에 추가
```ts
test('시험기간 — 고른 3곳에 한 번에(진행 라벨), 같은 기간은 한 행으로 접고 펼쳐서 지운다', async () => {
  const ex = page.getByRole('region', { name: '시험기간' })
  await ex.getByRole('button', { name: '+ 선택한 3곳에 기간 추가' }).click()
  const d = page.getByRole('dialog', { name: '시험기간 추가' })
  await expect(d).toContainText('대상 3곳 · 101호, 102호, 202호')
  await d.getByLabel('시작일').fill(kstDate(20))
  await d.getByLabel('종료일').fill(kstDate(24))
  await d.getByRole('button', { name: '선택한 3곳에 기간 추가' }).click()
  await expect(d).toHaveCount(0)
  await expect(page.getByText('3곳에 시험기간을 넣었습니다.')).toBeVisible()
  const g = ex.locator('tbody tr').first()
  await expect(g).toContainText('101, 102, 202')
  await expect(g).toContainText('3곳')
  await g.getByRole('button', { name: '펼치기' }).click()
  const items = ex.locator('.blk__item')
  await expect(items).toHaveCount(3)
  await items.filter({ hasText: '202호' }).getByRole('button', { name: '삭제' }).click()
  const c = page.getByRole('dialog', { name: '시험기간 삭제' })
  await c.getByRole('button', { name: '삭제' }).click()
  await expect(items).toHaveCount(2)
  await shot(page, 'admin-rooms-1440')
})

test('CSV — 먼저 미리보기, 웹에서 고친 행은 건너뛴다고 말하고, 적용하면 포털 출처 / 행 오류는 아무것도 적용 안 됨', async () => {
  const csv = (rows: string[]) => ({
    name: 'slots.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(
      ['school,building,room,day,start,end,type,subject,professor', ...rows].join('\n'),
    ),
  })
  await page
    .locator('input[type=file]')
    .setInputFiles(
      csv([
        '우송대,K,101,월,13:00,15:00,수업,포털수업,박교수',
        '우송대,K,202,수,09:00,10:00,수업,포털과목,이교수',
      ]),
    )
  const d = page.getByRole('dialog', { name: 'CSV 가져오기 — slots.csv' })
  await expect(d).toContainText('강의실 1곳 · 추가 1 · 수정 0 · 삭제 0')
  await expect(d.getByRole('row').filter({ hasText: '수동 슬롯 있음' })).toContainText('2')
  await shot(page, 'admin-rooms-csv-1440')
  await d.getByRole('button', { name: '적용' }).click()
  await expect(page.getByText(/시간표를 가져왔습니다/)).toBeVisible()
  const slots = page.getByRole('region', { name: '시간표' })
  await expect(slots.getByRole('row').filter({ hasText: '포털과목' })).toContainText('포털')
  await expect(slots.getByRole('row').filter({ hasText: '캡스톤디자인' })).toContainText('수동')
  await expect(slots.getByRole('row').filter({ hasText: '포털수업' })).toHaveCount(0)
  await page
    .locator('input[type=file]')
    .setInputFiles(csv(['우송대,K,999,월,09:00,10:00,수업,없는방,김교수']))
  const e = page.getByRole('dialog', { name: 'CSV 오류 — 아무것도 적용되지 않았습니다' })
  await expect(e.getByRole('row').filter({ hasText: '999' })).toContainText('2')
  await e.getByRole('button', { name: '닫기' }).click()
  await expect(e).toHaveCount(0)
})

test('선택한 곳 동기화 — 고른 방 수만큼 보내고 결과를 말한다', async () => {
  await page.getByRole('button', { name: '선택한 곳 동기화' }).click()
  await expect(page.getByText('3곳에 다시 보냈습니다.')).toBeVisible()
})
```

Run: **E2E 명령** + ` e2e/admin-ops.spec.ts`
Expected: `14 passed`

- [ ] **Step 6: 스크린샷 대조**

`admin-rooms-1440.png`·`admin-rooms-csv-1440.png` 를 `admin-rooms.md` 와 대조:
- 상단 바 오른쪽 `CSV 가져오기` · `선택한 곳 동기화`(secondary 둘).
- 세로 스택 순서: 시간표 → (신청 대기, 0건이면 없음) → 예약 → 시험기간. 블록 사이 space.5.
- 시험기간: `+ 선택한 3곳에 기간 추가`(primary), 접힌 행 `▸ 101, 102 | 시작일 | 종료일 | 2곳`, 펼친 줄은 sunken 바탕 한 단 들여쓰기, 방마다 `호 · 점 · 수정 · 삭제`.
- CSV 미리보기 Modal(lg): 굵은 요약 한 줄, source 보호 안내 문장, `행 | 사유` 표, `취소`·`적용`.
어긋나면 고치고 다시 찍는다.

- [ ] **Step 7: 커밋**

```bash
git add web/src/admin web/e2e
git commit -m "feat(web): 강의실 설정 C — 시험기간(같은 기간 묶기·펼쳐서 수정/삭제·고른 방 일괄), CSV 가져오기(dry_run 미리보기·건너뛴 행·행 오류는 아무것도 적용 안 됨), 선택한 곳 동기화 + E2E"
```

---

### Task 17: 주간 시간표 — 배치 계산(`weekView.ts`)

**Files:**
- Create: `web/src/admin/weekView.ts`
- Test: `web/src/admin/__tests__/weekView.spec.ts`

**Interfaces:**
- Consumes: `BUSY_TYPES`·`slotKey`·`resvKey`·`toMin`(Task 2), `addDays`·`dayOfDate`(Task 2), `SlotWithRoom`·`ResvWithRoom`·`ExamOut`(Task 1).
- Produces: `ROW_MIN = 30` · `ROW_PX = 44` · `DAY_START = 540` · `DAY_END = 1080` · `NIGHT_END = 1320` · `interface Block { key; day; s; e; busy; slot?; resv? }`(`s`·`e` 는 자정부터 분) · `interface Placed extends Block { lane; lanes }` · `interface Overlap { s; e; lane; lanes }` · `interface Range { from; to }` · `interface Box { top; height; cutEnd }` · `weekBlocks(slots, resv, monday): Block[]` · `layoutDay(blocks): { placed: Placed[]; overlaps: Overlap[] }` · `gridRange(blocks, night): Range` · `timeRows(r: Range): number[]` · `needsNight(blocks): boolean` · `needsWeekend(blocks): boolean` · `blockBox(b: { s; e }, r: Range): Box | null` · `examDates(exams, monday): Set<string>`.

- [ ] **Step 1: 실패 테스트**

`web/src/admin/__tests__/weekView.spec.ts`
```ts
import { describe, expect, it } from 'vitest'
import {
  blockBox,
  examDates,
  gridRange,
  layoutDay,
  needsNight,
  needsWeekend,
  timeRows,
  weekBlocks,
} from '@/admin/weekView'
import type { ResvWithRoom, SlotWithRoom } from '@/api/types'

const S = (o: Partial<SlotWithRoom>): SlotWithRoom => ({
  id: 1,
  room_id: 11,
  day: 1,
  s_h: 10,
  s_m: 0,
  e_h: 12,
  e_m: 0,
  type: 1,
  subject: '캡스톤디자인',
  professor: '김교수',
  source: 2,
  ...o,
})
const V = (o: Partial<ResvWithRoom>): ResvWithRoom => ({
  id: 7,
  room_id: 11,
  date: '2026-09-21',
  s_h: 11,
  s_m: 0,
  e_h: 12,
  e_m: 0,
  type: 5,
  subject: '특강',
  professor: '',
  status: 'approved',
  requester: null,
  pushed_at: null,
  ...o,
})
const monday = '2026-09-21'

describe('weekBlocks', () => {
  it('빈강의실(4)·거절·다른 주는 그리지 않는다 — 예약은 날짜의 요일, 점유는 사용중 슬롯·승인만', () => {
    const b = weekBlocks(
      [S({}), S({ id: 2, type: 4, day: 2 }), S({ id: 3, type: 3, day: 3 })],
      [
        V({}),
        V({ id: 8, date: '2026-09-23', status: 'requested' }),
        V({ id: 9, status: 'rejected' }),
        V({ id: 10, date: '2026-09-28' }),
      ],
      monday,
    )
    expect(b.map((x) => [x.key, x.day, x.busy])).toEqual([
      ['s11-1-10-0', 1, true],
      ['s11-3-10-0', 3, false],
      ['r7', 1, true],
      ['r8', 3, false],
    ])
  })
})

describe('layoutDay', () => {
  it('슬롯과 승인 예약이 겹치면 반씩 — 겹친 구간에만 막대 하나', () => {
    const { placed, overlaps } = layoutDay(weekBlocks([S({})], [V({})], monday))
    expect(placed.map((p) => [p.key, p.lane, p.lanes])).toEqual([
      ['s11-1-10-0', 0, 2],
      ['r7', 1, 2],
    ])
    expect(overlaps).toEqual([{ s: 660, e: 720, lane: 1, lanes: 2 }])
  })
  it('맞닿으면 한 줄, 휴강·신청과의 겹침은 나란히만 (막대 없음)', () => {
    const touch = weekBlocks([S({ e_h: 11 }), S({ id: 2, s_h: 11, e_h: 12 })], [], monday)
    expect(layoutDay(touch).placed.map((p) => p.lanes)).toEqual([1, 1])
    const soft = layoutDay(
      weekBlocks(
        [S({ type: 3 })],
        [V({}), V({ id: 8, s_h: 10, e_h: 11, status: 'requested' })],
        monday,
      ),
    )
    expect(soft.placed.map((p) => p.lanes)).toEqual([2, 2, 2])
    expect(soft.overlaps).toEqual([])
  })
  it('셋이 겹치면 1/3 씩 (디자인 미결 1 — 그대로 그린다)', () => {
    const three = layoutDay(
      weekBlocks(
        [S({}), S({ id: 2, s_m: 30 }), S({ id: 3, s_h: 11 })],
        [],
        monday,
      ),
    )
    expect(three.placed.map((p) => [p.lane, p.lanes])).toEqual([
      [0, 3],
      [1, 3],
      [2, 3],
    ])
    expect(three.overlaps).toHaveLength(3)
  })
})

describe('격자', () => {
  it('기본 09:00~18:00, 야간 22:00, 09:00 전 블록이 있으면 그 30분부터', () => {
    expect(gridRange([], false)).toEqual({ from: 540, to: 1080 })
    expect(gridRange([], true)).toEqual({ from: 540, to: 1320 })
    const early = weekBlocks([S({ s_h: 7, s_m: 40, e_h: 9 })], [], monday)
    expect(gridRange(early, false)).toEqual({ from: 450, to: 1080 })
    expect(timeRows({ from: 540, to: 600 })).toEqual([540, 570])
    expect(timeRows(gridRange([], false))).toHaveLength(18)
    expect(timeRows(gridRange([], true))).toHaveLength(26)
  })
  it('격자 밖은 잘라 그리고 잘렸다고 알린다 (격자를 늘리지 않는다)', () => {
    expect(blockBox({ s: 1020, e: 1170 }, { from: 540, to: 1080 })).toEqual({
      top: 704,
      height: 88,
      cutEnd: true,
    })
    expect(blockBox({ s: 1110, e: 1170 }, { from: 540, to: 1080 })).toBeNull()
  })
  it('야간은 18:00 넘게 끝나는 블록, 주말은 토·일 블록이 있으면 자동', () => {
    expect(needsNight(weekBlocks([S({ e_h: 18, e_m: 30 })], [], monday))).toBe(true)
    expect(needsNight(weekBlocks([S({ e_h: 18 })], [], monday))).toBe(false)
    expect(needsWeekend(weekBlocks([S({ day: 6 })], [], monday))).toBe(true)
    expect(needsWeekend(weekBlocks([S({})], [], monday))).toBe(false)
  })
  it('시험기간 띠 — 달을 넘어도 그 주의 날짜만', () => {
    const on = examDates(
      [{ id: 1, date_start: '2026-09-30', date_end: '2026-10-02' }],
      '2026-09-28',
    )
    expect([...on]).toEqual(['2026-09-30', '2026-10-01', '2026-10-02'])
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin/__tests__/weekView.spec.ts`
Expected: FAIL — `Failed to resolve import "@/admin/weekView"`

- [ ] **Step 3: 구현**

`web/src/admin/weekView.ts`
```ts
import type { ExamOut, ResvWithRoom, SlotWithRoom } from '@/api/types'
import { BUSY_TYPES, resvKey, slotKey, toMin } from '@/components/domain/rules'
import { addDays, dayOfDate } from '@/lib/time'

/** 격자 — 30분 행, 44px 고정. 기본 09:00~18:00(18행), 야간 보기 22:00 까지(26행) (admin-schedule.md).
 * 웹의 표시 축일 뿐 단말(교시)과 무관하다 */
export const ROW_MIN = 30
export const ROW_PX = 44
export const DAY_START = 9 * 60
export const DAY_END = 18 * 60
export const NIGHT_END = 22 * 60

export interface Block {
  key: string
  /** 1=월 … 7=일 */
  day: number
  /** 자정부터 분 */
  s: number
  e: number
  /** 점유 — 사용중 슬롯(1·2·5·6)과 승인 예약. 겹침 막대는 둘 다 점유일 때만 */
  busy: boolean
  slot?: SlotWithRoom
  resv?: ResvWithRoom
}
export interface Placed extends Block {
  lane: number
  lanes: number
}
export interface Overlap {
  s: number
  e: number
  /** 막대는 이 lane 의 왼쪽 경계에 선다 */
  lane: number
  lanes: number
}
export interface Range {
  from: number
  to: number
}
export interface Box {
  top: number
  height: number
  cutEnd: boolean
}

/** 시간표는 요일 기반이라 주가 바뀌어도 같다 — 예약만 보고 있는 주로 거른다.
 * 빈강의실(4)은 그리지 않는다, 거절·취소·만료 예약도 그리지 않는다 */
export function weekBlocks(slots: SlotWithRoom[], resv: ResvWithRoom[], monday: string): Block[] {
  const sunday = addDays(monday, 6)
  const fromSlots: Block[] = slots
    .filter((s) => s.type !== 4)
    .map((s) => ({
      key: slotKey(s),
      day: s.day,
      s: toMin(s.s_h, s.s_m),
      e: toMin(s.e_h, s.e_m),
      busy: BUSY_TYPES.includes(s.type),
      slot: s,
    }))
  const fromResv: Block[] = resv
    .filter(
      (r) =>
        (r.status === 'approved' || r.status === 'requested') && r.date >= monday && r.date <= sunday,
    )
    .map((r) => ({
      key: resvKey(r.id),
      day: dayOfDate(r.date),
      s: toMin(r.s_h, r.s_m),
      e: toMin(r.e_h, r.e_m),
      busy: r.status === 'approved',
      resv: r,
    }))
  return [...fromSlots, ...fromResv]
}

/** 하루치 배치 — 겹치는 무리마다 lane 을 탐욕 배정, 폭은 무리의 lane 수로 균등 분할.
 * 겹친 두 블록이 둘 다 점유면 겹친 구간에만 막대 하나 (테두리 둘은 "경고 두 개"로 읽힌다) */
export function layoutDay(blocks: Block[]): { placed: Placed[]; overlaps: Overlap[] } {
  const sorted = [...blocks].sort((a, b) => a.s - b.s || a.e - b.e)
  const placed: Placed[] = []
  let cluster: Placed[] = []
  let laneEnds: number[] = []
  let clusterEnd = -1
  const flush = () => {
    for (const p of cluster) p.lanes = laneEnds.length
    cluster = []
    laneEnds = []
  }
  for (const b of sorted) {
    if (b.s >= clusterEnd) flush()
    let lane = laneEnds.findIndex((end) => end <= b.s)
    if (lane < 0) {
      lane = laneEnds.length
      laneEnds.push(b.e)
    } else laneEnds[lane] = b.e
    const p: Placed = { ...b, lane, lanes: 1 }
    cluster.push(p)
    placed.push(p)
    clusterEnd = Math.max(clusterEnd, b.e)
  }
  flush()
  const overlaps: Overlap[] = []
  for (let i = 0; i < placed.length; i++)
    for (let j = i + 1; j < placed.length; j++) {
      const a = placed[i]
      const b = placed[j]
      if (!a.busy || !b.busy) continue
      const s = Math.max(a.s, b.s)
      const e = Math.min(a.e, b.e)
      if (s < e) overlaps.push({ s, e, lane: Math.max(a.lane, b.lane), lanes: a.lanes })
    }
  return { placed, overlaps }
}

/** 09:00 전 블록이 있으면 그 30분부터 — 07:30 수업이 화면에 없으면 편집할 길이 없다 (설계 판정) */
export function gridRange(blocks: Block[], night: boolean): Range {
  const from = blocks.reduce(
    (m, b) => Math.min(m, Math.floor(b.s / ROW_MIN) * ROW_MIN),
    DAY_START,
  )
  return { from, to: night ? NIGHT_END : DAY_END }
}
export const timeRows = (r: Range) =>
  Array.from({ length: (r.to - r.from) / ROW_MIN }, (_, i) => r.from + i * ROW_MIN)

/** 보고 있는 주에 18:00 넘게 끝나는 블록 — 없으면 19시 수업이 화면에 없다 */
export const needsNight = (blocks: Block[]) => blocks.some((b) => b.e > DAY_END)
export const needsWeekend = (blocks: Block[]) => blocks.some((b) => b.day >= 6)

/** 세로 위치 — 격자 밖은 잘라 그린다. 22:00 넘게 걸친 블록은 하단에 ~HH:MM 을 적는다 */
export function blockBox(b: { s: number; e: number }, r: Range): Box | null {
  const s = Math.max(b.s, r.from)
  const e = Math.min(b.e, r.to)
  if (e <= s) return null
  return {
    top: ((s - r.from) / ROW_MIN) * ROW_PX,
    height: ((e - s) / ROW_MIN) * ROW_PX,
    cutEnd: b.e > r.to,
  }
}

/** 시험기간에 걸린 그 주의 날짜 — 요일 헤더 아래 얇은 띠 */
export function examDates(exams: ExamOut[], monday: string): Set<string> {
  const out = new Set<string>()
  for (let i = 0; i < 7; i++) {
    const d = addDays(monday, i)
    if (exams.some((x) => x.date_start <= d && d <= x.date_end)) out.add(d)
  }
  return out
}
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add web/src/admin/weekView.ts web/src/admin/__tests__/weekView.spec.ts
git commit -m "feat(web): 주간 격자 배치 — 주 단위 블록(빈강의실·거절 제외), 겹침 lane 균등 분할과 점유끼리만 겹침 막대, 야간·주말 자동, 격자 밖 자르기, 시험기간 날짜"
```

---

### Task 18: 주간 시간표 — 화면 · 편집 · 메뉴 + E2E

**Files:**
- Create: `web/src/admin/views/WeekView.vue`
- Modify: `web/src/admin/router.ts`, `web/src/admin/AdminShell.vue`, `web/src/admin/__tests__/shell.spec.ts`, `web/e2e/admin-ops.spec.ts`, `web/e2e/admin-shell.spec.ts`
- Test: `web/src/admin/__tests__/week.spec.ts`

**Interfaces:**
- Consumes: `weekView.ts`(Task 17) · `RoomTree`(single)·`SlotForm`·`ResvForm`(Task 5·6·7) · `useOutboxTracker`·`weekRoom`·`weekMonday`·`nightPref`·`weekendPref`·`picked`(Task 9) · `resvDot`(Task 15) · `RowDot`(Task 14) · `ConfirmModal`(Task 10) · `roomsApi.{buildings, rooms, slots, reservations, exams, deleteSlot}`(Task 1).
- Produces: 라우트 `/week`(마지막 강의실 → 트리 첫 방 → 첫 강의실로 `replace`) · `/rooms/:roomId(\d+)/week`(props `roomId`). 메뉴 `주간 시간표` = `weekRoom` 이 있으면 `/rooms/{id}/week`, 없으면 `/week`.
- Produces (`WeekView.vue`): 빈 칸 `button.wk__cell[aria-label="{요일} {HH:MM} 슬롯 추가"]`, 블록 `.wk__block`(`.wk__label` 라벨), 겹침 `.wk__overlap-label`, 주 라벨 `.wk__range`, 주 이동 `이전 주`·`다음 주`(aria-label), `야간`·`주말` Checkbox.

- [ ] **Step 1: 실패 테스트**

`web/src/admin/__tests__/week.spec.ts`
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { RouterView, createMemoryHistory, createRouter } from 'vue-router'
import WeekView from '@/admin/views/WeekView.vue'
import { nightPref, picked, weekMonday, weekRoom, weekendPref } from '@/admin/selection'
import { roomsApi } from '@/api/rooms'
import { ApiError, MESSAGES } from '@/api/client'
import type { ResvWithRoom, RoomOut, SlotOut } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/rooms', () => ({
  roomsApi: {
    buildings: vi.fn(),
    rooms: vi.fn(),
    slots: vi.fn(),
    reservations: vi.fn(),
    exams: vi.fn(),
    buildingOutbox: vi.fn(),
    putSlot: vi.fn(),
    deleteSlot: vi.fn(),
    saveResv: vi.fn(),
  },
}))
vi.mock('@/api/lora', () => ({ loraApi: { syncRoom: vi.fn() } }))
const api = vi.mocked(roomsApi)

const R = (id: number, room: number): RoomOut => ({
  id,
  building_id: 1,
  room,
  units: 1,
  reservable: true,
})
const S = (o: Partial<SlotOut>): SlotOut => ({
  id: 1,
  day: 1,
  s_h: 10,
  s_m: 0,
  e_h: 12,
  e_m: 0,
  type: 1,
  subject: '캡스톤디자인',
  professor: '김교수',
  source: 2,
  ...o,
})
const V = (o: Partial<ResvWithRoom>): ResvWithRoom => ({
  id: 7,
  room_id: 11,
  date: '2026-09-21',
  s_h: 11,
  s_m: 0,
  e_h: 12,
  e_m: 0,
  type: 5,
  subject: '특강',
  professor: '학생처',
  status: 'approved',
  requester: null,
  pushed_at: new Date(),
  ...o,
})

let w: VueWrapper
async function mountAt(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/week', component: WeekView },
      { path: '/rooms/:roomId(\\d+)/week', component: WeekView, props: true },
      { path: '/:p(.*)*', component: { render: () => null } },
    ],
  })
  await router.push(path)
  await router.isReady()
  w = mount({ render: () => h(RouterView) }, { global: { plugins: [router], stubs: { teleport: true } } })
  await flushPromises()
  return router
}
type Root = VueWrapper | DOMWrapper<Element>
const btn = (root: Root, text: string) => root.findAll('button').find((b) => b.text() === text)!
const dialog = (title: string) =>
  w.findAll('[role=dialog]').find((d) => d.get('h2').text() === title)
const control = (root: Root, label: string) =>
  root
    .findAll('.field, .sel')
    .find((f) => f.find('label').exists() && f.get('label').text().replace('*', '').trim() === label)!
    .get('input, select')
const labels = () => w.findAll('.wk__block .wk__label').map((l) => l.text())
const check = (label: string) => w.findAll('.cb').find((c) => c.text() === label)!.get('input')

beforeEach(() => {
  // KST 2026-09-25(금) 12:00 — 이번 주 월요일 9/21
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-09-25T03:00:00Z'))
  picked.value = []
  weekRoom.value = null
  weekMonday.value = null
  nightPref.value = null
  weekendPref.value = null
  Object.values(api).forEach((f) => f.mockReset())
  api.buildings.mockResolvedValue([{ id: 1, school_id: 1, name: '공학관', bld: 'E', modem_id: 'm1' }])
  api.rooms.mockResolvedValue([R(11, 401), R(12, 402)])
  api.slots.mockResolvedValue([S({})])
  api.reservations.mockResolvedValue([
    V({}),
    V({
      id: 8,
      date: '2026-09-22',
      s_h: 13,
      e_h: 14,
      type: 6,
      subject: '스터디',
      status: 'requested',
      requester: { email: 's@wsu.ac.kr', name: '김민준', student_no: '1' },
    }),
    V({ id: 9, subject: '거절됨', status: 'rejected' }),
  ])
  api.exams.mockResolvedValue([{ id: 1, date_start: '2026-09-23', date_end: '2026-09-24' }])
  api.buildingOutbox.mockResolvedValue([])
  for (const t of [...toasts.value]) dismissToast(t.id)
})
afterEach(() => {
  w?.unmount()
  vi.useRealTimers()
})

describe('주간 시간표', () => {
  it('/week — 마지막 강의실 → 트리 첫 방 → 첫 강의실로 바꿔 간다', async () => {
    picked.value = [12]
    let router = await mountAt('/week')
    expect(router.currentRoute.value.path).toBe('/rooms/12/week')
    expect(weekRoom.value).toBe(12)
    w.unmount()
    weekRoom.value = null
    picked.value = []
    router = await mountAt('/week')
    expect(router.currentRoute.value.path).toBe('/rooms/11/week')
  })

  it('블록 — 슬롯은 유형 라벨, 예약은 "예약 · ", 신청은 "신청 · " 점선, 겹친 구간에 막대 하나, 시험기간 띠', async () => {
    await mountAt('/rooms/11/week')
    expect(w.get('.tree__trigger').text()).toContain('공학관 401호')
    expect(w.get('.wk__range').text()).toBe('9/21~9/27')
    expect(labels()).toEqual(['수업중', '예약 · 특강', '신청 · 대여중'])
    const requested = w.findAll('.wk__block').find((b) => b.text().includes('스터디'))!
    expect(requested.classes()).toContain('wk__block--requested')
    expect(w.findAll('.wk__overlap-label').map((l) => l.text())).toEqual(['겹침 11:00–12:00'])
    const heads = w.findAll('.wk__head').map((x) => x.text())
    expect(heads[2]).toContain('시험기간')
    expect(heads[3]).toContain('시험기간')
    expect(heads[0]).not.toContain('시험기간')
  })

  it('빈 칸을 누르면 그 요일·시각으로 슬롯 추가 — 종료는 +1시간', async () => {
    await mountAt('/rooms/11/week')
    await w.get('button[aria-label="수 14:00 슬롯 추가"]').trigger('click')
    const d = dialog('슬롯 추가')!
    expect((control(d, '요일').element as HTMLSelectElement).value).toBe('3')
    expect((control(d, '시작').element as HTMLInputElement).value).toBe('14:00')
    expect((control(d, '종료').element as HTMLInputElement).value).toBe('15:00')
  })

  it('주 이동은 서버를 다시 부르지 않는다 — 시간표는 그대로, 예약만 다시 걸러진다', async () => {
    await mountAt('/rooms/11/week')
    await w.get('button[aria-label="다음 주"]').trigger('click')
    expect(w.get('.wk__range').text()).toBe('9/28~10/4')
    expect(labels()).toEqual(['수업중'])
    expect(w.findAll('.wk__overlap-label')).toHaveLength(0)
    expect(api.slots).toHaveBeenCalledTimes(1)
    expect(api.reservations).toHaveBeenCalledTimes(1)
  })

  it('야간·주말 — 필요한 블록이 있으면 켠 채 시작, 사용자가 끄면 그 선택을 유지', async () => {
    api.slots.mockResolvedValue([S({}), S({ id: 2, day: 6, s_h: 19, e_h: 20, e_m: 30 })])
    await mountAt('/rooms/11/week')
    expect((check('야간').element as HTMLInputElement).checked).toBe(true)
    expect((check('주말').element as HTMLInputElement).checked).toBe(true)
    expect(w.findAll('.wk__time')).toHaveLength(26)
    expect(w.findAll('.wk__head')).toHaveLength(7)
    await check('야간').setValue(false)
    expect(w.findAll('.wk__time')).toHaveLength(18)
    w.unmount()
    await mountAt('/rooms/11/week')
    expect((check('야간').element as HTMLInputElement).checked).toBe(false)
  })

  it('다른 학교·없는 강의실(404) — "찾을 수 없습니다", 오류 Toast 없음', async () => {
    api.slots.mockRejectedValue(new ApiError(404, MESSAGES[404]))
    api.reservations.mockRejectedValue(new ApiError(404, MESSAGES[404]))
    api.exams.mockRejectedValue(new ApiError(404, MESSAGES[404]))
    await mountAt('/rooms/99/week')
    expect(w.text()).toContain('강의실을 찾을 수 없습니다. 위에서 다른 강의실을 고르세요.')
    expect(toasts.value).toHaveLength(0)
  })

  it('시간표가 없으면 격자는 두고 가운데 안내', async () => {
    api.slots.mockResolvedValue([])
    api.reservations.mockResolvedValue([])
    await mountAt('/rooms/11/week')
    expect(w.findAll('.wk__cell').length).toBeGreaterThan(0)
    expect(w.text()).toContain('이 강의실에 등록된 시간표가 없습니다')
  })

  it('슬롯을 누르면 수정 폼 — 거기서 삭제(확인), 신청 블록은 열지 않는다', async () => {
    await mountAt('/rooms/11/week')
    await w.findAll('.wk__block').find((b) => b.text().includes('스터디'))!.trigger('click')
    expect(w.findAll('[role=dialog]')).toHaveLength(0)
    await w.findAll('.wk__block').find((b) => b.text().includes('캡스톤디자인'))!.trigger('click')
    await btn(dialog('슬롯 수정')!, '삭제').trigger('click')
    const c = dialog('슬롯 삭제')!
    expect(c.text()).toContain('401호 월 10:00 캡스톤디자인')
  })
})
```

`web/src/admin/__tests__/shell.spec.ts` 첫 `it` 의 메뉴 기대값과 인덱스를 바꾼다 (최종 여섯 — #46 순서)
```ts
    expect(links.map((a) => a.text().replace(/\d+/g, '').trim())).toEqual([
      '건물 · 강의실',
      '강의실 설정',
      '주간 시간표',
      '노드 상태',
      '전송 현황',
      '회원',
    ])
    expect(links[2].attributes('href')).toBe('/week')
    expect(links[4].attributes('aria-current')).toBe('page')
    expect(links[5].text()).toContain('2')
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin`
Expected: FAIL — `Failed to resolve import "@/admin/views/WeekView.vue"`, shell.spec 메뉴 배열 불일치

- [ ] **Step 3: 구현**

`web/src/admin/views/WeekView.vue`
```vue
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import { showToast } from '@/components/ui/toast'
import OutboxDot from '@/components/domain/OutboxDot.vue'
import ResvForm from '@/components/domain/ResvForm.vue'
import RoomTree from '@/components/domain/RoomTree.vue'
import SlotForm from '@/components/domain/SlotForm.vue'
import { DAYS, TYPE_LABEL, type SavedRow } from '@/components/domain/rules'
import { ApiError } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { ResvWithRoom, SlotWithRoom } from '@/api/types'
import { addDays, hm, kstDateStr, md, mondayOf } from '@/lib/time'
import { useResource } from '@/lib/useResource'
import ConfirmModal from '../ConfirmModal.vue'
import { useOutboxTracker } from '../outboxTrack'
import { resvDot } from '../roomsView'
import { nightPref, picked, weekMonday, weekRoom, weekendPref } from '../selection'
import {
  ROW_PX,
  blockBox,
  examDates,
  gridRange,
  layoutDay,
  needsNight,
  needsWeekend,
  timeRows,
  weekBlocks,
  type Placed,
} from '../weekView'
import RowDot from './rooms/RowDot.vue'

const props = defineProps<{ roomId?: string }>()
const router = useRouter()
const today = kstDateStr(new Date())
const clock = (t: number) => hm(Math.floor(t / 60), t % 60)

const master = useResource(async () => {
  const [buildings, rooms] = await Promise.all([roomsApi.buildings(), roomsApi.rooms()])
  return { buildings, rooms }
})
const id = computed(() => (props.roomId ? Number(props.roomId) : null))
const room = computed(() => master.data.value?.rooms.find((r) => r.id === id.value) ?? null)
const noRooms = computed(() => !!master.data.value && !master.data.value.rooms.length)

// /week — 마지막으로 본 강의실 → 페이지1 트리의 첫 방 → 첫 강의실
watch(
  () => [master.data.value, id.value] as const,
  ([d, rid]) => {
    if (!d || rid !== null) return
    const has = (x: number | null | undefined): x is number =>
      x != null && d.rooms.some((r) => r.id === x)
    const first = [...d.rooms].sort((a, b) => a.building_id - b.building_id || a.room - b.room)[0]
    const target = [weekRoom.value, picked.value[0], first?.id].find(has)
    if (target !== undefined) void router.replace(`/rooms/${target}/week`)
  },
  { immediate: true },
)
watch(
  id,
  (v) => {
    if (v !== null) weekRoom.value = v
  },
  { immediate: true },
)

// 강의실 하나만 본다 — 건물 단위 API 가 필요 없다. 세 번 불러 겹쳐 그린다
const res = useResource(
  async () => {
    const rid = id.value
    if (rid === null) return null
    const [slots, resv, exams] = await Promise.all([
      roomsApi.slots(rid),
      roomsApi.reservations(rid),
      roomsApi.exams(rid),
    ])
    return { slots: slots.map((s) => ({ ...s, room_id: rid })), resv, exams }
  },
  { deps: id },
)
// 다른 학교·지워진 방은 404 — 권한 오류가 아니라 '없음'으로 다룬다 (서버가 존재를 숨긴다)
const notFound = computed(
  () =>
    (!!master.data.value && id.value !== null && !room.value) || res.error.value?.status === 404,
)
for (const r of [master, res])
  watch(r.error, (e) => {
    if (e && ![401, 403, 404].includes(e.status))
      showToast({
        tone: 'danger',
        message: e.message,
        action: { label: '재시도', onClick: () => void r.reload() },
      })
  })

// 보고 있는 주 — 강의실을 바꿔도 유지(같은 주의 다른 강의실을 견주는 것이 가장 잦다). 주 이동은 서버를 부르지 않는다
const monday = computed(() => weekMonday.value ?? mondayOf(today))
const sunday = computed(() => addDays(monday.value, 6))
function shiftWeek(n: number) {
  weekMonday.value = addDays(monday.value, 7 * n)
}
const slots = computed<SlotWithRoom[]>(() => res.data.value?.slots ?? [])
const resv = computed<ResvWithRoom[]>(() => res.data.value?.resv ?? [])
const blocks = computed(() => weekBlocks(slots.value, resv.value, monday.value))
// 야간·주말 — 필요한 블록이 있으면 켠 채 시작, 사용자가 누르면 그 선택을 유지
const night = computed({
  get: () => nightPref.value ?? needsNight(blocks.value),
  set: (v: boolean) => (nightPref.value = v),
})
const weekend = computed({
  get: () => weekendPref.value ?? needsWeekend(blocks.value),
  set: (v: boolean) => (weekendPref.value = v),
})
const range = computed(() => gridRange(blocks.value, night.value))
const rows = computed(() => timeRows(range.value))
const examOn = computed(() => examDates(res.data.value?.exams ?? [], monday.value))
const days = computed(() =>
  Array.from({ length: weekend.value ? 7 : 5 }, (_, i) => {
    const date = addDays(monday.value, i)
    const { placed, overlaps } = layoutDay(blocks.value.filter((b) => b.day === i + 1))
    return {
      day: i + 1,
      date,
      exam: examOn.value.has(date),
      blocks: placed.flatMap((p) => {
        const box = blockBox(p, range.value)
        return box ? [{ p, box }] : []
      }),
      marks: overlaps.flatMap((o) => {
        const box = blockBox(o, range.value)
        return box ? [{ o, box }] : []
      }),
    }
  }),
)
// 빈 격자 자체가 정보 — 격자는 두고 가운데 안내
const empty = computed(
  () => !!res.data.value && !slots.value.length && !blocks.value.some((b) => b.resv),
)

// 저장 뒤 OutboxDot — 블록 우상단 점, 실패면 블록에 danger 2px 테두리 (취소는 테두리 없음)
const tracker = useOutboxTracker()
function saved(s: SavedRow) {
  if (room.value) tracker.track(s.key, room.value.building_id, s.outboxIds)
  void res.reload()
}
function resync(key: string) {
  if (room.value) void tracker.resync(key, room.value.id, room.value.building_id)
}
const dotOf = (p: Placed) =>
  p.resv ? resvDot(p.resv, tracker.states.get(p.key), today) : tracker.states.get(p.key)
function blockClass(p: Placed) {
  const requested = p.resv?.status === 'requested'
  const cancelled = p.slot?.type === 3
  return {
    'wk__block--busy': !requested && !cancelled,
    'wk__block--cancelled': cancelled,
    'wk__block--requested': requested,
    'wk__block--failed': dotOf(p) === 'failed',
  }
}
// 라벨이 상태를 말한다 — 넷(수업·시험·특강·대여)을 색으로 나누지 않는다
function blockLabel(p: Placed) {
  if (p.slot) return TYPE_LABEL[p.slot.type]
  return `${p.resv!.status === 'requested' ? '신청' : '예약'} · ${TYPE_LABEL[p.resv!.type]}`
}
const who = (p: Placed) =>
  p.slot ? p.slot.professor : (p.resv!.requester?.name ?? p.resv!.professor)

// ---- 편집 — 페이지1과 같은 폼. 드래그로 만들지 않는다 (값은 숫자로) ----
const slotOpen = ref(false)
const slotEditing = ref<SlotWithRoom | null>(null)
const slotPreset = ref<{ room_id: number; day?: number; s_h?: number; s_m?: number } | null>(null)
function openSlot(s: SlotWithRoom | null, at?: { day: number; t: number }) {
  if (!room.value) return
  slotEditing.value = s
  slotPreset.value = at
    ? { room_id: room.value.id, day: at.day, s_h: Math.floor(at.t / 60), s_m: at.t % 60 }
    : { room_id: room.value.id }
  slotOpen.value = true
}
const resvOpen = ref(false)
const resvEditing = ref<ResvWithRoom | null>(null)
function openBlock(p: Placed) {
  if (p.slot) openSlot(p.slot)
  else if (p.resv?.status === 'approved') {
    resvEditing.value = p.resv
    resvOpen.value = true
  } // 신청은 강의실 설정의 신청 대기에서 승인·거절한다
}
const removing = ref<SlotWithRoom | null>(null)
const removingBusy = ref(false)
function askRemove() {
  removing.value = slotEditing.value
  slotOpen.value = false
}
async function remove() {
  const s = removing.value
  if (!s || removingBusy.value) return
  removingBusy.value = true
  try {
    await roomsApi.deleteSlot(s.room_id, s)
    showToast({ message: '지웠습니다.' })
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status !== 401 && e.status !== 403) showToast({ tone: 'danger', message: e.message })
  } finally {
    removingBusy.value = false
    removing.value = null
    void res.reload()
  }
}
function pickRoom(ids: number[]) {
  if (ids[0] !== undefined) void router.push(`/rooms/${ids[0]}/week`)
}
function toRooms() {
  if (id.value !== null) picked.value = [id.value]
  void router.push('/rooms')
}
</script>

<template>
  <main class="wk">
    <header class="wk__bar">
      <!-- 버튼 라벨이 곧 현재 강의실 — 화면 제목을 겸한다 (h1 을 따로 두지 않는다) -->
      <RoomTree
        mode="single"
        :buildings="master.data.value?.buildings ?? []"
        :rooms="master.data.value?.rooms ?? []"
        :selected="id === null ? [] : [id]"
        @update:selected="pickRoom"
      />
      <div class="wk__nav">
        <Button variant="ghost" size="sm" aria-label="이전 주" @click="shiftWeek(-1)">◀</Button>
        <span class="wk__range num">{{ md(monday) }}~{{ md(sunday) }}</span>
        <Button variant="ghost" size="sm" aria-label="다음 주" @click="shiftWeek(1)">▶</Button>
      </div>
      <Checkbox v-model="night" label="야간" />
      <Checkbox v-model="weekend" label="주말" />
      <Button class="wk__add" :disabled="!room" @click="openSlot(null)">+ 슬롯 추가</Button>
    </header>
    <div class="wk__legend">
      <Badge tone="busy">사용중</Badge>
      <span>수업·시험·특강·대여는 라벨로 구분</span>
      <Badge variant="outline">휴강</Badge>
      <span class="wk__legend-item"><OutboxDot state="acked" /> 완료</span>
      <span class="wk__legend-item"><OutboxDot state="queued" /> 대기</span>
    </div>
    <EmptyState
      v-if="notFound"
      message="강의실을 찾을 수 없습니다. 위에서 다른 강의실을 고르세요."
    />
    <EmptyState
      v-else-if="noRooms"
      message="강의실이 없습니다. 건물 · 강의실 화면에서 먼저 만드세요."
      :actions="[{ label: '건물 · 강의실로', variant: 'primary', onClick: () => router.push('/master') }]"
    />
    <div v-else class="wk__scroll">
      <div class="wk__grid" :style="{ '--cols': days.length }">
        <div class="wk__corner" />
        <div v-for="d in days" :key="d.date" class="wk__head">
          <span
            >{{ DAYS[d.day - 1] }} <span class="num">{{ md(d.date) }}</span></span
          >
          <!-- 시험기간은 요일 헤더 아래 얇은 띠 — 셀은 건드리지 않는다 -->
          <span v-if="d.exam" class="wk__exam">시험기간</span>
        </div>
        <div class="wk__times">
          <div v-for="t in rows" :key="t" class="wk__time num">{{ clock(t) }}</div>
        </div>
        <div
          v-for="d in days"
          :key="`c${d.date}`"
          class="wk__col"
          :style="{ height: `${rows.length * ROW_PX}px` }"
        >
          <button
            v-for="t in rows"
            :key="t"
            type="button"
            class="wk__cell"
            :disabled="!room"
            :aria-label="`${DAYS[d.day - 1]} ${clock(t)} 슬롯 추가`"
            @click="openSlot(null, { day: d.day, t })"
          />
          <div
            v-for="{ p, box } in d.blocks"
            :key="p.key"
            class="wk__block"
            :class="blockClass(p)"
            :style="{
              top: `${box.top}px`,
              height: `${box.height}px`,
              left: `calc(${(p.lane / p.lanes) * 100}% + 4px)`,
              width: `calc(${100 / p.lanes}% - 8px)`,
            }"
            :role="p.resv?.status === 'requested' ? undefined : 'button'"
            :tabindex="p.resv?.status === 'requested' ? undefined : 0"
            :title="
              p.resv?.status === 'requested' ? '신청 대기 — 강의실 설정에서 승인·거절' : undefined
            "
            @click="openBlock(p)"
            @keydown.enter="openBlock(p)"
          >
            <span class="wk__label">{{ blockLabel(p) }}</span>
            <!-- 높이가 모자라면 교수부터 지운다 -->
            <span v-if="box.height >= 40" class="wk__subject">{{
              p.slot?.subject ?? p.resv?.subject
            }}</span>
            <span v-if="box.height >= 80 && who(p)" class="wk__who">{{ who(p) }}</span>
            <span v-if="box.cutEnd" class="wk__cut num">~{{ clock(p.e) }}</span>
            <span class="wk__dot" @click.stop
              ><RowDot :state="dotOf(p)" @resync="resync(p.key)"
            /></span>
          </div>
          <div
            v-for="({ o, box }, i) in d.marks"
            :key="`m${i}`"
            class="wk__overlap"
            :style="{
              top: `${box.top}px`,
              height: `${box.height}px`,
              left: `calc(${(o.lane / o.lanes) * 100}% - 1.5px)`,
            }"
          >
            <span class="wk__overlap-label num">겹침 {{ clock(o.s) }}–{{ clock(o.e) }}</span>
          </div>
        </div>
        <div v-if="res.loading.value && !res.data.value" class="wk__overlay">
          <Skeleton variant="block" width="60%" />
        </div>
        <div v-else-if="empty" class="wk__overlay">
          <EmptyState
            message="이 강의실에 등록된 시간표가 없습니다"
            :actions="[
              { label: '슬롯 추가', variant: 'primary', onClick: () => openSlot(null) },
              { label: '페이지1에서 CSV 가져오기', onClick: toRooms },
            ]"
          />
        </div>
      </div>
    </div>
    <SlotForm
      :open="slotOpen"
      :mode="slotEditing ? 'edit' : 'create'"
      :rooms="room ? [room] : []"
      :value="slotEditing"
      :preset="slotPreset"
      :existing="slots"
      removable
      @close="slotOpen = false"
      @saved="saved"
      @stale="res.reload"
      @remove="askRemove"
    />
    <ResvForm
      :open="resvOpen"
      mode="edit"
      :rooms="room ? [room] : []"
      :value="resvEditing"
      :existing="resv"
      @close="resvOpen = false"
      @saved="saved"
      @stale="res.reload"
    />
    <ConfirmModal
      :open="!!removing"
      title="슬롯 삭제"
      :lines="
        removing && room
          ? [
              `${room.room}호 ${DAYS[removing.day - 1]} ${hm(removing.s_h, removing.s_m)} ${removing.subject}`,
            ]
          : []
      "
      :loading="removingBusy"
      @confirm="remove"
      @close="removing = null"
    />
  </main>
</template>

<style scoped>
.wk {
  padding: 0 var(--space-5) var(--space-5);
}
.wk__bar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-4) 0 var(--space-2);
  background: var(--bg);
}
.wk__nav {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}
.wk__range {
  font-weight: var(--font-weight-bold);
}
.wk__add {
  margin-left: auto;
}
.wk__legend {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding-bottom: var(--space-3);
  font-size: var(--font-size-xs);
  color: var(--text-2);
}
.wk__legend-item {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
}
/* 격자 컨테이너 line.2 1px + radius.lg, 세로 스크롤 — 요일 헤더와 시각 열은 붙어 있다 */
.wk__scroll {
  max-height: calc(100vh - 150px);
  overflow: auto;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.wk__grid {
  position: relative;
  display: grid;
  grid-template-columns: 56px repeat(var(--cols), minmax(0, 1fr));
}
.wk__corner,
.wk__head {
  position: sticky;
  top: 0;
  z-index: 3;
  border-bottom: var(--border-thin) solid var(--line-2);
  background: var(--surface);
}
.wk__corner {
  left: 0;
  z-index: 4;
}
.wk__head {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 44px;
  padding: var(--space-1) var(--space-2);
  border-left: var(--border-thin) solid var(--line-1);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
}
.wk__exam {
  align-self: flex-start;
  margin-top: 2px;
  padding: 0 var(--space-1);
  border-radius: var(--radius-sm);
  background: var(--room-busy-fill);
  color: var(--room-busy-label);
  font-size: var(--font-size-xs);
}
.wk__times {
  position: sticky;
  left: 0;
  z-index: 2;
  background: var(--surface);
}
.wk__time {
  height: 44px;
  padding: 2px var(--space-2);
  border-bottom: var(--border-thin) solid var(--line-1);
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
/* 열 구분선은 line.1 (설계 판정 — gray.50 의 2층 토큰이 없다) */
.wk__col {
  position: relative;
  border-left: var(--border-thin) solid var(--line-1);
}
.wk__cell {
  display: block;
  width: 100%;
  height: 44px;
  border: 0;
  border-bottom: var(--border-thin) solid var(--line-1);
  background: transparent;
  cursor: pointer;
}
.wk__cell:hover:enabled {
  background: var(--sunken);
}
.wk__block {
  position: absolute;
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow: hidden;
  padding: var(--space-1) var(--space-2);
  border: var(--border-thin) solid transparent;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  cursor: pointer;
}
.wk__block--busy {
  border-color: var(--room-busy-line);
  background: var(--room-busy-fill);
}
.wk__block--busy .wk__label {
  color: var(--room-busy-label);
}
.wk__block--cancelled {
  border: var(--border-thin) dashed var(--room-free-line);
  background: var(--surface);
  color: var(--room-free-text);
}
.wk__block--cancelled .wk__subject {
  text-decoration: line-through;
}
/* 신청(승인 대기) — 아무것도 점유하지 않았다: 바탕 없이 2px 점선 + text.3 */
.wk__block--requested {
  border: var(--border-thick) dashed var(--line-3);
  background: var(--surface);
  color: var(--text-3);
  cursor: default;
}
.wk__block--failed {
  border: var(--border-thick) solid var(--danger);
}
.wk__label {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
}
.wk__subject {
  overflow: hidden;
  font-weight: var(--font-weight-medium);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wk__who {
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.wk__cut {
  margin-top: auto;
  font-size: var(--font-size-xs);
}
.wk__dot {
  position: absolute;
  top: var(--space-1);
  right: var(--space-1);
}
/* 겹침 — 두 블록 사이 겹친 구간에만 danger 3px 막대 하나 + 라벨 하나 */
.wk__overlap {
  position: absolute;
  z-index: 1;
  width: 3px;
  background: var(--danger);
  pointer-events: none;
}
.wk__overlap-label {
  position: absolute;
  top: 0;
  left: 6px;
  padding: 0 var(--space-1);
  background: var(--surface);
  color: var(--danger);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  white-space: nowrap;
}
.wk__overlay {
  position: absolute;
  inset: 44px 0 0 56px;
  display: grid;
  place-items: center;
  pointer-events: none;
}
.wk__overlay > * {
  pointer-events: auto;
  border-radius: var(--radius-lg);
  background: var(--surface);
}
</style>
```

`web/src/admin/router.ts` 의 `children` 에서 `{ path: 'rooms', … }` 줄 **아래**에 추가
```ts
      { path: 'week', component: () => import('./views/WeekView.vue') },
      {
        path: 'rooms/:roomId(\\d+)/week',
        component: () => import('./views/WeekView.vue'),
        props: true,
      },
```

`web/src/admin/AdminShell.vue`
- import 에 `import { weekRoom } from './selection'` 을 더한다.
- `nav` 에서 `{ to: '/rooms', label: '강의실 설정' },` 줄 **아래**에 추가:
```ts
  // 메뉴 항목에 :roomId 를 둘 수 없다 — 마지막으로 본 강의실, 없으면 /week 가 골라 준다
  { to: weekRoom.value === null ? '/week' : `/rooms/${weekRoom.value}/week`, label: '주간 시간표' },
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint && pnpm exec prettier --check .`
Expected: PASS

- [ ] **Step 5: E2E**

`web/e2e/admin-ops.spec.ts`
- 파일 맨 위 import 들 **아래**에 추가 (e2e 는 node 타입 — `page.evaluate` 콜백은 브라우저에서 돈다):
```ts
declare const window: {
  history: { pushState(state: unknown, title: string, url: string): void }
  dispatchEvent(e: unknown): void
}
declare const PopStateEvent: new (type: string) => unknown
```
- helpers import 에 `cfg` 는 이미 있다. 파일 끝에 추가:
```ts
// ---- 주간 시간표 ----
test('주간 시간표 — 호수를 누르면 그 강의실의 한 주, 19시 수업이 있으면 야간 켠 채, 예약이 슬롯과 겹치면 그 구간만 표시', async () => {
  const tomorrow = kstDate(1)
  const dow = ((new Date(`${tomorrow}T00:00:00Z`).getUTCDay() + 6) % 7) + 1
  const headers = { authorization: `Bearer ${await apiLogin(api, cfg.ADMINS[0])}` }
  const room = ops.roomIds[102]
  const put = (data: object) => api.put(`/api/rooms/${room}/slots`, { headers, data })
  const base = { day: dow, s_m: 0, type: 1, professor: '최교수', source: 2 }
  expect((await put({ ...base, s_h: 10, e_h: 12, e_m: 0, subject: '운영체제' })).status()).toBe(200)
  expect((await put({ ...base, s_h: 19, e_h: 20, e_m: 30, subject: '야간수업' })).status()).toBe(200)
  const r = await api.post(`/api/rooms/${room}/reservations`, {
    headers,
    data: { date: tomorrow, s_h: 11, s_m: 0, e_h: 12, e_m: 0, type: 5, subject: '초청강연', professor: '학생처' },
  })
  expect(r.status()).toBe(200)
  // API 로 넣은 것은 화면을 다시 열어야 보인다
  await page.getByRole('link', { name: '건물 · 강의실' }).click()
  await page.getByRole('link', { name: '강의실 설정' }).click()
  await page.getByRole('region', { name: '시간표' }).getByRole('link', { name: '102' }).first().click()
  await expect(page).toHaveURL(new RegExp(`/admin/rooms/${room}/week$`))
  await expect(page.locator('.tree__trigger')).toContainText(`${OPS.building} 102호`)
  await expect(page.getByRole('link', { name: '주간 시간표' })).toHaveAttribute('aria-current', 'page')
  // 오늘이 일요일이면 내일(월)은 다음 주 — 그 주로 옮겨 본다 (주 이동은 서버를 다시 부르지 않는다)
  if (dow === 1) await page.getByRole('button', { name: '다음 주' }).click()
  await expect(page.getByLabel('야간')).toBeChecked()
  await expect(page.locator('.wk__block').filter({ hasText: '운영체제' })).toContainText('수업중')
  await expect(page.locator('.wk__block').filter({ hasText: '초청강연' })).toContainText('예약 · 특강')
  await expect(page.locator('.wk__overlap-label')).toHaveText('겹침 11:00–12:00')
  await shot(page, 'admin-week-1440')
})

test('빈 칸을 누르면 그 자리로 슬롯 추가, 주를 옮기고 강의실을 바꿔도 보고 있는 주는 유지', async () => {
  await page.getByRole('button', { name: '수 14:00 슬롯 추가', exact: true }).click()
  const d = page.getByRole('dialog', { name: '슬롯 추가' })
  await expect(d.getByLabel('시작')).toHaveValue('14:00')
  await expect(d.getByLabel('종료')).toHaveValue('15:00')
  await d.getByLabel('과목명').fill('자료구조')
  await d.getByRole('button', { name: '저장' }).click()
  await expect(d).toHaveCount(0)
  await expect(page.locator('.wk__block').filter({ hasText: '자료구조' })).toBeVisible()
  const range = page.locator('.wk__range')
  const before = await range.textContent()
  await page.getByRole('button', { name: '다음 주' }).click()
  await expect(range).not.toHaveText(before!)
  await expect(page.locator('.wk__block').filter({ hasText: '자료구조' })).toBeVisible()
  const after = await range.textContent()
  await page.locator('.tree__trigger').click()
  await page.getByRole('group', { name: '강의실 선택' }).getByRole('button', { name: '101호' }).click()
  await expect(page).toHaveURL(new RegExp(`/admin/rooms/${ops.roomIds[101]}/week$`))
  await expect(range).toHaveText(after!)
})

test('다른 학교 관리자 — 우리 강의실 주간 주소는 "찾을 수 없습니다" (404 를 없음으로)', async () => {
  await otherPage.getByRole('link', { name: '주간 시간표' }).click()
  await expect(otherPage.getByText('강의실이 없습니다. 건물 · 강의실 화면에서 먼저 만드세요.')).toBeVisible()
  // 새로고침 없이 주소만 바꾼다 — page.goto 는 메모리 세션을 잃는다
  await otherPage.evaluate((id) => {
    window.history.pushState({}, '', `/admin/rooms/${id}/week`)
    window.dispatchEvent(new PopStateEvent('popstate'))
  }, ops.roomIds[101])
  await expect(
    otherPage.getByText('강의실을 찾을 수 없습니다. 위에서 다른 강의실을 고르세요.'),
  ).toBeVisible()
  await shot(otherPage, 'admin-week-notfound-1440')
})
```

`web/e2e/admin-shell.spec.ts` 첫 테스트의 메뉴 기대값을 바꾼다 (최종 여섯)
```ts
  await expect(page.locator('nav a')).toHaveText([
    /^건물 · 강의실$/,
    /^강의실 설정$/,
    /^주간 시간표$/,
    /^노드 상태$/,
    /^전송 현황$/,
    /^회원\s*\d+$/,
  ])
```

Run: **E2E 명령**(전체)
Expected: F1·F3 스펙 그대로 + `admin-ops` 17 — 전부 통과. (`monitor.spec.ts` 의 다른 학교 테스트는 이 파일이 만든 다른 학교 건물 `타학교관`(강의실·모뎀 없음) 때문에 바뀌지 않는다 — 노드 0·모뎀 0·전송 0 그대로.)

- [ ] **Step 6: 스크린샷 대조**

`admin-week-1440.png`·`admin-week-notfound-1440.png` 를 `admin-schedule.md` 와 대조:
- 상단: `[운영관 102호 ▾] ◀ M/D~M/D ▶ ☑야간 ☐주말 [+ 슬롯 추가]`. 별도 h1 없음. 범례 줄 `[사용중] 수업·시험·특강·대여는 라벨로 구분 [휴강] ● 완료 ○ 대기`.
- 격자: 열 = 요일(주말 끄면 5열, 1440px 에서 하루 ≈219px), 행 30분 **44px**, 야간이면 09:00~22:00 26행. 요일 헤더와 시각 열 sticky, 헤더 아래 line.2, 행 구분 line.1.
- 블록: 사용중은 room.busy 틴트 + 1px 선 + 적색 라벨(`수업중`) → 과목명 → 교수. 예약은 `예약 · 특강`. 슬롯과 예약이 겹친 날은 두 블록이 반씩, 겹친 11:00–12:00 에만 danger 3px 막대 + `겹침 11:00–12:00` 라벨 하나(블록 테두리는 적색이 아니다). 우상단 점.
- 시험기간이 걸린 날은 헤더 아래 `시험기간` 띠(room.busy).
- 다른 학교: `강의실을 찾을 수 없습니다. 위에서 다른 강의실을 고르세요.`
어긋나면 고치고 다시 찍는다.

- [ ] **Step 7: 커밋**

```bash
git add web/src/admin web/e2e
git commit -m "feat(web): 주간 시간표 — 강의실 하나의 한 주 격자(30분·44px, 야간·주말 자동), 예약·신청·시험기간 겹쳐 보기, 겹친 구간만 막대, 빈 칸·블록 클릭 편집, 주 유지, 404 는 없음으로 + 메뉴 여섯 + E2E"
```

---

### Task 19: 회원 거절 사유 툴팁 (F1 Task 14 이월, 서버 A1)

**선행 조건:** 서버 additive **A1**(`UserOut.reject_reason: str | None`)이 E2E 서버(`E2E_SERVER_DIR`)에 들어 있어야 한다 — 컨트롤러가 통합 워크트리에 A1~A3 을 머지해 둔다. 확인: `grep -n "reject_reason" <E2E_SERVER_DIR>/app/schemas.py` 에 `class UserOut` 안의 줄이 보인다. 없으면 이 Task 를 멈추고 알린다.

**Files:**
- Modify: `web/src/api/types.ts`, `web/src/api/__fixtures__/users.json`, `web/src/admin/views/UsersView.vue`, `web/src/admin/__tests__/users.spec.ts`, `web/src/admin/__tests__/shell.spec.ts`, `web/e2e/admin-users.spec.ts`

**Interfaces:**
- Produces: `UserOut.reject_reason: string | null` — 값은 `status = 'rejected'` 행에만 있다(서버 A1).

- [ ] **Step 1: 실패 테스트**

`web/src/admin/__tests__/users.spec.ts`
- `u()` 기본값 객체의 `approved_at: null,` **아래**에 `reject_reason: null,` 을 더한다.
- `describe('UsersView', …)` 안 끝에 추가:
```ts
  it('거절됨 배지에 사유 툴팁 — 다른 상태에는 없다', async () => {
    api.list.mockResolvedValue([
      u({ email: 'r@wsu.ac.kr', status: 'rejected', reject_reason: '학번이 잘못되었습니다' }),
      u({ email: 'a@wsu.ac.kr', status: 'active' }),
    ])
    const w = await mountView()
    const badges = w.findAll('tbody .badge').filter((b) => ['거절됨', '활성'].includes(b.text()))
    expect(badges.find((b) => b.text() === '거절됨')!.attributes('title')).toBe(
      '학번이 잘못되었습니다',
    )
    expect(badges.find((b) => b.text() === '활성')!.attributes('title')).toBeUndefined()
  })
```
(`mountView` 는 F1 테스트 파일의 것 — 필터 기본값이 `pending_approval` 이어도 목록은 모의 `api.list` 가 돌려준 두 행이다.)

`web/src/admin/__tests__/shell.spec.ts` 의 `user()` 기본값 객체의 `approved_at: null,` **아래**에 `reject_reason: null,` 을 더한다.

`web/src/api/__fixtures__/users.json` 의 두 항목 모두 `"approved_at": …` 줄 **아래**에 `"reject_reason": null` 을 더한다(앞 줄 끝에 쉼표).

그 밖에 `UserOut` 을 만드는 테스트 팩토리가 있으면(`grep -rn "approved_at: null" web/src`) 같은 자리에 `reject_reason: null,` 을 더한다 — typecheck 가 빠진 곳을 알려 준다.

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin/__tests__/users.spec.ts`
Expected: FAIL — `expected undefined to be '학번이 잘못되었습니다'` (그리고 typecheck 는 `reject_reason` 이 `UserOut` 에 없다고 실패)

- [ ] **Step 3: 구현**

`web/src/api/types.ts` 의 `UserOut` 에서 `approved_at: Date | null` 줄 **아래**에 추가
```ts
  /** 서버 A1 — 거절 사유. status = 'rejected' 행에만 값이 있다 */
  reject_reason: string | null
```

`web/src/admin/views/UsersView.vue` 의 `#cell-status` 템플릿을 바꾼다
```vue
      <template #cell-status="{ row }">
        <!-- 거절 사유는 학생에게 메일로 간 그 문장 — 목록을 넓히지 않고 툴팁으로 -->
        <Badge
          :tone="STATUS_BADGE[asUser(row).status].tone"
          :variant="STATUS_BADGE[asUser(row).status].variant"
          :title="
            asUser(row).status === 'rejected' ? (asUser(row).reject_reason ?? undefined) : undefined
          "
          >{{ STATUS_BADGE[asUser(row).status].label }}</Badge
        >
      </template>
```
(`Badge` 는 `inheritAttrs` 기본값이라 `title` 이 루트 `<span>` 에 붙는다.)

- [ ] **Step 4: 통과 + E2E 한 줄**

`web/e2e/admin-users.spec.ts` 의 거절 테스트(`'거절 — 사유 필수, 거절 필터에 거절됨'`) 끝에 추가
```ts
  await expect(row(page, s.email).getByText('거절됨')).toHaveAttribute('title', '학번이 잘못되었습니다')
```

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint` 그리고 **E2E 명령** + ` e2e/admin-users.spec.ts`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add web/src web/e2e
git commit -m "feat(web): 회원 목록 거절됨 배지에 거절 사유 툴팁 (서버 A1)"
```

---

## 자체 점검 결과 (plan 작성 시)

1. **spec 범위 ↔ Task**: §5 admin-master → Task 10·11·12·13 / admin-rooms(트리·시간표·예약·신청 대기·시험기간·CSV·동기화·OutboxDot) → Task 5·9·14·15·16 / admin-schedule → Task 17·18 / §2.2 domain(TypeBadge·SourceBadge·RoomTree·SlotForm·ResvForm·ExamForm) → Task 4~8 (OutboxDot 은 F3 가 만들었다 — Task 3 에서 취소 문구만) / §4.3 OutboxDot 30 s·`scheduled` → Task 9·15 / §4.1 409·422·404 문장 → Task 2 `conflictMessage` + 각 폼 / §8 예외 표(동시 처리 409·연타·7일 창 밖) → Task 6·7·15 / §5 메뉴 순서·기본 라우트 → Task 11·14·18(기본 `/dashboard` 유지) / F1 이월: 거절 사유(Task 19), Button `loadingLabel` 폭(Task 3), Table 44px(Task 3 — 마스터 두 표가 쓴다) / §7.2 E2E·스크린샷 → 화면 Task 11~16·18.
2. **금지 패턴**: "TBD"·"TODO"·"나중에"·"적절한"·"위 테스트"·"Task N 과 같이" 없음. RoomsView 는 Task 15·16 에서 파일 전체를 다시 적었다. 부분 수정은 바꿀 블록 전체와 위치(앞·뒤 줄)를 적었다.
3. **이름 일치**: `roomsApi.*`(Task 1 ↔ 6·7·8·9·11~18 모의 객체), `adminApi.{pendingResv, approveResv, rejectResv, cancelResv}`(Task 1 ↔ 15), `SavedRow`·`slotKey`·`resvKey`·`examKey`·`conflictMessage`·`resvWindow`·`LATER_HINT`(Task 2 ↔ 6·7·8·9·14·15·16·18), `useOutboxTracker().{states, track, resync}`(Task 9 ↔ 14·18), `picked`·`weekRoom`·`weekMonday`·`nightPref`·`weekendPref`(Task 9 ↔ 14·18), `countFor`·`roomDeleteLines`·`roomNodeText`·`rangeProblem`·`rangeRooms`·`UNIT_OPTIONS`(Task 10 ↔ 12·13), `defaultPick`·`roomLabeler`·`resvDot`·`groupExams`·`roomsLabel`(Task 14·15·16 ↔ 18), `weekBlocks`·`layoutDay`·`gridRange`·`timeRows`·`blockBox`·`examDates`·`needsNight`·`needsWeekend`·`ROW_PX`(Task 17 ↔ 18), `OPS`·`seedOps`·`ensureModems`·`kstDate`(Task 11·14 ↔ E2E), 섹션 id `master-bld`·`master-room`·`blk-slots`·`blk-pending`·`blk-resv`·`blk-exams` 와 E2E region 이름(`건물`·`{건물} 강의실`·`시간표`·`신청 대기`·`예약`·`시험기간`) 일치.
4. **Review Focus 고정 테스트**: 1 → Task 11 `모뎀이 바뀌면 대기 건수로 확인…`·`이름만 바꾸면 묻지 않는다` + E2E / 2 → Task 6 `키가 바뀌면…`·`옛 행 지우기 실패…` + Task 14 E2E / 3 → Task 7 `7일 밖이면…` + Task 15 `resvDot`·E2E / 4 → Task 15 `409 — 다른 관리자가 먼저 처리…` + E2E `신청 대기 — …` / 5 → Task 8 `일부 실패…`·`진행 라벨…` + Task 3 Button `loadingLabel` 테스트.

## PR 체크리스트 (F2 완료 시)

- 브랜치 `feature/web-f2` → `main`. **F3 PR 머지 뒤**에 연다(F3 위에 쌓인 브랜치). 서버 S2c·S4b·S10·A1~A3 이 main 에 없으면 draft 로 두고 본문에 "통합 서버 워크트리(`E2E_SERVER_DIR`)로 E2E 확인"을 적는다.
- 제목 `feat(web): F2 관리자 운영 — 건물·강의실, 강의실 설정(시간표·예약·신청 대기·시험기간·CSV), 주간 시간표, 도메인 폼 셋`.
- 본문: `pnpm test`·`pnpm lint`·`pnpm typecheck`·`pnpm build` 결과, `pnpm e2e` 결과(`admin-ops` 17 + F1·F3), 스크린샷 13장(`admin-master-empty`·`-building`·`-room`·`-range`·`admin-master`, `admin-rooms-slots`·`-pending`·`-csv`·`admin-rooms`, `admin-week`·`-notfound`, `admin-shell`, `admin-users-reject`), 위 **설계 판정** 표.
- mh 에 확인 요청(CODEOWNERS `components/ui/`·디자인 QA): Button `loadingLabel` 폭 잡기 방식 · Table `tall` 을 강의실 표(스펙 42px)에 쓴 것 · `미배정` 배지 `danger+outline` · 격자 열 구분선 `line.1` · 마스터 노드 칸 `응답 없음` 문구 · 화면당 brand 버튼 하나 규칙과 페이지1 추가 버튼들 · ExamForm·ResvForm 의 `components.md` 옛 문장(화면 채번·강의실 Checkbox) 정리 · 사이드바 학교 표시에서 `email_domain` 생략.
- cw 에 알림: 서버 additive 후보(급하지 않음) — `SchoolOut.email_domain`(사이드바 표시), 건물 `bld` 소문자 거부·강의실 있는 건물의 `bld` 변경 거부(화면은 이미 막는다), 슬롯 PUT 의 노드 상한 48 검사(CSV 만 한다).
- F3 와 겹치는 곳: `api/types.ts`·`api/admin.ts`(끝에 덧붙임), `AdminShell.vue` `nav`·`router.ts` `children`, `OutboxDot.vue` 취소 문구(Task 3), `e2e/helpers.ts`·`admin-shell.spec.ts`. 머지 순서는 팀장이 정한다.
