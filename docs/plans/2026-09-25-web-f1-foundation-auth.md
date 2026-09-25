# 웹 F1 — 기반 · 인증 · 회원 승인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 관리자 앱·학생 앱 두 진입점, 디자인 토큰·폰트, `ui` 컴포넌트 15종, API·세션·폴링 계층, 인증 화면 전부, 관리자 회원 승인 화면을 만들고 Playwright 로 실제 브라우저에서 확인한다.

**Architecture:** Vite 멀티 페이지(`index.html` 학생, `admin.html` 관리자)가 `styles`·`components/ui`·`api`·`lib`·`auth` 를 공유한다. 서버 호출은 `api/client.ts` 한 곳을 지나며 여기서 시각 변환(naive UTC → `Date`)과 상태별 오류 처리(401·403 세션 폐기, 503 GET 재시도, 네트워크 오류 status 0)를 한다. JWT 는 모듈 메모리(`lib/session.ts`)에만 있다.

**Tech Stack:** Vue 3.5 · vue-router 4.5 · Vite 7 · TypeScript 5.9 · Vitest 3 + @vue/test-utils + jsdom · @playwright/test 1.63 · pnpm

**Spec:** `docs/specs/2026-09-25-web-frontend-design.md` (+ 화면 원본 `docs/design/` — `tokens.md`·`components.md`·`screens/auth.md`·`screens/admin-users.md`. `auth.md` 는 **PR #46 판**(`origin/feature/mh-05-admin-master`)을 따른다: `/forgot` 화면, 401·403 문구, 역할 확인 문구, 가입 422·400 필드 오류가 거기에만 있다)

## Global Constraints

- 작업 위치: `web/` 만. 예외는 Task 1 의 `.github/workflows/ci.yml` 한 줄(`vue-tsc --build`) — PR 본문에 이유를 적는다.
- 패키지 매니저 pnpm 만. `pnpm-lock.yaml` 을 커밋한다. 새 의존성은 `@playwright/test`(devDependency) **하나뿐**이다. Pinia·TanStack·UI 키트·날짜/드롭다운/차트 라이브러리 금지.
- 응답 타입은 `src/api/types.ts` 에 **한 번만**, 서버 스키마 이름 그대로(`UserOut`, `LoginOut`). 화면에서 응답을 재해석·보정하지 않는다.
- 서버 `*_at` 은 naive UTC(`Z` 없음). `Date` 변환은 `api/client.ts` 에서만, 표시는 `lib/time.ts` 의 KST 포맷터로만.
- JWT 는 메모리에만. `localStorage`·`sessionStorage` 에 토큰을 넣지 않는다. `localStorage` 는 Banner 닫힘 기억에만 쓴다.
- 서버 오류 원문(`detail`)을 화면에 그대로 내지 않는다 — 화면 문구는 이 plan 에 적힌 한국어 문장.
- `admin/views`·`student/views`·`auth`·`components` 의 `.vue` 에서 1층 원시 팔레트(`--gray-`·`--blue-`·`--red-`·`--teal-`·`--gold-`)와 16진 색 리터럴 금지(`tokens.guard.spec.ts`). 원시 값은 `src/styles/tokens.css` 에서만.
- 두 앱은 서로의 `admin/`·`student/` 를 import 하지 않는다(ESLint `no-restricted-imports`).
- 관리자 화면 컨테이너 `min-width: 1024px`. 학생 터치 타깃 48px 이상(`--control-height-md` 가 학생 표면에서 48px).
- 포커스 링: `outline: 2px solid var(--focus); outline-offset: 2px`.
- 커밋: `feat(web): …` / `style(web): …`(토큰·ui) / `test(web): …`. Claude·AI 저작 표기와 `Co-Authored-By` 트레일러 금지.
- 매 Task 끝에 `pnpm test`·`pnpm lint`·`pnpm exec vue-tsc --build`·`pnpm exec prettier --check .` 가 통과해야 한다.
- 화면 Task 의 완료 조건: Playwright E2E 통과 + 관리자 1440×900 / 학생 390×844 스크린샷을 `web/e2e/.shots/` 에 남기고 화면 스펙 수치와 대조(스크린샷은 커밋하지 않는다 — PR 에 첨부).

## Review Focus

테스트가 직접 겨누지 않으면 사람이 가장 먼저 밟을 입력·상황 다섯. 각 줄의 고정 테스트는 담당 Task 에 들어 있다.

1. `?next=` 에 외부 주소(`//evil.com`, `https://evil.com`)를 넣은 로그인 링크 → 로그인 뒤 기본 화면으로 간다(열린 리다이렉트 금지). — Task 10 `safeNext` 테스트
2. 메일 링크를 연 뒤 새로고침(fragment 는 이미 지워짐) → "링크가 만료되었거나 잘못되었습니다" 상태, 빈 토큰으로 서버를 부르지 않는다. — Task 11 `readFragmentToken` + VerifyView 테스트
3. 목록 필터를 빠르게 바꿔 옛 응답이 늦게 도착 → 옛 응답이 새 목록을 덮지 않는다. — Task 4 `useResource` 테스트, Task 13 E2E 없이 단위로 고정
4. 같은 신청을 다른 탭에서 먼저 승인(409) → Toast "이미 처리된 신청입니다" + 목록 재조회, 버튼이 잠긴 채 남지 않는다. — Task 13 UsersView 테스트
5. 로그인 버튼 연타·429 → 제출 중 잠금, 429 뒤 10초 잠금이 풀리면 다시 누를 수 있다. — Task 4 `useCooldown` 테스트 + Task 10 E2E

## 파일 지도

```
web/
├── index.html                 학생 앱 (data-surface="student", referrer no-referrer)
├── admin.html                 관리자 앱
├── vite.config.ts             멀티 페이지 input + /admin/* dev·preview fallback, vitest exclude e2e
├── eslint.config.js           no-restricted-imports (admin ↔ student)
├── playwright.config.ts
├── e2e/
│   ├── env.json               서버 기동·헬퍼 공용 값 (JWT_SECRET·학교 도메인·관리자 넷)
│   ├── start-server.mjs       임시 DB + CLI 시드 + uvicorn (stdout → e2e/.tmp/server.log)
│   ├── helpers.ts             mailToken · cli · apiLogin · createStudent · fillLogin · shot
│   ├── login.spec.ts · auth.spec.ts · admin-shell.spec.ts · admin-users.spec.ts
└── src/
    ├── styles/                tokens.css · surface-student.css · base.css · fonts.css
    ├── assets/fonts/          PretendardVariable.subset.woff2 · OFL.txt · README.md
    ├── api/                   client.ts · types.ts · auth.ts · users.ts · __fixtures__/*.json
    ├── lib/                   session.ts · time.ts · bytes.ts · useResource.ts · usePolling.ts · useCooldown.ts
    ├── components/ui/         Button · Badge · Skeleton · EmptyState · Input · Textarea · Select ·
    │                          Checkbox · Table · Modal · Toast(ToastHost + toast.ts) · Banner ·
    │                          SidebarNav · StatTile · Legend
    ├── auth/                  AuthShell · StepList · LoginView · SignupView · VerifyView ·
    │                          ForgotView · ResetView · fragment.ts · next.ts · guard.ts
    ├── admin/                 main.ts · router.ts · AdminApp.vue · AdminShell.vue · pending.ts ·
    │                          usersView.ts · views/UsersView.vue
    └── student/               main.ts · router.ts · StudentApp.vue · views/HomeView.vue
```

삭제: `src/App.vue`, `src/main.ts`, `src/router/`, `src/views/`, `src/__tests__/router.spec.ts`(각 앱 라우터 테스트로 대체).

## Task 순서와 의존

| Task | 내용 | 의존 |
|---|---|---|
| 1 | 두 진입점 · 타입 체크 · 경계 린트 | — |
| 2 | 토큰 · 폰트 · 가드 테스트 | 1 |
| 3 | `lib/time` · `lib/session` · `api/client` · 타입 · 픽스처 | 1 |
| 4 | `useResource` · `usePolling` · `useCooldown` | 3 |
| 5 | ui: Button · Badge · Skeleton · EmptyState | 2 |
| 6 | ui: Input · Textarea · Select · Checkbox | 5 |
| 7 | ui: Table | 5 |
| 8 | ui: Modal · Toast · Banner | 5 |
| 9 | ui: SidebarNav · StatTile · Legend | 5 |
| 10 | Playwright 하네스 + 로그인(두 앱) · 가드 · 401/403 | 4, 6, 8 |
| 11 | 가입 · verify · forgot · reset (학생 앱) | 10 |
| 12 | AdminShell (사이드바 · 좁은 폭 Banner · 대기 건수) | 9, 10 |
| 13 | 회원 승인 화면 | 7, 12 |
| 14 | 거절 사유 툴팁 — **서버 A1 머지 뒤에만** | 13, 서버 A1 |

---

### Task 1: 두 진입점 · 타입 체크 · 경계 린트

**Files:**
- Modify: `web/index.html`, `web/vite.config.ts`, `web/eslint.config.js`, `web/package.json`, `web/tsconfig.json`, `web/tsconfig.app.json`, `web/tsconfig.node.json`, `.github/workflows/ci.yml`
- Create: `web/admin.html`, `web/tsconfig.vitest.json`, `web/src/admin/main.ts`, `web/src/admin/router.ts`, `web/src/admin/AdminApp.vue`, `web/src/admin/views/PlaceholderView.vue`, `web/src/student/main.ts`, `web/src/student/router.ts`, `web/src/student/StudentApp.vue`, `web/src/student/views/HomeView.vue`
- Delete: `web/src/App.vue`, `web/src/main.ts`, `web/src/router/index.ts`, `web/src/views/AdminHome.vue`, `web/src/views/StudentHome.vue`, `web/src/__tests__/router.spec.ts`
- Test: `web/src/admin/__tests__/router.spec.ts`, `web/src/student/__tests__/router.spec.ts`

**Interfaces:**
- Produces: `src/admin/router.ts` → `export const routes: RouteRecordRaw[]`, `export function makeRouter(history?: RouterHistory): Router`(기본 `createWebHistory('/admin/')`). `src/student/router.ts` 도 같은 모양(기본 `createWebHistory('/')`). 이후 Task 가 `routes` 에 항목을 더한다.
- Produces: `pnpm typecheck` = `vue-tsc --build`.

배경: 지금 `vue-tsc --noEmit` 은 루트 tsconfig 가 `files: []` + references 라 **아무것도 검사하지 않는다**(plan 작성 중 일부러 타입 오류를 넣어도 exit 0 이었다). `--build` 로 바꾼다.

- [ ] **Step 1: 실패 테스트 — 두 라우터**

`web/src/admin/__tests__/router.spec.ts`
```ts
import { describe, expect, it } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import { makeRouter } from '@/admin/router'

describe('admin router', () => {
  it('/ 가 열린다', async () => {
    const r = makeRouter(createMemoryHistory())
    await r.push('/')
    await r.isReady()
    expect(r.currentRoute.value.matched.length).toBeGreaterThan(0)
  })
})
```
`web/src/student/__tests__/router.spec.ts` — 위와 같고 import 만 `@/student/router`, describe 이름 `student router`.

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test`
Expected: FAIL — `Failed to resolve import "@/admin/router"`

- [ ] **Step 3: 진입점 구현**

옛 스캐폴드 삭제:
```bash
cd web && git rm -q src/App.vue src/main.ts src/router/index.ts src/views/AdminHome.vue src/views/StudentHome.vue src/__tests__/router.spec.ts
```

`web/index.html`
```html
<!doctype html>
<html lang="ko" data-surface="student">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <!-- /verify·/reset 의 #token 이 Referer 로 새지 않게 (auth.md) -->
    <meta name="referrer" content="no-referrer" />
    <title>강의실 게시</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/student/main.ts"></script>
  </body>
</html>
```
`web/admin.html` — 위와 같되 `<html lang="ko">`(data-surface 없음), 제목 `강의실 게시 관리자`, 스크립트 `/src/admin/main.ts`.

`web/src/admin/router.ts`
```ts
import { createRouter, createWebHistory, type RouteRecordRaw, type RouterHistory } from 'vue-router'

export const routes: RouteRecordRaw[] = [
  { path: '/', component: () => import('./views/PlaceholderView.vue') },
]

export function makeRouter(history: RouterHistory = createWebHistory('/admin/')) {
  return createRouter({ history, routes })
}
```
`web/src/admin/views/PlaceholderView.vue` (Task 12 에서 지운다)
```vue
<template>
  <h1>관리자</h1>
</template>
```
`web/src/admin/AdminApp.vue`
```vue
<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <RouterView />
</template>
```
`web/src/admin/main.ts`
```ts
import { createApp } from 'vue'
import AdminApp from './AdminApp.vue'
import { makeRouter } from './router'

createApp(AdminApp).use(makeRouter()).mount('#app')
```
학생 쪽: `src/student/router.ts`(`HomeView.vue`, 기본 `createWebHistory('/')`), `StudentApp.vue`(`AdminApp.vue` 와 같은 내용), `main.ts`(`StudentApp`), `views/HomeView.vue`(`<h1>학생</h1>` — Task 10 이 바꾼다)를 같은 모양으로.

`web/vite.config.ts` 전체
```ts
/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'
import { defineConfig, type Connect, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'

// /admin, /admin/users 처럼 확장자 없는 경로는 관리자 앱 HTML 로. 나머지 SPA fallback 은 index.html(학생).
const ADMIN_PAGE = /^\/admin(\/[^.?]*)?(\?.*)?$/
const adminFallback: Connect.NextHandleFunction = (req, _res, next) => {
  if (req.url && ADMIN_PAGE.test(req.url)) req.url = '/admin.html'
  next()
}
function adminPages(): Plugin {
  return {
    name: 'admin-pages',
    configureServer: (s) => void s.middlewares.use(adminFallback),
    configurePreviewServer: (s) => void s.middlewares.use(adminFallback),
  }
}

// 개발 중에는 메인Pi 서버(uvicorn :8000)로 /api·/ws 를 프록시한다. 빌드 산출물은 같은 오리진에서 서빙된다.
export default defineConfig({
  plugins: [vue(), adminPages()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  build: {
    rollupOptions: {
      input: {
        student: fileURLToPath(new URL('./index.html', import.meta.url)),
        admin: fileURLToPath(new URL('./admin.html', import.meta.url)),
      },
    },
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
  test: { environment: 'jsdom', include: ['src/**/*.spec.ts'] },
})
```

타입 체크 구성:
- `web/tsconfig.app.json` 의 `exclude` → `["src/**/__tests__/*", "src/**/*.spec.ts"]`.
- `web/tsconfig.vitest.json` 새로:
```json
{
  "extends": "./tsconfig.app.json",
  "include": ["env.d.ts", "src/**/*", "src/**/*.vue"],
  "exclude": [],
  "compilerOptions": {
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.vitest.tsbuildinfo",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "types": ["node"]
  }
}
```
- `web/tsconfig.json` references 에 `{ "path": "./tsconfig.vitest.json" }` 추가.
- `web/tsconfig.node.json` include → `["vite.config.*", "eslint.config.*", "playwright.config.*", "e2e/**/*"]`.
- `web/package.json` scripts: `"build": "vue-tsc --build && vite build"`, `"typecheck": "vue-tsc --build"`.
- `.github/workflows/ci.yml` web job 의 `pnpm exec vue-tsc --noEmit` → `pnpm exec vue-tsc --build`.

`web/eslint.config.js` — `skipFormatting` 앞에 추가:
```js
  {
    name: 'app/boundary-admin',
    files: ['src/admin/**'],
    rules: { 'no-restricted-imports': ['error', { patterns: ['@/student/*', '**/student/**'] }] },
  },
  {
    name: 'app/boundary-student',
    files: ['src/student/**'],
    rules: { 'no-restricted-imports': ['error', { patterns: ['@/admin/*', '**/admin/**'] }] },
  },
  {
    name: 'app/boundary-shared',
    files: ['src/{api,lib,styles,components,auth}/**'],
    rules: {
      'no-restricted-imports': [
        'error',
        { patterns: ['@/admin/*', '@/student/*', '**/admin/**', '**/student/**'] },
      ],
    },
  },
```

- [ ] **Step 4: 통과 확인 + 체크가 실제로 잡는지(음성 대조)**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint && pnpm build && ls dist/index.html dist/admin.html`
Expected: 2 passed, 나머지 exit 0, HTML 두 개 존재.

경계 린트 음성 대조(되돌린다):
```bash
echo "import '@/student/router'" >> src/admin/main.ts; pnpm lint; echo "exit=$?"; git checkout src/admin/main.ts
```
Expected: `no-restricted-imports` 오류, `exit=1`.

타입 체크 음성 대조:
```bash
echo "export const x: number = 'a'" > src/__tmp.ts; pnpm typecheck; echo "exit=$?"; rm src/__tmp.ts
```
Expected: `TS2322`, exit ≠ 0.

dev fallback — `pnpm dev` 를 띄운 채:
```bash
curl -s localhost:5173/admin/users | grep -c 'src/admin/main.ts'   # 1
curl -s localhost:5173/signup | grep -c 'src/student/main.ts'      # 1
```

- [ ] **Step 5: 커밋**

```bash
git add -A web .github/workflows/ci.yml
git commit -m "feat(web): 관리자·학생 앱 진입점 2개(멀티 페이지)와 /admin fallback, vue-tsc --build, 앱 경계 린트"
```

---

### Task 2: 토큰 · 폰트 · 가드 테스트

**Files:**
- Create: `web/src/styles/tokens.css`, `web/src/styles/surface-student.css`, `web/src/styles/base.css`, `web/src/styles/fonts.css`, `web/src/styles/index.css`, `web/src/assets/fonts/PretendardVariable.subset.woff2`, `web/src/assets/fonts/OFL.txt`, `web/src/assets/fonts/README.md`
- Modify: `web/src/admin/main.ts`, `web/src/student/main.ts` (첫 줄에 `import '@/styles/index.css'`)
- Test: `web/src/styles/__tests__/tokens.spec.ts`, `web/src/styles/__tests__/tokens.guard.spec.ts`

**Interfaces:**
- Produces: CSS 변수 — 이후 모든 컴포넌트가 이 이름만 쓴다.
  - 2층: `--bg --bg-student --surface --sunken --line-1 --line-2 --line-3 --text-1 --text-2 --text-3 --text-disabled --brand --brand-tint --danger --focus`
  - 3층: `--room-busy-fill --room-busy-line --room-busy-label --room-free-text --room-free-line --chart-series-1..3 --chart-grid --chart-axis --chart-text`
  - 타이포·치수: `--font-family --font-weight-regular|medium|bold --leading-tight|normal --font-size-xs|sm|md|lg|xl --control-height-sm|md --radius-sm|md|lg|full --space-1..7 --border-thin --border-thick`
  - 구현 별칭(components.md 가 원시 값을 직접 부르는 자리): `--on-brand --modal-backdrop --skeleton-a --skeleton-b --nav-hover`
  - 전역 클래스 `.num` (`tabular-nums`)

토큰 값은 `docs/design/tokens.md` 가 원본이다. 여기서 값을 새로 정하지 않는다.

- [ ] **Step 1: 실패 테스트 — 원본 문서와 CSS 대조 + 가드**

`web/src/styles/__tests__/tokens.spec.ts`
```ts
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8')
const doc = read('../../../../docs/design/tokens.md')
const tokens = read('../tokens.css')
const student = read('../surface-student.css')

const cssVar = (css: string, name: string) =>
  css.match(new RegExp(`--${name}:\\s*([^;]+);`))?.[1].trim().toLowerCase()

describe('tokens.css 는 tokens.md 를 그대로 옮긴다', () => {
  it('1층 원시 팔레트 값 — (A) 계산값이 어긋나면 실패', () => {
    const rows = [...doc.matchAll(/^\| `([a-z]+)\.(\d+)` \| `(#[0-9A-Fa-f]{6})`/gm)]
    expect(rows.length).toBeGreaterThanOrEqual(17) // gray 10 + 유채색 7
    for (const [, fam, step, hex] of rows) {
      expect(cssVar(tokens, `${fam}-${step}`), `${fam}.${step}`).toBe(hex.toLowerCase())
    }
  })

  it('치수 — admin 은 :root, student 는 [data-surface=student]', () => {
    const rows = [
      ...doc.matchAll(/^\| `((?:font\.size|control\.height|radius)\.\w+)` \| (\S+) \| (\S+) \|/gm),
    ]
    expect(rows.length).toBeGreaterThanOrEqual(11)
    for (const [, name, admin, stu] of rows) {
      const v = name.replace(/\./g, '-')
      expect(cssVar(tokens, v), `${name} admin`).toBe(admin)
      if (stu !== '—' && stu !== admin) expect(cssVar(student, v), `${name} student`).toBe(stu)
    }
  })

  it('2층은 1층을 가리킨다 (값을 복사하지 않는다)', () => {
    expect(cssVar(tokens, 'brand')).toBe('var(--blue-600)')
    expect(cssVar(tokens, 'danger')).toBe('var(--red-700)')
    expect(cssVar(tokens, 'text-3')).toBe('var(--gray-500)')
    expect(cssVar(tokens, 'room-busy-fill')).toBe('var(--red-50)')
    expect(cssVar(tokens, 'bg-student')).toBe('var(--gray-25)')
  })
})
```

`web/src/styles/__tests__/tokens.guard.spec.ts`
```ts
import { describe, expect, it } from 'vitest'

// 화면·컴포넌트는 2·3층만 쓴다 (spec §3.1). 원시 팔레트와 16진 색은 styles/tokens.css 에서만.
const files = import.meta.glob('/src/**/*.vue', { query: '?raw', import: 'default', eager: true })
const PRIMITIVE = /--(gray|blue|red|teal|gold)-\d/
const HEX = /#[0-9a-fA-F]{3,8}\b/

describe('토큰 가드', () => {
  it.each(Object.entries(files))('%s 는 원시 팔레트·16진 색을 쓰지 않는다', (_path, src) => {
    const style = String(src).match(/<style[\s\S]*?<\/style>/g)?.join('\n') ?? ''
    const template = String(src).match(/<template>[\s\S]*<\/template>/)?.[0] ?? ''
    expect(style + template).not.toMatch(PRIMITIVE)
    expect(style + template).not.toMatch(HEX)
  })
})
```
(`.vue` 가 PlaceholderView·HomeView 뿐이라 가드는 지금도 통과한다 — 음성 대조는 Step 4.)

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/styles`
Expected: FAIL — `ENOENT … tokens.css`

- [ ] **Step 3: 토큰·기본 스타일 구현**

`web/src/styles/tokens.css`
```css
/* 원본: docs/design/tokens.md v2. 값을 바꾸려면 mh 의 docs/design PR 이 먼저다 (lockstep). */
:root {
  /* 1층 — 원시 팔레트. 이 파일 밖에서 직접 쓰지 않는다 */
  --gray-0: #ffffff;
  --gray-25: #fafafa;
  --gray-50: #f4f4f4;
  --gray-100: #ededed;
  --gray-200: #e3e3e3;
  --gray-300: #d4d4d4;
  --gray-400: #a6a6a6;
  --gray-500: #707070;
  --gray-600: #595959;
  --gray-800: #262626;
  --blue-600: #0b5ed7;
  --blue-50: #edf4fd;
  --red-700: #b42318;
  --red-100: #f6d4d0;
  --red-50: #fdf0ef;
  --teal-600: #0d9488;
  --gold-600: #ca8a04;

  /* 2층 — 시맨틱 */
  --bg: var(--gray-0);
  --bg-student: var(--gray-25);
  --surface: var(--gray-0);
  --sunken: var(--gray-25);
  --line-1: var(--gray-100);
  --line-2: var(--gray-200);
  --line-3: var(--gray-300);
  --text-1: var(--gray-800);
  --text-2: var(--gray-600);
  --text-3: var(--gray-500);
  --text-disabled: var(--gray-400);
  --brand: var(--blue-600);
  --brand-tint: var(--blue-50);
  --danger: var(--red-700);
  --focus: var(--blue-600);

  /* 3층 — 도메인 */
  --room-busy-fill: var(--red-50);
  --room-busy-line: var(--red-100);
  --room-busy-label: var(--red-700);
  --room-free-text: var(--text-3);
  --room-free-line: var(--line-3);
  --chart-series-1: var(--blue-600);
  --chart-series-2: var(--teal-600);
  --chart-series-3: var(--gold-600);
  --chart-grid: var(--line-1);
  --chart-axis: var(--line-3);
  --chart-text: var(--text-3);

  /* 구현 별칭 — components.md 가 원시 값을 직접 부르는 자리 (값은 위 1층 그대로) */
  --on-brand: var(--gray-0); /* brand·danger 채움 위 글자, 체크 표시 */
  --modal-backdrop: color-mix(in srgb, var(--gray-800) 45%, transparent); /* Modal 배경 .45 */
  --skeleton-a: var(--gray-50);
  --skeleton-b: var(--gray-100);
  --nav-hover: var(--gray-50); /* SidebarNav hover */

  /* 타이포 */
  --font-family: 'Pretendard Variable', Pretendard, system-ui, -apple-system, sans-serif;
  --font-weight-regular: 400;
  --font-weight-medium: 500;
  --font-weight-bold: 700;
  --leading-tight: 1.25;
  --leading-normal: 1.5;

  /* 치수 — admin 값. 학생 값은 surface-student.css */
  --font-size-xs: 11px;
  --font-size-sm: 12px;
  --font-size-md: 13px;
  --font-size-lg: 16px;
  --font-size-xl: 22px;
  --control-height-sm: 28px;
  --control-height-md: 32px;
  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;
  --radius-full: 999px;

  /* 간격 · 보더 — 두 웹 공용 */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --space-7: 48px;
  --border-thin: 1px;
  --border-thick: 2px;
}
```
`web/src/styles/surface-student.css`
```css
/* 학생 웹 — 이름은 같고 값만 갈린다 (tokens.md 「치수」). 색은 재정의하지 않는다 */
[data-surface='student'] {
  --font-size-xs: 12px;
  --font-size-sm: 13px;
  --font-size-md: 15px;
  --font-size-lg: 18px;
  --font-size-xl: 20px;
  --control-height-md: 48px;
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
}
```
`web/src/styles/base.css`
```css
*,
*::before,
*::after {
  box-sizing: border-box;
}
html {
  font-family: var(--font-family);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  line-height: var(--leading-normal);
  color: var(--text-1);
  background: var(--bg);
  -webkit-text-size-adjust: 100%;
}
html[data-surface='student'] {
  background: var(--bg-student);
}
body {
  margin: 0;
}
:focus-visible {
  outline: var(--border-thick) solid var(--focus);
  outline-offset: 2px;
}
.num {
  font-variant-numeric: tabular-nums;
}
```
`web/src/styles/fonts.css`
```css
/* self-host — 메인Pi 가 오프라인일 수 있다 (tokens.md). 서브셋 범위는 assets/fonts/README.md */
@font-face {
  font-family: 'Pretendard Variable';
  src: url('../assets/fonts/PretendardVariable.subset.woff2') format('woff2-variations');
  font-weight: 45 920;
  font-style: normal;
  font-display: swap;
}
```
`web/src/styles/index.css`
```css
@import './fonts.css';
@import './tokens.css';
@import './surface-student.css';
@import './base.css';
```
두 `main.ts` 의 첫 줄에 `import '@/styles/index.css'`.

- [ ] **Step 4: 폰트 서브셋 만들기 (KS X 1001 한글 2,350 + 호환 자모 + ASCII + 기호)**

```bash
cd web/src/assets/fonts
V=v1.3.9   # 404 면 https://github.com/orioncactus/pretendard/releases 의 최신 태그
curl -fsSLo "$TMP/pv.woff2" "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@$V/dist/web/variable/woff2/PretendardVariable.woff2"
curl -fsSLo OFL.txt "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@$V/LICENSE"
python - > "$TMP/chars.txt" <<'PY'
def ks(c):
    try: c.encode('euc-kr'); return True
    except UnicodeEncodeError: return False
hangul = ''.join(c for c in map(chr, range(0xAC00, 0xD7A4)) if ks(c))
assert len(hangul) == 2350, len(hangul)
jamo = ''.join(map(chr, range(0x3131, 0x318F)))
ascii_ = ''.join(map(chr, range(0x20, 0x7F)))
extra = '·‹›«»①②③④⑤⑥⑦•—–…※○●◐←→↑↓▾▴✓✕“”‘’℃°±×÷'
print(hangul + jamo + ascii_ + extra, end='')
PY
uvx --from fonttools --with brotli pyftsubset "$TMP/pv.woff2" --text-file="$TMP/chars.txt" \
  --flavor=woff2 --layout-features='*' --output-file=PretendardVariable.subset.woff2
wc -c PretendardVariable.subset.woff2
```
400 KB(409600 B)를 넘으면 `--no-hinting --desubroutinize` 를 붙여 다시 만든다. 그래도 넘으면 크기를 그대로 적고 진행한다 — spec §9 열린 결정이라 PR 에서 mh 와 정한다.

`web/src/assets/fonts/README.md` — 출처(태그 `$V`), 라이선스(SIL OFL 1.1, `OFL.txt`), 서브셋 범위(위 네 묶음), 위 명령 그대로, **실제 바이트 수**를 적는다.

- [ ] **Step 5: 통과 + 가드 음성 대조**

Run: `cd web && pnpm test src/styles`
Expected: PASS

가드 음성 대조(되돌린다):
```bash
printf '<template><p style="color: #fff">x</p></template>\n' > src/admin/views/Bad.vue
pnpm test src/styles; echo "exit=$?"; rm src/admin/views/Bad.vue
```
Expected: `Bad.vue` 한 건 FAIL, `exit=1`.

문서 대조 음성: `tokens.css` 의 `--blue-600` 을 `#0b5ed8` 로 바꾸면 `blue.600` 으로 FAIL → 되돌린다.

폰트 로드 확인: `pnpm dev` → 브라우저 개발자도구 Network 에 `PretendardVariable.subset.woff2` 200, `document.fonts.check('13px "Pretendard Variable"')` 가 `true`.

- [ ] **Step 6: 커밋**

```bash
git add web/src/styles web/src/assets/fonts web/src/admin/main.ts web/src/student/main.ts
git commit -m "style(web): 디자인 토큰 v2 를 CSS 변수로(admin·student 치수 분기), Pretendard 서브셋 self-host, 토큰 가드 테스트"
```

---

### Task 3: 시각 · 세션 · API 클라이언트 · 타입

**Files:**
- Create: `web/src/lib/time.ts`, `web/src/lib/session.ts`, `web/src/api/types.ts`, `web/src/api/auth.ts`, `web/src/api/users.ts`, `web/src/api/__fixtures__/users.json`, `web/src/api/__fixtures__/login.json`, `web/src/api/__fixtures__/error-422.json`
- Modify: `web/src/api/client.ts` (전부 교체)
- Test: `web/src/lib/__tests__/time.spec.ts`, `web/src/api/__tests__/client.spec.ts`

**Interfaces:**
- Produces `lib/time.ts`: `parseUtc(v: string): Date` · `formatKst(d: Date): string`(`'2026-09-26 00:30'`) · `formatHm(d: Date): string`(`'00:30'`) · `relativeKo(d: Date, now?: Date): string`
- Produces `lib/session.ts`: `session: Readonly<Ref<LoginOut | null>>` · `authNotice: Ref<AuthNotice | null>` · `type AuthNotice = 'expired' | 'forbidden'` · `setSession(s: LoginOut): void` · `clearSession(notice?: AuthNotice): void` · `onAuthFailure(cb: (n: AuthNotice) => void): void`
- Produces `api/client.ts`: `class ApiError extends Error { status: number; fields: string[]; detail: unknown }` · `MESSAGES: Record<number, string>` · `request<T>(method, path, body?, opts?: { auth?: boolean; dates?: readonly string[]; signal?: AbortSignal }): Promise<T>`
- Produces `api/types.ts`: `Role` · `UserStatus` · `UserOut` · `LoginOut` · `USER_DATES`
- Produces `api/auth.ts`: `authApi.{signup, verifyOpen, verify, login, forgot, reset, me}` / `api/users.ts`: `usersApi.{list, approve, reject, disable, enable}`

서버 사실(바꾸지 않는다): 오류 본문은 `{"detail": "…"}`, 422 는 `{"detail": [{"loc": ["body", "student_no"], "msg": …}]}`. `*_at` 은 `Z` 없는 UTC. 로그인 실패 401 은 **토큰 없이** 부르는 요청이라 세션 만료와 구분해야 한다.

- [ ] **Step 1: 실패 테스트 — 시각**

`web/src/lib/__tests__/time.spec.ts`
```ts
import { describe, expect, it } from 'vitest'
import { formatHm, formatKst, parseUtc, relativeKo } from '@/lib/time'

describe('time', () => {
  it('naive UTC 를 UTC 로 읽는다 (브라우저 로컬 시간대와 무관)', () => {
    expect(parseUtc('2026-09-25T15:30:00').toISOString()).toBe('2026-09-25T15:30:00.000Z')
    expect(parseUtc('2026-09-25T15:30:00.123456').toISOString()).toBe('2026-09-25T15:30:00.123Z')
    expect(parseUtc('2026-09-25T15:30:00Z').toISOString()).toBe('2026-09-25T15:30:00.000Z')
    expect(parseUtc('2026-09-25T15:30:00+00:00').toISOString()).toBe('2026-09-25T15:30:00.000Z')
  })

  it('KST 로 표시 — 자정 경계에서 날짜가 넘어간다', () => {
    const d = parseUtc('2026-09-25T15:30:00')
    expect(formatKst(d)).toBe('2026-09-26 00:30')
    expect(formatHm(d)).toBe('00:30')
  })

  it('상대 시각 — KST 달력 기준', () => {
    const now = parseUtc('2026-09-25T03:00:00') // KST 12:00
    expect(relativeKo(parseUtc('2026-09-25T02:59:30'), now)).toBe('방금')
    expect(relativeKo(parseUtc('2026-09-25T02:15:00'), now)).toBe('45분 전')
    expect(relativeKo(parseUtc('2026-09-24T16:00:00'), now)).toBe('11시간 전') // KST 같은 날 01:00
    expect(relativeKo(parseUtc('2026-09-24T14:00:00'), now)).toBe('어제') // KST 전날 23:00
    expect(relativeKo(parseUtc('2026-09-21T03:00:00'), now)).toBe('4일 전')
    expect(relativeKo(parseUtc('2026-09-01T03:00:00'), now)).toBe('9월 1일')
    expect(relativeKo(parseUtc('2026-09-25T03:05:00'), now)).toBe('방금') // 시계 어긋남(미래)
  })
})
```

- [ ] **Step 2: 실패 테스트 — 클라이언트**

`web/src/api/__fixtures__/users.json`
```json
[
  {
    "email": "s1@wsu.ac.kr",
    "school_id": 1,
    "role": "student",
    "status": "pending_approval",
    "name": "김민준",
    "student_no": "20231234",
    "created_at": "2026-09-25T01:00:00.123456",
    "approved_at": null
  },
  {
    "email": "admin@wsu.ac.kr",
    "school_id": 1,
    "role": "admin",
    "status": "active",
    "name": "관리자",
    "student_no": null,
    "created_at": "2026-09-20T00:00:00",
    "approved_at": null
  }
]
```
`web/src/api/__fixtures__/login.json`
```json
{ "token": "eyJ.test.sig", "role": "admin", "school_id": 1, "name": "관리자" }
```
`web/src/api/__fixtures__/error-422.json`
```json
{
  "detail": [
    {
      "type": "string_pattern_mismatch",
      "loc": ["body", "student_no"],
      "msg": "String should match pattern '^[0-9A-Za-z-]+$'",
      "input": "2023 1234"
    }
  ]
}
```

`web/src/api/__tests__/client.spec.ts`
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, MESSAGES, request } from '@/api/client'
import { USER_DATES, type UserOut } from '@/api/types'
import { authNotice, clearSession, onAuthFailure, session, setSession } from '@/lib/session'
import users from '@/api/__fixtures__/users.json'
import login from '@/api/__fixtures__/login.json'
import err422 from '@/api/__fixtures__/error-422.json'

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
const fetchMock = vi.fn<typeof fetch>()

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  clearSession()
  authNotice.value = null
})
afterEach(() => vi.useRealTimers())

