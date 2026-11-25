# 관리자 AI 비서 — 화면 스펙(cw) · 웹(wj) 구현 계획 (plan 03)

<!-- writing-plans 스킬로 작성. spec §7·§11·§13 과 공통 부록을 웹 Task 로 옮긴 작업지시서 -->

- 생성일시: 2026-11-25
- 기준 spec: `docs/specs/2026-11-25-admin-ai-assistant-design.md` (§7 웹, §11 오류 처리, §13 테스트)
- 공통 부록: `docs/plans/2026-11-25-ai-assistant-00-interfaces.md` (§2 프롬프트 조립, §4 HTTP API — **모양 그대로 쓴다**)
- 함께 도는 계획: `2026-11-25-ai-assistant-01-proto-backend.md`(cw), `2026-11-25-ai-assistant-02-finetune.md`(wj)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 관리자 웹 사이드바 맨 위 "AI 비서" 탭에서, 브라우저 안의 파인튜닝 모델이 관리자 문장을 양식으로 옮기고 서버가 되묻기·미리보기를 돌려주면, 기존│수정 주간표를 나란히 보여 준 뒤 [적용]으로 반영한다.

> **화면 변경(2026-11-26, #176)**: 화면은 머지된 `docs/design/screens/admin-assistant.md` 가 원본이다 — **상단 명령창**(사이드바 `AI 비서` 버튼·`Ctrl K` 로 보던 화면 위에 여는 창, 라우트 없음) + **펼친 확인 창**(왼쪽 요약·하루 막대, 오른쪽 격자 하나 + `기존 | 수정` 전환). 아래 Task 5·7·8·10·13 의 화면 코드는 처음 초안(별도 화면 `/assistant` · 대화 열 · 두 격자 · 탭) 기준이라 각 Task 머리의 「화면 변경」 블록대로 바꿔 만든다. 로직·상태·API 코드는 그대로다.
> 진행: Task 0 완료 #176 · Task 1 완료 #177 · Task 2 완료 #174 · Task 3·4 = #175 (Draft, 01 PR B 머지 뒤 머지).

**Architecture:** 화면 스펙(`docs/design/`, cw)을 먼저 머지하고 웹이 따라간다. 모델은 Web Worker 안의 실행 도구 어댑터(`ModelRunner`)가 돌리고, 화면은 서버 계약(`/api/assistant/*`)만 소비한다. 전·후 비교는 기존 주간 시간표의 격자를 `WeekGrid` 로 뽑아(표적 리팩터) 두 번 그린다. 모델 파일은 Hugging Face 에서 처음 한 번 받아 SHA-256 검증 후 Cache API 에 둔다. 0단계 실험(02 계획) 결과가 나오기 전에는 개발용 대역(`StubRunner`)으로 전 흐름을 만든다.

**Tech Stack:** Vue 3 + TypeScript (Vite, pnpm), Vitest + @vue/test-utils(jsdom), Playwright E2E. 새 의존성: `hash-wasm`(스트리밍 SHA-256, Task 11), `@mlc-ai/web-llm`(기본 가정 실행 도구, Task 12 — 0단계 결과로 바뀔 수 있음).

## Global Constraints

- 웹 규칙은 `web/CLAUDE.md` 그대로: 서버 응답 타입은 `src/api/` 에 한 번만 선언, 화면은 `components/ui/` 를 조합, 서버 응답을 프론트에서 변환·보정하지 않는다(날짜 문자열 → `Date` 변환만 기존 `request` 규칙대로).
- **토큰 우회 하드코딩 금지** — `.vue` 의 `<style>`·`<template>` 에 원시 팔레트(`--gray-*` 등)·16진 색을 쓰지 않는다(`src/styles/__tests__/tokens.guard.spec.ts`). 새 색은 Task 0(스펙) → Task 1(`tokens.css`) 순서로만 생긴다.
- **스펙 먼저 머지, 코드는 따라간다(lockstep).** 디자인 스펙 작성자는 이제 **cw**(mh 팀 제외, 2026-11-25). 새 아이콘·컴포넌트·토큰은 Task 0 PR 이 머지된 뒤에만 코드로 만든다.
- **서버 additive 머지가 먼저다** — `/api/assistant/*` 를 실제로 부르는 PR(δ)은 01 계획의 **PR B(서버 API)** 가 머지된 뒤 머지한다. 그 전에는 `fetch` 가짜(vitest `vi.stubGlobal('fetch')`·`vi.mock('@/api/assistant')`)로 개발한다.
- **02 계획 0단계(실행 도구 실험) 결과 전에는 개발용 대역(`StubRunner`)** 으로만 대화가 돈다. 실제 실행 도구 어댑터(Task 12)는 그 결과로 고른다.
- **모델은 처음엔 받지 않는다** — "AI 모델 받기" 버튼을 눌러야 받는다. `prefetchViews()` 는 화면 **코드 청크**만 받는다. 실행 도구 라이브러리(`@mlc-ai/web-llm`)는 Worker 안에서 **동적 import** 로만 불러 화면 청크에 들어가지 않는다.
- 모델 파일 URL 은 **커밋 해시로 고정한 판**: `https://huggingface.co/${repo}/resolve/${revision}/${name}`. 판이 바뀌면 옛 판 파일을 지운다.
- 적용은 **[적용] 버튼으로만** — 채팅 글로 적용하지 않는다. 막음(`blockers`)이 있으면 버튼 비활성.
- 화면은 모델·서버가 준 글을 **글자로만** 표시한다(`v-html` 금지).
- 관리자 화면은 데스크톱 전용(≥ 1024px, `docs/design/README.md`). (처음 초안의 "1024~1279px 에서 확인 화면이 대화 위를 덮는다"는 #176 에서 없어졌다 — 확인은 늘 펼친 창 하나다.)
- 커밋: Conventional Commits(`feat(web):`·`style(web):`·`refactor(web):`·`docs(design):`), attribution 줄 없음, `git add` 는 정확한 파일만. `main` 직접 push·force push 금지. 머지는 팀장(cw)만.
- 게이트: `pnpm test && pnpm lint && pnpm exec vue-tsc --noEmit` (web/ 에서).

## PR 경계

| PR | Task | 담당 | 제목 | 선행 |
|---|---|---|---|---|
| α | 0 | wj 시안 · cw 승인 | `docs(design): AI 비서 화면 스펙 — 상단 명령창·펼친 확인 창·모델 받기, diff 토큰, 사이드바 버튼 항목` | **머지 #176** |
| β | 1 | wj | `style(web): diff 토큰 · ProgressBar · 사이드바 AI 비서 아이콘 · 버튼 항목(action)` | **머지 #177** |
| γ | 2 | wj | `refactor(web): 주간 시간표 격자를 WeekGrid 로 분리 (동작 불변)` | **머지 #174** |
| δ | 3–10 | wj | `feat(web): AI 비서 — 명령창·확인 창·적용·변경 기록 (개발용 대역)` (Task 3·4 는 #175 Draft 로 먼저) | β, γ, **01 PR B 머지** |
| ε | 11–14 | wj | `feat(web): AI 비서 모델 받기·검증·WebLLM 실행, CSP` | δ, **02 0단계 결과** |

δ 가 운영에 나가도 서버의 모델 안내가 `{"enabled": false}` 인 동안 창은 "준비 중"만 보인다 — 안전하다.

## 파일 구조

```
docs/design/screens/admin-assistant.md        (새, Task 0 — 머지 #176)
docs/design/tokens.md · components.md · screens/admin-master.md   (수정, Task 0 — 머지 #176)

web/src/styles/tokens.css                      (수정, Task 1 — green·amber·diff.*)
web/src/styles/__tests__/tokens.guard.spec.ts  (수정, Task 1 — green·amber 도 원시로)
web/src/components/ui/ProgressBar.vue          (새, Task 1)
web/src/components/ui/SidebarNav.vue           (수정, Task 1 — assistant 아이콘, `action` 버튼 항목 · `shortcut`)

web/src/admin/views/week/WeekGrid.vue          (새, Task 2 — WeekView 의 격자)
web/src/admin/views/WeekView.vue               (수정, Task 2)

web/src/api/types.ts · assistant.ts            (Task 3)
web/src/api/__fixtures__/assistant-*.json      (Task 3)

web/src/admin/assistant/                       ← 화면이 아닌 로직 (테스트는 순수 함수·모듈 상태로)
├── prompt.ts          사용자 메시지 조립 · 모델 출력 parse            (Task 4)
├── runner.ts          ModelRunner · Worker 메시지 · WorkerRunner       (Task 4)
├── workerCore.ts      Worker 안 메시지 처리(테스트 가능)              (Task 4)
├── worker.ts          Worker 진입점 — workerCore 를 self 에 잇기만    (Task 4, Task 12 수정)
├── adapters/stub.ts   개발용 대역                                     (Task 4)
├── adapters/webllmFiles.ts  WebLLM 파일 → Cache 이름(순수)             (Task 11)
├── adapters/webllm.ts WebLLM 어댑터 (Worker 안에서만 import)           (Task 12)
├── model.ts           모델 상태(모듈) — 안내·기기 점검·받기·불러오기   (Task 5, Task 11 확장)
├── capability.ts      WebGPU·메모리·저장 공간 점검                     (Task 11)
├── modelStore.ts      HF 다운로드 · SHA-256 · Cache API · 옛 판 삭제   (Task 11)
├── conversation.ts    대화 상태(모듈) — 턴·선택·적용                   (Task 6, Task 9 확장)
└── diff.ts            미리보기 changes → 블록 표시                     (Task 8)

web/src/admin/views/assistant/AssistantPanel.vue  (Task 5, 7, 8, 10 — 창 껍데기. 처음 초안의 AssistantView.vue 자리)
web/src/admin/views/assistant/ModelGate.vue · CommandBar.vue · ConfirmPanel.vue · ChangeLog.vue
                                               (CommandBar = 처음 초안 ChatPane, ConfirmPanel = PreviewPane. Examples.vue 없음)
web/src/admin/AdminShell.vue                   (Task 5 — 창 한 번 마운트 · 사이드바 action · Ctrl K. 라우트 없음)
web/security-headers-admin.conf · nginx.conf · Dockerfile   (Task 12 — 관리자 앱만 넓힌 CSP)
web/e2e/admin-assistant.spec.ts                (Task 13)
```

---

### Task 0: 화면 스펙 — `admin-assistant.md`, diff 토큰, 사이드바 아이콘·버튼 항목, 메뉴 순서 — 완료 #176 (wj 시안, cw 승인 2026-11-26)

머지된 `docs/design/screens/admin-assistant.md`(와 `tokens.md` · `components.md` · `screens/admin-master.md` · `README.md`)가 원본이다. 이 자리에 있던 초안 전문은 지웠다. 초안에서 바뀐 것:

| | 처음 초안 | 머지본 (#176) |
|---|---|---|
| 진입 | `/admin/assistant` 라우트(사이드바 링크) | 사이드바 `AI 비서` **버튼**(`SidebarNav` `action` 항목) · `Ctrl K`(macOS `⌘K`). **라우트 없음** — 보던 화면 위에 창이 열린다(덮개는 본문만, 사이드바는 안 덮음) |
| 입력 | 대화 열 380px(말풍선) | 상단 **한 줄 명령창**(56px, 300자) + 되묻기 칸(질문 · 선택 버튼 또는 답 입력 · `요청 취소`) |
| 확인 | 기존│수정 격자 둘 나란히 | **펼친 창**: 왼쪽 340px 요약·막음·경고·안내·하루 막대(`기존`/`수정`, 최대 3일 + `외 N일`, 강의실 여럿이면 강의실 표), 오른쪽 격자 하나 + `기존 \| 수정` `SegmentedControl`(같은 시각 범위) · 아래 줄 `[취소]` `[적용]` |
| 대화 기록 | 화면에 말풍선으로 남음 | **화면에 안 남는다** — 다시 열면 빈 명령창 |
| 변경 기록 | 확인 열 `확인 \| 변경 기록` 탭 | 명령창 머리 줄 `변경 기록` 버튼 → 아래로 펼치는 칸 |
| 예문 · 좁은 화면 | 확인 열 빈 상태 예문, 1024~1279px 덮개 | 없음 |

- 대비 값 정정: `diff.add.text`(`green.50` 위) **5.40**, `diff.change.text`(`amber.50` 위) **5.20** (초안 5.48 · 5.22).
- 토큰 이름(`diff.*`, `green.50/700`, `amber.50/700`)·`ProgressBar` props·`assistant` 아이콘 path 는 초안 그대로다. 여기에 `SidebarNav` 항목 `{ to?, action?, label, group?, icon?, badge?, shortcut? }`(`to` 또는 `action` 하나)가 더해졌다 — Task 1 이 구현.

---

### Task 1: diff 토큰 · ProgressBar · 사이드바 AI 비서 아이콘 (`style(web)`) — 완료 #177

> 선행: Task 0(PR α) 머지.
> **완료 #177**: 아래에 더해 `SidebarNav` 의 `action` 버튼 항목(`<button>` + `aria-expanded`, 열림 활성 모양)과 `shortcut` 표시도 넣었다(`components.md` SidebarNav). Task 5 가 이것을 쓴다.

**Files:**
- Modify: `web/src/styles/tokens.css`
- Modify: `web/src/styles/__tests__/tokens.guard.spec.ts:5`
- Modify: `web/src/styles/__tests__/tokens.spec.ts` (2층 테스트에 diff 줄)
- Create: `web/src/components/ui/ProgressBar.vue`
- Modify: `web/src/components/ui/SidebarNav.vue:6-21`
- Test: `web/src/components/ui/__tests__/basic.spec.ts` (ProgressBar), `web/src/components/ui/__tests__/nav.spec.ts` (아이콘)

**Interfaces:**
- Produces: CSS 변수 `--diff-add-fill` `--diff-add-line` `--diff-add-text` `--diff-remove-fill` `--diff-remove-line` `--diff-remove-text` `--diff-change-fill` `--diff-change-line` `--diff-change-text`; `ProgressBar.vue` props `{ value: number; max: number; label: string }`; `NavIcon` 에 `'assistant'`.

- [ ] **Step 1: 실패하는 테스트**

`web/src/styles/__tests__/tokens.spec.ts` 의 `it('2층은 1층을 가리킨다 …')` 안 끝에 추가:

```ts
    expect(cssVar(tokens, 'diff-add-line')).toBe('var(--green-700)')
    expect(cssVar(tokens, 'diff-remove-line')).toBe('var(--red-700)')
    expect(cssVar(tokens, 'diff-change-fill')).toBe('var(--amber-50)')
```

`web/src/components/ui/__tests__/basic.spec.ts` 끝에 추가(파일 위 import 에 `ProgressBar` 추가):

```ts
import ProgressBar from '@/components/ui/ProgressBar.vue'

describe('ProgressBar', () => {
  it('progressbar 역할 · 값 · 이름, 채움 폭은 비율 (0~100% 로 자른다)', () => {
    const w = mount(ProgressBar, { props: { value: 3, max: 4, label: 'AI 모델 받는 중' } })
    const bar = w.get('[role="progressbar"]')
    expect(bar.attributes('aria-valuenow')).toBe('3')
    expect(bar.attributes('aria-valuemax')).toBe('4')
    expect(bar.attributes('aria-label')).toBe('AI 모델 받는 중')
    expect(w.get('.progress__fill').attributes('style')).toContain('width: 75%')
    const over = mount(ProgressBar, { props: { value: 9, max: 4, label: 'x' } })
    expect(over.get('.progress__fill').attributes('style')).toContain('width: 100%')
    const zero = mount(ProgressBar, { props: { value: 0, max: 0, label: 'x' } })
    expect(zero.get('.progress__fill').attributes('style')).toContain('width: 0%')
  })
})
```

`web/src/components/ui/__tests__/nav.spec.ts` 의 `describe('SidebarNav'` 안에 추가:

```ts
  it('AI 비서 아이콘 — assistant 값이 path 를 그린다', async () => {
    const router = await withRouter('/nodes')
    const w = mount(SidebarNav, {
      props: { items: [{ to: '/nodes', label: 'AI 비서', group: 'AI', icon: 'assistant' }] },
      global: { plugins: [router] },
    })
    expect(w.get('a svg.nav__icon path').attributes('d')).toMatch(/^M12 3l1\.8 4\.7/)
  })
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/styles src/components/ui/__tests__/basic.spec.ts src/components/ui/__tests__/nav.spec.ts`
Expected: FAIL — `diff-add-line` undefined, `ProgressBar.vue` 없음, `assistant` 아이콘 path 없음, 그리고 `tokens.spec` 1층 비교(`green.700` 등)가 실패.

- [ ] **Step 3: `tokens.css`**

1층 팔레트(`--gold-600: #ca8a04;` 다음 줄)에:

```css
  --green-700: #067647;
  --green-50: #ecfdf3;
  --amber-700: #b54708;
  --amber-50: #fffaeb;
```

3층(`--room-free-line: var(--line-3);` 다음 줄)에:

```css
  /* AI 비서 확인 화면 — 변경 표시 (tokens.md diff.*). 블록 바탕은 room.* 그대로, 테두리·태그만 */
  --diff-add-fill: var(--green-50);
  --diff-add-line: var(--green-700);
  --diff-add-text: var(--green-700);
  --diff-remove-fill: var(--red-50);
  --diff-remove-line: var(--red-700);
  --diff-remove-text: var(--red-700);
  --diff-change-fill: var(--amber-50);
  --diff-change-line: var(--amber-700);
  --diff-change-text: var(--amber-700);
```

`web/src/styles/__tests__/tokens.guard.spec.ts` 5행:

```ts
const PRIMITIVE = /--(gray|blue|red|teal|gold|green|amber)-\d/
```

- [ ] **Step 4: `ProgressBar.vue`**

```vue
<script setup lang="ts">
import { computed } from 'vue'

// components.md ProgressBar — 퍼센트 글자는 화면이 옆에 적는다
const props = defineProps<{ value: number; max: number; label: string }>()
const pct = computed(() =>
  props.max > 0 ? Math.min(100, Math.max(0, (props.value / props.max) * 100)) : 0,
)
</script>

<template>
  <div
    class="progress"
    role="progressbar"
    :aria-valuenow="value"
    aria-valuemin="0"
    :aria-valuemax="max"
    :aria-label="label"
  >
    <div class="progress__fill" :style="{ width: `${pct}%` }" />
  </div>
</template>

<style scoped>
.progress {
  height: 8px;
  overflow: hidden;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-full);
  background: var(--sunken);
}
.progress__fill {
  height: 100%;
  border-radius: var(--radius-full);
  background: var(--brand);
  transition: width 0.2s;
}
</style>
```

- [ ] **Step 5: `SidebarNav.vue` 아이콘**

6행:

```ts
export type NavIcon = 'building' | 'settings' | 'calendar' | 'node' | 'send' | 'users' | 'assistant'
```

`ICONS` 객체 마지막(`users:` 다음)에:

```ts
  assistant: 'M12 3l1.8 4.7 4.7 1.8-4.7 1.8L12 16l-1.8-4.7-4.7-1.8 4.7-1.8ZM18.5 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8Z',
```

- [ ] **Step 6: 통과 + 커밋**

Run: `cd web && pnpm test src/styles src/components/ui` → PASS.

```bash
git add web/src/styles/tokens.css web/src/styles/__tests__/tokens.guard.spec.ts web/src/styles/__tests__/tokens.spec.ts web/src/components/ui/ProgressBar.vue web/src/components/ui/SidebarNav.vue web/src/components/ui/__tests__/basic.spec.ts web/src/components/ui/__tests__/nav.spec.ts
git commit -m "style(web): diff 토큰 · ProgressBar · 사이드바 AI 비서 아이콘"
```

PR β 를 연다(α 바로 뒤 머지).

---

### Task 2: 주간 격자를 `WeekGrid` 로 분리 — 표적 리팩터 (동작 불변) — 완료 #174

**Files:**
- Create: `web/src/admin/views/week/WeekGrid.vue`
- Modify: `web/src/admin/views/WeekView.vue` (script 일부 · 격자 template · 격자 style 이동)
- Test: `web/src/admin/__tests__/weekGrid.spec.ts` (새), `web/src/admin/__tests__/week.spec.ts` (**고치지 않고** 통과해야 함)

**Interfaces:**
- Consumes: `web/src/admin/weekView.ts` — `Block`, `Placed`, `ROW_PX`, `blockBox`, `examDates`, `gridRange`, `layoutDay`, `timeRows` (그대로).
- Produces: `WeekGrid.vue`
  - props `{ blocks: Block[]; exams: ExamOut[]; monday: string; night: boolean; weekend: boolean; rangeBlocks?: Block[]; editable?: boolean; clickable?: (p: Placed) => boolean; blockTitle?: (p: Placed) => string | undefined; failed?: (p: Placed) => boolean }`
  - emits `cell: [{ day: number; t: number }]`, `block: [Placed]`
  - slots `dot({ p })`, `overlay()`
  - Task 8 이 `showDates`·`cells`·`mark`·`examMark` 를 더한다.

- [ ] **Step 1: 실패하는 테스트 `web/src/admin/__tests__/weekGrid.spec.ts`**

```ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import WeekGrid from '@/admin/views/week/WeekGrid.vue'
import { weekBlocks } from '@/admin/weekView'
import type { ResvWithRoom, SlotWithRoom } from '@/api/types'

const S = (o: Partial<SlotWithRoom> = {}): SlotWithRoom => ({
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
const V = (o: Partial<ResvWithRoom> = {}): ResvWithRoom => ({
  id: 7,
  room_id: 11,
  date: '2026-09-23',
  s_h: 13,
  s_m: 0,
  e_h: 15,
  e_m: 0,
  type: 5,
  subject: '특강',
  professor: '학생처',
  status: 'approved',
  requester: null,
  pushed_at: null,
  checked_in_at: null,
  checked_out_at: null,
  reject_reason: null,
  ...o,
})
const MON = '2026-09-21'
const mk = (props: Record<string, unknown> = {}) =>
  mount(WeekGrid, {
    props: {
      blocks: weekBlocks([S()], [V()], MON),
      exams: [{ id: 3, room_id: 11, date_start: '2026-09-22', date_end: '2026-09-22' }],
      monday: MON,
      night: false,
      weekend: false,
      ...props,
    },
  })

describe('WeekGrid', () => {
  it('블록 두 개 · 라벨 · 시험기간 띠 · 5열', () => {
    const w = mk()
    expect(w.findAll('.wk__head')).toHaveLength(5)
    expect(w.findAll('.wk__block').map((b) => b.get('.wk__label').text())).toEqual([
      '수업중',
      '예약 · 특강',
    ])
    expect(w.findAll('.wk__exam')).toHaveLength(1)
  })

  it('editable 이 아니면 셀이 비활성, editable 이면 셀 클릭이 cell(day, t) 를 낸다', async () => {
    expect(mk().get('.wk__cell').attributes('disabled')).toBeDefined()
    const w = mk({ editable: true })
    await w.get('.wk__cell').trigger('click')
    expect(w.emitted('cell')?.[0]).toEqual([{ day: 1, t: 540 }])
  })

  it('블록 클릭 → block, clickable 이면 button 역할과 이름', async () => {
    const w = mk({ clickable: () => true })
    const b = w.get('.wk__block')
    expect(b.attributes('role')).toBe('button')
    expect(b.attributes('aria-label')).toBe('월 10:00–12:00 수업중 캡스톤디자인')
    await b.trigger('click')
    expect(w.emitted('block')).toHaveLength(1)
  })

  it('failed 면 실패 테두리 클래스, dot 슬롯은 블록마다', () => {
    const w = mount(WeekGrid, {
      props: {
        blocks: weekBlocks([S()], [], MON),
        exams: [],
        monday: MON,
        night: false,
        weekend: false,
        failed: () => true,
      },
      slots: { dot: '<i class="d" />' },
    })
    expect(w.get('.wk__block').classes()).toContain('wk__block--failed')
    expect(w.findAll('.wk__dot .d')).toHaveLength(1)
  })

  it('rangeBlocks 가 있으면 격자 범위를 그것으로 잡는다 (기존│수정 두 격자 맞춤)', () => {
    const early = weekBlocks([S({ s_h: 8, s_m: 0 })], [], MON)
    const w = mk({ rangeBlocks: early })
    expect(w.get('.wk__time').text()).toBe('08:00')
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin/__tests__/weekGrid.spec.ts`
Expected: FAIL — `Failed to resolve import "@/admin/views/week/WeekGrid.vue"`.

- [ ] **Step 3: `web/src/admin/views/week/WeekGrid.vue` (WeekView 의 격자를 옮긴다)**

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { DAYS, TYPE_LABEL } from '@/components/domain/rules'
import type { ExamOut } from '@/api/types'
import { addDays, hm, md } from '@/lib/time'
import {
  ROW_PX,
  blockBox,
  examDates,
  gridRange,
  layoutDay,
  timeRows,
  type Block,
  type Placed,
} from '../../weekView'

// 주간 격자 하나 — 주간 시간표(편집)와 AI 비서 확인 화면(기존│수정, 읽기 전용)이 같이 쓴다 (admin-schedule.md)
const props = withDefaults(
  defineProps<{
    blocks: Block[]
    exams: ExamOut[]
    monday: string
    night: boolean
    weekend: boolean
    /** 세로 범위를 잡을 블록 — 기존│수정 두 격자를 같은 행에 맞출 때 둘을 합쳐 넘긴다 */
    rangeBlocks?: Block[]
    editable?: boolean
    clickable?: (p: Placed) => boolean
    blockTitle?: (p: Placed) => string | undefined
    failed?: (p: Placed) => boolean
  }>(),
  {
    rangeBlocks: undefined,
    editable: false,
    clickable: () => false,
    blockTitle: () => undefined,
    failed: () => false,
  },
)
const emit = defineEmits<{ cell: [at: { day: number; t: number }]; block: [p: Placed] }>()
defineSlots<{ dot?(props: { p: Placed }): unknown; overlay?(): unknown }>()

const clock = (t: number) => hm(Math.floor(t / 60), t % 60)
const range = computed(() => gridRange(props.rangeBlocks ?? props.blocks, props.night))
const rows = computed(() => timeRows(range.value))
const examOn = computed(() => examDates(props.exams, props.monday))
const days = computed(() =>
  Array.from({ length: props.weekend ? 7 : 5 }, (_, i) => {
    const date = addDays(props.monday, i)
    const { placed, overlaps } = layoutDay(props.blocks.filter((b) => b.day === i + 1))
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
function blockClass(p: Placed) {
  const requested = p.resv?.status === 'requested'
  const cancelled = p.slot?.type === 3
  return {
    'wk__block--busy': !requested && !cancelled,
    'wk__block--cancelled': cancelled,
    'wk__block--requested': requested,
    'wk__block--failed': props.failed(p),
    'wk__block--static': !props.clickable(p),
  }
}
// 라벨이 상태를 말한다 — 넷(수업·시험·특강·대여)을 색으로 나누지 않는다
// 연속 교시 블록은 '수업중 · 3교시' (admin-schedule.md)
const periodsOf = (p: Placed) => p.group?.slots.length ?? 1
function blockLabel(p: Placed) {
  if (p.slot) return TYPE_LABEL[p.slot.type] + (periodsOf(p) > 1 ? ` · ${periodsOf(p)}교시` : '')
  return `${p.resv!.status === 'requested' ? '신청' : '예약'} · ${TYPE_LABEL[p.resv!.type]}`
}
/** 스크린리더 이름 — '월 10:00–12:00 수업중 캡스톤디자인' */
const blockName = (p: Placed) =>
  `${DAYS[p.day - 1]} ${clock(p.s)}–${clock(p.e)} ${blockLabel(p)} ${p.slot?.subject ?? p.resv?.subject ?? ''}`.trim()
const who = (p: Placed) =>
  p.slot ? p.slot.professor : (p.resv!.requester?.name ?? p.resv!.professor)
</script>

<template>
  <div class="wk__scroll">
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
          :disabled="!editable"
          :aria-label="`${DAYS[d.day - 1]} ${clock(t)} 시간표 추가`"
          @click="emit('cell', { day: d.day, t })"
        />
        <!-- 자리 하나에 블록과 점이 형제로 선다 — 재전송 버튼을 role=button 블록 안에 넣으면
             스크린리더가 한 덩어리로 읽고, 재전송의 Enter 가 블록까지 올라가 편집을 연다 -->
        <div
          v-for="{ p, box } in d.blocks"
          :key="p.key"
          class="wk__place"
          :style="{
            top: `${box.top}px`,
            height: `${box.height}px`,
            left: `calc(${(p.lane / p.lanes) * 100}% + 4px)`,
            width: `calc(${100 / p.lanes}% - 8px)`,
          }"
        >
          <div
            class="wk__block"
            :class="blockClass(p)"
            :role="clickable(p) ? 'button' : undefined"
            :tabindex="clickable(p) ? 0 : undefined"
            :aria-label="clickable(p) ? blockName(p) : undefined"
            :title="blockTitle(p)"
            @click="emit('block', p)"
            @keydown.enter.self.prevent="emit('block', p)"
            @keydown.space.self.prevent="emit('block', p)"
          >
            <span class="wk__label">{{ blockLabel(p) }}</span>
            <!-- 높이가 모자라면 교수부터 지운다 -->
            <span v-if="box.height >= 40" class="wk__subject">{{
              p.slot?.subject ?? p.resv?.subject
            }}</span>
            <span v-if="box.height >= 80 && who(p)" class="wk__who">{{ who(p) }}</span>
            <span v-if="box.cutEnd" class="wk__cut num">~{{ clock(p.e) }}</span>
          </div>
          <span class="wk__dot"><slot name="dot" :p="p" /></span>
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
          <span class="wk__overlap-label num" :class="`wk__overlap-label--${o.side}`"
            ><span>겹침</span> <span>{{ clock(o.s) }}–{{ clock(o.e) }}</span></span
          >
        </div>
      </div>
      <slot name="overlay" />
    </div>
  </div>
</template>

<style scoped>
/* WeekView.vue 에서 그대로 옮겼다 — .wk__scroll 부터 .wk__overlap-label--right 까지 */
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
.wk__place {
  position: absolute;
}
.wk__block {
  position: absolute;
  inset: 0;
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
.wk__block--requested {
  border: var(--border-thick) dashed var(--line-3);
  background: var(--surface);
  color: var(--text-3);
  cursor: default;
}
.wk__block--static {
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
.wk__overlap {
  position: absolute;
  z-index: 1;
  width: 3px;
  background: var(--danger);
  pointer-events: none;
}
.wk__overlap-label {
  position: absolute;
  top: 100%;
  display: flex;
  flex-direction: column;
  padding: 0 var(--space-1);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--danger);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  white-space: nowrap;
}
.wk__overlap-label--left {
  right: 0;
  align-items: flex-end;
}
.wk__overlap-label--right {
  left: 0;
  align-items: flex-start;
}
</style>
```

- [ ] **Step 4: `WeekView.vue` 를 WeekGrid 로 바꾼다 (동작 불변)**

4-1. import — `rules` 블록에서 `TYPE_LABEL,` 줄을 지운다. `weekView` import 블록(`import { ROW_PX, blockBox, … } from '../weekView'`)과 그 아래 `import RowDot …` 를 다음으로 바꾼다:

```ts
import { needsNight, needsWeekend, weekBlocks, type Placed } from '../weekView'
import RowDot from './rooms/RowDot.vue'
import WeekGrid from './week/WeekGrid.vue'
```

4-2. `const clock = (t: number) => hm(Math.floor(t / 60), t % 60)` 줄을 지운다(격자로 옮겼다).

4-3. `const range = computed(() => gridRange(blocks.value, night.value))` 부터 `days` computed 끝(`}),\n)`)까지 지운다. `night`·`weekend`·`empty`·`editable` 은 그대로 둔다.

4-4. `function blockClass(p: Placed) { … }` 와 그 아래 `periodsOf`·`blockLabel`·`blockName`·`who` 를 지운다(격자로 옮겼다). `dotOf`·`clickable`·`blockTitle`·`openBlock`·`resvEditable` 은 그대로.

4-5. template — `<div v-else class="wk__scroll">` 부터 그 닫는 `</div>`(`<SlotForm` 바로 위)까지를 다음으로 바꾼다:

```vue
    <WeekGrid
      v-else
      :blocks="blocks"
      :exams="fresh?.exams ?? []"
      :monday="monday"
      :night="night"
      :weekend="weekend"
      :editable="editable"
      :clickable="clickable"
      :block-title="blockTitle"
      :failed="(p: Placed) => dotOf(p) === 'failed'"
      @cell="(at) => openSlot(null, at)"
      @block="openBlock"
    >
      <template #dot="{ p }">
        <RowDot
          :state="dotOf(p)"
          :busy="!!room && tracker.resyncing.has(room.id)"
          @resync="resync(p.key)"
        />
      </template>
      <template #overlay>
        <div v-if="failedRes" class="wk__overlay">
          <EmptyState
            message="시간표·예약·시험기간을 불러오지 못했습니다"
            :actions="[{ label: '다시 불러오기', onClick: () => void failedRes?.reload() }]"
          />
        </div>
        <div v-else-if="loadingRes" class="wk__overlay">
          <Skeleton variant="block" width="60%" />
        </div>
        <div v-else-if="empty" class="wk__overlay">
          <EmptyState
            message="이 강의실에 등록된 시간표가 없습니다"
            :actions="[
              { label: '시간표 추가', variant: 'primary', onClick: () => openSlot(null) },
              { label: '페이지1에서 CSV 가져오기', onClick: toRooms },
            ]"
          />
        </div>
      </template>
    </WeekGrid>
```

4-6. style — `/* 격자 컨테이너 line.2 1px …` 주석의 `.wk__scroll` 부터 `.wk__overlap-label--right { … }` 까지 지운다. **`.wk__overlay` 와 `.wk__overlay > *` 는 남긴다**(오버레이 슬롯 내용은 WeekView 범위로 컴파일된다).

- [ ] **Step 5: 새 테스트 + 기존 주간 시간표 테스트 무수정 통과**

Run: `cd web && pnpm test src/admin/__tests__/weekGrid.spec.ts src/admin/__tests__/week.spec.ts src/admin/__tests__/weekView.spec.ts`
Expected: PASS (`week.spec.ts`·`weekView.spec.ts` 는 한 줄도 고치지 않았다).

Run: `cd web && pnpm exec vue-tsc --noEmit && pnpm lint` → 오류 0. (`hm` 이 WeekView 에서 아직 쓰이는지 확인 — `removeLines` 가 쓰므로 import 유지. 쓰지 않게 된 import 가 있으면 lint 가 알려 준다 — 지운다.)

- [ ] **Step 6: 커밋 + PR γ**

```bash
git add web/src/admin/views/week/WeekGrid.vue web/src/admin/views/WeekView.vue web/src/admin/__tests__/weekGrid.spec.ts
git commit -m "refactor(web): 주간 시간표 격자를 WeekGrid 로 분리 (동작 불변)"
```

PR γ 본문: "AI 비서 확인 화면이 같은 격자를 읽기 전용으로 두 번 그리기 위한 분리. 기존 `week.spec.ts`·`weekView.spec.ts` 무수정 통과." Playwright 로 `/admin/week` 화면을 1440 폭에서 열어 리팩터 전후 스크린샷이 같은지 눈으로 확인한 결과를 첨부.

---

### Task 3: API 타입 · `assistantApi` · 오류 가르기 — #175 (Draft, 01 PR B 머지 뒤 머지)

> 선행: 없음(가짜 fetch 로 개발). **PR δ 머지는 01 PR B 머지 뒤.**

**Files:**
- Modify: `web/src/api/types.ts` (끝에 AI 비서 절)
- Create: `web/src/api/assistant.ts`
- Create: `web/src/api/__fixtures__/assistant-turn-preview.json`, `web/src/api/__fixtures__/assistant-changes.json`
- Test: `web/src/api/__tests__/assistant.spec.ts`

**Interfaces:**
- Produces (types.ts): `AssistantRuntime`, `ModelFile`, `ModelGeneration`, `ModelManifestOn`, `ModelManifest`, `TurnIn`, `TurnChoice`, `TurnKind`, `WeekData`, `DiffOp`, `PreviewMark`, `PreviewWeek`, `PreviewRoom`, `PreviewOut`, `AnswerOut`, `TurnOut`, `ApplyOut`, `ChangeOut`, `CHANGE_DATES`.
- Produces (assistant.ts): `assistantApi.{model(), turn(t: TurnIn), apply(previewId: string), changes(limit?: number)}`, `revivePreview(p: PreviewOut): PreviewOut`, `type AssistantFailure`, `classify(e: ApiError): AssistantFailure | null`.

- [ ] **Step 1: 픽스처**

`web/src/api/__fixtures__/assistant-turn-preview.json`:

```json
{
  "conversation_id": "c_1",
  "kind": "preview",
  "message": "오른쪽에서 확인해 주세요.",
  "choices": [],
  "next_prefix": "상태: event.add | 강의실 803 | 날짜 11/27(금) | 시각 15:00~18:00 | 유형 특강 | 이름 알고리즘 특강\n질문: 이대로 적용할까요?\n관리자: ",
  "closed": false,
  "answer": null,
  "preview": {
    "preview_id": "p_1",
    "expires_at": "2026-11-25T01:10:00Z",
    "summary": ["+ 11/27(금) 15:00–18:00 특강 \"알고리즘 특강\" (공학관 803)"],
    "blockers": [],
    "warnings": ["기존 수업 \"자료구조\"(금 15:00–16:15)와 겹칩니다"],
    "notices": [],
    "rooms": [
      {
        "room_id": 3,
        "building_id": 7,
        "label": "공학관 803",
        "added": 1,
        "removed": 0,
        "changed": 0,
        "weeks": [
          {
            "week_start": "2026-11-23",
            "before": {
              "slots": [
                { "id": 5, "room_id": 3, "day": 5, "s_h": 15, "s_m": 0, "e_h": 16, "e_m": 15, "type": 1, "subject": "자료구조", "professor": "김교수", "source": 2 }
              ],
              "reservations": [
                { "id": 9, "room_id": 3, "date": "2026-11-24", "s_h": 10, "s_m": 0, "e_h": 11, "e_m": 0, "type": 6, "subject": "동아리", "professor": "", "status": "approved", "requester": null, "pushed_at": "2026-11-20T01:00:00Z", "checked_in_at": null, "checked_out_at": null, "reject_reason": null }
              ],
              "exams": []
            },
            "after": {
              "slots": [
                { "id": 5, "room_id": 3, "day": 5, "s_h": 15, "s_m": 0, "e_h": 16, "e_m": 15, "type": 1, "subject": "자료구조", "professor": "김교수", "source": 2 }
              ],
              "reservations": [
                { "id": 9, "room_id": 3, "date": "2026-11-24", "s_h": 10, "s_m": 0, "e_h": 11, "e_m": 0, "type": 6, "subject": "동아리", "professor": "", "status": "approved", "requester": null, "pushed_at": "2026-11-20T01:00:00Z", "checked_in_at": null, "checked_out_at": null, "reject_reason": null },
                { "id": 17, "room_id": 3, "date": "2026-11-27", "s_h": 15, "s_m": 0, "e_h": 18, "e_m": 0, "type": 5, "subject": "알고리즘 특강", "professor": "", "status": "approved", "requester": null, "pushed_at": null, "checked_in_at": null, "checked_out_at": null, "reject_reason": null }
              ],
              "exams": []
            },
            "changes": [{ "entity": "resv", "key": "r17", "op": "add", "fields": [] }]
          }
        ]
      }
    ]
  }
}
```

`web/src/api/__fixtures__/assistant-changes.json`:

```json
[
  {
    "id": 41,
    "applied_at": "2026-11-25T01:02:03Z",
    "user_email": "admin@mjc.ac.kr",
    "utterance": "803호 이번주 금요일 15시부터 18시까지 특강 예약해줘",
    "summary": ["+ 11/27(금) 15:00–18:00 특강 \"알고리즘 특강\" (공학관 803)"],
    "outbox_ids": [512]
  }
]
```

- [ ] **Step 2: 실패하는 테스트 `web/src/api/__tests__/assistant.spec.ts`**

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { assistantApi, classify } from '@/api/assistant'
import { clearSession, setSession } from '@/lib/session'
import turnPreview from '@/api/__fixtures__/assistant-turn-preview.json'
import changes from '@/api/__fixtures__/assistant-changes.json'

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
const fetchMock = vi.fn<typeof fetch>()

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  clearSession()
  setSession({ token: 't', role: 'admin', school_id: 1, name: '관리자1' })
})

describe('assistantApi', () => {
  it('model — 안내를 그대로 (enabled:false 도)', async () => {
    fetchMock.mockResolvedValue(json(200, { enabled: false }))
    expect(await assistantApi.model()).toEqual({ enabled: false })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/assistant/model')
  })

  it('turn — 본문을 그대로 보내고, 미리보기 안쪽 날짜까지 Date 로', async () => {
    fetchMock.mockResolvedValue(json(200, turnPreview))
    const t = await assistantApi.turn({
      conversation_id: null,
      utterance: '803호 …',
      form: { v: 1, intent: 'event.add', target: {}, set: {} },
      choice: null,
    })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/assistant/turns')
    expect(init!.method).toBe('POST')
    expect(JSON.parse(String(init!.body))).toMatchObject({ conversation_id: null, choice: null })
    expect(t.preview!.expires_at).toBeInstanceOf(Date)
    const before = t.preview!.rooms[0].weeks[0].before.reservations[0]
    expect(before.pushed_at).toBeInstanceOf(Date)
    expect(t.preview!.rooms[0].weeks[0].after.reservations[1].pushed_at).toBeNull()
  })

  it('apply — preview_id 를 경로에, changes — applied_at 을 Date 로', async () => {
    fetchMock.mockResolvedValueOnce(json(200, { change_id: 41, outbox_ids: [512] }))
    expect(await assistantApi.apply('p_1')).toEqual({ change_id: 41, outbox_ids: [512] })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/assistant/previews/p_1/apply')
    fetchMock.mockResolvedValueOnce(json(200, changes))
    const c = await assistantApi.changes()
    expect(fetchMock.mock.calls[1][0]).toBe('/api/assistant/changes?limit=50')
    expect(c[0].applied_at).toBeInstanceOf(Date)
  })
})

describe('classify — 부록 §4 오류 본문', () => {
  const err = async (status: number, body: unknown) => {
    fetchMock.mockResolvedValueOnce(json(status, body))
    return (await assistantApi.apply('p_1').catch((e) => e)) as ApiError
  }
  it('409 schema_version · 409 stale(+새 미리보기) · 410 · 422 blocked · 429 · 그 밖은 null', async () => {
    expect(classify(await err(409, { detail: 'schema_version' }))).toEqual({
      kind: 'schema_version',
    })
    const stale = classify(await err(409, { detail: 'stale', preview: turnPreview.preview }))
    expect(stale?.kind).toBe('stale')
    expect(stale?.kind === 'stale' && stale.preview.expires_at).toBeInstanceOf(Date)
    expect(classify(await err(410, { detail: 'expired' }))).toEqual({ kind: 'expired' })
    expect(classify(await err(404, { detail: '미리보기 없음' }))).toEqual({ kind: 'expired' })
    expect(classify(await err(422, { detail: 'blocked', blockers: ['지난 날짜'] }))).toEqual({
      kind: 'blocked',
      blockers: ['지난 날짜'],
    })
    expect(classify(await err(429, { detail: 'slow down' }))).toEqual({ kind: 'rate' })
    expect(classify(await err(500, { detail: 'boom' }))).toBeNull()
    expect(classify(await err(409, { detail: '다른 사람이 먼저' }))).toBeNull()
  })
})
```

- [ ] **Step 3: 실패 확인**

Run: `cd web && pnpm test src/api/__tests__/assistant.spec.ts`
Expected: FAIL — `Failed to resolve import "@/api/assistant"`.

- [ ] **Step 4: `types.ts` 끝에 추가**

```ts
// ---- AI 비서 (docs/plans/2026-11-25-ai-assistant-00-interfaces.md §4) ----
/** 02 계획 0단계 실험으로 고른 브라우저 실행 도구 */
export type AssistantRuntime = 'webllm' | 'transformers' | 'litert' | 'wllama'
export interface ModelFile {
  name: string
  size: number
  sha256: string
}
export interface ModelGeneration {
  temperature: number
  max_tokens: number
}
export interface ModelManifestOn {
  enabled: true
  schema_v: number
  runtime: AssistantRuntime
  repo: string
  /** 40자 커밋 해시 — 브랜치 이름이 아니다 */
  revision: string
  files: ModelFile[]
  system_prompt: string
  first_prefix: string
  json_schema: Record<string, unknown>
  generation: ModelGeneration
}
/** enabled:false = 모델 안내가 아직 없다 (화면은 '준비 중') */
export type ModelManifest = { enabled: false } | ModelManifestOn
export interface TurnIn {
  conversation_id: string | null
  /** 1~300자. 선택 버튼 턴은 버튼 라벨 */
  utterance: string
  /** 모델 출력(파싱한 객체) — form · choice · raw_output 중 정확히 하나 */
  form: Record<string, unknown> | null
  choice: string | null
  /** 두 번 시도해도 JSON 으로 못 읽은 모델 출력 원문(≤2000자) — 서버가 학습용 기록에 남기고 error 로 답한다 */
  raw_output?: string | null
}
export interface TurnChoice {
  id: string
  label: string
}
export type TurnKind = 'ask' | 'preview' | 'answer' | 'error'
export interface WeekData {
  slots: SlotWithRoom[]
  reservations: ResvWithRoom[]
  exams: ExamWithRoom[]
}
export type DiffOp = 'add' | 'remove' | 'change'
export interface PreviewMark {
  entity: 'slot' | 'resv' | 'exam'
  /** 정규 시간표 d{day}-{HHMM} · 예약 r{id} · 시험기간 e{id} */
  key: string
  op: DiffOp
  /** change 일 때 바뀐 칸 이름 (s_h · subject …) */
  fields: string[]
}
export interface PreviewWeek {
  /** 그 주 월요일. null = 정규 시간표만 바뀜(요일 격자) */
  week_start: string | null
  before: WeekData
  after: WeekData
  changes: PreviewMark[]
}
export interface PreviewRoom {
  room_id: number
  /** 전송 추적이 건물 단위로 outbox 를 읽을 때 쓴다 */
  building_id: number
  label: string
  added: number
  removed: number
  changed: number
  weeks: PreviewWeek[]
}
export interface PreviewOut {
  preview_id: string
  expires_at: Date
  summary: string[]
  /** 하나라도 있으면 적용 불가 */
  blockers: string[]
  warnings: string[]
  notices: string[]
  rooms: PreviewRoom[]
}
export interface AnswerOut {
  title: string
  columns: string[]
  rows: string[][]
}
export interface TurnOut {
  conversation_id: string
  kind: TurnKind
  message: string
  choices: TurnChoice[]
  /** 다음 턴 모델 입력 접두어. 대화가 끝났으면 null */
  next_prefix: string | null
  /** true = 대화 끝 — 다음 턴은 conversation_id null 로 */
  closed: boolean
  preview: PreviewOut | null
  answer: AnswerOut | null
}
export interface ApplyOut {
  change_id: number
  outbox_ids: number[]
}
export interface ChangeOut {
  id: number
  applied_at: Date
  user_email: string
  utterance: string
  summary: string[]
  outbox_ids: number[]
}
export const CHANGE_DATES = ['applied_at'] as const
```

- [ ] **Step 5: `web/src/api/assistant.ts`**

```ts
import { ApiError, request } from './client'
import { parseUtc } from '@/lib/time'
import {
  CHANGE_DATES,
  RESV_DATES,
  type ApplyOut,
  type ChangeOut,
  type ModelManifest,
  type PreviewOut,
  type ResvWithRoom,
  type TurnIn,
  type TurnOut,
  type WeekData,
} from './types'

// 미리보기 안쪽(예약 행)까지 Date 로 — request 의 dates 는 맨 위 칸만 바꾼다. 모양은 바꾸지 않는다
function reviveResv(r: ResvWithRoom): ResvWithRoom {
  const o: Record<string, unknown> = { ...r }
  for (const k of RESV_DATES) if (typeof o[k] === 'string') o[k] = parseUtc(o[k] as string)
  return o as unknown as ResvWithRoom
}
const reviveWeek = (w: WeekData): WeekData => ({
  ...w,
  reservations: w.reservations.map(reviveResv),
})
export function revivePreview(p: PreviewOut): PreviewOut {
  const at = p.expires_at as unknown
  return {
    ...p,
    expires_at: typeof at === 'string' ? parseUtc(at) : (at as Date),
    rooms: p.rooms.map((r) => ({
      ...r,
      weeks: r.weeks.map((w) => ({
        ...w,
        before: reviveWeek(w.before),
        after: reviveWeek(w.after),
      })),
    })),
  }
}

// 관리자 전용 + 건물 범위 (spec §6). 범위 밖은 서버가 404
export const assistantApi = {
  /** 모델 안내 — 파일 목록·고정 지시문·출력 문법. 모델 파일 자체는 여기서 받지 않는다 */
  model: () => request<ModelManifest>('GET', '/api/assistant/model'),
  turn: async (t: TurnIn): Promise<TurnOut> => {
    const out = await request<TurnOut>('POST', '/api/assistant/turns', t)
    return out.preview ? { ...out, preview: revivePreview(out.preview) } : out
  },
  /** 저장된 확정 변경 목록을 적용 — 모델 출력을 다시 쓰지 않는다 */
  apply: (previewId: string) =>
    request<ApplyOut>('POST', `/api/assistant/previews/${encodeURIComponent(previewId)}/apply`),
  changes: (limit = 50) =>
    request<ChangeOut[]>('GET', `/api/assistant/changes?limit=${limit}`, undefined, {
      dates: CHANGE_DATES,
    }),
}

export type AssistantFailure =
  | { kind: 'schema_version' }
  | { kind: 'stale'; preview: PreviewOut }
  | { kind: 'expired' }
  | { kind: 'blocked'; blockers: string[] }
  | { kind: 'rate' }

/** 부록 §4 의 오류 본문을 가른다 — 모르는 오류는 null (화면은 e.message) */
export function classify(e: ApiError): AssistantFailure | null {
  const body = (e.detail ?? {}) as { detail?: unknown; preview?: PreviewOut; blockers?: unknown }
  if (e.status === 429) return { kind: 'rate' }
  if (e.status === 409 && body.detail === 'schema_version') return { kind: 'schema_version' }
  if (e.status === 409 && body.detail === 'stale' && body.preview)
    return { kind: 'stale', preview: revivePreview(body.preview) }
  // 404 = 없는·남의 미리보기 — 화면에서는 만료와 같게 다시 요청하라고 안내한다
  if (e.status === 410 || (e.status === 404 && body.detail === '미리보기 없음')) return { kind: 'expired' }
  if (e.status === 422 && body.detail === 'blocked' && Array.isArray(body.blockers))
    return { kind: 'blocked', blockers: body.blockers.map(String) }
  return null
}
```

- [ ] **Step 6: 통과 + 커밋**

Run: `cd web && pnpm test src/api/__tests__/assistant.spec.ts` → PASS. `pnpm exec vue-tsc --noEmit` → 오류 0.

```bash
git switch -c feat/ai-assistant-web main
git add web/src/api/types.ts web/src/api/assistant.ts web/src/api/__fixtures__/assistant-turn-preview.json web/src/api/__fixtures__/assistant-changes.json web/src/api/__tests__/assistant.spec.ts
git commit -m "feat(web): AI 비서 API 타입·클라이언트 — 턴·적용·변경 기록, 오류 가르기"
```

---

### Task 4: 모델 실행 추상화 — 프롬프트 조립 · `ModelRunner` · Worker 메시지 · 개발용 대역 — #175 (Draft)

**Files:**
- Create: `web/src/admin/assistant/prompt.ts`
- Create: `web/src/admin/assistant/runner.ts`
- Create: `web/src/admin/assistant/workerCore.ts`
- Create: `web/src/admin/assistant/worker.ts`
- Create: `web/src/admin/assistant/adapters/stub.ts`
- Test: `web/src/admin/__tests__/assistantRunner.spec.ts`

**Interfaces:**
- Consumes: `ModelManifestOn`, `ModelGeneration`, `AssistantRuntime` (Task 3).
- Produces:
  - `prompt.ts`: `userMessage(prefix: string, utterance: string): string`, `parseForm(text: string): Record<string, unknown> | null`
  - `runner.ts`: `interface GenerateReq { system: string; user: string; schema: Record<string, unknown>; generation: ModelGeneration }`, `interface LoadProgress { loaded: number; total: number; text: string }`, `interface ModelRunner { load(m, onProgress): Promise<void>; generate(req): Promise<string>; dispose(): Promise<void> }`, `type ToWorker`, `type FromWorker`, `interface WorkerLike`, `class WorkerRunner implements ModelRunner` (생성자 `(make?: () => WorkerLike)`)
  - `workerCore.ts`: `type AdapterFactory = (runtime: AssistantRuntime) => Promise<ModelRunner>`, `createHandler(post: (m: FromWorker) => void, adapterFor: AdapterFactory): (msg: ToWorker) => Promise<void>`
  - `adapters/stub.ts`: `STUB_KEY = 'esc-assistant-stub'`, `type StubScript = Record<string, unknown> | 'manual'`, `manualOutput: Ref<string>`, `readStubScript(storage?, dev?): StubScript | null`, `STUB_MANIFEST: ModelManifestOn`, `class StubRunner implements ModelRunner`

- [ ] **Step 1: 실패하는 테스트 `web/src/admin/__tests__/assistantRunner.spec.ts`**

```ts
import { describe, expect, it, vi } from 'vitest'
import { parseForm, userMessage } from '@/admin/assistant/prompt'
import {
  WorkerRunner,
  type FromWorker,
  type GenerateReq,
  type ModelRunner,
  type ToWorker,
  type WorkerLike,
} from '@/admin/assistant/runner'
import { createHandler } from '@/admin/assistant/workerCore'
import {
  STUB_MANIFEST,
  StubRunner,
  manualOutput,
  readStubScript,
} from '@/admin/assistant/adapters/stub'

const REQ: GenerateReq = {
  system: 'S',
  user: '관리자: 801 배터리?',
  schema: {},
  generation: { temperature: 0, max_tokens: 256 },
}

class FakeWorker implements WorkerLike {
  sent: ToWorker[] = []
  onmessage: ((e: MessageEvent<FromWorker>) => void) | null = null
  onerror: ((e: ErrorEvent) => void) | null = null
  terminate = vi.fn()
  postMessage(m: ToWorker) {
    this.sent.push(m)
  }
  emit(m: FromWorker) {
    this.onmessage?.({ data: m } as MessageEvent<FromWorker>)
  }
}

describe('prompt', () => {
  it('userMessage — 접두어 + 다듬은 문장', () => {
    expect(userMessage('관리자: ', '  803 금 특강 ')).toBe('관리자: 803 금 특강')
  })
  it('parseForm — 객체·코드펜스는 통과, 깨진 JSON·모양 위반은 null', () => {
    const ok = '{"v":1,"intent":"fill","target":{},"set":{"subject":"알고리즘 특강"}}'
    expect(parseForm(ok)).toMatchObject({ intent: 'fill' })
    expect(parseForm('```json\n' + ok + '\n```')).toMatchObject({ v: 1 })
    expect(parseForm('{"v":1,"intent":"fill"')).toBeNull()
    expect(parseForm('{"v":"1","intent":"fill","target":{},"set":{}}')).toBeNull()
    expect(parseForm('{"v":1,"intent":"fill","target":[],"set":{}}')).toBeNull()
    expect(parseForm('[1]')).toBeNull()
  })
})

describe('WorkerRunner', () => {
  it('load → progress 콜백 → ready 로 끝난다, generate 는 id 로 짝짓는다', async () => {
    const fw = new FakeWorker()
    const r = new WorkerRunner(() => fw)
    const onProgress = vi.fn()
    const loading = r.load(STUB_MANIFEST, onProgress)
    expect(fw.sent[0]).toEqual({ type: 'load', manifest: STUB_MANIFEST })
    fw.emit({ type: 'progress', progress: { loaded: 1, total: 2, text: 'x' } })
    fw.emit({ type: 'ready' })
    await loading
    expect(onProgress).toHaveBeenCalledWith({ loaded: 1, total: 2, text: 'x' })
    const a = r.generate(REQ)
    const b = r.generate(REQ)
    const [ga, gb] = fw.sent.slice(1) as Extract<ToWorker, { type: 'generate' }>[]
    fw.emit({ type: 'result', id: gb.id, text: 'B' })
    fw.emit({ type: 'result', id: ga.id, text: 'A' })
    expect(await a).toBe('A')
    expect(await b).toBe('B')
  })

  it('load 오류(id null)는 load 를, generate 오류는 그 요청을 실패시킨다, dispose 는 남은 요청을 끝낸다', async () => {
    const fw = new FakeWorker()
    const r = new WorkerRunner(() => fw)
    const loading = r.load(STUB_MANIFEST, () => {})
    fw.emit({ type: 'error', id: null, message: 'no gpu' })
    await expect(loading).rejects.toThrow('no gpu')
    const g = r.generate(REQ)
    const id = (fw.sent[1] as Extract<ToWorker, { type: 'generate' }>).id
    fw.emit({ type: 'error', id, message: 'oom' })
    await expect(g).rejects.toThrow('oom')
    const pending = r.generate(REQ)
    await r.dispose()
    await expect(pending).rejects.toThrow('모델을 내렸습니다')
    expect(fw.terminate).toHaveBeenCalled()
    await expect(r.generate(REQ)).rejects.toThrow('모델을 먼저 불러오세요')
  })
})

describe('createHandler (Worker 안)', () => {
  it('load → progress·ready, generate → result, 불러오기 전 generate → 그 id 로 error', async () => {
    const posted: FromWorker[] = []
    const engine: ModelRunner = {
      load: async (_m, onProgress) => onProgress({ loaded: 5, total: 5, text: '끝' }),
      generate: async () => '{"v":1}',
      dispose: vi.fn(async () => {}),
    }
    const h = createHandler((m) => posted.push(m), async () => engine)
    await h({ type: 'generate', id: 1, req: REQ })
    expect(posted[0]).toEqual({ type: 'error', id: 1, message: '모델을 먼저 불러오세요' })
    await h({ type: 'load', manifest: STUB_MANIFEST })
    await h({ type: 'generate', id: 2, req: REQ })
    expect(posted.slice(1)).toEqual([
      { type: 'progress', progress: { loaded: 5, total: 5, text: '끝' } },
      { type: 'ready' },
      { type: 'result', id: 2, text: '{"v":1}' },
    ])
    await h({ type: 'dispose' })
    expect(engine.dispose).toHaveBeenCalled()
  })

  it('어댑터가 없으면 load 가 error(id null)', async () => {
    const posted: FromWorker[] = []
    const h = createHandler(
      (m) => posted.push(m),
      async (rt) => {
        throw new Error(`지원 안 함 ${rt}`)
      },
    )
    await h({ type: 'load', manifest: STUB_MANIFEST })
    expect(posted).toEqual([{ type: 'error', id: null, message: '지원 안 함 webllm' }])
  })
})

describe('StubRunner · readStubScript', () => {
  it('대본 — 마지막 "관리자: " 뒤 문장으로 찾고, 없으면 unknown', async () => {
    const r = new StubRunner({ '801 배터리?': { v: 1, intent: 'ask.node', target: {}, set: {} } })
    expect(JSON.parse(await r.generate(REQ)).intent).toBe('ask.node')
    const follow = { ...REQ, user: '상태: …\n질문: 이름?\n관리자: 처음 보는 말' }
    expect(JSON.parse(await r.generate(follow)).intent).toBe('unknown')
  })
  it('manual — 개발 화면 입력칸을 그대로 낸다', async () => {
    manualOutput.value = '{"v":1,"intent":"cancel","target":{},"set":{}}'
    expect(await new StubRunner('manual').generate(REQ)).toBe(manualOutput.value)
  })
  it('개발 서버가 아니면 대본을 읽지 않는다, 깨진 JSON 도 null', () => {
    const s = { getItem: () => '{"a":1}' }
    expect(readStubScript(s, false)).toBeNull()
    expect(readStubScript(s, true)).toEqual({ a: 1 })
    expect(readStubScript({ getItem: () => 'manual' }, true)).toBe('manual')
    expect(readStubScript({ getItem: () => '{oops' }, true)).toBeNull()
    expect(readStubScript({ getItem: () => null }, true)).toBeNull()
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin/__tests__/assistantRunner.spec.ts`
Expected: FAIL — `Failed to resolve import "@/admin/assistant/prompt"`.

- [ ] **Step 3: `prompt.ts`**

```ts
// 부록 §2 — 사용자 메시지 = 접두어 + 관리자 문장.
// 접두어는 첫 턴 manifest.first_prefix("관리자: "), 이어지는 턴은 서버 응답의 next_prefix

export function userMessage(prefix: string, utterance: string): string {
  return prefix + utterance.trim()
}

const FENCE = /^```(?:json)?\s*([\s\S]*?)\s*```$/
const isObj = (x: unknown): x is Record<string, unknown> =>
  !!x && typeof x === 'object' && !Array.isArray(x)

/** 모델 출력 → 양식 객체. 최소 모양(v 숫자 · intent 문자열 · target/set 객체)만 본다 — 규격 검증은 서버가 한다 */
export function parseForm(text: string): Record<string, unknown> | null {
  const t = text.trim()
  const body = FENCE.exec(t)?.[1] ?? t
  let v: unknown
  try {
    v = JSON.parse(body)
  } catch {
    return null
  }
  if (!isObj(v)) return null
  if (typeof v.v !== 'number' || typeof v.intent !== 'string') return null
  if (!isObj(v.target) || !isObj(v.set)) return null
  return v
}
```

- [ ] **Step 4: `runner.ts`**

```ts
import type { ModelGeneration, ModelManifestOn } from '@/api/types'

export interface GenerateReq {
  system: string
  user: string
  /** 출력 문법 강제(JSON Schema) — 지원하는 실행 도구만 쓴다 */
  schema: Record<string, unknown>
  generation: ModelGeneration
}
export interface LoadProgress {
  loaded: number
  total: number
  text: string
}
/** 실행 도구 하나 — Worker 안의 어댑터와 화면 쪽 WorkerRunner·StubRunner 가 같은 모양 */
export interface ModelRunner {
  load(m: ModelManifestOn, onProgress: (p: LoadProgress) => void): Promise<void>
  generate(req: GenerateReq): Promise<string>
  dispose(): Promise<void>
}

export type ToWorker =
  | { type: 'load'; manifest: ModelManifestOn }
  | { type: 'generate'; id: number; req: GenerateReq }
  | { type: 'dispose' }
export type FromWorker =
  | { type: 'progress'; progress: LoadProgress }
  | { type: 'ready' }
  | { type: 'result'; id: number; text: string }
  /** id null = 불러오기 실패 */
  | { type: 'error'; id: number | null; message: string }

export interface WorkerLike {
  postMessage(m: ToWorker): void
  terminate(): void
  onmessage: ((e: MessageEvent<FromWorker>) => void) | null
  onerror: ((e: ErrorEvent) => void) | null
}
const makeWorker = (): WorkerLike =>
  new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' }) as unknown as WorkerLike

/** 화면 쪽 — 모델은 Web Worker 에서 돈다(답을 만드는 동안 화면이 멈추지 않게). 요청은 id 로 짝짓는다 */
export class WorkerRunner implements ModelRunner {
  private w: WorkerLike | null = null
  private seq = 0
  private waiting = new Map<number, { ok: (t: string) => void; fail: (e: Error) => void }>()
  private loading: { ok: () => void; fail: (e: Error) => void } | null = null
  private onProgress: (p: LoadProgress) => void = () => {}

  constructor(private make: () => WorkerLike = makeWorker) {}

  load(m: ModelManifestOn, onProgress: (p: LoadProgress) => void): Promise<void> {
    const w = (this.w ??= this.attach(this.make()))
    this.onProgress = onProgress
    return new Promise<void>((ok, fail) => {
      this.loading = { ok, fail }
      w.postMessage({ type: 'load', manifest: m })
    })
  }

  generate(req: GenerateReq): Promise<string> {
    const w = this.w
    if (!w) return Promise.reject(new Error('모델을 먼저 불러오세요'))
    const id = ++this.seq
    return new Promise<string>((ok, fail) => {
      this.waiting.set(id, { ok, fail })
      w.postMessage({ type: 'generate', id, req })
    })
  }

  async dispose(): Promise<void> {
    if (this.w) {
      this.w.postMessage({ type: 'dispose' })
      this.w.terminate()
    }
    this.w = null
    this.failAll(new Error('모델을 내렸습니다'))
  }

  private attach(w: WorkerLike): WorkerLike {
    w.onmessage = (e) => this.receive(e.data)
    w.onerror = (e) => this.failAll(new Error(e.message || '모델 작업 공간 오류'))
    return w
  }

  private receive(m: FromWorker) {
    if (m.type === 'progress') this.onProgress(m.progress)
    else if (m.type === 'ready') {
      this.loading?.ok()
      this.loading = null
    } else if (m.type === 'result') {
      this.waiting.get(m.id)?.ok(m.text)
      this.waiting.delete(m.id)
    } else if (m.id === null) {
      this.loading?.fail(new Error(m.message))
      this.loading = null
    } else {
      this.waiting.get(m.id)?.fail(new Error(m.message))
      this.waiting.delete(m.id)
    }
  }

  private failAll(e: Error) {
    this.loading?.fail(e)
    this.loading = null
    for (const p of this.waiting.values()) p.fail(e)
    this.waiting.clear()
  }
}
```

- [ ] **Step 5: `workerCore.ts` · `worker.ts`**

`web/src/admin/assistant/workerCore.ts`:

```ts
import type { AssistantRuntime } from '@/api/types'
import type { FromWorker, ModelRunner, ToWorker } from './runner'

export type AdapterFactory = (runtime: AssistantRuntime) => Promise<ModelRunner>

/** Worker 안의 메시지 처리 — worker.ts 는 이것을 self 에 잇기만 한다(테스트는 이것을 직접 부른다) */
export function createHandler(post: (m: FromWorker) => void, adapterFor: AdapterFactory) {
  let engine: ModelRunner | null = null
  return async (msg: ToWorker): Promise<void> => {
    try {
      if (msg.type === 'load') {
        await engine?.dispose()
        engine = null
        const next = await adapterFor(msg.manifest.runtime)
        await next.load(msg.manifest, (progress) => post({ type: 'progress', progress }))
        engine = next
        post({ type: 'ready' })
      } else if (msg.type === 'generate') {
        if (!engine) throw new Error('모델을 먼저 불러오세요')
        post({ type: 'result', id: msg.id, text: await engine.generate(msg.req) })
      } else {
        await engine?.dispose()
        engine = null
      }
    } catch (e) {
      post({
        type: 'error',
        id: msg.type === 'generate' ? msg.id : null,
        message: e instanceof Error ? e.message : String(e),
      })
    }
  }
}
```

`web/src/admin/assistant/worker.ts`:

```ts
import type { AssistantRuntime } from '@/api/types'
import type { FromWorker, ModelRunner, ToWorker } from './runner'
import { createHandler } from './workerCore'

// DOM 타입 안에서 쓰는 Worker 전역 — tsconfig 에 WebWorker lib 를 더하면 DOM 과 겹친다
const ctx = self as unknown as {
  postMessage(m: FromWorker): void
  onmessage: ((e: MessageEvent<ToWorker>) => void) | null
}

// 실행 도구 라이브러리는 여기서만 동적 import 한다 — 화면 청크(prefetchViews)에 들어가지 않게 (Task 12 가 채운다)
async function adapterFor(runtime: AssistantRuntime): Promise<ModelRunner> {
  throw new Error(`이 실행 도구(${runtime})는 아직 지원하지 않습니다`)
}

const handle = createHandler((m) => ctx.postMessage(m), adapterFor)
ctx.onmessage = (e) => void handle(e.data)
```

- [ ] **Step 6: `adapters/stub.ts`**

```ts
import { ref } from 'vue'
import type { ModelManifestOn } from '@/api/types'
import type { GenerateReq, LoadProgress, ModelRunner } from '../runner'

/** localStorage 키 — 개발 서버(import.meta.env.DEV)에서만 읽는다. 운영 빌드에는 영향 없음 */
export const STUB_KEY = 'esc-assistant-stub'
/** 관리자 문장(앞뒤 공백 정리) → 모델 출력(양식 객체 또는 원문). 'manual' 이면 개발 입력칸을 그대로 낸다 */
export type StubScript = Record<string, unknown> | 'manual'
/** manual 모드의 "모델 출력" 입력칸 (ChatPane 이 개발 서버에서만 그린다) */
export const manualOutput = ref('')

function safeLocal(): Pick<Storage, 'getItem'> | null {
  try {
    return localStorage
  } catch {
    return null
  }
}

export function readStubScript(
  storage: Pick<Storage, 'getItem'> | null = safeLocal(),
  dev: boolean = import.meta.env.DEV,
): StubScript | null {
  if (!dev || !storage) return null
  const raw = storage.getItem(STUB_KEY)
  if (!raw) return null
  if (raw === 'manual') return 'manual'
  try {
    const v: unknown = JSON.parse(raw)
    return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null
  } catch {
    return null
  }
}

/** 개발용 안내 — 서버 안내가 enabled:false 여도 대화 흐름을 만들 수 있게 */
export const STUB_MANIFEST: ModelManifestOn = {
  enabled: true,
  schema_v: 1,
  runtime: 'webllm',
  repo: 'dev/stub',
  revision: 'stub',
  files: [],
  system_prompt: '',
  first_prefix: '관리자: ',
  json_schema: {},
  generation: { temperature: 0, max_tokens: 256 },
}

const PREFIX = '관리자: '
const lastUtterance = (user: string) => {
  const i = user.lastIndexOf(PREFIX)
  return (i < 0 ? user : user.slice(i + PREFIX.length)).trim()
}
const UNKNOWN = JSON.stringify({ v: 1, intent: 'unknown', target: {}, set: {} })

/** 02 계획 0단계 결과 전에 화면·서버 흐름을 만드는 대역. 화면 쪽에서 돈다(Worker 없음) */
export class StubRunner implements ModelRunner {
  constructor(private script: StubScript) {}

  async load(_m: ModelManifestOn, onProgress: (p: LoadProgress) => void): Promise<void> {
    onProgress({ loaded: 1, total: 1, text: '개발용 대역' })
  }

  async generate(req: GenerateReq): Promise<string> {
    if (this.script === 'manual') return manualOutput.value
    const out = this.script[lastUtterance(req.user)]
    if (out === undefined) return UNKNOWN
    return typeof out === 'string' ? out : JSON.stringify(out)
  }

  async dispose(): Promise<void> {}
}
```

- [ ] **Step 7: 통과 + 커밋**

Run: `cd web && pnpm test src/admin/__tests__/assistantRunner.spec.ts` → PASS. `pnpm exec vue-tsc --noEmit && pnpm lint` → 오류 0.

```bash
git add web/src/admin/assistant/prompt.ts web/src/admin/assistant/runner.ts web/src/admin/assistant/workerCore.ts web/src/admin/assistant/worker.ts web/src/admin/assistant/adapters/stub.ts web/src/admin/__tests__/assistantRunner.spec.ts
git commit -m "feat(web): AI 비서 모델 실행 추상화 — Worker 메시지, 프롬프트 조립, 개발용 대역"
```

---

### Task 5: 사이드바 "AI" 묶음 · `/assistant` 라우트 · 모델 상태 v1 · 화면 뼈대

> 선행: Task 1(아이콘) 머지.

> **화면 변경(2026-11-26, #176)**: `/assistant` 라우트·메뉴 링크를 만들지 않는다(`router.ts`·`router.spec.ts` 는 고치지 않음, `prefetchViews` 대상도 아님).
> - 사이드바: `AdminShell.vue` nav 맨 위 묶음 `AI` 에 `{ action, label: 'AI 비서', group: 'AI', icon: 'assistant', shortcut }` 항목(Task 1 의 `action`). `shortcut` 은 macOS 면 `⌘K`, 아니면 `Ctrl K`. 창이 열려 있으면 활성 모양·`aria-expanded="true"`. `shell.spec.ts` 는 링크 목록 대신 맨 위 **버튼** `AI 비서` + 나머지 링크 순서로 바꾼다.
> - 창: `AssistantView.vue` 대신 `views/assistant/AssistantPanel.vue` — `AdminShell.vue` 에 **한 번만** 마운트한다(본문 영역 안, `role="dialog"` · `aria-modal="true"` · `aria-label="AI 비서"`, 덮개는 본문만). 열림 상태는 모듈 `ref` 하나(`open`)로 두고 사이드바 버튼·단축키가 토글한다.
> - 단축키: 전역 `keydown` 에서 `Ctrl+K`(macOS `⌘+K`) → `preventDefault` 후 토글. 닫기 = ×·`Esc`·덮개 클릭·버튼 다시 누름. 열리면 입력칸에 포커스, 닫히면 **연 요소로 포커스를 돌려준다**. 열려 있는 동안 포커스는 창 안에서 돈다(사이드바 `AI 비서` 버튼만 예외).
> - 모델 상태(`ModelGate`)는 명령창 아래 되묻기 칸 자리에 선다(스펙 「모델 상태」) — 준비되기 전엔 입력칸 비활성. 받는 중에 창을 닫아도 받기는 이어진다(`model.ts` 모듈 상태 — 아래 코드 그대로).
> - `Examples.vue`(예문)는 머지된 스펙에 없다 — 만들지 않는다.
> - 그대로: `model.ts`(상태·`initModel`·`setEngine`·`resetModel`), `ModelGate.vue` 의 상태별 문구·버튼. 아래 `assistantView.spec.ts` 의 모델 상태 테스트는 `mount(AssistantPanel)` 로 바꿔 그대로 쓴다.

**Files:**
- Modify: `web/src/admin/router.ts` (`views.assistant`, children `assistant`)
- Modify: `web/src/admin/AdminShell.vue:21-45` (nav 맨 위)
- Create: `web/src/admin/assistant/model.ts`
- Create: `web/src/admin/views/AssistantView.vue`
- Create: `web/src/admin/views/assistant/ModelGate.vue`
- Create: `web/src/admin/views/assistant/Examples.vue`
- Modify: `web/src/admin/__tests__/shell.spec.ts` (메뉴 순서·개수)
- Modify: `web/src/admin/__tests__/router.spec.ts` (라우트)
- Test: `web/src/admin/__tests__/assistantView.spec.ts` (새)

**Interfaces:**
- Consumes: `assistantApi.model()` (Task 3), `StubRunner`·`readStubScript`·`STUB_MANIFEST` (Task 4).
- Produces (`model.ts`):
  - `type GateState = 'loading' | 'disabled' | 'unsupported' | 'need-download' | 'no-space' | 'downloading' | 'starting' | 'ready' | 'failed'`
  - `model: { state; manifest: ModelManifest | null; reason: string; progress: LoadProgress; need: number; free: number | null; stub: false | 'script' | 'manual' }` (reactive, 모듈 상태)
  - `initModel(): Promise<void>`, `engine(): { runner: ModelRunner; manifest: ModelManifestOn } | null`, `setEngine(runner: ModelRunner | null, manifest: ModelManifestOn | null): void`, `resetModel(): Promise<void>`
  - Task 11 이 `downloadModel()`·`cancelDownload()` 를 더하고 `initModel` 의 enabled 분기를 바꾼다.

- [ ] **Step 1: 실패하는 테스트**

`web/src/admin/__tests__/shell.spec.ts` — `'/ 는 /dashboard 로, 메뉴 순서(#46) …'` 테스트의 기대값을 바꾼다:

```ts
    expect(links.map((a) => a.text().replace(/\d+/g, '').trim())).toEqual([
      'AI 비서',
      '건물 · 강의실',
      '강의실 설정',
      '주간 시간표',
      '노드 상태',
      '전송 현황',
      '회원',
    ])
    expect(links[0].attributes('href')).toBe('/assistant')
    expect(links[3].attributes('href')).toBe('/week')
    expect(links[5].attributes('aria-current')).toBe('page')
    expect(links[6].text()).toContain('2')
```

같은 파일 `'없는 주소 — 메뉴는 그대로 …'` 의 `toHaveLength(6)` → `toHaveLength(7)`.

`web/src/admin/__tests__/router.spec.ts` 의 `describe` 안에 추가:

```ts
  it('AI 비서 — /assistant 가 셸 안에 잡히고 미리 받기 목록에 있다', () => {
    const r = makeRouter(createMemoryHistory())
    expect(r.resolve('/assistant').matched).toHaveLength(2)
    expect(Object.keys(views)).toContain('assistant')
  })
```

`web/src/admin/__tests__/assistantView.spec.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import AssistantView from '@/admin/views/AssistantView.vue'
import { assistantApi } from '@/api/assistant'
import { model, resetModel } from '@/admin/assistant/model'
import { STUB_KEY } from '@/admin/assistant/adapters/stub'

vi.mock('@/api/assistant', () => ({
  assistantApi: { model: vi.fn(), turn: vi.fn(), apply: vi.fn(), changes: vi.fn(async () => []) },
  classify: vi.fn(() => null),
}))
const modelApi = vi.mocked(assistantApi.model)

beforeEach(async () => {
  await resetModel()
  localStorage.clear()
  modelApi.mockReset()
})
afterEach(() => localStorage.clear())

describe('AssistantView — 모델 상태 v1', () => {
  it('enabled:false → 준비 중 안내, 모델 파일은 받지 않는다', async () => {
    modelApi.mockResolvedValue({ enabled: false })
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)
    const w = mount(AssistantView)
    await flushPromises()
    expect(model.state).toBe('disabled')
    expect(w.text()).toContain('AI 비서를 준비하고 있습니다')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('개발용 대역 대본이 있으면 안내를 부르지 않고 바로 준비됨', async () => {
    localStorage.setItem(STUB_KEY, '{"a":1}')
    mount(AssistantView)
    await flushPromises()
    expect(modelApi).not.toHaveBeenCalled()
    expect(model.state).toBe('ready')
    expect(model.stub).toBe('script')
  })

  it('안내 실패 → 실패 + 다시 시도, 탭을 옮겼다 와도 준비된 모델은 다시 부르지 않는다', async () => {
    const { ApiError } = await import('@/api/client')
    modelApi.mockRejectedValueOnce(new ApiError(500, '서버 오류가 났습니다.'))
    const w = mount(AssistantView)
    await flushPromises()
    expect(model.state).toBe('failed')
    expect(w.text()).toContain('서버 오류가 났습니다.')
    localStorage.setItem(STUB_KEY, '{"a":1}')
    await w.get('.gate button').trigger('click')
    await flushPromises()
    expect(model.state).toBe('ready')
    w.unmount()
    mount(AssistantView)
    await flushPromises()
    expect(modelApi).toHaveBeenCalledTimes(1)
  })

  it('예문 목록이 오른쪽에 선다', async () => {
    modelApi.mockResolvedValue({ enabled: false })
    const w = mount(AssistantView)
    await flushPromises()
    expect(w.get('.as__side').text()).toContain('803호 이번 주 금요일 15시부터 18시까지 특강')
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin/__tests__/shell.spec.ts src/admin/__tests__/router.spec.ts src/admin/__tests__/assistantView.spec.ts`
Expected: FAIL — 메뉴에 `AI 비서` 없음, `/assistant` 미매칭, `AssistantView.vue` 없음.

- [ ] **Step 3: 라우트·메뉴**

`web/src/admin/router.ts` — `views` 객체 첫 줄에:

```ts
  assistant: () => import('./views/AssistantView.vue'),
```

children 의 `{ path: '', redirect: '/dashboard' },` 다음 줄에:

```ts
      // AI 비서 — 화면 코드 청크만 미리 받는다. 모델 파일은 화면 안 버튼으로만 (admin-assistant.md)
      { path: 'assistant', component: views.assistant },
```

`web/src/admin/AdminShell.vue` — 주석을 `// admin-master.md 순서: AI 비서(맨 위 AI 묶음) · 건물 · 강의실 · 강의실 설정 · 주간 시간표 · 노드 상태 · 전송 현황 · 회원` 으로 바꾸고 `nav` 배열 첫 항목으로:

```ts
  { to: '/assistant', label: 'AI 비서', group: 'AI', icon: 'assistant' as const },
```

- [ ] **Step 4: `web/src/admin/assistant/model.ts` (v1)**

```ts
import { reactive } from 'vue'
import { ApiError } from '@/api/client'
import { assistantApi } from '@/api/assistant'
import type { ModelManifest, ModelManifestOn } from '@/api/types'
import type { LoadProgress, ModelRunner } from './runner'
import { STUB_MANIFEST, StubRunner, readStubScript } from './adapters/stub'

export type GateState =
  | 'loading' // 모델 안내를 받는 중
  | 'disabled' // enabled:false — 준비 중
  | 'unsupported' // 이 PC·이 판의 실행 도구로는 못 씀 (reason)
  | 'need-download' // 받기 버튼
  | 'no-space'
  | 'downloading'
  | 'starting' // 받은 모델을 불러오는 중
  | 'ready'
  | 'failed'

/** 모듈 상태 — 탭을 옮겼다 와도 받은 모델·진행이 남는다(새로고침하면 처음부터, 파일은 브라우저에 남는다) */
export const model = reactive({
  state: 'loading' as GateState,
  manifest: null as ModelManifest | null,
  reason: '',
  progress: { loaded: 0, total: 0, text: '' } as LoadProgress,
  /** 받아야 할 바이트 · 남은 저장 공간 (Task 11) */
  need: 0,
  free: null as number | null,
  stub: false as false | 'script' | 'manual',
})

let current: { runner: ModelRunner; manifest: ModelManifestOn } | null = null
export const engine = () => current
export function setEngine(runner: ModelRunner | null, manifest: ModelManifestOn | null) {
  current = runner && manifest ? { runner, manifest } : null
}

const BUSY: GateState[] = ['ready', 'downloading', 'starting']

export async function initModel(): Promise<void> {
  if (BUSY.includes(model.state)) return
  const script = readStubScript()
  if (script) {
    const runner = new StubRunner(script)
    await runner.load(STUB_MANIFEST, () => {})
    setEngine(runner, STUB_MANIFEST)
    model.manifest = STUB_MANIFEST
    model.stub = script === 'manual' ? 'manual' : 'script'
    model.state = 'ready'
    return
  }
  model.state = 'loading'
  try {
    const m = await assistantApi.model()
    model.manifest = m
    if (!m.enabled) {
      model.state = 'disabled'
      return
    }
    // Task 11 이 이 분기를 기기 점검 → 받기/불러오기로 바꾼다
    model.state = 'unsupported'
    model.reason = `이 판의 실행 도구(${m.runtime})를 아직 지원하지 않습니다.`
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    model.state = 'failed'
    model.reason = e.message
  }
}

/** 테스트·로그아웃용 — 모델을 내리고 처음 상태로 */
export async function resetModel(): Promise<void> {
  await current?.runner.dispose()
  setEngine(null, null)
  Object.assign(model, {
    state: 'loading',
    manifest: null,
    reason: '',
    progress: { loaded: 0, total: 0, text: '' },
    need: 0,
    free: null,
    stub: false,
  })
}
```

- [ ] **Step 5: `ModelGate.vue` (v1) · `Examples.vue` · `AssistantView.vue` (뼈대)**

`web/src/admin/views/assistant/ModelGate.vue`:

```vue
<script setup lang="ts">
import EmptyState from '@/components/ui/EmptyState.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import { initModel, model } from '../../assistant/model'

// 대화 열 자리에 서는 모델 상태 (admin-assistant.md 「모델 상태」). Task 11 이 받기·진행·저장 공간을 더한다
</script>

<template>
  <div class="gate">
    <Skeleton v-if="model.state === 'loading'" variant="block" width="100%" />
    <EmptyState
      v-else-if="model.state === 'disabled'"
      message="AI 비서를 준비하고 있습니다. 모델이 배포되면 여기서 쓸 수 있습니다."
    />
    <EmptyState v-else-if="model.state === 'unsupported'" :message="model.reason" />
    <EmptyState
      v-else-if="model.state === 'failed'"
      :message="model.reason"
      :actions="[{ label: '다시 시도', onClick: () => void initModel() }]"
    />
  </div>
</template>

<style scoped>
.gate {
  display: grid;
  place-items: center;
  height: 100%;
  padding: var(--space-5);
}
</style>
```

`web/src/admin/views/assistant/Examples.vue`:

```vue
<script setup lang="ts">
// 미리보기가 없을 때 '할 수 있는 일' (admin-assistant.md 「빈 상태 · 예문」). 누르면 입력칸에 채운다(바로 보내지 않는다)
const emit = defineEmits<{ pick: [text: string] }>()
const GROUPS: { title: string; items: string[] }[] = [
  {
    title: '날짜별 일정',
    items: [
      '803호 이번 주 금요일 15시부터 18시까지 특강',
      '다음 주 화요일 자료구조 휴강',
      '목요일 보강 잡아줘',
    ],
  },
  { title: '시험기간', items: ['801·803 12/15~19 시험기간'] },
  { title: '정규 시간표', items: ['803 월 9~12시 자료구조 김교수로 바꿔'] },
  { title: '학생 신청', items: ['대기 중인 신청 보여 줘', '801호 내일 신청 승인'] },
  { title: '조회', items: ['금요일 오후 빈 강의실?', '801 노드 배터리?'] },
]
</script>

<template>
  <div class="ex">
    <p class="ex__lead">이렇게 말해 보세요</p>
    <section v-for="g in GROUPS" :key="g.title" class="ex__group">
      <h3 class="ex__title">{{ g.title }}</h3>
      <ul class="ex__list">
        <li v-for="t in g.items" :key="t">
          <button type="button" class="ex__item" @click="emit('pick', t)">{{ t }}</button>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.ex__lead {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.ex__group + .ex__group {
  margin-top: var(--space-4);
}
.ex__title {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.ex__list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}
.ex__item {
  padding: var(--space-1) var(--space-3);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-full);
  background: var(--surface);
  color: var(--text-1);
  font: inherit;
  font-size: var(--font-size-md);
  cursor: pointer;
}
.ex__item:hover {
  background: var(--sunken);
}
</style>
```

`web/src/admin/views/AssistantView.vue`:

```vue
<script setup lang="ts">
import { onMounted } from 'vue'
import { initModel, model } from '../assistant/model'
import Examples from './assistant/Examples.vue'
import ModelGate from './assistant/ModelGate.vue'

// AI 비서 (admin-assistant.md) — 왼쪽 대화 380px, 오른쪽 확인. Task 7·8·10 이 채운다
onMounted(() => void initModel())
</script>

<template>
  <main class="as">
    <section class="as__chat" aria-label="AI 비서 대화">
      <ModelGate v-if="model.state !== 'ready'" />
    </section>
    <section class="as__side" aria-label="확인">
      <Examples />
    </section>
  </main>
</template>

<style scoped>
.as {
  display: grid;
  grid-template-columns: 380px minmax(0, 1fr);
  height: 100vh;
}
.as__chat {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-right: var(--border-thin) solid var(--line-2);
  background: var(--surface);
}
.as__side {
  min-width: 0;
  overflow: auto;
  padding: var(--space-5);
}
</style>
```

- [ ] **Step 6: 통과 + 커밋**

Run: `cd web && pnpm test src/admin` → PASS. `pnpm exec vue-tsc --noEmit && pnpm lint` → 오류 0.

```bash
git add web/src/admin/router.ts web/src/admin/AdminShell.vue web/src/admin/assistant/model.ts web/src/admin/views/AssistantView.vue web/src/admin/views/assistant/ModelGate.vue web/src/admin/views/assistant/Examples.vue web/src/admin/__tests__/shell.spec.ts web/src/admin/__tests__/router.spec.ts web/src/admin/__tests__/assistantView.spec.ts
git commit -m "feat(web): 사이드바 맨 위 AI 비서 탭 — 라우트, 모델 상태(준비 중·개발용 대역), 예문"
```

---

### Task 6: 대화 상태 — 턴 흐름 (모델 출력 → 재시도 → 서버), 선택 버튼, 판 불일치

> **화면 변경(2026-11-26, #176)**: 턴 흐름·재시도·판 불일치 로직은 그대로다. 다른 점 하나 — 화면에 대화 기록이 남지 않으므로 **창을 닫으면 `resetChat()`**(미리보기가 있으면 적용하지 않고 버린다 = 취소와 같다). `chat.msgs` 는 그대로 두되 명령창은 마지막 AI 메시지(질문·선택지·오류)만 그린다. "탭을 옮겼다 와도 대화가 남는다" 주석은 "창을 닫으면 사라진다"로 고친다.

**Files:**
- Create: `web/src/admin/assistant/conversation.ts`
- Test: `web/src/admin/__tests__/assistantChat.spec.ts`

**Interfaces:**
- Consumes: `assistantApi.turn`·`classify` (Task 3), `userMessage`·`parseForm` (Task 4), `engine()` (Task 5).
- Produces: `chat` (reactive: `msgs: ChatMsg[]`, `conversationId`, `nextPrefix`, `preview: PreviewOut | null`, `busy`, `applying`, `applied: Applied | null`, `modelStale`), `draft: Ref<string>`, `interface ChatMsg { id; who: 'admin' | 'ai'; text; choices: TurnChoice[]; answer: AnswerOut | null; error: boolean }`, `interface Applied { changeId: number; outboxIds: number[]; roomIds: number[] }`, `send(text: string): Promise<void>`, `pick(c: TurnChoice): Promise<void>`, `resetChat(): void`, 상수 `RETRY_TEMPERATURE = 0.3`, `NOT_UNDERSTOOD`, `MODEL_CHANGED`, `MODEL_FAILED`. Task 9 가 `applyPreview()`·`discardPreview()` 를 더한다.

- [ ] **Step 1: 실패하는 테스트 `web/src/admin/__tests__/assistantChat.spec.ts`**

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { assistantApi } from '@/api/assistant'
import type { TurnOut } from '@/api/types'
import {
  MODEL_CHANGED,
  NOT_UNDERSTOOD,
  RETRY_TEMPERATURE,
  chat,
  pick,
  resetChat,
  send,
} from '@/admin/assistant/conversation'
import { setEngine } from '@/admin/assistant/model'
import { STUB_MANIFEST } from '@/admin/assistant/adapters/stub'
import type { GenerateReq, ModelRunner } from '@/admin/assistant/runner'
import turnPreview from '@/api/__fixtures__/assistant-turn-preview.json'

vi.mock('@/api/assistant', async () => {
  const real = await vi.importActual<typeof import('@/api/assistant')>('@/api/assistant')
  return {
    ...real,
    assistantApi: { model: vi.fn(), turn: vi.fn(), apply: vi.fn(), changes: vi.fn() },
  }
})
const turn = vi.mocked(assistantApi.turn)
const FORM = '{"v":1,"intent":"event.add","target":{},"set":{"rooms":["803"]}}'
const ask = (o: Partial<TurnOut> = {}): TurnOut => ({
  conversation_id: 'c_1',
  kind: 'ask',
  message: '특강 이름은 무엇인가요?',
  choices: [],
  next_prefix: '상태: …\n질문: 특강 이름은 무엇인가요?\n관리자: ',
  closed: false,
  preview: null,
  answer: null,
  ...o,
})
function runner(outputs: string[]) {
  const calls: GenerateReq[] = []
  const r: ModelRunner = {
    load: async () => {},
    generate: async (req) => {
      calls.push(req)
      return outputs.shift() ?? ''
    },
    dispose: async () => {},
  }
  setEngine(r, STUB_MANIFEST)
  return calls
}

beforeEach(() => {
  resetChat()
  turn.mockReset()
})

describe('send', () => {
  it('첫 턴은 first_prefix, 서버 질문 뒤에는 next_prefix 로 모델에 넣는다', async () => {
    const calls = runner([FORM, '{"v":1,"intent":"fill","target":{},"set":{"subject":"알고리즘 특강"}}'])
    turn.mockResolvedValueOnce(ask())
    await send('  803호 금요일 15~18 특강 ')
    expect(calls[0].user).toBe('관리자: 803호 금요일 15~18 특강')
    expect(turn.mock.calls[0][0]).toEqual({
      conversation_id: null,
      utterance: '803호 금요일 15~18 특강',
      form: JSON.parse(FORM),
      choice: null,
    })
    expect(chat.conversationId).toBe('c_1')
    expect(chat.msgs.map((m) => [m.who, m.text])).toEqual([
      ['admin', '803호 금요일 15~18 특강'],
      ['ai', '특강 이름은 무엇인가요?'],
    ])
    turn.mockResolvedValueOnce(turnPreview as unknown as TurnOut)
    await send('알고리즘 특강')
    expect(calls[1].user).toBe('상태: …\n질문: 특강 이름은 무엇인가요?\n관리자: 알고리즘 특강')
    expect(turn.mock.calls[1][0].conversation_id).toBe('c_1')
    expect(chat.preview?.preview_id).toBe('p_1')
  })

  it('parse 실패면 온도를 올려 한 번 더, 또 실패면 원문을 raw_output 으로 보내고 서버 안내를 보인다', async () => {
    const calls = runner(['oops', 'still oops'])
    turn.mockResolvedValueOnce(
      ask({ kind: 'error', message: NOT_UNDERSTOOD, closed: true, next_prefix: null }),
    )
    await send('아무 말')
    expect(calls).toHaveLength(2)
    expect(calls[1].generation.temperature).toBe(RETRY_TEMPERATURE)
    expect(turn).toHaveBeenCalledWith({
      conversation_id: null,
      utterance: '아무 말',
      form: null,
      choice: null,
      raw_output: 'still oops',
    })
    expect(chat.msgs.at(-1)).toMatchObject({ who: 'ai', text: NOT_UNDERSTOOD, error: true })
  })

  it('closed 면 대화를 끝낸다 — 다음 턴은 새 대화 · first_prefix', async () => {
    const calls = runner([FORM, FORM])
    turn.mockResolvedValueOnce(ask({ kind: 'answer', closed: true, next_prefix: null }))
    await send('801 배터리?')
    expect(chat.conversationId).toBeNull()
    turn.mockResolvedValueOnce(ask())
    await send('803 금 특강')
    expect(calls[1].user).toBe('관리자: 803 금 특강')
    expect(turn.mock.calls[1][0].conversation_id).toBeNull()
  })

  it('409 schema_version → modelStale + 안내, 429 → 잠시 후 안내, 빈 문장·진행 중은 무시', async () => {
    runner([FORM, FORM])
    turn.mockRejectedValueOnce(new ApiError(409, 'x', [], { detail: 'schema_version' }))
    await send('803 금 특강')
    expect(chat.modelStale).toBe(true)
    expect(chat.msgs.at(-1)?.text).toBe(MODEL_CHANGED)
    turn.mockRejectedValueOnce(new ApiError(429, '잠시 후 다시 시도해 주세요.', [], { detail: 'x' }))
    await send('803 금 특강')
    expect(chat.msgs.at(-1)?.text).toBe('잠시 후 다시 시도해 주세요.')
    const n = chat.msgs.length
    await send('   ')
    expect(chat.msgs).toHaveLength(n)
  })

  it('모델 오류(Worker 실패)는 대화에 오류 말풍선', async () => {
    setEngine(
      {
        load: async () => {},
        generate: async () => {
          throw new Error('oom')
        },
        dispose: async () => {},
      },
      STUB_MANIFEST,
    )
    await send('803 금 특강')
    expect(chat.msgs.at(-1)).toMatchObject({ who: 'ai', error: true })
    expect(chat.busy).toBe(false)
  })
})

describe('pick', () => {
  it('선택 버튼은 모델 없이 choice 로, utterance 는 버튼 라벨', async () => {
    const calls = runner([FORM])
    turn.mockResolvedValueOnce(
      ask({ message: '어느 803 인가요?', choices: [{ id: 'room:12', label: '공학관 803' }] }),
    )
    await send('803 금 특강')
    turn.mockResolvedValueOnce(ask())
    await pick({ id: 'room:12', label: '공학관 803' })
    expect(calls).toHaveLength(1)
    expect(turn.mock.calls[1][0]).toEqual({
      conversation_id: 'c_1',
      utterance: '공학관 803',
      form: null,
      choice: 'room:12',
    })
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin/__tests__/assistantChat.spec.ts`
Expected: FAIL — `Failed to resolve import "@/admin/assistant/conversation"`.

- [ ] **Step 3: `web/src/admin/assistant/conversation.ts`**

```ts
import { reactive, ref } from 'vue'
import { ApiError, MESSAGES } from '@/api/client'
import { assistantApi, classify } from '@/api/assistant'
import type { AnswerOut, PreviewOut, TurnChoice, TurnOut } from '@/api/types'
import { engine } from './model'
import { parseForm, userMessage } from './prompt'

/** parse 실패 뒤 한 번 더 — 온도 0 이면 같은 답이 나오므로 조금 올린다 */
export const RETRY_TEMPERATURE = 0.3
export const NOT_UNDERSTOOD =
  '이해하지 못했습니다. 예: "801호 다음 주 금요일 15시부터 18시까지 특강"처럼 말씀해 주세요.'
export const MODEL_CHANGED = 'AI 모델이 새 판으로 바뀌었습니다. 새 모델을 받은 뒤 다시 말씀해 주세요.'
export const MODEL_FAILED = '모델이 답을 만들지 못했습니다. 다시 시도해 주세요.'

export interface ChatMsg {
  id: number
  who: 'admin' | 'ai'
  text: string
  choices: TurnChoice[]
  answer: AnswerOut | null
  error: boolean
}
export interface Applied {
  changeId: number
  outboxIds: number[]
  roomIds: number[]
}

/** 모듈 상태 — 탭을 옮겼다 와도 대화가 남는다(새로고침하면 사라진다) */
export const chat = reactive({
  msgs: [] as ChatMsg[],
  conversationId: null as string | null,
  nextPrefix: null as string | null,
  preview: null as PreviewOut | null,
  busy: false,
  applying: false,
  applied: null as Applied | null,
  /** 서버가 규격 판이 다르다고 했다 — 모델 화면이 안내를 다시 받는다 */
  modelStale: false,
})
/** 입력칸 — 예문을 누르면 여기에 채운다 */
export const draft = ref('')

let seq = 0
function say(who: ChatMsg['who'], text: string, extra: Partial<ChatMsg> = {}) {
  chat.msgs.push({ id: ++seq, who, text, choices: [], answer: null, error: false, ...extra })
}
function endConversation() {
  chat.conversationId = null
  chat.nextPrefix = null
}

export function resetChat() {
  chat.msgs = []
  endConversation()
  chat.preview = null
  chat.busy = false
  chat.applying = false
  chat.applied = null
  chat.modelStale = false
  draft.value = ''
}

/** 모델 출력 → 양식. 두 번 다 못 읽으면 form 은 null, raw 는 마지막 원문 */
async function formOf(utterance: string): Promise<{ form: Record<string, unknown> | null; raw: string }> {
  const e = engine()
  if (!e) throw new Error('모델이 준비되지 않았습니다')
  const req = {
    system: e.manifest.system_prompt,
    user: userMessage(chat.nextPrefix ?? e.manifest.first_prefix, utterance),
    schema: e.manifest.json_schema,
    generation: e.manifest.generation,
  }
  const out1 = await e.runner.generate(req)
  const first = parseForm(out1)
  if (first) return { form: first, raw: out1 }
  const again = { ...req, generation: { ...req.generation, temperature: RETRY_TEMPERATURE } }
  const out2 = await e.runner.generate(again)
  return { form: parseForm(out2), raw: out2 }
}

function take(t: TurnOut) {
  if (t.closed) endConversation()
  else {
    chat.conversationId = t.conversation_id
    chat.nextPrefix = t.next_prefix
  }
  chat.preview = t.kind === 'preview' ? t.preview : null
  say('ai', t.message, { choices: t.choices, answer: t.answer, error: t.kind === 'error' })
}

/** 서버 오류 → 대화 말풍선. 401·403 은 client 가 세션을 정리하므로 말하지 않는다 */
export function sayFailure(e: ApiError) {
  const f = classify(e)
  if (f?.kind === 'schema_version') {
    chat.modelStale = true
    say('ai', MODEL_CHANGED, { error: true })
    return
  }
  if (e.status === 401 || e.status === 403) return
  say('ai', f?.kind === 'rate' ? MESSAGES[429] : e.message, { error: true })
}

export async function send(text: string): Promise<void> {
  const utterance = text.trim()
  if (!utterance || chat.busy || !engine()) return
  chat.busy = true
  say('admin', utterance)
  try {
    const { form, raw } = await formOf(utterance)
    if (!form) {
      // 못 읽은 원문도 서버에 보낸다 — 학습용 기록(spec §5.5)에 남고, 답은 서버의 안내 문장(error)
      take(
        await assistantApi.turn({
          conversation_id: chat.conversationId,
          utterance,
          form: null,
          choice: null,
          raw_output: raw.slice(0, 2000),
        }),
      )
      return
    }
    take(
      await assistantApi.turn({
        conversation_id: chat.conversationId,
        utterance,
        form,
        choice: null,
      }),
    )
  } catch (e) {
    if (e instanceof ApiError) sayFailure(e)
    else if (e instanceof Error) say('ai', MODEL_FAILED, { error: true })
    else throw e
  } finally {
    chat.busy = false
  }
}

export async function pick(c: TurnChoice): Promise<void> {
  if (chat.busy || !chat.conversationId) return
  chat.busy = true
  say('admin', c.label)
  try {
    take(
      await assistantApi.turn({
        conversation_id: chat.conversationId,
        utterance: c.label,
        form: null,
        choice: c.id,
      }),
    )
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    sayFailure(e)
  } finally {
    chat.busy = false
  }
}

// Task 9 가 이 아래에 적용 흐름(applyPreview · discardPreview)을 더한다
```

- [ ] **Step 4: 통과 + 커밋**

Run: `cd web && pnpm test src/admin/__tests__/assistantChat.spec.ts` → PASS. `pnpm exec vue-tsc --noEmit && pnpm lint` → 오류 0.

```bash
git add web/src/admin/assistant/conversation.ts web/src/admin/__tests__/assistantChat.spec.ts
git commit -m "feat(web): AI 비서 대화 상태 — 모델 출력 1회 재시도, 서버 턴, 선택 버튼, 판 불일치"
```

---

### Task 7: 대화 화면 (`ChatPane`) — 말풍선·선택 버튼·조회 표·입력

> **화면 변경(2026-11-26, #176)**: `ChatPane.vue` 대신 **`views/assistant/CommandBar.vue`** — 한 줄 명령창(스펙 「명령창」·「보내는 중」·「되묻기」·「오류」). 아래 코드에서 바뀌는 것:
> - 입력: 테두리 없는 한 줄 입력칸(숨은 라벨 `AI 비서에게 말하기`, 최대 300자) + `primary` `sm` `보내기`. **Enter = 보내기, 한글 조합 중(`isComposing`) Enter 는 무시**, 빈 입력은 안 보냄. 여러 줄 `textarea`·Shift+Enter 없음.
> - 보내는 중: 보낸 문장(한 줄 말줄임) + `변경 내용을 정리하는 중…` + 머리 줄 아래 2px 진행 줄(`role="progressbar"`). 이 동안 입력 막음.
> - 되묻기(`kind: ask`): 머리 줄 아래 칸 — `AI` + 질문, 선택지가 있으면 `secondary` `sm` 버튼 줄(누르면 `pick`), 없으면 답 `Input`(360px) + `답하기` + `ghost` `요청 취소`(`resetChat`). 머리 줄에는 처음 보낸 문장이 남는다.
> - 오류(`kind: error`·모델 실패): 되묻기 칸 자리에 `danger` 한 줄 + 입력칸 다시 열림. 판 불일치는 `새로고침` 버튼.
> - **말풍선 목록·대화 기록이 없다.** `aria-live="polite"` 는 질문·결과 줄에.
> - 조회 답(`answer`) 표는 머지된 스펙에 자리가 없다 — 되묻기 칸 자리에 `Table` 로 그린다(스펙 「되묻기」 칸과 같은 바탕·패딩). 화면 스펙에 더할 일이면 cw 에게 이슈로.
> - 개발용 `manualOutput` 입력칸(개발 서버만)은 되묻기 칸 아래에 그대로 둔다.
> - 테스트 `assistantChatPane.spec.ts` → `assistantCommandBar.spec.ts`: 말풍선 대신 위 동작(조합 중 Enter 무시 포함)을 확인. `send`·`pick`·`draft` 를 쓰는 방식은 그대로.

**Files:**
- Create: `web/src/admin/views/assistant/ChatPane.vue`
- Modify: `web/src/admin/views/AssistantView.vue` (ready 면 ChatPane, 예문 클릭 → draft)
- Test: `web/src/admin/__tests__/assistantChatPane.spec.ts`

**Interfaces:**
- Consumes: `chat`·`draft`·`send`·`pick` (Task 6), `model.stub` (Task 5), `manualOutput` (Task 4).
- Produces: `ChatPane.vue` (props 없음, 모듈 상태를 그린다).

- [ ] **Step 1: 실패하는 테스트 `web/src/admin/__tests__/assistantChatPane.spec.ts`**

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ChatPane from '@/admin/views/assistant/ChatPane.vue'
import { chat, draft, resetChat, send } from '@/admin/assistant/conversation'
import { model } from '@/admin/assistant/model'

vi.mock('@/api/assistant', () => ({
  assistantApi: { model: vi.fn(), turn: vi.fn(), apply: vi.fn(), changes: vi.fn() },
  classify: vi.fn(() => null),
}))
// ES 모듈 내보내기는 spyOn 으로 바꿀 수 없다 — send 만 가짜로, 나머지(chat·draft)는 진짜
vi.mock('@/admin/assistant/conversation', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/admin/assistant/conversation')>()),
  send: vi.fn(async () => {}),
}))

beforeEach(() => {
  resetChat()
  model.stub = false
})

describe('ChatPane', () => {
  it('말풍선 — 관리자·AI·오류, 마지막 말풍선의 선택 버튼만 누를 수 있다', async () => {
    chat.msgs.push(
      { id: 1, who: 'admin', text: '803 금 특강', choices: [], answer: null, error: false },
      {
        id: 2,
        who: 'ai',
        text: '어느 803?',
        choices: [{ id: 'room:1', label: '공학관 803' }],
        answer: null,
        error: false,
      },
      {
        id: 3,
        who: 'ai',
        text: '이해하지 못했습니다.',
        choices: [{ id: 'x', label: '다시' }],
        answer: null,
        error: true,
      },
    )
    const w = mount(ChatPane)
    expect(w.findAll('.chat__msg--admin')).toHaveLength(1)
    expect(w.findAll('.chat__msg--error')).toHaveLength(1)
    const btns = w.findAll('.chat__choices button')
    expect(btns[0].attributes('disabled')).toBeDefined()
    expect(btns[1].attributes('disabled')).toBeUndefined()
  })

  it('조회 답은 표로', () => {
    chat.msgs.push({
      id: 1,
      who: 'ai',
      text: '찾았습니다.',
      choices: [],
      answer: { title: '빈 강의실', columns: ['강의실', '빈 시간'], rows: [['공학관 801', '13:00–18:00']] },
      error: false,
    })
    const w = mount(ChatPane)
    expect(w.get('.chat__answer-title').text()).toBe('빈 강의실')
    expect(w.findAll('th').map((t) => t.text())).toEqual(['강의실', '빈 시간'])
    expect(w.text()).toContain('공학관 801')
  })

  it('Enter 로 보내고 입력칸을 비운다, 한글 조합 중 Enter 와 Shift+Enter 는 보내지 않는다', async () => {
    const spy = vi.mocked(send)
    spy.mockClear()
    const w = mount(ChatPane)
    draft.value = '803 금 특강'
    await flushPromises()
    const ta = w.get('textarea')
    await ta.trigger('keydown', { key: 'Enter', isComposing: true })
    await ta.trigger('keydown', { key: 'Enter', shiftKey: true })
    expect(spy).not.toHaveBeenCalled()
    await ta.trigger('keydown', { key: 'Enter' })
    expect(spy).toHaveBeenCalledWith('803 금 특강')
    expect(draft.value).toBe('')
  })

  it('답을 만드는 중이면 생각하는 중 · 보내기 비활성, 개발용 manual 이면 모델 출력 입력칸', async () => {
    chat.busy = true
    model.stub = 'manual'
    const w = mount(ChatPane)
    expect(w.text()).toContain('생각하는 중…')
    expect(w.get('form button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(w.text()).toContain('모델 출력 (개발용 JSON)')
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin/__tests__/assistantChatPane.spec.ts`
Expected: FAIL — `ChatPane.vue` 없음.

- [ ] **Step 3: `ChatPane.vue`**

```vue
<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Table from '@/components/ui/Table.vue'
import type { AnswerOut } from '@/api/types'
import { manualOutput } from '../../assistant/adapters/stub'
import { chat, draft, pick, send } from '../../assistant/conversation'
import { model } from '../../assistant/model'

// 대화 열 (admin-assistant.md 「대화 열」) — 모듈 상태(chat)를 그린다
const MAX = 300
const list = ref<HTMLOListElement | null>(null)

const answerCols = (a: AnswerOut) => a.columns.map((label, j) => ({ key: `c${j}`, label }))
const answerRows = (a: AnswerOut) =>
  a.rows.map((r, i) => ({
    _k: String(i),
    ...Object.fromEntries(a.columns.map((_, j) => [`c${j}`, r[j] ?? ''])),
  }))

function submit() {
  const text = draft.value.trim()
  if (!text || chat.busy) return
  draft.value = ''
  void send(text)
}
function onEnter(e: KeyboardEvent) {
  if (e.isComposing || e.shiftKey) return // 한글 조합 중 · 줄바꿈
  e.preventDefault()
  submit()
}
watch(
  () => [chat.msgs.length, chat.busy],
  async () => {
    await nextTick()
    if (list.value) list.value.scrollTop = list.value.scrollHeight
  },
)
</script>

<template>
  <div class="chat">
    <ol ref="list" class="chat__list" aria-live="polite">
      <li
        v-for="(m, i) in chat.msgs"
        :key="m.id"
        class="chat__msg"
        :class="[`chat__msg--${m.who}`, { 'chat__msg--error': m.error }]"
      >
        <p class="chat__text">{{ m.text }}</p>
        <div v-if="m.answer" class="chat__answer">
          <p class="chat__answer-title">{{ m.answer.title }}</p>
          <Table
            :columns="answerCols(m.answer)"
            :rows="answerRows(m.answer)"
            row-key="_k"
            empty="조건에 맞는 항목이 없습니다"
          />
        </div>
        <div v-if="m.choices.length" class="chat__choices">
          <Button
            v-for="c in m.choices"
            :key="c.id"
            variant="secondary"
            size="sm"
            :disabled="chat.busy || i !== chat.msgs.length - 1"
            @click="pick(c)"
            >{{ c.label }}</Button
          >
        </div>
      </li>
      <li v-if="chat.busy" class="chat__msg chat__msg--ai chat__msg--wait">생각하는 중…</li>
    </ol>
    <form class="chat__form" @submit.prevent="submit">
      <Input
        v-if="model.stub === 'manual'"
        v-model="manualOutput"
        multiline
        size="sm"
        label="모델 출력 (개발용 JSON)"
      />
      <Input
        v-model="draft"
        multiline
        label="AI 비서에게 말하기"
        :maxlength="MAX"
        :disabled="chat.busy"
        @keydown.enter="onEnter"
      />
      <Button class="chat__send" type="submit" :disabled="chat.busy || !draft.trim()"
        >보내기</Button
      >
    </form>
  </div>
</template>

<style scoped>
.chat {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.chat__list {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--space-3);
  margin: 0;
  padding: var(--space-4);
  overflow: auto;
  list-style: none;
}
.chat__msg {
  max-width: 85%;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-lg);
  font-size: var(--font-size-md);
  color: var(--text-1);
}
.chat__msg--admin {
  align-self: flex-end;
  background: var(--brand-tint);
}
.chat__msg--ai {
  align-self: flex-start;
  background: var(--sunken);
}
.chat__msg--error {
  background: var(--room-busy-fill);
  color: var(--danger);
}
.chat__msg--wait {
  color: var(--text-3);
}
.chat__text {
  margin: 0;
  white-space: pre-wrap;
}
.chat__answer {
  margin-top: var(--space-2);
}
.chat__answer-title {
  margin: 0 0 var(--space-1);
  font-weight: var(--font-weight-bold);
}
.chat__choices {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-2);
}
.chat__form {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4) var(--space-4);
  border-top: var(--border-thin) solid var(--line-2);
}
.chat__send {
  align-self: flex-end;
}
</style>
```

(오류 말풍선 바탕은 스펙의 `red.50` 틴트 — 2층에 `red.50` 을 가리키는 이름이 `room-busy-fill` 뿐이라 그것을 쓴다. 토큰 가드를 지키는 방법이다. 이름이 어색하면 Task 0 스펙 PR 에서 `danger-tint` 2층 이름을 더하는 것으로 바꿀 수 있다 — 보고서의 제안 1.)

- [ ] **Step 4: `AssistantView.vue` 에 잇기**

script 에 추가:

```ts
import { draft } from '../assistant/conversation'
import ChatPane from './assistant/ChatPane.vue'
```

script 에 (템플릿에서 가져온 ref 에 직접 대입하지 않는다):

```ts
function pickExample(t: string) {
  draft.value = t
}
```

template 의 `<section class="as__chat" …>` 안을:

```vue
      <ModelGate v-if="model.state !== 'ready'" />
      <ChatPane v-else />
```

`<Examples />` 를 `<Examples @pick="pickExample" />` 로.

- [ ] **Step 5: 통과 + 커밋**

Run: `cd web && pnpm test src/admin/__tests__/assistantChatPane.spec.ts src/admin/__tests__/assistantView.spec.ts` → PASS. (`Input` 이 `maxlength`·`@keydown` 을 `$attrs` 로 안쪽 `textarea` 에 넘긴다 — `Input.vue` 56행 `v-bind="$attrs"`.)

```bash
git add web/src/admin/views/assistant/ChatPane.vue web/src/admin/views/AssistantView.vue web/src/admin/__tests__/assistantChatPane.spec.ts
git commit -m "feat(web): AI 비서 대화 화면 — 말풍선, 선택 버튼, 조회 표, Enter 보내기"
```

---

### Task 8: 전·후 비교 — `diff.ts`, WeekGrid 변경 표시, `PreviewPane`

> 선행: Task 1(diff 토큰), Task 2(WeekGrid).

> **화면 변경(2026-11-26, #176)**: `diff.ts`(변경 표시 계산)와 WeekGrid 새 props(`showDates`·`cells`·`mark`·`examMark`)는 **그대로**. `PreviewPane.vue` 대신 **`views/assistant/ConfirmPanel.vue`**(같은 props `{ preview, applying }`, emits `apply`·`discard`) — 명령창이 아래로 펼쳐진 확인 창(스펙 「확인 — 펼친 창」):
> - 머리 줄: 보낸 문장 · `HH:MM 까지` · ×. 아래 줄(64px): `변경 N건 · 겹침 N건` · `[취소]` `[적용]`(막음이 있으면 비활성, 적용 중 `loading`).
> - **왼쪽 340px**: 제목 `변경 확인 · {강의실}`(여럿이면 `강의실 N곳`) · 요약 · 막음(`적용할 수 없습니다:` + `danger`, `role="alert"`) · 경고(`⚠`) · 안내(`text.3`) · **하루 막대**(바뀌는 날마다 `기존`/`수정` 두 줄, 09~18시 기본, 겹친 구간 `danger` 3px, 최대 3일 + `외 N일`) · 만료 안내 줄. 강의실이 둘 이상이면 제목 아래 강의실 표(행 누르면 하루 막대·격자가 그 강의실로).
> - **오른쪽**: 제목(`MM/DD~MM/DD 주` 또는 `매주 시간표`, 여러 주면 `◀` `▶`) + `SegmentedControl` `기존 | 수정`(기본 `수정`) + **읽기 전용 WeekGrid 하나**. 두 쪽이 **같은 시각 범위**를 쓴다(전환해도 행이 안 움직임) — 두 쪽 블록을 합쳐 `gridRange` 를 한 번 구한다.
> - 변경 표시는 블록 테두리 2px + 머리 태그(`+ 추가`·`− 삭제`·`~ 수정`)만, 바탕은 `room.*` 그대로(아래 WeekGrid 코드 그대로).
> - 하루 막대는 새 순수 함수로 계산한다(`diff.ts` 에 `dayBars(preview, roomId) → { date, before, after, overlaps }[]` 를 더하고 테스트). 왼쪽·오른쪽 두 열은 각각 스크롤.
> - 좁은 화면 덮개(Step 6 의 1024~1279px 분기)는 없앤다.
> - 테스트 `assistantDiff.spec.ts` 의 `PreviewPane` describe 는 `ConfirmPanel` 로: 격자가 **하나**이고 `기존 | 수정` 전환으로 바뀌는지, 막음 시 `[적용]` 비활성, 4일 이상이면 `외 N일`.

**Files:**
- Create: `web/src/admin/assistant/diff.ts`
- Modify: `web/src/admin/views/week/WeekGrid.vue` (props `showDates`·`cells`·`mark`·`examMark`, 태그·클래스)
- Create: `web/src/admin/views/assistant/PreviewPane.vue`
- Modify: `web/src/admin/views/AssistantView.vue` (미리보기가 있으면 PreviewPane, 좁은 화면 덮개)
- Test: `web/src/admin/__tests__/assistantDiff.spec.ts`

**Interfaces:**
- Consumes: `PreviewOut`·`PreviewMark`·`DiffOp` (Task 3), `WeekGrid` (Task 2), `weekBlocks`·`needsNight`·`needsWeekend` (`weekView.ts`).
- Produces:
  - `diff.ts`: `slotMarkKey(day, h, m): string`, `markIndex(changes): Map<string, PreviewMark>`, `blockMarks(b: Block, idx): PreviewMark[]`, `blockMark(b, idx): DiffOp | undefined`, `examMarkOn(exams: ExamOut[], idx, date: string): DiffOp | undefined`, `sideMark(op, side: 'before' | 'after'): DiffOp | undefined`, `MARK_TAG: Record<DiffOp, string>`, `FIELD_LABEL`, `fieldsText(fields: string[]): string`
  - WeekGrid 새 props: `showDates?: boolean`(기본 true), `cells?: boolean`(기본 true — false 면 셀을 버튼이 아닌 칸으로), `mark?: (p: Placed) => DiffOp | undefined`, `examMark?: (date: string) => DiffOp | undefined`
  - `PreviewPane.vue`: props `{ preview: PreviewOut; applying: boolean }`, emits `apply: []`, `discard: []`

- [ ] **Step 1: 실패하는 테스트 `web/src/admin/__tests__/assistantDiff.spec.ts`**

```ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import {
  blockMark,
  examMarkOn,
  fieldsText,
  markIndex,
  sideMark,
  slotMarkKey,
} from '@/admin/assistant/diff'
import { weekBlocks } from '@/admin/weekView'
import PreviewPane from '@/admin/views/assistant/PreviewPane.vue'
import { revivePreview } from '@/api/assistant'
import type { PreviewOut, SlotWithRoom } from '@/api/types'
import turnPreview from '@/api/__fixtures__/assistant-turn-preview.json'

const preview = (): PreviewOut => revivePreview(turnPreview.preview as unknown as PreviewOut)
const S = (o: Partial<SlotWithRoom> = {}): SlotWithRoom => ({
  id: 1,
  room_id: 3,
  day: 1,
  s_h: 9,
  s_m: 0,
  e_h: 9,
  e_m: 50,
  type: 1,
  subject: '자료구조',
  professor: '김교수',
  source: 2,
  ...o,
})

describe('diff', () => {
  it('slotMarkKey — d{day}-{HHMM}', () => {
    expect(slotMarkKey(5, 9, 5)).toBe('d5-0905')
  })

  it('예약은 r{id}, 연속 교시 묶음은 모두 같으면 그 표시 · 일부만이면 change', () => {
    const MON = '2026-11-23'
    const slots = [S(), S({ id: 2, s_h: 10, s_m: 0, e_h: 10, e_m: 50 })]
    const [group] = weekBlocks(slots, [], MON)
    expect(blockMark(group, markIndex([{ entity: 'slot', key: 'd1-0900', op: 'add', fields: [] }, { entity: 'slot', key: 'd1-1000', op: 'add', fields: [] }]))).toBe('add')
    expect(blockMark(group, markIndex([{ entity: 'slot', key: 'd1-1000', op: 'add', fields: [] }]))).toBe('change')
    expect(blockMark(group, markIndex([]))).toBeUndefined()
    const p = preview()
    const after = weekBlocks(p.rooms[0].weeks[0].after.slots, p.rooms[0].weeks[0].after.reservations, MON)
    const idx = markIndex(p.rooms[0].weeks[0].changes)
    expect(after.map((b) => blockMark(b, idx))).toEqual([undefined, undefined, 'add'])
  })

  it('시험기간 날짜 표시 · 쪽 가르기 · 바뀐 칸 글자', () => {
    const idx = markIndex([{ entity: 'exam', key: 'e4', op: 'remove', fields: [] }])
    const exams = [{ id: 4, room_id: 3, date_start: '2026-12-15', date_end: '2026-12-19' }]
    expect(examMarkOn(exams, idx, '2026-12-16')).toBe('remove')
    expect(examMarkOn(exams, idx, '2026-12-20')).toBeUndefined()
    expect(sideMark('add', 'before')).toBeUndefined()
    expect(sideMark('add', 'after')).toBe('add')
    expect(sideMark('remove', 'after')).toBeUndefined()
    expect(sideMark('change', 'before')).toBe('change')
    expect(fieldsText(['s_h', 's_m', 'subject'])).toBe('시작 · 이름')
  })
})

describe('PreviewPane', () => {
  it('요약 · 경고 · 기존│수정 두 격자, 추가 블록은 수정 쪽에만 + 추가 태그', () => {
    const w = mount(PreviewPane, { props: { preview: preview(), applying: false } })
    expect(w.text()).toContain('특강 "알고리즘 특강"')
    expect(w.text()).toContain('⚠ 기존 수업 "자료구조"')
    const sides = w.findAll('.pv__side')
    expect(sides.map((s) => s.get('figcaption').text())).toEqual(['기존', '수정'])
    expect(sides[0].findAll('.wk__tag')).toHaveLength(0)
    expect(sides[1].findAll('.wk__tag').map((t) => t.text())).toEqual(['+ 추가'])
    expect(sides[1].find('.wk__block--add').exists()).toBe(true)
    // 편집 없는 격자 — 셀은 버튼이 아니다
    expect(sides[0].findAll('button.wk__cell')).toHaveLength(0)
    expect(w.text()).toContain('공학관 803 · 11/23~11/29 주')
  })

  it('막음이 있으면 적용 비활성 + alert, 적용·취소 이벤트', async () => {
    const p = { ...preview(), blockers: ['지난 날짜입니다'] }
    const w = mount(PreviewPane, { props: { preview: p, applying: false } })
    expect(w.get('[role="alert"]').text()).toContain('지난 날짜입니다')
    const [cancel, apply] = w.findAll('.pv__actions button')
    expect(apply.attributes('disabled')).toBeDefined()
    await cancel.trigger('click')
    expect(w.emitted('discard')).toHaveLength(1)
    const ok = mount(PreviewPane, { props: { preview: preview(), applying: false } })
    await ok.findAll('.pv__actions button')[1].trigger('click')
    expect(ok.emitted('apply')).toHaveLength(1)
  })

  it('강의실이 둘 이상이면 요약 표, 행을 누르면 그 강의실 격자', async () => {
    const base = preview()
    const two = {
      ...base,
      rooms: [base.rooms[0], { ...base.rooms[0], room_id: 4, label: '공학관 801', added: 2 }],
    }
    const w = mount(PreviewPane, { props: { preview: two, applying: false } })
    expect(w.findAll('.pv__rooms tbody tr')).toHaveLength(2)
    await w.findAll('.pv__room-pick')[1].trigger('click')
    expect(w.get('.pv__week h3').text()).toContain('공학관 801')
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin/__tests__/assistantDiff.spec.ts`
Expected: FAIL — `Failed to resolve import "@/admin/assistant/diff"`.

- [ ] **Step 3: `web/src/admin/assistant/diff.ts`**

```ts
import type { DiffOp, ExamOut, PreviewMark } from '@/api/types'
import type { Block } from '../weekView'

// 미리보기 changes(부록 §4.2) → 격자 블록 표시. 서버가 계산한 표시를 키로 찾아 붙이기만 한다(다시 비교하지 않는다)
const pad = (n: number) => String(n).padStart(2, '0')
export const slotMarkKey = (day: number, h: number, m: number) => `d${day}-${pad(h)}${pad(m)}`
export const markIndex = (changes: PreviewMark[]) => new Map(changes.map((c) => [c.key, c]))

/** 블록에 걸린 표시들 — 예약은 하나, 연속 교시 묶음은 교시마다 */
export function blockMarks(b: Block, idx: Map<string, PreviewMark>): PreviewMark[] {
  if (b.resv) {
    const m = idx.get(`r${b.resv.id}`)
    return m ? [m] : []
  }
  const slots = b.group?.slots ?? (b.slot ? [b.slot] : [])
  return slots
    .map((s) => idx.get(slotMarkKey(s.day, s.s_h, s.s_m)))
    .filter((m): m is PreviewMark => !!m)
}

/** 묶음 안 교시가 모두 같은 표시면 그것, 일부만 바뀌었거나 섞였으면 change (admin-assistant.md 「변경 표시」) */
export function blockMark(b: Block, idx: Map<string, PreviewMark>): DiffOp | undefined {
  const marks = blockMarks(b, idx)
  if (!marks.length) return undefined
  const size = b.resv ? 1 : (b.group?.slots.length ?? 1)
  const op = marks[0].op
  return marks.length === size && marks.every((m) => m.op === op) ? op : 'change'
}

export function examMarkOn(
  exams: ExamOut[],
  idx: Map<string, PreviewMark>,
  date: string,
): DiffOp | undefined {
  for (const x of exams)
    if (x.date_start <= date && date <= x.date_end) {
      const m = idx.get(`e${x.id}`)
      if (m) return m.op
    }
  return undefined
}

/** 추가는 수정 쪽에만, 삭제는 기존 쪽에만, 수정은 양쪽 */
export function sideMark(op: DiffOp | undefined, side: 'before' | 'after'): DiffOp | undefined {
  if (!op) return undefined
  if (side === 'before') return op === 'add' ? undefined : op
  return op === 'remove' ? undefined : op
}

export const MARK_TAG: Record<DiffOp, string> = { add: '+ 추가', remove: '− 삭제', change: '~ 수정' }
export const FIELD_LABEL: Record<string, string> = {
  s_h: '시작',
  s_m: '시작',
  e_h: '끝',
  e_m: '끝',
  subject: '이름',
  professor: '교수',
  type: '유형',
  date: '날짜',
  day: '요일',
  date_start: '시작일',
  date_end: '끝일',
}
export const fieldsText = (fields: string[]) =>
  [...new Set(fields.map((f) => FIELD_LABEL[f] ?? f))].join(' · ')
```

- [ ] **Step 4: WeekGrid 변경 표시**

`WeekGrid.vue` script — import 에 `import type { DiffOp, ExamOut } from '@/api/types'`(기존 `ExamOut` import 를 이것으로) 와 `import { MARK_TAG } from '../../assistant/diff'` 를 더하고, props 정의에 넷을 더한다:

```ts
    /** false 면 요일 헤더에 날짜를 적지 않는다(정규 시간표만 바뀐 미리보기) */
    showDates?: boolean
    /** false 면 셀이 버튼이 아니다(읽기 전용 격자) */
    cells?: boolean
    mark?: (p: Placed) => DiffOp | undefined
    examMark?: (date: string) => DiffOp | undefined
```

withDefaults 에:

```ts
    showDates: true,
    cells: true,
    mark: () => undefined,
    examMark: () => undefined,
```

`blockClass` 반환 객체에 한 줄(아래 세 키)을 더한다:

```ts
    [`wk__block--${props.mark(p)}`]: !!props.mark(p),
```

`blockName` 을 표시까지 읽게 바꾼다:

```ts
const blockName = (p: Placed) => {
  const m = props.mark(p)
  const base = `${DAYS[p.day - 1]} ${clock(p.s)}–${clock(p.e)} ${blockLabel(p)} ${p.slot?.subject ?? p.resv?.subject ?? ''}`.trim()
  return m ? `${base}, ${MARK_TAG[m].slice(2)}` : base
}
```

template — 요일 헤더 날짜 span 에 `v-if="showDates"` 를 붙이고, `<span v-if="d.exam" class="wk__exam">시험기간</span>` 다음에:

```vue
        <span v-if="d.exam && examMark(d.date)" class="wk__tag" :class="`wk__tag--${examMark(d.date)}`">{{
          MARK_TAG[examMark(d.date)!]
        }}</span>
```

셀 `<button v-for="t in rows" …/>` 를 다음으로 바꾼다(`cells` 가 false 면 누를 수 없는 칸만):

```vue
        <template v-if="cells">
          <button
            v-for="t in rows"
            :key="t"
            type="button"
            class="wk__cell"
            :disabled="!editable"
            :aria-label="`${DAYS[d.day - 1]} ${clock(t)} 시간표 추가`"
            @click="emit('cell', { day: d.day, t })"
          />
        </template>
        <template v-else>
          <div v-for="t in rows" :key="t" class="wk__cell wk__cell--static" aria-hidden="true" />
        </template>
```

블록 안 `<span class="wk__label">` **앞**에:

```vue
            <span v-if="mark(p)" class="wk__tag" :class="`wk__tag--${mark(p)}`">{{
              MARK_TAG[mark(p)!]
            }}</span>
```

style 끝에:

```css
.wk__cell--static {
  cursor: default;
}
/* AI 비서 확인 화면 — 바탕은 상태 색 그대로, 테두리 2px + 태그만 (admin-assistant.md 「변경 표시」) */
.wk__block--add {
  border: var(--border-thick) solid var(--diff-add-line);
}
.wk__block--remove {
  border: var(--border-thick) dashed var(--diff-remove-line);
}
.wk__block--remove .wk__subject {
  text-decoration: line-through;
}
.wk__block--change {
  border: var(--border-thick) solid var(--diff-change-line);
}
.wk__tag {
  align-self: flex-start;
  padding: 0 var(--space-1);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  white-space: nowrap;
}
.wk__tag--add {
  background: var(--diff-add-fill);
  color: var(--diff-add-text);
}
.wk__tag--remove {
  background: var(--diff-remove-fill);
  color: var(--diff-remove-text);
}
.wk__tag--change {
  background: var(--diff-change-fill);
  color: var(--diff-change-text);
}
```

- [ ] **Step 5: `PreviewPane.vue`**

```vue
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import Table from '@/components/ui/Table.vue'
import type { PreviewOut, PreviewWeek, WeekData } from '@/api/types'
import { addDays, formatHm, kstDateStr, md, mondayOf } from '@/lib/time'
import {
  blockMark,
  blockMarks,
  examMarkOn,
  fieldsText,
  markIndex,
  sideMark,
} from '../../assistant/diff'
import { needsNight, needsWeekend, weekBlocks, type Placed } from '../../weekView'
import WeekGrid from '../week/WeekGrid.vue'

// 확인 열 — 미리보기 (admin-assistant.md 「확인 열 — 미리보기」)
const props = defineProps<{ preview: PreviewOut; applying: boolean }>()
const emit = defineEmits<{ apply: []; discard: [] }>()

const roomId = ref<number | null>(props.preview.rooms[0]?.room_id ?? null)
watch(
  () => props.preview.preview_id,
  () => (roomId.value = props.preview.rooms[0]?.room_id ?? null),
)
const room = computed(
  () => props.preview.rooms.find((r) => r.room_id === roomId.value) ?? props.preview.rooms[0],
)
const until = computed(() => formatHm(props.preview.expires_at))
const ROOM_COLS = [
  { key: 'label', label: '강의실' },
  { key: 'added', label: '추가', align: 'right' as const },
  { key: 'removed', label: '삭제', align: 'right' as const },
  { key: 'changed', label: '수정', align: 'right' as const },
]
const roomRows = computed(() =>
  props.preview.rooms.map((r) => ({
    room_id: r.room_id,
    label: r.label,
    added: r.added,
    removed: r.removed,
    changed: r.changed,
  })),
)

/** 한 주의 기존│수정 두 격자 — 같은 시각 범위·야간·주말을 쓴다 */
function grids(w: PreviewWeek) {
  const idx = markIndex(w.changes)
  const monday = w.week_start ?? mondayOf(kstDateStr(new Date()))
  const blocksOf = (d: WeekData) => weekBlocks(d.slots, w.week_start ? d.reservations : [], monday)
  const before = blocksOf(w.before)
  const after = blocksOf(w.after)
  const all = [...before, ...after]
  const common = {
    monday,
    rangeBlocks: all,
    night: needsNight(all),
    weekend: needsWeekend(all),
    showDates: !!w.week_start,
    cells: false,
    blockTitle: (p: Placed) => {
      const changed = blockMarks(p, idx).find((m) => m.op === 'change')
      return changed?.fields.length ? `바뀐 칸: ${fieldsText(changed.fields)}` : undefined
    },
  }
  const side = (which: 'before' | 'after', blocks: typeof before, data: WeekData) => ({
    ...common,
    blocks,
    exams: w.week_start ? data.exams : [],
    mark: (p: Placed) => sideMark(blockMark(p, idx), which),
    examMark: (date: string) => sideMark(examMarkOn(data.exams, idx, date), which),
  })
  return { before: side('before', before, w.before), after: side('after', after, w.after) }
}
const weeks = computed(() =>
  (room.value?.weeks ?? []).map((w) => ({
    key: w.week_start ?? 'weekly',
    title: w.week_start
      ? `${room.value!.label} · ${md(w.week_start)}~${md(addDays(w.week_start, 6))} 주`
      : `${room.value!.label} · 매주 시간표`,
    g: grids(w),
  })),
)
</script>

<template>
  <section class="pv" aria-label="변경 확인">
    <header class="pv__head">
      <h2 class="pv__title">변경 확인</h2>
      <span class="pv__until num">{{ until }} 까지</span>
    </header>
    <ul class="pv__summary">
      <li v-for="(s, i) in preview.summary" :key="i">{{ s }}</li>
    </ul>
    <div v-if="preview.blockers.length" class="pv__blockers" role="alert">
      <p>적용할 수 없습니다:</p>
      <ul>
        <li v-for="(b, i) in preview.blockers" :key="i">{{ b }}</li>
      </ul>
    </div>
    <ul v-if="preview.warnings.length" class="pv__warnings">
      <li v-for="(x, i) in preview.warnings" :key="i">⚠ {{ x }}</li>
    </ul>
    <ul v-if="preview.notices.length" class="pv__notices">
      <li v-for="(x, i) in preview.notices" :key="i">{{ x }}</li>
    </ul>
    <div v-if="preview.rooms.length > 1" class="pv__rooms">
      <Table :columns="ROOM_COLS" :rows="roomRows" row-key="room_id" :selected="[String(room?.room_id)]">
        <template #cell-label="{ row }">
          <button type="button" class="pv__room-pick" @click="roomId = Number(row.room_id)">
            {{ row.label }}
          </button>
        </template>
      </Table>
    </div>
    <div v-for="w in weeks" :key="w.key" class="pv__week">
      <h3 class="pv__week-title">{{ w.title }}</h3>
      <div class="pv__pair">
        <figure class="pv__side">
          <figcaption>기존</figcaption>
          <WeekGrid v-bind="w.g.before" />
        </figure>
        <figure class="pv__side">
          <figcaption>수정</figcaption>
          <WeekGrid v-bind="w.g.after" />
        </figure>
      </div>
    </div>
    <footer class="pv__actions">
      <Button variant="secondary" :disabled="applying" @click="emit('discard')">취소</Button>
      <Button :disabled="!!preview.blockers.length" :loading="applying" @click="emit('apply')"
        >적용</Button
      >
    </footer>
  </section>
</template>

<style scoped>
.pv__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.pv__title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.pv__until,
.pv__notices {
  color: var(--text-3);
  font-size: var(--font-size-sm);
}
.pv__summary,
.pv__warnings,
.pv__notices,
.pv__blockers ul {
  margin: var(--space-2) 0 0;
  padding-left: var(--space-4);
  font-size: var(--font-size-md);
}
.pv__blockers {
  margin-top: var(--space-3);
  color: var(--danger);
  font-size: var(--font-size-md);
}
.pv__blockers p {
  margin: 0;
  font-weight: var(--font-weight-bold);
}
.pv__rooms {
  margin-top: var(--space-4);
}
.pv__room-pick {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-1);
  font: inherit;
  cursor: pointer;
}
.pv__week {
  margin-top: var(--space-5);
}
.pv__week-title {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-md);
}
.pv__pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
}
.pv__side {
  min-width: 0;
  margin: 0;
}
.pv__side figcaption {
  margin-bottom: var(--space-1);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
  color: var(--text-2);
}
.pv__actions {
  position: sticky;
  bottom: 0;
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  margin-top: var(--space-4);
  padding: var(--space-3) 0;
  background: var(--bg);
}
</style>
```

(`formatHm(d: Date)` 는 `src/lib/time.ts` 29행에 있다 — KST `HH:MM`.)

- [ ] **Step 6: `AssistantView.vue` — 미리보기 자리 · 좁은 화면 덮개**

script 에 추가:

```ts
import { ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import Banner from '@/components/ui/Banner.vue'
import { chat } from '../assistant/conversation'
import PreviewPane from './assistant/PreviewPane.vue'

// 1024~1279px — 확인 열이 대화를 덮는다 (admin-assistant.md 「좁은 화면」). 미리보기가 오면 연다
const sideOpen = ref(false)
watch(
  () => chat.preview?.preview_id,
  (id) => (sideOpen.value = !!id),
)
```

(`onMounted` import 줄은 `import { onMounted, ref, watch } from 'vue'` 로 합친다.)

template 을:

```vue
<template>
  <main class="as">
    <section class="as__chat" aria-label="AI 비서 대화">
      <Banner
        v-if="chat.preview && !sideOpen"
        class="as__reopen"
        message="확인할 변경이 있습니다"
        :dismissible="false"
      />
      <Button v-if="chat.preview && !sideOpen" class="as__reopen-btn" variant="ghost" size="sm" @click="sideOpen = true"
        >확인 열기</Button
      >
      <ModelGate v-if="model.state !== 'ready'" />
      <ChatPane v-else />
    </section>
    <section class="as__side" :class="{ 'as__side--open': sideOpen }" aria-label="확인">
      <Button class="as__back" variant="ghost" size="sm" @click="sideOpen = false">← 대화로</Button>
      <PreviewPane
        v-if="chat.preview"
        :preview="chat.preview"
        :applying="chat.applying"
        @apply="onApply"
        @discard="onDiscard"
      />
      <Examples v-else @pick="pickExample" />
    </section>
  </main>
</template>
```

(이 화면의 조각들은 Task 10 Step 4 에서 전문으로 한 번 정리한다.) `onApply`·`onDiscard` 는 Task 9 에서 채운다 — 이 Task 에서는 script 에 빈 함수로 둔다:

```ts
function onApply() {}
function onDiscard() {}
```

style 에 추가:

```css
.as__back,
.as__reopen-btn,
.as__reopen {
  display: none;
}
/* 좁은 화면 — 확인 열이 대화를 덮는다 */
@media (max-width: 1279px) {
  .as {
    grid-template-columns: minmax(0, 1fr);
  }
  .as__side {
    display: none;
  }
  .as__side--open {
    position: fixed;
    inset: 0;
    z-index: 20;
    display: block;
    background: var(--bg);
  }
  .as__back {
    display: inline-flex;
    margin-bottom: var(--space-3);
  }
  .as__reopen {
    display: block;
    margin: var(--space-3) var(--space-4) 0;
  }
  .as__reopen-btn {
    display: inline-flex;
    align-self: flex-end;
    margin: var(--space-1) var(--space-4) 0;
  }
}
```

- [ ] **Step 7: 통과 + 커밋**

Run: `cd web && pnpm test src/admin` → PASS (`weekGrid.spec.ts`·`week.spec.ts` 포함 — WeekGrid 기본값이 기존 동작 그대로). `pnpm exec vue-tsc --noEmit && pnpm lint` → 오류 0.

```bash
git add web/src/admin/assistant/diff.ts web/src/admin/views/week/WeekGrid.vue web/src/admin/views/assistant/PreviewPane.vue web/src/admin/views/AssistantView.vue web/src/admin/__tests__/assistantDiff.spec.ts
git commit -m "feat(web): AI 비서 확인 화면 — 기존│수정 주간 격자, 추가·삭제·수정 표시, 강의실 요약 표"
```

---

### Task 9: 적용 흐름 — [적용]/[취소], 409 stale · 410 · 422, 전송 추적

> **화면 변경(2026-11-26, #176)**: `applyPreview`·`discardPreview`·409/410/422 처리·전송 추적 로직은 **그대로**. 그리는 자리만 바뀐다(스펙 「적용 후」·「오류」): 적용하면 펼친 창이 한 줄로 접히고 머리 줄에 `적용했습니다. 문 앞 화면으로 보내는 중입니다.` + `OutboxDot`(`ApplyTrack.vue`) — `acked` 면 3초 뒤 창을 닫고, `failed` 면 닫지 않고, 30초 뒤에도 안 끝나면 3초 뒤 닫는다. 409 `stale` 은 새 미리보기 + 왼쪽 열 맨 위 `Banner`, 410 은 한 줄로 접고 `danger` 문구 + 입력칸. 적용 뒤 **뒤 화면(주간 시간표 등)을 다시 불러온다** — 창이 라우트 밖에 있으므로 `AssistantPanel` 이 적용 완료 이벤트를 내고 열린 화면이 받아 다시 불러온다(또는 `router.replace` 로 같은 주소 다시 그리기 — 둘 중 단순한 쪽). `AssistantView.vue` 를 고치는 Step 은 `AssistantPanel.vue` 에 한다.

**Files:**
- Modify: `web/src/admin/assistant/conversation.ts` (`applyPreview`, `discardPreview`, 문구 상수)
- Modify: `web/src/admin/views/AssistantView.vue` (`onApply`·`onDiscard`, 전송 추적)
- Create: `web/src/admin/views/assistant/ApplyTrack.vue`
- Test: `web/src/admin/__tests__/assistantChat.spec.ts` (적용 describe 추가), `web/src/admin/__tests__/assistantView.spec.ts` (추적)

**Interfaces:**
- Consumes: `assistantApi.apply`·`classify` (Task 3), `useOutboxTracker` (`web/src/admin/outboxTrack.ts` — `track(key, buildingId, ids)`, `states`), `worst` (같은 파일), `roomsApi.rooms()`.
- Produces: `applyPreview(): Promise<void>`, `discardPreview(): void`, 상수 `APPLIED`·`STALE`·`EXPIRED`·`DISCARDED`; `ApplyTrack.vue` props `{ applied: Applied }`.

- [ ] **Step 1: 실패하는 테스트 — `assistantChat.spec.ts`**

파일 위 `@/admin/assistant/conversation` import 목록에 `APPLIED, EXPIRED, STALE, applyPreview, discardPreview` 를 더하고, 파일 끝에 추가:

```ts
describe('applyPreview', () => {
  const apply = vi.mocked(assistantApi.apply)
  const setPreview = () => {
    chat.preview = (turnPreview as unknown as TurnOut).preview
    chat.conversationId = 'c_1'
    chat.nextPrefix = 'x'
  }
  beforeEach(() => apply.mockReset())

  it('200 — 대화를 끝내고 적용 기록(방 id 포함), 미리보기 닫기', async () => {
    setPreview()
    apply.mockResolvedValue({ change_id: 41, outbox_ids: [512] })
    await applyPreview()
    expect(apply).toHaveBeenCalledWith('p_1')
    expect(chat.applied).toEqual({ changeId: 41, outboxIds: [512], roomIds: [3] })
    expect(chat.preview).toBeNull()
    expect(chat.conversationId).toBeNull()
    expect(chat.msgs.at(-1)?.text).toBe(APPLIED)
  })

  it('409 stale → 새 미리보기로 교체 + 안내, 410 → 닫기 + 만료 안내, 422 → blockers 갱신', async () => {
    setPreview()
    const fresh = { ...(turnPreview.preview as object), preview_id: 'p_2' }
    apply.mockRejectedValueOnce(new ApiError(409, 'x', [], { detail: 'stale', preview: fresh }))
    await applyPreview()
    expect(chat.preview?.preview_id).toBe('p_2')
    expect(chat.msgs.at(-1)?.text).toBe(STALE)
    apply.mockRejectedValueOnce(new ApiError(410, 'x', [], { detail: 'expired' }))
    await applyPreview()
    expect(chat.preview).toBeNull()
    expect(chat.msgs.at(-1)?.text).toBe(EXPIRED)
    setPreview()
    apply.mockRejectedValueOnce(
      new ApiError(422, 'x', [], { detail: 'blocked', blockers: ['노드 용량 24 초과'] }),
    )
    await applyPreview()
    expect(chat.preview?.blockers).toEqual(['노드 용량 24 초과'])
  })

  it('막음이 있거나 적용 중이면 부르지 않는다, 취소는 미리보기·대화를 닫는다', async () => {
    setPreview()
    chat.preview = { ...chat.preview!, blockers: ['지난 날짜'] }
    await applyPreview()
    expect(apply).not.toHaveBeenCalled()
    discardPreview()
    expect(chat.preview).toBeNull()
    expect(chat.conversationId).toBeNull()
    expect(chat.msgs.at(-1)?.text).toBe('취소했습니다.')
  })
})
```

`assistantView.spec.ts` — 파일 위(`vi.mock('@/api/assistant'…)` 다음)에 `@/api/rooms` 가짜를, 파일 끝에 describe 를 추가:

```ts
vi.mock('@/api/rooms', () => ({
  roomsApi: {
    rooms: vi.fn(async () => [{ id: 3, building_id: 7, room: 803, units: 1, reservable: false }]),
    buildingOutbox: vi.fn(async () => [
      { id: 512, state: 'acked', last_error: null, room_id: 3, building: 'G', room: 803 },
    ]),
  },
}))

describe('적용 뒤 전송 추적', () => {
  it('적용 기록이 생기면 그 방의 건물 outbox 를 따라가 완료를 보인다', async () => {
    vi.useFakeTimers()
    const { chat: c, resetChat: rc } = await import('@/admin/assistant/conversation')
    rc()
    modelApi.mockResolvedValue({ enabled: false })
    const w = mount(AssistantView)
    await flushPromises()
    c.msgs.push({ id: 1, who: 'ai', text: '적용했습니다.', choices: [], answer: null, error: false })
    c.applied = { changeId: 41, outboxIds: [512], roomIds: [3] }
    await flushPromises()
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
    expect(w.text()).toContain('문 앞 반영 완료')
    vi.useRealTimers()
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin/__tests__/assistantChat.spec.ts src/admin/__tests__/assistantView.spec.ts`
Expected: FAIL — `applyPreview` 없음, `문 앞 반영 완료` 없음.

- [ ] **Step 3: `conversation.ts` 에 적용 흐름**

파일 끝(`// Task 9 가 이 아래에 …` 주석 아래)에 다음을 더한다:

```ts
export const APPLIED = '적용했습니다. 문 앞 화면으로 보내는 중입니다.'
export const STALE = '확인하는 동안 다른 변경이 있었습니다. 바뀐 내용으로 다시 확인해 주세요.'
export const EXPIRED = '확인 화면이 만료되었습니다. 다시 말씀해 주세요.'
export const DISCARDED = '취소했습니다.'

/** [적용] — 서버가 저장해 둔 확정 변경 목록을 적용한다(모델 출력을 다시 쓰지 않는다). 버튼으로만 부른다 */
export async function applyPreview(): Promise<void> {
  const p = chat.preview
  if (!p || chat.applying || p.blockers.length) return
  chat.applying = true
  try {
    const r = await assistantApi.apply(p.preview_id)
    chat.applied = {
      changeId: r.change_id,
      outboxIds: r.outbox_ids,
      roomIds: p.rooms.map((x) => x.room_id),
    }
    chat.preview = null
    endConversation()
    say('ai', APPLIED)
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    const f = classify(e)
    if (f?.kind === 'stale') {
      chat.preview = f.preview
      say('ai', STALE, { error: true })
    } else if (f?.kind === 'expired') {
      chat.preview = null
      endConversation()
      say('ai', EXPIRED, { error: true })
    } else if (f?.kind === 'blocked') chat.preview = { ...p, blockers: f.blockers }
    else sayFailure(e)
  } finally {
    chat.applying = false
  }
}

/** [취소] — 서버 대화는 30분 뒤 스스로 만료된다. 화면에서만 닫는다 */
export function discardPreview(): void {
  chat.preview = null
  endConversation()
  say('ai', DISCARDED)
}
```

- [ ] **Step 4: `ApplyTrack.vue` — 적용 뒤 전송 추적**

```vue
<script setup lang="ts">
import { computed, watch } from 'vue'
import OutboxDot, { type DotState } from '@/components/domain/OutboxDot.vue'
import { roomsApi } from '@/api/rooms'
import { useResource } from '@/lib/useResource'
import type { Applied } from '../../assistant/conversation'
import { useOutboxTracker, worst } from '../../outboxTrack'

// 적용 뒤 30초 동안 건물 outbox 를 따라간다 — 주간 시간표 저장 뒤 점과 같은 규칙 (outboxTrack.ts)
const props = defineProps<{ applied: Applied }>()
const tracker = useOutboxTracker()
const rooms = useResource(() => roomsApi.rooms())
const buildings = computed(() => {
  const all = rooms.data.value ?? []
  return [...new Set(props.applied.roomIds.map((id) => all.find((r) => r.id === id)?.building_id))]
    .filter((b): b is number => b !== undefined)
})
const keyOf = (b: number) => `c${props.applied.changeId}-b${b}`
watch(
  buildings,
  (bs) => {
    for (const b of bs) tracker.track(keyOf(b), b, props.applied.outboxIds)
  },
  { immediate: true },
)
const state = computed<DotState | undefined>(() => {
  const s = buildings.value
    .map((b) => tracker.states.get(keyOf(b)))
    .filter((x): x is DotState => !!x)
  return s.length ? worst(s) : undefined
})
const label = computed(() =>
  state.value === 'acked'
    ? '문 앞 반영 완료'
    : state.value === 'failed' || state.value === 'cancelled'
      ? '일부 전송 실패 — 강의실 설정에서 재전송'
      : '문 앞 반영 중',
)
</script>

<template>
  <p v-if="applied.outboxIds.length" class="track" :class="{ 'track--failed': state === 'failed' }">
    <OutboxDot :state="state ?? 'queued'" /> {{ label }}
  </p>
</template>

<style scoped>
.track {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  margin: 0 var(--space-4);
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.track--failed {
  color: var(--danger);
}
</style>
```

(`OutboxDot.vue` 가 `DotState` 를 `export type` 으로 내보낸다 — `outboxTrack.ts` 4행이 같은 import 를 쓴다.)

- [ ] **Step 5: `AssistantView.vue` 잇기**

script:

```ts
import { applyPreview, discardPreview } from '../assistant/conversation'
import ApplyTrack from './assistant/ApplyTrack.vue'

function onApply() {
  void applyPreview()
}
function onDiscard() {
  discardPreview()
  sideOpen.value = false
}
```

(Task 8 의 빈 `onApply`·`onDiscard` 를 이것으로 바꾼다.) template 의 `<ChatPane v-else />` 다음 줄:

```vue
      <ApplyTrack v-if="chat.applied" :key="chat.applied.changeId" :applied="chat.applied" />
```

- [ ] **Step 6: 통과 + 커밋**

Run: `cd web && pnpm test src/admin` → PASS. `pnpm exec vue-tsc --noEmit && pnpm lint` → 오류 0.

```bash
git add web/src/admin/assistant/conversation.ts web/src/admin/views/assistant/ApplyTrack.vue web/src/admin/views/AssistantView.vue web/src/admin/__tests__/assistantChat.spec.ts web/src/admin/__tests__/assistantView.spec.ts
git commit -m "feat(web): AI 비서 적용 — 버튼으로만, 다른 변경·만료·막음 처리, 문 앞 전송 추적"
```

---

### Task 10: 변경 기록 목록 · 확인 열 탭

> **화면 변경(2026-11-26, #176)**: 탭(`SegmentedControl` `확인 | 변경 기록`)이 없다. `ChangeLog.vue`(목록·`reload`)는 그대로 쓰고, 명령창 상태에서 **입력칸이 비어 있을 때** 머리 줄 오른쪽 `ghost` `sm` `변경 기록` 버튼으로 머리 줄 아래 칸을 펼친다(최대 높이 400px 스크롤). 입력을 시작하면 접힌다. 적용 뒤 다시 불러오기는 그대로. Step 4 의 `AssistantView.vue` 전문은 `AssistantPanel.vue` 로 — 상태(닫힘·명령창·보내는 중·되묻기·확인·적용 후)에 따라 `ModelGate` / `CommandBar` / `ConfirmPanel` / `ApplyTrack` / `ChangeLog` 를 고르는 껍데기로 바꾸고, `pickTab` 은 지운다.

**Files:**
- Create: `web/src/admin/views/assistant/ChangeLog.vue`
- Modify: `web/src/admin/views/AssistantView.vue` (`SegmentedControl` `확인 | 변경 기록`, 적용 뒤 다시 불러오기)
- Test: `web/src/admin/__tests__/assistantChangeLog.spec.ts`

**Interfaces:**
- Consumes: `assistantApi.changes()` (Task 3), `formatKst` (`src/lib/time.ts`).
- Produces: `ChangeLog.vue` — `defineExpose({ reload })`.

- [ ] **Step 1: 실패하는 테스트 `web/src/admin/__tests__/assistantChangeLog.spec.ts`**

```ts
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ChangeLog from '@/admin/views/assistant/ChangeLog.vue'
import { assistantApi } from '@/api/assistant'

vi.mock('@/api/assistant', () => ({
  assistantApi: {
    changes: vi.fn(async () => [
      {
        id: 41,
        applied_at: new Date('2026-11-25T01:02:03Z'),
        user_email: 'admin@mjc.ac.kr',
        utterance: '803호 금 특강',
        summary: ['+ 11/27(금) 특강', '+ 11/28(토) 특강'],
        outbox_ids: [512],
      },
    ]),
  },
}))

describe('ChangeLog', () => {
  it('적용 시각(KST) · 관리자 · 요청 · 변경(줄마다), 빈 목록 문구, reload', async () => {
    const w = mount(ChangeLog)
    await flushPromises()
    expect(w.text()).toContain('2026-11-25 10:02')
    expect(w.text()).toContain('admin@mjc.ac.kr')
    expect(w.findAll('.log__line')).toHaveLength(2)
    vi.mocked(assistantApi.changes).mockResolvedValueOnce([])
    await (w.vm as unknown as { reload: () => Promise<void> }).reload()
    await flushPromises()
    expect(w.text()).toContain('AI 비서로 적용한 변경이 아직 없습니다')
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd web && pnpm test src/admin/__tests__/assistantChangeLog.spec.ts`
Expected: FAIL — `ChangeLog.vue` 없음.

- [ ] **Step 3: `ChangeLog.vue`**

```vue
<script setup lang="ts">
import { computed } from 'vue'
import Table from '@/components/ui/Table.vue'
import { assistantApi } from '@/api/assistant'
import { formatKst } from '@/lib/time'
import { useResource } from '@/lib/useResource'

// 변경 기록 (admin-assistant.md 「변경 기록」) — 최신 50건, 자기 범위 건물만(서버가 거른다)
const res = useResource(() => assistantApi.changes())
defineExpose({ reload: res.reload })
const COLS = [
  { key: 'applied_at', label: '적용 시각', width: '140px' },
  { key: 'user_email', label: '관리자' },
  { key: 'utterance', label: '요청' },
  { key: 'summary', label: '변경' },
]
const rows = computed(() =>
  (res.data.value ?? []).map((c) => ({
    id: c.id,
    applied_at: formatKst(c.applied_at),
    user_email: c.user_email,
    utterance: c.utterance,
    summary: c.summary,
  })),
)
</script>

<template>
  <Table
    :columns="COLS"
    :rows="rows"
    :loading="res.loading.value && !res.data.value"
    empty="AI 비서로 적용한 변경이 아직 없습니다"
  >
    <template #cell-summary="{ row }">
      <span v-for="(s, i) in row.summary as string[]" :key="i" class="log__line">{{ s }}</span>
    </template>
  </Table>
</template>

<style scoped>
.log__line {
  display: block;
}
</style>
```

- [ ] **Step 4: `AssistantView.vue` 전문 (Task 5·7·8·9 의 조각을 이것으로 맞춘다)**

```vue
<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import Banner from '@/components/ui/Banner.vue'
import Button from '@/components/ui/Button.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import { applyPreview, chat, discardPreview, draft } from '../assistant/conversation'
import { initModel, model } from '../assistant/model'
import ApplyTrack from './assistant/ApplyTrack.vue'
import ChangeLog from './assistant/ChangeLog.vue'
import ChatPane from './assistant/ChatPane.vue'
import Examples from './assistant/Examples.vue'
import ModelGate from './assistant/ModelGate.vue'
import PreviewPane from './assistant/PreviewPane.vue'

// AI 비서 (admin-assistant.md) — 왼쪽 대화 380px, 오른쪽 확인 | 변경 기록
onMounted(() => void initModel())

// 1024~1279px — 확인 열이 대화를 덮는다(「좁은 화면」). 미리보기가 오면 연다
const sideOpen = ref(false)
const tab = ref<'confirm' | 'log'>('confirm')
const TABS = [
  { value: 'confirm', label: '확인' },
  { value: 'log', label: '변경 기록' },
]
const log = ref<InstanceType<typeof ChangeLog> | null>(null)
watch(
  () => chat.preview?.preview_id,
  (id) => {
    sideOpen.value = !!id
    if (id) tab.value = 'confirm'
  },
)
watch(
  () => chat.applied?.changeId,
  () => void log.value?.reload(),
)

function pickExample(t: string) {
  draft.value = t
}
function pickTab(v: string) {
  tab.value = v === 'log' ? 'log' : 'confirm'
}
function onApply() {
  void applyPreview()
}
function onDiscard() {
  discardPreview()
  sideOpen.value = false
}
</script>

<template>
  <main class="as">
    <section class="as__chat" aria-label="AI 비서 대화">
      <div v-if="chat.preview && !sideOpen" class="as__reopen">
        <Banner message="확인할 변경이 있습니다" :dismissible="false" />
        <Button variant="ghost" size="sm" @click="sideOpen = true">확인 열기</Button>
      </div>
      <ModelGate v-if="model.state !== 'ready'" />
      <ChatPane v-else />
      <ApplyTrack v-if="chat.applied" :key="chat.applied.changeId" :applied="chat.applied" />
    </section>
    <section class="as__side" :class="{ 'as__side--open': sideOpen }" aria-label="확인">
      <Button class="as__back" variant="ghost" size="sm" @click="sideOpen = false"
        >← 대화로</Button
      >
      <SegmentedControl
        class="as__tabs"
        :items="TABS"
        :value="tab"
        label="확인 열"
        @update:value="pickTab"
      />
      <ChangeLog v-if="tab === 'log'" ref="log" />
      <PreviewPane
        v-else-if="chat.preview"
        :preview="chat.preview"
        :applying="chat.applying"
        @apply="onApply"
        @discard="onDiscard"
      />
      <Examples v-else @pick="pickExample" />
    </section>
  </main>
</template>

<style scoped>
.as {
  display: grid;
  grid-template-columns: 380px minmax(0, 1fr);
  height: 100vh;
}
.as__chat {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-right: var(--border-thin) solid var(--line-2);
  background: var(--surface);
}
.as__side {
  min-width: 0;
  overflow: auto;
  padding: var(--space-5);
}
.as__tabs {
  margin-bottom: var(--space-4);
}
.as__back,
.as__reopen {
  display: none;
}
/* 좁은 화면 — 확인 열이 대화를 덮는다 */
@media (max-width: 1279px) {
  .as {
    grid-template-columns: minmax(0, 1fr);
  }
  .as__side {
    display: none;
  }
  .as__side--open {
    position: fixed;
    inset: 0;
    z-index: 20;
    display: block;
    background: var(--bg);
  }
  .as__back {
    display: inline-flex;
    margin-bottom: var(--space-3);
  }
  .as__reopen {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    padding: var(--space-3) var(--space-4) 0;
  }
}
</style>
```

- [ ] **Step 5: 통과 + 커밋**

Run: `cd web && pnpm test src/admin` → PASS. 전체 게이트 `pnpm test && pnpm lint && pnpm exec vue-tsc --noEmit` → 통과.

```bash
git add web/src/admin/views/assistant/ChangeLog.vue web/src/admin/views/AssistantView.vue web/src/admin/__tests__/assistantChangeLog.spec.ts
git commit -m "feat(web): AI 비서 변경 기록 — 확인 | 변경 기록 탭, 적용 뒤 다시 불러오기"
```

- [ ] **Step 6: PR δ**

선행 확인: **01 계획 PR B(서버 `/api/assistant/*`) 가 main 에 머지됐는가.** 아니면 PR 을 열어 두고(Draft) 기다린다.

```bash
git push -u origin feat/ai-assistant-web
gh pr create --draft --title "feat(web): AI 비서 — 명령창·확인 창·적용·변경 기록 (개발용 대역)" --body "<아래 본문>"
```

본문: Task 3~10 요약 / 게이트 결과(`pnpm test`·`lint`·`vue-tsc`) / "서버 모델 안내가 enabled:false 인 동안 운영 화면은 '준비 중'만 — 안전" / 수동 확인: `pnpm dev` + 개발 서버에서 `localStorage.setItem('esc-assistant-stub','manual')` 로 대화·미리보기·적용을 실제 서버(01 PR B)와 돌린 스크린샷 1440·1200 폭.

---

### Task 11: 모델 받기 · 검증 · 보관 — 기기 점검, HF 다운로드, SHA-256, Cache API, 옛 판 삭제

> 선행: PR δ. **실행 도구 선택은 02 계획 0단계 결과**. 이 Task 는 실행 도구와 무관한 부분(받기·검증·보관·점검)과 기본 가정(WebLLM)의 Cache 이름 규칙만 둔다.

**저장소 결정: Cache API** (OPFS 아님). 이유: (1) 응답을 스트림 그대로 넣고 꺼낸다 — 1.5 GB 를 메모리에 올리지 않는다. (2) URL 이 키라 실행 도구가 URL 로 받는 경우(WebLLM·Transformers.js) 그 도구의 캐시에 미리 넣어 두면 그대로 쓴다. (3) 화면·Worker 양쪽에서 쓸 수 있다. OPFS 는 큰 파일 하나의 임의 접근에 유리하지만 실행 도구들이 직접 읽지 못한다.

**이어받기 단위 = 파일.** 검증을 마친 파일은 다시 받지 않는다. WebLLM 형식은 파일이 수십 MB 조각(`params_shard_*.bin`)이라 파일 단위로 충분하다. 0단계에서 **큰 파일 하나**(GGUF 1.5 GB 등)를 쓰는 도구로 정해지면 Task 12 게이트에서 Range 이어받기(OPFS 임시 파일)를 더한다.

**Files:**
- Modify: `web/package.json`·`web/pnpm-lock.yaml` (`hash-wasm`)
- Create: `web/src/admin/assistant/capability.ts`
- Create: `web/src/admin/assistant/modelStore.ts`
- Create: `web/src/admin/assistant/adapters/webllmFiles.ts`
- Modify: `web/src/admin/assistant/model.ts` (enabled 분기, `downloadModel`, `cancelDownload`, `checkAgain`)
- Modify: `web/src/admin/views/assistant/ModelGate.vue` (받기·진행·불러오기·저장 공간·못 씀)
- Modify: `web/src/admin/views/AssistantView.vue` (`chat.modelStale` → 안내 다시 받기)
- Test: `web/src/admin/__tests__/assistantModel.spec.ts` (점검·저장소 단위), `web/src/admin/__tests__/assistantModelFlow.spec.ts` (model.ts 흐름)

**Interfaces:**
- Consumes: `ModelManifestOn`·`ModelFile` (Task 3), `WorkerRunner` (Task 4), `model`·`setEngine` (Task 5), `chat.modelStale` (Task 6).
- Produces:
  - `capability.ts`: `type DeviceReason = 'no-webgpu' | 'no-adapter' | 'low-memory' | 'no-cache'`, `MIN_DEVICE_MEMORY_GB = 4`, `DEVICE_REASON: Record<DeviceReason, string>`, `interface NavLike`, `checkDevice(nav?, hasCaches?): Promise<{ ok: true } | { ok: false; reason: DeviceReason }>`, `checkStorage(need: number, nav?): Promise<{ ok: boolean; free: number | null }>`
  - `modelStore.ts`: `VERIFIED_CACHE = 'esc-assistant-verified'`, `DEFAULT_CACHE = 'esc-assistant-model'`, `fileUrl(m, name): string`, `type CacheNameOf = (f: ModelFile) => string`, `class ModelIntegrityError`, `missingFiles(m, cacheName, store?): Promise<ModelFile[]>`, `downloadFiles(m, cacheName, onProgress, signal?, store?): Promise<void>`, `pruneOld(m, cacheName, store?): Promise<number>`
  - `webllmFiles.ts`: `webllmCacheName(f: ModelFile): string`
  - `model.ts`: `SUPPORTED_RUNTIMES`, `cacheNameFor(runtime)`, `downloadModel()`, `cancelDownload()`, `checkAgain()`

- [ ] **Step 1: 의존성**

```bash
cd web && pnpm add hash-wasm
```

- [ ] **Step 2: 실패하는 테스트 `web/src/admin/__tests__/assistantModel.spec.ts`**

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DEVICE_REASON, checkDevice, checkStorage } from '@/admin/assistant/capability'
import {
  ModelIntegrityError,
  VERIFIED_CACHE,
  downloadFiles,
  fileUrl,
  missingFiles,
  pruneOld,
} from '@/admin/assistant/modelStore'
import { webllmCacheName } from '@/admin/assistant/adapters/webllmFiles'
import type { ModelManifestOn } from '@/api/types'

// sha256("abc")
const ABC = 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'

class FakeCache {
  map = new Map<string, Uint8Array>()
  async match(k: string) {
    const v = this.map.get(k)
    return v ? new Response(v) : undefined
  }
  async put(k: string, r: Response) {
    this.map.set(k, new Uint8Array(await r.arrayBuffer()))
  }
  async delete(k: string) {
    return this.map.delete(k)
  }
  async keys() {
    return [...this.map.keys()].map((u) => new Request(u))
  }
}
class FakeCaches {
  all = new Map<string, FakeCache>()
  async open(name: string) {
    if (!this.all.has(name)) this.all.set(name, new FakeCache())
    return this.all.get(name)! as unknown as Cache
  }
  async keys() {
    return [...this.all.keys()]
  }
}

const M = (o: Partial<ModelManifestOn> = {}): ModelManifestOn => ({
  enabled: true,
  schema_v: 1,
  runtime: 'webllm',
  repo: 'leemonta9482/esc-assistant-e2b',
  revision: 'a'.repeat(40),
  files: [
    { name: 'params_shard_0.bin', size: 3, sha256: ABC },
    { name: 'mlc-chat-config.json', size: 3, sha256: ABC },
  ],
  system_prompt: '',
  first_prefix: '관리자: ',
  json_schema: {},
  generation: { temperature: 0, max_tokens: 256 },
  ...o,
})
const body = (s: string) => new Response(new TextEncoder().encode(s))
let store: FakeCaches
let fetchMock: ReturnType<typeof vi.fn>
beforeEach(() => {
  store = new FakeCaches()
  fetchMock = vi.fn(async () => body('abc'))
  vi.stubGlobal('fetch', fetchMock)
})

describe('capability', () => {
  it('저장소 · WebGPU · 장치 · 메모리 순서로 본다', async () => {
    const adapter = { requestAdapter: async () => ({}) }
    expect(await checkDevice({ gpu: adapter, deviceMemory: 8 }, false)).toEqual({
      ok: false,
      reason: 'no-cache',
    })
    expect(await checkDevice({}, true)).toEqual({ ok: false, reason: 'no-webgpu' })
    expect(await checkDevice({ gpu: { requestAdapter: async () => null } }, true)).toEqual({
      ok: false,
      reason: 'no-adapter',
    })
    expect(await checkDevice({ gpu: adapter, deviceMemory: 2 }, true)).toEqual({
      ok: false,
      reason: 'low-memory',
    })
    expect(await checkDevice({ gpu: adapter }, true)).toEqual({ ok: true })
    expect(DEVICE_REASON['no-webgpu']).toContain('Chrome·Edge')
  })
  it('저장 공간 — 필요량의 1.1배가 남아야 ok, 모르면 ok', async () => {
    const nav = (quota: number, usage: number) => ({
      storage: { estimate: async () => ({ quota, usage }) },
    })
    expect(await checkStorage(100, nav(200, 50))).toEqual({ ok: true, free: 150 })
    expect(await checkStorage(100, nav(150, 50))).toEqual({ ok: false, free: 100 })
    expect(await checkStorage(100, {})).toEqual({ ok: true, free: null })
  })
})

describe('modelStore', () => {
  const cacheName = webllmCacheName
  it('fileUrl — 커밋 해시로 고정한 resolve 주소', () => {
    expect(fileUrl(M(), 'a b.bin')).toBe(
      `https://huggingface.co/leemonta9482/esc-assistant-e2b/resolve/${'a'.repeat(40)}/a%20b.bin`,
    )
  })

  it('받기 — 파일마다 검증 표시, 진행률, 이미 받은 파일은 건너뛴다', async () => {
    const m = M()
    expect(await missingFiles(m, cacheName, store as unknown as CacheStorage)).toHaveLength(2)
    const seen: number[] = []
    await downloadFiles(m, cacheName, (p) => seen.push(p.loaded), undefined, store as unknown as CacheStorage)
    expect(seen.at(-1)).toBe(6)
    expect(await missingFiles(m, cacheName, store as unknown as CacheStorage)).toEqual([])
    expect(store.all.get('webllm/model')!.map.has(fileUrl(m, 'params_shard_0.bin'))).toBe(true)
    expect(store.all.get('webllm/config')!.map.has(fileUrl(m, 'mlc-chat-config.json'))).toBe(true)
    expect(store.all.get(VERIFIED_CACHE)!.map.size).toBe(2)
    fetchMock.mockClear()
    await downloadFiles(m, cacheName, () => {}, undefined, store as unknown as CacheStorage)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('SHA-256 이 다르면 그 파일을 지우고 ModelIntegrityError', async () => {
    fetchMock.mockImplementation(async () => body('abd'))
    const m = M({ files: [{ name: 'params_shard_0.bin', size: 3, sha256: ABC }] })
    await expect(
      downloadFiles(m, cacheName, () => {}, undefined, store as unknown as CacheStorage),
    ).rejects.toBeInstanceOf(ModelIntegrityError)
    expect(store.all.get('webllm/model')!.map.size).toBe(0)
    expect(await missingFiles(m, cacheName, store as unknown as CacheStorage)).toHaveLength(1)
  })

  it('HTTP 오류면 멈춘다', async () => {
    fetchMock.mockResolvedValue(new Response('no', { status: 404 }))
    await expect(
      downloadFiles(M(), cacheName, () => {}, undefined, store as unknown as CacheStorage),
    ).rejects.toThrow('404')
  })

  it('옛 판 삭제 — 지금 판의 파일 주소가 아닌 키를 모두 지운다', async () => {
    const old = M({ revision: 'b'.repeat(40) })
    await downloadFiles(old, cacheName, () => {}, undefined, store as unknown as CacheStorage)
    const now = M()
    await downloadFiles(now, cacheName, () => {}, undefined, store as unknown as CacheStorage)
    expect(await pruneOld(now, cacheName, store as unknown as CacheStorage)).toBe(4)
    expect(await missingFiles(now, cacheName, store as unknown as CacheStorage)).toEqual([])
    expect(await missingFiles(old, cacheName, store as unknown as CacheStorage)).toHaveLength(2)
  })
})
```

- [ ] **Step 3: 실패 확인**

Run: `cd web && pnpm test src/admin/__tests__/assistantModel.spec.ts`
Expected: FAIL — `Failed to resolve import "@/admin/assistant/capability"`.

- [ ] **Step 4: `capability.ts`**

```ts
// 이 PC 에서 모델을 돌릴 수 있는가 (admin-assistant.md 「모델 상태」). navigator 를 받아 테스트한다
export type DeviceReason = 'no-webgpu' | 'no-adapter' | 'low-memory' | 'no-cache'
/** navigator.deviceMemory(GB, Chrome 만, 최대 8 로 뭉뚱그림) 하한 — E2B int4 약 1.5 GB + 브라우저 */
export const MIN_DEVICE_MEMORY_GB = 4
export const DEVICE_REASON: Record<DeviceReason, string> = {
  'no-webgpu':
    '이 브라우저는 WebGPU 를 지원하지 않아 AI 비서를 쓸 수 없습니다. 최신 Chrome·Edge 를 쓰세요.',
  'no-adapter': '이 PC 의 그래픽 장치로는 AI 모델을 돌릴 수 없습니다.',
  'low-memory': '이 PC 의 메모리가 부족해 AI 모델을 돌릴 수 없습니다.',
  'no-cache': '이 브라우저는 모델을 저장할 수 없습니다(사생활 보호 모드 등).',
}

export interface NavLike {
  gpu?: { requestAdapter(): Promise<unknown | null> }
  deviceMemory?: number
  storage?: {
    estimate?(): Promise<{ quota?: number; usage?: number }>
    persist?(): Promise<boolean>
  }
}
const realNav = () => navigator as unknown as NavLike

export async function checkDevice(
  nav: NavLike = realNav(),
  hasCaches: boolean = typeof caches !== 'undefined',
): Promise<{ ok: true } | { ok: false; reason: DeviceReason }> {
  if (!hasCaches) return { ok: false, reason: 'no-cache' }
  if (!nav.gpu) return { ok: false, reason: 'no-webgpu' }
  const adapter = await nav.gpu.requestAdapter().catch(() => null)
  if (!adapter) return { ok: false, reason: 'no-adapter' }
  if (typeof nav.deviceMemory === 'number' && nav.deviceMemory < MIN_DEVICE_MEMORY_GB)
    return { ok: false, reason: 'low-memory' }
  return { ok: true }
}

/** 남은 저장 공간 — 필요량의 1.1배. 브라우저가 알려 주지 않으면 막지 않는다(받다가 실패하면 그때 안내) */
export async function checkStorage(
  need: number,
  nav: NavLike = realNav(),
): Promise<{ ok: boolean; free: number | null }> {
  const est = await nav.storage?.estimate?.().catch(() => null)
  if (!est || typeof est.quota !== 'number') return { ok: true, free: null }
  const free = est.quota - (est.usage ?? 0)
  return { ok: free >= need * 1.1, free }
}
```

- [ ] **Step 5: `adapters/webllmFiles.ts`**

```ts
import type { ModelFile } from '@/api/types'

/** WebLLM 이 같은 URL 을 찾는 Cache API 이름 — 미리 넣어 두면 WebLLM 이 다시 받지 않는다.
 * 0단계 실험에서 실제 이름(webllm/model · webllm/config · webllm/wasm)을 확인한다.
 * 다르면 WebLLM 이 한 번 더 받을 뿐 깨지지 않는다 */
export function webllmCacheName(f: ModelFile): string {
  if (f.name.endsWith('.wasm')) return 'webllm/wasm'
  if (f.name.endsWith('.json') || f.name.startsWith('tokenizer')) return 'webllm/config'
  return 'webllm/model'
}
```

- [ ] **Step 6: `modelStore.ts`**

```ts
import { createSHA256 } from 'hash-wasm'
import type { ModelFile, ModelManifestOn } from '@/api/types'
import type { LoadProgress } from './runner'

/** 검증을 마친 파일 표시 — 파일 캐시와 따로 둔다(내려받는 도중 꺼진 파일을 '받음'으로 보지 않게) */
export const VERIFIED_CACHE = 'esc-assistant-verified'
/** 실행 도구가 따로 캐시 이름을 정하지 않으면 */
export const DEFAULT_CACHE = 'esc-assistant-model'
export type CacheNameOf = (f: ModelFile) => string

export class ModelIntegrityError extends Error {
  constructor(public file: string) {
    super(`모델 파일 검증에 실패했습니다(${file}). 다시 받아 주세요.`)
    this.name = 'ModelIntegrityError'
  }
}

/** 커밋 해시로 고정한 판 (부록 §4.1) */
export const fileUrl = (m: ModelManifestOn, name: string) =>
  `https://huggingface.co/${m.repo}/resolve/${m.revision}/${encodeURI(name)}`

const realStore = () => caches

export async function missingFiles(
  m: ModelManifestOn,
  cacheName: CacheNameOf,
  store: CacheStorage = realStore(),
): Promise<ModelFile[]> {
  const ok = await store.open(VERIFIED_CACHE)
  const out: ModelFile[] = []
  for (const f of m.files) {
    const url = fileUrl(m, f.name)
    const mark = await ok.match(url)
    const file = mark && (await (await store.open(cacheName(f))).match(url))
    if (!mark || !file || (await mark.text()) !== f.sha256) out.push(f)
  }
  return out
}

/** 빠진 파일만 차례로 받는다 — 스트림을 둘로 나눠 하나는 캐시로, 하나는 SHA-256 으로 (메모리에 통째로 올리지 않는다) */
export async function downloadFiles(
  m: ModelManifestOn,
  cacheName: CacheNameOf,
  onProgress: (p: LoadProgress) => void,
  signal?: AbortSignal,
  store: CacheStorage = realStore(),
): Promise<void> {
  const todo = await missingFiles(m, cacheName, store)
  const total = todo.reduce((s, f) => s + f.size, 0)
  let loaded = 0
  const ok = await store.open(VERIFIED_CACHE)
  for (const f of todo) {
    const url = fileUrl(m, f.name)
    const res = await fetch(url, { signal })
    if (!res.ok || !res.body) throw new Error(`모델 파일을 받지 못했습니다(${f.name}, ${res.status})`)
    const cache = await store.open(cacheName(f))
    const [toCache, toHash] = res.body.tee()
    const putting = cache.put(
      url,
      new Response(toCache, {
        headers: { 'content-type': res.headers.get('content-type') ?? 'application/octet-stream' },
      }),
    )
    const h = await createSHA256()
    h.init()
    const reader = toHash.getReader()
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      h.update(value)
      loaded += value.byteLength
      onProgress({ loaded, total, text: f.name })
    }
    await putting
    const got = h.digest('hex')
    if (got !== f.sha256) {
      await cache.delete(url)
      throw new ModelIntegrityError(f.name)
    }
    await ok.put(url, new Response(got))
  }
}

/** 지금 판의 파일 주소가 아닌 키를 지운다 — 판이 바뀌면 1.5 GB 가 두 벌 쌓이지 않게. 지운 개수를 돌려준다 */
export async function pruneOld(
  m: ModelManifestOn,
  cacheName: CacheNameOf,
  store: CacheStorage = realStore(),
): Promise<number> {
  const keep = new Set(m.files.map((f) => fileUrl(m, f.name)))
  const names = new Set([VERIFIED_CACHE, DEFAULT_CACHE, ...m.files.map(cacheName)])
  let n = 0
  for (const name of names) {
    const c = await store.open(name)
    for (const req of await c.keys())
      if (req.url.startsWith('https://huggingface.co/') && !keep.has(req.url)) {
        await c.delete(req.url)
        n++
      }
  }
  return n
}
```

(테스트의 옛 판 삭제 기대값 4 = 옛 판 파일 2 + 검증 표시 2.)

- [ ] **Step 7: `model.ts` — enabled 분기와 받기**

import 에 추가:

```ts
import type { AssistantRuntime, ModelFile } from '@/api/types'
import { DEVICE_REASON, checkDevice, checkStorage } from './capability'
import { DEFAULT_CACHE, downloadFiles, missingFiles, pruneOld, type CacheNameOf } from './modelStore'
import { WorkerRunner } from './runner'
import { webllmCacheName } from './adapters/webllmFiles'
```

(`import type { LoadProgress, ModelRunner } from './runner'` 는 `import { WorkerRunner, type LoadProgress, type ModelRunner } from './runner'` 로 합친다.)

모듈에 추가:

```ts
/** 0단계 결과로 고른 실행 도구 — Task 12 가 worker.ts 에 같은 목록의 어댑터를 둔다 */
export const SUPPORTED_RUNTIMES: AssistantRuntime[] = ['webllm']
export const cacheNameFor = (rt: AssistantRuntime): CacheNameOf =>
  rt === 'webllm' ? webllmCacheName : (_f: ModelFile) => DEFAULT_CACHE

let aborter: AbortController | null = null
const enabledManifest = (): ModelManifestOn | null =>
  model.manifest && model.manifest.enabled ? model.manifest : null

async function prepare(m: ModelManifestOn): Promise<void> {
  if (!SUPPORTED_RUNTIMES.includes(m.runtime)) {
    model.state = 'unsupported'
    model.reason = `이 판의 실행 도구(${m.runtime})를 아직 지원하지 않습니다.`
    return
  }
  const dev = await checkDevice()
  if (!dev.ok) {
    model.state = 'unsupported'
    model.reason = DEVICE_REASON[dev.reason]
    return
  }
  const missing = await missingFiles(m, cacheNameFor(m.runtime))
  if (!missing.length) return start(m)
  model.need = missing.reduce((s, f) => s + f.size, 0)
  const st = await checkStorage(model.need)
  model.free = st.free
  model.state = st.ok ? 'need-download' : 'no-space'
}

async function start(m: ModelManifestOn): Promise<void> {
  model.state = 'starting'
  try {
    const runner = new WorkerRunner()
    await runner.load(m, (p) => (model.progress = p))
    setEngine(runner, m)
    await pruneOld(m, cacheNameFor(m.runtime))
    model.state = 'ready'
  } catch (e) {
    model.state = 'failed'
    model.reason = e instanceof Error ? e.message : String(e)
  }
}

/** [AI 모델 받기] — 받는 동안 다른 화면으로 가도 계속 받는다(모듈 상태) */
export async function downloadModel(): Promise<void> {
  const m = enabledManifest()
  if (!m || model.state !== 'need-download') return
  model.state = 'downloading'
  aborter = new AbortController()
  try {
    await (navigator as unknown as { storage?: { persist?(): Promise<boolean> } }).storage
      ?.persist?.()
      .catch(() => false)
    await downloadFiles(m, cacheNameFor(m.runtime), (p) => (model.progress = p), aborter.signal)
    await start(m)
  } catch (e) {
    if ((e as Error).name === 'AbortError') {
      model.state = 'need-download'
      return
    }
    model.state = 'failed'
    model.reason = e instanceof Error ? e.message : String(e)
  } finally {
    aborter = null
  }
}
export function cancelDownload(): void {
  aborter?.abort()
}
/** 저장 공간 부족 · 판 바뀜 뒤 다시 확인 */
export async function checkAgain(): Promise<void> {
  await current?.runner.dispose()
  setEngine(null, null)
  model.state = 'failed' // initModel 의 BUSY 가드를 지나게
  await initModel()
}
```

`initModel` 안의 Task 5 분기

```ts
    // Task 11 이 이 분기를 기기 점검 → 받기/불러오기로 바꾼다
    model.state = 'unsupported'
    model.reason = `이 판의 실행 도구(${m.runtime})를 아직 지원하지 않습니다.`
```

를 다음 한 줄로 바꾼다:

```ts
    await prepare(m)
```

- [ ] **Step 8: `ModelGate.vue` 상태 전부**

script 를:

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import Banner from '@/components/ui/Banner.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import ProgressBar from '@/components/ui/ProgressBar.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import { cancelDownload, checkAgain, downloadModel, initModel, model } from '../../assistant/model'

// 대화 열 자리에 서는 모델 상태 (admin-assistant.md 「모델 상태」)
const router = useRouter()
const gb = (n: number) => (n / 1024 ** 3).toFixed(1)
const size = computed(() => gb(model.need))
const BACK = [
  { label: '주간 시간표로', onClick: () => void router.push('/week') },
  { label: '강의실 설정으로', onClick: () => void router.push('/rooms') },
]
</script>
```

template 의 `<div class="gate">` 안을:

```vue
    <Skeleton v-if="model.state === 'loading'" variant="block" width="100%" />
    <EmptyState
      v-else-if="model.state === 'disabled'"
      message="AI 비서를 준비하고 있습니다. 모델이 배포되면 여기서 쓸 수 있습니다."
    />
    <EmptyState v-else-if="model.state === 'unsupported'" :message="model.reason" :actions="BACK" />
    <div v-else-if="model.state === 'need-download'" class="gate__card">
      <p>이 PC 에서 AI 모델을 돌립니다. 문장은 학교 서버로만 갑니다.</p>
      <p>처음 한 번 약 {{ size }} GB 를 받습니다. 받는 동안 다른 화면을 써도 됩니다.</p>
      <Button @click="downloadModel">AI 모델 받기 (약 {{ size }} GB)</Button>
    </div>
    <div v-else-if="model.state === 'downloading'" class="gate__card">
      <ProgressBar
        :value="model.progress.loaded"
        :max="model.progress.total || 1"
        label="AI 모델 받는 중"
      />
      <p class="num">{{ gb(model.progress.loaded) }} / {{ gb(model.progress.total) }} GB</p>
      <Button variant="ghost" size="sm" @click="cancelDownload">취소</Button>
    </div>
    <div v-else-if="model.state === 'starting'" class="gate__card">
      <Skeleton variant="block" width="100%" />
      <p>모델을 불러오는 중…</p>
    </div>
    <div v-else-if="model.state === 'no-space'" class="gate__card">
      <Banner
        tone="danger"
        :dismissible="false"
        :message="`저장 공간이 부족합니다 (필요 ${size} GB, 남은 ${gb(model.free ?? 0)} GB). 브라우저 저장 공간을 비운 뒤 다시 확인해 주세요.`"
      />
      <Button variant="secondary" @click="checkAgain">다시 확인</Button>
    </div>
    <EmptyState
      v-else-if="model.state === 'failed'"
      :message="model.reason"
      :actions="[{ label: '다시 시도', onClick: () => void initModel() }]"
    />
```

style 에:

```css
.gate__card {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  width: 100%;
  font-size: var(--font-size-md);
  color: var(--text-2);
}
.gate__card p {
  margin: 0;
}
```

- [ ] **Step 9: 판 불일치 → 안내 다시 받기 (`AssistantView.vue`)**

script 에:

```ts
import { checkAgain } from '../assistant/model'

watch(
  () => chat.modelStale,
  (stale) => {
    if (!stale) return
    chat.modelStale = false
    void checkAgain()
  },
)
```

- [ ] **Step 10: model.ts 흐름 테스트 — 새 파일 `web/src/admin/__tests__/assistantModelFlow.spec.ts`**

(ES 모듈 내보내기는 `vi.spyOn` 으로 바꿀 수 없다 — 그래서 위 단위 테스트와 파일을 나누고 `vi.mock` 으로 갈아 끼운다.)

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { assistantApi } from '@/api/assistant'
import type { ModelManifestOn } from '@/api/types'
import { checkDevice, checkStorage } from '@/admin/assistant/capability'
import { downloadFiles, missingFiles } from '@/admin/assistant/modelStore'
import {
  cacheNameFor,
  checkAgain,
  downloadModel,
  initModel,
  model,
  resetModel,
} from '@/admin/assistant/model'

vi.mock('@/api/assistant', () => ({
  assistantApi: { model: vi.fn(), turn: vi.fn(), apply: vi.fn(), changes: vi.fn() },
  classify: vi.fn(() => null),
}))
vi.mock('@/admin/assistant/capability', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/admin/assistant/capability')>()),
  checkDevice: vi.fn(),
  checkStorage: vi.fn(),
}))
vi.mock('@/admin/assistant/modelStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/admin/assistant/modelStore')>()),
  missingFiles: vi.fn(),
  downloadFiles: vi.fn(async () => {}),
  pruneOld: vi.fn(async () => 0),
}))
vi.mock('@/admin/assistant/runner', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/admin/assistant/runner')>()
  class FakeRunner {
    load = vi.fn(async () => {})
    generate = vi.fn(async () => '')
    dispose = vi.fn(async () => {})
  }
  return { ...real, WorkerRunner: FakeRunner }
})

const M = (o: Partial<ModelManifestOn> = {}): ModelManifestOn => ({
  enabled: true,
  schema_v: 1,
  runtime: 'webllm',
  repo: 'leemonta9482/esc-assistant-e2b',
  revision: 'a'.repeat(40),
  files: [
    { name: 'params_shard_0.bin', size: 3, sha256: 'x' },
    { name: 'mlc-chat-config.json', size: 3, sha256: 'y' },
  ],
  system_prompt: '',
  first_prefix: '관리자: ',
  json_schema: {},
  generation: { temperature: 0, max_tokens: 256 },
  ...o,
})

beforeEach(async () => {
  await resetModel()
  localStorage.clear()
  vi.mocked(assistantApi.model).mockResolvedValue(M())
  vi.mocked(checkDevice).mockResolvedValue({ ok: true })
  vi.mocked(checkStorage).mockResolvedValue({ ok: true, free: 10 ** 10 })
  vi.mocked(downloadFiles).mockClear()
})

describe('model 흐름', () => {
  it('빠진 파일이 있으면 받기 버튼 → 받기 → 불러오기 → 준비됨', async () => {
    vi.mocked(missingFiles).mockResolvedValue(M().files)
    await initModel()
    expect(model.state).toBe('need-download')
    expect(model.need).toBe(6)
    await downloadModel()
    expect(downloadFiles).toHaveBeenCalled()
    expect(model.state).toBe('ready')
  })

  it('이미 받았으면 바로 불러온다, 기기 미지원이면 이유', async () => {
    vi.mocked(missingFiles).mockResolvedValue([])
    await initModel()
    expect(model.state).toBe('ready')
    expect(downloadFiles).not.toHaveBeenCalled()
    vi.mocked(checkDevice).mockResolvedValue({ ok: false, reason: 'no-webgpu' })
    await checkAgain()
    expect(model.state).toBe('unsupported')
    expect(model.reason).toContain('WebGPU')
  })

  it('저장 공간 부족 · 지원하지 않는 실행 도구', async () => {
    vi.mocked(missingFiles).mockResolvedValue(M().files)
    vi.mocked(checkStorage).mockResolvedValue({ ok: false, free: 1 })
    await initModel()
    expect(model.state).toBe('no-space')
    vi.mocked(assistantApi.model).mockResolvedValue(M({ runtime: 'wllama' }))
    await checkAgain()
    expect(model.state).toBe('unsupported')
    expect(cacheNameFor('wllama')(M().files[0])).toBe('esc-assistant-model')
  })
})
```

- [ ] **Step 11: 통과 + 커밋**

Run: `cd web && pnpm test src/admin` → PASS. `pnpm exec vue-tsc --noEmit && pnpm lint` → 오류 0.

```bash
git switch -c feat/ai-assistant-model main
git add web/package.json web/pnpm-lock.yaml web/src/admin/assistant/capability.ts web/src/admin/assistant/modelStore.ts web/src/admin/assistant/adapters/webllmFiles.ts web/src/admin/assistant/model.ts web/src/admin/views/assistant/ModelGate.vue web/src/admin/views/AssistantView.vue web/src/admin/__tests__/assistantModel.spec.ts web/src/admin/__tests__/assistantModelFlow.spec.ts
git commit -m "feat(web): AI 모델 받기 — 기기·저장 공간 점검, HF 고정 판 다운로드, SHA-256 검증, 옛 판 삭제"
```

---

### Task 12: 실행 도구 어댑터 (게이트: 02 계획 0단계 결과) · CSP

> **게이트**: 02 계획 Task(0단계) 선정 문서가 고른 실행 도구로 이 Task 를 한다. 아래는 **기본 가정 WebLLM**. 다른 도구로 정해지면 `adapters/<도구>.ts` 를 같은 `ModelRunner` 모양으로 쓰고, `worker.ts` 의 `adapterFor`·`model.ts` 의 `SUPPORTED_RUNTIMES`·`cacheNameFor` 를 그 값으로 바꾼다(아래 「wllama 로 정해지면」).

**Files:**
- Modify: `web/package.json`·`web/pnpm-lock.yaml` (`@mlc-ai/web-llm`)
- Create: `web/src/admin/assistant/adapters/webllm.ts`
- Modify: `web/src/admin/assistant/worker.ts` (`adapterFor`)
- Create: `web/security-headers-admin.conf` (관리자 앱 CSP — 2026-11-26 팀장 결정: 넓힌 CSP 는 `/admin` 만)
- Modify: `web/nginx.conf` (`/admin` location 이 admin 헤더를 include), `web/Dockerfile` (admin 헤더 COPY)
- 그대로: `web/security-headers.conf` (학생 앱 공용 — 지금의 좁은 CSP)
- Test: `web/src/admin/__tests__/assistantWebllm.spec.ts`, `web/src/admin/__tests__/csp.spec.ts`

**Interfaces:**
- Consumes: `ModelRunner`·`GenerateReq`·`LoadProgress` (Task 4), `fileUrl` (Task 11).
- Produces: `adapters/webllm.ts`: `MODEL_ID = 'esc-assistant'`, `appConfig(m: ModelManifestOn)`, `class WebLlmRunner implements ModelRunner`.

- [ ] **Step 1: 의존성**

```bash
cd web && pnpm add @mlc-ai/web-llm
```

- [ ] **Step 2: 실패하는 테스트**

`web/src/admin/__tests__/assistantWebllm.spec.ts`:

```ts
import { describe, expect, it, vi } from 'vitest'
import { MODEL_ID, WebLlmRunner, appConfig } from '@/admin/assistant/adapters/webllm'
import type { ModelManifestOn } from '@/api/types'

// vi.mock 은 파일 맨 위로 끌어올려진다 — 그 안에서 쓰는 가짜는 vi.hoisted 로 먼저 만든다
const { create, unload } = vi.hoisted(() => ({ create: vi.fn(), unload: vi.fn() }))
vi.mock('@mlc-ai/web-llm', () => ({
  CreateMLCEngine: vi.fn(async (_id: string, cfg: { initProgressCallback: (r: unknown) => void }) => {
    cfg.initProgressCallback({ progress: 0.5, timeElapsed: 1, text: '반' })
    return { chat: { completions: { create } }, unload }
  }),
}))

const M: ModelManifestOn = {
  enabled: true,
  schema_v: 1,
  runtime: 'webllm',
  repo: 'leemonta9482/esc-assistant-e2b',
  revision: 'a'.repeat(40),
  files: [
    { name: 'esc-assistant-webgpu.wasm', size: 1, sha256: 'x' },
    { name: 'params_shard_0.bin', size: 1, sha256: 'y' },
  ],
  system_prompt: 'SYS',
  first_prefix: '관리자: ',
  json_schema: { type: 'object' },
  generation: { temperature: 0, max_tokens: 256 },
}

describe('WebLLM 어댑터', () => {
  it('appConfig — 모델·라이브러리 모두 고정 판 HF 주소', () => {
    const c = appConfig(M)
    expect(c.model_list[0]).toEqual({
      model: `https://huggingface.co/leemonta9482/esc-assistant-e2b/resolve/${'a'.repeat(40)}/`,
      model_id: MODEL_ID,
      model_lib: `https://huggingface.co/leemonta9482/esc-assistant-e2b/resolve/${'a'.repeat(40)}/esc-assistant-webgpu.wasm`,
    })
    expect(() => appConfig({ ...M, files: [] })).toThrow('.wasm')
  })

  it('load 진행률 · generate 는 system/user + json_schema 문법 강제 · dispose 는 unload', async () => {
    const r = new WebLlmRunner()
    const seen: unknown[] = []
    await r.load(M, (p) => seen.push(p))
    expect(seen[0]).toEqual({ loaded: 500, total: 1000, text: '반' })
    create.mockResolvedValue({ choices: [{ message: { content: '{"v":1}' } }] })
    const out = await r.generate({
      system: 'SYS',
      user: '관리자: 801 배터리?',
      schema: { type: 'object' },
      generation: { temperature: 0, max_tokens: 256 },
    })
    expect(out).toBe('{"v":1}')
    expect(create).toHaveBeenCalledWith({
      messages: [
        { role: 'system', content: 'SYS' },
        { role: 'user', content: '관리자: 801 배터리?' },
      ],
      temperature: 0,
      max_tokens: 256,
      response_format: { type: 'json_object', schema: '{"type":"object"}' },
    })
    await r.dispose()
    expect(unload).toHaveBeenCalled()
  })
})
```

`web/src/admin/__tests__/csp.spec.ts`:

```ts
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const read = (name: string) =>
  readFileSync(fileURLToPath(new URL(`../../../${name}`, import.meta.url)), 'utf8')
const cspOf = (conf: string) => conf.match(/Content-Security-Policy "([^"]+)"/)?.[1] ?? ''
const dir = (csp: string, name: string) =>
  csp
    .split(';')
    .map((s) => s.trim())
    .find((s) => s.startsWith(`${name} `)) ?? ''
const HEADERS = ['X-Content-Type-Options', 'X-Frame-Options', 'Referrer-Policy']

describe('CSP — AI 비서 모델 받기·실행 (관리자 앱만)', () => {
  it('관리자 헤더: Hugging Face 와 그 CDN 으로만 연결, WASM 실행 허용, Worker 는 자기 출처', () => {
    const csp = cspOf(read('security-headers-admin.conf'))
    expect(dir(csp, 'connect-src')).toBe(
      "connect-src 'self' https://huggingface.co https://*.huggingface.co https://*.hf.co",
    )
    expect(dir(csp, 'script-src')).toBe("script-src 'self' 'wasm-unsafe-eval'")
    expect(dir(csp, 'worker-src')).toBe("worker-src 'self'")
    expect(dir(csp, 'default-src')).toBe("default-src 'self'")
    expect(csp).toContain("frame-ancestors 'none'")
  })

  it('관리자 헤더는 공용 헤더의 나머지 보안 헤더를 모두 되풀이한다 (location add_header 는 상속이 끊긴다)', () => {
    const admin = read('security-headers-admin.conf')
    for (const h of HEADERS) expect(admin).toContain(`add_header ${h} `)
  })

  it('공용(학생 앱) 헤더는 넓히지 않는다', () => {
    const csp = cspOf(read('security-headers.conf'))
    expect(csp).not.toContain('huggingface')
    expect(csp).not.toContain('hf.co')
    expect(csp).not.toContain('wasm-unsafe-eval')
  })

  it('nginx: /admin location 만 관리자 헤더를 include 한다', () => {
    const nginx = read('nginx.conf')
    const admin = nginx.match(/location \/admin \{([^}]+)\}/)?.[1] ?? ''
    expect(admin).toContain('security-headers-admin.conf')
    expect(admin).not.toMatch(/snippets\/security-headers\.conf/)
  })
})
```

- [ ] **Step 3: 실패 확인**

Run: `cd web && pnpm test src/admin/__tests__/assistantWebllm.spec.ts src/admin/__tests__/csp.spec.ts`
Expected: FAIL — `adapters/webllm` 없음, `security-headers-admin.conf` 없음.

- [ ] **Step 4: `adapters/webllm.ts`**

```ts
import type { MLCEngineInterface } from '@mlc-ai/web-llm'
import type { ModelManifestOn } from '@/api/types'
import { fileUrl } from '../modelStore'
import type { GenerateReq, LoadProgress, ModelRunner } from '../runner'

// Worker 안에서만 import 한다(worker.ts 의 동적 import) — 화면 청크에 들어가지 않는다
export const MODEL_ID = 'esc-assistant'

/** 모델 폴더와 모델 라이브러리(.wasm) 모두 고정 판 HF 주소 — WebLLM 기본(GitHub raw) 라이브러리를 쓰지 않는다 */
export function appConfig(m: ModelManifestOn) {
  const lib = m.files.find((f) => f.name.endsWith('.wasm'))
  if (!lib) throw new Error('모델 안내에 .wasm 모델 라이브러리가 없습니다')
  return {
    model_list: [
      {
        model: `https://huggingface.co/${m.repo}/resolve/${m.revision}/`,
        model_id: MODEL_ID,
        model_lib: fileUrl(m, lib.name),
      },
    ],
  }
}

export class WebLlmRunner implements ModelRunner {
  private engine: MLCEngineInterface | null = null

  async load(m: ModelManifestOn, onProgress: (p: LoadProgress) => void): Promise<void> {
    const webllm = await import('@mlc-ai/web-llm')
    this.engine = await webllm.CreateMLCEngine(MODEL_ID, {
      appConfig: appConfig(m),
      initProgressCallback: (r) =>
        onProgress({ loaded: Math.round(r.progress * 1000), total: 1000, text: r.text }),
    })
  }

  async generate(req: GenerateReq): Promise<string> {
    if (!this.engine) throw new Error('모델을 먼저 불러오세요')
    const r = await this.engine.chat.completions.create({
      messages: [
        { role: 'system', content: req.system },
        { role: 'user', content: req.user },
      ],
      temperature: req.generation.temperature,
      max_tokens: req.generation.max_tokens,
      // 출력 문법 강제 — 양식 밖 글자를 만들 수 없다 (spec §8.1 1순위 이유)
      response_format: { type: 'json_object', schema: JSON.stringify(req.schema) },
    })
    return r.choices[0]?.message?.content ?? ''
  }

  async dispose(): Promise<void> {
    await this.engine?.unload()
    this.engine = null
  }
}
```

- [ ] **Step 5: `worker.ts` — 어댑터 고르기**

`adapterFor` 를:

```ts
async function adapterFor(runtime: AssistantRuntime): Promise<ModelRunner> {
  switch (runtime) {
    case 'webllm':
      return new (await import('./adapters/webllm')).WebLlmRunner()
    default:
      throw new Error(`이 실행 도구(${runtime})는 아직 지원하지 않습니다`)
  }
}
```

- [ ] **Step 6: CSP — 관리자 앱(`/admin`)만 넓힌다 (2026-11-26 팀장 결정)**

`web/security-headers.conf`(학생 앱·공용)는 **고치지 않는다.** 새 파일 `web/security-headers-admin.conf`:

```nginx
# 관리자 앱(/admin) 보안 헤더 — nginx.conf 의 location /admin 이 include 한다.
# location 에 add_header 가 하나라도 있으면 바깥(server) add_header 가 상속되지 않는다 —
# 그래서 security-headers.conf 의 헤더를 모두 여기 되풀이한다(바꿀 때 두 파일을 함께).
# AI 비서(2026-11-25): 모델 파일은 Hugging Face 와 그 CDN(*.hf.co — 큰 파일은 cas-bridge.xethub.hf.co 로 넘어간다)에서만, 모델 실행은 WASM('wasm-unsafe-eval')·자기 출처 Worker
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; connect-src 'self' https://huggingface.co https://*.huggingface.co https://*.hf.co; img-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header Referrer-Policy "same-origin" always;
```

`web/nginx.conf` 의 `location /admin` 에서 include 줄을 바꾼다:

```nginx
    location /admin {
        try_files $uri /admin.html;
        add_header Cache-Control "no-cache";
        include /etc/nginx/snippets/security-headers-admin.conf;
    }
```

`web/Dockerfile` 의 `COPY security-headers.conf …` 다음 줄:

```dockerfile
COPY security-headers-admin.conf /etc/nginx/snippets/security-headers-admin.conf
```

주의 — **Worker 의 CSP 는 Worker 스크립트 응답의 헤더로 정해진다.** 빌드된 Worker 청크는 `/assets/` 에서 나가고 `/assets/` location 은 공용(좁은) 헤더라, 그대로면 Worker 안의 HF 연결·WASM 실행이 막힌다. Worker 청크를 따로 모은다 — `vite.config.ts` 에 `worker: { rollupOptions: { output: { entryFileNames: 'assets/worker/[name]-[hash].js', chunkFileNames: 'assets/worker/[name]-[hash].js' } } }`, `nginx.conf` 에 `/assets/` 와 같은 캐시 설정의 `location /assets/worker/ { … include /etc/nginx/snippets/security-headers-admin.conf; }`. Step 7 실기에서 Worker 쪽 CSP 위반 콘솔 오류가 없는지로 확인한다.

- [ ] **Step 7: 통과 + 실기 확인**

Run: `cd web && pnpm test src/admin && pnpm exec vue-tsc --noEmit && pnpm lint` → 통과.

실기(0단계와 같은 PC, Chrome): 02 계획이 올린 **테스트 판**을 가리키는 `server/app/assistant/model.json` 을 로컬 서버에 두고 `pnpm dev` → AI 비서 → `AI 모델 받기` → 진행률 → 준비됨 → "801 배터리?" 한 문장이 5초 안에 양식으로 나오는지. DevTools Application → Cache Storage 에 `webllm/model`·`webllm/config`·`webllm/wasm`·`esc-assistant-verified` 가 생기고, 새로고침 뒤 **다시 받지 않는지**(Network 에 HF 요청 0). 다시 받으면 `webllmFiles.ts` 의 이름을 실제 이름으로 고친다.

`pnpm build && pnpm preview` 로 빌드 결과에서도 한 번 — `dist/assets` 의 관리자 화면 청크에 `web-llm` 코드가 없고(Worker 청크에만) CSP 위반 콘솔 오류가 없는지.

- [ ] **Step 8: 커밋**

```bash
git add web/package.json web/pnpm-lock.yaml web/src/admin/assistant/adapters/webllm.ts web/src/admin/assistant/worker.ts web/security-headers-admin.conf web/nginx.conf web/Dockerfile web/vite.config.ts web/src/admin/__tests__/assistantWebllm.spec.ts web/src/admin/__tests__/csp.spec.ts
git commit -m "feat(web): AI 비서 WebLLM 실행 — 고정 판 모델·라이브러리, JSON Schema 문법 강제, 관리자 앱 CSP"
```

#### wllama 로 정해지면 (대안 어댑터의 차이)

| | WebLLM (기본 가정) | wllama (llama.cpp WASM) |
|---|---|---|
| 모델 파일 | MLC 형식 — 조각 여러 개 + `.wasm` 모델 라이브러리 | GGUF 한 파일(약 1.5 GB) |
| 불러오기 | `CreateMLCEngine(MODEL_ID, { appConfig })` — URL 로 받음(캐시 미리 채움) | `new Wllama(wasmPaths)` → `loadModel([blob])` — **Cache API 에서 꺼낸 Blob** 을 직접 넘긴다(다시 받지 않음이 확실) |
| 문법 강제 | `response_format: { type: 'json_object', schema }` | `createCompletion(prompt, { sampling: { temp: 0, grammar } })` — JSON Schema → GBNF 변환이 필요(`assistant_proto` 에서 `form.v1.gbnf` 를 함께 만들어 manifest 에 싣는 것을 01 계획에 요청) |
| 채팅 틀 | 모델 설정(`mlc-chat-config.json` 의 conv_template)이 적용 | 프롬프트를 Gemma 채팅 틀로 **직접** 조립(`<start_of_turn>user …`) — 학습 때 틀과 글자까지 같아야 한다 |
| 가속 | WebGPU | 기본 CPU(WASM SIMD·멀티스레드) — 멀티스레드는 `Cross-Origin-Opener-Policy`·`Cross-Origin-Embedder-Policy` 헤더가 필요 |
| 이어받기 | 파일(조각) 단위로 충분 | 한 파일이라 **Range 이어받기 필요** — `modelStore` 에 OPFS 임시 파일 + `Range: bytes=n-` 를 더한다 |
| 바꿀 곳 | — | `adapters/wllama.ts`(새), `worker.ts` `case 'wllama'`, `model.ts` `SUPPORTED_RUNTIMES`·`cacheNameFor`, `checkDevice`(WebGPU 대신 `crossOriginIsolated`), `nginx.conf` COOP/COEP |

---

### Task 13: E2E — 대화 → 되묻기 → 확인 화면 → 적용 (개발용 대역)

> **화면 변경(2026-11-26, #176)**: 대본(`SCRIPT`)·시드·정리(`afterAll`)·확인할 결과(예약이 생김)는 그대로. 흐름만 새 창 기준으로: `getByRole('link', { name: 'AI 비서' })` + `toHaveURL(/assistant/)` 대신 **주간 시간표 화면에서** `getByRole('button', { name: 'AI 비서' })` 를 누르거나 `Control+K` → `getByRole('dialog', { name: 'AI 비서' })` 가 보이고 URL 은 그대로 → 입력칸에 SAY1 + Enter → 되묻기 칸의 답 입력칸에 SAY2 → `답하기` → 펼친 창에서 `+ 추가` 태그가 보이고 `기존` 으로 바꾸면 사라짐 → `[적용]` → `적용했습니다` → 창이 닫히고 뒤의 주간 시간표에 새 블록. 덧붙여 `Esc` 로 닫으면 포커스가 `AI 비서` 버튼으로 돌아오는지 한 줄. 스크린샷은 명령창·되묻기·펼친 창 셋.

> 선행: 01 계획 PR B(서버 API)가 main 에 있거나 `E2E_SERVER_DIR` 로 그 서버를 가리킨다. 모델은 쓰지 않는다(개발용 대역 대본) — E2E 는 Vite dev 서버라 `import.meta.env.DEV` 가 참이다.

**Files:**
- Create: `web/e2e/admin-assistant.spec.ts`

**Interfaces:**
- Consumes: `e2e/helpers.ts` — `seedOps`, `login`, `nextAdmin`, `SIZES`, `WEB_URL`, `apiLogin`, `kstDate`, `shot`; `STUB_KEY` 값 `'esc-assistant-stub'`.

E2E 시드 건물은 `운영관`(K) · 강의실 101·102·201·202 다(`helpers.ts` `OPS`). 그래서 스펙 예문의 803 대신 **운영관 201** 을 쓴다. 날짜는 실행하는 요일과 무관하게 미래가 되도록 **다음 주 금요일**.

- [ ] **Step 1: 테스트 작성 `web/e2e/admin-assistant.spec.ts`**

```ts
import { expect, test, type BrowserContext, type Page } from '@playwright/test'
import cfg from './env.json' with { type: 'json' }
import { SIZES, WEB_URL, apiLogin, kstDate, login, nextAdmin, seedOps, shot } from './helpers'
import { addDays, mondayOf } from '../src/lib/time'

declare const localStorage: { setItem(k: string, v: string): void }

const STUB_KEY = 'esc-assistant-stub'
const SAY1 = '운영관 201호 다음 주 금요일 15시부터 18시까지 특강 예약해줘'
const SAY2 = '알고리즘 특강'
const SCRIPT = {
  [SAY1]: {
    v: 1,
    intent: 'event.add',
    target: {},
    set: { rooms: ['운영관 201'], when: '다음 주 금요일', time: '15시부터 18시까지', type: '특강' },
  },
  [SAY2]: { v: 1, intent: 'fill', target: {}, set: { subject: '알고리즘 특강' } },
}

test.describe.configure({ mode: 'serial' })
let ctx: BrowserContext
let page: Page
let roomId: number

test.beforeAll(async ({ browser }) => {
  ctx = await browser.newContext({ baseURL: WEB_URL, locale: 'ko-KR', viewport: SIZES.admin })
  roomId = (await seedOps(ctx.request)).roomIds[201]
  await ctx.addInitScript(([k, v]) => localStorage.setItem(k, v), [STUB_KEY, JSON.stringify(SCRIPT)])
  page = await ctx.newPage()
  await page.goto('/admin/dashboard')
  await login(page, nextAdmin)
})
test.afterAll(async () => {
  // 다른 spec 이 이 방의 예약 수를 세므로 만든 예약을 지운다
  const headers = { authorization: `Bearer ${await apiLogin(ctx.request, cfg.ADMINS[0])}` }
  const r = await ctx.request.get(`/api/rooms/${roomId}/reservations`, { headers })
  for (const v of (await r.json()) as { id: number; subject: string }[])
    if (v.subject === '알고리즘 특강')
      await ctx.request.delete(`/api/rooms/${roomId}/reservations/${v.id}`, { headers })
  await ctx.close()
})

test('AI 비서 — 이름을 되묻고, 기존│수정 확인 뒤 적용하면 예약이 생긴다', async () => {
  await page.getByRole('link', { name: 'AI 비서' }).click()
  await expect(page).toHaveURL(/\/admin\/assistant$/)
  const box = page.getByLabel('AI 비서에게 말하기')
  await box.fill(SAY1)
  await box.press('Enter')
  const chatList = page.getByRole('region', { name: 'AI 비서 대화' })
  await expect(chatList.locator('.chat__msg--ai').getByText(/이름/).last()).toBeVisible()
  await box.fill(SAY2)
  await box.press('Enter')

  const confirm = page.getByRole('region', { name: '변경 확인' })
  await expect(confirm).toBeVisible()
  await expect(confirm.getByText('알고리즘 특강').first()).toBeVisible()
  await expect(confirm.locator('figcaption')).toHaveText(['기존', '수정'])
  await expect(confirm.locator('.pv__side').nth(1).getByText('+ 추가')).toBeVisible()
  await shot(page, 'admin-assistant-preview-1440')

  await confirm.getByRole('button', { name: '적용' }).click()
  await expect(chatList.getByText('적용했습니다. 문 앞 화면으로 보내는 중입니다.')).toBeVisible()
  await expect(confirm).toHaveCount(0)

  const friday = addDays(mondayOf(kstDate()), 7 + 4)
  const headers = { authorization: `Bearer ${await apiLogin(ctx.request, cfg.ADMINS[0])}` }
  const r = await ctx.request.get(`/api/rooms/${roomId}/reservations`, { headers })
  const made = ((await r.json()) as { subject: string; date: string; s_h: number; e_h: number; type: number }[]).find(
    (v) => v.subject === '알고리즘 특강',
  )
  expect(made).toMatchObject({ date: friday, s_h: 15, e_h: 18, type: 5 })

  await page.getByRole('radio', { name: '변경 기록' }).click()
  // 같은 문장이 대화 말풍선에도 있다 — 표 안에서만 찾는다
  await expect(page.getByRole('table').getByText(SAY1)).toBeVisible()
})
```

(`kstDate()` 는 `helpers.ts` 265행 — 오늘 KST `YYYY-MM-DD`. 서버의 질문 문구는 01 계획이 정한다 — 여기서는 `/이름/` 만 본다. `SegmentedControl` 이 라디오 역할이 아니면 `getByRole('button', { name: '변경 기록' })` 로 바꾼다 — `components/ui/SegmentedControl.vue` 마크업을 보고 맞춘다.)

- [ ] **Step 2: 실행**

Run: `cd web && pnpm e2e e2e/admin-assistant.spec.ts`
Expected: PASS. 실패하면 `e2e/.tmp/server.log` 와 trace 를 보고 — 서버 질문·미리보기가 부록 §4.2 모양과 다르면 **01 계획(서버)** 쪽 문제로 이슈를 남긴다(웹에서 보정하지 않는다).

- [ ] **Step 3: 커밋**

```bash
git add web/e2e/admin-assistant.spec.ts
git commit -m "test(web): AI 비서 E2E — 되묻기 → 기존│수정 확인 → 적용 → 예약 생성"
```

---

### Task 14: 전체 게이트 + PR ε

- [ ] **Step 1: full 게이트**

```bash
cd web
pnpm test && pnpm lint && pnpm exec vue-tsc --noEmit
pnpm build
pnpm e2e
```

Expected: 전부 통과. `pnpm build` 산출물에서 관리자 화면 청크에 `web-llm` 문자열이 없는지:

```bash
grep -l "CreateMLCEngine" dist/assets/*.js
```

Expected: Worker 청크 파일 하나만 나온다(`assets/worker/` 아래. 관리자 화면 청크 `admin-*.js` 는 나오지 않는다).

- [ ] **Step 2: PR ε**

```bash
git push -u origin feat/ai-assistant-model
gh pr create --title "feat(web): AI 비서 모델 받기·검증·WebLLM 실행, CSP" --body "<아래 본문>"
```

본문:
- Task 11~14 요약
- 0단계 결과(02 계획 선정 문서 링크)와 고른 실행 도구
- 게이트 결과(`test`·`lint`·`vue-tsc`·`build`·`e2e`)
- 실기: 학과 관리자 PC(또는 같은 사양)에서 첫 다운로드 시간, 문장 1개 응답 시간(합격선 ≤ 5초), 새로고침 뒤 재다운로드 0, CSP 위반 0 — 스크린샷
- 배포 순서: 이 PR 머지 → 02 계획 릴리스 PR(`server/app/assistant/model.json` 판 지정) 머지 = 운영에서 모델 사용 시작. 이 PR 만 머지되면 안내가 enabled:false 라 화면은 '준비 중' 그대로

## 이후

- 2단계(spec §1 비목표): 되돌리기 화면(`POST /api/assistant/changes/{id}/revert` 가 생기면 변경 기록 행에 [되돌리기] → 같은 확인 화면), 모델을 못 돌리는 PC 의 서버 측 대체 실행.
- `web/CLAUDE.md` 의 "디자인 스펙 = mh" 문구는 01 계획의 CLAUDE.md·CODEOWNERS 정리 PR 이 바꾼다(이 계획은 건드리지 않는다).
