# 대학 로고 강 — 구현 계획 (plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- 생성일시: 2026-11-04

**Goal:** 메인 페이지와 인증 화면 뒤로 대학 로고를 흘리고, PC 메인 페이지에서만 로고를 잡아 던질 수 있게 한다.

**Architecture:** `logoRiver.ts` 가 크기 · 자리 · 캡슐 접촉을 계산하고, `LogoRiver.vue` 는 그 결과를 CSS 애니메이션으로 흘린다. PC 메인만 `riverPhysics.ts`(DOM 없는 순수 물리)와 `LogoRiverPhysics.vue`(포인터 · rAF)로 대체한다. 물리는 메인 페이지 폴더에 두어 관리자 번들에 들어가지 않는다.

**Tech Stack:** Vue 3 + TypeScript + Vitest + Playwright (pnpm). 새 의존성 없음.

**Spec:** `docs/specs/2026-11-04-landing-logo-river-design.md` · 화면: `docs/design/screens/landing.md` 「로고 강」, `docs/design/screens/auth.md` 「넓은 폭」

## Global Constraints

- `web/` 와 위 문서만 고친다. `server/`, `firmware/`, `modempi/`, `lora_proto/` 금지. `pnpm` 만 쓴다. `package.json` 의존성을 늘리지 않는다.
- 색 · 간격은 토큰(`var(--surface)` 등)을 쓴다. 예외는 로고 파일 안의 색뿐이다.
- 조절값은 `TUNING` 한곳에만 둔다: `FLOW 40`, `FLOW_TAU 0.8`, `LANE_K 1.2`, `LANE_DAMP 1.6`, `LANE_DODGE 140`, `LANE_RETURN_TAU 6`, `RESTITUTION 0.55`, `WALL_RESTITUTION 0.5`, `HOLD_TAU 0.05`, `THROW_MAX 900`, `BOB_PX 6`.
- 물리 조건 문자열(정확히): `(min-width: 1024px) and (hover: hover) and (pointer: fine)`, 그리고 `(prefers-reduced-motion: reduce)` 가 아님.
- 고지 문구(정확히): `표시된 로고는 각 대학의 상표이며, 제휴나 도입을 뜻하지 않습니다.` 인증 왼쪽 한 줄(정확히): `지금 빈 강의실 · 이번 주 시간표 · 예약 신청·승인`
- 판은 `aria-hidden="true"`, 이미지는 `alt=""` · `draggable="false"`. 메인 페이지에서 서버를 부르지 않는다.
- 커밋에 AI 저작 표기 · `Co-Authored-By` 금지. force push · `reset --hard` 금지. 작업은 `wj`. PR 은 사용자가 지시할 때만 연다.
- Windows `autocrlf` — prettier 는 고친 파일에만 `--end-of-line auto`, 변경 확인은 `git diff --ignore-cr-at-eol`. 줄바꿈만 다른 `web/e2e/student.spec.ts` 는 내용이 바뀌지 않으면 커밋하지 않는다.
- 머지는 이 작업에 한해 wj 가 한다(팀장 지시, 2026-11-04). 단 **코드 PR 은 cw 의 로고 사용 확인 전에 머지하지 않는다**(`main` 머지 = 운영 반영, spec §3).

## Review Focus

1. 잡은 채 창을 전환하거나 창 밖에서 놓음 → 로고가 손에 붙어 남지 않고 속도 0으로 놓인다. (Task 5)
2. 잡고 오래 서 있음 → 뒤에서 오는 로고가 줄지어 멈추지 않고 옆으로 비켜 지나간다. (Task 4)
3. 탭을 오래 숨겼다가 돌아옴 → 순간이동이나 폭주 없이 이어서 흐른다. (Task 4)
4. 잡은 채 창을 1024 아래로 줄임 → 모드가 바뀌며 리스너 · rAF 가 남지 않는다. (Task 5)
5. 작은 모니터에서 연 창을 큰 모니터로 옮겨 넓힘 → 화면 안에서 로고가 튀어 나타나지 않는다. (Task 4)

