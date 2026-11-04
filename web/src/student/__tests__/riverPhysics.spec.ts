import { describe, expect, it } from 'vitest'
import {
  capsuleContact,
  capsuleShape,
  layoutLogos,
  type LogoEntry,
  type RiverLogo,
} from '@/components/domain/logoRiver'
import {
  advance,
  bodyTransform,
  createWorld,
  ensureWidth,
  grab,
  hitTest,
  moveGrab,
  pointerVelocity,
  release,
  step,
  TUNING,
  WRAP_MARGIN,
  type World,
} from '@/student/views/landing/riverPhysics'

const DT = 1 / 60

function logo(x: number, y: number, w = 100, h = 100): RiverLogo {
  return { ...capsuleShape(w, h), x: x + WRAP_MARGIN, y, slug: 'u', url: '', w, h, d: 5, dl: 0 }
}
const makeWorld = (logos: RiverLogo[], W = 2000, H = 720) => createWorld(logos, W, H)
function run(w: World, seconds: number) {
  for (let i = 0; i < Math.round(seconds / DT); i++) step(w, DT)
}

describe('흐름 · 잇기', () => {
  it('아무도 안 건드리면 모두 vx ≈ -40, 1초에 약 40px 왼쪽', () => {
    const w = makeWorld([logo(900, 300), logo(300, 500)])
    const x0 = w.bodies[0].x
    run(w, 1)
    expect(w.bodies[0].vx).toBeCloseTo(-TUNING.FLOW)
    expect(x0 - w.bodies[0].x).toBeCloseTo(40, 0)
  })

  it('왼쪽 -WRAP_MARGIN 을 지나면 W 만큼 오른쪽으로, 오른쪽으로 던져 넘어가면 반대로', () => {
    const w = makeWorld([logo(-WRAP_MARGIN + 1, 300)])
    run(w, 0.1)
    expect(w.bodies[0].x).toBeGreaterThan(2000 - WRAP_MARGIN - 10)
    grab(w, 0, w.bodies[0].x, 300)
    release(w, 900, 0)
    run(w, 0.5)
    expect(w.bodies[0].x).toBeLessThan(2000 - WRAP_MARGIN)
  })

  it('advance — 3600초를 넘겨도 최대 3스텝, 위치가 튀지 않는다', () => {
    const w = makeWorld([logo(900, 300)])
    const x0 = w.bodies[0].x
    expect(advance(w, 3600)).toBeLessThanOrEqual(3)
    expect(Math.abs(x0 - w.bodies[0].x)).toBeLessThan(5)
  })

  it('advance — 60 Hz 보다 짧은 프레임은 쌓아 두었다 한 스텝 돈다', () => {
    const w = makeWorld([logo(900, 300)])
    expect(advance(w, DT / 2)).toBe(0)
    expect(advance(w, DT / 2 + 1e-6)).toBe(1)
  })

  it('ensureWidth — 넓힐 때만 W 를 키운다', () => {
    const w = makeWorld([logo(900, 300)])
    ensureWidth(w, 1280)
    expect(w.W).toBe(2000)
    ensureWidth(w, 2560)
    expect(w.W).toBe(2960)
    ensureWidth(w, 1280)
    expect(w.W).toBe(2960)
  })
})

describe('던지기 · 충돌', () => {
  it('throw — release(900,0) 뒤 5초 안에 vx 가 -40 ±2, 이동 거리 720px 이하', () => {
    const w = makeWorld([logo(0, 300)])
    grab(w, 0, 0, 300)
    release(w, 900, 0)
    const x0 = w.bodies[0].x
    let far = 0
    for (let i = 0; i < 300; i++) {
      step(w, DT)
      far = Math.max(far, w.bodies[0].x - x0)
    }
    expect(Math.abs(w.bodies[0].vx + TUNING.FLOW)).toBeLessThanOrEqual(2)
    expect(far).toBeGreaterThan(300)
    expect(far).toBeLessThanOrEqual(720)
  })

  it('release — 크기 5000 을 넣어도 속도 크기 900', () => {
    const w = makeWorld([logo(0, 300)])
    grab(w, 0, 0, 300)
    release(w, 3000, 4000)
    expect(Math.hypot(w.bodies[0].vx, w.bodies[0].vy)).toBeCloseTo(TUNING.THROW_MAX)
  })

  it('collision — 던진 로고가 흐르는 로고에 닿으면 상대가 밀리고 겹침이 2px 이하', () => {
    const w = makeWorld([logo(0, 300), logo(300, 300)])
    grab(w, 0, 0, 300)
    release(w, 800, 0)
    let hit = false
    for (let i = 0; i < 120; i++) {
      step(w, DT)
      hit ||= w.bodies[1].vx > 0
      const c = capsuleContact(w.bodies[0], w.bodies[1], w.W)
      expect(c?.overlap ?? 0).toBeLessThanOrEqual(2)
    }
    expect(hit).toBe(true)
  })

  it('collision — 작은 로고가 큰 로고보다 더 많이 밀린다(질량 ∝ 면적)', () => {
    const w = makeWorld([logo(500, 300, 200, 200), logo(620, 300, 80, 80)])
    const big0 = w.bodies[0].x
    const small0 = w.bodies[1].x
    step(w, DT)
    // 흐름으로 움직인 몫을 빼고 충돌로 밀린 거리만 비교한다
    const flow = TUNING.FLOW * DT
    const small = Math.abs(w.bodies[1].x - small0 + flow)
    const big = Math.abs(w.bodies[0].x - big0 + flow)
    expect(small).toBeGreaterThan(big * 3)
    expect(small + big).toBeCloseTo(20, 0)
  })

  it('wall — 위로 던져도 로고가 벽 안쪽에 있고, 튕겨 내려온다', () => {
    const w = makeWorld([logo(500, 200)])
    grab(w, 0, 500, 200)
    release(w, 0, -900)
    let bounced = false
    for (let i = 0; i < 120; i++) {
      step(w, DT)
      expect(w.bodies[0].y).toBeGreaterThanOrEqual(w.bodies[0].h / 2)
      bounced ||= w.bodies[0].vy > 0
    }
    expect(bounced).toBe(true)
  })

  it('가로 로고 둘도 옆으로 닿아 튕긴다', () => {
    const w = makeWorld([logo(0, 300, 300, 80), logo(500, 300, 300, 80)])
    grab(w, 0, 0, 300)
    release(w, 800, 0)
    run(w, 1)
    expect(w.bodies[1].x).toBeGreaterThan(500 + WRAP_MARGIN - WRAP_MARGIN)
  })
})

