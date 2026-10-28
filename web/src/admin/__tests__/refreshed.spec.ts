import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import LastRefreshed from '@/admin/LastRefreshed.vue'

afterEach(() => vi.useRealTimers())

describe('LastRefreshed', () => {
  it('시각이 없으면 그리지 않고, 5분 넘으면 danger 문구, 새로 받으면 풀린다', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
    vi.setSystemTime(new Date('2026-09-25T01:00:00Z'))
    const w = mount(LastRefreshed, { props: { at: null } })
    expect(w.find('.refreshed').exists()).toBe(false)
    await w.setProps({ at: new Date('2026-09-25T00:55:00Z') }) // KST 09:55, 5분 전
    expect(w.get('.refreshed').text()).toBe('마지막 갱신 09:55 · 갱신이 멈췄습니다')
    expect(w.get('.refreshed').classes()).toContain('refreshed--stale')
    expect(w.get('.refreshed').attributes('title')).toBe('2026-09-25 09:55')
    await w.setProps({ at: new Date('2026-09-25T00:59:30Z') })
    expect(w.get('.refreshed').text()).toBe('마지막 갱신 09:59')
    expect(w.get('.refreshed').classes()).not.toContain('refreshed--stale')
    w.unmount()
  })
})