describe('request', () => {
  it('표시한 필드만 Date 로 바꾼다', async () => {
    fetchMock.mockResolvedValue(json(200, users))
    const out = await request<UserOut[]>('GET', '/api/admin/users', undefined, { dates: USER_DATES })
    expect(out[0].created_at).toBeInstanceOf(Date)
    expect(out[0].created_at.toISOString()).toBe('2026-09-25T01:00:00.123Z')
    expect(out[0].approved_at).toBeNull()
    expect(out[0].email).toBe('s1@wsu.ac.kr')
  })

  it('세션이 있으면 Bearer, auth:false 면 붙이지 않는다', async () => {
    setSession(login as never)
    fetchMock.mockResolvedValue(json(200, {}))
    await request('GET', '/a')
    await request('POST', '/b', { x: 1 }, { auth: false })
    const h = (i: number) => new Headers(fetchMock.mock.calls[i][1]!.headers)
    expect(h(0).get('authorization')).toBe('Bearer eyJ.test.sig')
    expect(h(1).get('authorization')).toBeNull()
    expect(h(1).get('content-type')).toBe('application/json')
    expect(fetchMock.mock.calls[1][1]!.body).toBe('{"x":1}')
  })

  it('토큰을 보낸 요청의 401 → 세션 폐기 + expired 알림', async () => {
    const onFail = vi.fn()
    onAuthFailure(onFail)
    setSession(login as never)
    fetchMock.mockResolvedValue(json(401, { detail: 'invalid token' }))
    const e = await request('GET', '/a').catch((x) => x)
    expect(e).toBeInstanceOf(ApiError)
    expect(e.status).toBe(401)
    expect(e.message).toBe(MESSAGES[401])
    expect(session.value).toBeNull()
    expect(authNotice.value).toBe('expired')
    expect(onFail).toHaveBeenCalledWith('expired')
  })

  it('로그인 실패 401(auth:false)은 세션을 건드리지 않는다', async () => {
    const onFail = vi.fn()
    onAuthFailure(onFail)
    fetchMock.mockResolvedValue(json(401, { detail: '이메일 또는 비밀번호가 틀립니다' }))
    const e = await request('POST', '/api/auth/login', {}, { auth: false }).catch((x) => x)
    expect(e.status).toBe(401)
    expect(onFail).not.toHaveBeenCalled()
    expect(authNotice.value).toBeNull()
  })

  it('403 → forbidden 알림', async () => {
    onAuthFailure(() => {})
    setSession(login as never)
    fetchMock.mockResolvedValue(json(403, { detail: 'admin only' }))
    await request('GET', '/a').catch(() => {})
    expect(authNotice.value).toBe('forbidden')
    expect(session.value).toBeNull()
  })

  it('422 → 필드 이름 목록', async () => {
    fetchMock.mockResolvedValue(json(422, err422))
    const e = await request('POST', '/v', {}, { auth: false }).catch((x) => x)
    expect(e.fields).toEqual(['student_no'])
  })

  it('서버 원문을 message 로 내지 않는다', async () => {
    fetchMock.mockResolvedValue(json(409, { detail: 'constraint violation' }))
    const e = await request('POST', '/x').catch((x) => x)
    expect(e.message).toBe(MESSAGES[409])
    expect(e.detail).toEqual({ detail: 'constraint violation' })
  })

  it('503 GET 은 1초 뒤 한 번 재시도', async () => {
    vi.useFakeTimers()
    fetchMock.mockResolvedValueOnce(json(503, {})).mockResolvedValueOnce(json(200, { ok: 1 }))
    const p = request<{ ok: number }>('GET', '/g')
    await vi.advanceTimersByTimeAsync(1000)
    await expect(p).resolves.toEqual({ ok: 1 })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('503 쓰기는 재시도하지 않는다', async () => {
    fetchMock.mockResolvedValue(json(503, {}))
    const e = await request('POST', '/p').catch((x) => x)
    expect(e.status).toBe(503)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('네트워크 오류 → status 0', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const e = await request('GET', '/n').catch((x) => x)
    expect(e).toBeInstanceOf(ApiError)
    expect(e.status).toBe(0)
  })

  it('abort 는 ApiError 로 바꾸지 않는다', async () => {
    fetchMock.mockRejectedValue(new DOMException('aborted', 'AbortError'))
    const e = await request('GET', '/n').catch((x) => x)
    expect(e.name).toBe('AbortError')
  })

  it('204 는 undefined', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))
    await expect(request('DELETE', '/d')).resolves.toBeUndefined()
  })
})
```
`tsconfig.app.json` 의 `compilerOptions` 에 `"resolveJsonModule": true` 가 없으면 추가한다(`@vue/tsconfig` 에 이미 있으면 생략).

- [ ] **Step 3: 실패 확인**

Run: `cd web && pnpm test src/lib src/api`
Expected: FAIL — `Failed to resolve import "@/lib/time"`

- [ ] **Step 4: 구현**

`web/src/lib/time.ts`
```ts
// 서버 *_at 은 Z 없는 naive UTC (S4a §3.4). 해석은 api/client 가 이 함수로 한 번만, 표시는 KST 로만.
const TZ = 'Asia/Seoul'
const HAS_ZONE = /(Z|[+-]\d\d:?\d\d)$/

export function parseUtc(v: string): Date {
  return new Date(HAS_ZONE.test(v) ? v : `${v}Z`)
}