---

### Task 1: 스펙 커밋과 로고 수집

**Files:**
- Commit: `docs/specs/2026-11-04-landing-logo-river-design.md`, `docs/plans/2026-11-04-landing-logo-river.md`, `docs/design/screens/landing.md`, `docs/design/screens/auth.md`
- Create: `web/src/assets/logos/*.svg`(없으면 `*.png`), `web/src/assets/logos/logos.json`
- Test: `web/src/components/domain/__tests__/logos.spec.ts`

**Interfaces:**
- Produces: `logos.json` — `LogoEntry[]`, `rank` 오름차순. `{ slug: string; name: string; rank: number; file: string; source: string; license: string; aspect: number }`

- [ ] **Step 1: 스펙 커밋.** 사용자 확인 후 `docs: 대학 로고 강 스펙 · 계획` 으로 커밋한다. 스펙 PR 을 코드보다 먼저 연다(사용자 지시 시).

- [ ] **Step 2: 실패하는 테스트.** `logos.json` 과 파일을 `node:fs` 로 읽는다.

```ts
it('16~26개, rank 오름차순·중복 없음, 필수 값이 있다')
it('file 이 모두 있고 목록 밖 파일은 없다. 확장자는 svg 또는 png')
it('svg 40 KB · png 120 KB 이하, 합계 800 KB 이하')
it('aspect 는 파일 비율(svg viewBox, png IHDR)과 ±5% 안에서 같고 4 이하')
it('png 는 알파가 있다(IHDR color type 4·6 또는 tRNS)')
it('svg 에 <script · on*= · 외부 href(http) 가 없다') // xmlns 의 w3.org 는 제외
it('source 는 https 주소다')
```

Run: `cd web && pnpm exec vitest run src/components/domain/__tests__/logos.spec.ts` → FAIL.

- [ ] **Step 3: 수집.** 스펙 §2 표 순서대로 **1위부터** 대학 공식 UI 페이지와 Wikimedia Commons 를 확인해 SVG 를 받고, 없으면 배경이 투명한 PNG 를 받는다. 받은 파일은 데이터로만 다루고(실행 금지, 임시 폴더에 받아 XML 파싱 확인) 다음 규칙을 따른다.
  - 벡터 자동 변환 금지. 흰 배경 PNG 의 배경을 직접 지우지 않는다(가장자리가 깨진다). 공식 페이지의 현재 로고와 눈으로 대조해 옛 로고는 버린다.
  - 같은 대학에 심볼과 글자 로고가 있으면 aspect 가 작은 쪽. 흰 배경 사각형은 지운다(내용 변경은 이것뿐).
  - 40 KB 를 넘으면 `npx svgo@3 --multipass <file>` 1회(의존성 추가 없음).
  - 20개를 채우면 멈춘다. 명지전문대학은 파일을 구하면 목록 가운데에 넣는다(`rank` 는 그 앞 순위와 같은 값 + 0.5).

- [ ] **Step 4: 16개 미만이면 멈추고 보고한다.** 구한 대학 · 못 구한 대학 · 확인한 주소를 사용자에게 알린다. 특히 연세대(4위)의 파일을 구하지 못했다면 알린다.

- [ ] **Step 5: 로고 모음을 사용자에게 보여 주고 확인받는다.** 모든 로고를 흰 바탕 격자로 렌더링한 스크린샷을 `web/e2e/.shots/logos-sheet.png` 에 저장해 깨진 파일과 옛 로고를 함께 확인한다.

- [ ] **Step 6: 테스트 통과 후 커밋.** Run 위 명령 → PASS. `git add web/src/assets/logos web/src/components/domain/__tests__/logos.spec.ts`, `feat(web): 대학 로고 파일 · 목록`.

---

### Task 2: 크기 · 자리 · 캡슐 접촉

