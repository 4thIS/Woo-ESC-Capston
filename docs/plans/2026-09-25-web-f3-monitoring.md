# 웹 F3 — 모니터링 (노드 상태 · 전송 현황) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 관리자 `노드 상태`(`/admin/nodes`, 30 s 폴링)와 `전송 현황`(`/admin/dashboard`, 60 s 폴링, SVG 히스토그램) 화면을 만들고, 두 화면이 쓰는 도메인·차트 컴포넌트와 "마지막 갱신 / 5분 초과 danger" 표시를 더해 Playwright 로 실제 브라우저에서 확인한다.

**Architecture:** F1 의 `api/client.ts`·`useResource`·`usePolling` 위에 올린다. 화면마다 **리소스 하나**(`Promise.all` 로 엔드포인트를 한꺼번에 읽어 한 `refreshedAt`)를 두고 `usePolling` 으로 돌린다 — 겹침·숨김 정지·늦은 응답 폐기·오류 시 데이터 유지는 F1 컴포저블이 이미 진다. 판정(경고·지연 구간·학교 스코프)은 서버가 하고 화면은 배열을 읽어 그린다. E2E 는 무선 트래픽으로만 생기는 행(STATUS·pending·ACK)을 테스트 전용 `sql()` 헬퍼로 E2E DB 에 직접 넣는다.

**Tech Stack:** Vue 3.5 · vue-router 4.5 · Vite 7 · TypeScript 5.9 · Vitest 3 + @vue/test-utils + jsdom · @playwright/test 1.63 · pnpm (새 의존성 없음)

