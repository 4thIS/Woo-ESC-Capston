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