**Files:**
- Create: `web/src/components/domain/logoRiver.ts`
- Test: `web/src/components/domain/__tests__/logoRiver.spec.ts`

**Interfaces:**
- Consumes: `logos.json`
- Produces:

```ts
export interface LogoEntry { slug: string; name: string; rank: number; file: string; source: string; license: string; aspect: number }
export interface Capsule { x: number; y: number; r: number; s: number }
export interface RiverLogo extends Capsule { slug: string; url: string; w: number; h: number; d: number; dl: number } // x,y 중심. d·dl 은 몽글몽글 주기·지연(초)
export const LOGOS: LogoEntry[]
export function logoUrl(file: string): string // import.meta.glob('../../assets/logos/*.{svg,png}', { eager: true, query: '?url', import: 'default' })
export function logoSize(i: number, n: number, aspect: number, k: number): { w: number; h: number }
export function capsuleShape(w: number, h: number): { r: number; s: number } // r = min(w,h)/2, s = max(0,(w-h)/2)
export function capsuleContact(a: Capsule, b: Capsule, W: number): { nx: number; ny: number; overlap: number } | null
export function layoutLogos(entries: LogoEntry[], o: { W: number; H: number; k: number }): RiverLogo[]
export function riverCoverEdge(heroW: number): number // max(0,(heroW-1280)/2)+560
```

- [ ] **Step 1: 실패하는 테스트**

```ts
it('logoSize — 첫째 D 170, 마지막 D 110, w×h = D², w/h = aspect')
it('logoSize — n=1 이어도 D 170 (0으로 나누지 않는다)')
it('logoSize — k 배율이 w,h 에 곱해진다')
it('capsuleContact — 원 둘: 떨어지면 null, 겹치면 overlap = r합 - 거리, 단위 법선')
it('capsuleContact — 가로 캡슐 둘이 옆으로 닿고 위아래로 지나갈 수 있다')
it('capsuleContact — W 경계를 넘어 가장 짧은 쪽으로 잰다 (x=10 과 x=W-10 은 거리 20)')
it('capsuleContact — 완전히 같은 자리여도 NaN 이 아니고 법선 길이 1')
it.each([[2000,720,1],[1440,470,.72],[1120,430,.56],[600,200,.3]])('layoutLogos — 로고 20개가 경계 포함 겹치지 않고 위아래 안에 있다')
it('layoutLogos — 두 번 불러도 결과가 같다')
it('layoutLogos — 크기 순서가 왼쪽부터 줄지어 있지 않다') // 앞 5개의 x 가 오름차순이 아님
it('layoutLogos — 빈 목록이면 빈 배열')
it('riverCoverEdge — 1280 폭 560, 2560 폭 1200')
```

Run: `cd web && pnpm exec vitest run src/components/domain/__tests__/logoRiver.spec.ts` → FAIL.

- [ ] **Step 2: 구현.** `capsuleContact` 는 회전이 없으므로 아래로 충분하다.

```ts
let dx = b.x - a.x
dx -= W * Math.round(dx / W)
const gapX = Math.max(0, Math.abs(dx) - a.s - b.s)
const dy = b.y - a.y
const dist = Math.hypot(gapX, dy)
const overlap = a.r + b.r - dist
if (overlap <= 0) return null
if (dist < 1e-6) return { nx: 0, ny: 1, overlap }
return { nx: (Math.sign(dx) * gapX) / dist, ny: dy / dist, overlap }
```

`layoutLogos` 는 `x = frac(i × 0.618) × W`, `y = r + frac(i × 0.382 + 0.2) × (H − 2r)` 로 흩은 뒤 겹친 쌍을 법선 방향으로 밀어내기를 최대 300회 반복한다. `d = 4 + (i % 5) × 0.7`, `dl = -(i × 1.3)`(시안 값).

- [ ] **Step 3: 통과 후 커밋.** `feat(web): 로고 강 크기 · 자리 계산`.

---

### Task 3: 흐르기만 하는 판