**Spec:** `docs/specs/2026-09-25-web-frontend-design.md` §4.3·§5·§6(F3)·§8·§9 (+ 화면 원본 `docs/design/screens/admin-nodes.md`·`admin-dashboard.md`, `components.md` §OutboxDot·§SignalBars·§NodeStateBadge·§Histogram·§StatTile·§Legend, `tokens.md` §outbox·§chart, `admin-master.md`(#46) 사이드 메뉴 순서)

**브랜치:** `feature/web-f3` ← `feature/web-f1` (워크트리는 컨트롤러가 만든다). 서버 S4b·S10 이 아직 main 에 없으므로 E2E 는 통합 서버 워크트리로 돈다(Task 1).

## Global Constraints

- 작업 위치: `web/` 만. 서버·`docs/design/` 은 읽기만 한다.
- pnpm 만. **새 의존성 없음** — 차트 라이브러리 금지, Histogram 은 SVG 직접.
- 응답 타입은 `src/api/types.ts` 에 **한 번만**, 서버 스키마 이름 그대로(`ModemOut`·`NodeOut`·`PendingOut`·`OutboxOut`·`FailedOut`·`LatencyOut`·`Enqueued`·`TokenOut`). Date 로 바꿀 필드는 `*_DATES` 에 적고 `api/client.ts` 의 `dates` 로만 변환한다.
- 표시는 KST 로만(`lib/time.ts` 의 `formatKst`·`formatHm`·`relativeKo`). 분석 API 의 `from`·`to` 는 **KST 날짜**(`kstDateStr`, Task 3).
- 판정을 화면이 다시 하지 않는다: 노드 경고는 `NodeOut.warnings[]`, 배터리 경고는 펌웨어 LOW_BATT 플래그(`low_batt` 경고) — **mV 임계값을 화면에 두지 않는다**. `unseen` 48 h 도 화면에 적지 않는다.
- 배터리는 V 로만(`3980` → `3.98 V`), 퍼센트 환산 금지. 신호는 `−71 dBm`(U+2212) + 3칸 막대, 색 없음.
- 서버 오류 원문을 화면에 내지 않는다 — 문구는 이 plan 의 한국어 문장 또는 `MESSAGES`.
- `.vue` 의 `<style>`·`<template>` 에 1층 팔레트(`--gray-` 등)·16진 색 금지(F1 `tokens.guard.spec.ts`). `outbox` 색 `gray.400`/`gray.600` 은 같은 값의 2층 `--text-disabled`/`--text-2` 로 쓴다.
- 폴링: 노드 30 s, 대시보드 60 s, 사이드바 대기 건수 60 s(F1) — **각자 자기 `usePolling`**. 화면을 떠나면 해제(`onScopeDispose`), 숨김이면 정지, 복귀 시 즉시 1회(F1). 끊긴 동안 danger Toast 는 **한 번**(오류가 없다가 생길 때만), 이전 데이터는 지우지 않는다.
- "마지막 갱신 HH:MM" 은 `useResource.refreshedAt` 에서 만든다. `now − refreshedAt ≥ 5분` 이면 `danger` + 문구 ` · 갱신이 멈췄습니다`(색만으로 말하지 않는다).
- 사이드 메뉴 순서(#46): `건물 · 강의실` · `강의실 설정` · `주간 시간표` · `노드 상태` · `전송 현황` · `회원`. F3 는 `노드 상태`·`전송 현황` 만 넣는다(앞 셋은 F2). 관리자 기본 라우트는 `/dashboard`(spec §5).
- 커밋: `feat(web): …` / `test(web): …`. **Claude·AI 저작 표기와 `Co-Authored-By` 트레일러 금지.**
- 매 Task 끝에 `cd web && pnpm test && pnpm lint && pnpm typecheck && pnpm exec prettier --check .` 통과. 새 파일은 `pnpm exec prettier --write <파일>` 로 정리하고, CRLF 만 바뀐 파일은 커밋하지 않는다.
- **E2E 명령**(Task 1 부터, PowerShell):
  ```powershell
  cd web
  $env:E2E_SERVER_DIR = 'C:/path/to/server'
  pnpm e2e
  ```
  (통합 서버 워크트리는 `uv sync` 가 끝나 있어야 한다. S4b·S10 이 main 에 머지되면 변수 없이 `pnpm e2e`.)
- 화면 Task 완료 조건: E2E 통과 + 1440×900 스크린샷을 `web/e2e/.shots/` 에 남기고 화면 스펙 수치와 대조(스크린샷은 커밋하지 않는다 — PR 에 첨부).

## Review Focus

테스트가 직접 겨누지 않으면 사람이 가장 먼저 밟을 상황 다섯. 각 줄의 고정 테스트는 담당 Task 에 있다.

1. 전시 중 서버가 죽거나 Wi-Fi 가 끊긴 채 대시보드를 켜 둠 → 숫자·표는 그대로, Toast 는 한 번만, 5분이 지나면 "마지막 갱신" 이 danger + "갱신이 멈췄습니다". — Task 3 `useStale`·`LastRefreshed` 테스트, Task 6 `갱신 실패 — 표를 지우지 않고…` 테스트 + E2E `네트워크가 끊겨도…`
2. 노드 화면을 연 채 다른 메뉴로 이동·탭 숨김 → 폴링이 새지 않는다(떠나면 0회). — Task 6 `30초마다 다시 읽고, 화면을 떠나면 멈춘다`, Task 9 `60초마다…`
3. 전송 이력 0건(설치 첫날·다른 학교) → KPI 는 `—`(0% 아님), 차트 자리 "아직 전송된 작업이 없습니다". — Task 9 `kpis` 단위 테스트 + E2E `다른 학교 관리자…`
4. 한 번도 보고하지 않은 노드(상태 null) → 표 맨 위, 칸은 `—`, `응답 없음` 배지. 첫 조회가 실패하면 "강의실이 없습니다" 로 오독되지 않는다. — Task 6 `sortNodes`·`보고 없는 노드가 먼저…`·`첫 조회 실패…` + E2E
5. 모뎀Pi 토큰 창을 Esc·배경 클릭으로 실수로 닫음 → 닫히지 않는다(토큰은 다시 볼 수 없다), `닫기` 버튼만. — Task 7 `토큰 창은 Esc·배경으로 닫히지 않는다`

## 설계 판정 (디자인 미결·서버와 어긋난 곳)

| 항목 | 판정 | 근거 |
|---|---|---|
| 노드 정렬(`admin-nodes.md` "last_seen 오래된 순, null 먼저" vs 서버 `bld·room·unit`) | **화면에서 정렬**(`sortNodes`, 안정 정렬 — 같은 값이면 서버 순서) | 표시 순서일 뿐 데이터 보정이 아니다. 서버 `/summary` 도 같은 키(`by_seen`)로 정렬한다. 서버 변경을 기다릴 이유가 없다 |
| `unit` 1/2 표시(`admin-nodes.md` 미결 2) | 노드가 2대인 방만 `402-1`·`402-2`, 1대면 `401` | 한 행 = 한 장치(상태·배터리가 장치마다 다르다) |
| 배터리 경고 | `warnings` 에 `low_batt` 가 있을 때만 V 값을 `busy` 틴트 Badge 로 | 펌웨어 LOW_BATT 플래그(<3.5 V)를 서버가 전달. 화면 임계값 없음 |
| 웨이크 수신률(`admin-dashboard.md` 미결 3, spec §9) | 서버에 없음 → `90초 이내 비율` 타일로 대체(디자인 그대로) | 서버 지표는 후속 |
| 대시보드 `건물` Select | **넣지 않는다** | `/analytics/latency` 에 `building_id` 파라미터가 없다(서버 S10 §4.3). 없는 필터를 화면이 흉내 내지 않는다 |
| 기간 Select | `최근 7일`(기본, 시안)·`30일`·`90일` | 서버 상한 90일 |
| `전체 전송 내역 →` 링크(미결 2) | 넣지 않는다 | 갈 화면이 없다 |
| 최근 전송의 강의실 표기 | `E 401 · 시간표`(건물 **코드** + 호수 + 종류) | `OutboxOut` 에 건물 이름이 없다. `/api/buildings` 를 더 부르는 대신 코드로 — 이름이 필요하면 서버 additive(`FailedOut` 처럼 `building`)로 |
| 최근 전송 출처 | `GET /api/lora/outbox?limit=7`(학교 스코프, 모든 상태·종류) | `latency/samples` 는 acked 만이라 `대기`·`실패` 행을 못 그린다 |
| 실패 타일 모수 | `최근 N일 · 모든 작업`, 500건 이상이면 `500+` | `outbox/failed` 는 모든 종류, `latency.n` 은 SLOT·RESV acked 만 — 섞어 비율을 만들면 거짓이다 |
| 모뎀Pi 카드의 건물 이름 | 생략(모뎀 ID 만) | `ModemOut` 에 건물이 없다. 필요하면 서버 additive |
| 사이드바 하단 모뎀 연결 표시 | 이번 범위 밖 | 화면 스펙 본문에 없는 부가 진입점 |
| 회원 대기 배지 → `/api/admin/summary`? (F1 이 F3 로 미룬 결정) | **바꾸지 않는다** — `GET /api/admin/users?status=pending_approval` 유지 | `/summary` 는 요청마다 기대 노드·실패·pending·예약을 전부 계산한다. 배지 하나에 60 s 마다 쓰기엔 무겁고, 대시보드도 `/summary` 를 쓰지 않는다(디자인 미결 5) |
| Histogram 막대 폭(`components.md` 15px vs `admin-dashboard.md` 17px) | 컴포넌트 스펙 **15px** | 공용 컴포넌트는 `components.md` 가 원본. mh 에 확인 요청 |
| 배정 후 `등록 대기` 행 | 즉시 사라지지 않는다(서버가 행을 지우지 않음) → Toast "장치가 다음에 깨어나면 적용됩니다" | 서버 동작 그대로 |
| E2E 의 노드·pending·ACK 데이터 | 테스트 전용 `sql()` 로 E2E SQLite 에 직접 넣는다 | 관리자 REST 로는 만들 수 없는 행(모뎀 트래픽 전용)이다. 가짜 모뎀 WS 로 만들려면 공중 프레임 인코딩까지 흉내 내야 해 E2E 가 서버 파이프라인 테스트가 된다. 건물·방·모뎀은 **실제 REST** 로 만들고, 무선에서만 오는 행만 SQL 로 |

## 파일 지도

```
web/
├── CLAUDE.md                          E2E 절 추가 (E2E_SERVER_DIR, sql() 은 테스트 전용)
├── eslint.config.js                   components/chart 도 한 단어 컴포넌트 이름 허용
├── e2e/
│   ├── env.json                       + OTHER_DOMAIN · OTHER_ADMIN
│   ├── start-server.mjs               E2E_SERVER_DIR · 다른 학교(id 2) 시드
│   ├── helpers.ts                     E2E_SERVER_DIR · serverEnv · sql() · SEED · seedMonitoring()
│   ├── login.spec.ts · admin-shell.spec.ts   기본 라우트 /dashboard 로 기대값 수정 (Task 9)
│   └── monitor.spec.ts                시드 확인 · 노드 상태 · 전송 현황 · 다른 학교 (한 파일 = 로그인 한 번)
└── src/
    ├── api/
    │   ├── types.ts                   + NodeWarning · OutboxState · ModemOut · TokenOut · NodeOut · PendingOut ·
    │   │                                Enqueued · OutboxOut · FailedOut · LatencyBin · LatencyOut · LatencyType · *_DATES
    │   ├── admin.ts                   adminApi.{nodes, failed, latency} · FAILED_LIMIT
    │   ├── lora.ts                    loraApi.{modems, registerModem, rotateToken, pending, provision, broadcastTime, recentOutbox, syncRoom}
    │   └── __fixtures__/              nodes · modems · pending · outbox · failed · latency (.json)
    ├── lib/
    │   ├── time.ts                    + kstDateStr
    │   └── useStale.ts                5분 판정
    ├── components/
    │   ├── domain/                    SignalBars · NodeStateBadge · OutboxDot
    │   └── chart/                     Histogram (SVG)
    └── admin/
        ├── router.ts · AdminShell.vue 라우트·메뉴
        ├── LastRefreshed.vue          "마지막 갱신 HH:MM"
        ├── nodesView.ts               sortNodes · unitsByRoom · roomLabel · volts · versions · buildingOptions · provisionChoices
        ├── dashboardView.ts           PERIODS · RECENT_LIMIT · fmt1 · binLabel · kpis · histogram · recentRows
        └── views/
            ├── NodesView.vue
            ├── nodes/ModemPanel.vue · nodes/PendingPanel.vue
            └── DashboardView.vue
```

## Task 순서와 의존

| Task | 내용 | 의존 |
|---|---|---|
| 1 | E2E 하네스 — `E2E_SERVER_DIR` · 다른 학교 · `sql()` · `seedMonitoring` | — |
| 2 | 응답 타입 · `api/admin` · `api/lora` · 픽스처 | — |
| 3 | `kstDateStr` · `useStale` · `LastRefreshed` | — |
| 4 | domain — SignalBars · NodeStateBadge · OutboxDot | 2 |
| 5 | chart — Histogram | — |
| 6 | 노드 상태 화면 — 헤더 · ESP노드 표 · 30 s · 메뉴 | 1, 2, 3, 4 |
| 7 | 모뎀Pi 블록 — 카드 · 등록 · 토큰 재발급 · 토큰 1회 표시 | 6 |
| 8 | 등록 대기 블록 — 표 · 강의실 배정 | 6 |
| 9 | 전송 현황 화면 — KPI · 분포 · 최근 전송 · 60 s · 기본 라우트 | 1, 2, 3, 4, 5, 6 |

---

### Task 1: E2E 하네스 — `E2E_SERVER_DIR` · 다른 학교 · `sql()` · `seedMonitoring`

**Files:**
- Modify: `web/e2e/start-server.mjs` (전부), `web/e2e/helpers.ts` (전부), `web/e2e/env.json`, `web/CLAUDE.md`
- Create/Test: `web/e2e/monitor.spec.ts`

**Interfaces:**
- Consumes: 서버 `POST /api/lora/modems`, `POST /api/buildings`, `POST /api/rooms`, `GET /api/buildings` (전부 관리자, 학교 스코프), CLI `create-school`·`create-admin`.
- Produces (`e2e/helpers.ts`): `sql(script: string): void` · `SEED: { modem: 'e2e-m1'; offlineModem: 'e2e-m2'; building: '공학관'; bld: 'E'; mac: 'A1B2C3D4E5F6' }` · `seedMonitoring(request: APIRequestContext): Promise<void>`(멱등). 기존 `SIZES`·`PASSWORD`·`nextAdmin`·`uniqEmail`·`shot`·`mailCount`·`mailToken`·`cli`·`apiLogin`·`createStudent`·`fillLogin` 은 이름·동작 그대로.
- Produces (`env.json`): `OTHER_DOMAIN: "other.ac.kr"`, `OTHER_ADMIN: "admin@other.ac.kr"` — 학교 id 2 의 관리자(비밀번호는 `ADMIN_PASSWORD`).
- 시드 결과(뒤 Task 의 E2E 가 기대하는 값):
  - 모뎀 `e2e-m1`(DB `connected=1`, agent `0.4.1`) · `e2e-m2`(끊김, 접속 기록 없음). 허브 메모리에는 둘 다 연결돼 있지 않다 → 시각 브로드캐스트는 `{modems: 0}`.
  - 건물 `공학관`(bld `E`, 모뎀 `e2e-m1`), 방 401(units 1)·402(units 2)·403(units 1).
  - 노드(서버 순서): `401-1` 경고 없음(2분 전, 3980 mV, −71, 41/12/3/2) · `402-1` `unseen,low_batt`(50시간 전, 3420 mV, −95) · `402-2` `unseen`(보고 없음) · `403-1` `low_batt,resync`(10분 전, 3900 mV, −82).
  - pending `A1B2C3D4E5F6`(모뎀 `e2e-m1`, fw 3, 4100 mV, −68).
  - outbox(이 순서로 id 증가): acked SLOT_SET 8·18·25·28 s, acked RESV_SET 12·35·50 s, acked SLOT_SET 95 s, failed SLOT_SET(401), queued RESV_SET(402). → `latency(all)`: n 8, p50 25, p95 50, max 95, within_30s 0.625, within_90s 0.875.

- [ ] **Step 1: 실패 테스트 — 시드 확인**

`web/e2e/monitor.spec.ts`
```ts
import { expect, test, type APIRequestContext, type BrowserContext } from '@playwright/test'
import cfg from './env.json' with { type: 'json' }
import { SEED, SIZES, apiLogin, seedMonitoring } from './helpers'

// 한 파일 = 한 브라우저 컨텍스트·로그인 한 번 — 서버의 IP 당 분당 로그인 30회 상한 (F1 plan Task 13 메모)
test.describe.configure({ mode: 'serial' })
const BASE = 'http://127.0.0.1:5173'
let ctx: BrowserContext
let api: APIRequestContext

test.beforeAll(async ({ browser }) => {
  ctx = await browser.newContext({
    baseURL: BASE,
    locale: 'ko-KR',
    viewport: SIZES.admin,
    permissions: ['clipboard-read', 'clipboard-write'],
  })
  api = ctx.request
  await seedMonitoring(api)
})
test.afterAll(async () => {
  await ctx.close()
})

test('시드 — 노드 4행·경고, 대기 장치 1, 모뎀 2, 지연 표본 8 (두 번 불러도 한 벌)', async () => {
  await seedMonitoring(api)
  const headers = { authorization: `Bearer ${await apiLogin(api, cfg.ADMINS[0])}` }
  const get = async (p: string) => {
    const r = await api.get(p, { headers })
    expect(r.status(), p).toBe(200)
    return r.json()
  }
  const nodes = (await get('/api/admin/nodes')) as { room: number; unit: number; warnings: string[] }[]
  expect(nodes.map((n) => `${n.room}-${n.unit}:${n.warnings.join(',')}`)).toEqual([
    '401-1:',
    '402-1:unseen,low_batt',
    '402-2:unseen',
    '403-1:low_batt,resync',
  ])
  const pending = (await get('/api/lora/pending')) as { mac: string }[]
  expect(pending.map((p) => p.mac)).toEqual([SEED.mac])
  const modems = (await get('/api/lora/modems')) as { modem_id: string; connected: boolean }[]
  expect(modems.map((m) => `${m.modem_id}:${m.connected}`)).toEqual(['e2e-m1:true', 'e2e-m2:false'])
  expect(await get('/api/admin/analytics/latency')).toMatchObject({
    n: 8,
    p50: 25,
    p95: 50,
    max: 95,
    within_30s: 0.625,
    within_90s: 0.875,
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: Global Constraints 의 **E2E 명령** 뒤에 `e2e/monitor.spec.ts` 를 붙여 실행.
Expected: FAIL — `does not provide an export named 'SEED'`(또는 `seedMonitoring is not a function`).

- [ ] **Step 3: 구현**

`web/e2e/env.json` 전체
```json
{
  "JWT_SECRET": "e2e-only-secret-not-for-production-0123456789abcdef",
  "STUDENT_WEB_URL": "http://127.0.0.1:5173",
  "MAIL_BACKEND": "console",
  "DEBUG": "1",
  "PYTHONUNBUFFERED": "1",
  "PYTHONIOENCODING": "utf-8",
  "SCHOOL_DOMAIN": "wsu.ac.kr",
  "ADMIN_PASSWORD": "adminpass1",
  "ADMINS": ["admin1@wsu.ac.kr", "admin2@wsu.ac.kr", "admin3@wsu.ac.kr", "admin4@wsu.ac.kr"],
  "OTHER_DOMAIN": "other.ac.kr",
  "OTHER_ADMIN": "admin@other.ac.kr"
}
```

`web/e2e/start-server.mjs` 전체
```js
// E2E 용 메인Pi 서버 — 매번 빈 DB, CLI 로 학교·관리자 시드, 메일은 콘솔(stdout → e2e/.tmp/server.log)
// 서버 체크아웃: E2E_SERVER_DIR (web/ 기준 상대 또는 절대 경로, 기본 ../server) — web/CLAUDE.md §E2E
import { spawn, spawnSync } from 'node:child_process'
import { createWriteStream, existsSync, mkdirSync, rmSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import cfg from './env.json' with { type: 'json' }

const web = fileURLToPath(new URL('..', import.meta.url))
const serverDir = path.resolve(web, process.env.E2E_SERVER_DIR ?? '../server')
if (!existsSync(path.join(serverDir, 'app', 'main.py'))) {
  console.error(`E2E_SERVER_DIR 가 메인Pi 서버 체크아웃이 아닙니다: ${serverDir}`)
  process.exit(1)
}
const tmp = path.join(web, 'e2e/.tmp')
rmSync(tmp, { recursive: true, force: true })
mkdirSync(tmp, { recursive: true })

const env = {
  ...process.env,
  SERVER_DB: path.join(tmp, 'e2e.db'),
  JWT_SECRET: cfg.JWT_SECRET,
  STUDENT_WEB_URL: cfg.STUDENT_WEB_URL,
  MAIL_BACKEND: cfg.MAIL_BACKEND,
  DEBUG: cfg.DEBUG,
  PYTHONUNBUFFERED: cfg.PYTHONUNBUFFERED,
  PYTHONIOENCODING: cfg.PYTHONIOENCODING,
}
const shell = process.platform === 'win32'

function cli(args, input) {
  const r = spawnSync('uv', ['run', 'python', '-m', 'app.cli', ...args], {
    cwd: serverDir,
    env,
    input,
    encoding: 'utf8',
    shell,
  })
  if (r.status !== 0) {
    console.error(r.stdout, r.stderr)
    process.exit(1)
  }
}

// CLI 가 alembic upgrade head 를 먼저 돈다. 비밀번호는 stdin(비TTY)으로
cli(['create-school', '--name', '우송대', '--net-id', '75', '--email-domain', cfg.SCHOOL_DOMAIN])
cfg.ADMINS.forEach((email, i) =>
  cli(
    ['create-admin', '--school-id', '1', '--email', email, '--name', `관리자${i + 1}`],
    `${cfg.ADMIN_PASSWORD}\n`,
  ),
)
// 다른 학교(id 2) — 학교 스코프·빈 상태 E2E 용 (monitor.spec.ts)
cli(['create-school', '--name', '타학교', '--net-id', '76', '--email-domain', cfg.OTHER_DOMAIN])
cli(
  ['create-admin', '--school-id', '2', '--email', cfg.OTHER_ADMIN, '--name', '타학교관리자'],
  `${cfg.ADMIN_PASSWORD}\n`,
)

const log = createWriteStream(path.join(tmp, 'server.log'))
log.write(`[e2e] server dir ${serverDir}\n`)
const p = spawn(
  'uv',
  ['run', 'uvicorn', '--factory', 'app.main:create_app', '--host', '127.0.0.1', '--port', '8000'],
  { cwd: serverDir, env, shell },
)
p.stdout.pipe(log)
p.stderr.pipe(log)
p.on('exit', (code) => process.exit(code ?? 0))
for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => p.kill())
```

`web/e2e/helpers.ts` 전체
```ts
import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, type APIRequestContext, type Page } from '@playwright/test'
import cfg from './env.json' with { type: 'json' }

const web = fileURLToPath(new URL('..', import.meta.url))
// start-server.mjs 와 같은 규칙 — E2E_SERVER_DIR(web/ 기준 상대 또는 절대), 기본 ../server
const serverDir = path.resolve(web, process.env.E2E_SERVER_DIR ?? '../server')
const logPath = path.join(web, 'e2e/.tmp/server.log')
const shell = process.platform === 'win32'
const serverEnv = () => ({
  ...process.env,
  SERVER_DB: path.join(web, 'e2e/.tmp/e2e.db'),
  JWT_SECRET: cfg.JWT_SECRET,
  STUDENT_WEB_URL: cfg.STUDENT_WEB_URL,
  MAIL_BACKEND: cfg.MAIL_BACKEND,
  DEBUG: cfg.DEBUG,
  PYTHONIOENCODING: cfg.PYTHONIOENCODING,
})

export const SIZES = {
  admin: { width: 1440, height: 900 },
  student: { width: 390, height: 844 },
} as const
export const PASSWORD = cfg.ADMIN_PASSWORD

let rr = 0
/** 로그인 상한(이메일당 분당 5회)을 피하려고 관리자 계정을 돌려 쓴다.
 * IP 당 분당 30회 상한(모두 127.0.0.1)은 돌려 써도 피하지 못한다 — 한 번의 E2E 실행이 1분 안에 30번 넘게 로그인하면 429 */
export const nextAdmin = () => cfg.ADMINS[rr++ % cfg.ADMINS.length]

export const uniqEmail = (prefix: string) =>
  `${prefix}${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}@${cfg.SCHOOL_DOMAIN}`

export async function shot(page: Page, name: string) {
  await page.screenshot({ path: path.join(web, 'e2e/.shots', `${name}.png`), fullPage: true })
}

/** 콘솔 메일 백엔드가 stdout 에 찍은 `to` 앞 메일 중 링크 토큰이 있는 것들 (오래된 것부터).
 * 로그를 `[mail] ` 줄에서 잘라 블록 하나 = 메일 하나로 본다 — 다른 사람 메일로 넘어가지 않는다 */
function tokensFor(to: string): string[] {
  const log = existsSync(logPath) ? readFileSync(logPath, 'utf8') : ''
  return log
    .split(/^(?=\[mail\] )/m)
    .filter((b) => b.startsWith(`[mail] to=${to} `))
    .map((b) => /#token=([A-Za-z0-9_-]+)/.exec(b)?.[1])
    .filter((t): t is string => !!t)
}

/** 메일을 부르기 전에 세어 두고 `mailToken(to, { after })` 로 넘긴다 */
export const mailCount = (to: string) => tokensFor(to).length

/** `to` 앞 토큰 메일이 `after` 통보다 많아지면 마지막 것의 토큰 (메일은 응답 뒤 BackgroundTasks 로 나간다) */
export async function mailToken(to: string, { after = 0 } = {}): Promise<string> {
  let tokens: string[] = []
  await expect
    .poll(() => (tokens = tokensFor(to)).length, { timeout: 5_000 })
    .toBeGreaterThan(after)
  return tokens.at(-1)!
}

/** 이메일별 관리자 토큰 캐시 — IP 당 분당 30회 로그인 상한을 아끼려고 (비밀번호가 기본값일 때만) */
const tokens = new Map<string, string>()

export function cli(args: string[], input?: string) {
  const r = spawnSync('uv', ['run', 'python', '-m', 'app.cli', ...args], {
    cwd: serverDir,
    env: serverEnv(),
    input,
    encoding: 'utf8',
    shell,
  })
  expect(r.status, r.stderr).toBe(0)
  // set-user 는 token_version 을 올린다 — 그 사람의 캐시된 토큰은 이제 401
  const i = args.indexOf('--email')
  if (args[0] === 'set-user' && i >= 0) tokens.delete(args[i + 1])
}

/** **테스트 전용.** 무선 트래픽(STATUS·pending 발견·ACK)으로만 생기는 행을 E2E DB 에 직접 넣는다 —
 * 관리자 REST 로는 만들 수 없다. 스크립트는 stdin 으로 넘긴다(Windows shell 인용 문제 회피). 시각은 SQLite 'now'(UTC) 기준 */
export function sql(script: string) {
  const py = [
    'import os, sqlite3',
    'c = sqlite3.connect(os.environ["SERVER_DB"], timeout=10)',
    `c.executescript(${JSON.stringify(script)})`,
    'c.close()',
  ].join('\n')
  const r = spawnSync('uv', ['run', 'python', '-'], {
    cwd: serverDir,
    env: serverEnv(),
    input: py,
    encoding: 'utf8',
    shell,
  })
  expect(r.status, r.stderr).toBe(0)
}

export async function apiLogin(request: APIRequestContext, email: string, pw = PASSWORD) {
  const hit = pw === PASSWORD ? tokens.get(email) : undefined
  if (hit) return hit
  const r = await request.post('/api/auth/login', { data: { email, password: pw } })
  expect(r.status()).toBe(200)
  const token = (await r.json()).token as string
  if (pw === PASSWORD) tokens.set(email, token)
  return token
}

/** 가입 신청 → 메일 토큰 → verify/open → verify (+ 승인). 화면을 거치지 않는 준비용 */
export async function createStudent(
  request: APIRequestContext,
  opts: { email?: string; name?: string; studentNo?: string; approve?: boolean } = {},
) {
  const email = opts.email ?? uniqEmail('s')
  const studentNo = opts.studentNo ?? `S${Date.now().toString(36)}`
  const after = mailCount(email)
  expect((await request.post('/api/auth/signup', { data: { email } })).status()).toBe(202)
  const token = await mailToken(email, { after })
  expect((await request.post('/api/auth/verify/open', { data: { token } })).ok()).toBe(true)
  const v = await request.post('/api/auth/verify', {
    data: { token, name: opts.name ?? '김민준', student_no: studentNo, password: PASSWORD },
  })
  expect(v.ok()).toBe(true)
  if (opts.approve) {
    const t = await apiLogin(request, nextAdmin())
    const a = await request.post(`/api/admin/users/${encodeURIComponent(email)}/approve`, {
      headers: { authorization: `Bearer ${t}` },
    })
    expect(a.ok()).toBe(true)
  }
  return { email, studentNo, password: PASSWORD }
}

export async function fillLogin(page: Page, email: string, pw = PASSWORD) {
  await page.getByLabel(/웹메일|이메일/).fill(email)
  await page.getByLabel('비밀번호').fill(pw)
  await page.getByRole('button', { name: '로그인' }).click()
}

// ---- F3 모니터링 시드 ----

export const SEED = {
  modem: 'e2e-m1',
  offlineModem: 'e2e-m2',
  building: '공학관',
  bld: 'E',
  mac: 'A1B2C3D4E5F6',
} as const

/** SQLite 시각 식 — 서버 DateTime 과 같은 'YYYY-MM-DD HH:MM:SS' (naive UTC) */
const at = (...mods: string[]) =>
  `strftime('%Y-%m-%d %H:%M:%S', ${['now', ...mods].map((m) => `'${m}'`).join(', ')})`
const acked = (type: string, ago: number, secs: number) =>
  `('e2e-m1', 'E', 401, 1, '${type}', '{}', 5, NULL, 'acked', 1, ${at(`-${ago} minutes`)}, ` +
  `${at(`-${ago} minutes`)}, ${at(`-${ago} minutes`, `+${secs} seconds`)}, NULL)`

const SEED_SQL = `
UPDATE modems SET connected = 1, agent_ver = '0.4.1', modem_fw = '1.2.0', last_seen_at = ${at()}
  WHERE modem_id = 'e2e-m1';
INSERT OR REPLACE INTO terminal_status
  (bld, room, unit, modem_id, mac, fw, batt_mv, rssi, snr, sched_ver, resv_ver, exam_ver, ident_ver,
   layout, clock_stale, low_batt, uptime_h, last_seen_at, last_ack_at, last_status_at, sync_state)
VALUES
  ('E', 401, 1, 'e2e-m1', '0A1B2C3D4E01', 3, 3980, -71, 7.5, 41, 12, 3, 2, 1, 0, 0, 120,
   ${at('-2 minutes')}, ${at('-2 minutes')}, ${at('-2 minutes')}, 'synced'),
  ('E', 402, 1, 'e2e-m1', '0A1B2C3D4E02', 3, 3420, -95, -3.5, 40, 12, 3, 2, 2, 0, 1, 300,
   ${at('-50 hours')}, ${at('-50 hours')}, ${at('-50 hours')}, 'synced'),
  ('E', 403, 1, 'e2e-m1', '0A1B2C3D4E03', 3, 3900, -82, 2.0, 41, 11, 3, 2, 1, 0, 1, 10,
   ${at('-10 minutes')}, NULL, ${at('-10 minutes')}, 'resync');
INSERT OR REPLACE INTO pending_devices (mac, modem_id, fw, batt_mv, rssi, first_seen_at, last_seen_at)
VALUES ('A1B2C3D4E5F6', 'e2e-m1', 3, 4100, -68, ${at('-3 hours')}, ${at('-1 minutes')});
INSERT INTO outbox
  (modem_id, bld, room, unit, type, payload, priority, new_ver, state, attempts,
   created_at, dispatched_at, finished_at, last_error)
VALUES
  ${[
    acked('SLOT_SET', 90, 8),
    acked('SLOT_SET', 85, 18),
    acked('SLOT_SET', 80, 25),
    acked('SLOT_SET', 75, 28),
    acked('RESV_SET', 70, 12),
    acked('RESV_SET', 65, 35),
    acked('RESV_SET', 60, 50),
    acked('SLOT_SET', 55, 95),
  ].join(',\n  ')},
  ('e2e-m1', 'E', 401, 1, 'SLOT_SET', '{}', 5, NULL, 'failed', 5, ${at('-20 minutes')},
   ${at('-20 minutes')}, ${at('-15 minutes')}, 'max_retries'),
  ('e2e-m1', 'E', 402, 1, 'RESV_SET', '{}', 5, NULL, 'queued', 0, ${at('-1 minutes')}, NULL, NULL, NULL);
`

/** 노드·전송 화면용 시드 (멱등 — 건물 E 가 있으면 건너뛴다. 서버는 E2E 실행마다 새 DB).
 * 건물·방·모뎀은 실제 관리자 REST 로, 무선에서만 오는 행만 sql() 로 */
export async function seedMonitoring(request: APIRequestContext) {
  const headers = { authorization: `Bearer ${await apiLogin(request, cfg.ADMINS[0])}` }
  const r = await request.get('/api/buildings', { headers })
  expect(r.status()).toBe(200)
  if (((await r.json()) as { bld: string }[]).some((b) => b.bld === SEED.bld)) return
  for (const modem_id of [SEED.modem, SEED.offlineModem]) {
    const m = await request.post('/api/lora/modems', { headers, data: { modem_id } })
    expect(m.status(), modem_id).toBe(200)
  }
  const b = await request.post('/api/buildings', {
    headers,
    data: { school_id: 1, name: SEED.building, bld: SEED.bld, modem_id: SEED.modem },
  })
  expect(b.status()).toBe(200)
  const building_id = ((await b.json()) as { id: number }).id
  for (const [room, units] of [
    [401, 1],
    [402, 2],
    [403, 1],
  ]) {
    const rr = await request.post('/api/rooms', { headers, data: { building_id, room, units } })
    expect(rr.status(), String(room)).toBe(200)
  }
  sql(SEED_SQL)
}
```

`web/CLAUDE.md` 의 `## 테스트` 절 바로 아래에 추가:
```markdown
## E2E (Playwright)

- `pnpm e2e` — 임시 DB 로 메인Pi 서버(기본 `../server`)와 Vite dev 서버를 띄우고 `e2e/*.spec.ts` 를 돈다. 학교 둘(우송대 id 1 · 타학교 id 2)과 관리자들을 CLI 로 심는다(`e2e/env.json`).
- **다른 서버 체크아웃으로 돌리기**: `E2E_SERVER_DIR` 에 서버 폴더(web/ 기준 상대 또는 절대 경로). 예: 아직 main 에 없는 API 를 가진 통합 워크트리.
  - PowerShell: `$env:E2E_SERVER_DIR = 'C:\path\to\server'; pnpm e2e`
  - bash: `E2E_SERVER_DIR='C:\path\to\server' pnpm e2e` (Windows 에서는 `/c/...` 가 아니라 `C:\...` 로)
- `e2e/helpers.ts` 의 `sql()` 은 **테스트 전용** — 무선 트래픽(STATUS·pending·ACK)으로만 생기는 행을 E2E DB 에 직접 넣는다. 관리자 REST 로 만들 수 있는 것(건물·방·모뎀)은 REST 로 만든다.
- 로그인 상한(IP 당 분당 30회) 때문에 새 spec 파일은 `beforeAll` 에서 컨텍스트·로그인을 한 번만 하고 화면 이동은 사이드 메뉴 클릭으로 한다(`page.goto` 는 새로고침 = 메모리 세션 소실).
```

- [ ] **Step 4: 통과 확인**

Run: **E2E 명령** + ` e2e/monitor.spec.ts`
Expected: `1 passed`. 이어서 **E2E 명령**(전체) — F1 의 17 개 + 1 = `18 passed`(다른 학교가 생겨도 F1 흐름은 영향 없음). `e2e/.tmp/server.log` 첫 줄이 `[e2e] server dir …srv-wt\server`.

- [ ] **Step 5: 커밋**

```bash
git add web/e2e web/CLAUDE.md
git commit -m "test(web): E2E 하네스 — E2E_SERVER_DIR 로 서버 체크아웃 선택, 다른 학교 시드, 무선 행 테스트 전용 sql() 시드"
```

---

### Task 2: 응답 타입 · `api/admin` · `api/lora` · 픽스처

**Files:**
- Modify: `web/src/api/types.ts`
- Create: `web/src/api/admin.ts`, `web/src/api/lora.ts`, `web/src/api/__fixtures__/{nodes,modems,pending,outbox,failed,latency}.json`
- Test: `web/src/api/__tests__/monitor.spec.ts`

**Interfaces:**
- Consumes: `request<T>(method, path, body?, opts?)` (`api/client.ts`, F1).
- Produces (`types.ts`): `NodeWarning = 'unseen'|'low_batt'|'resync'|'clock_stale'` · `OutboxState = 'queued'|'dispatched'|'acked'|'failed'|'cancelled'` · `ModemOut` + `MODEM_DATES` · `TokenOut` · `NodeOut` + `NODE_DATES` · `PendingOut` + `PENDING_DATES` · `Enqueued` · `OutboxOut` + `OUTBOX_DATES` · `FailedOut` · `LatencyBin` · `LatencyOut` · `LatencyType = 'SLOT_SET'|'RESV_SET'|'all'`.
- Produces (`api/admin.ts`): `FAILED_LIMIT = 500` · `adminApi.nodes(): Promise<NodeOut[]>` · `adminApi.failed(days: number): Promise<FailedOut[]>` · `adminApi.latency(q: { from: string; to: string; type: LatencyType }): Promise<LatencyOut>`.
- Produces (`api/lora.ts`): `loraApi.modems(): Promise<ModemOut[]>` · `registerModem(modemId: string): Promise<TokenOut>` · `rotateToken(modemId: string): Promise<TokenOut>` · `pending(): Promise<PendingOut[]>` · `provision(mac: string, body: { bld: string; room: number; unit: number }): Promise<Enqueued>` · `broadcastTime(): Promise<{ modems: number }>` · `recentOutbox(limit: number): Promise<OutboxOut[]>` · `syncRoom(roomId: number): Promise<Enqueued>`.

- [ ] **Step 1: 픽스처 (서버 응답 모양 그대로)**

`web/src/api/__fixtures__/nodes.json`
```json
[
  {
    "room_id": 11,
    "building_id": 1,
    "building": "공학관",
    "bld": "E",
    "room": 401,
    "unit": 1,
    "modem_id": "gonghak-01",
    "mac": "0A1B2C3D4E01",
    "fw": 3,
    "batt_mv": 3980,
    "rssi": -71,
    "snr": 7.5,
    "sched_ver": 41,
    "resv_ver": 12,
    "exam_ver": 3,
    "ident_ver": 2,
    "layout": 1,
    "clock_stale": false,
    "low_batt": false,
    "uptime_h": 120,
    "last_seen_at": "2026-09-25T00:58:00.123456",
    "last_ack_at": "2026-09-25T00:58:00",
    "last_status_at": "2026-09-24T19:00:00",
    "sync_state": "synced",
    "warnings": []
  },
  {
    "room_id": 12,
    "building_id": 1,
    "building": "공학관",
    "bld": "E",
    "room": 402,
    "unit": 2,
    "modem_id": null,
    "mac": null,
    "fw": null,
    "batt_mv": null,
    "rssi": null,
    "snr": null,
    "sched_ver": null,
    "resv_ver": null,
    "exam_ver": null,
    "ident_ver": null,
    "layout": null,
    "clock_stale": false,
    "low_batt": false,
    "uptime_h": null,
    "last_seen_at": null,
    "last_ack_at": null,
    "last_status_at": null,
    "sync_state": "unknown",
    "warnings": ["unseen"]
  }
]
```
`web/src/api/__fixtures__/modems.json`
```json
[
  {
    "modem_id": "gonghak-01",
    "agent_ver": "0.4.1",
    "modem_fw": "1.2.0",
    "last_seen_at": "2026-09-25T01:00:00.5",
    "connected": true,
    "school_id": 1
  },
  {
    "modem_id": "sahoe-01",
    "agent_ver": null,
    "modem_fw": null,
    "last_seen_at": null,
    "connected": false,
    "school_id": 1
  }
]
```
`web/src/api/__fixtures__/pending.json`
```json
[
  {
    "mac": "A1B2C3D4E5F6",
    "modem_id": "gonghak-01",
    "fw": 3,
    "batt_mv": 4100,
    "rssi": -68,
    "first_seen_at": "2026-09-24T22:00:00",
    "last_seen_at": "2026-09-25T00:59:00"
  }
]
```
`web/src/api/__fixtures__/outbox.json`
```json
[
  {
    "id": 41,
    "modem_id": "gonghak-01",
    "bld": "E",
    "room": 401,
    "unit": 1,
    "type": "SLOT_SET",
    "payload": {},
    "priority": 3,
    "new_ver": 41,
    "state": "acked",
    "attempts": 1,
    "ack_status": 0,
    "ack_detail": null,
    "rssi": -71,
    "snr": 7.5,
    "last_error": null,
    "created_at": "2026-09-25T00:00:00",
    "dispatched_at": "2026-09-25T00:00:02",
    "finished_at": "2026-09-25T00:00:18.4"
  },
  {
    "id": 42,
    "modem_id": "gonghak-01",
    "bld": "E",
    "room": 402,
    "unit": 1,
    "type": "RESV_SET",
    "payload": {},
    "priority": 1,
    "new_ver": 7,
    "state": "queued",
    "attempts": 0,
    "ack_status": null,
    "ack_detail": null,
    "rssi": null,
    "snr": null,
    "last_error": null,
    "created_at": "2026-09-25T00:59:00",
    "dispatched_at": null,
    "finished_at": null
  }
]
```
`web/src/api/__fixtures__/failed.json`
```json
[
  {
    "id": 40,
    "modem_id": "gonghak-01",
    "bld": "E",
    "room": 401,
    "unit": 1,
    "type": "SLOT_SET",
    "payload": {},
    "priority": 3,
    "new_ver": 40,
    "state": "failed",
    "attempts": 5,
    "ack_status": null,
    "ack_detail": null,
    "rssi": null,
    "snr": null,
    "last_error": "max_retries",
    "created_at": "2026-09-24T23:40:00",
    "dispatched_at": "2026-09-24T23:40:01",
    "finished_at": "2026-09-24T23:45:00",
    "room_id": 11,
    "building": "공학관"
  }
]
```
`web/src/api/__fixtures__/latency.json`
```json
{
  "n": 8,
  "bins": [
    { "ge": 0, "lt": 10, "count": 1 },
    { "ge": 10, "lt": 20, "count": 2 },
    { "ge": 20, "lt": 30, "count": 2 },
    { "ge": 30, "lt": 45, "count": 1 },
    { "ge": 45, "lt": 60, "count": 1 },
    { "ge": 60, "lt": 90, "count": 0 },
    { "ge": 90, "lt": 120, "count": 1 },
    { "ge": 120, "lt": null, "count": 0 }
  ],
  "p50": 25.0,
  "p95": 50.0,
  "max": 95.0,
  "within_30s": 0.625,
  "within_90s": 0.875
}
```

- [ ] **Step 2: 실패 테스트**

`web/src/api/__tests__/monitor.spec.ts`
```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { adminApi } from '@/api/admin'
import { loraApi } from '@/api/lora'
import { clearSession } from '@/lib/session'
import nodes from '@/api/__fixtures__/nodes.json'
import modems from '@/api/__fixtures__/modems.json'
import pending from '@/api/__fixtures__/pending.json'
import outbox from '@/api/__fixtures__/outbox.json'
import failed from '@/api/__fixtures__/failed.json'
import latency from '@/api/__fixtures__/latency.json'

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } })
const fetchMock = vi.fn<typeof fetch>()
const call = (i = 0) => ({ url: fetchMock.mock.calls[i][0], init: fetchMock.mock.calls[i][1]! })

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  clearSession()
})

describe('adminApi', () => {
  it('nodes — 시각 필드만 Date, 보고 없는 노드는 null 그대로', async () => {
    fetchMock.mockResolvedValue(json(nodes))
    const out = await adminApi.nodes()
    expect(call().url).toBe('/api/admin/nodes')
    expect(out[0].last_seen_at).toBeInstanceOf(Date)
    expect(out[0].last_seen_at!.toISOString()).toBe('2026-09-25T00:58:00.123Z')
    expect(out[0].last_status_at!.toISOString()).toBe('2026-09-24T19:00:00.000Z')
    expect(out[1].last_seen_at).toBeNull()
    expect(out[1].warnings).toEqual(['unseen'])
  })

  it('failed — days·limit 쿼리, 시각 Date', async () => {
    fetchMock.mockResolvedValue(json(failed))
    const out = await adminApi.failed(7)
    expect(call().url).toBe('/api/admin/outbox/failed?days=7&limit=500')
    expect(out[0].finished_at!.toISOString()).toBe('2026-09-24T23:45:00.000Z')
    expect(out[0].building).toBe('공학관')
  })

  it('latency — KST 날짜 from·to 와 type 쿼리', async () => {
    fetchMock.mockResolvedValue(json(latency))
    const out = await adminApi.latency({ from: '2026-09-19', to: '2026-09-25', type: 'all' })
    expect(call().url).toBe('/api/admin/analytics/latency?from=2026-09-19&to=2026-09-25&type=all')
    expect(out.bins.at(-1)).toEqual({ ge: 120, lt: null, count: 0 })
  })
})

describe('loraApi', () => {
  it('modems — last_seen_at Date, null 그대로', async () => {
    fetchMock.mockResolvedValue(json(modems))
    const out = await loraApi.modems()
    expect(call().url).toBe('/api/lora/modems')
    expect(out[0].last_seen_at!.toISOString()).toBe('2026-09-25T01:00:00.500Z')
    expect(out[1].last_seen_at).toBeNull()
  })

  it('pending — first·last Date', async () => {
    fetchMock.mockResolvedValue(json(pending))
    const out = await loraApi.pending()
    expect(out[0].first_seen_at.toISOString()).toBe('2026-09-24T22:00:00.000Z')
    expect(out[0].last_seen_at.toISOString()).toBe('2026-09-25T00:59:00.000Z')
  })

  it('recentOutbox — limit 쿼리, 끝나지 않은 작업의 finished_at 은 null', async () => {
    fetchMock.mockResolvedValue(json(outbox))
    const out = await loraApi.recentOutbox(7)
    expect(call().url).toBe('/api/lora/outbox?limit=7')
    expect(out[0].finished_at!.toISOString()).toBe('2026-09-25T00:00:18.400Z')
    expect(out[1].finished_at).toBeNull()
  })

  it('registerModem · rotateToken — 본문·경로', async () => {
    fetchMock.mockImplementation(async () => json({ modem_id: 'gonghak-02', token: 't' }))
    await loraApi.registerModem('gonghak-02')
    await loraApi.rotateToken('gonghak-02')
    expect(call(0).url).toBe('/api/lora/modems')
    expect(call(0).init.method).toBe('POST')
    expect(call(0).init.body).toBe('{"modem_id":"gonghak-02"}')
    expect(call(1).url).toBe('/api/lora/modems/gonghak-02/token')
    expect(call(1).init.body).toBeUndefined()
  })

  it('provision · syncRoom · broadcastTime — 경로와 본문', async () => {
    fetchMock.mockImplementation(async () => json({ outbox_ids: [1], id: null, modems: 0 }))
    await loraApi.provision('A1B2C3D4E5F6', { bld: 'E', room: 402, unit: 2 })
    await loraApi.syncRoom(11)
    await loraApi.broadcastTime()
    expect(call(0).url).toBe('/api/lora/pending/A1B2C3D4E5F6/provision')
    expect(call(0).init.body).toBe('{"bld":"E","room":402,"unit":2}')
    expect(call(1).url).toBe('/api/rooms/11/sync')
    expect(call(1).init.body).toBe('{}') // SyncIn 기본값 = 세 종류 전부
    expect(call(2).url).toBe('/api/lora/time')
    expect(call(2).init.method).toBe('POST')
  })
})
```

- [ ] **Step 3: 실패 확인**

Run: `cd web && pnpm test src/api/__tests__/monitor.spec.ts`
Expected: FAIL — `Failed to resolve import "@/api/admin"`

- [ ] **Step 4: 구현**

`web/src/api/types.ts` 끝에 추가
```ts
// ---- F3 모니터링 — S4b(노드·실패), S10 §4.3(지연), lora_service(모뎀·pending·outbox) ----
/** 서버 WARNING_ORDER 와 같은 순서 (S4b §2.1) — 판정은 서버가 한다 */
export type NodeWarning = 'unseen' | 'low_batt' | 'resync' | 'clock_stale'
export type OutboxState = 'queued' | 'dispatched' | 'acked' | 'failed' | 'cancelled'

export interface ModemOut {
  modem_id: string
  agent_ver: string | null
  modem_fw: string | null
  last_seen_at: Date | null
  connected: boolean
  school_id: number | null
}
export const MODEM_DATES = ['last_seen_at'] as const

export interface TokenOut {
  modem_id: string
  token: string
}

export interface NodeOut {
  room_id: number
  building_id: number
  building: string
  bld: string
  room: number
  unit: number
  modem_id: string | null
  mac: string | null
  fw: number | null
  batt_mv: number | null
  rssi: number | null
  snr: number | null
  sched_ver: number | null
  resv_ver: number | null
  exam_ver: number | null
  ident_ver: number | null
  layout: number | null
  clock_stale: boolean
  low_batt: boolean
  uptime_h: number | null
  last_seen_at: Date | null
  last_ack_at: Date | null
  last_status_at: Date | null
  sync_state: string
  warnings: NodeWarning[]
}
export const NODE_DATES = ['last_seen_at', 'last_ack_at', 'last_status_at'] as const

export interface PendingOut {
  mac: string
  modem_id: string | null
  fw: number | null
  batt_mv: number | null
  rssi: number | null
  first_seen_at: Date
  last_seen_at: Date
}
export const PENDING_DATES = ['first_seen_at', 'last_seen_at'] as const

export interface Enqueued {
  outbox_ids: number[]
  id: number | null
}

export interface OutboxOut {
  id: number
  modem_id: string | null
  bld: string
  room: number
  unit: number
  type: string
  payload: Record<string, unknown>
  priority: number
  new_ver: number | null
  state: OutboxState
  attempts: number
  ack_status: number | null
  ack_detail: number | null
  rssi: number | null
  snr: number | null
  last_error: string | null
  created_at: Date
  dispatched_at: Date | null
  finished_at: Date | null
}
export const OUTBOX_DATES = ['created_at', 'dispatched_at', 'finished_at'] as const

export interface FailedOut extends OutboxOut {
  room_id: number
  building: string
}

export interface LatencyBin {
  ge: number
  lt: number | null
  count: number
}
export interface LatencyOut {
  n: number
  bins: LatencyBin[]
  p50: number | null
  p95: number | null
  max: number | null
  within_30s: number
  within_90s: number
}
export type LatencyType = 'SLOT_SET' | 'RESV_SET' | 'all'
```

`web/src/api/admin.ts`
```ts
import { request } from './client'
import {
  NODE_DATES,
  OUTBOX_DATES,
  type FailedOut,
  type LatencyOut,
  type LatencyType,
  type NodeOut,
} from './types'

/** 실패 목록 한 번에 받는 상한 (서버 le=500). 이만큼 오면 화면은 "500+" */
export const FAILED_LIMIT = 500

export const adminApi = {
  /** 기대 노드(rooms × units) × 상태 — 경고는 서버 판정 (S4b §2.2) */
  nodes: () => request<NodeOut[]>('GET', '/api/admin/nodes', undefined, { dates: NODE_DATES }),
  failed: (days: number) =>
    request<FailedOut[]>(
      'GET',
      `/api/admin/outbox/failed?days=${days}&limit=${FAILED_LIMIT}`,
      undefined,
      { dates: OUTBOX_DATES },
    ),
  /** from·to 는 KST 날짜(양끝 포함), 90일 이내 (S10 §4.3) */
  latency: (q: { from: string; to: string; type: LatencyType }) =>
    request<LatencyOut>('GET', `/api/admin/analytics/latency?${new URLSearchParams(q)}`),
}
```

`web/src/api/lora.ts`
```ts
import { request } from './client'
import {
  MODEM_DATES,
  OUTBOX_DATES,
  PENDING_DATES,
  type Enqueued,
  type ModemOut,
  type OutboxOut,
  type PendingOut,
  type TokenOut,
} from './types'

export const loraApi = {
  modems: () => request<ModemOut[]>('GET', '/api/lora/modems', undefined, { dates: MODEM_DATES }),
  /** 응답의 token 은 이때 한 번만 받는다 — 서버가 다시 알려주지 않는다 */
  registerModem: (modemId: string) =>
    request<TokenOut>('POST', '/api/lora/modems', { modem_id: modemId }),
  rotateToken: (modemId: string) =>
    request<TokenOut>('POST', `/api/lora/modems/${encodeURIComponent(modemId)}/token`),
  pending: () =>
    request<PendingOut[]>('GET', '/api/lora/pending', undefined, { dates: PENDING_DATES }),
  provision: (mac: string, body: { bld: string; room: number; unit: number }) =>
    request<Enqueued>('POST', `/api/lora/pending/${encodeURIComponent(mac)}/provision`, body),
  /** 서버 전역 10분 1회 — 넘으면 429 */
  broadcastTime: () => request<{ modems: number }>('POST', '/api/lora/time'),
  /** 학교 스코프 최신 limit 건, id 오름차순으로 온다 */
  recentOutbox: (limit: number) =>
    request<OutboxOut[]>('GET', `/api/lora/outbox?limit=${limit}`, undefined, {
      dates: OUTBOX_DATES,
    }),
  /** 재전송은 방 단위 — 본문 {} = SyncIn 기본(schedule·resv·exam 전부) */
  syncRoom: (roomId: number) => request<Enqueued>('POST', `/api/rooms/${roomId}/sync`, {}),
}
```

- [ ] **Step 5: 통과 확인**

Run: `cd web && pnpm test src/api && pnpm typecheck && pnpm lint`
Expected: PASS (monitor.spec 9 tests + F1 client.spec 그대로)

- [ ] **Step 6: 커밋**

```bash
git add web/src/api
git commit -m "feat(web): 모니터링 응답 타입과 adminApi·loraApi — 노드·모뎀·pending·outbox·지연, 시각은 *_DATES 로만 변환"
```

---

### Task 3: `kstDateStr` · `useStale` · `LastRefreshed`

**Files:**
- Modify: `web/src/lib/time.ts`
- Create: `web/src/lib/useStale.ts`, `web/src/admin/LastRefreshed.vue`
- Test: `web/src/lib/__tests__/useStale.spec.ts`, `web/src/admin/__tests__/refreshed.spec.ts`

**Interfaces:**
- Produces: `kstDateStr(d: Date, offsetDays?: number): string` — KST 달력 날짜 `YYYY-MM-DD`.
- Produces: `STALE_MS = 300_000` · `useStale(at: MaybeRefOrGetter<Date | null>, tickMs?: number): { stale: ComputedRef<boolean> }` — `at` 이 null 이면 false.
- Produces: `LastRefreshed.vue` props `{ at: Date | null }` — `at` 이 null 이면 아무것도 그리지 않는다. 루트 `p.refreshed`(`.refreshed--stale` 추가).

- [ ] **Step 1: 실패 테스트**

`web/src/lib/__tests__/useStale.spec.ts`
```ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope, shallowRef } from 'vue'
import { kstDateStr } from '@/lib/time'
import { useStale } from '@/lib/useStale'

afterEach(() => vi.useRealTimers())

describe('kstDateStr', () => {
  it('KST 자정 경계 — UTC 15:00 이 KST 다음 날 00:00', () => {
    expect(kstDateStr(new Date('2026-09-24T14:59:59Z'))).toBe('2026-09-24')
    expect(kstDateStr(new Date('2026-09-24T15:00:00Z'))).toBe('2026-09-25')
  })
  it('offsetDays 로 앞뒤 날짜 (월 경계 포함)', () => {
    expect(kstDateStr(new Date('2026-09-24T16:00:00Z'), -6)).toBe('2026-09-19')
    expect(kstDateStr(new Date('2026-09-24T16:00:00Z'), -29)).toBe('2026-08-27')
  })
})

describe('useStale', () => {
  it('5분이 지나면 stale, 새 갱신이 오면 풀린다', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
    vi.setSystemTime(new Date('2026-09-25T00:00:00Z'))
    const at = shallowRef<Date | null>(new Date())
    const scope = effectScope()
    const { stale } = scope.run(() => useStale(at))!
    expect(stale.value).toBe(false)
    vi.advanceTimersByTime(4 * 60_000 + 59_000) // 마지막 틱 4:45
    expect(stale.value).toBe(false)
    vi.advanceTimersByTime(15_000) // 5:00 틱
    expect(stale.value).toBe(true)
    at.value = new Date()
    expect(stale.value).toBe(false)
    scope.stop()
  })

  it('한 번도 받지 못했으면(null) stale 이 아니다 — 표시 자체가 없다', () => {
    const scope = effectScope()
    const { stale } = scope.run(() => useStale(() => null))!
    expect(stale.value).toBe(false)
    scope.stop()
  })
})
```

`web/src/admin/__tests__/refreshed.spec.ts`
```ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import LastRefreshed from '@/admin/LastRefreshed.vue'

afterEach(() => vi.useRealTimers())

describe('LastRefreshed', () => {
  it('시각이 없으면 그리지 않고, 5분 넘으면 danger 문구, 새로 받으면 풀린다', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
    vi.setSystemTime(new Date('2026-09-25T01:00:00Z'))
    const w = mount(LastRefreshed, { props: { at: null } })
    expect(w.find('.refreshed').exists()).toBe(false)
    await w.setProps({ at: new Date('2026-09-25T00:55:00Z') }) // KST 09:55, 5분 전
    expect(w.get('.refreshed').text()).toBe('마지막 갱신 09:55 · 갱신이 멈췄습니다')
    expect(w.get('.refreshed').classes()).toContain('refreshed--stale')
    expect(w.get('.refreshed').attributes('title')).toBe('2026-09-25 09:55')
    await w.setProps({ at: new Date('2026-09-25T00:59:30Z') })
    expect(w.get('.refreshed').text()).toBe('마지막 갱신 09:59')
    expect(w.get('.refreshed').classes()).not.toContain('refreshed--stale')
    w.unmount()
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/lib/__tests__/useStale.spec.ts src/admin/__tests__/refreshed.spec.ts`
Expected: FAIL — `"kstDateStr" is not exported` / `Failed to resolve import "@/lib/useStale"`

- [ ] **Step 3: 구현**

`web/src/lib/time.ts` — `const kstDay = …` 줄 **바로 아래**에 추가
```ts
/** KST 달력 날짜 'YYYY-MM-DD' (+offsetDays). 분석 API 의 from·to 가 KST 날짜다 (S10 §4.3) */
export function kstDateStr(d: Date, offsetDays = 0): string {
  return new Date((kstDay(d) + offsetDays) * 86_400_000).toISOString().slice(0, 10)
}
```

`web/src/lib/useStale.ts`
```ts
import { computed, onScopeDispose, ref, toValue, type MaybeRefOrGetter } from 'vue'

/** 마지막 갱신이 이만큼 지나면 danger (spec §4.3 — student-room 규칙, 관리자도 같다) */
export const STALE_MS = 5 * 60_000

/** refreshedAt 이 STALE_MS 이상 지났는가. 시계는 tickMs 마다 한 번 본다 — 폴링이 멈춰도(끊김·숨김) 판정은 흐른다 */
export function useStale(at: MaybeRefOrGetter<Date | null>, tickMs = 15_000) {
  const now = ref(Date.now())
  const timer = setInterval(() => (now.value = Date.now()), tickMs)
  onScopeDispose(() => clearInterval(timer))
  const stale = computed(() => {
    const t = toValue(at)
    return !!t && now.value - t.getTime() >= STALE_MS
  })
  return { stale }
}
```

`web/src/admin/LastRefreshed.vue`
```vue
<script setup lang="ts">
import { formatHm, formatKst } from '@/lib/time'
import { useStale } from '@/lib/useStale'

const props = defineProps<{ at: Date | null }>()
const { stale } = useStale(() => props.at)
</script>

<template>
  <!-- 색만으로 말하지 않는다 — 멈췄으면 문장을 붙인다 -->
  <p
    v-if="at"
    class="refreshed num"
    :class="{ 'refreshed--stale': stale }"
    :title="formatKst(at)"
    role="status"
  >
    마지막 갱신 {{ formatHm(at) }}<template v-if="stale"> · 갱신이 멈췄습니다</template>
  </p>
</template>

<style scoped>
.refreshed {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.refreshed--stale {
  color: var(--danger);
  font-weight: var(--font-weight-bold);
}
</style>
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add web/src/lib web/src/admin/LastRefreshed.vue web/src/admin/__tests__/refreshed.spec.ts
git commit -m "feat(web): 마지막 갱신 표시 — refreshedAt 5분 초과 시 danger 문구, KST 날짜 헬퍼"
```

---

### Task 4: domain — SignalBars · NodeStateBadge · OutboxDot

**Files:**
- Create: `web/src/components/domain/SignalBars.vue`, `web/src/components/domain/NodeStateBadge.vue`, `web/src/components/domain/OutboxDot.vue`
- Test: `web/src/components/domain/__tests__/domain.spec.ts`

**Interfaces:**
- Consumes: `Badge`(F1 — 조합 `busy+tint`·`neutral+outline`·`neutral+solid`·`danger+outline`), `NodeWarning`·`OutboxState`(Task 2).
- Produces: `SignalBars` props `{ rssi: number | null }`, 모듈 export `signalLevel(rssi: number): 1 | 2 | 3`.
- Produces: `NodeStateBadge` props `{ warnings?: NodeWarning[] }`, 모듈 export `WARNING_ORDER: NodeWarning[]`, `WARNING_LABEL: Record<NodeWarning, string>`.
- Produces: `OutboxDot` props `{ state: DotState }`, 모듈 export `type DotState = OutboxState | 'scheduled'`, `DOT_LABEL: Record<DotState, string>`.

`components.md` 는 SignalBars·NodeStateBadge 를 `chart/` 절에 적었지만 spec §2.2 와 `admin-nodes.md` 는 `components/domain/` — 서버 필드명(`warnings`)을 아는 컴포넌트라 `domain/` 에 둔다(mh 에 알림).

- [ ] **Step 1: 실패 테스트**

`web/src/components/domain/__tests__/domain.spec.ts`
```ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SignalBars, { signalLevel } from '@/components/domain/SignalBars.vue'
import NodeStateBadge from '@/components/domain/NodeStateBadge.vue'
import OutboxDot from '@/components/domain/OutboxDot.vue'

describe('SignalBars', () => {
  it('칸 수 경계 — ≥ −75 3칸 · ≥ −90 2칸 · 그 아래 1칸', () => {
    expect([-60, -75, -76, -90, -91, -120].map(signalLevel)).toEqual([3, 3, 2, 2, 1, 1])
  })
  it('숫자와 막대를 함께, 색이 아니라 채운 칸 수로', () => {
    const w = mount(SignalBars, { props: { rssi: -88 } })
    expect(w.text()).toBe('−88 dBm')
    expect(w.findAll('.sig__on')).toHaveLength(2)
    expect(w.findAll('.sig__off')).toHaveLength(1)
    expect(w.get('svg').attributes('aria-label')).toBe('신호 3칸 중 2칸')
  })
  it('null 이면 — 만, 막대 없음', () => {
    const w = mount(SignalBars, { props: { rssi: null } })
    expect(w.text()).toBe('—')
    expect(w.find('svg').exists()).toBe(false)
  })
})

describe('NodeStateBadge', () => {
  it('비면 동기화됨(neutral solid)', () => {
    const w = mount(NodeStateBadge, { props: { warnings: [] } })
    expect(w.text()).toBe('동기화됨')
    expect(w.classes()).toEqual(expect.arrayContaining(['badge--neutral', 'badge--solid']))
  })
  it('가장 나쁜 하나만 배지로, 나머지는 title', () => {
    const w = mount(NodeStateBadge, { props: { warnings: ['resync', 'unseen', 'low_batt'] } })
    expect(w.text()).toBe('응답 없음')
    expect(w.classes()).toEqual(expect.arrayContaining(['badge--danger', 'badge--outline']))
    expect(w.attributes('title')).toBe('배터리 · 재동기 중')
  })
  it('배터리는 danger, 재동기·시계는 neutral outline', () => {
    const b = mount(NodeStateBadge, { props: { warnings: ['clock_stale', 'low_batt'] } })
    expect(b.text()).toBe('배터리')
    expect(b.classes()).toContain('badge--danger')
    expect(b.attributes('title')).toBe('시계')
    const r = mount(NodeStateBadge, { props: { warnings: ['resync'] } })
    expect(r.text()).toBe('재동기 중')
    expect(r.classes()).toEqual(expect.arrayContaining(['badge--neutral', 'badge--outline']))
    expect(r.attributes('title')).toBeUndefined()
  })
})

describe('OutboxDot', () => {
  it.each([
    ['queued', '대기'],
    ['dispatched', '전송 중'],
    ['acked', '반영됨'],
    ['failed', '실패'],
    ['cancelled', '취소됨'],
  ] as const)('%s — 점 + 툴팁 %s', (state, label) => {
    const w = mount(OutboxDot, { props: { state } })
    expect(w.classes()).toContain(`dot--${state}`)
    expect(w.attributes('title')).toBe(label)
    expect(w.attributes('aria-label')).toBe(label)
  })
  it('scheduled 는 점이 아니라 예정 배지 — 실패로 그리지 않는다', () => {
    const w = mount(OutboxDot, { props: { state: 'scheduled' } })
    expect(w.text()).toBe('예정')
    expect(w.classes()).toContain('badge--outline')
    expect(w.attributes('title')).toBe('7일 이내로 들어오면 자동 전송됩니다')
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/components/domain`
Expected: FAIL — `Failed to resolve import "@/components/domain/SignalBars.vue"`

- [ ] **Step 3: 구현**

`web/src/components/domain/SignalBars.vue`
```vue
<script lang="ts">
/** 칸 수는 화면이 정한다 (admin-nodes.md) — ≥ −75 3칸 · ≥ −90 2칸 · 그 아래 1칸 */
export function signalLevel(rssi: number): 1 | 2 | 3 {
  return rssi >= -75 ? 3 : rssi >= -90 ? 2 : 1
}
</script>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ rssi: number | null }>()
const level = computed(() => (props.rssi == null ? 0 : signalLevel(props.rssi)))
// 음수 기호는 U+2212 (디자인 표기 −71 dBm)
const text = computed(() =>
  props.rssi == null ? '—' : `${props.rssi < 0 ? '−' : ''}${Math.abs(props.rssi)} dBm`,
)
</script>

<template>
  <span class="sig num">
    <svg
      v-if="rssi != null"
      class="sig__bars"
      width="13"
      height="12"
      viewBox="0 0 13 12"
      role="img"
      :aria-label="`신호 3칸 중 ${level}칸`"
    >
      <rect
        v-for="i in 3"
        :key="i"
        :x="(i - 1) * 5"
        :y="12 - i * 4"
        width="3"
        :height="i * 4"
        :class="i <= level ? 'sig__on' : 'sig__off'"
      />
    </svg>
    {{ text }}
  </span>
</template>

<style scoped>
.sig {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
}
/* 색을 쓰지 않는다 — 채운 칸 수로만 */
.sig__on {
  fill: var(--text-2);
}
.sig__off {
  fill: var(--line-3);
}
</style>
```

`web/src/components/domain/NodeStateBadge.vue`
```vue
<script lang="ts">
import type { NodeWarning } from '@/api/types'

/** 우선순위 unseen > low_batt > resync > clock_stale (admin-nodes.md, 서버 WARNING_ORDER 와 같다) */
export const WARNING_ORDER: NodeWarning[] = ['unseen', 'low_batt', 'resync', 'clock_stale']
export const WARNING_LABEL: Record<NodeWarning, string> = {
  unseen: '응답 없음',
  low_batt: '배터리',
  resync: '재동기 중',
  clock_stale: '시계',
}
</script>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/components/ui/Badge.vue'

// 판정은 서버가 한다 — 받은 배열을 배지 하나로 줄이기만 한다
const props = withDefaults(defineProps<{ warnings?: NodeWarning[] }>(), { warnings: () => [] })
const present = computed(() => WARNING_ORDER.filter((w) => props.warnings.includes(w)))
const worst = computed(() => present.value[0])
const rest = computed(
  () =>
    present.value
      .slice(1)
      .map((w) => WARNING_LABEL[w])
      .join(' · ') || undefined,
)
const danger = computed(() => worst.value === 'unseen' || worst.value === 'low_batt')
</script>

<template>
  <Badge v-if="!worst" variant="solid">동기화됨</Badge>
  <Badge v-else variant="outline" :tone="danger ? 'danger' : 'neutral'" :title="rest">{{
    WARNING_LABEL[worst]
  }}</Badge>
</template>
```

`web/src/components/domain/OutboxDot.vue`
```vue
<script lang="ts">
import type { OutboxState } from '@/api/types'

/** scheduled 는 서버 상태가 아니다 — 7일 창 밖이라 outbox_ids 가 빈 배열일 때 화면이 만든다 (components.md) */
export type DotState = OutboxState | 'scheduled'
export const DOT_LABEL: Record<DotState, string> = {
  queued: '대기',
  dispatched: '전송 중',
  acked: '반영됨',
  failed: '실패',
  cancelled: '취소됨',
  scheduled: '7일 이내로 들어오면 자동 전송됩니다',
}
</script>

<script setup lang="ts">
import Badge from '@/components/ui/Badge.vue'

defineProps<{ state: DotState }>()
</script>

<template>
  <Badge v-if="state === 'scheduled'" variant="outline" :title="DOT_LABEL.scheduled">예정</Badge>
  <span
    v-else
    class="dot"
    :class="`dot--${state}`"
    role="img"
    :aria-label="DOT_LABEL[state]"
    :title="DOT_LABEL[state]"
  />
</template>

<style scoped>
/* 색이 아니라 채움 정도로 단계를 읽는다 (tokens.md §outbox). gray.400 = --text-disabled, gray.600 = --text-2 */
.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border: 1.5px solid transparent;
  border-radius: var(--radius-full);
  vertical-align: middle;
}
.dot--queued {
  border-color: var(--text-disabled);
}
.dot--dispatched {
  border-color: var(--text-2);
  background: linear-gradient(90deg, var(--text-2) 50%, transparent 50%);
}
.dot--acked {
  background: var(--text-2);
}
.dot--failed {
  background: var(--danger);
}
.dot--cancelled {
  border-color: var(--text-disabled);
  background: linear-gradient(
    135deg,
    transparent 42%,
    var(--text-disabled) 42% 58%,
    transparent 58%
  );
}
</style>
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`
Expected: PASS (토큰 가드가 새 `.vue` 3개도 검사한다)

- [ ] **Step 5: 커밋**

```bash
git add web/src/components/domain
git commit -m "feat(web): domain 컴포넌트 — SignalBars(숫자+3칸), NodeStateBadge(가장 나쁜 경고 하나), OutboxDot(채움 정도)"
```

---

### Task 5: chart — Histogram

**Files:**
- Create: `web/src/components/chart/Histogram.vue`
- Modify: `web/eslint.config.js`
- Test: `web/src/components/chart/__tests__/histogram.spec.ts`

**Interfaces:**
- Produces (모듈 export): `SERIES_COLORS: readonly ['var(--chart-series-1)', 'var(--chart-series-2)', 'var(--chart-series-3)']` · `type HistogramSeries = [S] | [S, S] | [S, S, S]`(`S = { label: string }` — 4계열 이상은 **타입에서** 막는다) · `interface HistogramBucket { label: string; values: number[] }` · `niceStep(max: number): number`.
- Produces: props `{ buckets: HistogramBucket[]; series: HistogramSeries; marker?: { at: number; label: string }; yMax?: number }`. `marker.at` 은 **bucket 경계 번호**(0 = 첫 bucket 왼쪽, `at` = `at` 번째 bucket 왼쪽 경계). 루트 `<svg class="hist">` — `role`·`aria-label` 은 부르는 쪽이 attrs 로 준다.
- 기하(px 고정, 확대하지 않는다): 막대 폭 15 · 같은 bucket 계열 간격 2 · bucket 칸 72 · 왼쪽 여백 32 · 위 24 · 그림 높이 160 · 아래 24 · 오른쪽 8. 막대 색은 클래스 `hist__bar--1..3`(→ `--chart-series-*`).

- [ ] **Step 1: 실패 테스트**

`web/src/components/chart/__tests__/histogram.spec.ts`
```ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import Histogram, { niceStep } from '@/components/chart/Histogram.vue'

const B = (label: string, ...values: number[]) => ({ label, values })

describe('niceStep', () => {
  it('최댓값을 세 칸에 담는 1·2·5 간격, 건수라 1 미만은 없다', () => {
    expect([0, 1, 2, 7, 30, 95].map(niceStep)).toEqual([1, 1, 1, 5, 10, 50])
  })
})

describe('Histogram', () => {
  it('두 계열 — 막대 폭 15·간격 2, bucket 가운데 정렬, 계열 색은 고정 순서 클래스', () => {
    const w = mount(Histogram, {
      props: { buckets: [B('0–10', 3, 1)], series: [{ label: 'A' }, { label: 'B' }] },
    })
    const paths = w.findAll('path')
    expect(paths.map((p) => p.attributes('d')!.split(',')[0])).toEqual(['M52', 'M69'])
    expect(paths.map((p) => p.classes().find((c) => c.startsWith('hist__bar--')))).toEqual([
      'hist__bar--1',
      'hist__bar--2',
    ])
  })

  it('0 인 값은 막대를 그리지 않고, 값 라벨은 계열마다 가장 큰 막대(첫 것) 하나에만', () => {
    const w = mount(Histogram, {
      props: {
        buckets: [B('a', 1, 0), B('b', 3, 2), B('c', 3, 5)],
        series: [{ label: 'A' }, { label: 'B' }],
      },
    })
    expect(w.findAll('path')).toHaveLength(5)
    expect(w.findAll('.hist__value').map((t) => t.text())).toEqual(['3', '5'])
  })

  it('한 계열 — 막대 하나가 bucket 가운데', () => {
    const w = mount(Histogram, { props: { buckets: [B('a', 2)], series: [{ label: 'A' }] } })
    expect(w.get('path').attributes('d')!.startsWith('M60.5,')).toBe(true)
  })

  it('marker — bucket 경계에 세로 점선 + 라벨, 격자선은 두 줄', () => {
    const w = mount(Histogram, {
      props: {
        buckets: [B('0–10', 1), B('10–20', 30), B('20–30', 2), B('30–45', 1)],
        series: [{ label: 'A' }],
        marker: { at: 3, label: 'SLA 30초' },
      },
    })
    expect(w.get('.hist__marker line').attributes('x1')).toBe('248')
    expect(w.get('.hist__marker text').text()).toBe('SLA 30초')
    expect(w.findAll('.hist__grid line')).toHaveLength(2)
    expect(w.findAll('.hist__ticks text').map((t) => t.text())).toEqual(['10', '20'])
    expect(w.findAll('.hist__label').map((t) => t.text())).toEqual([
      '0–10',
      '10–20',
      '20–30',
      '30–45',
    ])
  })

  it('데이터가 전부 0 이어도 깨지지 않는다 — 막대·값 라벨 없음', () => {
    const w = mount(Histogram, { props: { buckets: [B('a', 0), B('b', 0)], series: [{ label: 'A' }] } })
    expect(w.findAll('path')).toHaveLength(0)
    expect(w.findAll('.hist__value')).toHaveLength(0)
    expect(w.get('svg').attributes('width')).toBe('184')
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/components/chart`
Expected: FAIL — `Failed to resolve import "@/components/chart/Histogram.vue"`

- [ ] **Step 3: 구현**

`web/eslint.config.js` 의 `app/ui-component-names` 블록을 바꾼다
```js
  {
    // ui·chart 컴포넌트는 components.md 표의 단어 그대로 (Button·Badge·Histogram) 쓴다
    name: 'app/ui-component-names',
    files: ['src/components/ui/**', 'src/components/chart/**'],
    rules: { 'vue/multi-word-component-names': 'off' },
  },
```

`web/src/components/chart/Histogram.vue`
```vue
<script lang="ts">
/** 계열색은 고정 순서 (tokens.md §chart 규칙 1). 범례(Legend)도 이 값을 쓴다 */
export const SERIES_COLORS = [
  'var(--chart-series-1)',
  'var(--chart-series-2)',
  'var(--chart-series-3)',
] as const
type S = { label: string }
/** 4계열 이상은 타입에서 막는다 (tokens.md §chart 규칙 2) */
export type HistogramSeries = [S] | [S, S] | [S, S, S]
export interface HistogramBucket {
  label: string
  values: number[]
}

/** 눈금 간격 — 최댓값을 세 칸에 담는 1·2·5 계열 수. 건수라 1 보다 작지 않다 */
export function niceStep(max: number): number {
  if (max <= 0) return 1
  const raw = max / 3
  const pow = 10 ** Math.floor(Math.log10(raw))
  const step = ([1, 2, 5, 10].find((m) => m * pow >= raw) ?? 10) * pow
  return Math.max(1, step)
}
</script>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  buckets: HistogramBucket[]
  series: HistogramSeries
  marker?: { at: number; label: string }
  yMax?: number
}>()

// px 고정 — 막대 폭 15px 를 지키려고 확대·축소하지 않는다 (components.md)
const BAR = 15
const GAP = 2
const SLOT = 72
const L = 32
const T = 24
const PLOT = 160
const B = 24
const R = 8
const BASE = T + PLOT

const width = computed(() => L + props.buckets.length * SLOT + R)
const height = T + PLOT + B
const peak = computed(() => Math.max(0, ...props.buckets.flatMap((b) => b.values)))
const step = computed(() => (props.yMax ? props.yMax / 3 : niceStep(peak.value)))
const top = computed(() => props.yMax ?? step.value * 3)
const y = (v: number) => BASE - (Math.min(v, top.value) / top.value) * PLOT
const n = computed(() => props.series.length)
const barX = (i: number, j: number) =>
  L + i * SLOT + (SLOT - (n.value * BAR + (n.value - 1) * GAP)) / 2 + j * (BAR + GAP)
const val = (b: HistogramBucket, j: number) => b.values[j] ?? 0

/** 계열마다 가장 큰 막대(같으면 첫 것)의 bucket 번호 — 값 라벨은 거기에만. 전부 0 이면 -1 */
const peakIdx = computed(() =>
  Array.from({ length: n.value }, (_, j) => {
    let best = -1
    let bv = 0
    props.buckets.forEach((b, i) => {
      if (val(b, j) > bv) {
        bv = val(b, j)
        best = i
      }
    })
    return best
  }),
)

/** 위 두 모서리만 radius.sm(4px), 바닥은 축에 붙는다 */
function barPath(x: number, v: number): string {
  const yt = y(v)
  const r = Math.min(4, BASE - yt, BAR / 2)
  return (
    `M${x},${BASE}V${yt + r}Q${x},${yt} ${x + r},${yt}` +
    `H${x + BAR - r}Q${x + BAR},${yt} ${x + BAR},${yt + r}V${BASE}Z`
  )
}
const tick = (v: number) => String(Math.round(v * 10) / 10)
</script>

<template>
  <svg class="hist" :width="width" :height="height" :viewBox="`0 0 ${width} ${height}`">
    <!-- 격자선은 두 줄만 (admin-dashboard.md) -->
    <g class="hist__grid">
      <line v-for="k in [1, 2]" :key="k" :x1="L" :x2="width - R" :y1="y(step * k)" :y2="y(step * k)" />
    </g>
    <g class="hist__ticks">
      <text v-for="k in [1, 2]" :key="k" :x="L - 6" :y="y(step * k) + 4" text-anchor="end">
        {{ tick(step * k) }}
      </text>
    </g>
    <g v-for="(b, i) in buckets" :key="b.label">
      <template v-for="(s, j) in series" :key="s.label">
        <path
          v-if="val(b, j) > 0"
          :class="['hist__bar', `hist__bar--${j + 1}`]"
          :d="barPath(barX(i, j), val(b, j))"
        />
        <text
          v-if="peakIdx[j] === i"
          class="hist__value"
          :x="barX(i, j) + BAR / 2"
          :y="y(val(b, j)) - 4"
          text-anchor="middle"
        >
          {{ val(b, j) }}
        </text>
      </template>
      <text class="hist__label" :x="L + i * SLOT + SLOT / 2" :y="BASE + 16" text-anchor="middle">
        {{ b.label }}
      </text>
    </g>
    <line class="hist__axis" :x1="L" :x2="width - R" :y1="BASE" :y2="BASE" />
    <g v-if="marker" class="hist__marker">
      <line :x1="L + marker.at * SLOT" :x2="L + marker.at * SLOT" :y1="T - 8" :y2="BASE" />
      <text :x="L + marker.at * SLOT + 4" :y="T - 12">{{ marker.label }}</text>
    </g>
  </svg>
</template>

<style scoped>
.hist {
  display: block;
  font-size: var(--font-size-xs);
  font-variant-numeric: tabular-nums;
}
.hist__grid line {
  stroke: var(--chart-grid);
}
.hist__axis {
  stroke: var(--chart-axis);
}
.hist__ticks text,
.hist__label {
  fill: var(--chart-text);
}
.hist__bar--1 {
  fill: var(--chart-series-1);
}
.hist__bar--2 {
  fill: var(--chart-series-2);
}
.hist__bar--3 {
  fill: var(--chart-series-3);
}
/* 글자는 계열색을 입지 않는다 (규칙 5) */
.hist__value {
  fill: var(--text-2);
  font-weight: var(--font-weight-bold);
}
.hist__marker line {
  stroke: var(--line-3);
  stroke-dasharray: 3 3;
}
.hist__marker text {
  fill: var(--text-3);
}
</style>
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`
Expected: PASS. (마지막 테스트: 2 bucket → 32 + 144 + 8 = 184)

- [ ] **Step 5: 커밋**

```bash
git add web/src/components/chart web/eslint.config.js
git commit -m "feat(web): Histogram — SVG 직접, 계열 고정색·최대 3계열(타입), 최대 막대에만 값 라벨, SLA 경계 점선"
```

---

### Task 6: 노드 상태 화면 — 헤더 · ESP노드 표 · 30 s · 메뉴

**Files:**
- Create: `web/src/admin/nodesView.ts`, `web/src/admin/views/NodesView.vue`
- Modify: `web/src/admin/router.ts`, `web/src/admin/AdminShell.vue`, `web/src/admin/__tests__/shell.spec.ts`, `web/e2e/monitor.spec.ts`
- Test: `web/src/admin/__tests__/nodes.spec.ts`

**Interfaces:**
- Consumes: `adminApi.nodes`, `loraApi.{modems, pending, syncRoom, broadcastTime}` (Task 2) · `useResource`·`usePolling` (F1) · `LastRefreshed` (Task 3) · `SignalBars`·`NodeStateBadge` (Task 4) · `Table`·`Badge`·`Button`·`Checkbox`·`Select`·`EmptyState`·`showToast` (F1) · `formatKst`·`relativeKo`.
- Produces (`admin/nodesView.ts`): `sortNodes(nodes: NodeOut[]): NodeOut[]` · `unitsByRoom(nodes: NodeOut[]): Map<number, number>` · `roomLabel(n: NodeOut, units: Map<number, number>): string` · `volts(mv: number | null): string` · `versions(n: NodeOut): string` · `buildingOptions(nodes: NodeOut[]): { value: number | ''; label: string }[]` · `provisionChoices(nodes: NodeOut[], bld: string, room: number | '')`(Task 8 이 쓴다 — 여기서 함께 만든다):
  `{ buildings: { value: string; label: string }[]; rooms: { value: number; label: string }[]; units: { value: number; label: string; mac: string | null }[] }`.
- Produces (`NodesView.vue`): 리소스 `data: { modems: ModemOut[]; nodes: NodeOut[]; pending: PendingOut[] } | undefined`, `nodes` computed, `reload`. Task 7·8 이 이 파일에 패널을 끼운다. ESP노드 블록은 `<section aria-labelledby="nodes-esp">`, 건물 필터는 `.nodes__filter select`.
- 라우트 `/nodes`, 메뉴 `노드 상태`(회원 위).

화면 규칙(`admin-nodes.md`): 블록 사이 `space.5` · 헤더 `ESP노드 · 모뎀Pi` + 마지막 갱신 + 건물 Select + `새로고침`(ghost) + `시각 브로드캐스트`(secondary) · 표 열 `호수 | MAC | FW | 배터리 | 신호 | 버전 S/R/E/I | 상태 | 마지막 수신 | 작업` · 정렬 `last_seen` 오래된 순, null 먼저 · `문제 있는 것만` Checkbox · 에러 시 이전 표 유지 + Toast(danger) + 재시도 · 30초 자동 새로고침.

- [ ] **Step 1: 실패 테스트**

`web/src/admin/__tests__/nodes.spec.ts`
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import NodesView from '@/admin/views/NodesView.vue'
import {
  buildingOptions,
  roomLabel,
  sortNodes,
  unitsByRoom,
  versions,
  volts,
} from '@/admin/nodesView'
import { adminApi } from '@/api/admin'
import { loraApi } from '@/api/lora'
import { ApiError, MESSAGES } from '@/api/client'
import type { Enqueued, NodeOut } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/admin', () => ({ adminApi: { nodes: vi.fn() } }))
vi.mock('@/api/lora', () => ({
  loraApi: {
    modems: vi.fn(),
    pending: vi.fn(),
    syncRoom: vi.fn(),
    broadcastTime: vi.fn(),
    registerModem: vi.fn(),
    rotateToken: vi.fn(),
    provision: vi.fn(),
  },
}))
const nodesApi = vi.mocked(adminApi.nodes)
const lora = vi.mocked(loraApi, true)

const node = (over: Partial<NodeOut> = {}): NodeOut => ({
  room_id: 1,
  building_id: 1,
  building: '공학관',
  bld: 'E',
  room: 401,
  unit: 1,
  modem_id: 'm1',
  mac: '0A1B2C3D4E01',
  fw: 3,
  batt_mv: 3980,
  rssi: -71,
  snr: 7.5,
  sched_ver: 41,
  resv_ver: 12,
  exam_ver: 3,
  ident_ver: 2,
  layout: 1,
  clock_stale: false,
  low_batt: false,
  uptime_h: 10,
  last_seen_at: new Date('2026-09-25T00:00:00Z'),
  last_ack_at: null,
  last_status_at: null,
  sync_state: 'synced',
  warnings: [],
  ...over,
})
const never = (over: Partial<NodeOut> = {}) =>
  node({
    mac: null,
    fw: null,
    batt_mv: null,
    rssi: null,
    snr: null,
    sched_ver: null,
    resv_ver: null,
    exam_ver: null,
    ident_ver: null,
    last_seen_at: null,
    sync_state: 'unknown',
    warnings: ['unseen'],
    ...over,
  })

let visibility: DocumentVisibilityState = 'visible'
beforeEach(() => {
  visibility = 'visible'
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => visibility })
  toasts.value.forEach((t) => dismissToast(t.id))
  nodesApi.mockReset().mockResolvedValue([node(), never({ room_id: 2, room: 402 })])
  lora.modems.mockReset().mockResolvedValue([])
  lora.pending.mockReset().mockResolvedValue([])
  lora.syncRoom.mockReset().mockResolvedValue({ outbox_ids: [1], id: null })
  lora.broadcastTime.mockReset()
})
afterEach(() => vi.useRealTimers())

async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { render: () => null } }],
  })
  const w = mount(NodesView, { global: { plugins: [router], stubs: { teleport: true } } })
  await flushPromises()
  return w
}
const esp = (w: VueWrapper) => w.get('section[aria-labelledby="nodes-esp"]')
const firstCells = (w: VueWrapper) => esp(w).findAll('tbody tr').map((r) => r.get('td').text())
const button = (w: VueWrapper, text: string) => w.findAll('button').find((b) => b.text() === text)!

describe('nodesView', () => {
  it('sortNodes — 보고 없음(null) 먼저, 그다음 오래된 순, 같으면 서버 순서', () => {
    const a = node({ room: 1, last_seen_at: new Date('2026-09-25T01:00:00Z') })
    const b = never({ room: 2 })
    const c = node({ room: 3, last_seen_at: new Date('2026-09-23T01:00:00Z') })
    const d = never({ room: 4 })
    expect(sortNodes([a, b, c, d]).map((n) => n.room)).toEqual([2, 4, 3, 1])
  })
  it('roomLabel — 노드가 2대인 방만 -unit', () => {
    const ns = [
      node({ room_id: 1, room: 401 }),
      node({ room_id: 2, room: 402, unit: 1 }),
      node({ room_id: 2, room: 402, unit: 2 }),
    ]
    const u = unitsByRoom(ns)
    expect(ns.map((n) => roomLabel(n, u))).toEqual(['401', '402-1', '402-2'])
  })
  it('volts·versions — 퍼센트로 바꾸지 않고, null 은 —', () => {
    expect(volts(3980)).toBe('3.98 V')
    expect(volts(null)).toBe('—')
    expect(versions(node())).toBe('41/12/3/2')
    expect(versions(node({ exam_ver: null }))).toBe('41/12/—/2')
    expect(versions(never())).toBe('—')
  })
  it('buildingOptions — 전체 + 이름순, 중복 없음', () => {
    const ns = [
      node({ building_id: 2, building: '사회관' }),
      node({ building_id: 1, building: '공학관' }),
      node({ building_id: 2, building: '사회관' }),
    ]
    expect(buildingOptions(ns)).toEqual([
      { value: '', label: '전체' },
      { value: 1, label: '공학관' },
      { value: 2, label: '사회관' },
    ])
  })
})

describe('NodesView', () => {
  it('보고 없는 노드가 먼저, 빈 칸은 —, 응답 없음 배지 · 값은 V·dBm·버전', async () => {
    const w = await mountView()
    expect(firstCells(w)).toEqual(['공학관 402', '공학관 401'])
    const [first, second] = esp(w).findAll('tbody tr')
    expect(first.text()).toContain('응답 없음')
    expect(first.findAll('td')[1].text()).toBe('—')
    expect(second.text()).toContain('3.98 V')
    expect(second.text()).toContain('−71 dBm')
    expect(second.text()).toContain('41/12/3/2')
    expect(second.text()).toContain('동기화됨')
  })

  it('배터리 경고(low_batt)면 V 값을 busy 틴트 배지로', async () => {
    nodesApi.mockResolvedValue([node({ warnings: ['low_batt'], batt_mv: 3420 })])
    const w = await mountView()
    expect(esp(w).get('.badge--busy').text()).toBe('3.42 V')
  })

  it('문제 있는 것만 · 건물 필터', async () => {
    nodesApi.mockResolvedValue([
      node({ room_id: 1, room: 401 }),
      node({ room_id: 2, room: 402, warnings: ['resync'] }),
      node({ room_id: 3, building_id: 2, building: '사회관', room: 101 }),
    ])
    const w = await mountView()
    await esp(w).get('input[type="checkbox"]').setValue(true)
    expect(firstCells(w)).toEqual(['공학관 402'])
    await esp(w).get('input[type="checkbox"]').setValue(false)
    await w.get('.nodes__filter select').setValue('2')
    expect(firstCells(w)).toEqual(['사회관 101'])
  })

  it('강의실이 없으면 빈 상태 — master 화면이 아직 없으면 링크 버튼도 없다', async () => {
    nodesApi.mockResolvedValue([])
    const w = await mountView()
    expect(esp(w).text()).toContain('이 건물에 강의실이 없습니다')
    expect(esp(w).find('.empty button').exists()).toBe(false)
  })

  it('첫 조회 실패 — "강의실 없음"으로 오독되지 않게 불러오지 못했다고 말한다', async () => {
    nodesApi.mockRejectedValue(new ApiError(500, MESSAGES[500]))
    const w = await mountView()
    expect(esp(w).text()).toContain('노드 목록을 불러오지 못했습니다')
    expect(esp(w).text()).not.toContain('이 건물에 강의실이 없습니다')
  })

  it('30초마다 다시 읽고, 화면을 떠나면 멈춘다', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    const w = await mountView()
    expect(nodesApi).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(30_000)
    await flushPromises()
    expect(nodesApi).toHaveBeenCalledTimes(2)
    w.unmount()
    vi.advanceTimersByTime(90_000)
    await flushPromises()
    expect(nodesApi).toHaveBeenCalledTimes(2)
  })

  it('숨긴 탭에서는 읽지 않고, 다시 보이면 즉시 1회', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    const w = await mountView()
    visibility = 'hidden'
    document.dispatchEvent(new Event('visibilitychange'))
    vi.advanceTimersByTime(120_000)
    await flushPromises()
    expect(nodesApi).toHaveBeenCalledTimes(1)
    visibility = 'visible'
    document.dispatchEvent(new Event('visibilitychange'))
    await flushPromises()
    expect(nodesApi).toHaveBeenCalledTimes(2)
    w.unmount()
  })

  it('갱신 실패 — 표를 지우지 않고, 끊긴 동안 Toast 는 한 번', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    const w = await mountView()
    nodesApi.mockRejectedValue(new ApiError(0, MESSAGES[0]))
    for (let i = 0; i < 3; i++) {
      vi.advanceTimersByTime(30_000)
      await flushPromises()
    }
    expect(esp(w).findAll('tbody tr')).toHaveLength(2)
    expect(toasts.value.filter((t) => t.tone === 'danger').map((t) => t.message)).toEqual([
      MESSAGES[0],
    ])
    w.unmount()
  })

  it('재전송 — 방 id 로 요청, 처리 중에는 다시 누를 수 없다', async () => {
    let resolve!: (v: Enqueued) => void
    lora.syncRoom.mockReturnValue(new Promise((r) => (resolve = r)))
    const w = await mountView()
    const btn = esp(w).findAll('tbody tr')[1].get('button')
    await btn.trigger('click')
    await btn.trigger('click')
    expect(lora.syncRoom).toHaveBeenCalledTimes(1)
    expect(lora.syncRoom).toHaveBeenCalledWith(1)
    resolve({ outbox_ids: [9], id: null })
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe('공학관 401호 재전송을 요청했습니다.')
  })

  it('시각 브로드캐스트 — 0대 · 429 · 성공 문구', async () => {
    const w = await mountView()
    lora.broadcastTime.mockResolvedValueOnce({ modems: 0 })
    await button(w, '시각 브로드캐스트').trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe('연결된 모뎀Pi가 없어 보내지 못했습니다.')
    lora.broadcastTime.mockRejectedValueOnce(new ApiError(429, MESSAGES[429]))
    await button(w, '시각 브로드캐스트').trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe('시각 브로드캐스트는 10분에 한 번만 보낼 수 있습니다.')
    lora.broadcastTime.mockResolvedValueOnce({ modems: 2 })
    await button(w, '시각 브로드캐스트').trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe('모뎀Pi 2대에 시각을 보냈습니다.')
  })
})
```

`web/src/admin/__tests__/shell.spec.ts` 의 첫 `it`(`'/ 는 /users 로, 회원 메뉴가 활성이고 대기 건수 배지'`)를 통째로 바꾼다
```ts
  it('/ 는 /users 로, 메뉴 순서 · 회원 활성 · 대기 건수 배지', async () => {
    const { w, router } = await mountApp('/')
    expect(router.currentRoute.value.path).toBe('/users')
    expect(list).toHaveBeenCalledWith('pending_approval')
    const links = w.findAll('nav a')
    expect(links.map((a) => a.text().replace(/\d+/g, '').trim())).toEqual(['노드 상태', '회원'])
    expect(links[1].text()).toContain('2')
    expect(links[1].attributes('aria-current')).toBe('page')
    expect(w.text()).toContain('관리자1')
  })
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin`
Expected: FAIL — `Failed to resolve import "@/admin/views/NodesView.vue"`, shell.spec `expected [ '회원' ] to deeply equal [ '노드 상태', '회원' ]`

- [ ] **Step 3: 구현**

`web/src/admin/nodesView.ts`
```ts
import type { NodeOut } from '@/api/types'

const seenAt = (n: NodeOut) => n.last_seen_at?.getTime() ?? Number.NEGATIVE_INFINITY

/** last_seen 오래된 순, 보고 없음(null) 먼저 (admin-nodes.md). 같으면 서버 순서(bld·room·unit) 유지 —
 * 서버 /summary 의 미리보기 정렬과 같은 키. 표시 순서일 뿐 데이터 보정이 아니다 */
export function sortNodes(nodes: NodeOut[]): NodeOut[] {
  return [...nodes].sort((a, b) => {
    const x = seenAt(a)
    const y = seenAt(b)
    return x === y ? 0 : x < y ? -1 : 1
  })
}

/** 방마다 노드 대수 (rooms.units — NodeOut 은 rooms × units 를 다 준다) */
export function unitsByRoom(nodes: NodeOut[]): Map<number, number> {
  const m = new Map<number, number>()
  for (const n of nodes) m.set(n.room_id, Math.max(m.get(n.room_id) ?? 0, n.unit))
  return m
}

/** 노드가 2대인 방만 401-1 · 401-2 (admin-nodes.md 미결 2 — 한 행 = 한 장치) */
export function roomLabel(n: NodeOut, units: Map<number, number>): string {
  return (units.get(n.room_id) ?? 1) > 1 ? `${n.room}-${n.unit}` : String(n.room)
}

/** V 로만 — 퍼센트 환산 금지 (방전 곡선을 모르는 채 환산하면 없는 정밀도를 만든다) */
export const volts = (mv: number | null) => (mv == null ? '—' : `${(mv / 1000).toFixed(2)} V`)

/** 버전 S/R/E/I 를 한 칸에 — 전부 없으면 — */
export function versions(n: NodeOut): string {
  const v = [n.sched_ver, n.resv_ver, n.exam_ver, n.ident_ver]
  return v.every((x) => x == null) ? '—' : v.map((x) => x ?? '—').join('/')
}

/** 건물 Select — 노드 목록에서 파생 (강의실이 없는 건물은 노드도 없다) */
export function buildingOptions(nodes: NodeOut[]): { value: number | ''; label: string }[] {
  const seen = new Map<number, string>()
  for (const n of nodes) seen.set(n.building_id, n.building)
  const list = [...seen]
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label, 'ko'))
  return [{ value: '', label: '전체' }, ...list]
}

/** 강의실 배정 Modal 의 선택지 — 기대 노드(rooms × units)가 곧 배정 가능한 (bld, room, unit) 전부다 */
export function provisionChoices(nodes: NodeOut[], bld: string, room: number | '') {
  const buildings = new Map<string, string>()
  const rooms = new Set<number>()
  for (const n of nodes) {
    buildings.set(n.bld, n.building)
    if (n.bld === bld) rooms.add(n.room)
  }
  return {
    buildings: [...buildings].map(([value, label]) => ({ value, label })),
    rooms: [...rooms].sort((a, b) => a - b).map((r) => ({ value: r, label: `${r}호` })),
    units: nodes
      .filter((n) => n.bld === bld && n.room === room)
      .map((n) => ({
        value: n.unit,
        label: n.mac ? `${n.unit}번 노드 — 사용 중` : `${n.unit}번 노드`,
        mac: n.mac,
      })),
  }
}
```

`web/src/admin/views/NodesView.vue`
```vue
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Select from '@/components/ui/Select.vue'
import Table from '@/components/ui/Table.vue'
import { showToast } from '@/components/ui/toast'
import NodeStateBadge from '@/components/domain/NodeStateBadge.vue'
import SignalBars from '@/components/domain/SignalBars.vue'
import { adminApi } from '@/api/admin'
import { loraApi } from '@/api/lora'
import { ApiError } from '@/api/client'
import type { NodeOut } from '@/api/types'
import { useResource } from '@/lib/useResource'
import { usePolling } from '@/lib/usePolling'
import { formatKst, relativeKo } from '@/lib/time'
import LastRefreshed from '../LastRefreshed.vue'
import {
  buildingOptions,
  roomLabel,
  sortNodes,
  unitsByRoom,
  versions,
  volts,
} from '../nodesView'

const router = useRouter()

// 블록 셋 = 엔드포인트 셋 (admin-nodes.md). 한 번에 읽어 한 시각(refreshedAt)으로 보인다
const { data, error, loading, refreshedAt, reload } = useResource(async () => {
  const [modems, nodes, pending] = await Promise.all([
    loraApi.modems(),
    adminApi.nodes(),
    loraApi.pending(),
  ])
  return { modems, nodes, pending }
})
// 노드를 켜 놓고 이 화면을 보는 일이 잦다 — 30초 (숨김이면 정지, 떠나면 해제)
usePolling(reload, 30_000)

// 끊긴 동안 Toast 는 한 번 — 30초마다 쌓이지 않게. 이전 표는 그대로 둔다(빈 표 = "전부 죽었다"로 오독)
watch(error, (e, prev) => {
  if (e && !prev && e.status !== 401 && e.status !== 403)
    showToast({
      tone: 'danger',
      message: e.message,
      action: { label: '재시도', onClick: () => void reload() },
    })
})

const nodes = computed(() => data.value?.nodes ?? [])
const units = computed(() => unitsByRoom(nodes.value))
const buildingId = ref<number | ''>('')
const buildingOpts = computed(() => buildingOptions(nodes.value))
// 고른 건물이 목록에서 사라지면(삭제) 전체로
watch(buildingOpts, (opts) => {
  if (!opts.some((o) => o.value === buildingId.value)) buildingId.value = ''
})
const onlyWarn = ref(false)
const rows = computed(() =>
  sortNodes(
    nodes.value.filter(
      (n) =>
        (buildingId.value === '' || n.building_id === buildingId.value) &&
        (!onlyWarn.value || n.warnings.length > 0),
    ),
  ).map((n) => ({ ...n, key: `${n.room_id}-${n.unit}` })),
)

// master 화면(F2)이 있을 때만 링크 — 라우트가 없으면 버튼을 두지 않는다
const hasMaster = router.resolve('/master').matched.length > 0
const empty = computed(() => {
  if (!data.value)
    return {
      message: '노드 목록을 불러오지 못했습니다',
      actions: [{ label: '다시 불러오기', onClick: () => void reload() }],
    }
  if (nodes.value.length === 0)
    return {
      message: '이 건물에 강의실이 없습니다',
      actions: hasMaster
        ? [{ label: '건물 · 강의실', onClick: () => void router.push('/master') }]
        : [],
    }
  return { message: '문제 있는 노드가 없습니다', actions: [] }
})

const COLUMNS: {
  key: string
  label: string
  width?: string
  align?: 'left' | 'right' | 'center'
}[] = [
  { key: 'room', label: '호수' },
  { key: 'mac', label: 'MAC', width: '120px' },
  { key: 'fw', label: 'FW', width: '56px', align: 'right' },
  { key: 'batt', label: '배터리', width: '96px', align: 'right' },
  { key: 'rssi', label: '신호', width: '112px' },
  { key: 'ver', label: '버전 S/R/E/I', width: '112px' },
  { key: 'state', label: '상태', width: '104px' },
  { key: 'seen', label: '마지막 수신', width: '104px' },
  { key: 'actions', label: '작업', width: '88px' },
]
const asNode = (row: Record<string, unknown>) => row as unknown as NodeOut

// 재전송 — 방 단위 전체 동기화. 한 번에 하나만
const syncing = ref<number | null>(null)
async function resend(n: NodeOut) {
  if (syncing.value !== null) return
  syncing.value = n.room_id
  try {
    await loraApi.syncRoom(n.room_id)
    showToast({ message: `${n.building} ${n.room}호 재전송을 요청했습니다.` })
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 404) {
      showToast({ message: '강의실이 이미 삭제되었습니다. 목록을 새로 불러옵니다.' })
      void reload()
    } else if (e.status !== 401 && e.status !== 403)
      showToast({
        tone: 'danger',
        message: e.message,
        action: { label: '재시도', onClick: () => void resend(n) },
      })
  } finally {
    syncing.value = null
  }
}

// 시각 브로드캐스트 — 서버 전역 10분 1회. 연결된 모뎀이 0대면 실패가 아니라 안내
const broadcasting = ref(false)
async function broadcast() {
  if (broadcasting.value) return
  broadcasting.value = true
  try {
    const { modems } = await loraApi.broadcastTime()
    showToast({
      message: modems
        ? `모뎀Pi ${modems}대에 시각을 보냈습니다.`
        : '연결된 모뎀Pi가 없어 보내지 못했습니다.',
    })
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 429)
      showToast({ message: '시각 브로드캐스트는 10분에 한 번만 보낼 수 있습니다.' })
    else if (e.status !== 401 && e.status !== 403)
      showToast({ tone: 'danger', message: e.message })
  } finally {
    broadcasting.value = false
  }
}
</script>

<template>
  <main class="nodes">
    <header class="nodes__head">
      <h1 class="nodes__title">ESP노드 · 모뎀Pi</h1>
      <LastRefreshed :at="refreshedAt" />
      <div class="nodes__tools">
        <label class="nodes__filter">
          <span>건물</span>
          <Select v-model="buildingId" :options="buildingOpts" size="sm" />
        </label>
        <Button variant="ghost" size="sm" :loading="loading" @click="reload">새로고침</Button>
        <Button variant="secondary" size="sm" :loading="broadcasting" @click="broadcast"
          >시각 브로드캐스트</Button
        >
      </div>
    </header>

    <section class="nodes__block" aria-labelledby="nodes-esp">
      <div class="nodes__block-head">
        <h2 id="nodes-esp" class="nodes__h2">ESP노드</h2>
        <Checkbox v-model="onlyWarn" label="문제 있는 것만" />
      </div>
      <Table
        :columns="COLUMNS"
        :rows="rows as unknown as Record<string, unknown>[]"
        row-key="key"
        :loading="loading && !data"
      >
        <template #empty>
          <EmptyState :message="empty.message" :actions="empty.actions" />
        </template>
        <template #cell-room="{ row }"
          >{{ asNode(row).building }} {{ roomLabel(asNode(row), units) }}</template
        >
        <template #cell-batt="{ row }">
          <Badge v-if="asNode(row).warnings.includes('low_batt')" tone="busy" class="num">{{
            volts(asNode(row).batt_mv)
          }}</Badge>
          <span v-else class="num">{{ volts(asNode(row).batt_mv) }}</span>
        </template>
        <template #cell-rssi="{ row }"><SignalBars :rssi="asNode(row).rssi" /></template>
        <template #cell-ver="{ row }"
          ><span class="num">{{ versions(asNode(row)) }}</span></template
        >
        <template #cell-state="{ row }"
          ><NodeStateBadge :warnings="asNode(row).warnings"
        /></template>
        <template #cell-seen="{ row }">
          <span v-if="asNode(row).last_seen_at" :title="formatKst(asNode(row).last_seen_at!)">{{
            relativeKo(asNode(row).last_seen_at!)
          }}</span>
          <template v-else>—</template>
        </template>
        <template #cell-actions="{ row }">
          <Button
            variant="ghost"
            size="sm"
            :loading="syncing === asNode(row).room_id"
            :disabled="syncing !== null"
            @click="resend(asNode(row))"
            >재전송</Button
          >
        </template>
      </Table>
    </section>
  </main>
</template>

<style scoped>
.nodes {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  padding: var(--space-5);
}
.nodes__head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.nodes__title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
}
.nodes__tools {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-left: auto;
}
.nodes__filter {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.nodes__block-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}
.nodes__h2 {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
</style>
```

`web/src/admin/router.ts` 의 `children` 을 바꾼다
```ts
    children: [
      { path: '', redirect: '/users' },
      { path: 'nodes', component: () => import('./views/NodesView.vue') },
      { path: 'users', component: () => import('./views/UsersView.vue') },
    ],
```

`web/src/admin/AdminShell.vue` 의 `nav` 를 바꾼다
```ts
// #46 admin-master.md 순서: 건물 · 강의실 · 강의실 설정 · 주간 시간표(F2) · 노드 상태 · 전송 현황 · 회원
const nav = computed(() => [
  { to: '/nodes', label: '노드 상태' },
  { to: '/users', label: '회원', badge: pendingCount.value },
])
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint && pnpm exec prettier --check .`
Expected: PASS

- [ ] **Step 5: E2E — 노드 표**

`web/e2e/monitor.spec.ts` 를 고친다. import 줄을
```ts
import { expect, test, type APIRequestContext, type BrowserContext, type Page } from '@playwright/test'
import cfg from './env.json' with { type: 'json' }
import { SEED, SIZES, apiLogin, fillLogin, nextAdmin, seedMonitoring, shot } from './helpers'
```
로, `let api: APIRequestContext` 아래에 `let page: Page` 를 두고, `beforeAll` 의 `await seedMonitoring(api)` 뒤에 추가
```ts
  page = await ctx.newPage()
  await page.goto('/admin/nodes')
  await fillLogin(page, nextAdmin())
  await expect(page).toHaveURL(/\/admin\/nodes$/)
```
파일 끝에 추가
```ts
// ---- 노드 상태 ----
const esp = () => page.getByRole('region', { name: 'ESP노드', exact: true })

test('노드 상태 — 보고 없음 먼저, 경고 배지 하나, 배터리 V·신호, 마지막 갱신', async () => {
  const rows = esp().locator('tbody tr')
  await expect(rows).toHaveCount(4)
  await expect(rows.nth(0)).toContainText('공학관 402-2')
  await expect(rows.nth(0)).toContainText('응답 없음')
  await expect(rows.nth(1)).toContainText('공학관 402-1')
  await expect(rows.nth(1).getByText('응답 없음')).toHaveAttribute('title', '배터리')
  await expect(rows.nth(1)).toContainText('3.42 V')
  await expect(rows.nth(1)).toContainText('−95 dBm')
  await expect(rows.nth(2)).toContainText('공학관 403')
  await expect(rows.nth(2).getByText('배터리', { exact: true })).toHaveAttribute('title', '재동기 중')
  await expect(rows.nth(3)).toContainText('공학관 401')
  await expect(rows.nth(3)).toContainText('동기화됨')
  await expect(rows.nth(3)).toContainText('41/12/3/2')
  await expect(page.getByText(/마지막 갱신 \d\d:\d\d/)).toBeVisible()
  await expect(page.getByRole('link', { name: '노드 상태' })).toHaveAttribute('aria-current', 'page')
  await shot(page, 'admin-nodes-1440')
})

test('문제 있는 것만 · 건물 필터', async () => {
  await esp().getByLabel('문제 있는 것만').check()
  await expect(esp().locator('tbody tr')).toHaveCount(3)
  await esp().getByLabel('문제 있는 것만').uncheck()
  await page.getByLabel('건물').selectOption({ label: SEED.building })
  await expect(esp().locator('tbody tr')).toHaveCount(4)
  await page.getByLabel('건물').selectOption({ label: '전체' })
})

test('네트워크가 끊겨도 표를 지우지 않는다', async () => {
  // 경로 함수로 — '**/api/**' 는 Vite 모듈(/src/api/client.ts)까지 잡는다
  const isApi = (u: URL) => u.pathname.startsWith('/api/')
  await page.route(isApi, (r) => r.abort())
  await page.getByRole('button', { name: '새로고침' }).click()
  await expect(page.getByText('서버에 연결할 수 없습니다. 네트워크를 확인해 주세요.')).toBeVisible()
  await expect(esp().locator('tbody tr')).toHaveCount(4)
  await page.unroute(isApi)
  await page.getByRole('alert').getByRole('button', { name: '닫기' }).click()
})

test('시각 브로드캐스트 — 연결된 모뎀Pi 가 없으면 그렇게 말한다', async () => {
  await page.getByRole('button', { name: '시각 브로드캐스트' }).click()
  await expect(page.getByText('연결된 모뎀Pi가 없어 보내지 못했습니다.')).toBeVisible()
})

test('재전송 — 방 단위 동기화 요청', async () => {
  const row = esp().locator('tbody tr', { hasText: '공학관 401' })
  await row.getByRole('button', { name: '재전송' }).click()
  await expect(page.getByText('공학관 401호 재전송을 요청했습니다.')).toBeVisible()
})
```
(`재전송` 은 outbox 행을 새로 만든다 — Task 9 의 대시보드 테스트는 이 테스트보다 **앞**에 끼운다.)

- [ ] **Step 6: E2E 실행 + 스크린샷 대조**

Run: **E2E 명령** + ` e2e/monitor.spec.ts`
Expected: `6 passed`. `admin-nodes-1440.png` 를 `admin-nodes.md` 와 대조:
- 제목 `ESP노드 · 모뎀Pi` 옆 `마지막 갱신 HH:MM`(text.3, xs), 오른쪽 끝에 `건물[전체▾]` · `새로고침`(ghost) · `시각 브로드캐스트`(secondary). 블록 사이 24px(space.5).
- 표: 헤더 `sunken` + 아래 2px, 행 32px, 세로선 없음. 열 순서 `호수 | MAC | FW | 배터리 | 신호 | 버전 S/R/E/I | 상태 | 마지막 수신 | 작업`.
- 402-2 행은 `—` 가 줄지어 있고 맨 위. 적색은 `응답 없음`·`배터리` 테두리 배지와 402-1 의 `3.42 V` 틴트 배지뿐. `동기화됨` 은 회색 solid.
- 신호 막대는 무채색 3칸(채운 칸 `text.2`, 빈 칸 `line.3`) + `−71 dBm`.
어긋나면 고치고 다시 찍는다. 전체 **E2E 명령** 도 한 번(F1 테스트는 아직 `/admin/users` 로 착지 — Task 9 에서 바뀐다).

- [ ] **Step 7: 커밋**

```bash
git add web/src/admin web/e2e/monitor.spec.ts
git commit -m "feat(web): 노드 상태 화면 — ESP노드 표(보고 없음 먼저·경고 배지 하나·V·dBm), 건물·문제만 필터, 재전송, 시각 브로드캐스트, 30초 갱신 + E2E"
```

---

### Task 7: 모뎀Pi 블록 — 카드 · 등록 · 토큰 재발급 · 토큰 1회 표시

**Files:**
- Create: `web/src/admin/views/nodes/ModemPanel.vue`
- Modify: `web/src/admin/views/NodesView.vue`, `web/e2e/monitor.spec.ts`
- Test: `web/src/admin/__tests__/modems.spec.ts`

**Interfaces:**
- Consumes: `loraApi.registerModem`, `loraApi.rotateToken` (Task 2) · `ModemOut`, `TokenOut` · `Modal`·`Input`·`Button`·`Badge`·`EmptyState`·`Skeleton`·`showToast` · `formatKst`·`relativeKo`.
- Produces: `ModemPanel.vue` props `{ modems?: ModemOut[]; loading: boolean }`, emits `changed`, `defineExpose({ openRegister })`. 루트 `<section aria-labelledby="nodes-modem">`, 카드 `li.modem`, 토큰 `code.token`.

화면 규칙(`admin-nodes.md` §토큰은 한 번만 보인다): 발급 직후 Modal 에 토큰을 크게 + `복사` + "이 창을 닫으면 다시 볼 수 없습니다" · 재발급은 확인 Modal(danger 버튼은 그 안에서만), 본문에 "끊긴다" · 토큰을 표·카드에 두지 않는다 · 모뎀 0대 EmptyState "등록된 모뎀Pi가 없습니다" + `모뎀Pi 등록` · 로딩 Skeleton 2개.

- [ ] **Step 1: 실패 테스트**

`web/src/admin/__tests__/modems.spec.ts`
```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import ModemPanel from '@/admin/views/nodes/ModemPanel.vue'
import { loraApi } from '@/api/lora'
import { ApiError, MESSAGES } from '@/api/client'
import type { ModemOut } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/lora', () => ({ loraApi: { registerModem: vi.fn(), rotateToken: vi.fn() } }))
const lora = vi.mocked(loraApi, true)

const m = (over: Partial<ModemOut> = {}): ModemOut => ({
  modem_id: 'gonghak-01',
  agent_ver: '0.4.1',
  modem_fw: '1.2.0',
  last_seen_at: new Date(),
  connected: true,
  school_id: 1,
  ...over,
})
const mountPanel = (modems?: ModemOut[], loading = false) =>
  mount(ModemPanel, { props: { modems, loading }, global: { stubs: { teleport: true } } })
const button = (w: VueWrapper, text: string) => w.findAll('button').find((b) => b.text() === text)!
async function issueToken(w: VueWrapper) {
  lora.registerModem.mockResolvedValue({ modem_id: 'gonghak-02', token: 'tok-abc' })
  ;(w.vm as unknown as { openRegister(): void }).openRegister()
  await nextTick()
  await w.get('[role="dialog"] input').setValue('gonghak-02')
  await button(w, '등록').trigger('click')
  await flushPromises()
}

beforeEach(() => {
  toasts.value.forEach((t) => dismissToast(t.id))
  lora.registerModem.mockReset()
  lora.rotateToken.mockReset()
})

describe('ModemPanel', () => {
  it('카드 — 연결됨(solid)/끊김(danger), 접속 기록 없음, 토큰은 어디에도 없다', () => {
    const w = mountPanel([
      m(),
      m({ modem_id: 'sahoe-01', connected: false, last_seen_at: null, agent_ver: null }),
    ])
    const cards = w.findAll('li.modem')
    expect(cards[0].text()).toContain('gonghak-01')
    expect(cards[0].text()).toContain('agent 0.4.1 · 방금')
    expect(cards[0].get('.badge').text()).toBe('연결됨')
    expect(cards[1].get('.badge--danger').text()).toBe('끊김')
    expect(cards[1].text()).toContain('agent — · 접속 기록 없음')
    expect(w.find('code.token').exists()).toBe(false)
  })

  it('로딩 중 첫 조회 — Skeleton 2개', () => {
    const w = mountPanel(undefined, true)
    expect(w.findAll('.sk')).toHaveLength(2)
  })

  it('0대면 빈 상태 + 등록 버튼이 등록 Modal 을 연다', async () => {
    const w = mountPanel([])
    expect(w.text()).toContain('등록된 모뎀Pi가 없습니다')
    await button(w, '모뎀Pi 등록').trigger('click')
    expect(w.get('[role="dialog"]').text()).toContain('모뎀Pi ID')
  })

  it('등록 — 형식이 틀리면 막고, 성공하면 토큰을 한 번 보여 주고 changed', async () => {
    const w = mountPanel([m()])
    ;(w.vm as unknown as { openRegister(): void }).openRegister()
    await nextTick()
    await w.get('[role="dialog"] input').setValue('Gonghak 02')
    expect(w.text()).toContain('영문 소문자·숫자·하이픈만, 32자 이내로 적어 주세요.')
    expect(button(w, '등록').attributes('disabled')).toBeDefined()
    await issueToken(w)
    expect(lora.registerModem).toHaveBeenCalledWith('gonghak-02')
    expect(w.get('code.token').text()).toBe('tok-abc')
    expect(w.text()).toContain('이 창을 닫으면 다시 볼 수 없습니다.')
    expect(w.emitted('changed')).toHaveLength(1)
  })

  it('이미 있는 ID(400) — 입력 오류로, Modal 은 그대로', async () => {
    lora.registerModem.mockRejectedValue(new ApiError(400, MESSAGES[400]))
    const w = mountPanel([m()])
    ;(w.vm as unknown as { openRegister(): void }).openRegister()
    await nextTick()
    await w.get('[role="dialog"] input').setValue('gonghak-01')
    await button(w, '등록').trigger('click')
    await flushPromises()
    expect(w.get('[role="dialog"]').text()).toContain('이미 등록된 모뎀Pi ID입니다.')
    expect(w.find('code.token').exists()).toBe(false)
    await w.get('[role="dialog"] input').setValue('gonghak-09')
    expect(w.get('[role="dialog"]').text()).not.toContain('이미 등록된 모뎀Pi ID입니다.')
  })

  it('토큰 재발급 — 확인 Modal 뒤에만 호출, 새 토큰 표시', async () => {
    lora.rotateToken.mockResolvedValue({ modem_id: 'gonghak-01', token: 'tok-new' })
    const w = mountPanel([m()])
    await button(w, '토큰 재발급').trigger('click')
    expect(lora.rotateToken).not.toHaveBeenCalled()
    expect(w.get('[role="dialog"]').text()).toContain(
      '기존 토큰이 즉시 무효가 되어 이 모뎀Pi가 끊깁니다',
    )
    await button(w, '재발급').trigger('click')
    await flushPromises()
    expect(lora.rotateToken).toHaveBeenCalledWith('gonghak-01')
    expect(w.get('code.token').text()).toBe('tok-new')
  })

  it('재발급 404 — 안내 + changed, Modal 닫힘', async () => {
    lora.rotateToken.mockRejectedValue(new ApiError(404, MESSAGES[404]))
    const w = mountPanel([m()])
    await button(w, '토큰 재발급').trigger('click')
    await button(w, '재발급').trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe('이미 삭제된 모뎀Pi입니다. 목록을 새로 불러옵니다.')
    expect(w.emitted('changed')).toHaveLength(1)
    expect(w.find('[role="dialog"]').exists()).toBe(false)
  })

  it('토큰 창은 Esc·배경으로 닫히지 않는다 — 닫기 버튼만 (Review Focus 5)', async () => {
    const w = mountPanel([m()])
    await issueToken(w)
    await w.get('[role="dialog"]').trigger('keydown', { key: 'Escape' })
    expect(w.find('code.token').exists()).toBe(true)
    await w.get('.modal__backdrop').trigger('mousedown')
    expect(w.find('code.token').exists()).toBe(true)
    await button(w, '닫기').trigger('click')
    expect(w.find('code.token').exists()).toBe(false)
  })

  it('복사 — 클립보드에 쓰고 알린다, 실패하면 직접 복사 안내', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    const w = mountPanel([m()])
    await issueToken(w)
    await button(w, '복사').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('tok-abc')
    expect(toasts.value.at(-1)?.message).toBe('복사했습니다.')
    writeText.mockRejectedValueOnce(new Error('denied'))
    await button(w, '복사').trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe(
      '복사하지 못했습니다. 토큰을 직접 선택해 복사해 주세요.',
    )
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin/__tests__/modems.spec.ts`
Expected: FAIL — `Failed to resolve import "@/admin/views/nodes/ModemPanel.vue"`

- [ ] **Step 3: 구현**

`web/src/admin/views/nodes/ModemPanel.vue`
```vue
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Input from '@/components/ui/Input.vue'
import Modal from '@/components/ui/Modal.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import { showToast } from '@/components/ui/toast'
import { loraApi } from '@/api/lora'
import { ApiError } from '@/api/client'
import type { ModemOut, TokenOut } from '@/api/types'
import { formatKst, relativeKo } from '@/lib/time'

defineProps<{ modems?: ModemOut[]; loading: boolean }>()
const emit = defineEmits<{ changed: [] }>()

// 서버 ModemIn 과 같은 규칙 — 소문자·숫자·하이픈, 1~32자
const MODEM_ID = /^[a-z0-9-]{1,32}$/
const FORMAT_MSG = '영문 소문자·숫자·하이픈만, 32자 이내로 적어 주세요.'
const registering = ref(false)
const modemId = ref('')
const serverError = ref('')
const submitting = ref(false)
const validId = computed(() => MODEM_ID.test(modemId.value))
const idError = computed(
  () => serverError.value || (modemId.value && !validId.value ? FORMAT_MSG : ''),
)
watch(modemId, () => (serverError.value = ''))

function openRegister() {
  modemId.value = ''
  serverError.value = ''
  registering.value = true
}
defineExpose({ openRegister })

// 토큰은 이 Modal 에서 한 번만 보인다 — 서버가 다시 알려주지 않는다
const issued = ref<TokenOut | null>(null)

async function submitRegister() {
  if (!validId.value || submitting.value) return
  submitting.value = true
  try {
    issued.value = await loraApi.registerModem(modemId.value)
    registering.value = false
    emit('changed')
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    // 서버: 같은 ID 가 있으면 400(lora_service ValidationError), 형식이 틀리면 422
    if (e.status === 400) serverError.value = '이미 등록된 모뎀Pi ID입니다.'
    else if (e.status === 422) serverError.value = FORMAT_MSG
    else if (e.status !== 401 && e.status !== 403)
      showToast({ tone: 'danger', message: e.message })
  } finally {
    submitting.value = false
  }
}

// 재발급 — 기존 토큰이 즉시 무효 → 그 모뎀Pi 가 끊긴다. 확인 Modal 안에서만
const rotating = ref<string | null>(null)
const rotatingBusy = ref(false)
async function submitRotate() {
  const id = rotating.value
  if (!id || rotatingBusy.value) return
  rotatingBusy.value = true
  try {
    issued.value = await loraApi.rotateToken(id)
    rotating.value = null
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 404) {
      rotating.value = null
      showToast({ message: '이미 삭제된 모뎀Pi입니다. 목록을 새로 불러옵니다.' })
      emit('changed')
    } else if (e.status !== 401 && e.status !== 403)
      showToast({ tone: 'danger', message: e.message })
  } finally {
    rotatingBusy.value = false
  }
}

async function copy() {
  try {
    await navigator.clipboard.writeText(issued.value!.token)
    showToast({ message: '복사했습니다.' })
  } catch {
    // 권한 거부·비보안 컨텍스트(http) — 토큰은 user-select: all 이라 한 번 클릭으로 선택된다
    showToast({ message: '복사하지 못했습니다. 토큰을 직접 선택해 복사해 주세요.' })
  }
}
</script>

<template>
  <section class="block" aria-labelledby="nodes-modem">
    <h2 id="nodes-modem" class="block__title">모뎀Pi</h2>
    <div v-if="loading && !modems" class="modems">
      <Skeleton v-for="i in 2" :key="i" variant="block" width="260px" />
    </div>
    <EmptyState
      v-else-if="modems && modems.length === 0"
      message="등록된 모뎀Pi가 없습니다"
      :actions="[{ label: '모뎀Pi 등록', variant: 'primary', onClick: openRegister }]"
    />
    <ul v-else-if="modems" class="modems">
      <li v-for="md in modems" :key="md.modem_id" class="modem">
        <p class="modem__id">{{ md.modem_id }}</p>
        <p class="modem__meta num">
          agent {{ md.agent_ver ?? '—' }} ·
          <span v-if="md.last_seen_at" :title="formatKst(md.last_seen_at)">{{
            relativeKo(md.last_seen_at)
          }}</span>
          <template v-else>접속 기록 없음</template>
        </p>
        <div class="modem__foot">
          <Badge v-if="md.connected" variant="solid">연결됨</Badge>
          <Badge v-else variant="outline" tone="danger">끊김</Badge>
          <Button variant="ghost" size="sm" @click="rotating = md.modem_id">토큰 재발급</Button>
        </div>
      </li>
    </ul>

    <Modal
      :open="registering"
      title="모뎀Pi 등록"
      size="sm"
      :close-on-backdrop="!modemId"
      @close="registering = false"
    >
      <form @submit.prevent="submitRegister">
        <Input
          v-model="modemId"
          label="모뎀Pi ID"
          hint="예: gonghak-01 — 모뎀Pi 설정의 modem_id 와 같아야 합니다"
          :error="idError || undefined"
          required
        />
      </form>
      <template #footer>
        <Button variant="secondary" @click="registering = false">취소</Button>
        <Button :loading="submitting" :disabled="!validId" @click="submitRegister">등록</Button>
      </template>
    </Modal>

    <Modal :open="!!rotating" title="토큰 재발급" size="sm" @close="rotating = null">
      <p class="block__text">
        {{ rotating }} 의 기존 토큰이 즉시 무효가 되어 이 모뎀Pi가 끊깁니다. 새 토큰을 모뎀Pi
        설정에 넣어야 다시 연결됩니다.
      </p>
      <template #footer>
        <Button variant="secondary" @click="rotating = null">취소</Button>
        <Button variant="danger" :loading="rotatingBusy" @click="submitRotate">재발급</Button>
      </template>
    </Modal>

    <!-- 배경 클릭·Esc 로 닫히지 않는다 (closeOnBackdrop=false 는 Esc 도 막는다) — 토큰은 다시 볼 수 없다 -->
    <Modal :open="!!issued" title="모뎀Pi 토큰" :close-on-backdrop="false" @close="issued = null">
      <p class="block__text">{{ issued?.modem_id }} 의 토큰입니다. 모뎀Pi 설정에 넣으세요.</p>
      <code class="token">{{ issued?.token }}</code>
      <p class="token__warn">이 창을 닫으면 다시 볼 수 없습니다.</p>
      <template #footer>
        <Button variant="secondary" @click="copy">복사</Button>
        <Button @click="issued = null">닫기</Button>
      </template>
    </Modal>
  </section>
</template>

<style scoped>
.block__title {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.block__text {
  margin: 0 0 var(--space-3);
}
.modems {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  margin: 0;
  padding: 0;
  list-style: none;
}
.modem {
  width: 260px;
  padding: var(--space-4);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-md);
}
.modem p {
  margin: 0;
}
.modem__id {
  font-weight: var(--font-weight-bold);
}
.modem__meta {
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
.modem__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: var(--space-3);
}
.token {
  display: block;
  padding: var(--space-3);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-sm);
  background: var(--sunken);
  font-size: var(--font-size-lg);
  word-break: break-all;
  user-select: all;
}
.token__warn {
  margin: var(--space-3) 0 0;
  color: var(--danger);
  font-weight: var(--font-weight-bold);
}
</style>
```

`web/src/admin/views/NodesView.vue` 네 곳을 고친다:
1. import 에 추가: `import ModemPanel from './nodes/ModemPanel.vue'`
2. `const router = useRouter()` 아래에 추가: `const modemPanel = ref<InstanceType<typeof ModemPanel> | null>(null)`
3. 헤더 `시각 브로드캐스트` 버튼 뒤에 추가:
   ```vue
        <Button size="sm" @click="modemPanel?.openRegister()">+ 모뎀Pi 등록</Button>
   ```
4. ESP노드 `<section>` **앞**에 추가:
   ```vue
    <ModemPanel ref="modemPanel" :modems="data?.modems" :loading="loading" @changed="reload" />
   ```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint && pnpm exec prettier --check .`
Expected: PASS (nodes.spec 도 그대로 — 모뎀 목록 `[]` 이면 EmptyState 가 보일 뿐)

- [ ] **Step 5: E2E — 모뎀Pi**

`web/e2e/monitor.spec.ts` 맨 위 import 아래에 추가
```ts
// e2e 는 node 타입 — page.evaluate 콜백은 브라우저에서 돈다
declare const navigator: { clipboard: { readText(): Promise<string> } }
```
파일 끝에 추가
```ts
// ---- 모뎀Pi ----
const modemCard = (id: string) =>
  page
    .getByRole('region', { name: '모뎀Pi', exact: true })
    .getByRole('listitem')
    .filter({ hasText: id })

test('모뎀Pi — 연결 상태 카드, 등록하면 토큰을 한 번만 보여 준다', async () => {
  await expect(modemCard(SEED.modem)).toContainText('연결됨')
  await expect(modemCard(SEED.offlineModem)).toContainText('끊김')
  await expect(modemCard(SEED.offlineModem)).toContainText('접속 기록 없음')
  await page.getByRole('button', { name: '+ 모뎀Pi 등록' }).click()
  await page.getByRole('dialog').getByLabel('모뎀Pi ID').fill('e2e-ui-1')
  await page.getByRole('dialog').getByRole('button', { name: '등록' }).click()
  const code = page.getByRole('dialog').locator('code')
  await expect(code).toBeVisible()
  const token = (await code.textContent())!.trim()
  expect(token.length).toBeGreaterThan(20)
  await expect(page.getByRole('dialog')).toContainText('이 창을 닫으면 다시 볼 수 없습니다.')
  await page.getByRole('dialog').getByRole('button', { name: '복사' }).click()
  await expect(page.getByText('복사했습니다.')).toBeVisible()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(token)
  await shot(page, 'admin-nodes-token-1440')
  await page.keyboard.press('Escape')
  await expect(code).toBeVisible()
  await page.getByRole('dialog').getByRole('button', { name: '닫기' }).click()
  await expect(modemCard('e2e-ui-1')).toContainText('끊김')
})

test('토큰 재발급 — 확인 뒤에만, 새 토큰 표시', async () => {
  await modemCard(SEED.offlineModem).getByRole('button', { name: '토큰 재발급' }).click()
  await expect(page.getByRole('dialog')).toContainText('끊깁니다')
  await page.getByRole('dialog').getByRole('button', { name: '재발급', exact: true }).click()
  await expect(page.getByRole('dialog').locator('code')).toBeVisible()
  await page.getByRole('dialog').getByRole('button', { name: '닫기' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
})
```

- [ ] **Step 6: E2E 실행 + 스크린샷 대조**

Run: **E2E 명령** + ` e2e/monitor.spec.ts`
Expected: `8 passed`. `admin-nodes-1440.png`(Task 6 테스트가 다시 찍는다)·`admin-nodes-token-1440.png` 를 `admin-nodes.md` 와 대조:
- 헤더 오른쪽 끝 `+ 모뎀Pi 등록`(primary). 헤더 아래 `모뎀Pi` 블록이 ESP노드 표 위, 카드가 가로로 나열(폭 260, `line.2` 1px, `radius.md`, 패딩 16).
- 카드: 모뎀 ID 굵게 → `agent 0.4.1 · 방금`(text.3, sm) → `연결됨`(회색 solid) / `끊김`(적색 테두리) + `토큰 재발급`(ghost).
- 토큰 Modal: 배경 딤, 토큰이 `sunken` 상자에 lg 로 크게, 아래 적색 굵은 "이 창을 닫으면 다시 볼 수 없습니다.", 푸터 `복사`(secondary) · `닫기`(primary). 카드·표 어디에도 토큰이 없다.

- [ ] **Step 7: 커밋**

```bash
git add web/src/admin web/e2e/monitor.spec.ts
git commit -m "feat(web): 모뎀Pi 블록 — 연결 상태 카드, 등록·토큰 재발급(확인 Modal), 토큰은 닫기 전 한 번만 표시·복사 + E2E"
```

---

### Task 8: 등록 대기 블록 — 표 · 강의실 배정

**Files:**
- Create: `web/src/admin/views/nodes/PendingPanel.vue`
- Modify: `web/src/admin/views/NodesView.vue`, `web/e2e/monitor.spec.ts`
- Test: `web/src/admin/__tests__/pending.spec.ts`

**Interfaces:**
- Consumes: `loraApi.provision` (Task 2) · `provisionChoices`, `volts` (Task 6 `nodesView.ts`) · `SignalBars` (Task 4) · `Table`·`Select`·`Modal`·`Button`·`EmptyState`·`showToast` · `formatKst`·`relativeKo`.
- Produces: `PendingPanel.vue` props `{ pending?: PendingOut[]; nodes: NodeOut[]; loading: boolean }`, emits `changed`. 루트 `<section aria-labelledby="nodes-pending">`.

화면 규칙(`admin-nodes.md` §등록 대기): 열 `MAC | 모뎀Pi | FW | 배터리 | 신호 | 처음 발견 | 마지막 발견 | [강의실 배정]` · `처음 발견`·`마지막 발견` 나란히 · 빈 상태 "등록을 기다리는 장치가 없습니다." · `강의실 배정` → Modal(건물·호수·노드 번호) → `POST /pending/{mac}/provision`. 선택지는 **기대 노드 목록**에서 — 없는 조합을 고를 수 없다. 이미 노드가 있는 자리는 막지 않되(교체 설치) 알린다.

- [ ] **Step 1: 실패 테스트**

`web/src/admin/__tests__/pending.spec.ts`
```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import PendingPanel from '@/admin/views/nodes/PendingPanel.vue'
import { loraApi } from '@/api/lora'
import { ApiError, MESSAGES } from '@/api/client'
import type { NodeOut, PendingOut } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/lora', () => ({ loraApi: { provision: vi.fn() } }))
const provision = vi.mocked(loraApi.provision)

const node = (over: Partial<NodeOut> = {}): NodeOut => ({
  room_id: 1,
  building_id: 1,
  building: '공학관',
  bld: 'E',
  room: 401,
  unit: 1,
  modem_id: 'm1',
  mac: '0A1B2C3D4E01',
  fw: 3,
  batt_mv: 3980,
  rssi: -71,
  snr: 7.5,
  sched_ver: 41,
  resv_ver: 12,
  exam_ver: 3,
  ident_ver: 2,
  layout: 1,
  clock_stale: false,
  low_batt: false,
  uptime_h: 10,
  last_seen_at: new Date('2026-09-25T00:00:00Z'),
  last_ack_at: null,
  last_status_at: null,
  sync_state: 'synced',
  warnings: [],
  ...over,
})
const NODES: NodeOut[] = [
  node(),
  node({ room_id: 2, room: 402, unit: 1, mac: '0A1B2C3D4E02' }),
  node({ room_id: 2, room: 402, unit: 2, mac: null, last_seen_at: null, warnings: ['unseen'] }),
  node({ room_id: 3, building_id: 2, building: '사회관', bld: 'S', room: 101, mac: null }),
]
const p = (over: Partial<PendingOut> = {}): PendingOut => ({
  mac: 'A1B2C3D4E5F6',
  modem_id: 'gonghak-01',
  fw: 3,
  batt_mv: 4100,
  rssi: -68,
  first_seen_at: new Date('2026-09-24T22:00:00Z'),
  last_seen_at: new Date('2026-09-25T00:59:00Z'),
  ...over,
})
const mountPanel = (pending: PendingOut[] | undefined, nodes = NODES) =>
  mount(PendingPanel, {
    props: { pending, nodes, loading: false },
    global: { stubs: { teleport: true } },
  })
const button = (w: VueWrapper, text: string) => w.findAll('button').find((b) => b.text() === text)!
const selects = (w: VueWrapper) => w.findAll('[role="dialog"] select')
const optionTexts = (w: VueWrapper, i: number) =>
  selects(w)[i]
    .findAll('option')
    .map((o) => o.text())

beforeEach(() => {
  toasts.value.forEach((t) => dismissToast(t.id))
  provision.mockReset().mockResolvedValue({ outbox_ids: [77], id: null })
})

describe('PendingPanel', () => {
  it('행 — MAC · 모뎀 · FW · V · dBm, 처음·마지막 발견 KST 툴팁', () => {
    const w = mountPanel([p()])
    const row = w.get('tbody tr')
    expect(row.text()).toContain('A1B2C3D4E5F6')
    expect(row.text()).toContain('gonghak-01')
    expect(row.text()).toContain('4.10 V')
    expect(row.text()).toContain('−68 dBm')
    const titles = row.findAll('span[title]').map((s) => s.attributes('title'))
    expect(titles).toEqual(['2026-09-25 07:00', '2026-09-25 09:59'])
  })

  it('비어 있으면(정상) 빈 상태 문구', () => {
    expect(mountPanel([]).text()).toContain('등록을 기다리는 장치가 없습니다.')
  })

  it('배정 — 건물 → 호수 → 노드, 1대뿐인 방은 자동 선택, 사용 중 표시, 제출', async () => {
    const w = mountPanel([p()])
    await button(w, '강의실 배정').trigger('click')
    expect(button(w, '배정').attributes('disabled')).toBeDefined()
    expect(optionTexts(w, 0)).toEqual(['건물 선택', '공학관', '사회관'])
    await selects(w)[0].setValue('E')
    expect(optionTexts(w, 1)).toEqual(['호수 선택', '401호', '402호'])
    await selects(w)[1].setValue('401')
    expect((selects(w)[2].element as HTMLSelectElement).value).toBe('1')
    expect(w.text()).toContain('이 자리에는 이미 노드 0A1B2C3D4E01 가 있습니다.')
    await selects(w)[1].setValue('402')
    expect(optionTexts(w, 2)).toEqual(['노드 선택', '1번 노드 — 사용 중', '2번 노드'])
    await selects(w)[2].setValue('2')
    expect(w.text()).not.toContain('이 자리에는 이미 노드')
    await button(w, '배정').trigger('click')
    await flushPromises()
    expect(provision).toHaveBeenCalledWith('A1B2C3D4E5F6', { bld: 'E', room: 402, unit: 2 })
    expect(toasts.value.at(-1)?.message).toBe(
      '공학관 402호에 배정했습니다. 장치가 다음에 깨어나면 적용됩니다.',
    )
    expect(w.emitted('changed')).toHaveLength(1)
    expect(w.find('[role="dialog"]').exists()).toBe(false)
  })

  it('건물을 바꾸면 호수·노드 선택이 풀린다', async () => {
    const w = mountPanel([p()])
    await button(w, '강의실 배정').trigger('click')
    await selects(w)[0].setValue('E')
    await selects(w)[1].setValue('401')
    await selects(w)[0].setValue('S')
    expect((selects(w)[1].element as HTMLSelectElement).value).toBe('')
    expect(button(w, '배정').attributes('disabled')).toBeDefined()
  })

  it('404(다른 관리자가 먼저 배정·방 삭제) — 안내 + changed, Modal 닫힘', async () => {
    provision.mockRejectedValue(new ApiError(404, MESSAGES[404]))
    const w = mountPanel([p()])
    await button(w, '강의실 배정').trigger('click')
    await selects(w)[0].setValue('E')
    await selects(w)[1].setValue('401')
    await button(w, '배정').trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe(
      '장치 또는 강의실이 사라졌습니다. 목록을 새로 불러옵니다.',
    )
    expect(w.emitted('changed')).toHaveLength(1)
    expect(w.find('[role="dialog"]').exists()).toBe(false)
  })

  it('강의실이 하나도 없으면 먼저 등록하라고, 배정 버튼 잠금', async () => {
    const w = mountPanel([p()], [])
    await button(w, '강의실 배정').trigger('click')
    expect(w.get('[role="dialog"]').text()).toContain('먼저 건물 · 강의실을 등록해 주세요.')
    expect(button(w, '배정').attributes('disabled')).toBeDefined()
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin/__tests__/pending.spec.ts`
Expected: FAIL — `Failed to resolve import "@/admin/views/nodes/PendingPanel.vue"`

- [ ] **Step 3: 구현**

`web/src/admin/views/nodes/PendingPanel.vue`
```vue
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Modal from '@/components/ui/Modal.vue'
import Select from '@/components/ui/Select.vue'
import Table from '@/components/ui/Table.vue'
import { showToast } from '@/components/ui/toast'
import SignalBars from '@/components/domain/SignalBars.vue'
import { loraApi } from '@/api/lora'
import { ApiError } from '@/api/client'
import type { NodeOut, PendingOut } from '@/api/types'
import { formatKst, relativeKo } from '@/lib/time'
import { provisionChoices, volts } from '../../nodesView'

const props = defineProps<{ pending?: PendingOut[]; nodes: NodeOut[]; loading: boolean }>()
const emit = defineEmits<{ changed: [] }>()

const COLUMNS: {
  key: string
  label: string
  width?: string
  align?: 'left' | 'right' | 'center'
}[] = [
  { key: 'mac', label: 'MAC', width: '128px' },
  { key: 'modem_id', label: '모뎀Pi', width: '128px' },
  { key: 'fw', label: 'FW', width: '56px', align: 'right' },
  { key: 'batt', label: '배터리', width: '88px', align: 'right' },
  { key: 'rssi', label: '신호', width: '112px' },
  { key: 'first', label: '처음 발견', width: '104px' },
  { key: 'last', label: '마지막 발견' },
  { key: 'actions', label: '작업', width: '112px' },
]
const asP = (row: Record<string, unknown>) => row as unknown as PendingOut

// 배정 Modal — 선택지는 기대 노드(rooms × units)에서만: 없는 (bld, room, unit) 을 고를 수 없다
const target = ref<PendingOut | null>(null)
const bld = ref('')
const room = ref<number | ''>('')
const unit = ref<number | ''>('')
const choices = computed(() => provisionChoices(props.nodes, bld.value, room.value))
watch(bld, () => (room.value = ''))
// 노드가 1대뿐인 방은 번호를 고를 필요가 없다
watch(room, () => {
  const u = choices.value.units
  unit.value = u.length === 1 ? u[0].value : ''
})
const occupied = computed(() => choices.value.units.find((u) => u.value === unit.value)?.mac ?? null)
const ready = computed(() => !!bld.value && room.value !== '' && unit.value !== '')
const busy = ref(false)

function open(p: PendingOut) {
  bld.value = ''
  room.value = ''
  unit.value = ''
  target.value = p
}

async function submit() {
  const p = target.value
  if (!p || busy.value || !ready.value) return
  const body = { bld: bld.value, room: room.value as number, unit: unit.value as number }
  const name = choices.value.buildings.find((b) => b.value === body.bld)?.label ?? body.bld
  busy.value = true
  try {
    await loraApi.provision(p.mac, body)
    target.value = null
    // 서버는 pending 행을 바로 지우지 않는다 — 장치가 SET_ROOM 을 받고 응답하면 ESP노드 표로 옮겨 간다
    showToast({
      message: `${name} ${body.room}호에 배정했습니다. 장치가 다음에 깨어나면 적용됩니다.`,
    })
    emit('changed')
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 404) {
      target.value = null
      showToast({ message: '장치 또는 강의실이 사라졌습니다. 목록을 새로 불러옵니다.' })
      emit('changed')
    } else if (e.status !== 401 && e.status !== 403)
      showToast({ tone: 'danger', message: e.message })
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="block" aria-labelledby="nodes-pending">
    <h2 id="nodes-pending" class="block__title">등록 대기</h2>
    <Table
      :columns="COLUMNS"
      :rows="(pending ?? []) as unknown as Record<string, unknown>[]"
      row-key="mac"
      :loading="loading && !pending"
    >
      <template #empty><EmptyState message="등록을 기다리는 장치가 없습니다." /></template>
      <template #cell-batt="{ row }"
        ><span class="num">{{ volts(asP(row).batt_mv) }}</span></template
      >
      <template #cell-rssi="{ row }"><SignalBars :rssi="asP(row).rssi" /></template>
      <template #cell-first="{ row }">
        <span :title="formatKst(asP(row).first_seen_at)">{{
          relativeKo(asP(row).first_seen_at)
        }}</span>
      </template>
      <template #cell-last="{ row }">
        <span :title="formatKst(asP(row).last_seen_at)">{{
          relativeKo(asP(row).last_seen_at)
        }}</span>
      </template>
      <template #cell-actions="{ row }">
        <Button size="sm" @click="open(asP(row))">강의실 배정</Button>
      </template>
    </Table>

    <Modal
      :open="!!target"
      title="강의실 배정"
      size="sm"
      :close-on-backdrop="!bld"
      @close="target = null"
    >
      <p class="block__text num">장치 {{ target?.mac }}</p>
      <p v-if="!choices.buildings.length" class="block__text">
        먼저 건물 · 강의실을 등록해 주세요.
      </p>
      <div v-else class="assign">
        <Select v-model="bld" :options="choices.buildings" label="건물" placeholder="건물 선택" />
        <Select
          v-model="room"
          :options="choices.rooms"
          label="호수"
          placeholder="호수 선택"
          :disabled="!bld"
        />
        <Select
          v-model="unit"
          :options="choices.units"
          label="노드"
          placeholder="노드 선택"
          :disabled="room === ''"
        />
        <p v-if="occupied" class="assign__hint">이 자리에는 이미 노드 {{ occupied }} 가 있습니다.</p>
      </div>
      <template #footer>
        <Button variant="secondary" @click="target = null">취소</Button>
        <Button :loading="busy" :disabled="!ready" @click="submit">배정</Button>
      </template>
    </Modal>
  </section>
</template>

<style scoped>
.block__title {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.block__text {
  margin: 0 0 var(--space-3);
}
.assign {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.assign__hint {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
</style>
```

`web/src/admin/views/NodesView.vue` 두 곳을 고친다:
1. import 에 추가: `import PendingPanel from './nodes/PendingPanel.vue'`
2. ESP노드 `</section>` **뒤**에 추가:
   ```vue
    <PendingPanel
      :pending="data?.pending"
      :nodes="nodes"
      :loading="loading"
      @changed="reload"
    />
   ```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint && pnpm exec prettier --check .`
Expected: PASS

- [ ] **Step 5: E2E — 등록 대기**

`web/e2e/monitor.spec.ts` 파일 끝에 추가
```ts
// ---- 등록 대기 ----
test('등록 대기 → 강의실 배정', async () => {
  const row = page
    .getByRole('region', { name: '등록 대기', exact: true })
    .locator('tbody tr', { hasText: SEED.mac })
  await expect(row).toContainText(SEED.modem)
  await expect(row).toContainText('4.10 V')
  await expect(row).toContainText('−68 dBm')
  await row.getByRole('button', { name: '강의실 배정' }).click()
  const d = page.getByRole('dialog')
  await d.getByLabel('건물').selectOption({ label: SEED.building })
  await d.getByLabel('호수').selectOption({ label: '402호' })
  await expect(d.getByLabel('노드').locator('option')).toHaveText([
    '노드 선택',
    '1번 노드 — 사용 중',
    '2번 노드',
  ])
  await d.getByLabel('노드').selectOption({ label: '2번 노드' })
  await shot(page, 'admin-nodes-provision-1440')
  await d.getByRole('button', { name: '배정', exact: true }).click()
  await expect(
    page.getByText(`${SEED.building} 402호에 배정했습니다. 장치가 다음에 깨어나면 적용됩니다.`),
  ).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
})
```

- [ ] **Step 6: E2E 실행 + 스크린샷 대조**

Run: **E2E 명령** + ` e2e/monitor.spec.ts`
Expected: `9 passed`. `admin-nodes-1440.png`(fullPage)·`admin-nodes-provision-1440.png` 를 `admin-nodes.md` 와 대조:
- 블록 순서 `모뎀Pi` → `ESP노드` → `등록 대기`, 사이 24px. 1440×900 에서 `등록 대기` 는 스크롤 아래(스펙: 전체 높이 ~1120).
- 등록 대기 열 `MAC | 모뎀Pi | FW | 배터리 | 신호 | 처음 발견 | 마지막 발견 | 작업`, `처음 발견`·`마지막 발견` 이 나란히, `강의실 배정` primary sm.
- 배정 Modal 폭 400(sm), `장치 A1B2C3D4E5F6` 아래 `건물`·`호수`·`노드` Select 세로 나열, 푸터 `취소`(secondary) · `배정`(primary).

- [ ] **Step 7: 커밋**

```bash
git add web/src/admin web/e2e/monitor.spec.ts
git commit -m "feat(web): 등록 대기 블록 — 발견된 장치 표, 기대 노드에서만 고르는 강의실 배정 Modal, 404 재조회 + E2E"
```

---

### Task 9: 전송 현황 화면 — KPI · 분포 · 최근 전송 · 60 s · 기본 라우트

**Files:**
- Create: `web/src/admin/dashboardView.ts`, `web/src/admin/views/DashboardView.vue`
- Modify: `web/src/admin/router.ts`, `web/src/admin/AdminShell.vue`, `web/src/admin/__tests__/shell.spec.ts`, `web/e2e/login.spec.ts`, `web/e2e/admin-shell.spec.ts`, `web/e2e/monitor.spec.ts`
- Test: `web/src/admin/__tests__/dashboard.spec.ts`

**Interfaces:**
- Consumes: `adminApi.{latency, failed}`, `FAILED_LIMIT`, `loraApi.recentOutbox` (Task 2) · `kstDateStr`, `LastRefreshed` (Task 3) · `OutboxDot` (Task 4) · `Histogram`, `SERIES_COLORS`, `HistogramSeries`, `HistogramBucket` (Task 5) · `StatTile`·`Legend`·`Table`·`Select`·`Skeleton`·`EmptyState`·`showToast` (F1).
- Produces (`admin/dashboardView.ts`): `PERIODS: { value: number; label: string }[]` · `RECENT_LIMIT = 7` · `fmt1(v: number): string` · `binLabel(b: LatencyBin): string` · `interface Kpi { label; value; unit?; sub?; tone: 'neutral'|'danger' }` · `kpis(l: LatencyOut, failed: number, days: number): Kpi[]` · `histogram(slot: LatencyOut, resv: LatencyOut): { buckets: HistogramBucket[]; marker?: { at: number; label: string } }` · `interface RecentRow { id; time; when; room; kind; delay; slow; failed; state: OutboxState }` · `recentRows(list: OutboxOut[]): RecentRow[]`.
- 라우트 `/dashboard`, 메뉴 `전송 현황`(노드 상태 아래), `''` → `/dashboard`.

화면 규칙(`admin-dashboard.md`): 1440×900 **한 화면**(스크롤 없음) · 상단 `반영 지연` + 마지막 갱신 + 기간 Select · KPI 4(p50 · 30초 이내 · 90초 이내 · 실패, 값만 danger, 화살표 없음, 목표와 판정을 문장으로) · 본문 1.7 : 1(분포 차트 : 최근 전송 7행) · 차트 계열 `SLOT_SET`(series.1)·`RESV_SET`(series.2), 범례는 제목 오른쪽, SLA 30초 점선 · 최근 전송: 30초 넘는 지연만 bold(적색 아님), 실패는 값·점 danger, 대기는 `대기` + 빈 원 · 로딩 Skeleton(KPI 4 · 차트 · 표 5행) · 전송 0건이면 KPI `—`, 차트 자리 "아직 전송된 작업이 없습니다" · 60초 자동 새로고침.

- [ ] **Step 1: 실패 테스트**

`web/src/admin/__tests__/dashboard.spec.ts`
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import DashboardView from '@/admin/views/DashboardView.vue'
import { binLabel, histogram, kpis, recentRows } from '@/admin/dashboardView'
import { adminApi } from '@/api/admin'
import { loraApi } from '@/api/lora'
import { ApiError, MESSAGES } from '@/api/client'
import type { FailedOut, LatencyOut, OutboxOut } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/admin', () => ({ FAILED_LIMIT: 500, adminApi: { latency: vi.fn(), failed: vi.fn() } }))
vi.mock('@/api/lora', () => ({ loraApi: { recentOutbox: vi.fn() } }))
const latencyApi = vi.mocked(adminApi.latency)
const failedApi = vi.mocked(adminApi.failed)
const recentApi = vi.mocked(loraApi.recentOutbox)

const BINS = [0, 10, 20, 30, 45, 60, 90, 120].map((ge, i, a) => ({
  ge,
  lt: a[i + 1] ?? null,
  count: 0,
}))
const lat = (over: Partial<LatencyOut> = {}): LatencyOut => ({
  n: 8,
  bins: BINS,
  p50: 25,
  p95: 50,
  max: 95,
  within_30s: 0.625,
  within_90s: 0.875,
  ...over,
})
const counts = (c: number[]) => lat({ bins: BINS.map((b, i) => ({ ...b, count: c[i] ?? 0 })) })
const EMPTY = lat({ n: 0, p50: null, p95: null, max: null, within_30s: 0, within_90s: 0 })
const o = (over: Partial<OutboxOut> = {}): OutboxOut => ({
  id: 1,
  modem_id: 'm1',
  bld: 'E',
  room: 401,
  unit: 1,
  type: 'SLOT_SET',
  payload: {},
  priority: 3,
  new_ver: 1,
  state: 'acked',
  attempts: 1,
  ack_status: 0,
  ack_detail: null,
  rssi: null,
  snr: null,
  last_error: null,
  created_at: new Date('2026-09-25T00:00:00Z'),
  dispatched_at: null,
  finished_at: new Date('2026-09-25T00:00:31.5Z'),
  ...over,
})

let visibility: DocumentVisibilityState = 'visible'
beforeEach(() => {
  visibility = 'visible'
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => visibility })
  toasts.value.forEach((t) => dismissToast(t.id))
  latencyApi.mockReset().mockImplementation(async ({ type }) =>
    type === 'SLOT_SET'
      ? counts([1, 1, 2, 0, 0, 0, 1, 0])
      : type === 'RESV_SET'
        ? counts([0, 1, 0, 1, 1, 0, 0, 0])
        : lat(),
  )
  failedApi.mockReset().mockResolvedValue([{} as FailedOut])
  recentApi.mockReset().mockResolvedValue([o({ id: 1 }), o({ id: 2, state: 'queued', finished_at: null })])
})
afterEach(() => vi.useRealTimers())

describe('dashboardView', () => {
  it('kpis — 값·단위·목표와 판정 문장, 실패는 값만 danger', () => {
    expect(kpis(lat(), 1, 7)).toEqual([
      { label: 'p50 반영 지연', value: '25', unit: '초', sub: 'p95 50초 · 최대 95초', tone: 'neutral' },
      { label: '30초 이내 비율', value: '62.5', unit: '%', sub: '목표 95% · 미달', tone: 'neutral' },
      { label: '90초 이내 비율', value: '87.5', unit: '%', sub: '목표 전부 · 미달', tone: 'neutral' },
      { label: '전송 실패', value: '1', unit: '건', sub: '최근 7일 · 모든 작업', tone: 'danger' },
    ])
    const ok = kpis(lat({ within_30s: 0.95, within_90s: 1, p50: 18.44 }), 0, 30)
    expect(ok[0].value).toBe('18.4')
    expect(ok[1].sub).toBe('목표 95% · 충족')
    expect(ok[2].sub).toBe('목표 전부 · 충족')
    expect(ok[3]).toMatchObject({ value: '0', tone: 'neutral', sub: '최근 30일 · 모든 작업' })
  })

  it('kpis — 전송 0건이면 —, 0% 가 아니다 (Review Focus 3)', () => {
    const k = kpis(EMPTY, 0, 7)
    expect(k.slice(0, 3).map((x) => [x.value, x.unit])).toEqual([
      ['—', undefined],
      ['—', undefined],
      ['—', undefined],
    ])
    expect(k.map((x) => x.sub)).toEqual(['전송 기록 없음', '목표 95%', '목표 전부', '최근 7일 · 모든 작업'])
  })

  it('kpis — 실패가 상한(500)이면 500+', () => {
    expect(kpis(lat(), 500, 90)[3].value).toBe('500+')
  })

  it('binLabel · histogram — 서버 구간 그대로, SLA 선은 ge=30 경계', () => {
    expect(binLabel({ ge: 20, lt: 30, count: 0 })).toBe('20–30')
    expect(binLabel({ ge: 120, lt: null, count: 0 })).toBe('120+')
    const h = histogram(counts([1, 0, 2]), counts([0, 3]))
    expect(h.buckets.slice(0, 3)).toEqual([
      { label: '0–10', values: [1, 0] },
      { label: '10–20', values: [0, 3] },
      { label: '20–30', values: [2, 0] },
    ])
    expect(h.marker).toEqual({ at: 3, label: 'SLA 30초' })
  })

  it('recentRows — 최신이 위, 지연·대기·실패 문구, 30초 초과만 slow, 시각은 KST', () => {
    const rows = recentRows([
      o({ id: 1 }),
      o({ id: 2, state: 'failed' }),
      o({ id: 3, type: 'RESV_SET', room: 402, state: 'queued', finished_at: null }),
      o({ id: 4, type: 'SET_ROOM', state: 'cancelled', finished_at: null }),
    ])
    expect(rows.map((r) => [r.id, r.room, r.kind, r.delay, r.slow, r.failed])).toEqual([
      [4, 'E 401', '강의실 배정', '취소', false, false],
      [3, 'E 402', '예약', '대기', false, false],
      [2, 'E 401', '시간표', '실패', false, true],
      [1, 'E 401', '시간표', '31.5초', true, false],
    ])
    expect(rows[3]).toMatchObject({ time: '09:00', when: '2026-09-25 09:00', state: 'acked' })
  })
})

describe('DashboardView', () => {
  it('KPI 4 · 분포(막대 7개·SLA 선·범례) · 최근 전송(최신 위)', async () => {
    const w = mount(DashboardView)
    await flushPromises()
    const tiles = w.findAll('.stat')
    expect(tiles).toHaveLength(4)
    expect(tiles[0].text()).toContain('25초')
    expect(tiles[3].get('.stat__value').classes()).toContain('stat__value--danger')
    expect(w.findAll('svg.hist path')).toHaveLength(7)
    expect(w.get('.hist__marker text').text()).toBe('SLA 30초')
    expect(w.findAll('.legend__item').map((l) => l.text())).toEqual(['SLOT_SET', 'RESV_SET'])
    expect(w.findAll('tbody tr').map((r) => r.findAll('td')[2].text())).toEqual(['대기', '31.5초'])
    expect(w.get('tbody tr:last-child .dash__slow').text()).toBe('31.5초')
    w.unmount()
  })

  it('전송 0건 — KPI 는 —, 차트 자리에 빈 상태, 막대 없음', async () => {
    latencyApi.mockResolvedValue(EMPTY)
    failedApi.mockResolvedValue([])
    recentApi.mockResolvedValue([])
    const w = mount(DashboardView)
    await flushPromises()
    expect(w.findAll('.stat__value').map((v) => v.text())).toEqual(['—', '—', '—', '0건'])
    expect(w.text()).toContain('아직 전송된 작업이 없습니다')
    expect(w.find('svg.hist').exists()).toBe(false)
    w.unmount()
  })

  it('기간 — 기본 최근 7일(KST 날짜), 30일로 바꾸면 from 이 29일 앞', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-09-24T16:00:00Z')) // KST 9/25 01:00 — UTC 로는 아직 9/24
    const w = mount(DashboardView)
    await flushPromises()
    expect(latencyApi).toHaveBeenCalledWith({ from: '2026-09-19', to: '2026-09-25', type: 'all' })
    expect(failedApi).toHaveBeenCalledWith(7)
    expect(recentApi).toHaveBeenCalledWith(7)
    await w.get('select').setValue('30')
    await flushPromises()
    expect(latencyApi).toHaveBeenLastCalledWith({
      from: '2026-08-27',
      to: '2026-09-25',
      type: 'RESV_SET',
    })
    expect(failedApi).toHaveBeenLastCalledWith(30)
    w.unmount()
  })

  it('60초마다 다시 읽고, 떠나면 멈춘다', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    const w = mount(DashboardView)
    await flushPromises()
    expect(failedApi).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(60_000)
    await flushPromises()
    expect(failedApi).toHaveBeenCalledTimes(2)
    w.unmount()
    vi.advanceTimersByTime(180_000)
    await flushPromises()
    expect(failedApi).toHaveBeenCalledTimes(2)
  })

  it('갱신 실패 — 숫자를 지우지 않고 Toast 는 한 번 (Review Focus 1)', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    const w = mount(DashboardView)
    await flushPromises()
    failedApi.mockRejectedValue(new ApiError(0, MESSAGES[0]))
    for (let i = 0; i < 3; i++) {
      vi.advanceTimersByTime(60_000)
      await flushPromises()
    }
    expect(w.findAll('.stat')[0].text()).toContain('25초')
    expect(toasts.value.filter((t) => t.tone === 'danger')).toHaveLength(1)
    w.unmount()
  })
})
```

`web/src/admin/__tests__/shell.spec.ts` 를 고친다:
1. `beforeEach` 첫 줄에 추가 — 대시보드가 부르는 API 가 끝나지 않게(이 테스트는 셸만 본다):
   ```ts
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})))
   ```
2. 첫 `it`(Task 6 에서 바꾼 `'/ 는 /users 로, 메뉴 순서 · 회원 활성 · 대기 건수 배지'`)를 통째로 바꾼다:
   ```ts
  it('/ 는 /dashboard 로, 메뉴 순서(#46) · 전송 현황 활성 · 회원 대기 건수', async () => {
    const { w, router } = await mountApp('/')
    expect(router.currentRoute.value.path).toBe('/dashboard')
    expect(list).toHaveBeenCalledWith('pending_approval')
    const links = w.findAll('nav a')
    expect(links.map((a) => a.text().replace(/\d+/g, '').trim())).toEqual([
      '노드 상태',
      '전송 현황',
      '회원',
    ])
    expect(links[1].attributes('aria-current')).toBe('page')
    expect(links[2].text()).toContain('2')
    expect(w.text()).toContain('관리자1')
  })
   ```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin`
Expected: FAIL — `Failed to resolve import "@/admin/views/DashboardView.vue"`, shell.spec `expected '/users' to be '/dashboard'`

- [ ] **Step 3: 구현**

`web/src/admin/dashboardView.ts`
```ts
import { FAILED_LIMIT } from '@/api/admin'
import type { LatencyBin, LatencyOut, OutboxOut, OutboxState } from '@/api/types'
import type { HistogramBucket } from '@/components/chart/Histogram.vue'
import { formatHm, formatKst } from '@/lib/time'

/** 기간 — 기본은 시안의 최근 7일. 서버 상한 90일 (S10 §4.3) */
export const PERIODS = [
  { value: 7, label: '최근 7일' },
  { value: 30, label: '최근 30일' },
  { value: 90, label: '최근 90일' },
]
export const RECENT_LIMIT = 7

const nf = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 1 })
/** 소수 한 자리까지, 천 단위 쉼표 — 25 → "25", 18.44 → "18.4", 1234 → "1,234" */
export const fmt1 = (v: number) => nf.format(v)

/** 서버 bin 경계 그대로 — 화면이 버킷을 만들지 않는다 (admin-dashboard.md) */
export const binLabel = (b: LatencyBin) => (b.lt == null ? `${b.ge}+` : `${b.ge}–${b.lt}`)

export interface Kpi {
  label: string
  value: string
  unit?: string
  sub?: string
  tone: 'neutral' | 'danger'
}

/** KPI 4 — 추세 화살표 없이 목표와 판정을 문장으로. 전송 0건이면 — (0건과 0%는 다른 말이다) */
export function kpis(l: LatencyOut, failed: number, days: number): Kpi[] {
  const has = l.n > 0
  const pct = (r: number) => fmt1(r * 100)
  return [
    has
      ? {
          label: 'p50 반영 지연',
          value: fmt1(l.p50 ?? 0),
          unit: '초',
          sub: `p95 ${fmt1(l.p95 ?? 0)}초 · 최대 ${fmt1(l.max ?? 0)}초`,
          tone: 'neutral',
        }
      : { label: 'p50 반영 지연', value: '—', sub: '전송 기록 없음', tone: 'neutral' },
    has
      ? {
          label: '30초 이내 비율',
          value: pct(l.within_30s),
          unit: '%',
          sub: `목표 95% · ${l.within_30s >= 0.95 ? '충족' : '미달'}`,
          tone: 'neutral',
        }
      : { label: '30초 이내 비율', value: '—', sub: '목표 95%', tone: 'neutral' },
    // 웨이크 수신률 대신 (서버 지표 없음 — spec §9)
    has
      ? {
          label: '90초 이내 비율',
          value: pct(l.within_90s),
          unit: '%',
          sub: `목표 전부 · ${l.within_90s >= 1 ? '충족' : '미달'}`,
          tone: 'neutral',
        }
      : { label: '90초 이내 비율', value: '—', sub: '목표 전부', tone: 'neutral' },
    {
      label: '전송 실패',
      value: failed >= FAILED_LIMIT ? `${fmt1(FAILED_LIMIT)}+` : fmt1(failed),
      unit: '건',
      sub: `최근 ${days}일 · 모든 작업`,
      tone: failed > 0 ? 'danger' : 'neutral',
    },
  ]
}

/** 두 계열(SLOT_SET·RESV_SET)을 bucket 별로 묶고, SLA 30초 선은 ge=30 bin 의 왼쪽 경계 */
export function histogram(slot: LatencyOut, resv: LatencyOut) {
  const buckets: HistogramBucket[] = slot.bins.map((b, i) => ({
    label: binLabel(b),
    values: [b.count, resv.bins[i]?.count ?? 0],
  }))
  const at = slot.bins.findIndex((b) => b.ge === 30)
  return { buckets, marker: at >= 0 ? { at, label: 'SLA 30초' } : undefined }
}

const TYPE_LABEL: Record<string, string> = {
  SLOT_SET: '시간표',
  SLOT_DEL: '시간표 삭제',
  DAY_CLEAR: '하루 비움',
  RESV_SET: '예약',
  RESV_DEL: '예약 삭제',
  EXAM_SET: '시험기간',
  EXAM_DEL: '시험기간 삭제',
  FILE: '전체 동기화',
  CMD: '명령',
  SET_ROOM: '강의실 배정',
}

export interface RecentRow {
  id: number
  time: string
  when: string
  room: string
  kind: string
  delay: string
  slow: boolean
  failed: boolean
  state: OutboxState
}

/** 최근 전송 — 서버는 id 오름차순, 화면은 최신이 위. 지연은 acked 만(서버 analytics 와 같은 식: finished − created, 음수 0) */
export function recentRows(list: OutboxOut[]): RecentRow[] {
  return [...list].reverse().map((o) => {
    const secs =
      o.state === 'acked' && o.finished_at
        ? Math.max(0, (o.finished_at.getTime() - o.created_at.getTime()) / 1000)
        : null
    return {
      id: o.id,
      time: formatHm(o.created_at),
      when: formatKst(o.created_at),
      room: `${o.bld} ${o.room}`,
      kind: TYPE_LABEL[o.type] ?? o.type,
      delay:
        secs != null
          ? `${fmt1(secs)}초`
          : o.state === 'failed'
            ? '실패'
            : o.state === 'cancelled'
              ? '취소'
              : '대기',
      // 느린 것은 실패가 아니다 — bold 로만 (적색 아님)
      slow: secs != null && secs > 30,
      failed: o.state === 'failed',
      state: o.state,
    }
  })
}
```

`web/src/admin/views/DashboardView.vue`
```vue
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Legend from '@/components/ui/Legend.vue'
import Select from '@/components/ui/Select.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import StatTile from '@/components/ui/StatTile.vue'
import Table from '@/components/ui/Table.vue'
import { showToast } from '@/components/ui/toast'
import Histogram, { SERIES_COLORS, type HistogramSeries } from '@/components/chart/Histogram.vue'
import OutboxDot from '@/components/domain/OutboxDot.vue'
import { adminApi } from '@/api/admin'
import { loraApi } from '@/api/lora'
import { useResource } from '@/lib/useResource'
import { usePolling } from '@/lib/usePolling'
import { kstDateStr } from '@/lib/time'
import LastRefreshed from '../LastRefreshed.vue'
import {
  PERIODS,
  RECENT_LIMIT,
  histogram,
  kpis,
  recentRows,
  type RecentRow,
} from '../dashboardView'

const SERIES: HistogramSeries = [{ label: 'SLOT_SET' }, { label: 'RESV_SET' }]
const LEGEND = [
  { label: 'SLOT_SET', color: SERIES_COLORS[0] },
  { label: 'RESV_SET', color: SERIES_COLORS[1] },
]

const days = ref(7)
// 한 번에 읽어 한 시각으로 — KPI(all)·분포(계열별 2)·실패·최근 전송
const { data, error, loading, refreshedAt, reload } = useResource(
  async () => {
    const d = days.value
    const now = new Date()
    const range = { from: kstDateStr(now, -(d - 1)), to: kstDateStr(now) }
    const [all, slot, resv, failed, recent] = await Promise.all([
      adminApi.latency({ ...range, type: 'all' }),
      adminApi.latency({ ...range, type: 'SLOT_SET' }),
      adminApi.latency({ ...range, type: 'RESV_SET' }),
      adminApi.failed(d),
      loraApi.recentOutbox(RECENT_LIMIT),
    ])
    return { days: d, all, slot, resv, failed: failed.length, recent }
  },
  { deps: days },
)
// 전시 중 켜 두는 화면 — 60초 (숨김이면 정지, 떠나면 해제)
usePolling(reload, 60_000)

watch(error, (e, prev) => {
  if (e && !prev && e.status !== 401 && e.status !== 403)
    showToast({
      tone: 'danger',
      message: e.message,
      action: { label: '재시도', onClick: () => void reload() },
    })
})

const tiles = computed(() =>
  data.value ? kpis(data.value.all, data.value.failed, data.value.days) : [],
)
const hist = computed(() => (data.value ? histogram(data.value.slot, data.value.resv) : null))
const recent = computed(() => (data.value ? recentRows(data.value.recent) : []))
const r = (row: Record<string, unknown>) => row as unknown as RecentRow
const COLUMNS = [
  { key: 'time', label: '시각', width: '64px' },
  { key: 'room', label: '강의실' },
  { key: 'delay', label: '지연', width: '72px', align: 'right' as const },
  { key: 'state', label: '상태', width: '48px', align: 'center' as const },
]
</script>

<template>
  <main class="dash">
    <header class="dash__head">
      <h1 class="dash__title">반영 지연</h1>
      <LastRefreshed :at="refreshedAt" />
      <label class="dash__filter">
        <span>기간</span>
        <Select v-model="days" :options="PERIODS" size="sm" />
      </label>
    </header>

    <div class="dash__kpis">
      <template v-if="data">
        <StatTile v-for="k in tiles" :key="k.label" v-bind="k" />
      </template>
      <template v-else>
        <Skeleton v-for="i in 4" :key="i" variant="block" />
      </template>
    </div>

    <div class="dash__body">
      <section class="card" aria-labelledby="dash-hist">
        <div class="card__head">
          <h2 id="dash-hist" class="card__title">반영 지연 분포</h2>
          <Legend :series="LEGEND" />
        </div>
        <Skeleton v-if="!hist" variant="block" />
        <EmptyState v-else-if="data?.all.n === 0" message="아직 전송된 작업이 없습니다" />
        <div v-else class="dash__chart">
          <Histogram
            :buckets="hist.buckets"
            :series="SERIES"
            :marker="hist.marker"
            role="img"
            aria-label="반영 지연 분포 — 구간(초)별 건수"
          />
        </div>
      </section>

      <section class="card" aria-labelledby="dash-recent">
        <div class="card__head">
          <h2 id="dash-recent" class="card__title">최근 전송</h2>
        </div>
        <Table
          :columns="COLUMNS"
          :rows="recent as unknown as Record<string, unknown>[]"
          :loading="!data && loading"
          empty="아직 전송된 작업이 없습니다"
        >
          <template #cell-time="{ row }"
            ><span class="num" :title="r(row).when">{{ r(row).time }}</span></template
          >
          <template #cell-room="{ row }">{{ r(row).room }} · {{ r(row).kind }}</template>
          <template #cell-delay="{ row }">
            <span :class="{ dash__slow: r(row).slow, dash__failed: r(row).failed }">{{
              r(row).delay
            }}</span>
          </template>
          <template #cell-state="{ row }"><OutboxDot :state="r(row).state" /></template>
        </Table>
      </section>
    </div>
  </main>
</template>

<style scoped>
.dash {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  padding: var(--space-5);
}
.dash__head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.dash__title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
}
.dash__filter {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  margin-left: auto;
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.dash__kpis {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
}
/* 차트가 주인공, 목록은 곁 — 1.7 : 1 */
.dash__body {
  display: grid;
  grid-template-columns: 1.7fr 1fr;
  gap: var(--space-5);
  align-items: start;
}
.card {
  min-width: 0;
  padding: var(--space-4);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-md);
}
.card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}
.card__title {
  margin: 0;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-bold);
}
/* 1024px 폭에서는 차트(616px)가 칸보다 넓다 — 가로 스크롤 */
.dash__chart {
  overflow-x: auto;
}
.dash__slow {
  font-weight: var(--font-weight-bold);
}
.dash__failed {
  color: var(--danger);
}
</style>
```

`web/src/admin/router.ts` 의 `children` 을 바꾼다
```ts
    children: [
      // 관리자 기본 화면은 전송 현황 (spec §5)
      { path: '', redirect: '/dashboard' },
      { path: 'nodes', component: () => import('./views/NodesView.vue') },
      { path: 'dashboard', component: () => import('./views/DashboardView.vue') },
      { path: 'users', component: () => import('./views/UsersView.vue') },
    ],
```

`web/src/admin/AdminShell.vue` 의 `nav` 를 바꾼다
```ts
// #46 admin-master.md 순서: 건물 · 강의실 · 강의실 설정 · 주간 시간표(F2) · 노드 상태 · 전송 현황 · 회원
const nav = computed(() => [
  { to: '/nodes', label: '노드 상태' },
  { to: '/dashboard', label: '전송 현황' },
  { to: '/users', label: '회원', badge: pendingCount.value },
])
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint && pnpm exec prettier --check .`
Expected: PASS

- [ ] **Step 5: E2E — 기본 라우트 기대값 수정 + 전송 현황**

`web/e2e/login.spec.ts` 첫 테스트의 마지막 줄을 바꾼다
```ts
  await expect(page).toHaveURL(/\/admin\/dashboard$/)
```

`web/e2e/admin-shell.spec.ts` 첫 테스트를 통째로 바꾸고, 둘째 테스트의 `await expect(page).toHaveURL(/\/admin\/users$/)` 를 `await expect(page).toHaveURL(/\/admin\/dashboard$/)` 로 바꾼다
```ts
test('로그인 → 전송 현황, 사이드바 순서·활성 + 회원 대기 건수', async ({ page, request }) => {
  await createStudent(request) // 승인 대기 1건 이상
  await page.setViewportSize(SIZES.admin)
  await page.goto('/admin/')
  await fillLogin(page, nextAdmin())
  await expect(page).toHaveURL(/\/admin\/dashboard$/)
  await expect(page.locator('nav a')).toHaveText([/^노드 상태$/, /^전송 현황$/, /^회원\s*\d+$/])
  await expect(page.getByRole('link', { name: '전송 현황' })).toHaveAttribute('aria-current', 'page')
  const nav = await page.locator('nav').boundingBox()
  expect(Math.round(nav!.width)).toBe(220)
  await shot(page, 'admin-shell-1440')
})
```

`web/e2e/monitor.spec.ts`:
1. `declare const navigator …` 줄 아래에 추가:
   ```ts
declare const document: { documentElement: { scrollHeight: number } }
   ```
2. 첫 테스트(`시드 — …`) **바로 뒤**, `// ---- 노드 상태 ----` **앞**에 끼운다 — 노드 화면의 재전송·배정이 outbox 행을 더 만들기 전에 최근 전송 7행을 본다:
   ```ts
// ---- 전송 현황 (노드 화면 조작보다 먼저 — 재전송·배정이 outbox 를 더 만든다) ----
test('전송 현황 — KPI·분포·최근 전송이 1440×900 한 화면에', async () => {
  await page.getByRole('link', { name: '전송 현황' }).click()
  await expect(page).toHaveURL(/\/admin\/dashboard$/)
  const tiles = page.locator('.stat')
  await expect(tiles.nth(0)).toContainText('25초')
  await expect(tiles.nth(0)).toContainText('p95 50초 · 최대 95초')
  await expect(tiles.nth(1)).toContainText('62.5%')
  await expect(tiles.nth(1)).toContainText('목표 95% · 미달')
  await expect(tiles.nth(2)).toContainText('87.5%')
  await expect(tiles.nth(2)).toContainText('목표 전부 · 미달')
  await expect(tiles.nth(3)).toContainText('1건')
  const hist = page.locator('svg.hist')
  await expect(hist.locator('path')).toHaveCount(7)
  await expect(hist.locator('.hist__value')).toHaveText(['1', '2'])
  await expect(hist.locator('.hist__marker text')).toHaveText('SLA 30초')
  const recent = page.getByRole('region', { name: '최근 전송' }).locator('tbody tr')
  await expect(recent.locator('td:nth-child(3)')).toHaveText([
    '대기',
    '실패',
    '95초',
    '50초',
    '35초',
    '12초',
    '28초',
  ])
  await expect(recent.nth(0)).toContainText('E 402 · 예약')
  await expect(recent.locator('.dash__slow')).toHaveCount(3)
  await expect(recent.nth(1).locator('.dash__failed')).toHaveText('실패')
  expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThanOrEqual(900)
  await shot(page, 'admin-dashboard-1440')
})

test('기간 30일 — from 이 to 보다 29일 앞 (KST 날짜)', async () => {
  const req = page.waitForRequest(
    (r) => r.url().includes('/api/admin/analytics/latency') && r.url().includes('type=all'),
  )
  await page.getByLabel('기간').selectOption({ label: '최근 30일' })
  const q = new URL((await req).url()).searchParams
  expect((Date.parse(q.get('to')!) - Date.parse(q.get('from')!)) / 86_400_000).toBe(29)
  await expect(page.locator('.stat').nth(0)).toContainText('25초')
  await page.getByLabel('기간').selectOption({ label: '최근 7일' })
  await page.getByRole('link', { name: '노드 상태' }).click()
  await expect(page).toHaveURL(/\/admin\/nodes$/)
})
   ```
3. 파일 **끝**에 추가:
   ```ts
// ---- 다른 학교 — 학교 스코프 · 빈 상태 ----
test('다른 학교 관리자 — 우리 학교 장비·전송이 보이지 않고 빈 상태', async ({ browser }) => {
  const other = await browser.newContext({ baseURL: BASE, locale: 'ko-KR', viewport: SIZES.admin })
  const p = await other.newPage()
  await p.goto('/admin/')
  await fillLogin(p, cfg.OTHER_ADMIN)
  await expect(p).toHaveURL(/\/admin\/dashboard$/)
  await expect(p.getByText('아직 전송된 작업이 없습니다').first()).toBeVisible()
  await expect(p.locator('.stat__value')).toHaveText(['—', '—', '—', '0건'])
  await expect(p.locator('svg.hist')).toHaveCount(0)
  await shot(p, 'admin-dashboard-empty-1440')
  await p.getByRole('link', { name: '노드 상태' }).click()
  await expect(p.getByText('등록된 모뎀Pi가 없습니다')).toBeVisible()
  await expect(p.getByText('이 건물에 강의실이 없습니다')).toBeVisible()
  await expect(p.getByText('등록을 기다리는 장치가 없습니다.')).toBeVisible()
  await expect(p.getByText(SEED.modem)).toHaveCount(0)
  await shot(p, 'admin-nodes-empty-1440')
  await other.close()
})
   ```

- [ ] **Step 6: E2E 전체 실행 + 스크린샷 대조**

Run: **E2E 명령**(전체)
Expected: F1 17 + monitor 12 = `29 passed`. 로그인 횟수는 F1 ≤ 25 + monitor 3(시드 API 1 · 공유 페이지 1 · 다른 학교 1) — 1분 창에 몰리지 않지만 429 가 나면 `seedMonitoring` 의 `apiLogin` 을 공유 페이지 로그인 뒤로 옮겨 1회 줄인다.

`admin-dashboard-1440.png` 를 `admin-dashboard.md` 와 대조:
- **스크롤 없음**(테스트가 `scrollHeight ≤ 900` 을 고정). 상단 `반영 지연` · `마지막 갱신 HH:MM` · 오른쪽 `기간[최근 7일▾]`(건물 Select 없음 — 판정 표).
- KPI 4 타일 한 줄: 값 xl bold tabular, 단위 sm `text.2`, `sub` xs `text.3`. `전송 실패` 는 **값 글자만** 적색, 타일 바탕·테두리는 그대로. 화살표 없음.
- 본문 좌우 1.7 : 1. 차트: 막대 폭 15, 계열 간격 2, 위 모서리만 둥근 4px, 파랑(SLOT_SET)·청록(RESV_SET), 값 라벨은 계열마다 한 개(`2`·`1`), `20–30` 과 `30–45` 사이 세로 점선 + `SLA 30초`(text.3), 격자선 두 줄(line.1), 축선 line.3. 범례는 제목 오른쪽, 글자는 회색.
- 최근 전송 7행: `시각 | 강의실 · 종류 | 지연 | 점`. 30초 넘는 지연(95·50·35)만 bold(적색 아님), `실패` 값 적색 + 적색 점, `대기` 는 빈 원.
- `admin-dashboard-empty-1440.png`: KPI `— — — 0건`, 차트 자리 EmptyState. `admin-nodes-empty-1440.png`: 세 블록 모두 빈 상태 문구.
어긋나면 고치고 다시 찍는다.

- [ ] **Step 7: 커밋**

```bash
git add web/src/admin web/e2e
git commit -m "feat(web): 전송 현황 화면 — KPI 4(목표·판정 문장), 반영 지연 분포 SVG(SLA 30초), 최근 전송 7행, 60초 갱신, 관리자 기본 화면으로 + E2E"
```

---

## 자체 점검 결과 (plan 작성 시)

1. **spec 범위 ↔ Task**: §5 admin-nodes(30 s) → Task 6·7·8 / admin-dashboard(60 s, Histogram) → Task 5·9 / §4.3 마지막 갱신 5분 danger → Task 3(두 화면이 씀) / §2.2 domain·chart 컴포넌트 → Task 4·5 / §5 기본 화면 `/admin/dashboard`·메뉴 순서 → Task 6·9 / §9 웨이크 수신률 대체 → Task 9 `kpis` / §7.2 E2E·스크린샷 → 매 화면 Task + Task 1 하네스. `/api/lora/status` 는 화면 스펙이 "원자료(필요 시)" 라 쓰지 않는다(`NodeOut` 에 전부 있다).
2. **금지 패턴**: "TBD"·"TODO"·"나중에"·"적절한"·"위 테스트" 없음. 파일 수정은 전체 코드 또는 바꿀 블록 전체를 적었다.
3. **이름 일치**: `adminApi.{nodes,failed,latency}`·`loraApi.{modems,registerModem,rotateToken,pending,provision,broadcastTime,recentOutbox,syncRoom}`·`FAILED_LIMIT` (Task 2 ↔ 6·7·8·9 모의 객체), `provisionChoices`·`volts` (Task 6 ↔ 8), `SERIES_COLORS`·`HistogramSeries`·`HistogramBucket` (Task 5 ↔ 9), `SEED`·`seedMonitoring` (Task 1 ↔ 6~9 E2E), 섹션 id `nodes-esp`·`nodes-modem`·`nodes-pending`·`dash-recent` 과 E2E region 이름 일치.
4. **Review Focus 고정 테스트**: 1 → Task 3 `useStale`/`LastRefreshed` + Task 6·9 "Toast 는 한 번" / 2 → Task 6·9 폴링 해제 + Task 6 숨김 / 3 → Task 9 `kpis — 전송 0건이면 —` + E2E 다른 학교 / 4 → Task 6 `sortNodes`·`첫 조회 실패` / 5 → Task 7 `토큰 창은 Esc·배경으로 닫히지 않는다`.

## PR 체크리스트 (F3 완료 시)

- 브랜치 `feature/web-f3` → `main`. **F1 PR(`feature/web-f1`) 머지 뒤**에 연다(F1 위에 쌓인 브랜치). 서버 S4b·S10 이 main 에 없으면 PR 은 draft 로 두고 본문에 "통합 서버 워크트리(E2E_SERVER_DIR)로 E2E 확인" 을 적는다.
- 제목 `feat(web): F3 모니터링 — 노드 상태·전송 현황, SignalBars·NodeStateBadge·OutboxDot·Histogram, 마지막 갱신 표시`.
- 본문: `pnpm test`·`pnpm lint`·`pnpm typecheck`·`pnpm build` 결과, `pnpm e2e` 결과(29 passed), 스크린샷 7장(`admin-nodes`·`-token`·`-provision`·`-empty`, `admin-dashboard`·`-empty`, `admin-shell`), 위 **설계 판정** 표.
- mh 에 확인 요청: Histogram 막대 폭 15(components.md) vs 17(admin-dashboard.md) · SignalBars·NodeStateBadge 를 `domain/` 에 둔 것(components.md 는 chart 절) · OutboxDot 색을 같은 값의 2층(`--text-disabled`/`--text-2`)으로 쓴 것 · 마지막 갱신 문구 "· 갱신이 멈췄습니다" · 대시보드 건물 Select 제외 · 최근 전송의 건물 코드 표기.
- cw 에 알림: E2E 하네스가 `E2E_SERVER_DIR` 를 받는다(#44 Docker 편입 때 같은 변수로 서버 경로를 넘길 수 있다). 서버 additive 후보(급하지 않음): `OutboxOut`/`ModemOut` 에 건물 이름, 웨이크 수신률 지표.
- F2 와 겹칠 수 있는 곳: `api/types.ts`(끝에 덧붙임), `AdminShell.vue` `nav`·`router.ts` `children`(F2 가 위에 세 항목을 더한다), `OutboxDot`(F2 가 먼저 만들었다면 같은 props 라 한쪽을 지운다). 머지 순서는 팀장이 정한다.
