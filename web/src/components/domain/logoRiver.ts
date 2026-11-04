// 대학 로고 강 — 크기 · 자리 · 충돌 모양 (docs/specs/2026-11-04-landing-logo-river-design.md §2, §4)
import entries from '@/assets/logos/logos.json'

export interface LogoEntry {
  slug: string
  name: string
  rank: number
  file: string
  source: string
  license: string
  aspect: number
}

/** 회전 없는 가로 캡슐. x,y 는 중심, r 은 반지름, s 는 막대 반길이(0 이면 원) */
export interface Capsule {
  x: number
  y: number
  r: number
  s: number
}

/** d · dl 은 몽글몽글 주기 · 지연(초) */
export interface RiverLogo extends Capsule {
  slug: string
  url: string
  w: number
  h: number
  d: number
  dl: number
}

export const LOGOS = entries as LogoEntry[]

const FILES = import.meta.glob('../../assets/logos/*.{svg,png}', {
  eager: true,
  query: '?url',
  import: 'default',
}) as Record<string, string>

export function logoUrl(file: string): string {
  return FILES[`../../assets/logos/${file}`] ?? ''
}

const D_MAX = 170
const D_MIN = 110
// 로고 사이 최소 틈 — 처음 자리에서 닿아 있지 않게
const LAYOUT_GAP = 12
const LAYOUT_ITER = 300

/** 면적이 같은 지름 D 를 순서로 정하고 비율을 지킨다 — 가로 로고가 혼자 커 보이지 않게 */
export function logoSize(i: number, n: number, aspect: number, k: number) {
  const d = D_MAX - (n > 1 ? i / (n - 1) : 0) * (D_MAX - D_MIN)
  const root = Math.sqrt(aspect)
  return { w: d * root * k, h: (d / root) * k }
}

// ponytail: 세로로 긴 로고는 위아래 끝이 충돌 원 밖으로 나와 살짝 겹칠 수 있다. 세로 캡슐이 필요하면 그때 더한다
export function capsuleShape(w: number, h: number) {
  return { r: Math.min(w, h) / 2, s: Math.max(0, (w - h) / 2) }
}

/** 겹치면 a → b 방향 단위 법선과 겹친 깊이. 좌우가 이어진 세계라 W 경계 너머 가까운 쪽으로 잰다 */
export function capsuleContact(a: Capsule, b: Capsule, W: number) {
  let dx = b.x - a.x
  dx -= W * Math.round(dx / W)
  const gapX = Math.max(0, Math.abs(dx) - a.s - b.s)
  const dy = b.y - a.y
  const dist = Math.hypot(gapX, dy)
  const overlap = a.r + b.r - dist
  if (overlap <= 0) return null
  if (dist < 1e-6) return { nx: 0, ny: 1, overlap }
  return { nx: (Math.sign(dx) * gapX) / dist, ny: dy / dist, overlap }
}

const frac = (v: number) => v - Math.floor(v)

/** 황금비로 흩고 겹침을 푼다. 무작위가 아니라 매번 같다 */
export function layoutLogos(
  list: LogoEntry[],
  { W, H, k }: { W: number; H: number; k: number },
): RiverLogo[] {
  const out: RiverLogo[] = list.map((e, i) => {
    const { w, h } = logoSize(i, list.length, e.aspect, k)
    return {
      ...capsuleShape(w, h),
      x: frac(i * 0.618) * W,
      y: h / 2 + frac(i * 0.382 + 0.2) * Math.max(0, H - h),
      slug: e.slug,
      url: logoUrl(e.file),
      w,
      h,
      d: 4 + (i % 5) * 0.7,
      dl: -(i * 1.3),
    }
  })
  const gap = LAYOUT_GAP * k
  for (let iter = 0; iter < LAYOUT_ITER; iter++) {
    let moved = false
    for (let i = 0; i < out.length; i++) {
      for (let j = i + 1; j < out.length; j++) {
        const a = out[i]
        const b = out[j]
        const hit = capsuleContact({ ...a, r: a.r + gap }, b, W)
        if (!hit) continue
        moved = true
        const push = hit.overlap / 2 + 0.01
        a.x -= hit.nx * push
        a.y -= hit.ny * push
        b.x += hit.nx * push
        b.y += hit.ny * push
      }
    }
    for (const l of out) {
      l.x = frac(l.x / W) * W
      l.y = Math.min(H - l.h / 2, Math.max(l.h / 2, l.y))
    }
    if (!moved) break
  }
  return out
}

/** 글자 칸 오른쪽 끝 — 가운데 1280 틀 기준(여백 80 + 글자 480). 덮개 CSS 와 숫자를 맞춘다 */
export function riverCoverEdge(heroW: number): number {
  return Math.max(0, (heroW - 1280) / 2) + 560
}
