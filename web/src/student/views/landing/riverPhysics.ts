// 대학 로고 강의 물리 — DOM 없는 순수 계산 (docs/specs/2026-11-04-landing-logo-river-design.md §4)
// 라이브러리를 쓰지 않는다: 회전 없는 캡슐 20개와 흐름 힘이면 충분하다
import { capsuleContact, type RiverLogo } from '@/components/domain/logoRiver'

/** 손맛 조절값 — 실제로 던져 보고 맞춘다. 바꾸면 spec §4 표도 함께 */
export const TUNING = {
  FLOW: 40, // px/s 흐름 속도
  FLOW_TAU: 0.8, // s 속도가 흐름으로 돌아가는 시간
  LANE_K: 1.2, // /s² 자기 줄로 돌아가는 힘
  LANE_DAMP: 1.6, // /s 세로 흔들림 줄임
  LANE_DODGE: 140, // px/s 잡힌 로고에 닿았을 때 줄을 옮기는 속도
  LANE_RETURN_TAU: 6, // s 옮긴 줄이 원래 줄로 돌아오는 시간
  RESTITUTION: 0.55,
  WALL_RESTITUTION: 0.5,
  HOLD_TAU: 0.05, // s 잡았을 때 따라오는 지연
  THROW_MAX: 900, // px/s
  BOB_PX: 6, // px 몽글몽글 폭
} as const

/** 화면 왼쪽 밖 이만큼에서 세계가 이어진다. 가장 긴 로고의 반폭보다 크다 */
export const WRAP_MARGIN = 200

const STEP = 1 / 60
const MAX_STEPS = 3
const SOLVER_PASSES = 2
const BOB_TAU = 0.6
const BOB_OFF_SPEED = 60 // 흐름과 이만큼 다르면 몽글몽글을 끈다
const BOB_SCALE = 0.015
const VELOCITY_WINDOW_MS = 100

export interface Body extends RiverLogo {
  vx: number
  vy: number
  m: number
  homeY: number
  laneY: number
  bob: number
  phase: number
}

