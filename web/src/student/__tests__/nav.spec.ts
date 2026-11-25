import { ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { mineResv } from '@/api/__fixtures__/mine'
import type { ResvMineOut } from '@/api/types'
import { clearSession, setSession } from '@/lib/session'
import StudentNav from '@/student/StudentNav.vue'
import { MINE } from '@/student/building'
import { blank } from './support'

async function mountNav(path: string, mine: ResvMineOut[] = [], tabs = true) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/:bld([A-Z])/:rest(.*)*', component: blank },
      { path: '/:rest(.*)*', component: blank },
    ],
  })
  await router.push(path)
  await router.isReady()
  const w = mount(StudentNav, {
    props: { tabs },
    global: { plugins: [router], provide: { [MINE as symbol]: { data: ref(mine) } } },
  })
  await flushPromises()
  return w
}
const links = (w: Awaited<ReturnType<typeof mountNav>>, sel: string) =>
  w.findAll(`${sel} a`).map((a) => ({
    text: a.find('.nav__name').text(),
    href: a.attributes('href'),
    current: a.attributes('aria-current'),
  }))

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-23T01:42:00Z')) // KST 금 10:42
  localStorage.clear()
  setSession({
    token: 't',
    role: 'student',
    school_id: 1,
    school_name: '명지전문대학',
    name: '이우진',
  })
})
afterEach(() => {
  vi.useRealTimers()
  clearSession()
})

describe('StudentNav — 메뉴 넷 (student-room.md 「학생 앱 메뉴」)', () => {
  it('건물 안 — 강의실 /E · 내 예약 /E/me · 이용 안내 · 내 정보, 지금 메뉴 표시, 진행 중 건수 배지', async () => {
    const w = await mountNav('/E/402', [
      mineResv({ id: 1, date: '2026-10-24', status: 'requested' }),
      mineResv({ id: 2, date: '2026-10-24', status: 'approved' }),
      mineResv({ id: 3, date: '2026-10-20', status: 'approved' }), // 끝났다
      mineResv({ id: 4, date: '2026-10-24', status: 'rejected' }),
    ])
    const expected = [
      { text: '강의실', href: '/E', current: 'page' },
      { text: '내 예약', href: '/E/me', current: undefined },
      { text: '이용 안내', href: '/guide', current: undefined },
      { text: '내 정보', href: '/account', current: undefined },
    ]
    expect(links(w, '.nav__tabs')).toEqual(expected)
    expect(links(w, '.nav__top')).toEqual(expected)
    expect(w.get('.nav__tabs .nav__badge').text()).toBe('2')
    expect(w.get('.nav__top').text()).toContain('명지전문대학')
    expect(w.get('.nav__brand img').attributes('alt')).toBe('ESC')
  })

  it('건물 밖 — 마지막 건물로, 없으면 / · /me. 건수 0 이면 배지 없음', async () => {
    let w = await mountNav('/me')
    expect(links(w, '.nav__tabs').map((l) => [l.href, l.current])).toEqual([
      ['/', undefined],
      ['/me', 'page'],
      ['/guide', undefined],
      ['/account', undefined],
    ])
    expect(w.find('.nav__badge').exists()).toBe(false)
    localStorage.setItem('esc.lastBld', 'K')
    w = await mountNav('/guide')
    expect(links(w, '.nav__tabs').map((l) => [l.href, l.current])).toEqual([
      ['/K', undefined],
      ['/K/me', undefined],
      ['/guide', 'page'],
      ['/account', undefined],
    ])
  })

  it('상세 화면(tabs=false)은 아래 탭이 없다 — 위 막대는 그대로', async () => {
    const w = await mountNav('/E/402/reserve', [], false)
    expect(w.find('.nav__tabs').exists()).toBe(false)
    expect(w.find('.nav__top').exists()).toBe(true)
  })
})