**Files:**
- Create: `web/src/components/domain/LogoRiver.vue`
- Test: `web/src/components/domain/__tests__/LogoRiver.spec.ts`

**Interfaces:**
- Consumes: `LOGOS`, `layoutLogos`
- Produces: `<LogoRiver :k="number" :height="number" />` — 루트 `.river`, 부모를 `position: absolute; inset: 0` 으로 채운다.

- [ ] **Step 1: 실패하는 테스트**

```ts
it('로고마다 두 벌 — img 수 = 2N, alt 빈 값, draggable=false')
it('루트 aria-hidden, 링크·버튼 없음')
it('트랙 폭 = 2W, 지속 시간 = W ÷ (40 × max(k, 0.7)) 초') // k=1, W=2000 → 4000px, 50s
it('.river--physics 클래스가 없다')
```

- [ ] **Step 2: 구현.** `W = max(2000 × k, screen.width)`. 트랙에 `@keyframes` 로 `translateX(-50%)` 무한 반복, 로고마다 위아래 ±7px · 크기 0.985~1.015 교대 반복(시안 `esc-bob`). 움직임 줄이기는 `base.css` 전역 규칙이 끈다. `overflow: hidden`, `pointer-events: none`.

- [ ] **Step 3: 통과 후 커밋.** `feat(web): LogoRiver — 흐르는 대학 로고 판`.

---

### Task 4: 물리

**Files:**
- Create: `web/src/student/views/landing/riverPhysics.ts`
- Test: `web/src/student/__tests__/riverPhysics.spec.ts`

**Interfaces:**
- Consumes: `RiverLogo`, `capsuleContact`
- Produces:

```ts
export const TUNING: { FLOW: number; FLOW_TAU: number; /* Global Constraints 의 값 전부 */ }
export const WRAP_MARGIN = 200
export interface Body extends RiverLogo { vx: number; vy: number; m: number; homeY: number; laneY: number; bob: number; phase: number }
export interface World { bodies: Body[]; W: number; H: number; held: number; target: { x: number; y: number } | null; grabDx: number; grabDy: number; acc: number; t: number }
export function createWorld(logos: RiverLogo[], W: number, H: number): World // x 는 layout x - WRAP_MARGIN, 초기 vx = -FLOW
export function step(w: World, dt: number): void
export function advance(w: World, elapsed: number): number // 고정 스텝 1/60, elapsed 는 0.05 로 자르고 최대 3스텝. 돌린 스텝 수 반환
export function ensureWidth(w: World, heroW: number): void // W = max(W, heroW + 400). 줄이지 않는다
export function hitTest(w: World, px: number, py: number, minX: number): number // 없으면 -1. 겹치면 가장 작은 로고, px < minX 면 -1
export function grab(w: World, i: number, px: number, py: number): void
export function moveGrab(w: World, px: number, py: number, heroW: number): void // 목표를 히어로 안으로 자른다
export function release(w: World, vx: number, vy: number): void // 크기를 THROW_MAX 로 자른다
export function pointerVelocity(samples: { t: number; x: number; y: number }[], now: number): { vx: number; vy: number } // 최근 100ms. 마지막 표본이 100ms 넘게 오래되면 0
export function bodyTransform(b: Body, t: number): string // translate3d(xpx, ypx, 0) scale(s) — x,y 는 좌상단
```

- [ ] **Step 1: 실패하는 테스트**