const parts = new Intl.DateTimeFormat('en-CA', {
  timeZone: TZ,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

function kst(d: Date) {
  const p = Object.fromEntries(parts.formatToParts(d).map((x) => [x.type, x.value]))
  return { y: p.year, mo: p.month, d: p.day, h: p.hour, mi: p.minute }
}

export function formatKst(d: Date): string {
  const k = kst(d)
  return `${k.y}-${k.mo}-${k.d} ${k.h}:${k.mi}`
}

export function formatHm(d: Date): string {
  const k = kst(d)
  return `${k.h}:${k.mi}`
}

const KST_MS = 9 * 3600_000
const kstDay = (d: Date) => Math.floor((d.getTime() + KST_MS) / 86_400_000)

export function relativeKo(d: Date, now: Date = new Date()): string {
  const sec = (now.getTime() - d.getTime()) / 1000
  if (sec < 60) return '방금'
  const days = kstDay(now) - kstDay(d)
  if (days === 0) return sec < 3600 ? `${Math.floor(sec / 60)}분 전` : `${Math.floor(sec / 3600)}시간 전`
  if (days === 1) return '어제'
  if (days < 7) return `${days}일 전`
  const k = kst(d)
  return `${Number(k.mo)}월 ${Number(k.d)}일`
}
```
(`'45분 전'` 케이스: 같은 KST 날이고 45분 — `days === 0` 분기 안에서 분으로 나온다.)

`web/src/api/types.ts`
```ts
// 서버 응답 타입 — 서버 스키마 이름 그대로, 여기에 한 번만 (web/CLAUDE.md). Date 필드는 *_DATES 에 적는다.
export type Role = 'admin' | 'student'
export type UserStatus = 'pending_approval' | 'active' | 'rejected' | 'disabled'

export interface UserOut {
  email: string
  school_id: number
  role: Role
  status: UserStatus
  name: string
  student_no: string | null
  created_at: Date
  approved_at: Date | null
}
export const USER_DATES = ['created_at', 'approved_at'] as const

export interface LoginOut {
  token: string
  role: Role
  school_id: number
  name: string
}
```

`web/src/lib/session.ts`
```ts
import { readonly, ref } from 'vue'
import type { LoginOut } from '@/api/types'

// JWT 는 메모리에만 (auth.md). 앱(페이지)마다 모듈이 따로라 관리자·학생 세션이 섞이지 않는다.
export type AuthNotice = 'expired' | 'forbidden'

const current = ref<LoginOut | null>(null)
export const session = readonly(current)
export const authNotice = ref<AuthNotice | null>(null)

let onFailure: ((n: AuthNotice) => void) | null = null
export function onAuthFailure(cb: (n: AuthNotice) => void): void {
  onFailure = cb
}

export function setSession(s: LoginOut): void {
  current.value = s
  authNotice.value = null
}

/** 로그아웃 API 는 없다 — 토큰을 버리는 것이 로그아웃이다. notice 가 있으면 앱이 로그인 화면으로 보낸다. */
export function clearSession(notice?: AuthNotice): void {
  current.value = null
  if (notice) {
    authNotice.value = notice
    onFailure?.(notice)
  }
}
```

`web/src/api/client.ts` 전체
```ts
// 서버 계약의 유일한 출입구 (spec §4.1). 화면은 fetch 를 직접 부르지 않는다.
import { parseUtc } from '@/lib/time'
import { clearSession, session } from '@/lib/session'

export const MESSAGES: Record<number, string> = {
  0: '서버에 연결할 수 없습니다. 네트워크를 확인해 주세요.',
  400: '요청을 처리할 수 없습니다.',
  401: '다시 로그인해 주세요.',
  403: '이 화면을 쓸 권한이 없습니다.',
  404: '찾을 수 없습니다.',
  409: '다른 사람이 먼저 바꿨습니다. 목록을 새로 불러옵니다.',
  422: '입력값을 확인해 주세요.',
  429: '잠시 후 다시 시도해 주세요.',
  500: '서버 오류가 났습니다. 잠시 후 다시 시도해 주세요.',
  503: '요청이 몰렸습니다. 잠시 후 다시 시도해 주세요.',
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public fields: string[] = [],
    public detail: unknown = null,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
export interface RequestOpts {
  auth?: boolean
  dates?: readonly string[]
  signal?: AbortSignal
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

function withDates(v: unknown, keys: readonly string[]): unknown {
  if (Array.isArray(v)) return v.map((x) => withDates(x, keys))
  if (v && typeof v === 'object') {
    const o: Record<string, unknown> = { ...(v as Record<string, unknown>) }
    for (const k of keys) if (typeof o[k] === 'string') o[k] = parseUtc(o[k] as string)
    return o
  }
  return v
}

function fieldNames(detail: unknown): string[] {
  const list = (detail as { detail?: unknown } | null)?.detail
  if (!Array.isArray(list)) return []
  return list
    .map((x) => (x as { loc?: unknown[] }).loc?.at(-1))
    .filter((x): x is string => typeof x === 'string')
}

export async function request<T>(
  method: Method,
  path: string,
  body?: unknown,
  opts: RequestOpts = {},
): Promise<T> {
  const token = opts.auth === false ? null : (session.value?.token ?? null)
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['content-type'] = 'application/json'
  if (token) headers.authorization = `Bearer ${token}`

  let res: Response
  for (let attempt = 0; ; attempt++) {
    try {
      res = await fetch(path, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: opts.signal,
      })
    } catch (e) {
      if ((e as Error).name === 'AbortError') throw e
      throw new ApiError(0, MESSAGES[0])
    }
    // 멱등한 GET 만 1초 뒤 1회 (spec §4.1). 쓰기는 두 번 들어갈 수 있어 재시도하지 않는다
    if (res.status === 503 && method === 'GET' && attempt === 0) {
      await sleep(1000)
      continue
    }
    break
  }

  if (res.ok) {
    if (res.status === 204) return undefined as T
    const data: unknown = await res.json()
    return (opts.dates ? withDates(data, opts.dates) : data) as T
  }

  const detail: unknown = await res.json().catch(() => null)
  // 토큰을 보낸 요청만 — 로그인 실패 401(auth:false)은 세션 만료가 아니다
  if (token && res.status === 401) clearSession('expired')
  if (token && res.status === 403) {
    console.error('403 — 역할 불일치(정상 흐름이면 로그인 단계에서 막힌다)', path)
    clearSession('forbidden')
  }
  throw new ApiError(
    res.status,
    MESSAGES[res.status] ?? MESSAGES[500],
    res.status === 422 ? fieldNames(detail) : [],
    detail,
  )
}
```

`web/src/api/auth.ts`
```ts
import { request } from './client'
import { USER_DATES, type LoginOut, type UserOut } from './types'

const pub = { auth: false } as const

export const authApi = {
  signup: (email: string) => request<{ status: 'sent' }>('POST', '/api/auth/signup', { email }, pub),
  verifyOpen: (token: string) =>
    request<{ email: string }>('POST', '/api/auth/verify/open', { token }, pub),
  verify: (b: { token: string; name: string; student_no: string; password: string }) =>
    request<{ status: 'pending_approval' }>('POST', '/api/auth/verify', b, pub),
  login: (email: string, password: string) =>
    request<LoginOut>('POST', '/api/auth/login', { email, password }, pub),
  forgot: (email: string) => request<{ status: 'sent' }>('POST', '/api/auth/forgot', { email }, pub),
  reset: (token: string, password: string) =>
    request<{ status: 'ok' }>('POST', '/api/auth/reset', { token, password }, pub),
  me: () => request<UserOut>('GET', '/api/auth/me', undefined, { dates: USER_DATES }),
}
```
`web/src/api/users.ts`
```ts
import { request } from './client'
import { USER_DATES, type UserOut, type UserStatus } from './types'

const d = { dates: USER_DATES }
const path = (email: string, act: string) =>
  `/api/admin/users/${encodeURIComponent(email)}/${act}`

export const usersApi = {
  list: (status?: UserStatus) =>
    request<UserOut[]>('GET', `/api/admin/users${status ? `?status=${status}` : ''}`, undefined, d),
  approve: (email: string) => request<UserOut>('POST', path(email, 'approve'), undefined, d),
  reject: (email: string, reason: string) =>
    request<UserOut>('POST', path(email, 'reject'), { reason }, d),
  disable: (email: string) => request<UserOut>('POST', path(email, 'disable'), undefined, d),
  enable: (email: string) => request<UserOut>('POST', path(email, 'enable'), undefined, d),
}
```

- [ ] **Step 5: 통과 확인**

Run: `cd web && pnpm test src/lib src/api && pnpm typecheck && pnpm lint`
Expected: PASS. `TZ=America/New_York pnpm test src/lib` 도 PASS(시각 테스트가 로컬 시간대에 기대지 않는다).

- [ ] **Step 6: 커밋**

```bash
git add web/src/lib web/src/api
git commit -m "feat(web): API 클라이언트(시각 UTC 해석·401/403 세션 폐기·503 GET 재시도·네트워크 오류), 메모리 세션, KST 표시, 인증·회원 API"
```

---

### Task 4: 컴포저블 — useResource · usePolling · useCooldown

**Files:**
- Create: `web/src/lib/useResource.ts`, `web/src/lib/usePolling.ts`, `web/src/lib/useCooldown.ts`
- Test: `web/src/lib/__tests__/useResource.spec.ts`, `web/src/lib/__tests__/usePolling.spec.ts`, `web/src/lib/__tests__/useCooldown.spec.ts`

**Interfaces:**
- Consumes: `ApiError` (Task 3)
- Produces:
  - `useResource<T>(fetcher: () => Promise<T>, opts?: { immediate?: boolean; deps?: WatchSource | WatchSource[] }): { data: ShallowRef<T | undefined>; error: ShallowRef<ApiError | null>; loading: Ref<boolean>; refreshedAt: ShallowRef<Date | null>; reload: () => Promise<void> }`
  - `usePolling(fn: () => Promise<unknown>, ms: number): { stop: () => void }` — 반드시 `setup()`(effect scope) 안에서 부른다
  - `useCooldown(): { remaining: Ref<number>; active: ComputedRef<boolean>; start: (sec: number) => void }`

Ruling(spec §4.3 대비): "5분 넘으면 마지막 갱신 danger" 표시는 폴링 화면이 처음 생기는 F3 에서 `refreshedAt` 을 읽어 만든다. F1 화면(회원)에는 새로고침 주기가 없어 쓸 곳이 없다.

- [ ] **Step 1: 실패 테스트**

`web/src/lib/__tests__/useResource.spec.ts`
```ts
import { describe, expect, it } from 'vitest'
import { nextTick, ref } from 'vue'
import { ApiError } from '@/api/client'
import { useResource } from '@/lib/useResource'

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((a, b) => ((resolve = a), (reject = b)))
  return { promise, resolve, reject }
}
const flush = () => new Promise((r) => setTimeout(r))

describe('useResource', () => {
  it('늦게 온 옛 응답은 버린다 (Review Focus 3)', async () => {
    const calls: ReturnType<typeof deferred<string>>[] = []
    const r = useResource(() => {
      const d = deferred<string>()
      calls.push(d)
      return d.promise
    })
    void r.reload() // 두 번째 요청
    calls[1].resolve('new')
    await flush()
    calls[0].resolve('old')
    await flush()
    expect(r.data.value).toBe('new')
    expect(r.loading.value).toBe(false)
  })

  it('오류여도 이전 data 를 지킨다', async () => {
    let fail = false
    const r = useResource(async () => {
      if (fail) throw new ApiError(0, 'x')
      return 1
    })
    await flush()
    const first = r.refreshedAt.value
    fail = true
    await r.reload()
    expect(r.data.value).toBe(1)
    expect(r.error.value?.status).toBe(0)
    expect(r.refreshedAt.value).toBe(first)
  })

  it('성공하면 error 를 지운다', async () => {
    let fail = true
    const r = useResource(async () => {
      if (fail) throw new ApiError(500, 'x')
      return 2
    })
    await flush()
    fail = false
    await r.reload()
    expect(r.error.value).toBeNull()
    expect(r.data.value).toBe(2)
  })

  it('deps 가 바뀌면 다시 부른다, immediate:false 면 처음엔 안 부른다', async () => {
    const q = ref('a')
    const seen: string[] = []
    useResource(async () => seen.push(q.value), { deps: q, immediate: false })
    await flush()
    expect(seen).toEqual([])
    q.value = 'b'
    await nextTick()
    await flush()
    expect(seen).toEqual(['b'])
  })
})
```

`web/src/lib/__tests__/usePolling.spec.ts`
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import { usePolling } from '@/lib/usePolling'

let visibility: DocumentVisibilityState = 'visible'
beforeEach(() => {
  vi.useFakeTimers()
  visibility = 'visible'
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => visibility })
})
afterEach(() => vi.useRealTimers())
const setVisibility = (v: DocumentVisibilityState) => {
  visibility = v
  document.dispatchEvent(new Event('visibilitychange'))
}

describe('usePolling', () => {
  it('주기마다 부르고, 숨김이면 건너뛴다', async () => {
    const fn = vi.fn().mockResolvedValue(undefined)
    const scope = effectScope()
    scope.run(() => usePolling(fn, 1000))
    await vi.advanceTimersByTimeAsync(1000)
    expect(fn).toHaveBeenCalledTimes(1)
    setVisibility('hidden')
    await vi.advanceTimersByTimeAsync(3000)
    expect(fn).toHaveBeenCalledTimes(1)
    scope.stop()
  })

  it('다시 보이면 즉시 1회', async () => {
    const fn = vi.fn().mockResolvedValue(undefined)
    const scope = effectScope()
    scope.run(() => usePolling(fn, 60_000))
    setVisibility('hidden')
    setVisibility('visible')
    await vi.advanceTimersByTimeAsync(0)
    expect(fn).toHaveBeenCalledTimes(1)
    scope.stop()
  })

  it('이전 호출이 안 끝났으면 이번 틱은 건너뛴다 (겹침 금지)', async () => {
    let finish!: () => void
    const fn = vi.fn(() => new Promise<void>((r) => (finish = r)))
    const scope = effectScope()
    scope.run(() => usePolling(fn, 1000))
    await vi.advanceTimersByTimeAsync(3000)
    expect(fn).toHaveBeenCalledTimes(1)
    finish()
    await vi.advanceTimersByTimeAsync(1000)
    expect(fn).toHaveBeenCalledTimes(2)
    scope.stop()
  })

  it('scope 가 끝나면 멈추고 리스너도 뗀다', async () => {
    const fn = vi.fn().mockResolvedValue(undefined)
    const scope = effectScope()
    scope.run(() => usePolling(fn, 1000))
    scope.stop()
    setVisibility('visible')
    await vi.advanceTimersByTimeAsync(5000)
    expect(fn).not.toHaveBeenCalled()
  })
})
```

`web/src/lib/__tests__/useCooldown.spec.ts`
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import { useCooldown } from '@/lib/useCooldown'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('useCooldown', () => {
  it('10초 잠갔다가 풀린다 (Review Focus 5)', async () => {
    const scope = effectScope()
    const c = scope.run(() => useCooldown())!
    c.start(10)
    expect(c.active.value).toBe(true)
    expect(c.remaining.value).toBe(10)
    await vi.advanceTimersByTimeAsync(9000)
    expect(c.remaining.value).toBe(1)
    await vi.advanceTimersByTimeAsync(1000)
    expect(c.active.value).toBe(false)
    expect(c.remaining.value).toBe(0)
    scope.stop()
  })

  it('다시 start 하면 처음부터', async () => {
    const scope = effectScope()
    const c = scope.run(() => useCooldown())!
    c.start(60)
    await vi.advanceTimersByTimeAsync(30_000)
    c.start(60)
    expect(c.remaining.value).toBe(60)
    scope.stop()
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/lib`
Expected: FAIL — `Failed to resolve import "@/lib/useResource"`

- [ ] **Step 3: 구현**

`web/src/lib/useResource.ts`
```ts
import { ref, shallowRef, watch, type WatchSource } from 'vue'
import { ApiError } from '@/api/client'

/** 읽기 전용 리소스. 새 요청이 나가면 옛 응답은 버리고(요청 번호), 오류여도 이전 data 를 지킨다 (spec §4.3). */
export function useResource<T>(
  fetcher: () => Promise<T>,
  opts: { immediate?: boolean; deps?: WatchSource | WatchSource[] } = {},
) {
  const data = shallowRef<T>()
  const error = shallowRef<ApiError | null>(null)
  const loading = ref(false)
  const refreshedAt = shallowRef<Date | null>(null)
  let seq = 0

  async function reload(): Promise<void> {
    const mine = ++seq
    loading.value = true
    try {
      const v = await fetcher()
      if (mine !== seq) return
      data.value = v
      error.value = null
      refreshedAt.value = new Date()
    } catch (e) {
      if (mine !== seq) return
      if (!(e instanceof ApiError)) throw e // 버그는 삼키지 않는다
      error.value = e
    } finally {
      if (mine === seq) loading.value = false
    }
  }

  if (opts.deps) watch(opts.deps, () => void reload())
  if (opts.immediate !== false) void reload()
  return { data, error, loading, refreshedAt, reload }
}
```
`web/src/lib/usePolling.ts`
```ts
import { onScopeDispose } from 'vue'

/** 숨김이면 건너뛰고, 보이면 즉시 1회. 이전 호출이 안 끝났으면 이번 틱은 건너뛴다 (spec §4.3). */
export function usePolling(fn: () => Promise<unknown>, ms: number) {
  let running = false
  const tick = async () => {
    if (running || document.visibilityState === 'hidden') return
    running = true
    try {
      await fn()
    } catch (e) {
      console.error(e)
    } finally {
      running = false
    }
  }
  const timer = setInterval(() => void tick(), ms)
  const onVisible = () => {
    if (document.visibilityState === 'visible') void tick()
  }
  document.addEventListener('visibilitychange', onVisible)
  const stop = () => {
    clearInterval(timer)
    document.removeEventListener('visibilitychange', onVisible)
  }
  onScopeDispose(stop)
  return { stop }
}
```
`web/src/lib/useCooldown.ts`
```ts
import { computed, onScopeDispose, ref } from 'vue'

/** 버튼 잠금 초 세기 — 429 뒤 10초, 메일 재전송 60초. 서버가 남은 시간을 주지 않아 고정값이다. */
export function useCooldown() {
  const remaining = ref(0)
  let timer: ReturnType<typeof setInterval> | null = null
  const clear = () => {
    if (timer) clearInterval(timer)
    timer = null
  }
  function start(sec: number) {
    clear()
    remaining.value = sec
    timer = setInterval(() => {
      remaining.value -= 1
      if (remaining.value <= 0) {
        remaining.value = 0
        clear()
      }
    }, 1000)
  }
  onScopeDispose(clear)
  return { remaining, active: computed(() => remaining.value > 0), start }
}
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test src/lib && pnpm typecheck && pnpm lint`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add web/src/lib
git commit -m "feat(web): useResource(늦은 응답 폐기·오류 시 데이터 유지)·usePolling(숨김 정지·겹침 방지)·useCooldown"
```

---

### Task 5: ui — Button · Badge · Skeleton · EmptyState

**Files:**
- Create: `web/src/components/ui/Button.vue`, `web/src/components/ui/Badge.vue`, `web/src/components/ui/Skeleton.vue`, `web/src/components/ui/EmptyState.vue`
- Delete: `web/src/components/ui/.gitkeep`
- Test: `web/src/components/ui/__tests__/basic.spec.ts`

**Interfaces:** (props 는 `components.md` 표 그대로 — 표가 곧 인터페이스)
- `Button` props `variant?: 'primary'|'secondary'|'danger'|'ghost'`(primary) · `size?: 'sm'|'md'`(md) · `disabled?` · `loading?` · `loadingLabel?: string` · `type?: 'button'|'submit'`(button). 기본 슬롯 = 라벨. 루트는 `<button>` 이라 `@click` 은 그대로 붙는다.
- `Badge` props `variant?: 'solid'|'tint'|'outline'`(tint) · `tone?: 'neutral'|'busy'|'danger'|'brand'`(neutral) · `size?: 'xs'|'sm'`(xs). 기본 슬롯 = 라벨(필수).
- `Skeleton` props `variant?: 'text'|'block'`(text) · `rows?: number`(1) · `width?: string`('100%')
- `EmptyState` props `message: string` · `actions?: { label: string; variant?: ButtonVariant; onClick: () => void }[]`([])
- `Button.vue` 에서 `export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost'` 를 `<script lang="ts">`(setup 아닌 블록)로 내보낸다.

Ruling: Badge 는 `components.md` 표에 있는 4 조합(`busy+tint`·`neutral+outline`·`neutral+solid`·`danger+outline`)만 스타일을 준다. 표에 없는 조합(기본값 `tint+neutral`, `brand` tone 전부)은 테두리·바탕 없는 글자로 두고, PR 에서 mh 에 확인을 요청한다 — 스펙에 없는 variant 를 먼저 만들지 않는다(web/CLAUDE.md).

- [ ] **Step 1: 실패 테스트**

`web/src/components/ui/__tests__/basic.spec.ts`
```ts
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import Button from '@/components/ui/Button.vue'
import Badge from '@/components/ui/Badge.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import EmptyState from '@/components/ui/EmptyState.vue'

describe('Button', () => {
  it('기본은 primary·md·type=button', () => {
    const w = mount(Button, { slots: { default: '저장' } })
    const b = w.get('button')
    expect(b.text()).toBe('저장')
    expect(b.classes()).toEqual(expect.arrayContaining(['btn--primary', 'btn--md']))
    expect(b.attributes('type')).toBe('button')
  })

  it('loading 은 라벨을 유지하고 잠근다', () => {
    const w = mount(Button, { props: { loading: true }, slots: { default: '저장' } })
    expect(w.get('button').text()).toBe('저장')
    expect(w.get('button').element.disabled).toBe(true)
    expect(w.find('.btn__spin').exists()).toBe(true)
  })

  it('loadingLabel 이 있으면 진행도로 바꾼다', () => {
    const w = mount(Button, {
      props: { loading: true, loadingLabel: '3/7 적용 중' },
      slots: { default: '적용' },
    })
    expect(w.get('button').text()).toBe('3/7 적용 중')
  })

  it('disabled 면 click 이 나가지 않는다', async () => {
    const onClick = vi.fn()
    const w = mount(Button, { props: { disabled: true }, attrs: { onClick } })
    await w.get('button').trigger('click')
    expect(onClick).not.toHaveBeenCalled()
  })
})

describe('Badge', () => {
  it.each([
    ['busy', 'tint'],
    ['neutral', 'outline'],
    ['neutral', 'solid'],
    ['danger', 'outline'],
  ])('%s + %s', (tone, variant) => {
    const w = mount(Badge, { props: { tone, variant } as never, slots: { default: '대기중' } })
    expect(w.classes()).toEqual(expect.arrayContaining([`badge--${tone}`, `badge--${variant}`]))
    expect(w.text()).toBe('대기중')
  })
})

describe('Skeleton', () => {
  it('text 는 rows 줄, 마지막 줄은 60%', () => {
    const w = mount(Skeleton, { props: { rows: 3 } })
    const lines = w.findAll('.sk__line')
    expect(lines).toHaveLength(3)
    expect(lines[2].attributes('style')).toContain('width: 60%')
    expect(lines[0].attributes('style')).toContain('width: 100%')
  })

  it('한 줄이면 60% 로 줄이지 않는다', () => {
    const w = mount(Skeleton)
    expect(w.get('.sk__line').attributes('style')).toContain('width: 100%')
  })
})

describe('EmptyState', () => {
  it('버튼은 최대 2개, 누르면 onClick', async () => {
    const a = vi.fn()
    const w = mount(EmptyState, {
      props: {
        message: '이 건물에 등록된 시간표가 없습니다',
        actions: [
          { label: 'CSV 가져오기', variant: 'secondary', onClick: a },
          { label: '슬롯 추가', onClick: vi.fn() },
          { label: '세 번째', onClick: vi.fn() },
        ],
      },
    })
    expect(w.text()).toContain('이 건물에 등록된 시간표가 없습니다')
    const buttons = w.findAll('button')
    expect(buttons).toHaveLength(2)
    await buttons[0].trigger('click')
    expect(a).toHaveBeenCalledOnce()
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/components`
Expected: FAIL — `Failed to resolve import "@/components/ui/Button.vue"`

- [ ] **Step 3: 구현**

`web/src/components/ui/Button.vue`
```vue
<script lang="ts">
export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost'
</script>

<script setup lang="ts">
withDefaults(
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
    <template v-if="loading && loadingLabel">{{ loadingLabel }}</template>
    <slot v-else />
  </button>
</template>

<style scoped>
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  height: var(--control-height-md);
  padding: 0 var(--space-4);
  border: var(--border-thin) solid transparent;
  border-radius: var(--radius-md);
  font: inherit;
  font-weight: var(--font-weight-medium);
  white-space: nowrap;
  cursor: pointer;
}
.btn--sm {
  height: var(--control-height-sm);
}
.btn--primary {
  background: var(--brand);
  color: var(--on-brand);
}
.btn--danger {
  background: var(--danger);
  color: var(--on-brand);
}
.btn--secondary {
  background: var(--surface);
  border-color: var(--line-3);
  color: var(--text-1);
}
.btn--ghost {
  background: transparent;
  color: var(--text-1);
}
.btn--primary:hover:enabled,
.btn--danger:hover:enabled {
  filter: brightness(0.9);
}
.btn--secondary:hover:enabled,
.btn--ghost:hover:enabled {
  background: var(--sunken);
}
/* disabled: 글자 text.disabled + opacity .6, hue 는 그대로. loading 은 잠그기만 하고 색은 유지 */
.btn:disabled:not([aria-busy]) {
  color: var(--text-disabled);
  opacity: 0.6;
  cursor: not-allowed;
}
.btn[aria-busy] {
  cursor: progress;
}
.btn__spin {
  width: 1em;
  height: 1em;
  border: var(--border-thick) solid currentColor;
  border-right-color: transparent;
  border-radius: var(--radius-full);
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .btn__spin {
    animation: none;
  }
}
</style>
```

`web/src/components/ui/Badge.vue`
```vue
<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: 'solid' | 'tint' | 'outline'
    tone?: 'neutral' | 'busy' | 'danger' | 'brand'
    size?: 'xs' | 'sm'
  }>(),
  { variant: 'tint', tone: 'neutral', size: 'xs' },
)
</script>

<template>
  <span class="badge" :class="[`badge--${variant}`, `badge--${tone}`, `badge--${size}`]">
    <slot />
  </span>
</template>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--space-2);
  border: var(--border-thin) solid transparent;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  line-height: var(--leading-tight);
  white-space: nowrap;
}
.badge--sm {
  font-size: var(--font-size-sm);
}
/* components.md 표의 네 조합만 — 표에 없는 조합은 mh 확인 뒤 */
.badge--busy.badge--tint {
  background: var(--room-busy-fill);
  border-color: var(--room-busy-line);
  color: var(--room-busy-label);
}
.badge--neutral.badge--outline {
  border-color: var(--line-3);
  color: var(--text-2);
}
.badge--neutral.badge--solid {
  background: var(--sunken);
  color: var(--text-1);
}
.badge--danger.badge--outline {
  border-color: var(--danger);
  color: var(--danger);
}
</style>
```

`web/src/components/ui/Skeleton.vue`
```vue
<script setup lang="ts">
withDefaults(
  defineProps<{ variant?: 'text' | 'block'; rows?: number; width?: string }>(),
  { variant: 'text', rows: 1, width: '100%' },
)
</script>

<template>
  <div class="sk" :class="`sk--${variant}`" aria-hidden="true">
    <template v-if="variant === 'text'">
      <span
        v-for="i in rows"
        :key="i"
        class="sk__line"
        :style="{ width: rows > 1 && i === rows ? '60%' : width }"
      />
    </template>
    <span v-else class="sk__block" :style="{ width }" />
  </div>
</template>

<style scoped>
.sk--text {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.sk__line,
.sk__block {
  display: block;
  border-radius: var(--radius-sm);
  background: var(--skeleton-a);
  animation: pulse 1.4s ease-in-out infinite;
}
.sk__line {
  height: var(--font-size-md);
}
.sk__block {
  height: 100%;
  min-height: var(--control-height-md);
}
@keyframes pulse {
  50% {
    background: var(--skeleton-b);
  }
}
@media (prefers-reduced-motion: reduce) {
  .sk__line,
  .sk__block {
    animation: none;
  }
}
</style>
```

`web/src/components/ui/EmptyState.vue`
```vue
<script setup lang="ts">
import Button, { type ButtonVariant } from './Button.vue'

withDefaults(
  defineProps<{
    message: string
    actions?: { label: string; variant?: ButtonVariant; onClick: () => void }[]
  }>(),
  { actions: () => [] },
)
</script>

<template>
  <div class="empty">
    <p class="empty__msg">{{ message }}</p>
    <div v-if="actions.length" class="empty__actions">
      <!-- 최대 2개 (components.md) -->
      <Button
        v-for="a in actions.slice(0, 2)"
        :key="a.label"
        :variant="a.variant ?? 'secondary'"
        @click="a.onClick"
        >{{ a.label }}</Button
      >
    </div>
  </div>
</template>

<style scoped>
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-6) var(--space-4);
  text-align: center;
}
.empty__msg {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.empty__actions {
  display: flex;
  gap: var(--space-2);
}
</style>
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint && pnpm exec prettier --check .`
Expected: PASS (토큰 가드가 새 `.vue` 4개도 검사해 통과)

- [ ] **Step 5: 커밋**

```bash
git add -A web/src/components/ui
git commit -m "style(web): ui Button·Badge·Skeleton·EmptyState (components.md v2)"
```

---

### Task 6: ui — Input · Textarea · Select · Checkbox

**Files:**
- Create: `web/src/components/ui/Input.vue`, `web/src/components/ui/Textarea.vue`, `web/src/components/ui/Select.vue`, `web/src/components/ui/Checkbox.vue`, `web/src/lib/bytes.ts`
- Test: `web/src/components/ui/__tests__/form.spec.ts`

**Interfaces:**
- `Input` props `modelValue?: string|number` · `label?` · `hint?` · `error?` · `required?` · `disabled?` · `size?: 'sm'|'md'` · `maxBytes?: number` · (내부) `multiline?: boolean`. emit `update:modelValue(string)`. 그 밖의 속성(`type`·`placeholder`·`autocomplete`·`readonly`·`maxlength`·`name`)은 `<input>` 으로 그대로 간다(`inheritAttrs: false`).
- `Textarea` = `Input` + `multiline`(같은 props, `rows` 속성 통과).
- `Select` props `modelValue?: string|number` · `options: { value: string|number; label: string; disabled?: boolean }[]` · `label?` · `placeholder?` · `disabled?` · `size?`. emit `update:modelValue(원래 타입 값)`.
- `Checkbox` props `modelValue?: boolean | unknown[]` · `value?: unknown` · `label?` · `indeterminate?` · `disabled?`. emit `update:modelValue(boolean | unknown[])`.
- `lib/bytes.ts`: `utf8Bytes(s: string): number` · `clipBytes(s: string, max: number): string`(코드 포인트 단위로 자름 — 한글 한 글자를 반으로 자르지 않는다)

`maxBytes` 는 글자 수가 아니라 UTF-8 바이트다(components.md) — 서버 `subject`·`professor` 상한이 바이트라서. 한글 IME 조합 중에는 자르지 않고 조합이 끝나면(`compositionend`) 자른다 — 조합 중에 값을 되돌리면 입력이 깨진다.

- [ ] **Step 1: 실패 테스트**

`web/src/components/ui/__tests__/form.spec.ts`
```ts
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import Input from '@/components/ui/Input.vue'
import Textarea from '@/components/ui/Textarea.vue'
import Select from '@/components/ui/Select.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import { clipBytes, utf8Bytes } from '@/lib/bytes'

describe('bytes', () => {
  it('UTF-8 바이트를 세고 코드 포인트 단위로 자른다', () => {
    expect(utf8Bytes('한글a')).toBe(7)
    expect(clipBytes('한글한글', 10)).toBe('한글한')
    expect(clipBytes('ab', 10)).toBe('ab')
    expect(clipBytes('😀a', 3)).toBe('') // 4바이트 이모지를 반으로 자르지 않는다
  })
})

describe('Input', () => {
  it('label 과 input 이 id 로 이어지고 required 면 * 가 붙는다', () => {
    const w = mount(Input, { props: { label: '이름', required: true } })
    const id = w.get('input').attributes('id')
    expect(w.get('label').attributes('for')).toBe(id)
    expect(w.get('label').text()).toBe('이름*')
  })

  it('error 는 hint 자리를 대체하고 aria-invalid', () => {
    const w = mount(Input, { props: { hint: '8자 이상', error: '비밀번호가 짧습니다' } })
    expect(w.text()).toContain('비밀번호가 짧습니다')
    expect(w.text()).not.toContain('8자 이상')
    expect(w.get('input').attributes('aria-invalid')).toBe('true')
  })

  it('v-model 과 속성 통과', async () => {
    const w = mount(Input, { props: { modelValue: '' }, attrs: { type: 'password', autocomplete: 'new-password' } })
    expect(w.get('input').attributes('type')).toBe('password')
    await w.get('input').setValue('abc')
    expect(w.emitted('update:modelValue')![0]).toEqual(['abc'])
  })

  it('maxBytes — 남은 양을 보이고 넘으면 자른다', async () => {
    const w = mount(Input, { props: { modelValue: '한글', maxBytes: 10 } })
    expect(w.text()).toContain('6 / 10 B')
    await w.get('input').setValue('한글한글')
    expect(w.emitted('update:modelValue')!.at(-1)).toEqual(['한글한'])
    expect((w.get('input').element as HTMLInputElement).value).toBe('한글한')
  })
})

describe('Textarea', () => {
  it('textarea 로 그린다', async () => {
    const onUpdate = vi.fn()
    const w = mount(Textarea, {
      attrs: { label: '사유', modelValue: '', rows: 4, 'onUpdate:modelValue': onUpdate },
    })
    expect(w.find('textarea').attributes('rows')).toBe('4')
    await w.get('textarea').setValue('학번이 잘못되었습니다')
    expect(onUpdate).toHaveBeenCalledWith('학번이 잘못되었습니다')
  })
})

describe('Select', () => {
  const options = [
    { value: 1, label: '월' },
    { value: 2, label: '화' },
  ]
  it('네이티브 select, 원래 타입 값으로 emit', async () => {
    const w = mount(Select, { props: { options, modelValue: 1, label: '요일' } })
    expect(w.findAll('option')).toHaveLength(2)
    await w.get('select').setValue('2')
    expect(w.emitted('update:modelValue')![0]).toEqual([2])
  })
  it('placeholder 는 고를 수 없는 첫 항목', () => {
    const w = mount(Select, { props: { options, placeholder: '선택' } })
    const first = w.findAll('option')[0]
    expect(first.text()).toBe('선택')
    expect(first.attributes('disabled')).toBeDefined()
  })
})

describe('Checkbox', () => {
  it('boolean v-model', async () => {
    const w = mount(Checkbox, { props: { modelValue: false, label: '받음' } })
    await w.get('input').setValue(true)
    expect(w.emitted('update:modelValue')![0]).toEqual([true])
  })
  it('배열 v-model 은 value 를 넣고 뺀다', async () => {
    const w = mount(Checkbox, { props: { modelValue: [1], value: 2 } })
    await w.get('input').setValue(true)
    expect(w.emitted('update:modelValue')![0]).toEqual([[1, 2]])
    await w.setProps({ modelValue: [1, 2] })
    await w.get('input').setValue(false)
    expect(w.emitted('update:modelValue')![1]).toEqual([[1]])
  })
  it('indeterminate 는 DOM 속성으로', () => {
    const w = mount(Checkbox, { props: { modelValue: false, indeterminate: true } })
    expect((w.get('input').element as HTMLInputElement).indeterminate).toBe(true)
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/components`
Expected: FAIL — `Failed to resolve import "@/components/ui/Input.vue"`

- [ ] **Step 3: 구현**

`web/src/lib/bytes.ts`
```ts
const enc = new TextEncoder()
export const utf8Bytes = (s: string) => enc.encode(s).length

/** max 바이트 안에 드는 앞부분 — 코드 포인트 단위라 글자를 반으로 자르지 않는다 */
export function clipBytes(s: string, max: number): string {
  let out = ''
  let n = 0
  for (const ch of s) {
    n += utf8Bytes(ch)
    if (n > max) break
    out += ch
  }
  return out
}
```

`web/src/components/ui/Input.vue`
```vue
<script setup lang="ts">
import { computed, useId } from 'vue'
import { clipBytes, utf8Bytes } from '@/lib/bytes'

defineOptions({ inheritAttrs: false })
const props = withDefaults(
  defineProps<{
    modelValue?: string | number
    label?: string
    hint?: string
    error?: string
    required?: boolean
    disabled?: boolean
    size?: 'sm' | 'md'
    maxBytes?: number
    multiline?: boolean
  }>(),
  { size: 'md' },
)
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const id = useId()
const msgId = `${id}-msg`
const bytes = computed(() => utf8Bytes(String(props.modelValue ?? '')))
const hasMsg = computed(() => Boolean(props.error || props.hint || props.maxBytes))

function commit(el: HTMLInputElement | HTMLTextAreaElement) {
  let v = el.value
  if (props.maxBytes && utf8Bytes(v) > props.maxBytes) {
    v = clipBytes(v, props.maxBytes)
    el.value = v
  }
  emit('update:modelValue', v)
}
function onInput(e: Event) {
  if ((e as InputEvent).isComposing) return // 한글 조합 중에는 자르지 않는다
  commit(e.target as HTMLInputElement)
}
</script>

<template>
  <div class="field" :class="[`field--${size}`, { 'field--error': error }]">
    <label v-if="label" :for="id" class="field__label"
      >{{ label }}<span v-if="required" class="field__req" aria-hidden="true">*</span></label
    >
    <component
      :is="multiline ? 'textarea' : 'input'"
      :id="id"
      class="field__control"
      :class="{ 'field__control--multi': multiline }"
      :value="modelValue ?? ''"
      :required="required"
      :disabled="disabled"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="hasMsg ? msgId : undefined"
      v-bind="$attrs"
      @input="onInput"
      @compositionend="commit($event.target)"
    />
    <p v-if="error" :id="msgId" class="field__msg field__msg--error" role="alert">{{ error }}</p>
    <p v-else-if="hint || maxBytes" :id="msgId" class="field__msg">
      <span>{{ hint }}</span>
      <span v-if="maxBytes" class="num">{{ bytes }} / {{ maxBytes }} B</span>
    </p>
  </div>
</template>

<style scoped>
.field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.field__label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-regular);
  color: var(--text-2);
}
.field__req {
  margin-left: 2px;
  color: var(--danger);
}
.field__control {
  height: var(--control-height-md);
  padding: 0 var(--space-3);
  border: var(--border-thin) solid var(--line-3);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-1);
  font: inherit;
}
.field--sm .field__control {
  height: var(--control-height-sm);
}
.field__control--multi {
  height: auto;
  padding: var(--space-2) var(--space-3);
  resize: vertical;
}
.field__control:disabled {
  color: var(--text-disabled);
  opacity: 0.6;
  cursor: not-allowed;
}
.field__control[readonly] {
  background: var(--sunken);
}
.field--error .field__control {
  border: var(--border-thick) solid var(--danger);
}
/* 에러와 포커스가 겹치면 outline 만 */
.field--error .field__control:focus-visible {
  border-color: var(--line-3);
}
.field__msg {
  display: flex;
  justify-content: space-between;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.field__msg--error {
  color: var(--danger);
}
</style>
```
`web/src/components/ui/Textarea.vue`
```vue
<script setup lang="ts">
import Input from './Input.vue'
</script>

<template>
  <Input multiline />
</template>
```
(`inheritAttrs` 기본값이라 `modelValue`·`label`·`rows`·`onUpdate:modelValue` 가 전부 `Input` 으로 간다.)

`web/src/components/ui/Select.vue`
```vue
<script setup lang="ts">
import { useId } from 'vue'

type Opt = { value: string | number; label: string; disabled?: boolean }
const props = withDefaults(
  defineProps<{
    modelValue?: string | number
    options: Opt[]
    label?: string
    placeholder?: string
    disabled?: boolean
    size?: 'sm' | 'md'
  }>(),
  { size: 'md' },
)
const emit = defineEmits<{ 'update:modelValue': [value: string | number] }>()
const id = useId()

function onChange(e: Event) {
  const i = (e.target as HTMLSelectElement).selectedIndex - (props.placeholder ? 1 : 0)
  const opt = props.options[i]
  if (opt) emit('update:modelValue', opt.value)
}
</script>

<template>
  <div class="sel" :class="`sel--${size}`">
    <label v-if="label" :for="id" class="sel__label">{{ label }}</label>
    <select
      :id="id"
      class="sel__control"
      :disabled="disabled"
      :value="modelValue ?? ''"
      @change="onChange"
    >
      <option v-if="placeholder" value="" disabled>{{ placeholder }}</option>
      <option v-for="o in options" :key="o.value" :value="o.value" :disabled="o.disabled">
        {{ o.label }}
      </option>
    </select>
  </div>
</template>

<style scoped>
.sel {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.sel__label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-regular);
  color: var(--text-2);
}
.sel__control {
  height: var(--control-height-md);
  padding: 0 calc(var(--space-3) * 2 + 8px) 0 var(--space-3);
  border: var(--border-thin) solid var(--line-3);
  border-radius: var(--radius-sm);
  color: var(--text-1);
  font: inherit;
  appearance: none;
  /* 화살표만 배경으로 갈아 끼운다 (components.md) — 두 삼각 그라데이션으로 V 자 */
  background:
    linear-gradient(45deg, transparent 50%, var(--text-2) 50%) no-repeat
      calc(100% - var(--space-3) - 4px) 50% / 4px 4px,
    linear-gradient(135deg, var(--text-2) 50%, transparent 50%) no-repeat
      calc(100% - var(--space-3)) 50% / 4px 4px,
    var(--surface);
}
.sel--sm .sel__control {
  height: var(--control-height-sm);
}
.sel__control:disabled {
  color: var(--text-disabled);
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
```

`web/src/components/ui/Checkbox.vue`
```vue
<script setup lang="ts">
import { computed, ref, watchEffect } from 'vue'

const props = defineProps<{
  modelValue?: boolean | unknown[]
  value?: unknown
  label?: string
  indeterminate?: boolean
  disabled?: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean | unknown[]] }>()
const el = ref<HTMLInputElement>()
const checked = computed(() =>
  Array.isArray(props.modelValue) ? props.modelValue.includes(props.value) : !!props.modelValue,
)
watchEffect(() => {
  if (el.value) el.value.indeterminate = !!props.indeterminate
})

function onChange(e: Event) {
  const on = (e.target as HTMLInputElement).checked
  if (Array.isArray(props.modelValue)) {
    const rest = props.modelValue.filter((v) => v !== props.value)
    emit('update:modelValue', on ? [...rest, props.value] : rest)
  } else emit('update:modelValue', on)
}
</script>

<template>
  <label class="cb" :class="{ 'cb--disabled': disabled }">
    <span class="cb__wrap">
      <input
        ref="el"
        type="checkbox"
        class="cb__input"
        :checked="checked"
        :disabled="disabled"
        @change="onChange"
      />
      <span class="cb__box" aria-hidden="true" />
    </span>
    <span v-if="label || $slots.default"
      ><slot>{{ label }}</slot></span
    >
  </label>
</template>

<style scoped>
.cb {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--control-height-sm); /* 28px */
  cursor: pointer;
}
/* 학생 웹은 터치 타깃 48px (components.md Checkbox) */
:global([data-surface='student']) .cb {
  min-height: var(--control-height-md);
}
.cb--disabled {
  color: var(--text-disabled);
  opacity: 0.6;
  cursor: not-allowed;
}
.cb__wrap {
  position: relative;
  width: 16px;
  height: 16px;
}
.cb__input {
  position: absolute;
  inset: 0;
  margin: 0;
  opacity: 0;
  cursor: inherit;
}
.cb__box {
  position: absolute;
  inset: 0;
  border: var(--border-thin) solid var(--line-3);
  border-radius: var(--radius-sm);
  background: var(--surface);
  pointer-events: none;
}
.cb__input:checked + .cb__box,
.cb__input:indeterminate + .cb__box {
  border-color: var(--brand);
  background: var(--brand);
}
.cb__input:checked + .cb__box::after {
  content: '';
  position: absolute;
  left: 4px;
  top: 1px;
  width: 5px;
  height: 9px;
  border: solid var(--on-brand);
  border-width: 0 var(--border-thick) var(--border-thick) 0;
  transform: rotate(45deg);
}
.cb__input:indeterminate + .cb__box::after {
  content: '';
  position: absolute;
  left: 3px;
  right: 3px;
  top: 6px;
  height: var(--border-thick);
  background: var(--on-brand);
}
.cb__input:focus-visible + .cb__box {
  outline: var(--border-thick) solid var(--focus);
  outline-offset: 2px;
}
</style>
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint && pnpm exec prettier --check .`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add web/src/components/ui web/src/lib/bytes.ts
git commit -m "style(web): ui Input·Textarea(UTF-8 바이트 상한, IME 조합 보호)·Select(네이티브)·Checkbox(indeterminate)"
```

---

### Task 7: ui — Table

**Files:**
- Create: `web/src/components/ui/Table.vue`
- Test: `web/src/components/ui/__tests__/table.spec.ts`

**Interfaces:**
- Consumes: `Skeleton`, `EmptyState` (Task 5)
- Produces `Table` props: `columns: { key: string; label: string; align?: 'left'|'right'|'center'; width?: string; sticky?: boolean }[]` · `rows: Record<string, unknown>[]` · `rowKey?: string`('id') · `selected?: string[]`([]) · `loading?` · `empty?: string`('항목이 없습니다') · `expandable?`
- 슬롯: `cell-<key>`(`{ row }`) — 없으면 `row[key]` 를 글자로 · `expanded`(`{ row }`) · `empty` — 없으면 `EmptyState :message="empty"`
- `align: 'right'` 열은 `tabular-nums` 가 자동으로 붙는다(숫자 열 규칙).

- [ ] **Step 1: 실패 테스트**

`web/src/components/ui/__tests__/table.spec.ts`
```ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import Table from '@/components/ui/Table.vue'

const columns = [
  { key: 'name', label: '이름', width: '96px' },
  { key: 'count', label: '건수', align: 'right' as const },
]
const rows = [
  { id: 'a', name: '김민준', count: 3 },
  { id: 'b', name: '이정민', count: 12 },
]

describe('Table', () => {
  it('헤더와 셀을 그린다, 숫자 열은 우측·tabular', () => {
    const w = mount(Table, { props: { columns, rows } })
    expect(w.findAll('th').map((t) => t.text())).toEqual(['이름', '건수'])
    expect(w.get('th').attributes('style')).toContain('width: 96px')
    const cells = w.findAll('tbody tr')[1].findAll('td')
    expect(cells.map((c) => c.text())).toEqual(['이정민', '12'])
    expect(cells[1].classes()).toEqual(expect.arrayContaining(['tbl__cell--right', 'num']))
  })

  it('cell 슬롯이 기본 표시를 대신한다', () => {
    const w = mount(Table, {
      props: { columns, rows },
      slots: { 'cell-name': '<template #cell-name="{ row }"><b>{{ row.name }}님</b></template>' },
    })
    expect(w.get('tbody b').text()).toBe('김민준님')
  })

  it('선택된 행', () => {
    const w = mount(Table, { props: { columns, rows, selected: ['b'] } })
    const trs = w.findAll('tbody tr')
    expect(trs[0].classes()).not.toContain('tbl__row--selected')
    expect(trs[1].classes()).toContain('tbl__row--selected')
  })

  it('loading 이면 헤더는 두고 Skeleton 행 5개', () => {
    const w = mount(Table, { props: { columns, rows, loading: true } })
    expect(w.findAll('th')).toHaveLength(2)
    expect(w.findAll('tbody tr')).toHaveLength(5)
    expect(w.text()).not.toContain('김민준')
  })

  it('행이 없으면 empty 문구, 슬롯이 있으면 슬롯', () => {
    expect(mount(Table, { props: { columns, rows: [], empty: '회원이 없습니다' } }).text()).toContain(
      '회원이 없습니다',
    )
    const w = mount(Table, { props: { columns, rows: [] }, slots: { empty: '<p class="x">직접</p>' } })
    expect(w.find('.x').exists()).toBe(true)
  })

  it('expandable — 펼치면 expanded 슬롯', async () => {
    const w = mount(Table, {
      props: { columns, rows, expandable: true },
      slots: { expanded: '<template #expanded="{ row }"><i>{{ row.name }} 상세</i></template>' },
    })
    expect(w.find('i').exists()).toBe(false)
    const toggle = w.findAll('button.tbl__toggle')[0]
    expect(toggle.attributes('aria-expanded')).toBe('false')
    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(w.get('i').text()).toBe('김민준 상세')
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/components/ui/__tests__/table.spec.ts`
Expected: FAIL — `Failed to resolve import "@/components/ui/Table.vue"`

- [ ] **Step 3: 구현**

`web/src/components/ui/Table.vue`
```vue
<script setup lang="ts">
import { reactive } from 'vue'
import Skeleton from './Skeleton.vue'
import EmptyState from './EmptyState.vue'

type Col = {
  key: string
  label: string
  align?: 'left' | 'right' | 'center'
  width?: string
  sticky?: boolean
}
const props = withDefaults(
  defineProps<{
    columns: Col[]
    rows: Record<string, unknown>[]
    rowKey?: string
    selected?: string[]
    loading?: boolean
    empty?: string
    expandable?: boolean
  }>(),
  { rowKey: 'id', selected: () => [], loading: false, empty: '항목이 없습니다', expandable: false },
)
const open = reactive(new Set<string>())
const keyOf = (row: Record<string, unknown>) => String(row[props.rowKey])
const toggle = (k: string) => (open.has(k) ? open.delete(k) : open.add(k))
const cellClass = (c: Col) => [
  `tbl__cell--${c.align ?? 'left'}`,
  { num: c.align === 'right', 'tbl__cell--sticky': c.sticky },
]
const span = () => props.columns.length + (props.expandable ? 1 : 0)
</script>

<template>
  <div class="tbl-wrap">
    <table class="tbl">
      <thead>
        <tr>
          <th v-if="expandable" class="tbl__toggle-col" aria-label="펼치기" />
          <th
            v-for="c in columns"
            :key="c.key"
            scope="col"
            :class="cellClass(c)"
            :style="c.width ? { width: c.width } : undefined"
          >
            {{ c.label }}
          </th>
        </tr>
      </thead>
      <tbody>
        <template v-if="loading">
          <tr v-for="i in 5" :key="`sk${i}`" class="tbl__row">
            <td :colspan="span()"><Skeleton /></td>
          </tr>
        </template>
        <tr v-else-if="rows.length === 0">
          <td :colspan="span()" class="tbl__empty">
            <slot name="empty"><EmptyState :message="empty" /></slot>
          </td>
        </tr>
        <template v-else>
        <template v-for="row in rows" :key="keyOf(row)">
          <tr class="tbl__row" :class="{ 'tbl__row--selected': selected.includes(keyOf(row)) }">
            <td v-if="expandable" class="tbl__toggle-col">
              <button
                type="button"
                class="tbl__toggle"
                :aria-expanded="open.has(keyOf(row)) ? 'true' : 'false'"
                aria-label="펼치기"
                @click="toggle(keyOf(row))"
              >
                {{ open.has(keyOf(row)) ? '▾' : '▸' }}
              </button>
            </td>
            <td v-for="c in columns" :key="c.key" :class="cellClass(c)">
              <slot :name="`cell-${c.key}`" :row="row">{{ row[c.key] ?? '—' }}</slot>
            </td>
          </tr>
          <tr v-if="expandable && open.has(keyOf(row))" class="tbl__expanded">
            <td :colspan="span()"><slot name="expanded" :row="row" /></td>
          </tr>
        </template>
        </template>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.tbl-wrap {
  overflow-x: auto;
}
.tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
  color: var(--text-1);
}
/* 선을 덜 긋는다 — 헤더 아래 line.2 2px, 행 사이 line.1 1px, 세로선 없음 */
th {
  height: 32px;
  padding: 0 var(--space-3);
  background: var(--sunken);
  border-bottom: var(--border-thick) solid var(--line-2);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  letter-spacing: 0.06em;
  color: var(--text-2);
  white-space: nowrap;
}
td {
  height: 32px;
  padding: 0 var(--space-3);
  border-bottom: var(--border-thin) solid var(--line-1);
}
.tbl__cell--left {
  text-align: left;
}
.tbl__cell--right {
  text-align: right;
}
.tbl__cell--center {
  text-align: center;
}
.tbl__cell--sticky {
  position: sticky;
  left: 0;
  background: inherit;
}
.tbl__row {
  background: var(--surface);
}
.tbl__row:hover {
  background: var(--sunken);
}
.tbl__row--selected,
.tbl__row--selected:hover {
  background: var(--brand-tint);
}
.tbl__expanded > td {
  padding: var(--space-2) var(--space-3) var(--space-2) var(--space-6);
  background: var(--sunken);
}
.tbl__toggle-col {
  width: 32px;
  padding: 0;
  text-align: center;
}
.tbl__toggle {
  border: 0;
  background: none;
  color: var(--text-2);
  font: inherit;
  cursor: pointer;
}
.tbl__empty {
  height: auto;
}
</style>
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint && pnpm exec prettier --check .`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add web/src/components/ui
git commit -m "style(web): ui Table — 선 덜 긋기, 선택 행 brand.tint, 로딩 Skeleton 5행, 빈 상태, 펼침"
```

---

### Task 8: ui — Modal · Toast · Banner

**Files:**
- Create: `web/src/components/ui/Modal.vue`, `web/src/components/ui/Toast.vue`, `web/src/components/ui/ToastHost.vue`, `web/src/components/ui/toast.ts`, `web/src/components/ui/Banner.vue`
- Test: `web/src/components/ui/__tests__/overlay.spec.ts`

**Interfaces:**
- `Modal` props `open: boolean` · `title: string` · `size?: 'sm'|'md'|'lg'`(md) · `closeOnBackdrop?: boolean`(true). emit `close`. 슬롯 `default`(본문) · `footer`. `body` 로 Teleport.
- `Toast` props `tone?: 'neutral'|'danger'` · `message: string` · `action?: { label: string; onClick: () => void }`. emit `dismiss`. (`duration` 은 `toast.ts` 가 쓴다.)
- `toast.ts`: `showToast(t: { tone?: 'neutral'|'danger'; message: string; action?: {label; onClick}; duration?: number }): number` · `dismissToast(id: number): void` · `toasts: Readonly<Ref<ToastItem[]>>`. 기본 duration 5000, `danger` 는 0(자동 해제 없음). 최대 3개 — 넘으면 가장 오래된 것부터 밀어낸다.
- `ToastHost` — 앱 루트에 한 번 두는 우상단 스택(Task 10·12 가 `StudentApp`·`AdminApp` 에 넣는다).
- `Banner` props `tone?: 'neutral'|'danger'` · `message: string` · `dismissible?: boolean`(true) · `storageKey?: string`. emit `dismiss`. 기본 슬롯 = 문구 뒤 링크 등. `storageKey` 가 있으면 닫은 사실을 `localStorage` 에 남긴다(접근이 막힌 브라우저에서도 죽지 않게 try/catch).

- [ ] **Step 1: 실패 테스트**

`web/src/components/ui/__tests__/overlay.spec.ts`
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import Modal from '@/components/ui/Modal.vue'
import Banner from '@/components/ui/Banner.vue'
import { dismissToast, showToast, toasts } from '@/components/ui/toast'

const stubs = { teleport: true }

describe('Modal', () => {
  it('닫혀 있으면 그리지 않는다', () => {
    const w = mount(Modal, { props: { open: false, title: '거절' }, global: { stubs } })
    expect(w.find('[role="dialog"]').exists()).toBe(false)
  })

  it('제목·본문·푸터, aria 연결', () => {
    const w = mount(Modal, {
      props: { open: true, title: '거절 사유' },
      slots: { default: '<p>본문</p>', footer: '<button>취소</button>' },
      global: { stubs },
    })
    const dlg = w.get('[role="dialog"]')
    expect(dlg.attributes('aria-modal')).toBe('true')
    expect(w.get(`#${dlg.attributes('aria-labelledby')}`).text()).toBe('거절 사유')
    expect(w.text()).toContain('본문')
  })

  it('Esc 로 닫힌다', async () => {
    const w = mount(Modal, { props: { open: true, title: 't' }, global: { stubs } })
    await w.get('[role="dialog"]').trigger('keydown', { key: 'Escape' })
    expect(w.emitted('close')).toHaveLength(1)
  })

  it('배경 클릭 — closeOnBackdrop 이 false 면 닫지 않는다', async () => {
    const a = mount(Modal, { props: { open: true, title: 't' }, global: { stubs } })
    await a.get('.modal__backdrop').trigger('mousedown')
    expect(a.emitted('close')).toHaveLength(1)
    const b = mount(Modal, {
      props: { open: true, title: 't', closeOnBackdrop: false },
      global: { stubs },
    })
    await b.get('.modal__backdrop').trigger('mousedown')
    expect(b.emitted('close')).toBeUndefined()
  })

  it('열리면 첫 입력에 포커스, 닫히면 열었던 버튼으로', async () => {
    const opener = document.createElement('button')
    document.body.appendChild(opener)
    opener.focus()
    const w = mount(Modal, {
      props: { open: false, title: 't' },
      slots: { default: '<input id="first" />', footer: '<button>확인</button>' },
      global: { stubs },
      attachTo: document.body,
    })
    await w.setProps({ open: true })
    await new Promise((r) => setTimeout(r))
    expect(document.activeElement?.id).toBe('first')
    await w.setProps({ open: false })
    await new Promise((r) => setTimeout(r))
    expect(document.activeElement).toBe(opener)
    w.unmount()
    opener.remove()
  })

  it('Tab 은 패널 안에서 돈다', async () => {
    const w = mount(Modal, {
      props: { open: true, title: 't' },
      slots: { default: '<input id="a" />', footer: '<button id="z">확인</button>' },
      global: { stubs },
      attachTo: document.body,
    })
    await new Promise((r) => setTimeout(r))
    ;(document.getElementById('z') as HTMLElement).focus()
    await w.get('[role="dialog"]').trigger('keydown', { key: 'Tab' })
    expect(document.activeElement?.id).toBe('a')
    w.unmount()
  })
})

describe('toast', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    for (const t of [...toasts.value]) dismissToast(t.id)
  })
  afterEach(() => vi.useRealTimers())

  it('최대 3개 — 넘으면 오래된 것부터', () => {
    for (const m of ['1', '2', '3', '4']) showToast({ message: m })
    expect(toasts.value.map((t) => t.message)).toEqual(['2', '3', '4'])
  })

  it('neutral 은 5초 뒤 사라지고 danger 는 남는다', async () => {
    showToast({ message: '저장했습니다' })
    showToast({ tone: 'danger', message: '실패했습니다' })
    await vi.advanceTimersByTimeAsync(5000)
    expect(toasts.value.map((t) => t.message)).toEqual(['실패했습니다'])
  })
})

describe('Banner', () => {
  beforeEach(() => localStorage.clear())

  it('닫으면 사라지고 storageKey 를 남긴다', async () => {
    const w = mount(Banner, { props: { message: '1024px 이상', storageKey: 'narrow' } })
    await w.get('button').trigger('click')
    expect(w.find('.banner').exists()).toBe(false)
    expect(localStorage.getItem('banner:narrow')).toBe('1')
    expect(w.emitted('dismiss')).toHaveLength(1)
  })

  it('이미 닫은 배너는 다시 띄우지 않는다', () => {
    localStorage.setItem('banner:narrow', '1')
    const w = mount(Banner, { props: { message: 'x', storageKey: 'narrow' } })
    expect(w.find('.banner').exists()).toBe(false)
  })

  it('localStorage 가 막혀도 죽지 않는다', async () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    const w = mount(Banner, { props: { message: 'x', storageKey: 'k' } })
    expect(w.find('.banner').exists()).toBe(true)
    spy.mockRestore()
  })

  it('dismissible:false 면 닫기 버튼이 없다', () => {
    const w = mount(Banner, { props: { message: 'x', dismissible: false } })
    expect(w.find('button').exists()).toBe(false)
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/components/ui/__tests__/overlay.spec.ts`
Expected: FAIL — `Failed to resolve import "@/components/ui/Modal.vue"`

- [ ] **Step 3: 구현**

`web/src/components/ui/Modal.vue`
```vue
<script setup lang="ts">
import { nextTick, ref, useId, watch } from 'vue'

const props = withDefaults(
  defineProps<{ open: boolean; title: string; size?: 'sm' | 'md' | 'lg'; closeOnBackdrop?: boolean }>(),
  { size: 'md', closeOnBackdrop: true },
)
const emit = defineEmits<{ close: [] }>()
const titleId = useId()
const panel = ref<HTMLElement>()
let opener: HTMLElement | null = null

const FOCUSABLE =
  'input:not([disabled]),select:not([disabled]),textarea:not([disabled]),button:not([disabled]),a[href],[tabindex]:not([tabindex="-1"])'
const focusables = () => [...(panel.value?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])]

watch(
  () => props.open,
  async (open) => {
    if (open) {
      opener = document.activeElement as HTMLElement | null
      await nextTick()
      // 첫 입력 → 없으면 첫 포커스 대상 (components.md)
      const first =
        panel.value?.querySelector<HTMLElement>('input,select,textarea') ?? focusables()[0]
      ;(first ?? panel.value)?.focus()
    } else {
      await nextTick()
      opener?.focus()
      opener = null
    }
  },
  { immediate: true },
)

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.stopPropagation()
    emit('close')
  } else if (e.key === 'Tab') {
    const f = focusables()
    if (!f.length) return
    const i = f.indexOf(document.activeElement as HTMLElement)
    const next = e.shiftKey ? (i <= 0 ? f.length - 1 : i - 1) : i === f.length - 1 ? 0 : i + 1
    e.preventDefault()
    f[next].focus()
  }
}
function onBackdrop() {
  if (props.closeOnBackdrop) emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="modal">
      <div class="modal__backdrop" @mousedown.self="onBackdrop" />
      <div
        ref="panel"
        class="modal__panel"
        :class="`modal__panel--${size}`"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        tabindex="-1"
        @keydown="onKeydown"
      >
        <h2 :id="titleId" class="modal__title">{{ title }}</h2>
        <div class="modal__body"><slot /></div>
        <div v-if="$slots.footer" class="modal__footer"><slot name="footer" /></div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: grid;
  place-items: center;
  padding: var(--space-4);
}
.modal__backdrop {
  position: absolute;
  inset: 0;
  background: var(--modal-backdrop); /* 블러 없음 */
}
.modal__panel {
  position: relative;
  width: 100%;
  max-height: calc(100vh - var(--space-6));
  overflow: auto;
  padding: var(--space-5);
  border-radius: var(--radius-lg);
  background: var(--surface); /* 그림자 없음 — 배경 딤이 층을 진다 */
}
.modal__panel--sm {
  max-width: 400px;
}
.modal__panel--md {
  max-width: 560px;
}
.modal__panel--lg {
  max-width: 800px;
}
.modal__title {
  margin: 0 0 var(--space-4);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  line-height: var(--leading-tight);
}
.modal__footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  margin-top: var(--space-5);
}
</style>
```
`@mousedown.self` 는 배경 요소 자신에서 시작한 누름만 받는다 — 패널 안에서 텍스트를 드래그하다 배경에서 떼도 닫히지 않는다. 테스트는 `.modal__backdrop` 에 직접 `mousedown` 을 보낸다.

`web/src/components/ui/toast.ts`
```ts
import { readonly, ref } from 'vue'

export type ToastTone = 'neutral' | 'danger'
export interface ToastAction {
  label: string
  onClick: () => void
}
export interface ToastItem {
  id: number
  tone: ToastTone
  message: string
  action?: ToastAction
}

const MAX = 3
const items = ref<ToastItem[]>([])
export const toasts = readonly(items)
let seq = 0

export function dismissToast(id: number): void {
  items.value = items.value.filter((t) => t.id !== id)
}

/** danger 는 자동으로 사라지지 않는다 — 에러를 놓치면 안 된다 (components.md) */
export function showToast(t: {
  tone?: ToastTone
  message: string
  action?: ToastAction
  duration?: number
}): number {
  const id = ++seq
  const tone = t.tone ?? 'neutral'
  items.value = [...items.value, { id, tone, message: t.message, action: t.action }].slice(-MAX)
  const duration = t.duration ?? (tone === 'danger' ? 0 : 5000)
  if (duration > 0) setTimeout(() => dismissToast(id), duration)
  return id
}
```
`web/src/components/ui/Toast.vue`
```vue
<script setup lang="ts">
import Button from './Button.vue'
import type { ToastAction } from './toast'

withDefaults(defineProps<{ tone?: 'neutral' | 'danger'; message: string; action?: ToastAction }>(), {
  tone: 'neutral',
})
const emit = defineEmits<{ dismiss: [] }>()
</script>

<template>
  <div class="toast" :class="`toast--${tone}`" :role="tone === 'danger' ? 'alert' : 'status'">
    <p class="toast__msg">{{ message }}</p>
    <Button
      v-if="action"
      variant="ghost"
      size="sm"
      @click="
        () => {
          action!.onClick()
          emit('dismiss')
        }
      "
      >{{ action.label }}</Button
    >
    <button type="button" class="toast__close" aria-label="닫기" @click="emit('dismiss')">×</button>
  </div>
</template>

<style scoped>
.toast {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 360px;
  max-width: calc(100vw - var(--space-6));
  padding: var(--space-3) var(--space-3) var(--space-3) var(--space-4);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-md);
  background: var(--surface);
  color: var(--text-1);
}
/* 성공에는 색을 쓰지 않는다 — danger 만 왼쪽 3px 띠 */
.toast--danger {
  box-shadow: inset 3px 0 0 var(--danger);
}
.toast__msg {
  flex: 1;
  margin: 0;
}
.toast__close {
  border: 0;
  background: none;
  color: var(--text-2);
  font: inherit;
  font-size: var(--font-size-lg);
  cursor: pointer;
}
</style>
```
(`box-shadow: inset` 는 그림자 토큰이 아니라 띠를 그리는 수단이다 — 테두리 두께를 바꾸면 글자 위치가 흔들린다.)

`web/src/components/ui/ToastHost.vue`
```vue
<script setup lang="ts">
import Toast from './Toast.vue'
import { dismissToast, toasts } from './toast'
</script>

<template>
  <div class="toast-host" aria-live="polite">
    <Toast
      v-for="t in toasts"
      :key="t.id"
      :tone="t.tone"
      :message="t.message"
      :action="t.action"
      @dismiss="dismissToast(t.id)"
    />
  </div>
</template>

<style scoped>
.toast-host {
  position: fixed;
  top: var(--space-4);
  right: var(--space-4);
  z-index: 200;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
</style>
```

`web/src/components/ui/Banner.vue`
```vue
<script setup lang="ts">
import { ref } from 'vue'

const props = withDefaults(
  defineProps<{
    tone?: 'neutral' | 'danger'
    message: string
    dismissible?: boolean
    storageKey?: string
  }>(),
  { tone: 'neutral', dismissible: true },
)
const emit = defineEmits<{ dismiss: [] }>()
const key = props.storageKey ? `banner:${props.storageKey}` : null

function wasDismissed(): boolean {
  if (!key) return false
  try {
    return localStorage.getItem(key) === '1'
  } catch {
    return false // 사생활 보호 모드 등 — 기억 못 해도 배너는 보인다
  }
}
const hidden = ref(wasDismissed())

function dismiss() {
  hidden.value = true
  if (key) {
    try {
      localStorage.setItem(key, '1')
    } catch {
      /* 기억 못 해도 지금은 닫는다 */
    }
  }
  emit('dismiss')
}
</script>

<template>
  <div
    v-if="!hidden"
    class="banner"
    :class="`banner--${tone}`"
    :role="tone === 'danger' ? 'alert' : 'status'"
  >
    <p class="banner__msg">{{ message }} <slot /></p>
    <button v-if="dismissible" type="button" class="banner__close" aria-label="닫기" @click="dismiss">
      ×
    </button>
  </div>
</template>

<style scoped>
.banner {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--sunken);
  border-bottom: var(--border-thin) solid var(--line-2);
  color: var(--text-1);
}
.banner--danger .banner__msg {
  color: var(--danger);
}
.banner__msg {
  flex: 1;
  margin: 0;
}
.banner__close {
  border: 0;
  background: none;
  color: var(--text-2);
  font: inherit;
  font-size: var(--font-size-lg);
  cursor: pointer;
}
</style>
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint && pnpm exec prettier --check .`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add web/src/components/ui
git commit -m "style(web): ui Modal(포커스 가둠·Esc·배경 클릭 옵션)·Toast(최대 3, danger 유지)·Banner(닫힘 기억)"
```

---

### Task 9: ui — SidebarNav · StatTile · Legend

**Files:**
- Create: `web/src/components/ui/SidebarNav.vue`, `web/src/components/ui/StatTile.vue`, `web/src/components/ui/Legend.vue`
- Test: `web/src/components/ui/__tests__/nav.spec.ts`

**Interfaces:**
- `SidebarNav` props `items: { to: string; label: string; badge?: number }[]`. 슬롯 `footer`. 활성 항목은 `RouterLink` 의 활성 클래스로(`aria-current="page"` 자동).
- `StatTile` props `label: string` · `value: string|number` · `unit?` · `sub?` · `tone?: 'neutral'|'danger'`(neutral)
- `Legend` props `series: { label: string; color: string }[]` — `color` 는 `'var(--chart-series-1)'` 같은 토큰 참조. **계열이 1개 이하면 아무것도 그리지 않는다**(tokens.md chart 규칙 6).

Ruling: `SidebarNav` 항목의 `badge` 는 `components.md` props 표에 없지만 `admin-users.md` 가 "사이드 메뉴 `회원` 옆에 대기 건수 배지"를 요구한다. 선택 필드로 두고 `Badge neutral+solid` 로 그린다. 0 이면 그리지 않는다. PR 에서 mh 에 `components.md` 반영을 요청한다. F1 에서 `StatTile`·`Legend` 를 쓰는 화면은 없다(F3 대시보드) — spec §6 이 F1 범위로 정해 여기서 만든다.

- [ ] **Step 1: 실패 테스트**

`web/src/components/ui/__tests__/nav.spec.ts`
```ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import SidebarNav from '@/components/ui/SidebarNav.vue'
import StatTile from '@/components/ui/StatTile.vue'
import Legend from '@/components/ui/Legend.vue'

const Empty = { template: '<div />' }
async function withRouter(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/users', component: Empty },
      { path: '/nodes', component: Empty },
    ],
  })
  await router.push(path)
  await router.isReady()
  return router
}

describe('SidebarNav', () => {
  it('현재 경로 항목이 활성, badge 는 0 이면 숨김', async () => {
    const router = await withRouter('/users')
    const w = mount(SidebarNav, {
      props: {
        items: [
          { to: '/nodes', label: '노드 상태', badge: 0 },
          { to: '/users', label: '회원', badge: 5 },
        ],
      },
      slots: { footer: '<p class="f">우송대</p>' },
      global: { plugins: [router] },
    })
    const links = w.findAll('a')
    expect(links[1].attributes('aria-current')).toBe('page')
    expect(links[0].attributes('aria-current')).toBeUndefined()
    expect(links[1].text()).toContain('5')
    expect(links[0].find('.badge').exists()).toBe(false)
    expect(w.find('.f').exists()).toBe(true)
  })
})

describe('StatTile', () => {
  it('danger 는 값 글자만', () => {
    const w = mount(StatTile, {
      props: { label: '수신률', value: 91.2, unit: '%', sub: '목표 95% · 미달', tone: 'danger' },
    })
    expect(w.text()).toContain('91.2')
    expect(w.get('.stat__value').classes()).toContain('stat__value--danger')
    expect(w.classes()).not.toContain('stat--danger')
  })
})

describe('Legend', () => {
  it('2개 이상일 때만 그린다', () => {
    const one = mount(Legend, { props: { series: [{ label: 'A', color: 'var(--chart-series-1)' }] } })
    expect(one.find('.legend').exists()).toBe(false)
    const two = mount(Legend, {
      props: {
        series: [
          { label: '이번 주', color: 'var(--chart-series-1)' },
          { label: '지난주', color: 'var(--chart-series-2)' },
        ],
      },
    })
    expect(two.findAll('.legend__item').map((x) => x.text())).toEqual(['이번 주', '지난주'])
    expect(two.get('.legend__mark').attributes('style')).toContain('var(--chart-series-1)')
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/components/ui/__tests__/nav.spec.ts`
Expected: FAIL — `Failed to resolve import "@/components/ui/SidebarNav.vue"`

- [ ] **Step 3: 구현**

`web/src/components/ui/SidebarNav.vue`
```vue
<script setup lang="ts">
import { RouterLink } from 'vue-router'
import Badge from './Badge.vue'

defineProps<{ items: { to: string; label: string; badge?: number }[] }>()
</script>

<template>
  <nav class="nav">
    <ul class="nav__list">
      <li v-for="i in items" :key="i.to">
        <RouterLink :to="i.to" class="nav__item" active-class="nav__item--active">
          <span>{{ i.label }}</span>
          <Badge v-if="i.badge" variant="solid" class="num">{{ i.badge }}</Badge>
        </RouterLink>
      </li>
    </ul>
    <div v-if="$slots.footer" class="nav__footer"><slot name="footer" /></div>
  </nav>
</template>

<style scoped>
.nav {
  display: flex;
  flex-direction: column;
  width: 220px;
  min-height: 100vh;
  padding: var(--space-3) var(--space-2);
  background: var(--sunken);
  border-right: var(--border-thin) solid var(--line-2);
}
.nav__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.nav__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 32px;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  font-size: var(--font-size-md);
  color: var(--text-2);
  text-decoration: none;
}
.nav__item:hover {
  background: var(--nav-hover);
}
.nav__item--active,
.nav__item--active:hover {
  background: var(--brand-tint);
  color: var(--brand);
  font-weight: var(--font-weight-medium);
}
.nav__footer {
  margin-top: auto;
  padding: var(--space-3);
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
</style>
```

`web/src/components/ui/StatTile.vue`
```vue
<script setup lang="ts">
withDefaults(
  defineProps<{
    label: string
    value: string | number
    unit?: string
    sub?: string
    tone?: 'neutral' | 'danger'
  }>(),
  { tone: 'neutral' },
)
</script>

<template>
  <div class="stat">
    <p class="stat__label">{{ label }}</p>
    <p class="stat__value num" :class="{ 'stat__value--danger': tone === 'danger' }">
      {{ value }}<span v-if="unit" class="stat__unit">{{ unit }}</span>
    </p>
    <p v-if="sub" class="stat__sub">{{ sub }}</p>
  </div>
</template>

<style scoped>
.stat {
  padding: var(--space-4);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-md);
}
.stat p {
  margin: 0;
}
.stat__label {
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
.stat__value {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  line-height: var(--leading-tight);
}
.stat__value--danger {
  color: var(--danger);
}
.stat__unit {
  margin-left: 2px;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--text-2);
}
.stat__sub {
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
</style>
```

`web/src/components/ui/Legend.vue`
```vue
<script setup lang="ts">
defineProps<{ series: { label: string; color: string }[] }>()
</script>

<template>
  <!-- 계열 1개면 제목이 이름을 진다 — 범례 없음 -->
  <ul v-if="series.length >= 2" class="legend">
    <li v-for="s in series" :key="s.label" class="legend__item">
      <span class="legend__mark" :style="{ background: s.color }" aria-hidden="true" />{{ s.label }}
    </li>
  </ul>
</template>

<style scoped>
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin: 0;
  padding: 0;
  list-style: none;
}
.legend__item {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--font-size-xs);
  color: var(--text-2); /* 글자는 계열색을 입지 않는다 */
}
.legend__mark {
  width: 9px;
  height: 9px;
  border-radius: var(--radius-sm);
}
</style>
```

- [ ] **Step 4: 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint && pnpm exec prettier --check .`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add web/src/components/ui
git commit -m "style(web): ui SidebarNav(활성 brand.tint·대기 건수 배지)·StatTile·Legend"
```

---

### Task 10: Playwright 하네스 + 로그인(두 앱) · 가드 · 401/403 연결

**Files:**
- Create: `web/src/auth/next.ts`, `web/src/auth/guard.ts`, `web/src/auth/AuthShell.vue`, `web/src/auth/LoginView.vue`, `web/playwright.config.ts`, `web/e2e/env.json`, `web/e2e/start-server.mjs`, `web/e2e/helpers.ts`, `web/e2e/login.spec.ts`
- Modify: `web/src/admin/router.ts`, `web/src/student/router.ts`, `web/src/admin/AdminApp.vue`, `web/src/student/StudentApp.vue`, `web/src/student/views/HomeView.vue`, `web/env.d.ts`, `web/package.json`, `web/.gitignore`
- Test: `web/src/auth/__tests__/login.spec.ts`

**Interfaces:**
- Consumes: `authApi.login`, `ApiError`, `MESSAGES` (Task 3) · `session`, `setSession`, `clearSession`, `authNotice`, `onAuthFailure` (Task 3) · `useCooldown` (Task 4) · `Button`, `Input`, `Banner`, `EmptyState`, `ToastHost` (Task 5·6·8)
- Produces:
  - `safeNext(v: unknown, fallback: string): string` — `/` 로 시작하고 `//`·`/\` 로 시작하지 않는 경로만 통과
  - `installAuth(router: Router): void` — `meta.auth` 라우트에 세션이 없으면 `/login?next=<fullPath>`, 401·403 이면 `/login?next=` 로 보낸다
  - `AuthShell` props `title: string` · `surface: 'student'|'admin'` · `back?: string`. 슬롯 `banner` · `default` · `footer`. 슬롯 안의 `<form class="auth-form">`·`.auth-form__error`·`.auth-form__note` 에 공통 간격·문구 스타일을 준다
  - `LoginView` props `app: 'admin'|'student'`
  - E2E: `e2e/helpers.ts` → `ADMIN`, `uniqEmail(prefix)`, `mailToken(to)`, `cli(args, input?)`, `apiLogin(request, email, pw)`, `createStudent(request, opts)`, `shot(page, name)`, `SIZES`
  - `RouteMeta.auth?: boolean`

로그인 뒤 기본 화면: 두 앱 모두 `/`. 관리자 `/` 는 Task 12 에서 `/users` 로 넘긴다.

- [ ] **Step 1: 실패 테스트 — next · 가드 · LoginView**

`web/src/auth/__tests__/login.spec.ts`
```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { safeNext } from '@/auth/next'
import { installAuth } from '@/auth/guard'
import LoginView from '@/auth/LoginView.vue'
import { ApiError, MESSAGES } from '@/api/client'
import { authNotice, clearSession, session, setSession } from '@/lib/session'
import { authApi } from '@/api/auth'

vi.mock('@/api/auth', () => ({ authApi: { login: vi.fn() } }))
const login = vi.mocked(authApi.login)
const Empty = { template: '<div />' }

function makeRouter(): Router {
  const r = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: Empty, meta: { auth: true } },
      { path: '/users', component: Empty, meta: { auth: true } },
      { path: '/login', component: Empty },
      { path: '/signup', component: Empty },
      { path: '/forgot', component: Empty },
    ],
  })
  installAuth(r)
  return r
}
async function mountLogin(app: 'admin' | 'student', path = '/login') {
  const router = makeRouter()
  await router.push(path)
  await router.isReady()
  const w = mount(LoginView, { props: { app }, global: { plugins: [router] } })
  return { w, router }
}
async function submit(w: ReturnType<typeof mount>, email = 'a@wsu.ac.kr', pw = 'password1') {
  const [e, p] = w.findAll('input')
  await e.setValue(email)
  await p.setValue(pw)
  await w.get('form').trigger('submit')
  await flushPromises()
}
const out = (role: 'admin' | 'student') => ({ token: 't', role, school_id: 1, name: '김민준' })

