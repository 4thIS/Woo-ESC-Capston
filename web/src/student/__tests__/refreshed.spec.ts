import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import RefreshedNote from '@/student/RefreshedNote.vue'

afterEach(() => vi.useRealTimers())

describe('RefreshedNote — 문 앞 e-Paper 와 같은 내용 · 갱신 시각', () => {
  it('갱신 시각과 e-Paper 문구, 5분이 지나면 danger + 문장 (색만으로 말하지 않는다)', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-23T01:42:00Z'))
    const w = mount(RefreshedNote, { props: { at: new Date('2026-10-23T01:41:00Z') } })
    expect(w.attributes('role')).toBe('status')
    expect(w.text()).toContain('문 앞 e-Paper 와 같은 내용')
    expect(w.text()).toContain('10:41 갱신')
    expect(w.classes()).not.toContain('rn--stale')
    vi.advanceTimersByTime(5 * 60_000)
    await nextTick()
    expect(w.classes()).toContain('rn--stale')
    expect(w.text()).toContain('갱신이 멈췄어요')
  })

  it('epaper=false 면 갱신 시각만 (/me), 아직 한 번도 못 받았으면 시각 없음', () => {
    const me = mount(RefreshedNote, {
      props: { at: new Date('2026-10-23T01:41:00Z'), epaper: false },
    })
    expect(me.text()).not.toContain('e-Paper')
    expect(me.text()).toContain('10:41 갱신')
    const none = mount(RefreshedNote, { props: { at: null } })
    expect(none.text()).not.toContain('갱신')
  })
})