```ts
it('아무도 안 건드리면 모두 vx ≈ -40, 1초에 약 40px 왼쪽')
it('왼쪽 -WRAP_MARGIN 을 지나면 W 만큼 오른쪽으로, 오른쪽으로 던져 넘어가면 반대로')
it('throw — release(900,0) 뒤 5초 안에 vx 가 -40 ±2, 이동 거리 720px 이하')
it('release — 크기 5000 을 넣어도 속도 크기 900')
it('collision — 던진 로고가 정지한 로고에 닿으면 상대가 밀리고 겹침이 1프레임 뒤 2px 이하')
it('collision — 작은 로고가 큰 로고보다 더 많이 밀린다(질량 ∝ 면적)')
it('wall — 위로 던져도 y 는 r 안쪽, 튕겨 내려온다')
it('held — 잡힌 로고는 충돌로 밀리지 않고 0.3초 안에 목표에 2px 이내')
it('held — 목표가 히어로 밖이면 히어로 안에 머문다')
it('dodge — 잡힌 로고와 y 가 같은 뒤 로고가 10초 안에 왼쪽으로 지나간다') // Review Focus 2, y 완전 일치 포함
it('dodge — 잡힌 로고가 위 벽 근처면 아래로 비켜 간다')
it('dodge — 지나간 뒤 laneY 가 homeY 로 돌아온다(30초 뒤 5px 이내)')
it('advance — 3600초를 넘겨도 최대 3스텝, 위치가 튀지 않는다') // Review Focus 3
it('ensureWidth — 넓힐 때만 W 를 키운다') // Review Focus 5
it('hitTest — 캡슐 끝 둥근 부분 밖은 -1, minX 왼쪽은 -1, 겹치면 작은 쪽')
it('pointerVelocity — 최근 100ms 평균, 멈춘 뒤 놓으면 0, 표본 하나면 0')
it('bodyTransform — 잡히면 bob 이 0 으로 줄고, 흐름을 되찾으면 돌아온다')
it('1시간 — 시드 고정 던지기를 섞어 돌려도 NaN 없음, 평균 |y - homeY| < 120, 겹침 평균 < 2px') // 216000 스텝
```

Run: `cd web && pnpm exec vitest run src/student/__tests__/riverPhysics.spec.ts` → FAIL.

- [ ] **Step 2: 구현.** `step` 순서는 spec §4 그대로. 스펙만으로 정해지지 않는 부분:

```ts
// 흐름 복귀 (안 잡힌 로고)
b.vx += (-FLOW - b.vx) * (1 - Math.exp(-dt / FLOW_TAU))
b.vy += (-LANE_K * (b.y - b.laneY) - LANE_DAMP * b.vy) * dt
b.laneY += (b.homeY - b.laneY) * (1 - Math.exp(-dt / LANE_RETURN_TAU))

// 잡힌 로고: 목표를 따라가고, 움직임이 곧 속도(충돌에서 다른 로고를 민다). 역질량 0
const nx = h.x + (tx - h.x) * (1 - Math.exp(-dt / HOLD_TAU))
h.vx = (nx - h.x) / dt

// 잡힌 로고와 닿은 로고: 위아래 통로 중 로고 지름이 들어가는 쪽으로 줄을 옮긴다.
// 흐름 힘만으로는 줄 복원력을 못 이겨 뒤에 줄지어 멈춘다
const up = h.y - h.r - 2 * b.r >= 0, down = h.y + h.r + 2 * b.r <= H
const dir = !up ? 1 : !down ? -1 : b.y === h.y ? (b.y < H / 2 ? 1 : -1) : Math.sign(b.y - h.y)
b.laneY = clamp(b.laneY + dir * LANE_DODGE * dt, b.r, H - b.r)
```

충돌은 스텝당 2회 반복한다. 겹침을 역질량 비율로 풀고, 접근 중일 때만 `RESTITUTION` 으로 충격량을 준 뒤 안 잡힌 로고의 속도 크기를 `THROW_MAX` 로 자른다. `m = w × h`, 잡힌 로고의 역질량은 0. `bob` 은 잡혔거나 `|v - 흐름| > 60` 이면 0으로, 아니면 1로 시간상수 0.6초로 움직인다. 그리기 오프셋은 `BOB_PX × sin(2πt / (2d) + phase) × bob`.

- [ ] **Step 3: 통과 후 커밋.** `feat(web): 로고 강 물리 — 흐름 · 충돌 · 잡기 · 던지기`.

---