beforeEach(() => {
  login.mockReset()
  clearSession()
  authNotice.value = null
})

describe('safeNext (Review Focus 1)', () => {
  it.each([
    ['/users?status=active', '/users?status=active'],
    ['//evil.com', '/'],
    ['/\\evil.com', '/'],
    ['https://evil.com', '/'],
    [undefined, '/'],
    [['/a'], '/'],
  ])('%s → %s', (v, want) => expect(safeNext(v, '/')).toBe(want))
})

describe('installAuth', () => {
  it('세션 없이 auth 라우트 → /login?next=', async () => {
    const r = makeRouter()
    await r.push('/users?x=1')
    expect(r.currentRoute.value.path).toBe('/login')
    expect(r.currentRoute.value.query.next).toBe('/users?x=1')
  })

  it('401 알림이 오면 지금 화면을 next 로 로그인에 보낸다', async () => {
    const r = makeRouter()
    setSession(out('admin'))
    await r.push('/users')
    clearSession('expired')
    await flushPromises()
    expect(r.currentRoute.value.path).toBe('/login')
    expect(r.currentRoute.value.query.next).toBe('/users')
  })
})

describe('LoginView', () => {
  it('성공 → 세션 저장 + next 로', async () => {
    login.mockResolvedValue(out('admin'))
    const { w, router } = await mountLogin('admin', '/login?next=/users')
    await submit(w)
    expect(session.value?.role).toBe('admin')
    expect(router.currentRoute.value.path).toBe('/users')
  })

  it('역할이 앱과 다르면 토큰을 버리고 폼에 머문다', async () => {
    login.mockResolvedValue(out('student'))
    const { w, router } = await mountLogin('admin')
    await submit(w)
    expect(session.value).toBeNull()
    expect(router.currentRoute.value.path).toBe('/login')
    expect(w.text()).toContain('관리자 계정이 아닙니다. 학생은 학생 웹에서 로그인하세요.')
  })

  it('학생 앱에 관리자 계정', async () => {
    login.mockResolvedValue(out('admin'))
    const { w } = await mountLogin('student')
    await submit(w)
    expect(w.text()).toContain('관리자 계정입니다. 관리자 웹에서 로그인하세요.')
  })

  it('401 → 어느 쪽이 틀렸는지 말하지 않는다', async () => {
    login.mockRejectedValue(new ApiError(401, MESSAGES[401]))
    const { w } = await mountLogin('student')
    await submit(w)
    expect(w.get('.auth-form__error').text()).toBe('이메일 또는 비밀번호가 틀립니다')
  })

  it('403 → 적색이 아닌 안내 Banner', async () => {
    login.mockRejectedValue(new ApiError(403, MESSAGES[403]))
    const { w } = await mountLogin('student')
    await submit(w)
    const b = w.get('.banner')
    expect(b.classes()).toContain('banner--neutral')
    expect(b.text()).toContain('아직 승인되지 않았어요. 관리자 승인 뒤 로그인할 수 있어요.')
    expect(w.find('.auth-form__error').exists()).toBe(false)
  })

  it('429 → 문구 + 버튼 10초 잠금 (Review Focus 5)', async () => {
    vi.useFakeTimers()
    login.mockRejectedValue(new ApiError(429, MESSAGES[429]))
    const { w } = await mountLogin('student')
    await submit(w)
    const btn = () => w.get('button[type="submit"]').element as HTMLButtonElement
    expect(w.text()).toContain('잠시 후 다시 시도해 주세요')
    expect(btn().disabled).toBe(true)
    await vi.advanceTimersByTimeAsync(10_000)
    expect(btn().disabled).toBe(false)
    vi.useRealTimers()
  })

  it('422 → 이메일 칸 에러', async () => {
    login.mockRejectedValue(new ApiError(422, MESSAGES[422], ['email']))
    const { w } = await mountLogin('student')
    await submit(w, 'a,b@x')
    expect(w.text()).toContain('메일 주소 형식이 올바르지 않습니다')
  })

  it('401 로 쫓겨 왔으면 "다시 로그인해 주세요." Banner', async () => {
    authNotice.value = 'expired'
    const { w } = await mountLogin('admin')
    expect(w.get('.banner').text()).toContain('다시 로그인해 주세요.')
  })

  it('제출 중 연타는 한 번만 보낸다', async () => {
    let finish!: (v: ReturnType<typeof out>) => void
    login.mockReturnValue(new Promise((r) => (finish = r)))
    const { w } = await mountLogin('student')
    const [e, p] = w.findAll('input')
    await e.setValue('a@wsu.ac.kr')
    await p.setValue('password1')
    await w.get('form').trigger('submit')
    await w.get('form').trigger('submit')
    expect(login).toHaveBeenCalledTimes(1)
    finish(out('student'))
    await flushPromises()
  })

  it('관리자 앱에는 가입 링크가 없고 재설정은 학생 앱 /forgot 으로', async () => {
    const { w } = await mountLogin('admin')
    expect(w.text()).not.toContain('가입 신청')
    expect(w.get('a[href="/forgot"]').text()).toBe('비밀번호를 잊었어요')
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/auth`
Expected: FAIL — `Failed to resolve import "@/auth/next"`

- [ ] **Step 3: 구현 — next · guard · 라우터 · 셸**

`web/env.d.ts` 끝에:
```ts
import 'vue-router'
declare module 'vue-router' {
  interface RouteMeta {
    auth?: boolean
  }
}
```

`web/src/auth/next.ts`
```ts
/** 로그인 뒤 돌아갈 경로 — 앱 안의 경로만. `//evil.com`·`/\evil.com` 은 브라우저가 외부 주소로 읽는다 */
export function safeNext(v: unknown, fallback: string): string {
  if (typeof v !== 'string' || !v.startsWith('/') || v.startsWith('//') || v.startsWith('/\\'))
    return fallback
  return v
}
```
`web/src/auth/guard.ts`
```ts
import type { Router } from 'vue-router'
import { onAuthFailure, session } from '@/lib/session'

/** 인증 라우트 가드 + 401/403 이면 로그인으로 (spec §4.2). 두 앱 라우터가 똑같이 부른다 */
export function installAuth(router: Router): void {
  router.beforeEach((to) =>
    to.meta.auth && !session.value ? { path: '/login', query: { next: to.fullPath } } : true,
  )
  onAuthFailure(() => {
    const cur = router.currentRoute.value
    if (cur.path !== '/login') void router.push({ path: '/login', query: { next: cur.fullPath } })
  })
}
```
`web/src/student/router.ts`
```ts
import { createRouter, createWebHistory, type RouteRecordRaw, type RouterHistory } from 'vue-router'
import { installAuth } from '@/auth/guard'

export const routes: RouteRecordRaw[] = [
  { path: '/', component: () => import('./views/HomeView.vue'), meta: { auth: true } },
  { path: '/login', component: () => import('@/auth/LoginView.vue'), props: { app: 'student' } },
]

export function makeRouter(history: RouterHistory = createWebHistory('/')) {
  const router = createRouter({ history, routes })
  installAuth(router)
  return router
}
```
`web/src/admin/router.ts` — 같은 모양. routes: `'/'` → `PlaceholderView`(`meta.auth`), `'/login'` → `LoginView`(`props: { app: 'admin' }`). 기본 history `createWebHistory('/admin/')`.

Task 1 의 라우터 테스트 두 개는 `/` 가 이제 `/login` 으로 넘어가므로 기대값을 바꾼다:
```ts
    expect(r.currentRoute.value.path).toBe('/login')
```

`web/src/student/StudentApp.vue`·`web/src/admin/AdminApp.vue`
```vue
<script setup lang="ts">
import { RouterView } from 'vue-router'
import ToastHost from '@/components/ui/ToastHost.vue'
</script>

<template>
  <RouterView />
  <ToastHost />
</template>
```

`web/src/auth/AuthShell.vue`
```vue
<script setup lang="ts">
import { RouterLink } from 'vue-router'

defineProps<{ title: string; surface: 'student' | 'admin'; back?: string }>()
</script>

<template>
  <!-- 로그인 전에는 사이드바를 그리지 않는다 — 빈 바탕에 폼 하나 (auth.md) -->
  <div class="auth" :class="`auth--${surface}`">
    <slot name="banner" />
    <main class="auth__card">
      <p class="auth__brand">우송 ESC</p>
      <h1 class="auth__title">
        <RouterLink v-if="back" :to="back" class="auth__back" aria-label="뒤로">‹</RouterLink
        >{{ title }}
      </h1>
      <slot />
      <div v-if="$slots.footer" class="auth__footer"><slot name="footer" /></div>
    </main>
  </div>
</template>

<style scoped>
.auth {
  min-height: 100vh;
}
.auth__card {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  width: 100%;
  max-width: 400px;
  margin: 0 auto;
  padding: var(--space-6) var(--space-4);
}
.auth--student .auth__card {
  background: var(--surface);
}
@media (min-width: 640px) {
  .auth--student .auth__card {
    margin-top: var(--space-7);
    border: var(--border-thin) solid var(--line-2);
    border-radius: var(--radius-lg);
  }
}
.auth--admin .auth__card {
  max-width: 360px;
  margin-top: 15vh;
}
.auth__brand {
  margin: 0;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
  color: var(--text-2);
}
.auth__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  line-height: var(--leading-tight);
}
.auth__back {
  display: inline-grid;
  place-items: center;
  min-width: var(--control-height-md);
  min-height: var(--control-height-md);
  margin-left: calc(-1 * var(--space-3));
  color: var(--text-1);
  text-decoration: none;
}
.auth__footer {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  justify-content: center;
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
.auth__footer :deep(a) {
  color: var(--text-2);
}
:slotted(.auth-form) {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
:slotted(.auth-form) button[type='submit'] {
  width: 100%;
}
:slotted(.auth-form__error) {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--danger);
}
:slotted(.auth-form__note) {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
</style>
```
(`:slotted(.auth-form) button[type='submit']` 는 `.auth-form[data-v-…-s] button[type='submit']` 로 컴파일된다 — 자손 버튼에는 스코프 속성이 필요 없어 `Button` 루트에 닿는다. Step 7 스크린샷에서 제출 버튼이 폼 전폭인지 본다.)

`web/src/auth/LoginView.vue`
```vue
<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AuthShell from './AuthShell.vue'
import Banner from '@/components/ui/Banner.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import { authApi } from '@/api/auth'
import { ApiError } from '@/api/client'
import { authNotice, setSession } from '@/lib/session'
import { useCooldown } from '@/lib/useCooldown'
import { safeNext } from './next'

const props = defineProps<{ app: 'admin' | 'student' }>()
const route = useRoute()
const router = useRouter()

const email = ref('')
const password = ref('')
const error = ref('')
const emailError = ref('')
const pending = ref(false)
const submitting = ref(false)
const notice = ref(authNotice.value) // 401·403 으로 쫓겨 온 이유 — 한 번 보이고 지운다
authNotice.value = null
const { active: locked, start: lock } = useCooldown()

// 비밀번호가 맞았을 때만 보이는 문구라 계정 존재를 새지 않는다 (auth.md 「역할 확인」)
const ROLE_MISMATCH = {
  admin: '관리자 계정이 아닙니다. 학생은 학생 웹에서 로그인하세요.',
  student: '관리자 계정입니다. 관리자 웹에서 로그인하세요.',
} as const

async function submit() {
  if (submitting.value || locked.value) return
  error.value = ''
  emailError.value = ''
  pending.value = false
  notice.value = null
  submitting.value = true
  try {
    const out = await authApi.login(email.value.trim(), password.value)
    if (out.role !== props.app) {
      error.value = ROLE_MISMATCH[props.app] // 토큰은 저장하지 않고 버린다
      return
    }
    setSession(out)
    await router.replace(safeNext(route.query.next, '/'))
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 401) error.value = '이메일 또는 비밀번호가 틀립니다'
    else if (e.status === 403) pending.value = true
    else if (e.status === 422) emailError.value = '메일 주소 형식이 올바르지 않습니다'
    else if (e.status === 429) {
      error.value = '잠시 후 다시 시도해 주세요'
      lock(10) // 서버가 남은 시간을 주지 않는다 (spec §4.1)
    } else error.value = e.message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthShell :title="app === 'admin' ? '관리자 로그인' : '로그인'" :surface="app">
    <template #banner>
      <Banner v-if="notice === 'expired'" message="다시 로그인해 주세요." :dismissible="false" />
      <Banner
        v-else-if="notice === 'forbidden'"
        tone="danger"
        message="이 화면을 쓸 권한이 없습니다."
        :dismissible="false"
      />
      <!-- 403 승인 대기는 적색이 아니다 — 학생이 뭘 잘못한 게 아니다 -->
      <Banner
        v-if="pending"
        message="아직 승인되지 않았어요. 관리자 승인 뒤 로그인할 수 있어요."
        :dismissible="false"
      />
    </template>
    <form class="auth-form" novalidate @submit.prevent="submit">
      <Input
        v-model="email"
        :label="app === 'admin' ? '이메일' : '학교 웹메일'"
        type="email"
        autocomplete="username"
        :error="emailError"
        required
      />
      <Input
        v-model="password"
        label="비밀번호"
        type="password"
        autocomplete="current-password"
        required
      />
      <p v-if="error" class="auth-form__error" role="alert">{{ error }}</p>
      <Button type="submit" :loading="submitting" :disabled="locked">로그인</Button>
    </form>
    <template #footer>
      <template v-if="app === 'student'">
        <RouterLink to="/signup">가입 신청</RouterLink>
        <span aria-hidden="true">·</span>
        <RouterLink to="/forgot">비밀번호를 잊었어요</RouterLink>
      </template>
      <!-- 관리자 재설정도 학생 앱 /forgot·/reset (#46 auth.md). ponytail: 같은 오리진 전제 — 배포에서 도메인을 나누면(#44 뒤) STUDENT_WEB_URL 로 -->
      <a v-else href="/forgot">비밀번호를 잊었어요</a>
    </template>
  </AuthShell>
</template>
```

`web/src/student/views/HomeView.vue` (F4 가 건물 목록으로 바꾼다)
```vue
<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import EmptyState from '@/components/ui/EmptyState.vue'
import { clearSession, session } from '@/lib/session'

const router = useRouter()
const message = computed(() => `${session.value?.name ?? ''}님, 강의실 화면은 준비 중입니다`)
function logout() {
  clearSession()
  void router.replace('/login')
}
</script>

<template>
  <main>
    <EmptyState
      :message="message"
      :actions="[{ label: '로그아웃', variant: 'secondary', onClick: logout }]"
    />
  </main>
</template>
```

- [ ] **Step 4: 단위 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`
Expected: PASS

- [ ] **Step 5: Playwright 설치 · 설정**

```bash
cd web
pnpm add -D @playwright/test@1.63.0
pnpm exec playwright install chromium
```
`web/package.json` scripts 에 `"e2e": "playwright test"`. `web/tsconfig.node.json` 의 `compilerOptions` 에 `"resolveJsonModule": true`(E2E 파일이 `env.json` 을 import 한다).
`web/.gitignore` 에 추가:
```
e2e/.tmp/
e2e/.shots/
test-results/
playwright-report/
```

`web/e2e/env.json` — 서버 기동 스크립트와 테스트 헬퍼가 같은 값을 쓴다
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
  "ADMINS": ["admin1@wsu.ac.kr", "admin2@wsu.ac.kr", "admin3@wsu.ac.kr", "admin4@wsu.ac.kr"]
}
```
관리자를 넷 두는 이유: 서버 로그인 상한이 **이메일당 분당 5회**라 한 계정으로 E2E 를 돌리면 429 로 막힌다. 헬퍼가 돌려 쓴다.

`web/e2e/start-server.mjs`
```js
// E2E 용 메인Pi 서버 — 매번 빈 DB, CLI 로 학교·관리자 시드, 메일은 콘솔(stdout → e2e/.tmp/server.log)
import { spawn, spawnSync } from 'node:child_process'
import { createWriteStream, mkdirSync, rmSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import cfg from './env.json' with { type: 'json' }

const web = fileURLToPath(new URL('..', import.meta.url))
const serverDir = path.resolve(web, '../server')
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
  cli(['create-admin', '--school-id', '1', '--email', email, '--name', `관리자${i + 1}`], `${cfg.ADMIN_PASSWORD}\n`),
)

const log = createWriteStream(path.join(tmp, 'server.log'))
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

`web/playwright.config.ts`
```ts
import { defineConfig, devices } from '@playwright/test'

// 서버는 매번 새 DB 로 띄운다(재사용 안 함). 서버 상태를 공유하므로 직렬 실행.
export default defineConfig({
  testDir: './e2e',
  workers: 1,
  fullyParallel: false,
  timeout: 30_000,
  use: { baseURL: 'http://127.0.0.1:5173', trace: 'retain-on-failure', locale: 'ko-KR' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: 'node e2e/start-server.mjs',
      url: 'http://127.0.0.1:8000/api/health',
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: 'pnpm dev --host 127.0.0.1 --port 5173 --strictPort',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: !process.env.CI,
    },
  ],
})
```
포트 8000 에 개발 서버가 떠 있으면 E2E 가 기동에 실패한다 — 끄고 돌린다(옛 DB 로 도는 서버에 붙지 않게 일부러 재사용하지 않는다).

`web/e2e/helpers.ts`
```ts
import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, type APIRequestContext, type Page } from '@playwright/test'
import cfg from './env.json' with { type: 'json' }

const web = fileURLToPath(new URL('..', import.meta.url))
const serverDir = path.resolve(web, '../server')
const logPath = path.join(web, 'e2e/.tmp/server.log')

export const SIZES = {
  admin: { width: 1440, height: 900 },
  student: { width: 390, height: 844 },
} as const
export const PASSWORD = cfg.ADMIN_PASSWORD

let rr = 0
/** 로그인 상한(이메일당 분당 5회)을 피하려고 관리자 계정을 돌려 쓴다 */
export const nextAdmin = () => cfg.ADMINS[rr++ % cfg.ADMINS.length]

export const uniqEmail = (prefix: string) =>
  `${prefix}${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}@${cfg.SCHOOL_DOMAIN}`

export async function shot(page: Page, name: string) {
  await page.screenshot({ path: path.join(web, 'e2e/.shots', `${name}.png`), fullPage: true })
}

/** 콘솔 메일 백엔드가 stdout 에 찍은 마지막 링크의 토큰 (메일은 응답 뒤 BackgroundTasks 로 나간다) */
export async function mailToken(to: string): Promise<string> {
  const re = new RegExp(`\\[mail\\] to=${to.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')} [^\\n]*\\n[^\\n]*?(?:\\n[^\\n]*?)*?#token=([A-Za-z0-9_-]+)`, 'g')
  let token: string | undefined
  await expect
    .poll(() => {
      const log = existsSync(logPath) ? readFileSync(logPath, 'utf8') : ''
      token = [...log.matchAll(re)].at(-1)?.[1]
      return token
    }, { timeout: 5_000 })
    .toBeTruthy()
  return token!
}

export function cli(args: string[], input?: string) {
  const r = spawnSync('uv', ['run', 'python', '-m', 'app.cli', ...args], {
    cwd: serverDir,
    env: {
      ...process.env,
      SERVER_DB: path.join(web, 'e2e/.tmp/e2e.db'),
      JWT_SECRET: cfg.JWT_SECRET,
      STUDENT_WEB_URL: cfg.STUDENT_WEB_URL,
      MAIL_BACKEND: cfg.MAIL_BACKEND,
      DEBUG: cfg.DEBUG,
      PYTHONIOENCODING: cfg.PYTHONIOENCODING,
    },
    input,
    encoding: 'utf8',
    shell: process.platform === 'win32',
  })
  expect(r.status, r.stderr).toBe(0)
}

export async function apiLogin(request: APIRequestContext, email: string, pw = PASSWORD) {
  const r = await request.post('/api/auth/login', { data: { email, password: pw } })
  expect(r.status()).toBe(200)
  return (await r.json()).token as string
}

/** 가입 신청 → 메일 토큰 → verify/open → verify (+ 승인). 화면을 거치지 않는 준비용 */
export async function createStudent(
  request: APIRequestContext,
  opts: { email?: string; name?: string; studentNo?: string; approve?: boolean } = {},
) {
  const email = opts.email ?? uniqEmail('s')
  const studentNo = opts.studentNo ?? `S${Date.now().toString(36)}`
  expect((await request.post('/api/auth/signup', { data: { email } })).status()).toBe(202)
  const token = await mailToken(email)
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
```
`mailToken` 정규식: `[mail] to=<주소> subject=…` 줄 다음 몇 줄 안의 첫 `#token=` 을 잡는다(메일 본문 형식은 `server/app/auth/mailer.py`). 여러 번 받았으면 마지막 것.

- [ ] **Step 6: E2E — 로그인**

`web/e2e/login.spec.ts`
```ts
import { expect, test } from '@playwright/test'
import { SIZES, createStudent, fillLogin, nextAdmin, shot, uniqEmail } from './helpers'

test('관리자 — 가드가 로그인으로 보내고, 로그인하면 돌아온다', async ({ page }) => {
  await page.setViewportSize(SIZES.admin)
  await page.goto('/admin/')
  await expect(page).toHaveURL(/\/admin\/login\?next=/)
  await expect(page.getByRole('link', { name: '가입 신청' })).toHaveCount(0)
  await shot(page, 'admin-login-1440')
  await fillLogin(page, nextAdmin())
  await expect(page).toHaveURL(/\/admin\/$/)
})

test('학생 로그인 화면 390', async ({ page }) => {
  await page.setViewportSize(SIZES.student)
  await page.goto('/login')
  await expect(page.getByRole('heading', { name: '로그인' })).toBeVisible()
  // 터치 타깃 48px (tokens.md)
  const box = await page.getByRole('button', { name: '로그인' }).boundingBox()
  expect(box!.height).toBeGreaterThanOrEqual(48)
  await shot(page, 'student-login-390')
})

test('역할이 다른 앱에 로그인하면 토큰을 버리고 안내한다', async ({ page, request }) => {
  const s = await createStudent(request, { approve: true })
  await page.goto('/admin/login')
  await fillLogin(page, s.email)
  await expect(page.getByText('관리자 계정이 아닙니다. 학생은 학생 웹에서 로그인하세요.')).toBeVisible()
  await expect(page).toHaveURL(/\/admin\/login/)

  await page.goto('/login')
  await fillLogin(page, nextAdmin())
  await expect(page.getByText('관리자 계정입니다. 관리자 웹에서 로그인하세요.')).toBeVisible()
})

test('429 뒤 10초 잠금이 풀린다 (Review Focus 5)', async ({ page }) => {
  test.setTimeout(45_000)
  const email = uniqEmail('nobody')
  await page.goto('/login')
  for (let i = 0; i < 5; i++) {
    await fillLogin(page, email, 'wrongpass1')
    await expect(page.getByText('이메일 또는 비밀번호가 틀립니다')).toBeVisible()
  }
  await fillLogin(page, email, 'wrongpass1')
  await expect(page.getByText('잠시 후 다시 시도해 주세요')).toBeVisible()
  const btn = page.getByRole('button', { name: '로그인' })
  await expect(btn).toBeDisabled()
  await expect(btn).toBeEnabled({ timeout: 12_000 })
})

test('next 가 외부 주소면 기본 화면으로 (Review Focus 1)', async ({ page, request }) => {
  const s = await createStudent(request, { approve: true })
  await page.goto('/login?next=//evil.example')
  await fillLogin(page, s.email)
  await expect(page).toHaveURL('http://127.0.0.1:5173/')
  await expect(page.getByText('강의실 화면은 준비 중입니다')).toBeVisible()
})
```

- [ ] **Step 7: E2E 실행 + 스크린샷 대조**

Run: `cd web && pnpm e2e e2e/login.spec.ts`
Expected: 5 passed. `e2e/.shots/admin-login-1440.png`·`student-login-390.png` 를 열어 `auth.md` 와 대조한다:
- 관리자: 사이드바 없음, 빈 바탕 가운데 폼 하나, 가입 링크 없음, 입력 높이 32px.
- 학생: 페이지 바탕 `gray.25` 위 흰 카드, 입력·버튼 48px, 제출 버튼 폼 전폭, 링크 `가입 신청 · 비밀번호를 잊었어요`.
- 두 화면 모두 Pretendard 로 그려졌는지(시스템 글꼴 대체가 아닌지).
어긋나면 고치고 다시 찍는다.

- [ ] **Step 8: 커밋**

```bash
git add -A web
git commit -m "feat(web): 로그인(두 앱·역할 확인·403 안내·429 잠금), 인증 가드와 401/403 연결, Playwright 하네스(임시 DB 서버·메일 토큰)"
```

---

### Task 11: 가입 · verify · forgot · reset (학생 앱)

**Files:**
- Create: `web/src/auth/fragment.ts`, `web/src/auth/StepList.vue`, `web/src/auth/SignupView.vue`, `web/src/auth/VerifyView.vue`, `web/src/auth/ForgotView.vue`, `web/src/auth/ResetView.vue`, `web/e2e/auth.spec.ts`
- Modify: `web/src/student/router.ts`
- Test: `web/src/auth/__tests__/signup.spec.ts`

**Interfaces:**
- Consumes: `authApi.{signup, verifyOpen, verify, forgot, reset}` (Task 3) · `AuthShell` (Task 10) · `useCooldown` (Task 4) · `Input`, `Button`, `Banner`
- Produces: `readFragmentToken(): string | null` — `#token=<urlsafe>` 를 읽고 **읽자마자** 주소에서 지운다(`history.replaceState`, 라우터 state 유지). `StepList` props `steps: string[]` · `current: number`(0부터).
- 학생 라우트 추가: `/signup`·`/verify`·`/forgot`·`/reset` (가드 없음)

문구는 `auth.md`(#46 판) 그대로. 서버 사실: signup 은 형식 오류 422, 학교 도메인 아님 400, 그 외 **항상 202**(이미 가입이어도). forgot 은 422 외 항상 202. verify 409 는 토큰을 쓰지 않는다. verify·reset 의 400 은 이유를 가리지 않는다.

Ruling: 가입 429 는 "이메일당 분당 5회"와 "학교 도메인 시간당 60"이 같은 429·같은 본문이라 화면이 둘을 가를 수 없다. `auth.md` 는 도메인 상한에 다른 문구(`지금 가입 신청이 몰리고 있어요…`)를 적었지만 구분할 근거가 없으므로 둘 다 `잠시 후 다시 시도해 주세요` + 10초 잠금으로 한다. PR 에서 mh 에 알린다.

- [ ] **Step 1: 실패 테스트**

`web/src/auth/__tests__/signup.spec.ts`
```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { readFragmentToken } from '@/auth/fragment'
import SignupView from '@/auth/SignupView.vue'
import VerifyView from '@/auth/VerifyView.vue'
import ResetView from '@/auth/ResetView.vue'
import { ApiError, MESSAGES } from '@/api/client'
import { authApi } from '@/api/auth'

vi.mock('@/api/auth', () => ({
  authApi: { signup: vi.fn(), verifyOpen: vi.fn(), verify: vi.fn(), reset: vi.fn(), forgot: vi.fn() },
}))
const api = vi.mocked(authApi)
const err = (s: number, fields: string[] = []) => new ApiError(s, MESSAGES[s], fields)
const Empty = { template: '<div />' }

async function mountView(C: object) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: ['/login', '/signup', '/verify', '/forgot', '/reset'].map((path) => ({ path, component: Empty })),
  })
  await router.push('/signup')
  const w = mount(C, { global: { plugins: [router] } })
  await flushPromises()
  return { w, router }
}
const setHash = (h: string) => history.replaceState(null, '', `/verify${h}`)

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset())
  setHash('')
})

describe('readFragmentToken', () => {
  it('읽자마자 주소에서 지운다', () => {
    setHash('#token=abc_DEF-123')
    expect(readFragmentToken()).toBe('abc_DEF-123')
    expect(location.hash).toBe('')
    expect(location.pathname).toBe('/verify')
  })
  it('없거나 모양이 다르면 null (그래도 지운다)', () => {
    expect(readFragmentToken()).toBeNull()
    setHash('#token=<script>')
    expect(readFragmentToken()).toBeNull()
    expect(location.hash).toBe('')
  })
})

describe('SignupView', () => {
  it('400 → 입력 칸 에러, 단계 안내는 그대로', async () => {
    api.signup.mockRejectedValue(err(400))
    const { w } = await mountView(SignupView)
    await w.get('input').setValue('a@gmail.com')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(w.text()).toContain('학교 웹메일로만 가입할 수 있어요')
    expect(w.text()).toContain('메일로 링크를 보냅니다')
  })

  it('202 → 보냈어요 + 60초 동안 다시 보내기 잠금 + 이미 가입 안내', async () => {
    vi.useFakeTimers()
    api.signup.mockResolvedValue({ status: 'sent' })
    const { w } = await mountView(SignupView)
    await w.get('input').setValue(' s1@wsu.ac.kr ')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(api.signup).toHaveBeenCalledWith('s1@wsu.ac.kr')
    expect(w.text()).toContain('s1@wsu.ac.kr 로 보냈어요')
    expect(w.text()).toContain('이미 가입한 메일이면 메일이 오지 않습니다. 로그인해 보세요.')
    const resend = () => w.get('button').element as HTMLButtonElement
    expect(resend().disabled).toBe(true)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(resend().disabled).toBe(false)
    vi.useRealTimers()
  })
})

describe('VerifyView', () => {
  it('토큰이 없으면 서버를 부르지 않고 만료 안내 (Review Focus 2)', async () => {
    const { w } = await mountView(VerifyView)
    expect(api.verifyOpen).not.toHaveBeenCalled()
    expect(w.text()).toContain('링크가 만료되었거나 잘못되었습니다')
  })

  it('열자마자 verify/open, 이메일은 읽기 전용으로', async () => {
    setHash('#token=tok1')
    api.verifyOpen.mockResolvedValue({ email: 's1@wsu.ac.kr' })
    const { w } = await mountView(VerifyView)
    expect(api.verifyOpen).toHaveBeenCalledWith('tok1')
    expect(w.text()).toContain('s1@wsu.ac.kr')
    expect(w.findAll('input')).toHaveLength(3) // 이름·학번·비밀번호 — 이메일은 입력이 아니다
  })

  it('409 → 학번 칸만 에러, 나머지 입력은 유지', async () => {
    setHash('#token=tok1')
    api.verifyOpen.mockResolvedValue({ email: 's1@wsu.ac.kr' })
    api.verify.mockRejectedValue(err(409))
    const { w } = await mountView(VerifyView)
    const [name, no, pw] = w.findAll('input')
    await name.setValue('김민준')
    await no.setValue('20231234')
    await pw.setValue('password1')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(w.text()).toContain('이미 등록된 학번입니다')
    expect((name.element as HTMLInputElement).value).toBe('김민준')
    expect(api.verify).toHaveBeenCalledWith({
      token: 'tok1',
      name: '김민준',
      student_no: '20231234',
      password: 'password1',
    })
  })

  it('학번 형식·비밀번호 길이는 보내기 전에 막는다', async () => {
    setHash('#token=tok1')
    api.verifyOpen.mockResolvedValue({ email: 's1@wsu.ac.kr' })
    const { w } = await mountView(VerifyView)
    const [name, no, pw] = w.findAll('input')
    await name.setValue('김민준')
    await no.setValue('2023 1234')
    await pw.setValue('short')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(api.verify).not.toHaveBeenCalled()
    expect(w.text()).toContain('학번은 영문·숫자·하이픈만 쓸 수 있어요')
    expect(w.text()).toContain('8자 이상 입력해 주세요')
  })

  it('성공 → 승인 대기 화면', async () => {
    setHash('#token=tok1')
    api.verifyOpen.mockResolvedValue({ email: 's1@wsu.ac.kr' })
    api.verify.mockResolvedValue({ status: 'pending_approval' })
    const { w } = await mountView(VerifyView)
    const [name, no, pw] = w.findAll('input')
    await name.setValue('김민준')
    await no.setValue('20231234')
    await pw.setValue('password1')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(w.text()).toContain('승인을 기다리는 중입니다')
    expect(w.find('form').exists()).toBe(false)
  })
})

describe('ResetView', () => {
  it('성공 → 다른 기기 로그아웃 안내 + 관리자 안내 한 줄', async () => {
    setHash('#token=r1')
    api.reset.mockResolvedValue({ status: 'ok' })
    const { w } = await mountView(ResetView)
    await w.get('input').setValue('newpassword1')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(api.reset).toHaveBeenCalledWith('r1', 'newpassword1')
    expect(w.text()).toContain('다른 기기에서 로그인해 있던 곳은 모두 로그아웃됩니다')
    expect(w.text()).toContain('관리자 계정이면 관리자 웹 주소에서 로그인하세요.')
  })

  it('400 → 비밀번호를 잊었어요로 되돌린다', async () => {
    setHash('#token=r1')
    api.reset.mockRejectedValue(err(400))
    const { w } = await mountView(ResetView)
    await w.get('input').setValue('newpassword1')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(w.text()).toContain('링크가 만료되었거나 잘못되었습니다')
    expect(w.get('a[href="/forgot"]').exists()).toBe(true)
  })
})
```
(jsdom 의 기본 URL 은 `http://localhost:3000/` 이다 — `history.replaceState` 로 `/verify#…` 를 만든다.)

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/auth/__tests__/signup.spec.ts`
Expected: FAIL — `Failed to resolve import "@/auth/fragment"`

- [ ] **Step 3: 구현**

`web/src/auth/fragment.ts`
```ts
/**
 * 메일 링크의 #token= 을 읽고 즉시 주소에서 지운다 — 서버 로그·Referer·방문 기록에 남지 않게 (auth.md).
 * 지운 뒤 새로고침하면 토큰이 없으므로 화면은 "링크가 만료되었거나 잘못되었습니다" 로 간다.
 */
export function readFragmentToken(): string | null {
  const m = /^#token=([A-Za-z0-9_-]+)$/.exec(location.hash)
  if (location.hash) history.replaceState(history.state, '', location.pathname + location.search)
  return m ? m[1] : null
}
```

`web/src/auth/StepList.vue`
```vue
<script setup lang="ts">
defineProps<{ steps: string[]; current: number }>()
const MARK = ['①', '②', '③', '④', '⑤']
</script>

<template>
  <!-- 번호는 장식이 아니라 실제 순서 — 지금 단계만 brand (auth.md) -->
  <ol class="steps">
    <li
      v-for="(s, i) in steps"
      :key="s"
      class="steps__item"
      :class="{ 'steps__item--current': i === current }"
      :aria-current="i === current ? 'step' : undefined"
    >
      <span aria-hidden="true">{{ MARK[i] }}</span> {{ s }}
    </li>
  </ol>
</template>

<style scoped>
.steps {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.steps__item--current {
  color: var(--brand);
  font-weight: var(--font-weight-bold);
}
</style>
```

`web/src/auth/SignupView.vue`
```vue
<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import AuthShell from './AuthShell.vue'
import StepList from './StepList.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import { authApi } from '@/api/auth'
import { ApiError } from '@/api/client'
import { useCooldown } from '@/lib/useCooldown'

const STEPS = ['메일로 링크를 보냅니다', '링크를 열어 이름·학번·비밀번호', '관리자 승인 뒤 로그인']
const email = ref('')
const sentTo = ref('')
const emailError = ref('')
const error = ref('')
const submitting = ref(false)
const resend = useCooldown()
const { active: locked, start: lock } = useCooldown()

async function send() {
  if (submitting.value || locked.value) return
  emailError.value = ''
  error.value = ''
  submitting.value = true
  const to = email.value.trim()
  try {
    await authApi.signup(to) // 이미 가입이어도 202 — 결과를 가려 말하지 않는다
    sentTo.value = to
    resend.start(60)
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 422) emailError.value = '메일 주소 형식이 올바르지 않습니다'
    else if (e.status === 400) emailError.value = '학교 웹메일로만 가입할 수 있어요'
    else if (e.status === 429) {
      error.value = '잠시 후 다시 시도해 주세요'
      lock(10)
    } else error.value = e.message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthShell title="가입 신청" surface="student" back="/login">
    <template v-if="!sentTo">
      <form class="auth-form" novalidate @submit.prevent="send">
        <Input
          v-model="email"
          label="학교 웹메일"
          type="email"
          autocomplete="email"
          placeholder="20231234@wsu.ac.kr"
          :error="emailError"
          required
        />
        <StepList :steps="STEPS" :current="0" />
        <p v-if="error" class="auth-form__error" role="alert">{{ error }}</p>
        <Button type="submit" :loading="submitting" :disabled="locked">인증 메일 받기</Button>
        <p class="auth-form__note">링크는 5분 안에 열어주세요</p>
      </form>
    </template>
    <template v-else>
      <div class="auth-form">
        <p>
          <strong>{{ sentTo }} 로 보냈어요</strong>
        </p>
        <StepList :steps="STEPS" :current="1" />
        <p class="auth-form__note">
          메일이 안 오면 60초 뒤 다시 보낼 수 있어요<span v-if="resend.active.value" class="num">
            ({{ resend.remaining.value }}초)</span
          >
        </p>
        <p v-if="error" class="auth-form__error" role="alert">{{ error }}</p>
        <Button
          variant="secondary"
          :loading="submitting"
          :disabled="resend.active.value || locked"
          @click="send"
          >다시 보내기</Button
        >
        <p class="auth-form__note">
          이미 가입한 메일이면 메일이 오지 않습니다. 로그인해 보세요.
          <RouterLink to="/login">로그인</RouterLink>
        </p>
      </div>
    </template>
  </AuthShell>
</template>
```
`resend` 는 객체라 템플릿에서 `.value` 를 붙인다(최상위 ref 만 자동으로 풀린다).
보낸 화면의 `다시 보내기` 는 `type="button"` 이 기본이라 폼 제출과 섞이지 않는다. 다시 보낼 때도 같은 `email` 값을 쓴다(보낸 화면에는 입력 칸이 없다).

`web/src/auth/VerifyView.vue`
```vue
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import AuthShell from './AuthShell.vue'
import StepList from './StepList.vue'
import Banner from '@/components/ui/Banner.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import { authApi } from '@/api/auth'
import { ApiError } from '@/api/client'
import { useCooldown } from '@/lib/useCooldown'
import { readFragmentToken } from './fragment'

const STEPS = ['메일로 링크를 보냅니다', '링크를 열어 이름·학번·비밀번호', '관리자 승인 뒤 로그인']
const STUDENT_NO = /^[0-9A-Za-z-]+$/ // 서버 VerifyIn 과 같은 규칙 (S4a §3.4)
const router = useRouter()
const token = readFragmentToken()
type State = 'opening' | 'form' | 'invalid' | 'done'
const state = ref<State>(token ? 'opening' : 'invalid')
const email = ref('')
const name = ref('')
const studentNo = ref('')
const password = ref('')
const errs = ref<{ name?: string; studentNo?: string; password?: string }>({})
const error = ref('')
const submitting = ref(false)
const { active: locked, start: lock } = useCooldown()

async function open() {
  if (!token) return
  error.value = ''
  state.value = 'opening'
  try {
    // 토큰을 쓰지 않고 확인 + 입력 시간 30분 연장 — 다 채운 뒤에 만료를 알면 처음부터 다시다
    email.value = (await authApi.verifyOpen(token)).email
    state.value = 'form'
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 400) state.value = 'invalid'
    else error.value = e.message // 네트워크·503 — 다시 열기 버튼
  }
}
onMounted(open)

function validate(): boolean {
  const e: typeof errs.value = {}
  if (!name.value.trim()) e.name = '이름을 입력해 주세요'
  if (!STUDENT_NO.test(studentNo.value.trim())) e.studentNo = '학번은 영문·숫자·하이픈만 쓸 수 있어요'
  if (password.value.length < 8) e.password = '8자 이상 입력해 주세요'
  errs.value = e
  return Object.keys(e).length === 0
}

async function submit() {
  if (submitting.value || locked.value || !token || !validate()) return
  error.value = ''
  submitting.value = true
  try {
    await authApi.verify({
      token,
      name: name.value.trim(),
      student_no: studentNo.value.trim(),
      password: password.value,
    })
    state.value = 'done'
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    // 409 는 토큰을 쓰지 않는다 — 학번만 고쳐 다시 낸다 (auth.md)
    if (e.status === 409) errs.value = { studentNo: '이미 등록된 학번입니다' }
    else if (e.status === 400) state.value = 'invalid'
    else if (e.status === 422)
      errs.value = {
        name: e.fields.includes('name') ? '이름을 확인해 주세요' : undefined,
        studentNo: e.fields.includes('student_no') ? '학번은 영문·숫자·하이픈만 쓸 수 있어요' : undefined,
        password: e.fields.includes('password') ? '8자 이상 입력해 주세요' : undefined,
      }
    else if (e.status === 429) {
      error.value = '잠시 후 다시 시도해 주세요'
      lock(10)
    } else error.value = e.message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthShell :title="state === 'done' ? '가입 신청 완료' : '가입 완료'" surface="student">
    <template #banner>
      <Banner v-if="error && state === 'opening'" tone="danger" :message="error" :dismissible="false" />
    </template>

    <template v-if="state === 'opening'">
      <Skeleton :rows="3" />
      <Button v-if="error" variant="secondary" @click="open">다시 열기</Button>
    </template>

    <template v-else-if="state === 'invalid'">
      <p class="auth-form__error" role="alert">링크가 만료되었거나 잘못되었습니다</p>
      <Button @click="router.push('/signup')">가입 신청 다시 하기</Button>
    </template>

    <template v-else-if="state === 'form'">
      <p class="verify__email">{{ email }}</p>
      <StepList :steps="STEPS" :current="1" />
      <form class="auth-form" novalidate @submit.prevent="submit">
        <Input v-model="name" label="이름" autocomplete="name" :error="errs.name" required />
        <Input
          v-model="studentNo"
          label="학번"
          inputmode="text"
          autocomplete="off"
          :error="errs.studentNo"
          required
        />
        <Input
          v-model="password"
          label="비밀번호"
          type="password"
          autocomplete="new-password"
          hint="8자 이상"
          :error="errs.password"
          required
        />
        <p v-if="error" class="auth-form__error" role="alert">{{ error }}</p>
        <Button type="submit" :loading="submitting" :disabled="locked">가입 신청</Button>
      </form>
    </template>

    <template v-else>
      <StepList :steps="STEPS" :current="2" />
      <p><strong>승인을 기다리는 중입니다</strong></p>
      <p class="auth-form__note">
        관리자가 승인해야 로그인할 수 있어요. 승인되면 메일로 알려 드려요.
      </p>
      <RouterLink to="/login">로그인 화면으로</RouterLink>
    </template>
  </AuthShell>
</template>

<style scoped>
.verify__email {
  margin: 0;
  font-weight: var(--font-weight-bold);
  word-break: break-all;
}
</style>
```
`.auth-form__error`·`.auth-form__note` 는 `AuthShell` 의 `:slotted` 스타일이 받는다.

`web/src/auth/ForgotView.vue`
```vue
<script setup lang="ts">
import { ref } from 'vue'
import AuthShell from './AuthShell.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import { authApi } from '@/api/auth'
import { ApiError } from '@/api/client'
import { useCooldown } from '@/lib/useCooldown'

const email = ref('')
const sent = ref(false)
const emailError = ref('')
const error = ref('')
const submitting = ref(false)
const resend = useCooldown()
const { active: locked, start: lock } = useCooldown()

async function send() {
  if (submitting.value || locked.value) return
  emailError.value = ''
  error.value = ''
  submitting.value = true
  try {
    await authApi.forgot(email.value.trim()) // 없는 메일·대기 계정도 202 — 결과는 하나뿐
    sent.value = true
    resend.start(60)
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 422) emailError.value = '메일 주소 형식이 올바르지 않습니다'
    else if (e.status === 429) {
      error.value = '잠시 후 다시 시도해 주세요'
      lock(10)
    } else error.value = e.message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthShell title="비밀번호 재설정" surface="student" back="/login">
    <form v-if="!sent" class="auth-form" novalidate @submit.prevent="send">
      <Input
        v-model="email"
        label="학교 웹메일"
        type="email"
        autocomplete="email"
        :error="emailError"
        required
      />
      <p v-if="error" class="auth-form__error" role="alert">{{ error }}</p>
      <Button type="submit" :loading="submitting" :disabled="locked">재설정 메일 받기</Button>
      <p class="auth-form__note">링크는 5분 안에 열어주세요</p>
    </form>
    <div v-else class="auth-form">
      <p><strong>보냈어요</strong></p>
      <!-- "가입된 메일이면" 을 꼭 적는다 — 없으면 오타 낸 사람이 영원히 기다린다 (auth.md) -->
      <p class="auth-form__note">
        가입된 메일이면 재설정 링크가 갑니다. 안 오면 60초 뒤 다시 보낼 수 있어요<span
          v-if="resend.active.value"
          class="num"
        >
          ({{ resend.remaining.value }}초)</span
        >
      </p>
      <p v-if="error" class="auth-form__error" role="alert">{{ error }}</p>
      <Button
        variant="secondary"
        :loading="submitting"
        :disabled="resend.active.value || locked"
        @click="send"
        >다시 보내기</Button
      >
    </div>
  </AuthShell>
</template>
```

`web/src/auth/ResetView.vue`
```vue
<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import AuthShell from './AuthShell.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import { authApi } from '@/api/auth'
import { ApiError } from '@/api/client'
import { useCooldown } from '@/lib/useCooldown'
import { readFragmentToken } from './fragment'

// 입력 시간 연장이 없다 (비밀번호 하나라 5분이면 충분 — S4a). 만료되면 /forgot 으로 되돌린다
const token = readFragmentToken()
const state = ref<'form' | 'invalid' | 'done'>(token ? 'form' : 'invalid')
const password = ref('')
const pwError = ref('')
const error = ref('')
const submitting = ref(false)
const { active: locked, start: lock } = useCooldown()

async function submit() {
  if (submitting.value || locked.value || !token) return
  pwError.value = password.value.length < 8 ? '8자 이상 입력해 주세요' : ''
  if (pwError.value) return
  error.value = ''
  submitting.value = true
  try {
    await authApi.reset(token, password.value)
    state.value = 'done'
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 400) state.value = 'invalid'
    else if (e.status === 422) pwError.value = '8자 이상 입력해 주세요'
    else if (e.status === 429) {
      error.value = '잠시 후 다시 시도해 주세요'
      lock(10)
    } else error.value = e.message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthShell title="새 비밀번호" surface="student">
    <form v-if="state === 'form'" class="auth-form" novalidate @submit.prevent="submit">
      <Input
        v-model="password"
        label="새 비밀번호"
        type="password"
        autocomplete="new-password"
        hint="8자 이상"
        :error="pwError"
        required
      />
      <p v-if="error" class="auth-form__error" role="alert">{{ error }}</p>
      <Button type="submit" :loading="submitting" :disabled="locked">비밀번호 바꾸기</Button>
    </form>
    <template v-else-if="state === 'invalid'">
      <p class="auth-form__error" role="alert">링크가 만료되었거나 잘못되었습니다</p>
      <RouterLink to="/forgot">비밀번호를 잊었어요</RouterLink>
    </template>
    <template v-else>
      <p><strong>비밀번호를 바꿨어요</strong></p>
      <p class="auth-form__note">다른 기기에서 로그인해 있던 곳은 모두 로그아웃됩니다.</p>
      <RouterLink to="/login">로그인하러 가기</RouterLink>
      <!-- 관리자 웹 주소를 링크로 걸지 않는다 — 학생 웹이 관리자 주소를 실을 이유가 없다 (auth.md) -->
      <p class="auth-form__note">관리자 계정이면 관리자 웹 주소에서 로그인하세요.</p>
    </template>
  </AuthShell>
</template>
```

`web/src/student/router.ts` 의 `routes` 에 추가:
```ts
  { path: '/signup', component: () => import('@/auth/SignupView.vue') },
  { path: '/verify', component: () => import('@/auth/VerifyView.vue') },
  { path: '/forgot', component: () => import('@/auth/ForgotView.vue') },
  { path: '/reset', component: () => import('@/auth/ResetView.vue') },
```

- [ ] **Step 4: 단위 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint && pnpm exec prettier --check .`
Expected: PASS

- [ ] **Step 5: E2E — 가입부터 로그인까지, 재설정**

`web/e2e/auth.spec.ts`
```ts
import { expect, test } from '@playwright/test'
import {
  PASSWORD,
  SIZES,
  apiLogin,
  createStudent,
  fillLogin,
  mailToken,
  nextAdmin,
  shot,
  uniqEmail,
} from './helpers'

test.use({ viewport: SIZES.student })

test('가입 신청 → 링크 → 승인 대기 403 → 승인 → 로그인', async ({ page, request }) => {
  const email = uniqEmail('new')
  await page.goto('/signup')
  await shot(page, 'signup-390')
  await page.getByLabel('학교 웹메일').fill(email)
  await page.getByRole('button', { name: '인증 메일 받기' }).click()
  await expect(page.getByText(`${email} 로 보냈어요`)).toBeVisible()
  await expect(page.getByRole('button', { name: '다시 보내기' })).toBeDisabled()
  await shot(page, 'signup-sent-390')

  const token = await mailToken(email)
  await page.goto(`/verify#token=${token}`)
  await expect(page.getByText(email)).toBeVisible()
  expect(new URL(page.url()).hash).toBe('') // 토큰은 주소에서 지워졌다
  await page.getByLabel('이름').fill('김민준')
  await page.getByLabel('학번').fill(`E${Date.now().toString(36)}`)
  await page.getByLabel('비밀번호').fill(PASSWORD)
  await shot(page, 'verify-390')
  await page.getByRole('button', { name: '가입 신청' }).click()
  await expect(page.getByText('승인을 기다리는 중입니다')).toBeVisible()
  await shot(page, 'verify-done-390')

  await page.goto('/login')
  await fillLogin(page, email)
  await expect(page.getByText('아직 승인되지 않았어요. 관리자 승인 뒤 로그인할 수 있어요.')).toBeVisible()
  await shot(page, 'login-pending-390')

  const t = await apiLogin(request, nextAdmin())
  await request.post(`/api/admin/users/${encodeURIComponent(email)}/approve`, {
    headers: { authorization: `Bearer ${t}` },
  })
  await fillLogin(page, email)
  await expect(page.getByText('강의실 화면은 준비 중입니다')).toBeVisible()
})

test('학번 중복 409 → 학번만 고쳐 다시 제출', async ({ page, request }) => {
  const taken = await createStudent(request)
  const email = uniqEmail('dup')
  await request.post('/api/auth/signup', { data: { email } })
  await page.goto(`/verify#token=${await mailToken(email)}`)
  await page.getByLabel('이름').fill('이정민')
  await page.getByLabel('학번').fill(taken.studentNo)
  await page.getByLabel('비밀번호').fill(PASSWORD)
  await page.getByRole('button', { name: '가입 신청' }).click()
  await expect(page.getByText('이미 등록된 학번입니다')).toBeVisible()
  await expect(page.getByLabel('이름')).toHaveValue('이정민')
  await page.getByLabel('학번').fill(`${taken.studentNo}X`)
  await page.getByRole('button', { name: '가입 신청' }).click()
  await expect(page.getByText('승인을 기다리는 중입니다')).toBeVisible()
})

test('링크를 연 뒤 새로고침하면 만료 안내 (Review Focus 2)', async ({ page }) => {
  const email = uniqEmail('reload')
  await page.goto('/signup')
  await page.getByLabel('학교 웹메일').fill(email)
  await page.getByRole('button', { name: '인증 메일 받기' }).click()
  await page.goto(`/verify#token=${await mailToken(email)}`)
  await expect(page.getByText(email)).toBeVisible()
  await page.reload()
  await expect(page.getByText('링크가 만료되었거나 잘못되었습니다')).toBeVisible()
})

test('학교 웹메일이 아니면 입력 칸 에러', async ({ page }) => {
  await page.goto('/signup')
  await page.getByLabel('학교 웹메일').fill('someone@gmail.com')
  await page.getByRole('button', { name: '인증 메일 받기' }).click()
  await expect(page.getByText('학교 웹메일로만 가입할 수 있어요')).toBeVisible()
  await expect(page.getByText('메일로 링크를 보냅니다')).toBeVisible()
})

test('비밀번호 재설정 → 새 비밀번호로 로그인, 옛 비밀번호는 거절', async ({ page, request }) => {
  const s = await createStudent(request, { approve: true })
  await page.goto('/forgot')
  await page.getByLabel('학교 웹메일').fill(s.email)
  await page.getByRole('button', { name: '재설정 메일 받기' }).click()
  await expect(page.getByText('가입된 메일이면 재설정 링크가 갑니다.')).toBeVisible()
  await shot(page, 'forgot-sent-390')

  await page.goto(`/reset#token=${await mailToken(s.email)}`)
  await page.getByLabel('새 비밀번호').fill('newpassword9')
  await page.getByRole('button', { name: '비밀번호 바꾸기' }).click()
  await expect(page.getByText('다른 기기에서 로그인해 있던 곳은 모두 로그아웃됩니다.')).toBeVisible()
  await shot(page, 'reset-done-390')

  await page.goto('/login')
  await fillLogin(page, s.email, PASSWORD)
  await expect(page.getByText('이메일 또는 비밀번호가 틀립니다')).toBeVisible()
  await fillLogin(page, s.email, 'newpassword9')
  await expect(page.getByText('강의실 화면은 준비 중입니다')).toBeVisible()
})
```
`mailToken` 은 그 주소로 온 **마지막** 메일의 토큰을 준다 — 재설정 테스트에서는 가입 메일 뒤에 온 재설정 메일이다.

- [ ] **Step 6: E2E 실행 + 스크린샷 대조**

Run: `cd web && pnpm e2e`
Expected: 로그인 5 + 인증 5 = 10 passed. 스크린샷 7장(`signup-390` … `reset-done-390`)을 `auth.md` 와 대조한다:
- `/signup`: 뒤로 `‹` + 제목, 입력 placeholder `20231234@wsu.ac.kr`, ①②③ 중 ① 만 `brand`, 버튼 아래 `링크는 5분 안에 열어주세요`.
- 보낸 화면: `… 로 보냈어요`, `다시 보내기` 비활성, 이미 가입 안내 + `로그인` 링크.
- `/verify`: 이메일이 입력이 아니라 굵은 글자, 입력 셋, 비밀번호 hint `8자 이상`.
- 승인 대기 403 Banner 가 적색이 아닌 `sunken` 바탕.
- 모든 터치 타깃 48px 이상(입력·버튼·뒤로 링크).

- [ ] **Step 7: 커밋**

```bash
git add -A web
git commit -m "feat(web): 학생 가입 신청·verify(fragment 즉시 삭제·open 선확인·409 학번만)·비밀번호 재설정 화면 + E2E"
```

---

### Task 12: AdminShell — 사이드바 · 좁은 폭 Banner · 대기 건수

**Files:**
- Create: `web/src/admin/AdminShell.vue`, `web/src/admin/pending.ts`, `web/src/admin/views/UsersView.vue`(자리만 — Task 13 이 채운다), `web/e2e/admin-shell.spec.ts`
- Modify: `web/src/admin/router.ts`
- Delete: `web/src/admin/views/PlaceholderView.vue`
- Test: `web/src/admin/__tests__/shell.spec.ts`

**Interfaces:**
- Consumes: `usersApi.list` (Task 3) · `usePolling` (Task 4) · `SidebarNav`, `Banner`, `Button` · `session`, `clearSession`
- Produces:
  - `pending.ts`: `pendingCount: Ref<number>` · `refreshPending(): Promise<void>` — `GET /api/admin/users?status=pending_approval` 의 길이. Task 13 이 승인·거절 뒤 부른다.
  - 관리자 라우트 모양: `'/'`(`AdminShell`, `meta.auth`) 의 children — `''` → `/users` 리다이렉트, `'users'` → `UsersView`. F2·F3 는 이 children 에 화면을 더하고 `NAV` 에 항목을 **위쪽에** 끼운다(메뉴 순서는 #46 `admin-master.md` 확정본: `건물 · 강의실` · `강의실 설정` · `주간 시간표` · `노드 상태` · `전송 현황` · `회원`).

Ruling: F1 사이드바에는 `회원` 하나만 둔다 — 아직 없는 화면을 메뉴에 두면 "누르면 아무것도 없는 항목"이 된다(#46 이 `설정` 을 뺀 이유와 같다). 대기 건수는 `admin-users.md` 미결 4 의 `/api/admin/summary` 가 아니라 `users?status=pending_approval` 길이로 센다 — summary 는 S4b(#48) 라 아직 main 에 없고, 회원 수가 수십이라 목록 길이로 충분하다. F3 에서 summary 로 바꿀지 판단한다. 사이드바 아래 학교 정보(#46)는 학교 API 를 쓰는 F2 에서 넣는다. F1 푸터는 로그인한 이름 + 로그아웃.

- [ ] **Step 1: 실패 테스트**

`web/src/admin/__tests__/shell.spec.ts`
```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import AdminApp from '@/admin/AdminApp.vue'
import { makeRouter } from '@/admin/router'
import { usersApi } from '@/api/users'
import { clearSession, session, setSession } from '@/lib/session'

vi.mock('@/api/users', () => ({ usersApi: { list: vi.fn() } }))
const list = vi.mocked(usersApi.list)
const user = (email: string) => ({ email }) as never

function mockWidth(narrow: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({ matches: narrow, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
  )
}
async function mountApp(path = '/users') {
  const router = makeRouter(createMemoryHistory())
  await router.push(path)
  await router.isReady()
  const w = mount(AdminApp, { global: { plugins: [router] } })
  await flushPromises()
  return { w, router }
}

beforeEach(() => {
  localStorage.clear()
  list.mockReset().mockResolvedValue([user('a'), user('b')])
  setSession({ token: 't', role: 'admin', school_id: 1, name: '관리자1' })
  mockWidth(false)
})

describe('AdminShell', () => {
  it('/ 는 /users 로, 회원 메뉴가 활성이고 대기 건수 배지', async () => {
    const { w, router } = await mountApp('/')
    expect(router.currentRoute.value.path).toBe('/users')
    expect(list).toHaveBeenCalledWith('pending_approval')
    const link = w.get('nav a')
    expect(link.text()).toContain('회원')
    expect(link.text()).toContain('2')
    expect(link.attributes('aria-current')).toBe('page')
    expect(w.text()).toContain('관리자1')
  })

  it('1024px 미만이면 안내 Banner, 닫으면 다시 안 뜬다', async () => {
    mockWidth(true)
    const a = await mountApp()
    expect(a.w.text()).toContain('관리자 화면은 1024px 이상에서 쓰도록 만들어졌습니다')
    await a.w.get('.banner button').trigger('click')
    a.w.unmount()
    const b = await mountApp()
    expect(b.w.find('.banner').exists()).toBe(false)
  })

  it('넓으면 Banner 없음', async () => {
    const { w } = await mountApp()
    expect(w.find('.banner').exists()).toBe(false)
  })

  it('로그아웃 → 세션을 버리고 로그인으로', async () => {
    const { w, router } = await mountApp()
    await w.get('button.shell__logout').trigger('click')
    await flushPromises()
    expect(session.value).toBeNull()
    expect(router.currentRoute.value.path).toBe('/login')
  })
})

describe('guard', () => {
  it('세션 없이 /users → /login?next=/users', async () => {
    clearSession()
    const router = makeRouter(createMemoryHistory())
    await router.push('/users')
    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.next).toBe('/users')
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin`
Expected: FAIL — `/users` 라우트 없음(리다이렉트 기대 실패) 또는 `Failed to resolve import "@/admin/pending"`

- [ ] **Step 3: 구현**

`web/src/admin/pending.ts`
```ts
import { ref } from 'vue'
import { usersApi } from '@/api/users'
import { ApiError } from '@/api/client'

/** 사이드 메뉴 `회원` 옆 대기 건수 (admin-users.md) — 이 화면이 막히면 학생 웹 전체가 막힌다 */
export const pendingCount = ref(0)

export async function refreshPending(): Promise<void> {
  try {
    pendingCount.value = (await usersApi.list('pending_approval')).length
  } catch (e) {
    if (!(e instanceof ApiError)) throw e // 네트워크·401 은 client 가 처리 — 배지는 옛 값을 둔다
  }
}
```

`web/src/admin/AdminShell.vue`
```vue
<script setup lang="ts">
import { computed, onMounted, onScopeDispose, ref } from 'vue'
import { RouterView, useRouter } from 'vue-router'
import SidebarNav from '@/components/ui/SidebarNav.vue'
import Banner from '@/components/ui/Banner.vue'
import Button from '@/components/ui/Button.vue'
import { clearSession, session } from '@/lib/session'
import { usePolling } from '@/lib/usePolling'
import { pendingCount, refreshPending } from './pending'

const router = useRouter()
const me = computed(() => session.value?.name ?? '')
// F2·F3 가 위쪽에 항목을 더한다 — 순서는 #46 admin-master.md 확정본
const nav = computed(() => [{ to: '/users', label: '회원', badge: pendingCount.value }])

onMounted(refreshPending)
usePolling(refreshPending, 60_000)

// 데스크톱 전용 — 막지 않고 가로 스크롤 + 1회 안내 (tokens.md 브레이크포인트)
const mq = window.matchMedia('(max-width: 1023px)')
const narrow = ref(mq.matches)
const onChange = (e: MediaQueryListEvent) => (narrow.value = e.matches)
mq.addEventListener('change', onChange)
onScopeDispose(() => mq.removeEventListener('change', onChange))

function logout() {
  clearSession()
  void router.replace('/login')
}
</script>

<template>
  <div class="shell">
    <SidebarNav :items="nav">
      <template #footer>
        <p class="shell__user">{{ me }}</p>
        <Button variant="ghost" size="sm" class="shell__logout" @click="logout">로그아웃</Button>
      </template>
    </SidebarNav>
    <div class="shell__main">
      <Banner
        v-if="narrow"
        message="관리자 화면은 1024px 이상에서 쓰도록 만들어졌습니다"
        storage-key="admin-narrow"
      />
      <RouterView />
    </div>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  min-width: 1024px;
  min-height: 100vh;
}
.shell__main {
  flex: 1;
  min-width: 0;
}
.shell__user {
  margin: 0 0 var(--space-1);
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
</style>
```
`web/src/admin/views/UsersView.vue` (Task 13 이 채운다)
```vue
<template>
  <h1>회원</h1>
</template>
```

`web/src/admin/router.ts` 의 `routes`:
```ts
export const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: () => import('./AdminShell.vue'),
    meta: { auth: true },
    children: [
      { path: '', redirect: '/users' },
      { path: 'users', component: () => import('./views/UsersView.vue') },
    ],
  },
  { path: '/login', component: () => import('@/auth/LoginView.vue'), props: { app: 'admin' } },
]
```
`meta.auth` 는 부모에 두면 `to.meta` 로 합쳐져 자식에도 걸린다.
`PlaceholderView.vue` 를 지운다(`git rm`). Task 1 의 `admin/__tests__/router.spec.ts` 는 Task 10 에서 `/login` 기대로 바뀌어 그대로 통과한다.

`LoginView` 의 로그인 뒤 기본 경로 `'/'` 는 이제 `/users` 로 넘어간다.

- [ ] **Step 4: 단위 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint && pnpm exec prettier --check .`
Expected: PASS

- [ ] **Step 5: E2E — 셸**

`web/e2e/admin-shell.spec.ts`
```ts
import { expect, test } from '@playwright/test'
import { SIZES, createStudent, fillLogin, nextAdmin, shot } from './helpers'

test('로그인 → 회원 화면, 사이드바 활성 + 대기 건수', async ({ page, request }) => {
  await createStudent(request) // 승인 대기 1건 이상
  await page.setViewportSize(SIZES.admin)
  await page.goto('/admin/')
  await fillLogin(page, nextAdmin())
  await expect(page).toHaveURL(/\/admin\/users$/)
  const link = page.getByRole('link', { name: /회원/ })
  await expect(link).toHaveAttribute('aria-current', 'page')
  await expect(link).toContainText(/\d+/)
  const nav = await page.locator('nav').boundingBox()
  expect(Math.round(nav!.width)).toBe(220)
  await shot(page, 'admin-shell-1440')
})

test('1024px 미만 — 가로 스크롤 + 한 번만 뜨는 Banner', async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 800 })
  await page.goto('/admin/login')
  await fillLogin(page, nextAdmin())
  const banner = page.getByText('관리자 화면은 1024px 이상에서 쓰도록 만들어졌습니다')
  await expect(banner).toBeVisible()
  const scrollW = await page.evaluate(() => document.documentElement.scrollWidth)
  expect(scrollW).toBeGreaterThanOrEqual(1024)
  await shot(page, 'admin-narrow-900')
  await page.getByRole('button', { name: '닫기' }).click()
  await expect(banner).toHaveCount(0)
  // 새로고침하면 메모리 세션이라 다시 로그인 — Banner 는 localStorage 로 기억
  await page.reload()
  await fillLogin(page, nextAdmin())
  await expect(page).toHaveURL(/\/admin\/users$/)
  await expect(banner).toHaveCount(0)
})
```

- [ ] **Step 6: E2E 실행 + 스크린샷 대조**

Run: `cd web && pnpm e2e e2e/admin-shell.spec.ts`
Expected: 2 passed. `admin-shell-1440.png` 를 `components.md` SidebarNav 와 대조: 폭 220, 바탕 `sunken`, 오른쪽 `line.2` 1px, 활성 항목 `brand.tint` 바탕 + `brand` 글자, 항목 높이 32. `admin-narrow-900.png`: Banner 가 본문 위 전폭, 레이아웃이 줄지 않고 가로 스크롤.

- [ ] **Step 7: 커밋**

```bash
git add -A web
git commit -m "feat(web): 관리자 셸 — 사이드바(회원·대기 건수 60초 폴링), 1024px 미만 안내 Banner, 로그아웃"
```

---

### Task 13: 회원 승인 화면

**Files:**
- Create: `web/src/admin/usersView.ts`, `web/e2e/admin-users.spec.ts`
- Modify: `web/src/admin/views/UsersView.vue` (전부)
- Test: `web/src/admin/__tests__/users.spec.ts`

**Interfaces:**
- Consumes: `usersApi.{list, approve, reject, disable, enable}` · `UserOut`, `UserStatus` (Task 3) · `useResource` (Task 4) · `Table`, `Badge`, `Button`, `Select`, `Input`, `Textarea`, `Modal`, `showToast`, `EmptyState` · `relativeKo`, `formatKst` · `refreshPending` (Task 12)
- Produces `admin/usersView.ts`: `STATUS_BADGE: Record<UserStatus, { label: string; tone: 'neutral'|'danger'; variant: 'outline'|'solid' }>` · `FILTERS` · `sortUsers(users: UserOut[]): UserOut[]` · `matchUser(u: UserOut, q: string): boolean`

화면 규칙은 `admin-users.md` 그대로: 기본 필터 `승인 대기` · 정렬 대기 건 오래된 순, 나머지 `created_at` 최신순 · 컬럼 폭 이름 96 · 학번 104 · 웹메일 나머지 · 역할 72 · 상태 88 · 신청 96 · 승인 96 · 작업 136 · `승인` 에 확인 없음 · `거절` 은 사유 필수 Modal · `정지` 는 확인 Modal · 관리자 행은 작업 칸에 `CLI 에서만 변경`(text.3) · 409 는 Toast `이미 처리된 신청입니다` + 목록 새로고침 · 성공 Toast 는 메일 발송을 보장하지 않는 문구.

Ruling(미결 3 검색 범위): 이름·학번·메일 부분 일치(대소문자 무시)로 화면에서 거른다. 회원 수가 수십이라 서버 검색이 필요 없다. 목업의 placeholder `호수 검색` 은 복사 오류로 보고 `이름·학번·메일 검색` 으로 쓴다.

- [ ] **Step 1: 실패 테스트**

`web/src/admin/__tests__/users.spec.ts`
```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import UsersView from '@/admin/views/UsersView.vue'
import { matchUser, sortUsers } from '@/admin/usersView'
import { usersApi } from '@/api/users'
import { ApiError, MESSAGES } from '@/api/client'
import type { UserOut } from '@/api/types'
import { toasts, dismissToast } from '@/components/ui/toast'

vi.mock('@/api/users', () => ({
  usersApi: { list: vi.fn(), approve: vi.fn(), reject: vi.fn(), disable: vi.fn(), enable: vi.fn() },
}))
vi.mock('@/admin/pending', () => ({ refreshPending: vi.fn() }))
const api = vi.mocked(usersApi)

const u = (over: Partial<UserOut>): UserOut => ({
  email: 's@wsu.ac.kr',
  school_id: 1,
  role: 'student',
  status: 'pending_approval',
  name: '김민준',
  student_no: '20231234',
  created_at: new Date('2026-09-25T00:00:00Z'),
  approved_at: null,
  ...over,
})
const stubs = { teleport: true }
async function mountView() {
  const w = mount(UsersView, { global: { stubs } })
  await flushPromises()
  return w
}
const buttonByText = (w: ReturnType<typeof mount>, text: string) =>
  w.findAll('button').find((b) => b.text() === text)!

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset())
  for (const t of [...toasts.value]) dismissToast(t.id)
})

describe('정렬·검색', () => {
  it('대기 건은 오래된 순으로 먼저, 나머지는 최신순', () => {
    const d = (s: string) => new Date(`2026-09-${s}T00:00:00Z`)
    const out = sortUsers([
      u({ email: 'a', status: 'active', created_at: d('01') }),
      u({ email: 'p2', created_at: d('20') }),
      u({ email: 'b', status: 'active', created_at: d('10') }),
      u({ email: 'p1', created_at: d('05') }),
    ])
    expect(out.map((x) => x.email)).toEqual(['p1', 'p2', 'b', 'a'])
  })
  it('이름·학번·메일 부분 일치, 대소문자 무시', () => {
    const x = u({ name: '이정민', student_no: 'AB-12', email: 'Lee@wsu.ac.kr' })
    expect(matchUser(x, '정민')).toBe(true)
    expect(matchUser(x, 'ab-1')).toBe(true)
    expect(matchUser(x, 'lee@')).toBe(true)
    expect(matchUser(x, '김')).toBe(false)
    expect(matchUser(u({ student_no: null }), '')).toBe(true)
  })
})

describe('UsersView', () => {
  it('기본 필터는 승인 대기, 대기 행에 승인·거절', async () => {
    api.list.mockResolvedValue([u({})])
    const w = await mountView()
    expect(api.list).toHaveBeenCalledWith('pending_approval')
    expect(w.text()).toContain('대기중')
    expect(buttonByText(w, '승인')).toBeTruthy()
    expect(buttonByText(w, '거절')).toBeTruthy()
  })

  it('승인은 확인 없이 바로, 성공 Toast 는 발송을 보장하지 않는 문구', async () => {
    api.list.mockResolvedValue([u({})])
    api.approve.mockResolvedValue(u({ status: 'active' }))
    const w = await mountView()
    await buttonByText(w, '승인').trigger('click')
    await flushPromises()
    expect(api.approve).toHaveBeenCalledWith('s@wsu.ac.kr')
    expect(w.find('[role="dialog"]').exists()).toBe(false)
    expect(toasts.value.at(-1)?.message).toBe('승인했습니다. 학생에게 메일이 갑니다.')
    expect(api.list).toHaveBeenCalledTimes(2) // 새로고침
  })

  it('409 → 이미 처리된 신청 + 새로고침, 버튼이 잠긴 채 남지 않는다 (Review Focus 4)', async () => {
    api.list.mockResolvedValue([u({})])
    api.approve.mockRejectedValue(new ApiError(409, MESSAGES[409]))
    const w = await mountView()
    await buttonByText(w, '승인').trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe('이미 처리된 신청입니다')
    expect(api.list).toHaveBeenCalledTimes(2)
    expect((buttonByText(w, '승인').element as HTMLButtonElement).disabled).toBe(false)
  })

  it('네트워크 오류 → danger Toast + 재시도', async () => {
    api.list.mockResolvedValue([u({})])
    api.approve.mockRejectedValueOnce(new ApiError(0, MESSAGES[0]))
    api.approve.mockResolvedValueOnce(u({ status: 'active' }))
    const w = await mountView()
    await buttonByText(w, '승인').trigger('click')
    await flushPromises()
    const t = toasts.value.at(-1)!
    expect(t.tone).toBe('danger')
    t.action!.onClick()
    await flushPromises()
    expect(api.approve).toHaveBeenCalledTimes(2)
  })

  it('거절 — 사유 없이는 못 보낸다, 사유는 그대로 간다', async () => {
    api.list.mockResolvedValue([u({})])
    api.reject.mockResolvedValue(u({ status: 'rejected' }))
    const w = await mountView()
    await buttonByText(w, '거절').trigger('click')
    const dialog = w.get('[role="dialog"]')
    const submit = () => dialog.findAll('button').find((b) => b.text() === '거절')!
    expect((submit().element as HTMLButtonElement).disabled).toBe(true)
    await dialog.get('textarea').setValue('  학번이 잘못되었습니다  ')
    expect((submit().element as HTMLButtonElement).disabled).toBe(false)
    await submit().trigger('click')
    await flushPromises()
    expect(api.reject).toHaveBeenCalledWith('s@wsu.ac.kr', '학번이 잘못되었습니다')
    expect(w.find('[role="dialog"]').exists()).toBe(false)
  })

  it('정지는 확인 Modal, 관리자 행은 CLI 에서만 변경', async () => {
    api.list.mockResolvedValue([
      u({ email: 'a@wsu.ac.kr', status: 'active' }),
      u({ email: 'admin@wsu.ac.kr', role: 'admin', status: 'active', student_no: null }),
    ])
    api.disable.mockResolvedValue(u({ status: 'disabled' }))
    const w = await mountView()
    expect(w.text()).toContain('CLI 에서만 변경')
    expect(w.findAll('button').filter((b) => b.text() === '정지')).toHaveLength(1)
    await buttonByText(w, '정지').trigger('click')
    expect(w.get('[role="dialog"]').text()).toContain('로그인이 즉시 끊깁니다')
    const confirm = w.get('[role="dialog"]').findAll('button').find((b) => b.text() === '정지')!
    await confirm.trigger('click')
    await flushPromises()
    expect(api.disable).toHaveBeenCalledWith('a@wsu.ac.kr')
  })

  it('정지된 회원은 해제(확인 없음), 정지됨 배지는 적색', async () => {
    api.list.mockResolvedValue([u({ status: 'disabled' })])
    api.enable.mockResolvedValue(u({ status: 'active' }))
    const w = await mountView()
    expect(w.get('.badge--danger').text()).toBe('정지됨')
    await buttonByText(w, '해제').trigger('click')
    await flushPromises()
    expect(api.enable).toHaveBeenCalledWith('s@wsu.ac.kr')
  })

  it('필터를 바꾸면 그 상태로 다시 부른다, 전체는 status 없이', async () => {
    api.list.mockResolvedValue([])
    const w = await mountView()
    await w.get('select').setValue('')
    await flushPromises()
    expect(api.list).toHaveBeenLastCalledWith(undefined)
    expect(w.text()).toContain('아직 가입한 회원이 없습니다')
  })

  it('대기 0건은 평소 상태 — 버튼 없는 빈 문구', async () => {
    api.list.mockResolvedValue([])
    const w = await mountView()
    expect(w.text()).toContain('승인을 기다리는 신청이 없습니다')
    expect(w.find('.empty button').exists()).toBe(false)
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin/__tests__/users.spec.ts`
Expected: FAIL — `Failed to resolve import "@/admin/usersView"`

- [ ] **Step 3: 구현**

`web/src/admin/usersView.ts`
```ts
import type { UserOut, UserStatus } from '@/api/types'

/** 적색은 disabled 에만 — 대기·거절은 문제 상황이 아니다 (admin-users.md) */
export const STATUS_BADGE: Record<
  UserStatus,
  { label: string; tone: 'neutral' | 'danger'; variant: 'outline' | 'solid' }
> = {
  pending_approval: { label: '대기중', tone: 'neutral', variant: 'outline' },
  active: { label: '활성', tone: 'neutral', variant: 'solid' },
  rejected: { label: '거절됨', tone: 'neutral', variant: 'outline' },
  disabled: { label: '정지됨', tone: 'danger', variant: 'outline' },
}

export const FILTERS: { value: UserStatus | ''; label: string }[] = [
  { value: 'pending_approval', label: '승인 대기' },
  { value: '', label: '전체' },
  { value: 'active', label: '활성' },
  { value: 'rejected', label: '거절' },
  { value: 'disabled', label: '정지' },
]

/** 대기 건은 먼저 온 사람 먼저, 나머지는 최신순 */
export function sortUsers(users: UserOut[]): UserOut[] {
  const t = (x: UserOut) => x.created_at.getTime()
  const pending = users.filter((x) => x.status === 'pending_approval').sort((a, b) => t(a) - t(b))
  const rest = users.filter((x) => x.status !== 'pending_approval').sort((a, b) => t(b) - t(a))
  return [...pending, ...rest]
}

export function matchUser(u: UserOut, q: string): boolean {
  const s = q.trim().toLowerCase()
  if (!s) return true
  return [u.name, u.student_no ?? '', u.email].some((v) => v.toLowerCase().includes(s))
}
```

`web/src/admin/views/UsersView.vue`
```vue
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Input from '@/components/ui/Input.vue'
import Modal from '@/components/ui/Modal.vue'
import Select from '@/components/ui/Select.vue'
import Table from '@/components/ui/Table.vue'
import Textarea from '@/components/ui/Textarea.vue'
import { showToast } from '@/components/ui/toast'
import { usersApi } from '@/api/users'
import { ApiError } from '@/api/client'
import type { UserOut, UserStatus } from '@/api/types'
import { useResource } from '@/lib/useResource'
import { formatKst, relativeKo } from '@/lib/time'
import { refreshPending } from '../pending'
import { FILTERS, STATUS_BADGE, matchUser, sortUsers } from '../usersView'

const status = ref<UserStatus | ''>('pending_approval')
const q = ref('')
const { data, error, loading, reload } = useResource(() => usersApi.list(status.value || undefined), {
  deps: status,
})
const rows = computed(() => sortUsers((data.value ?? []).filter((x) => matchUser(x, q.value))))
const pendingHere = computed(
  () => (data.value ?? []).filter((x) => x.status === 'pending_approval').length,
)

const COLUMNS = [
  { key: 'name', label: '이름', width: '96px' },
  { key: 'student_no', label: '학번', width: '104px' },
  { key: 'email', label: '웹메일' },
  { key: 'role', label: '역할', width: '72px' },
  { key: 'status', label: '상태', width: '88px' },
  { key: 'created_at', label: '신청', width: '96px' },
  { key: 'approved_at', label: '승인', width: '96px' },
  { key: 'actions', label: '작업', width: '136px' },
]

const emptyMessage = computed(() => {
  if (q.value.trim()) return '검색 결과가 없습니다'
  if (status.value === 'pending_approval') return '승인을 기다리는 신청이 없습니다' // 평소 상태 — 버튼 없음
  if (status.value === '') return '아직 가입한 회원이 없습니다. 학생 웹 주소에서 가입 신청을 받습니다.'
  return '해당하는 회원이 없습니다'
})

// 목록 오류 — 401·403 은 client 가 로그인으로 보낸다
watch(error, (e) => {
  if (e && e.status !== 401 && e.status !== 403)
    showToast({ tone: 'danger', message: e.message, action: { label: '재시도', onClick: reload } })
})

type Kind = 'approve' | 'reject' | 'disable' | 'enable'
const OK: Record<Kind, string> = {
  // 메일은 응답을 기다리지 않는다 — 발송을 보장하는 문구로 쓰지 않는다
  approve: '승인했습니다. 학생에게 메일이 갑니다.',
  reject: '거절했습니다. 학생에게 메일이 갑니다.',
  disable: '정지했습니다.',
  enable: '해제했습니다.',
}
const CHANGED: Record<Kind, string> = {
  approve: '이미 처리된 신청입니다',
  reject: '이미 처리된 신청입니다',
  disable: '상태가 이미 바뀌었습니다. 목록을 새로 불러옵니다.',
  enable: '상태가 이미 바뀌었습니다. 목록을 새로 불러옵니다.',
}
const busy = ref<string | null>(null) // 처리 중인 행 — 연타 방지

async function act(user: UserOut, kind: Kind, call: () => Promise<unknown>): Promise<boolean> {
  if (busy.value) return false
  busy.value = user.email
  try {
    await call()
    showToast({ message: OK[kind] })
    return true
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 409 || e.status === 404) showToast({ message: CHANGED[kind] })
    else if (e.status !== 401 && e.status !== 403)
      showToast({
        tone: 'danger',
        message: e.message,
        action: { label: '재시도', onClick: () => void act(user, kind, call) },
      })
    return e.status === 409 || e.status === 404 // 모달은 닫는다 — 대상이 이미 바뀌었다
  } finally {
    busy.value = null
    await Promise.all([reload(), refreshPending()])
  }
}

// 거절 — 사유가 학생에게 메일로 그대로 간다 (Modal 필수)
const rejecting = ref<UserOut | null>(null)
const reason = ref('')
function openReject(user: UserOut) {
  reason.value = ''
  rejecting.value = user
}
async function submitReject() {
  const user = rejecting.value
  const r = reason.value.trim()
  if (!user || !r) return
  if (await act(user, 'reject', () => usersApi.reject(user.email, r))) rejecting.value = null
}

// 정지 — token_version 이 올라 그 사람의 세션이 즉시 끊긴다
const disabling = ref<UserOut | null>(null)
async function submitDisable() {
  const user = disabling.value
  if (!user) return
  if (await act(user, 'disable', () => usersApi.disable(user.email))) disabling.value = null
}

const asUser = (row: Record<string, unknown>) => row as unknown as UserOut
</script>

<template>
  <main class="users">
    <header class="users__head">
      <h1 class="users__title">회원</h1>
      <Badge v-if="status === 'pending_approval'" variant="solid" size="sm" class="num"
        >승인 대기 {{ pendingHere }}</Badge
      >
      <Select v-model="status" :options="FILTERS" size="sm" class="users__filter" />
      <Input v-model="q" size="sm" placeholder="이름·학번·메일 검색" aria-label="회원 검색" class="users__search" />
    </header>

    <Table
      :columns="COLUMNS"
      :rows="rows as unknown as Record<string, unknown>[]"
      row-key="email"
      :loading="loading && !data"
    >
      <template #empty>
        <EmptyState :message="emptyMessage" />
      </template>
      <template #cell-student_no="{ row }">{{ asUser(row).student_no ?? '—' }}</template>
      <template #cell-role="{ row }">
        <Badge variant="outline">{{ asUser(row).role === 'admin' ? '관리자' : '학생' }}</Badge>
      </template>
      <template #cell-status="{ row }">
        <Badge
          :tone="STATUS_BADGE[asUser(row).status].tone"
          :variant="STATUS_BADGE[asUser(row).status].variant"
          >{{ STATUS_BADGE[asUser(row).status].label }}</Badge
        >
      </template>
      <template #cell-created_at="{ row }">
        <span v-if="asUser(row).role === 'admin'">—</span>
        <span v-else :title="formatKst(asUser(row).created_at)">{{
          relativeKo(asUser(row).created_at)
        }}</span>
      </template>
      <template #cell-approved_at="{ row }">
        <span v-if="asUser(row).approved_at" :title="formatKst(asUser(row).approved_at!)">{{
          relativeKo(asUser(row).approved_at!)
        }}</span>
        <span v-else>—</span>
      </template>
      <template #cell-actions="{ row }">
        <span v-if="asUser(row).role === 'admin'" class="users__cli">CLI 에서만 변경</span>
        <div v-else class="users__actions">
          <template v-if="asUser(row).status === 'pending_approval'">
            <Button
              size="sm"
              :loading="busy === asUser(row).email"
              :disabled="!!busy && busy !== asUser(row).email"
              @click="act(asUser(row), 'approve', () => usersApi.approve(asUser(row).email))"
              >승인</Button
            >
            <Button variant="ghost" size="sm" :disabled="!!busy" @click="openReject(asUser(row))"
              >거절</Button
            >
          </template>
          <Button
            v-else-if="asUser(row).status === 'active'"
            variant="ghost"
            size="sm"
            :disabled="!!busy"
            @click="disabling = asUser(row)"
            >정지</Button
          >
          <Button
            v-else-if="asUser(row).status === 'disabled'"
            variant="ghost"
            size="sm"
            :loading="busy === asUser(row).email"
            :disabled="!!busy && busy !== asUser(row).email"
            @click="act(asUser(row), 'enable', () => usersApi.enable(asUser(row).email))"
            >해제</Button
          >
        </div>
      </template>
    </Table>

    <Modal
      :open="!!rejecting"
      title="가입 신청 거절"
      size="sm"
      :close-on-backdrop="!reason"
      @close="rejecting = null"
    >
      <p class="users__modal-text">
        {{ rejecting?.name }} ({{ rejecting?.email }}) 의 신청을 거절합니다. 사유는 학생에게 메일로
        그대로 갑니다.
      </p>
      <Textarea
        v-model="reason"
        label="거절 사유"
        placeholder="학번이 잘못되었습니다"
        maxlength="200"
        rows="3"
        required
      />
      <template #footer>
        <Button variant="secondary" @click="rejecting = null">취소</Button>
        <Button
          variant="danger"
          :loading="busy === rejecting?.email"
          :disabled="!reason.trim()"
          @click="submitReject"
          >거절</Button
        >
      </template>
    </Modal>

    <Modal :open="!!disabling" title="회원 정지" size="sm" @close="disabling = null">
      <p class="users__modal-text">
        {{ disabling?.name }} ({{ disabling?.email }}) 을 정지합니다. 이 사람의 로그인이 즉시
        끊깁니다.
      </p>
      <template #footer>
        <Button variant="secondary" @click="disabling = null">취소</Button>
        <Button variant="danger" :loading="busy === disabling?.email" @click="submitDisable"
          >정지</Button
        >
      </template>
    </Modal>
  </main>
</template>

<style scoped>
.users {
  padding: var(--space-5);
}
.users__head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}
.users__title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
}
.users__search {
  width: 220px;
  margin-left: auto;
}
.users__actions {
  display: flex;
  gap: var(--space-1);
}
.users__cli {
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.users__modal-text {
  margin: 0 0 var(--space-4);
}
</style>
```
`act` 는 `finally` 에서 목록과 대기 건수를 둘 다 다시 부른다 — 성공·409·오류 어느 쪽이든 화면이 서버 상태를 따라간다. 테스트의 `api.list` 호출 횟수(처음 1 + 새로고침 1)는 이것이 만든다.

- [ ] **Step 4: 단위 통과 확인**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint && pnpm exec prettier --check .`
Expected: PASS

- [ ] **Step 5: E2E — 회원 승인**

`web/e2e/admin-users.spec.ts`
```ts
import { expect, test, type Page } from '@playwright/test'
import { SIZES, apiLogin, cli, createStudent, fillLogin, nextAdmin, shot } from './helpers'

test.use({ viewport: SIZES.admin })

async function openUsers(page: Page, admin = nextAdmin()) {
  await page.goto('/admin/users')
  await fillLogin(page, admin)
  await expect(page).toHaveURL(/\/admin\/users$/)
  return admin
}
const row = (page: Page, email: string) => page.getByRole('row').filter({ hasText: email })

test('승인 — 확인 없이 바로, 대기 목록에서 빠진다', async ({ page, request }) => {
  const a = await createStudent(request, { name: '김민준' })
  const b = await createStudent(request, { name: '박서연' })
  await openUsers(page)
  await expect(row(page, a.email)).toContainText('대기중')
  await expect(row(page, b.email)).toBeVisible()
  await shot(page, 'admin-users-1440')
  await row(page, a.email).getByRole('button', { name: '승인' }).click()
  await expect(page.getByText('승인했습니다. 학생에게 메일이 갑니다.')).toBeVisible()
  await expect(row(page, a.email)).toHaveCount(0)
})

test('거절 — 사유 필수, 거절 필터에 거절됨', async ({ page, request }) => {
  const s = await createStudent(request)
  await openUsers(page)
  await row(page, s.email).getByRole('button', { name: '거절' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('button', { name: '거절' })).toBeDisabled()
  await dialog.getByLabel('거절 사유').fill('학번이 잘못되었습니다')
  await shot(page, 'admin-users-reject-1440')
  await dialog.getByRole('button', { name: '거절' }).click()
  await expect(page.getByText('거절했습니다. 학생에게 메일이 갑니다.')).toBeVisible()
  await page.getByRole('combobox').selectOption({ label: '거절' })
  await expect(row(page, s.email)).toContainText('거절됨')
})

test('정지 → 해제', async ({ page, request }) => {
  const s = await createStudent(request, { approve: true })
  await openUsers(page)
  await page.getByRole('combobox').selectOption({ label: '활성' })
  await row(page, s.email).getByRole('button', { name: '정지' }).click()
  await expect(page.getByRole('dialog')).toContainText('로그인이 즉시 끊깁니다')
  await page.getByRole('dialog').getByRole('button', { name: '정지' }).click()
  await expect(page.getByText('정지했습니다.')).toBeVisible()
  await page.getByRole('combobox').selectOption({ label: '정지' })
  await expect(row(page, s.email)).toContainText('정지됨')
  await row(page, s.email).getByRole('button', { name: '해제' }).click()
  await expect(page.getByText('해제했습니다.')).toBeVisible()
  await expect(row(page, s.email)).toHaveCount(0)
})

test('다른 곳에서 먼저 승인 → 409 안내 + 새로고침 (Review Focus 4)', async ({ page, request }) => {
  const s = await createStudent(request)
  await openUsers(page)
  await expect(row(page, s.email)).toBeVisible()
  const t = await apiLogin(request, nextAdmin())
  await request.post(`/api/admin/users/${encodeURIComponent(s.email)}/approve`, {
    headers: { authorization: `Bearer ${t}` },
  })
  await row(page, s.email).getByRole('button', { name: '승인' }).click()
  await expect(page.getByText('이미 처리된 신청입니다')).toBeVisible()
  await expect(row(page, s.email)).toHaveCount(0)
})

test('세션이 무효가 되면 로그인으로, 다시 로그인하면 같은 화면', async ({ page }) => {
  const admin = await openUsers(page)
  // 관리자 token_version 을 올린다 — 비밀번호 재설정·정지와 같은 효과 (S4a)
  cli(['set-user', '--email', admin, '--status', 'active'])
  await page.getByRole('combobox').selectOption({ label: '전체' })
  await expect(page).toHaveURL(/\/admin\/login\?next=/)
  await expect(page.getByText('다시 로그인해 주세요.')).toBeVisible()
  await shot(page, 'admin-relogin-1440')
  await fillLogin(page, admin)
  await expect(page).toHaveURL(/\/admin\/users$/)
})
```
로그인 상한 메모: 서버는 IP 당 분당 30회도 센다. 전체 E2E(로그인·인증·셸·회원)의 로그인은 25회 안쪽이다. 뒤 plan 에서 테스트를 더해 넘기면, 파일 안에서 `apiLogin` 토큰을 한 번 받아 재사용해 횟수를 줄인다.

- [ ] **Step 6: E2E 전체 실행 + 스크린샷 대조**

Run: `cd web && pnpm e2e`
Expected: 로그인 5 + 인증 5 + 셸 2 + 회원 5 = 17 passed. `admin-users-1440.png` 를 `admin-users.md` 와 대조:
- 상단 `회원` 제목 · `승인 대기 N` 배지 · 상태 Select · 검색 Input 한 줄.
- 컬럼 폭(이름 96 · 학번 104 · 역할 72 · 상태 88 · 신청 96 · 승인 96 · 작업 136), 행 높이 32, 세로 구분선 없음, 헤더 `sunken` + 아래 2px.
- 대기중·거절됨 무채색, 정지됨만 적색. `승인` 은 `primary`, `거절` 은 `ghost`.
- `admin-users-reject-1440.png`: 배경 딤(블러 없음), 패널 폭 400, 푸터 `취소`(secondary) + `거절`(danger).
어긋나면 고치고 다시 찍는다.

- [ ] **Step 7: 커밋**

```bash
git add -A web
git commit -m "feat(web): 관리자 회원 승인 화면 — 대기 우선 정렬·검색, 승인(확인 없음)·거절(사유 필수)·정지(확인)·해제, 409 새로고침 + E2E"
```

---

### Task 14: 거절 사유 툴팁 — 서버 A1 머지 뒤에만

**선행 조건:** 서버 additive **A1**(`UserOut.reject_reason: str | None`, 관리자 목록에서 채움)이 main 에 머지돼 있어야 한다(spec §6, `web/CLAUDE.md` — 서버가 아직 안 만든 필드를 가정하고 화면을 만들지 않는다). 머지 전이면 이 Task 를 건너뛰고 PR 본문에 "A1 대기 — 거절 사유 표시 없음"을 적는다. Task 1~13 만으로 화면은 끝까지 동작한다.

**Files:**
- Modify: `web/src/api/types.ts`, `web/src/api/__fixtures__/users.json`, `web/src/admin/views/UsersView.vue`
- Test: `web/src/admin/__tests__/users.spec.ts`

**Interfaces:**
- Produces: `UserOut.reject_reason: string | null`

- [ ] **Step 1: 서버 응답에 필드가 있는지 확인**

```bash
cd server && git log origin/main --oneline -- app/schemas.py | head -3
grep -n "reject_reason" app/schemas.py
```
Expected: `class UserOut` 안에 `reject_reason: str | None`. 없으면 여기서 멈춘다.

- [ ] **Step 2: 실패 테스트** — `users.spec.ts` 의 `describe('UsersView')` 에 추가

```ts
  it('거절됨 배지에 사유 툴팁', async () => {
    api.list.mockResolvedValue([u({ status: 'rejected', reject_reason: '학번이 잘못되었습니다' })])
    const w = await mountView()
    expect(w.get('.badge').attributes('title')).toBe('학번이 잘못되었습니다')
  })
```
`u()` 기본값에 `reject_reason: null` 을 더한다. `users.json` 픽스처 두 항목에도 `"reject_reason": null`.

Run: `cd web && pnpm test src/admin/__tests__/users.spec.ts`
Expected: FAIL — `title` 이 `undefined`

- [ ] **Step 3: 구현**

`web/src/api/types.ts` 의 `UserOut` 에 `reject_reason: string | null` 추가.
`UsersView.vue` 의 상태 셀:
```vue
      <template #cell-status="{ row }">
        <Badge
          :tone="STATUS_BADGE[asUser(row).status].tone"
          :variant="STATUS_BADGE[asUser(row).status].variant"
          :title="asUser(row).status === 'rejected' ? (asUser(row).reject_reason ?? undefined) : undefined"
          >{{ STATUS_BADGE[asUser(row).status].label }}</Badge
        >
      </template>
```
(`Badge` 는 `inheritAttrs` 기본값이라 `title` 이 루트 `<span>` 에 붙는다.)

- [ ] **Step 4: 통과 + E2E 한 줄**

`e2e/admin-users.spec.ts` 의 거절 테스트 끝에:
```ts
  await expect(row(page, s.email).getByText('거절됨')).toHaveAttribute('title', '학번이 잘못되었습니다')
```
Run: `cd web && pnpm test && pnpm typecheck && pnpm e2e e2e/admin-users.spec.ts`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add web/src web/e2e
git commit -m "feat(web): 회원 목록 거절됨 배지에 거절 사유 툴팁 (서버 A1)"
```

---

## PR 체크리스트 (F1 완료 시)

- 브랜치 `feature/web-f1` → `main`. 제목 `feat(web): F1 기반·인증·회원 승인 — 앱 2개, 토큰·ui 15종, API·세션 계층, 인증 화면, 회원 승인`.
- 본문에 붙일 것: `pnpm test`·`pnpm lint`·`pnpm typecheck`·`pnpm build` 결과, `pnpm e2e` 결과(17 passed, Task 14 포함 시 그대로), 스크린샷(관리자 1440 × 5, 학생 390 × 8), 폰트 서브셋 실제 크기.
- mh 에 확인 요청(CODEOWNERS `styles/`·`components/ui/`): Badge 표에 없는 조합(기본 `tint+neutral`, `brand` tone), SidebarNav `badge` 필드, 가입 429 문구 하나로 통일, 폰트 서브셋 범위·크기.
- cw 에 알림: `.github/workflows/ci.yml` web job `vue-tsc --noEmit` → `--build`(지금은 타입 검사가 돌지 않는다).
- E2E 는 로컬 필수(CI 편입은 #44 머지 뒤, spec §7.3).
