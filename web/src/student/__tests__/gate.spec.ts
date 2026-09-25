import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import StudentApp from '@/student/StudentApp.vue'
import { clearSession, setSession } from '@/lib/session'

const Page = { render: () => h('p', '강의실 화면') }
async function mountApp(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: Page, meta: { gate: true } },
      { path: '/:bld([A-Z])', component: Page, meta: { gate: true } },
      { path: '/open', component: Page },
      { path: '/login', component: { render: () => h('p', '로그인 폼') } },
    ],
  })
  await router.push(path)
  await router.isReady()
  const w = mount(StudentApp, { global: { plugins: [router] } })
  await flushPromises()
  return { w, router }
}
afterEach(() => clearSession())

describe('로그인 벽 (student-room.md §로그인 벽)', () => {
  it('세션이 없으면 그 주소 그대로 벽 — 건물 글자, 로그인 링크는 원래 주소를 안다', async () => {
    const { w, router } = await mountApp('/E')
    expect(router.currentRoute.value.path).toBe('/E')
    expect(w.get('h1').text()).toBe('E동의 빈 강의실을 확인하고 예약을 신청할 수 있어요.')
    expect(w.get('a.cta').attributes('href')).toBe('/login?next=/E')
    expect(w.get('a[href="/signup"]').text()).toBe('가입 신청')
    expect(w.text()).not.toContain('강의실 화면')
  })

  it('건물 글자가 없는 주소는 학교 문장', async () => {
    const { w } = await mountApp('/')
    expect(w.get('h1').text()).toBe('학교의 빈 강의실을 확인하고 예약을 신청할 수 있어요.')
    expect(w.get('a.cta').attributes('href')).toBe('/login?next=/')
  })

  it('세션이 있으면 화면 그대로, gate 가 아닌 화면은 벽 없이', async () => {
    setSession({ token: 't', role: 'student', school_id: 1, name: '김민준' })
    expect((await mountApp('/E')).w.text()).toContain('강의실 화면')
    clearSession()
    expect((await mountApp('/open')).w.text()).toContain('강의실 화면')
  })
})