### Task 5: 잡고 던지는 판

**Files:**
- Create: `web/src/student/views/landing/LogoRiverPhysics.vue`, `web/src/student/views/landing/useRiverMode.ts`
- Test: `web/src/student/__tests__/LogoRiverPhysics.spec.ts`

**Interfaces:**
- Consumes: Task 2 · 4 전부, `components/ui/Button.vue`
- Produces:
  - `useRiverMode(): Ref<boolean>` — 물리 켤지. `window.matchMedia` 가 없으면 false. 조건이 바뀌면 값이 바뀌고 `onScopeDispose` 로 정리.
  - `<LogoRiverPhysics :surface="HTMLElement | null" />` — 루트 `.river.river--physics`. 포인터는 `surface`(히어로)에 건다.

- [ ] **Step 1: 실패하는 테스트.** `matchMedia` · `requestAnimationFrame` · `setPointerCapture` 를 스텁한다. 시각은 스텁한 rAF 로 진행한다.

```ts
it('useRiverMode — 두 조건이 맞을 때만 true, change 이벤트에 따라간다')
it('useRiverMode — matchMedia 없으면 false')
it('img 수 = N(복제 없음), alt 빈 값, 루트 aria-hidden')
it('덮인 곳(riverCoverEdge + 140 왼쪽)의 로고는 잡히지 않는다')
it('링크에서 시작한 pointerdown 은 잡지 않고 preventDefault 도 안 한다')
it('마우스 왼쪽 버튼만 잡는다 — pointerType touch, button 2 는 무시')
it('로고 위 pointermove → surface 커서 grab, 잡으면 grabbing, 놓으면 해제')
it('pointerdown → setPointerCapture + preventDefault')
it('pointerup — 표본 속도로 release')
it.each(['pointercancel', 'lostpointercapture'])('%s — 속도 0으로 놓는다') // Review Focus 1
it('window blur — 속도 0으로 놓는다') // Review Focus 1
it('unmount — 리스너 제거, rAF 취소, 커서 복구') // Review Focus 4
it('멈춤 — 문구 재생으로, rAF 멈춤, 잡히지 않음. 재생하면 이어서')
it('히어로가 화면 밖(IntersectionObserver)·document.hidden 이면 rAF 를 돌리지 않는다')
```

Run: `cd web && pnpm exec vitest run src/student/__tests__/LogoRiverPhysics.spec.ts` → FAIL.

- [ ] **Step 2: 구현.** 프레임마다 Vue 상태를 바꾸지 않고 `img.style.transform` 만 쓴다. 자리는 `layoutLogos(LOGOS, { W, H: 720, k: 1 })`, `W = max(2000, screen.width + 400)`. 프레임마다 `ensureWidth(world, surface.clientWidth)` → `advance` → `bodyTransform`. `mouse` 포인터의 표본은 잡은 동안 최근 150ms 만 보관한다. `IntersectionObserver` 가 없는 환경은 보이는 것으로 친다. 버튼은 `Button variant="secondary"`, 오른쪽 아래 16px, 높이 44px, 문구 `멈춤` / `재생`.

- [ ] **Step 3: 통과 후 커밋.** `feat(web): LogoRiverPhysics — PC 메인 로고 잡고 던지기`.

---

### Task 6: 메인 페이지 히어로

**Files:**
- Modify: `web/src/student/views/landing/LandingView.vue`
- Test: `web/src/student/__tests__/landing.spec.ts`

**Interfaces:**
- Consumes: `LogoRiver`, `LogoRiverPhysics`, `useRiverMode`, `riverCoverEdge`

- [ ] **Step 1: 테스트 수정(실패 확인).**

