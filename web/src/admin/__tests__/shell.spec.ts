import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import AdminApp from '@/admin/AdminApp.vue'
import { makeRouter } from '@/admin/router'
import { usersApi } from '@/api/users'
import { clearSession, session, setSession } from '@/lib/session'

vi.mock('@/api/users', () => ({ usersApi: { list: vi.fn() } }))
const list = vi.mocked(usersApi.list)
const user = (email: string) => ({ email }) as never

function mockWidth(narrow: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({ matches: narrow, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
  )
}
async function mountApp(path = '/users') {
  const router = makeRouter(createMemoryHistory())
  await router.push(path)
  await router.isReady()
  const w = mount(AdminApp, { global: { plugins: [router] } })
  await flushPromises()
  return { w, router }
}

beforeEach(() => {
  localStorage.clear()
  list.mockReset().mockResolvedValue([user('a'), user('b')])
  setSession({ token: 't', role: 'admin', school_id: 1, name: '관리자1' })
  mockWidth(false)
})

describe('AdminShell', () => {
  it('/ 는 /users 로, 회원 메뉴가 활성이고 대기 건수 배지', async () => {
    const { w, router } = await mountApp('/')
    expect(router.currentRoute.value.path).toBe('/users')
    expect(list).toHaveBeenCalledWith('pending_approval')
    const link = w.get('nav a')
    expect(link.text()).toContain('회원')
    expect(link.text()).toContain('2')
    expect(link.attributes('aria-current')).toBe('page')
    expect(w.text()).toContain('관리자1')
  })

  it('1024px 미만이면 안내 Banner, 닫으면 다시 안 뜬다', async () => {
    mockWidth(true)
    const a = await mountApp()
    expect(a.w.text()).toContain('관리자 화면은 1024px 이상에서 쓰도록 만들어졌습니다')
    await a.w.get('.banner button').trigger('click')
    a.w.unmount()
    const b = await mountApp()
    expect(b.w.find('.banner').exists()).toBe(false)
  })

  it('넓으면 Banner 없음', async () => {
    const { w } = await mountApp()
    expect(w.find('.banner').exists()).toBe(false)
  })

  it('로그아웃 → 세션을 버리고 로그인으로', async () => {
    const { w, router } = await mountApp()
    await w.get('button.shell__logout').trigger('click')
    await flushPromises()
    expect(session.value).toBeNull()
    expect(router.currentRoute.value.path).toBe('/login')
  })
})

describe('guard', () => {
  it('세션 없이 /users → /login?next=/users', async () => {
    clearSession()
    const router = makeRouter(createMemoryHistory())
    await router.push('/users')
    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.next).toBe('/users')
  })
})
