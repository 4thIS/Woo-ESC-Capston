import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { safeNext } from '@/auth/next'
import { installAuth } from '@/auth/guard'
import LoginView from '@/auth/LoginView.vue'
import { ApiError, MESSAGES } from '@/api/client'
import { authNotice, clearSession, session, setSession } from '@/lib/session'
import { authApi } from '@/api/auth'

vi.mock('@/api/auth', () => ({ authApi: { login: vi.fn() } }))
const login = vi.mocked(authApi.login)
const Empty = { template: '<div />' }

function makeRouter(): Router {
  const r = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: Empty, meta: { auth: true } },
      { path: '/users', component: Empty, meta: { auth: true } },
      { path: '/login', component: Empty },
      { path: '/signup', component: Empty },
      { path: '/forgot', component: Empty },
    ],
  })
  installAuth(r)
  return r
}
async function mountLogin(app: 'admin' | 'student', path = '/login') {
  const router = makeRouter()
  await router.push(path)
  await router.isReady()
  const w = mount(LoginView, { props: { app }, global: { plugins: [router] } })
  return { w, router }
}
async function submit(w: ReturnType<typeof mount>, email = 'a@wsu.ac.kr', pw = 'password1') {
  const [e, p] = w.findAll('input')
  await e.setValue(email)
  await p.setValue(pw)
  await w.get('form').trigger('submit')
  await flushPromises()
}
const out = (role: 'admin' | 'student') => ({ token: 't', role, school_id: 1, name: '김민준' })

beforeEach(() => {
  login.mockReset()
  clearSession()
  authNotice.value = null
})
afterEach(() => vi.useRealTimers())

describe('safeNext (Review Focus 1)', () => {
  it.each([
    ['/users?status=active', '/users?status=active'],
    ['//evil.com', '/'],
    ['/\\evil.com', '/'],
    ['https://evil.com', '/'],
    [undefined, '/'],
    [['/a'], '/'],
  ])('%s → %s', (v, want) => expect(safeNext(v, '/')).toBe(want))
})

describe('installAuth', () => {
  it('세션 없이 auth 라우트 → /login?next=', async () => {
    const r = makeRouter()
    await r.push('/users?x=1')
    expect(r.currentRoute.value.path).toBe('/login')
    expect(r.currentRoute.value.query.next).toBe('/users?x=1')
  })

  it('401 알림이 오면 지금 화면을 next 로 로그인에 보낸다', async () => {
    const r = makeRouter()
    setSession(out('admin'))
    await r.push('/users')
    clearSession('expired')
    await flushPromises()
    expect(r.currentRoute.value.path).toBe('/login')
    expect(r.currentRoute.value.query.next).toBe('/users')
  })
})

describe('LoginView', () => {
  it('성공 → 세션 저장 + next 로', async () => {
    login.mockResolvedValue(out('admin'))
    const { w, router } = await mountLogin('admin', '/login?next=/users')
    await submit(w)
    expect(session.value?.role).toBe('admin')
    expect(router.currentRoute.value.path).toBe('/users')
  })

  it('역할이 앱과 다르면 토큰을 버리고 폼에 머문다', async () => {
    login.mockResolvedValue(out('student'))
    const { w, router } = await mountLogin('admin')
    await submit(w)
    expect(session.value).toBeNull()
    expect(router.currentRoute.value.path).toBe('/login')
    expect(w.text()).toContain('관리자 계정이 아닙니다. 학생은 학생 웹에서 로그인하세요.')
  })

  it('학생 앱에 관리자 계정', async () => {
    login.mockResolvedValue(out('admin'))
    const { w } = await mountLogin('student')
    await submit(w)
    expect(w.text()).toContain('관리자 계정입니다. 관리자 웹에서 로그인하세요.')
  })

  it('401 → 어느 쪽이 틀렸는지 말하지 않는다', async () => {
    login.mockRejectedValue(new ApiError(401, MESSAGES[401]))
    const { w } = await mountLogin('student')
    await submit(w)
    expect(w.get('.auth-form__error').text()).toBe('이메일 또는 비밀번호가 틀립니다')
  })

  it('403 → 적색이 아닌 안내 Banner', async () => {
    login.mockRejectedValue(new ApiError(403, MESSAGES[403]))
    const { w } = await mountLogin('student')
    await submit(w)
    const b = w.get('.banner')
    expect(b.classes()).toContain('banner--neutral')
    expect(b.text()).toContain('아직 승인되지 않았어요. 관리자 승인 뒤 로그인할 수 있어요.')
    expect(w.find('.auth-form__error').exists()).toBe(false)
  })

  it('429 → 문구 + 버튼 10초 잠금 (Review Focus 5)', async () => {
    vi.useFakeTimers()
    login.mockRejectedValue(new ApiError(429, MESSAGES[429]))
    const { w } = await mountLogin('student')
    await submit(w)
    const btn = () => w.get('button[type="submit"]').element as HTMLButtonElement
    expect(w.text()).toContain('잠시 후 다시 시도해 주세요')
    expect(btn().disabled).toBe(true)
    await vi.advanceTimersByTimeAsync(10_000)
    expect(btn().disabled).toBe(false)
    vi.useRealTimers()
  })

  it('422 → 이메일 칸 에러', async () => {
    login.mockRejectedValue(new ApiError(422, MESSAGES[422], ['email']))
    const { w } = await mountLogin('student')
    await submit(w, 'a,b@x')
    expect(w.text()).toContain('메일 주소 형식이 올바르지 않습니다')
  })

  it('401 로 쫓겨 왔으면 "다시 로그인해 주세요." Banner', async () => {
    authNotice.value = 'expired'
    const { w } = await mountLogin('admin')
    expect(w.get('.banner').text()).toContain('다시 로그인해 주세요.')
  })

  it('제출 중 연타는 한 번만 보낸다', async () => {
    let finish!: (v: ReturnType<typeof out>) => void
    login.mockReturnValue(new Promise((r) => (finish = r)))
    const { w } = await mountLogin('student')
    const [e, p] = w.findAll('input')
    await e.setValue('a@wsu.ac.kr')
    await p.setValue('password1')
    await w.get('form').trigger('submit')
    await w.get('form').trigger('submit')
    expect(login).toHaveBeenCalledTimes(1)
    finish(out('student'))
    await flushPromises()
  })

  it('관리자 앱에는 가입 링크가 없고 재설정은 학생 앱 /forgot 으로', async () => {
    const { w } = await mountLogin('admin')
    expect(w.text()).not.toContain('가입 신청')
    expect(w.get('a[href="/forgot"]').text()).toBe('비밀번호를 잊었어요')
  })
})