```ts
it('히어로 — 제목 h1, 로그인(brand 하나)·가입 신청, 보조 문구와 미리보기 없음') // .hero 안 [role="img"] 0개, '학교 웹메일로 가입 · 관리자' 없음
it('matchMedia 없으면 LogoRiver, 조건이 맞으면 LogoRiverPhysics')
it('바닥글 고지 — 표시된 로고는 각 대학의 상표이며, 제휴나 도입을 뜻하지 않습니다.')
it('미리보기는 넷, 카드 1은 3행 — 수업중·시험중, ★ 하나') // 기존 미리보기 테스트에서 히어로 항목을 뺀다
it('학교 이름을 쓰지 않는다') // 기존 유지 — 로고가 alt 빈 값이므로 그대로 통과해야 한다
```

- [ ] **Step 2: 구현.** `landing.md` 표의 값대로.
  - `.lh` 는 히어로 안 `position: absolute`(sticky 제거, 바탕 · 선 없음). 폰 · 태블릿 58px, `≥ 1024` 72px. 버튼은 `surface` 바탕 유지.
  - `≥ 1024`: `.hero` 높이 720px. 덮개 `linear-gradient(90deg, var(--surface) calc(max(0px, (100% - 1280px) / 2) + 560px), transparent calc(max(0px, (100% - 1280px) / 2) + 840px))`, `pointer-events: none`. `riverCoverEdge` 와 숫자를 맞춘다. `.hero__text` 최대 480px, 판 위에 놓는다.
  - `< 1024`: `<LogoRiver :k="0.56" :height="430" />` 를 위 40px 띠로, 글자는 `padding-top: 360px`, 덮개는 띠 아래 40%→54% 로 바탕색. 태블릿은 글 가운데 정렬.
  - `physics = useRiverMode()` 로 `≥ 1024` 물리 판을 고른다. 넓지만 터치인 화면은 `:k="1" :height="720"` 의 `LogoRiver`. 폭 판별은 `useMediaQuery` 없이 `matchMedia('(min-width: 1024px)')` 를 `useRiverMode.ts` 에 함께 둔다(`useRiverWide(): Ref<boolean>`).

- [ ] **Step 3: 통과 후 커밋.** `feat(web): 메인 페이지 히어로 — 대학 로고 강`. `git add` 는 `LandingView.vue`, `useRiverMode.ts`, `landing.spec.ts` 만.

---

### Task 7: 인증 화면

**Files:**
- Modify: `web/src/auth/AuthShell.vue`
- Test: `web/src/auth/__tests__/shell.spec.ts`, 필요 시 `web/src/auth/__tests__/login.spec.ts`, `web/src/student/__tests__/gate.spec.ts`

**Interfaces:**
- Consumes: `LogoRiver`

- [ ] **Step 1: 테스트 수정(실패 확인).**

```ts
it('학생 왼쪽 — ESC 링크, 한 문장, 한 줄 "지금 빈 강의실 · 이번 주 시간표 · 예약 신청·승인", LogoRiver 하나')
it('home 이면 폰 띠 .auth__band — LogoRiver, ‹ ESC 링크(/), 한 문장. home 아니면 없음')
it('surface=admin 이면 왼쪽도 띠도 그리지 않는다')
it('어디에도 .river--physics 가 없다')
```

- [ ] **Step 2: 구현.** `auth.md` 값대로. 왼쪽 `<LogoRiver :k="0.72" :height="470" />`, 덮개 `linear-gradient(180deg, transparent 44%, var(--surface) 68%)`, 글자는 맨 아래. 폰 띠 `<LogoRiver :k="0.3" :height="200" />`, 높이 270px, `≥ 640` 에서 숨김. 띠의 `‹ ESC` 가 있는 폰 로그인에서는 카드의 `.auth__brand` 를 숨겨 이름이 두 번 나오지 않게 한다.

- [ ] **Step 3: 통과 후 커밋.** `feat(web): 인증 화면 왼쪽 · 폰 로그인 띠 — 대학 로고 흐름`.

---

### Task 8: 실제 브라우저 확인과 전체 게이트

**Files:**
- Create: `web/e2e/landing-river.spec.ts`
- Modify: 깨진 경우에만 `web/e2e/student.spec.ts`, `web/e2e/login.spec.ts`