describe('잡기', () => {
  it('held — 잡힌 로고는 충돌로 밀리지 않고 0.3초 안에 목표에 2px 이내', () => {
    const w = makeWorld([logo(500, 300), logo(560, 300)])
    grab(w, 0, 500, 300)
    moveGrab(w, 700, 400, 1280)
    run(w, 0.3)
    expect(Math.abs(w.bodies[0].x - 700)).toBeLessThanOrEqual(2)
    expect(Math.abs(w.bodies[0].y - 400)).toBeLessThanOrEqual(2)
  })

  it('held — 누른 지점을 유지한다(로고 중심으로 튀지 않는다)', () => {
    const w = makeWorld([logo(500, 300)])
    grab(w, 0, 520, 310)
    moveGrab(w, 620, 310, 1280)
    run(w, 0.5)
    expect(w.bodies[0].x).toBeCloseTo(600, 0)
    expect(w.bodies[0].y).toBeCloseTo(300, 0)
  })

  it('held — 목표가 히어로 밖이면 히어로 안에 머문다', () => {
    const w = makeWorld([logo(500, 300)])
    grab(w, 0, 500, 300)
    moveGrab(w, -500, 5000, 1280)
    run(w, 0.5)
    expect(w.bodies[0].x).toBeCloseTo(50, 0)
    expect(w.bodies[0].y).toBeCloseTo(720 - 50, 0)
    moveGrab(w, 5000, -500, 1280)
    run(w, 0.5)
    expect(w.bodies[0].x).toBeCloseTo(1230, 0)
    expect(w.bodies[0].y).toBeCloseTo(50, 0)
  })

  it('dodge — 잡힌 로고와 y 가 같은 뒤 로고가 12초 안에 왼쪽으로 완전히 지나간다', () => {
    const w = makeWorld([logo(600, 360), logo(800, 360)])
    grab(w, 0, 600, 360)
    run(w, 12)
    expect(w.bodies[1].x).toBeLessThan(w.bodies[0].x - 100)
  })

  it('dodge — 잡힌 로고가 위 벽 근처면 아래로 비켜 간다', () => {
    const w = makeWorld([logo(600, 60), logo(800, 50)])
    grab(w, 0, 600, 60)
    run(w, 12)
    expect(w.bodies[1].x).toBeLessThan(w.bodies[0].x - 100)
  })

  it('dodge — 지나간 뒤 laneY 가 homeY 로 돌아온다(30초 뒤 5px 이내)', () => {
    const w = makeWorld([logo(600, 360), logo(800, 360)])
    grab(w, 0, 600, 360)
    run(w, 10)
    expect(Math.abs(w.bodies[1].laneY - 360)).toBeGreaterThan(20)
    release(w, 0, 0)
    run(w, 30)
    expect(Math.abs(w.bodies[1].laneY - 360)).toBeLessThanOrEqual(5)
  })

  it('놓으면 잡힘이 풀리고 다시 흐른다', () => {
    const w = makeWorld([logo(600, 360)])
    grab(w, 0, 600, 360)
    run(w, 1)
    expect(w.bodies[0].x).toBeCloseTo(600, 0)
    release(w, 0, 0)
    expect(w.held).toBe(-1)
    run(w, 5)
    expect(w.bodies[0].vx).toBeCloseTo(-TUNING.FLOW, 0)
  })
})