export interface World {
  bodies: Body[]
  W: number
  H: number
  held: number
  target: { x: number; y: number } | null
  grabDx: number
  grabDy: number
  acc: number
  t: number
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

export function createWorld(logos: RiverLogo[], W: number, H: number): World {
  return {
    bodies: logos.map((l) => ({
      ...l,
      x: l.x - WRAP_MARGIN,
      vx: -TUNING.FLOW,
      vy: 0,
      m: l.w * l.h,
      homeY: l.y,
      laneY: l.y,
      bob: 1,
      phase: (2 * Math.PI * l.dl) / (2 * l.d),
    })),
    W,
    H,
    held: -1,
    target: null,
    grabDx: 0,
    grabDy: 0,
    acc: 0,
    t: 0,
  }
}

/** 잡힌 로고에 닿은 로고가 줄을 어느 쪽으로 옮길지. 지름이 들어가는 통로로 간다 */
function dodgeDir(h: Body, b: Body, H: number): number {
  const up = h.y - h.h / 2 - b.h >= 0
  const down = h.y + h.h / 2 + b.h <= H
  if (!up) return 1
  if (!down) return -1
  if (b.y === h.y) return b.y < H / 2 ? 1 : -1
  return Math.sign(b.y - h.y)
}

function integrate(w: World, dt: number) {
  const { FLOW, FLOW_TAU, LANE_K, LANE_DAMP, LANE_RETURN_TAU, HOLD_TAU } = TUNING
  w.bodies.forEach((b, i) => {
    if (i === w.held && w.target) {
      // 움직임이 곧 속도 — 충돌에서 다른 로고를 민다
      const a = 1 - Math.exp(-dt / HOLD_TAU)
      const nx = b.x + (w.target.x - b.x) * a
      const ny = b.y + (w.target.y - b.y) * a
      b.vx = (nx - b.x) / dt
      b.vy = (ny - b.y) / dt
      b.x = nx
      b.y = ny
    } else {
      b.vx += (-FLOW - b.vx) * (1 - Math.exp(-dt / FLOW_TAU))
      b.vy += (-LANE_K * (b.y - b.laneY) - LANE_DAMP * b.vy) * dt
      b.laneY += (b.homeY - b.laneY) * (1 - Math.exp(-dt / LANE_RETURN_TAU))
      b.x += b.vx * dt
      b.y += b.vy * dt
    }
  })
}

function solveCollisions(w: World, dt: number) {
  const { RESTITUTION, LANE_DODGE } = TUNING
  const { bodies } = w
  for (let pass = 0; pass < SOLVER_PASSES; pass++) {
    for (let i = 0; i < bodies.length; i++) {
      for (let j = i + 1; j < bodies.length; j++) {
        const a = bodies[i]
        const b = bodies[j]
        const hit = capsuleContact(a, b, w.W)
        if (!hit) continue
        const ia = i === w.held ? 0 : 1 / a.m
        const ib = j === w.held ? 0 : 1 / b.m
        const sum = ia + ib
        a.x -= hit.nx * hit.overlap * (ia / sum)
        a.y -= hit.ny * hit.overlap * (ia / sum)
        b.x += hit.nx * hit.overlap * (ib / sum)
        b.y += hit.ny * hit.overlap * (ib / sum)
        const vn = (b.vx - a.vx) * hit.nx + (b.vy - a.vy) * hit.ny
        if (vn < 0) {
          const imp = (-(1 + RESTITUTION) * vn) / sum
          a.vx -= imp * ia * hit.nx
          a.vy -= imp * ia * hit.ny
          b.vx += imp * ib * hit.nx
          b.vy += imp * ib * hit.ny
        }
        // 흐름 힘만으로는 줄 복원력을 못 이겨 잡힌 로고 뒤에 줄지어 멈춘다 — 줄 자체를 비켜 옮긴다
        if (pass === 0 && (i === w.held || j === w.held)) {
          const other = i === w.held ? b : a
          const h = i === w.held ? a : b
          other.laneY = clamp(
            other.laneY + dodgeDir(h, other, w.H) * LANE_DODGE * dt,
            other.h / 2,
            w.H - other.h / 2,
          )
        }
      }
    }
  }
}

function constrain(w: World, dt: number) {
  const { FLOW, THROW_MAX, WALL_RESTITUTION } = TUNING
  w.bodies.forEach((b, i) => {
    const held = i === w.held
    if (!held) {
      const speed = Math.hypot(b.vx, b.vy)
      if (speed > THROW_MAX) {
        b.vx *= THROW_MAX / speed
        b.vy *= THROW_MAX / speed
      }
      if (b.y < b.h / 2) {
        b.y = b.h / 2
        b.vy = Math.abs(b.vy) * WALL_RESTITUTION
      } else if (b.y > w.H - b.h / 2) {
        b.y = w.H - b.h / 2
        b.vy = -Math.abs(b.vy) * WALL_RESTITUTION
      }
      if (b.x < -WRAP_MARGIN) b.x += w.W
      else if (b.x > w.W - WRAP_MARGIN) b.x -= w.W
    }
    const calm = !held && Math.hypot(b.vx + FLOW, b.vy) <= BOB_OFF_SPEED
    b.bob += ((calm ? 1 : 0) - b.bob) * (1 - Math.exp(-dt / BOB_TAU))
  })
}

export function step(w: World, dt: number): void {
  integrate(w, dt)
  solveCollisions(w, dt)
  constrain(w, dt)
  w.t += dt
}

/** 고정 스텝으로 쪼개 돌린다. 탭을 숨겼다 돌아와도 폭주하지 않게 자른다. 돌린 스텝 수를 돌려준다 */
export function advance(w: World, elapsed: number): number {
  w.acc = Math.min(w.acc + Math.min(elapsed, 0.05), STEP * MAX_STEPS)
  let n = 0
  while (w.acc >= STEP && n < MAX_STEPS) {
    step(w, STEP)
    w.acc -= STEP
    n++
  }
  return n
}

/** 창이 넓어지면 이어지는 곳이 화면 안에 들어오지 않게 세계를 키운다. 줄이지는 않는다 */
export function ensureWidth(w: World, heroW: number): void {
  w.W = Math.max(w.W, heroW + 2 * WRAP_MARGIN)
}

/** 포인터 아래 로고 번호, 없으면 -1. 겹치면 가장 작은 로고. minX 왼쪽은 덮여 있어 잡지 않는다 */
export function hitTest(w: World, px: number, py: number, minX: number): number {
  if (px < minX) return -1
  let best = -1
  let bestArea = Infinity
  w.bodies.forEach((b, i) => {
    const gapX = Math.max(0, Math.abs(px - b.x) - b.s)
    // 세로로 긴 로고는 충돌 원이 위아래를 다 덮지 못한다 — 누르는 곳은 그림 전체여야 한다
    const gapY = Math.max(0, Math.abs(py - b.y) - Math.max(0, (b.h - b.w) / 2))
    if (Math.hypot(gapX, gapY) <= b.r && b.m < bestArea) {
      best = i
      bestArea = b.m
    }
  })
  return best
}

export function grab(w: World, i: number, px: number, py: number): void {
  const b = w.bodies[i]
  w.held = i
  w.grabDx = b.x - px
  w.grabDy = b.y - py
  w.target = { x: b.x, y: b.y }
}

/** 로고가 히어로 밖으로 나가지 않게 목표를 자른다 */
export function moveGrab(w: World, px: number, py: number, heroW: number): void {
  if (w.held < 0) return
  const b = w.bodies[w.held]
  w.target = {
    x: clamp(px + w.grabDx, b.w / 2, heroW - b.w / 2),
    y: clamp(py + w.grabDy, b.h / 2, w.H - b.h / 2),
  }
}

export function release(w: World, vx: number, vy: number): void {
  if (w.held < 0) return
  const b = w.bodies[w.held]
  const speed = Math.hypot(vx, vy)
  const k = speed > TUNING.THROW_MAX ? TUNING.THROW_MAX / speed : 1
  b.vx = vx * k
  b.vy = vy * k
  w.held = -1
  w.target = null
}

/** 최근 100ms 포인터 속도(px/s). 멈춘 뒤 놓으면 0 — 툭 놓는 것과 던지는 것을 가른다 */
export function pointerVelocity(
  samples: { t: number; x: number; y: number }[],
  now: number,
): { vx: number; vy: number } {
  const recent = samples.filter((s) => now - s.t <= VELOCITY_WINDOW_MS)
  if (recent.length < 2) return { vx: 0, vy: 0 }
  const a = recent[0]
  const b = recent[recent.length - 1]
  const dt = (b.t - a.t) / 1000
  if (dt <= 0) return { vx: 0, vy: 0 }
  return { vx: (b.x - a.x) / dt, vy: (b.y - a.y) / dt }
}

export function bodyTransform(b: Body, t: number): string {
  const wave = Math.sin((2 * Math.PI * t) / (2 * b.d) + b.phase) * b.bob
  const x = b.x - b.w / 2
  const y = b.y - b.h / 2 + TUNING.BOB_PX * wave
  const s = 1 + BOB_SCALE * wave
  return `translate3d(${x.toFixed(2)}px, ${y.toFixed(2)}px, 0) scale(${s.toFixed(4)})`
}