- [ ] **Step 1: E2E 작성.** 프로젝트 기본이 `reducedMotion: 'reduce'` 이므로 물리 테스트는 파일에서 `test.use({ reducedMotion: 'no-preference' })` 로 켠다. 로그인이 필요 없어 `beforeAll` 로그인은 두지 않는다.

```ts
test('PC — 잡으면 포인터를 따라 멈춰 있고, 다른 로고는 계속 흐른다')
test('PC — 던지면 날아갔다가 5초 안에 왼쪽 약 40 px/s 로 돌아온다')
test('PC — 로그인 링크 클릭은 그대로 /login 으로 간다')
test('PC — 멈춤 누르면 위치 고정, 재생하면 이어서')
test('폰 390 · 태블릿 768 터치 — .river--physics 없음, 트랙은 흐른다')
test('로그인 1280 — .river 있고 .river--physics 없음, 잡아도 움직이지 않는다')
test('움직임 줄이기 — 두 시점의 위치가 같고 멈춤 버튼이 없다') // 이 테스트만 reduce
test('390 · 768 · 1280 · 2560 폭 — 가로 스크롤 없음, 스크린샷 저장')
```

Run: `cd web && E2E_API_PORT=8200 E2E_WEB_PORT=6173 pnpm e2e landing-river` → PASS.

- [ ] **Step 2: 시안과 대조.** `web/e2e/.shots/` 스크린샷을 `D-Landing` · `D-Login` · `D-Phone` 과 비교한다. 애니메이션 도중에 찍지 말고 `.page` 의 `opacity: 1` 을 기다린다.

- [ ] **Step 3: 손맛 확인을 사용자에게 요청한다.** dev 서버를 띄우고 사용자가 직접 던져 본다. 고칠 값은 `TUNING` 과 spec §4 표를 함께 바꾼다. **던지는 느낌은 자동 테스트로 판단하지 않는다.**

- [ ] **Step 4: 전체 게이트.**

```bash
cd web && pnpm test && pnpm lint && pnpm exec vue-tsc --build && pnpm build
E2E_API_PORT=8200 E2E_WEB_PORT=6173 pnpm e2e
```

추가 확인: `dist/assets` 의 관리자 번들에 `riverPhysics` 코드가 없다(`THROW_MAX` 검색). 로고 합계 800 KB 이하. `git diff --stat main -- web/package.json web/pnpm-lock.yaml` 이 비어 있다.

- [ ] **Step 5: 커밋 후 PR 은 지시를 기다린다.** PR 본문에 `머지 전 cw 로고 사용 확인 필요` 를 맨 위에 적는다. 제목 `feat(web): 메인 · 인증 화면 대학 로고 강, PC 메인 잡고 던지기`.

## 이후

- 조절값 확정 후 spec §4 표를 실제 값으로 갱신한다.
- 경진대회 전 전시 PC(해상도 · 입력 장치)에서 한 번 더 던져 본다.

## Self-Review (계획 검토)

- 스펙 커버리지: 목표 1 → Task 6 · 7, 목표 2 → Task 4 · 5, 목표 3 → Task 1 · 2, 목표 4 → Task 5 · 6 · 8. §3 로고 확인 → Global Constraints · Task 8. 성공 기준 전부 Task 4 · 5 · 8 테스트. ✅
- 함정 선제 회피: E2E 기본 `reducedMotion: reduce`, 흐름 힘이 줄 복원력을 못 이겨 잡은 로고 뒤에 멈추는 문제(`LANE_DODGE`), 대부분 가로 로고라 원 충돌 불가(캡슐), `n=1` 나눗셈, 좌우 잇기 경계의 충돌. ✅
- 사전 조사로 확인한 SVG 는 26곳 중 12곳이다(투명 PNG 는 2026-11-04 허용). 최소 16개를 못 채울 위험이 있어 Task 1 에 멈춤 지점을 두었다. ✅
