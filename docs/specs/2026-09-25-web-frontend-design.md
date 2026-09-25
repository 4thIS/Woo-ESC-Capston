# 웹 프론트엔드 — 관리자 웹·학생 웹 (Vue 3 + TS) — 설계 (spec)

- 생성일시: 2026-09-25
- 상위 문서: `2026-09-09-roadmap-design.md` §5 S4(관리자 웹)·S10(학생 웹). 화면·토큰·컴포넌트의 **원본은 `docs/design/`**(mh) — 이 spec 은 그것을 코드로 옮기는 **구조와 규칙**만 정한다. 서버 계약: `2026-09-23-s4a-auth-design.md`(인증), `2026-09-23-s4b-admin-api-design.md`(관리자 API), `2026-09-23-s10-student-analytics-design.md`(학생·분석).
- 담당: wj @leemonta9482. 영역 `web/` 전체. `src/styles/`·`src/components/ui/` 는 mh 가 CODEOWNERS 로 디자인 일치를 검수한다.
- 구현 단위: 이 spec 하나 → plan 4개(F1~F4, §6). 각 plan 이 PR 하나.

## 0. 배경 · 위치

`web/` 에는 스캐폴드(Vue 3.5·vue-router 4.5·Vite 7·TS 5.9·Vitest·ESLint, `/api`·`/ws` dev 프록시)만 있고 화면은 없다. 디자인 스펙 v2(#41 머지, #46 진행 중)가 토큰 3층·컴포넌트 24종·화면 8종을 확정했고, 서버는 S4a(머지)·S2c·S4b·S10(구현 중)으로 화면이 부를 API 를 갖춰 가고 있다. 이 spec 은 그 둘을 잇는 **웹 코드의 뼈대**다.

## 1. 목표 · 비목표

### 목표
- 관리자 웹(데스크톱 전용)과 학생 웹(모바일 우선)을 **빌드 진입점 2개**로 만들되 토큰·`ui` 컴포넌트·API 계층은 공유한다.
- 디자인 스펙의 값·규칙을 그대로 옮기고, 스펙에서 벗어난 값을 **테스트가 잡게** 한다.
- 서버 오류·세션 만료·네트워크 끊김·경합 같은 **예외 상황을 한 곳(API 계층·컴포저블)에서** 처리해 화면마다 다르게 새지 않게 한다.
- 모든 화면을 **Playwright 로 실제 브라우저에서 확인**한다(E2E + 스크린샷 대조).

### 비목표
- 다크 모드(디자인 v2 범위 밖), 다국어(한국어 고정), 오프라인 캐시·PWA.
- 관리자 웹의 태블릿·모바일 레이아웃(디자인: 데스크톱 전용).
- 상태 관리·데이터 페칭 라이브러리(Pinia·TanStack Query), UI 키트, 날짜 피커·커스텀 드롭다운 라이브러리, 차트 라이브러리.
- 배포 파이프라인(메인Pi 서빙 방식은 cw PR #44 Docker 머지 후 별도).

## 2. 구조

### 2.1 빌드 진입점 2개 (Vite 멀티 페이지)

| 앱 | HTML | 진입 | 라우터 | 셸 |
|---|---|---|---|---|
| 관리자 | `web/admin.html` | `src/admin/main.ts` | `src/admin/router.ts` (`createWebHistory('/admin/')`) | `AdminShell` — SidebarNav 220px + 본문, `min-width: 1024px`(가로 스크롤 허용) |
| 학생 | `web/index.html` | `src/student/main.ts` | `src/student/router.ts` | `StudentShell` — 모바일 우선, `<html data-surface="student">` |

- `vite.config.ts` `build.rollupOptions.input` 에 두 HTML. dev 서버 하나에서 `/`·`/admin/` 둘 다 열린다(dev 서버의 history fallback 을 앱별로: `/admin/*` → `admin.html`).
- 두 앱은 서로의 `views` 를 import 하지 않는다(ESLint `no-restricted-imports` 로 강제). 공유는 `styles`·`components/ui`·`components/chart`·`api`·`lib`·`auth` 만.

### 2.2 폴더

```
web/src/
├── styles/        tokens.css · surface-student.css · base.css · fonts.css   (보호 계층, mh 검수)
├── components/
│   ├── ui/        공용 15종 (Button·Select·Input·Textarea·Checkbox·Table·Badge·Modal·Toast·Banner·EmptyState·Skeleton·SidebarNav·StatTile·Legend)
│   ├── domain/    관리자 전용 (OutboxDot·TypeBadge·SourceBadge·RoomTree·SlotForm·ResvForm·ExamForm·SignalBars·NodeStateBadge)
│   ├── student/   학생 전용 (RoomListRow·FavoriteStar·ReserveSheet·ResvStatusBadge·MyResvCard·WeekGrid) — student-room.md 기준
│   └── chart/     Histogram (SVG 직접)
├── api/           client.ts · types.ts · auth.ts · admin.ts · rooms.ts · lora.ts · student.ts
├── lib/           session.ts · useResource.ts · usePolling.ts · time.ts · draft.ts
├── auth/          AuthShell · LoginView · SignupView · VerifyView · ForgotView · ResetView
├── admin/         main.ts · router.ts · AdminShell.vue · views/
└── student/       main.ts · router.ts · StudentShell.vue · views/
web/e2e/           Playwright 테스트 (§7.2)
```

### 2.3 인증 화면의 배치
- 학생 앱: `/login`·`/signup`·`/verify`·`/forgot`·`/reset` 전부.
- 관리자 앱: `/admin/login`·`/admin/forgot`·`/admin/reset`(관리자 가입 화면 없음 — 계정은 CLI).
- 메일 링크는 `STUDENT_WEB_URL` 기준(`/verify#token=`·`/reset#token=`). 관리자가 재설정 메일을 받으면 학생 앱의 `/reset` 이 열린다 — 재설정 자체는 역할 무관이라 그대로 두고, 완료 문구에 "관리자는 관리자 화면에서 로그인" 링크를 둔다.

## 3. 토큰 · 컴포넌트

### 3.1 토큰 → CSS 변수
- `docs/design/tokens.md` 의 모든 토큰을 `src/styles/tokens.css` 의 `:root` CSS 변수로 옮긴다. 이름 규칙: 점 → 하이픈(`room.busy.fill` → `--room-busy-fill`, `font.size.md` → `--font-size-md`).
- 치수(`font.size.*`·`control.height.*`·`radius.*`·행 높이)는 `:root` 에 **admin 값**, `src/styles/surface-student.css` 의 `[data-surface="student"]` 에 **student 값**. 컴포넌트는 표면을 모른다.
- `space.*`·`border.*`·색은 두 앱 공용(재정의 없음).
- 화면(`admin/views`·`student/views`)은 **1층(원시 팔레트)과 16진 색 리터럴을 쓰지 않는다** — `tokens.guard.spec.ts` 가 views·components 의 `.vue` 에서 `--gray-`·`--blue-`·`--red-`·`--teal-`·`--gold-` 와 `#[0-9a-fA-F]{3,8}` 을 찾으면 실패한다(토큰 파일 자신은 예외).
- 토큰 값은 코드에서 바꾸지 않는다 — 바꾸려면 mh 가 `docs/design/` PR 을 먼저 머지(lockstep).

### 3.2 폰트
- Pretendard Variable 을 `src/assets/fonts/` 에 **한국어 서브셋 woff2** 로 두고 `fonts.css` 의 `@font-face` 로 로드(CDN 금지 — 메인Pi 오프라인 대비). `font-display: swap`. 숫자는 `font-variant-numeric: tabular-nums`.
- 서브셋 범위(KS X 1001 2,350자 + ASCII)와 파일 크기 상한(≤ 400 KB)은 F1 에서 확정하고 mh 에 공유.

### 3.3 컴포넌트 규칙
- `components.md` 의 props·variant·상태를 그대로. 스펙에 없는 variant 를 먼저 만들지 않는다(필요하면 mh 에 요청).
- Select 는 네이티브 `<select>`, 날짜는 네이티브 `<input type="date">`. Modal 은 포커스 트랩·Esc 닫기·미저장 폼일 때 배경 클릭 닫기 금지. Toast 는 우상단 최대 3개, danger 는 자동 해제 없음.
- 위험 동작(삭제·거절·정지·토큰 재발급·units 축소)은 **확인 Modal 안에서만** danger Button 을 노출.
- 학생 전용 6종은 아직 `components.md` 에 없고 `student-room.md` 에만 있다 — F4 에서 그 문서를 기준으로 만들고, mh 에 `components.md` 이관을 요청한다.
- 접근성: 텍스트 대비 4.5:1 이상 값만, 포커스 링 `--focus`, 색만으로 상태를 구분하지 않음(라벨 병기), 학생 터치 타깃 48px 이상.

## 4. API · 인증 · 데이터 계층

### 4.1 `api/client.ts` — 서버 계약의 유일한 출입구
- `request<T>(method, path, body?, opts?)`: `Authorization: Bearer <세션 토큰>`, JSON 직렬화, 응답 파싱.
- **시각 변환 한 곳**: 서버 `*_at`·`finished_at` 등은 naive UTC(`Z` 없음, S4a §3.4). 응답 타입에 표시한 필드만 `new Date(v + 'Z')` 로 바꾼다. 화면은 `lib/time.ts` 의 KST 포맷터(`Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul' })`)로만 표시.
- 오류 → `ApiError{ status, code, message }`. `message` 는 **사람 문장**(서버 원문 노출 금지). 상태별 공통 처리:

| 상태 | 처리 |
|---|---|
| 401 | 세션 폐기 → 로그인 화면으로(`?next=` 현재 경로) + Banner "다시 로그인해 주세요". **작성 중 폼 초안**을 `lib/draft.ts` 가 `sessionStorage` 에 보관했다가 로그인 뒤 같은 화면에서 복원(비밀번호 필드는 저장하지 않음) |
| 403 | 역할 불일치 — 세션 폐기 + danger Banner(정상 흐름에선 로그인 시 사전 차단되므로 버그 취급, 콘솔에 남김) |
| 409 | 화면이 준 문맥 문장(예: "다른 사람이 먼저 바꿨습니다 — 목록을 새로 불러옵니다") + 해당 리소스 재조회 |
| 422 | 필드 오류로 매핑(Input.error), 매핑 못 하면 폼 상단 Banner |
| 429 | "잠시 후 다시 시도하세요" + 해당 버튼 10 s 잠금(서버가 남은 시간을 주지 않음) |
| 503 | "요청이 몰렸습니다" — 멱등한 GET 은 1 s 뒤 1회 자동 재시도, 쓰기는 재시도하지 않고 안내만 |
| 네트워크 오류 | `ApiError{status:0}` — 화면은 이전 데이터 유지 + "마지막 갱신 HH:MM"(§4.3) |

- 응답 타입은 `api/types.ts` 에 **한 번만** 선언(서버 스키마 이름 그대로: `UserOut`, `NodeOut`, `SummaryOut`, `WeekOut` …). 화면에서 응답을 재해석·보정하지 않는다 — 불편하면 서버를 고친다(`web/CLAUDE.md`).

### 4.2 세션 (`lib/session.ts`)
- JWT 는 **메모리에만**(`auth.md` 결정 — localStorage 금지). 새로고침·새 탭은 재로그인. 앱마다 자기 세션(관리자·학생이 섞이지 않음).
- 로그인 응답 `role` 을 앱과 비교: 관리자 앱에 `student` 로그인 → 토큰 버리고 "관리자 계정이 아닙니다", 반대도 같음(`auth.md` 403 사전 차단).
- 로그아웃 API 는 없다 — 토큰 폐기 = 로그아웃. `exp` 가 지나면 다음 요청이 401 → §4.1.
- 라우터 가드: 인증 필요 라우트에 세션이 없으면 `/login?next=`.

### 4.3 컴포저블
- `useResource(fetcher, deps)`: `{ data, error, loading, refreshedAt, reload }`.
  - 새 요청이 나가면 이전 요청의 응답은 **버린다**(요청 번호 비교) — 필터를 빠르게 바꿀 때 늦게 온 옛 응답이 덮지 않게.
  - 오류여도 `data` 는 이전 값 유지. `refreshedAt` 이 5분 이상 지나면 화면이 danger 로 "마지막 갱신" 표시(student-room 규칙, 관리자도 동일).
- `usePolling(fn, ms)`: `document.visibilityState === 'hidden'` 이면 멈추고, 보이면 **즉시 1회** 실행 후 재개. 이전 호출이 끝나지 않았으면 이번 틱은 건너뜀(겹침 금지). 화면 이탈 시 해제.
- 쓰기: 제출 중 버튼 `loading` 으로 **이중 제출 금지**. 성공 후 관련 목록 `reload`.
- OutboxDot: 저장 응답의 `outbox_ids` 를 30 s 동안 `/api/lora/outbox`·건물 outbox 재조회로 추적(`queued → dispatched → acked|failed|cancelled`). `outbox_ids` 가 빈 배열이면 `scheduled`(7일 창 밖, 실패 아님). 새로고침하면 추적이 끊긴다(디자인 문서 합의).

## 5. 화면 (디자인 스펙 → views)

| 화면 스펙 | 앱·라우트 | 주요 API | 새로고침 |
|---|---|---|---|
| auth.md | 학생 `/login` `/signup` `/verify` `/forgot` `/reset`, 관리자 `/admin/login` `/admin/forgot` `/admin/reset` | `/api/auth/*` | 없음. 가입 재전송 60 s 쿨다운 |
| admin-users.md | `/admin/users` | `GET /api/admin/users?status=`, `POST …/{approve,reject,disable,enable}` | 없음 |
| admin-master.md (#46) | `/admin/master` | `/api/buildings`·`/api/rooms` CRUD, `/api/lora/modems`, `/api/admin/nodes` | 없음 |
| admin-rooms.md | `/admin/rooms` | 건물 단위 조회 4개, 방 단위 slots·reservations·exams, `/api/import/slots`, `/api/rooms/{id}/sync`, 신청 대기(`/api/admin/reservations`) | 저장 후 OutboxDot |
| admin-schedule.md | `/admin/rooms/:roomId/week` | 방 단위 slots·reservations·exams | 없음 |
| admin-nodes.md | `/admin/nodes` | `/api/lora/modems`·`/status`·`/pending`·`/time`, `/api/admin/nodes` | 30 s |
| admin-dashboard.md | `/admin/dashboard` | `/api/admin/summary`, `/api/admin/outbox/failed`, `/api/admin/analytics/*` | 60 s |
| student-room.md | 학생 `/:bld`, `/:bld/:room`, `/:bld/:room/week`, `/:bld/:room/reserve`, `/me` | `/api/student/*` | 60 s(숨김 시 정지) |

- 관리자 기본 화면은 `/admin/dashboard`. SidebarNav 순서는 #46 머지본을 따른다(건물·강의실 최상단).
- 학생 첫 화면 `/` 는 학교의 건물 목록(`/api/student/rooms` 에서 파생) → 건물 선택. 즐겨찾기는 `localStorage`(디자인 결정, 서버 저장 없음).

## 6. 구현 순서 (plan 4개)와 선행 조건

| plan | 범위 | 필요한 서버 | 선행 조건 |
|---|---|---|---|
| **F1** 기반·인증·회원 승인 | 두 앱 셸·라우터·가드, styles·폰트, `ui` 15종, api·lib, auth 전 화면, admin-users, Playwright 하네스 | S4a(머지) | 서버 additive **A1** |
| **F2** 관리자 운영 | domain 컴포넌트, admin-master·admin-rooms·admin-schedule·신청 대기 | S2c·S4b·S10 | mh **#46 머지**, 서버 additive **A2** |
| **F3** 모니터링 | admin-nodes, admin-dashboard(Histogram) | S4b·S10 분석 | — |
| **F4** 학생 웹 | student 컴포넌트, student-room 전 화면 | S10 | 서버 additive **A3** |

**서버 additive (웹보다 먼저 — `web/CLAUDE.md` lockstep)** — S10 뒤 서버 PR 하나로:
- **A1** `UserOut.reject_reason: str | None`(관리자 목록에서만 채움 — 학생 `/me` 에는 넣지 않거나 본인 것만).
- **A2** `ResvWithRoom`·관리자 예약 목록에 `status`, `requester{name, student_no}`(없으면 null), `pushed_at` — 관리자 예약 표의 신청자 열과 `예정` 배지(`pushed_at IS NULL`).
- **A3** `WeekOut.busy: [{day, spans:[{from, to, label, type, mine}]}]`(정규 슬롯·approved·**남의 requested**·시험기간을 `room_state` 규칙으로 합친 것), `WeekOut.free: [{date, spans:[{from, to}]}]`(오늘~+7, 운영 시간 안) — 학생 예약 화면은 이것 없이 성립하지 않는다(남의 신청이 빈칸으로 보여 구조적으로 409).

F1 은 A1 만 있으면 끝까지 동작한다. A1 이 늦으면 admin-users 의 거절 사유 표시만 빼고 진행한다(목록은 동작).

## 7. 테스트

### 7.1 Vitest (단위·컴포넌트)
- `api/`: 서버 응답 **픽스처 JSON**(`src/api/__fixtures__/`)으로 파싱·시각 변환·오류 매핑을 검사 — 서버가 필드를 바꾸면 여기가 먼저 실패한다. 픽스처는 서버 테스트가 쓰는 응답 모양에서 가져온다.
- `lib/`: `useResource` 의 늦은 응답 폐기·오류 시 데이터 유지, `usePolling` 의 숨김 정지·겹침 방지·복귀 즉시 실행(가짜 타이머), `time` 의 UTC→KST(자정 경계 포함), `draft` 저장·복원·비밀번호 제외.
- 컴포넌트: props·variant·상태별 렌더와 상호작용(@vue/test-utils). `tokens.guard.spec.ts`(§3.1).

### 7.2 Playwright (E2E — 실제 브라우저)
- `@playwright/test` 를 devDependency 로. `web/e2e/` + `playwright.config.ts`.
- `globalSetup`: 임시 DB 로 메인Pi 서버를 띄운다(`DEBUG=1 MAIL_BACKEND=console JWT_SECRET=…`, `uv run alembic upgrade head` → CLI `create-school`·`create-admin` 시드) + Vite dev 서버. 메일 링크는 서버 stdout(console 백엔드)에서 토큰을 읽는다.
- 흐름(최소): 관리자 로그인 → 회원 승인 / 학생 가입 → verify/open → verify → 승인 대기 403 → 관리자 승인 → 학생 로그인 / 관리자 앱에 학생 로그인 → 거절 / 401 만료 → 재로그인 → 폼 초안 복원 / 429 버튼 잠금 / 관리자 화면 1024px 미만 Banner.
- **화면별 완료 조건**: 관리자 1440×900, 학생 390×844 스크린샷을 찍어 화면 스펙의 수치(치수·간격·상태)와 대조 — 구현자가 확인하고 PR 에 첨부. 시각 회귀 스냅샷(`toHaveScreenshot`)은 폰트 렌더 차이가 OS 마다 달라 CI 기준으로만 켠다(§7.3).
- 날짜 의존 흐름은 서버 시계를 고정할 수 없으므로 "오늘+1" 처럼 상대 날짜로 만든다.

### 7.3 CI
- 지금 CI `web` job: `pnpm test`·`pnpm lint`·`vue-tsc`. 여기에 `pnpm build` 를 추가한다.
- E2E 는 서버(uv)까지 띄워야 해서 CI 편입은 **cw PR #44(Docker Compose) 머지 뒤** — 그 전까지는 로컬 필수(PR 체크리스트에 결과 첨부).

## 8. 예외 상황 (설계 단계 점검)

| 상황 | 대응 |
|---|---|
| 폼 작성 중 토큰 만료(24 h) | 401 → 초안 `sessionStorage` 보관 → 재로그인 후 복원(§4.1) |
| 새로고침 | 메모리 세션이라 재로그인 — `next` 로 원래 화면 복귀 |
| 필터를 빠르게 바꿈 | 늦게 온 옛 응답 폐기(§4.3) |
| 탭을 숨긴 채 방치 | 폴링 정지, 복귀 시 즉시 갱신 |
| 서버 재시작·네트워크 끊김 | 이전 데이터 유지 + 마지막 갱신 시각, 5분 초과 danger |
| 두 관리자가 같은 예약·신청을 동시에 처리 | 서버 409 → 문장 + 재조회 |
| 저장 버튼 연타 | 제출 중 잠금 |
| 학생이 예약 가능한 방이 0개 | 학생 목록 EmptyState + 관리자 master 화면의 `reservable` 경고 Banner(#46) |
| 7일 창 밖 예약 저장 | `outbox_ids` 빈 배열 → `scheduled` 로 표시(실패 아님) |
| 로그인 몰림(503) | GET 1회 재시도, 로그인은 안내 후 수동 재시도 |
| 서버 시각 표기(`Z` 없음) | client 한 곳에서만 UTC 로 해석(§4.1) |
| 관리자 재설정 메일이 학생 도메인 링크 | 학생 앱 `/reset` 이 처리, 완료 후 관리자 로그인 링크(§2.3) |
| 좁은 창에서 관리자 웹 | 가로 스크롤 + 1회 Banner(`localStorage` 기억) |

## 9. 열린 결정
- Pretendard 서브셋 범위·용량(F1 에서 측정 후 mh 와 확정).
- `WeekGrid`(학생)와 관리자 페이지2 격자의 코드 공유 여부 — 겹침 규칙이 달라(관리자 분할·학생 서버 병합) 우선 별도로 만들고 F4 에서 판단.
- 대시보드 "웨이크 수신률"은 서버 분석에 없다(admin-dashboard 미결) — F3 에서 90 s 이내 비율로 대체 표시하고 서버 지표는 후속.
- 배포(빌드 결과를 누가 어떻게 서빙하나)는 #44 머지 뒤 정한다.
