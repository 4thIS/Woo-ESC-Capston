import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import AdminApp from '@/admin/AdminApp.vue'
import { makeRouter } from '@/admin/router'
import { usersApi } from '@/api/users'
import type { UserOut } from '@/api/types'
import { clearSession, session, setSession } from '@/lib/session'

vi.mock('@/api/users', () => ({ usersApi: { list: vi.fn() } }))
vi.mock('@/api/rooms', () => ({
  roomsApi: { schools: vi.fn(async () => [{ id: 1, name: '우송대', net_id: 75 }]) },
}))
const list = vi.mocked(usersApi.list)
// 회원 화면(Task 13)이 /users 에서 실제로 그린다 — 정렬에 쓰는 필드까지 채운다
const user = (email: string): UserOut => ({
  email,
  school_id: 1,
  role: 'student',
  status: 'pending_approval',
  name: email,
  student_no: null,
  created_at: new Date(),
  approved_at: null,
})

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
  vi.stubGlobal(
    'fetch',
    vi.fn(() => new Promise<Response>(() => {})),
  )
  localStorage.clear()
  list.mockReset().mockResolvedValue([user('a'), user('b')])
  setSession({ token: 't', role: 'admin', school_id: 1, name: '관리자1' })
  mockWidth(false)
})

describe('AdminShell', () => {
  it('/ 는 /dashboard 로, 메뉴 순서(#46) · 전송 현황 활성 · 회원 대기 건수 · 학교 읽기 전용', async () => {
    const { w, router } = await mountApp('/')
    expect(router.currentRoute.value.path).toBe('/dashboard')
    expect(list).toHaveBeenCalledWith('pending_approval')
    const links = w.findAll('nav a')
    expect(links.map((a) => a.text().replace(/\d+/g, '').trim())).toEqual([
      '건물 · 강의실',
      '강의실 설정',
      '주간 시간표',
      '노드 상태',
      '전송 현황',
      '회원',
    ])
    expect(links[2].attributes('href')).toBe('/week')
    expect(links[4].attributes('aria-current')).toBe('page')
    expect(links[5].text()).toContain('2')
    expect(w.text()).toContain('우송대 · net_id 75')
    expect(w.text()).toContain('학교는 CLI 에서만 만든다')
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
    expect(session.value).toBeNull()
    // /login 은 지연 로드라 첫 이동은 dynamic import 만큼 걸린다 — 이동이 끝날 때까지 기다린다
    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe('/login'))
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
