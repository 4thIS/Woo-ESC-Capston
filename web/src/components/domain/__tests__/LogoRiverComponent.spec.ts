import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import LogoRiver from '../LogoRiver.vue'
import { LOGOS } from '../logoRiver'

describe('LogoRiver — 흐르기만 하는 판 (spec §5)', () => {
  const mountRiver = (k = 1, height = 720) => mount(LogoRiver, { props: { k, height } })

  it('로고마다 두 벌 — 이어 붙여 끊김 없이 돈다. alt 빈 값, 끌리지 않는다', () => {
    const imgs = mountRiver().findAll('img')
    expect(LOGOS.length).toBeGreaterThan(0)
    expect(imgs).toHaveLength(LOGOS.length * 2)
    for (const img of imgs) {
      expect(img.attributes('alt')).toBe('')
      expect(img.attributes('draggable')).toBe('false')
      expect(img.attributes('src')).toBeTruthy()
    }
  })

  it('장식 — 루트 aria-hidden, 링크·버튼 없음, 잡기 모드 아님', () => {
    const w = mountRiver()
    expect(w.attributes('aria-hidden')).toBe('true')
    expect(w.findAll('a, button')).toHaveLength(0)
    expect(w.classes()).toContain('river')
    expect(w.classes()).not.toContain('river--physics')
  })

  it.each([
    [1, 720, '4000px', '50s'],
    [0.56, 430, '2240px', '40s'],
  ])('k=%f — 트랙 폭 = 2W, 지속 시간 = W ÷ (40 × max(k, 0.7))', (k, height, width, dur) => {
    const track = mountRiver(k, height).get('.river__track').attributes('style')
    expect(track).toContain(`width: ${width}`)
    expect(track).toContain(`animation-duration: ${dur}`)
  })

  it('두 번째 벌은 첫 번째 벌에서 W 만큼 오른쪽이다', () => {
    const imgs = mountRiver().findAll('img')
    const n = LOGOS.length
    const left = (i: number) =>
      parseFloat(imgs[i].attributes('style')!.match(/left: ([-\d.]+)px/)![1])
    expect(left(n) - left(0)).toBeCloseTo(2000)
  })
})
