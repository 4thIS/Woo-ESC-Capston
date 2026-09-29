import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TypeBadge from '@/components/domain/TypeBadge.vue'
import SourceBadge from '@/components/domain/SourceBadge.vue'

describe('TypeBadge', () => {
  it.each([
    [1, '수업중'],
    [2, '시험중'],
    [5, '특강'],
    [6, '대여중'],
  ] as const)('%s — 사용중은 전부 같은 busy 틴트, 구분은 라벨 %s', (type, label) => {
    const w = mount(TypeBadge, { props: { type } })
    expect(w.text()).toBe(label)
    expect(w.classes()).toEqual(expect.arrayContaining(['badge--busy', 'badge--tint']))
  })
  it.each([
    [3, '휴강'],
    [4, '빈강의실'],
  ] as const)('%s — 테두리만 (%s)', (type, label) => {
    const w = mount(TypeBadge, { props: { type } })
    expect(w.text()).toBe(label)
    expect(w.classes()).toEqual(expect.arrayContaining(['badge--neutral', 'badge--outline']))
  })
})

describe('SourceBadge', () => {
  it.each([
    [1, '포털', 'badge--neutral', 'badge--outline'],
    [2, '수동', 'badge--neutral', 'badge--solid'],
    [3, '긴급', 'badge--danger', 'badge--outline'],
  ] as const)('%s → %s (색만이 아니라 라벨로)', (source, label, tone, variant) => {
    const w = mount(SourceBadge, { props: { source } })
    expect(w.text()).toBe(label)
    expect(w.classes()).toEqual(expect.arrayContaining([tone, variant]))
  })
  it('툴팁이 CSV 와의 관계를 말한다', () => {
    expect(mount(SourceBadge, { props: { source: 1 } }).attributes('title')).toBe(
      'CSV 로 들어온 행 — 다음 CSV 가 덮는다',
    )
    expect(mount(SourceBadge, { props: { source: 2 } }).attributes('title')).toBe(
      '웹에서 고친 행 — CSV 가 덮지 않는다',
    )
  })
})