describe('hitTest', () => {
  const w = makeWorld([logo(500, 300, 300, 100), logo(500, 300, 60, 60)])
  w.bodies[0].y = 300

  it('캡슐 끝 둥근 부분 밖은 -1, 막대 위는 잡힌다', () => {
    const only = makeWorld([logo(500, 300, 300, 100)])
    expect(hitTest(only, 620, 340, 0)).toBe(0)
    // 상자 모서리: 캡슐의 둥근 끝 바깥
    expect(hitTest(only, 648, 348, 0)).toBe(-1)
    expect(hitTest(only, 500, 360, 0)).toBe(-1)
  })

  it('세로로 긴 로고는 위아래 끝까지 잡힌다', () => {
    const tall = makeWorld([logo(500, 300, 60, 200)])
    expect(hitTest(tall, 500, 390, 0)).toBe(0)
  })

  it('minX 왼쪽은 -1', () => {
    expect(hitTest(w, 500, 300, 600)).toBe(-1)
  })

  it('겹치면 작은 쪽', () => {
    expect(hitTest(w, 500, 300, 0)).toBe(1)
  })
})

describe('pointerVelocity', () => {
  it('최근 100ms 평균 — 오래된 표본은 보지 않는다', () => {
    const v = pointerVelocity(
      [
        { t: 0, x: 9999, y: 0 },
        { t: 900, x: 0, y: 0 },
        { t: 1000, x: 100, y: -50 },
      ],
      1000,
    )
    expect(v.vx).toBeCloseTo(1000)
    expect(v.vy).toBeCloseTo(-500)
  })

  it('멈춘 뒤 놓으면 0 — 마지막 표본이 100ms 넘게 오래됨', () => {
    const s = [
      { t: 0, x: 0, y: 0 },
      { t: 50, x: 500, y: 0 },
    ]
    expect(pointerVelocity(s, 300)).toEqual({ vx: 0, vy: 0 })
  })

  it('표본 하나면 0', () => {
    expect(pointerVelocity([{ t: 10, x: 5, y: 5 }], 20)).toEqual({ vx: 0, vy: 0 })
  })
})

describe('bodyTransform — 몽글몽글', () => {
  it('좌상단 기준 translate3d + scale', () => {
    const w = makeWorld([logo(500, 300, 100, 100)])
    w.bodies[0].bob = 0
    expect(bodyTransform(w.bodies[0], 0)).toBe('translate3d(450.00px, 250.00px, 0) scale(1.0000)')
  })

  it('잡히면 bob 이 0 으로 줄고, 흐름을 되찾으면 돌아온다', () => {
    const w = makeWorld([logo(500, 300)])
    grab(w, 0, 500, 300)
    run(w, 3)
    expect(w.bodies[0].bob).toBeLessThan(0.02)
    release(w, 0, 0)
    run(w, 6)
    expect(w.bodies[0].bob).toBeGreaterThan(0.9)
  })

  it('bob 이 1 이면 시간에 따라 위아래로 움직인다(폭 BOB_PX)', () => {
    const w = makeWorld([logo(500, 300)])
    const ys = Array.from({ length: 40 }, (_, i) => {
      const m = /, ([\d.]+)px, 0/.exec(bodyTransform(w.bodies[0], i * 0.5))!
      return Number(m[1])
    })
    expect(Math.max(...ys) - Math.min(...ys)).toBeGreaterThan(TUNING.BOB_PX)
    expect(Math.max(...ys) - Math.min(...ys)).toBeLessThanOrEqual(TUNING.BOB_PX * 2 + 0.01)
  })
})

describe('오래 켜 둠', () => {
  it('1시간 — 시드 고정 던지기를 섞어 돌려도 NaN 없음, 한쪽에 몰리지 않음, 겹쳐 굳지 않음', () => {
    const entries: LogoEntry[] = Array.from({ length: 20 }, (_, i) => ({
      slug: `u${i}`,
      name: '',
      rank: i,
      file: '',
      source: '',
      license: '',
      aspect: [1, 3.9, 1.4, 2.6, 0.7][i % 5],
    }))
    const W = 2000
    const w = createWorld(layoutLogos(entries, { W, H: 720, k: 1 }), W, 720)
    let seed = 12345
    const rnd = () => (seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296
    let drift = 0
    let overlap = 0
    let samples = 0
    let holdLeft = 0
    for (let n = 0; n < 3600 * 60; n++) {
      if (holdLeft > 0 && --holdLeft === 0) release(w, (rnd() - 0.5) * 1800, (rnd() - 0.5) * 1800)
      if (w.held < 0 && n % 1200 === 0) {
        const i = Math.floor(rnd() * 20)
        grab(w, i, w.bodies[i].x, w.bodies[i].y)
        moveGrab(w, 200 + rnd() * 900, 100 + rnd() * 500, 1280)
        holdLeft = Math.floor(rnd() * 180) + 1
      }
      step(w, DT)
      if (n % 600 === 0) {
        for (let i = 0; i < 20; i++) {
          const b = w.bodies[i]
          expect(Number.isFinite(b.x + b.y + b.vx + b.vy)).toBe(true)
          drift += Math.abs(b.y - b.homeY)
          samples++
          for (let j = i + 1; j < 20; j++) {
            overlap += capsuleContact(b, w.bodies[j], W)?.overlap ?? 0
          }
        }
      }
    }
    expect(drift / samples).toBeLessThan(120)
    expect(overlap / samples).toBeLessThan(2)
  })
})
