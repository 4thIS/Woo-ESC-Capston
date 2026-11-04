import { describe, expect, it } from 'vitest'
import {
  capsuleContact,
  capsuleShape,
  layoutLogos,
  logoSize,
  riverCoverEdge,
  type LogoEntry,
} from '../logoRiver'

const entries = (n: number, aspect = 1): LogoEntry[] =>
  Array.from({ length: n }, (_, i) => ({
    slug: `u${i}`,
    name: `대학${i}`,
    rank: i + 1,
    file: `u${i}.svg`,
    source: 'https://example.org',
    license: 'test',
    // 실제 목록처럼 원형과 가로 글자 로고가 섞인다
    aspect: aspect === 1 ? [1, 3.9, 1.4, 2.6, 0.7][i % 5] : aspect,
  }))

describe('logoSize — 면적이 같은 지름 D 로 크기를 정한다 (spec §2)', () => {
  it('첫째 D 170, 마지막 D 110, w×h = D², w/h = aspect', () => {
    const first = logoSize(0, 20, 1, 1)
    expect(first.w).toBeCloseTo(170)
    expect(first.h).toBeCloseTo(170)
    const last = logoSize(19, 20, 4, 1)
    expect(last.w * last.h).toBeCloseTo(110 * 110)
    expect(last.w / last.h).toBeCloseTo(4)
  })

  it('n=1 이어도 D 170 (0으로 나누지 않는다)', () => {
    expect(logoSize(0, 1, 1, 1).w).toBeCloseTo(170)
  })

  it('k 배율이 w,h 에 곱해진다', () => {
    expect(logoSize(0, 20, 1, 0.5).w).toBeCloseTo(85)
  })
})

describe('capsuleShape', () => {
  it('가로 로고는 r = h/2, s = (w-h)/2. 세로 로고는 r = w/2, s = 0', () => {
    expect(capsuleShape(300, 100)).toEqual({ r: 50, s: 100 })
    expect(capsuleShape(100, 300)).toEqual({ r: 50, s: 0 })
  })
})

describe('capsuleContact — 회전 없는 가로 캡슐', () => {
  const W = 2000
  const c = (x: number, y: number, r: number, s = 0) => ({ x, y, r, s })

  it('원 둘: 떨어지면 null, 겹치면 overlap = r합 - 거리, 단위 법선', () => {
    expect(capsuleContact(c(0, 0, 10), c(30, 0, 10), W)).toBeNull()
    // 거리 20 = r합 — 닿기만 한 것은 겹침이 아니다
    expect(capsuleContact(c(0, 0, 10), c(12, 16, 10), W)).toBeNull()
    const inner = capsuleContact(c(0, 0, 15), c(12, 16, 10), W)!
    expect(inner.overlap).toBeCloseTo(5)
    expect(inner.nx).toBeCloseTo(0.6)
    expect(inner.ny).toBeCloseTo(0.8)
  })

  it('가로 캡슐 둘이 옆으로 닿고 위아래로 지나갈 수 있다', () => {
    const side = capsuleContact(c(0, 0, 20, 100), c(235, 0, 20, 100), W)!
    expect(side.nx).toBeCloseTo(1)
    expect(side.overlap).toBeCloseTo(5)
    // 막대 구간끼리 위아래: 법선은 세로
    const over = capsuleContact(c(0, 0, 20, 100), c(30, 35, 20, 100), W)!
    expect(over.nx).toBeCloseTo(0)
    expect(over.ny).toBeCloseTo(1)
    expect(over.overlap).toBeCloseTo(5)
    expect(capsuleContact(c(0, 0, 20, 100), c(30, 45, 20, 100), W)).toBeNull()
  })

  it('W 경계를 넘어 가장 짧은 쪽으로 잰다 (x=10 과 x=W-10 은 거리 20)', () => {
    const hit = capsuleContact(c(10, 0, 15), c(W - 10, 0, 15), W)!
    expect(hit.overlap).toBeCloseTo(10)
    expect(hit.nx).toBeCloseTo(-1)
  })

  it('완전히 같은 자리여도 NaN 이 아니고 법선 길이 1', () => {
    const hit = capsuleContact(c(5, 5, 10), c(5, 5, 10), W)!
    expect(Math.hypot(hit.nx, hit.ny)).toBeCloseTo(1)
    expect(hit.overlap).toBeCloseTo(20)
  })
})

describe('layoutLogos', () => {
  it.each([
    [2000, 720, 1],
    [1440, 470, 0.72],
    [1120, 300, 0.56],
    [600, 150, 0.3],
  ])('W=%i H=%i k=%f — 로고 20개가 경계 포함 겹치지 않고 위아래 안에 있다', (W, H, k) => {
    const out = layoutLogos(entries(20), { W, H, k })
    expect(out).toHaveLength(20)
    for (let i = 0; i < out.length; i++) {
      expect(out[i].y - out[i].h / 2, out[i].slug).toBeGreaterThanOrEqual(-0.5)
      expect(out[i].y + out[i].h / 2, out[i].slug).toBeLessThanOrEqual(H + 0.5)
      for (let j = i + 1; j < out.length; j++) {
        const hit = capsuleContact(out[i], out[j], W)
        expect(hit?.overlap ?? 0, `${out[i].slug}-${out[j].slug}`).toBeLessThan(0.5)
      }
    }
  })

  it('두 번 불러도 결과가 같다', () => {
    const o = { W: 2000, H: 720, k: 1 }
    expect(layoutLogos(entries(20), o)).toEqual(layoutLogos(entries(20), o))
  })

  it('크기 순서가 왼쪽부터 줄지어 있지 않다', () => {
    const xs = layoutLogos(entries(20), { W: 2000, H: 720, k: 1 })
      .slice(0, 5)
      .map((l) => l.x)
    expect(xs).not.toEqual([...xs].sort((a, b) => a - b))
  })

  it('빈 목록이면 빈 배열', () => {
    expect(layoutLogos([], { W: 2000, H: 720, k: 1 })).toEqual([])
  })
})

describe('riverCoverEdge — 글자 칸 오른쪽 끝, 가운데 틀 기준', () => {
  it('1280 폭 560, 2560 폭 1200', () => {
    expect(riverCoverEdge(1280)).toBe(560)
    expect(riverCoverEdge(2560)).toBe(1200)
  })
})
