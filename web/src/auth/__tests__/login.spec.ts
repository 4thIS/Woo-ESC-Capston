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
async function submit(w: ReturnType<typeof mount>, email = 'a@mjc.ac.kr', pw = 'password1') {
  const [e, p] = w.findAll('form input') // 탭(라디오)이 아니라 폼의 입력칸
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
    // 문구가 바로 위의 탭을 가리킨다 (auth.md 「역할 확인」, #87)
    expect(w.text()).toContain("학생 계정입니다. 위의 '학생'을 골라 로그인하세요.")
  })

  it('학생 앱에 관리자 계정', async () => {
    login.mockResolvedValue(out('admin'))
    const { w } = await mountLogin('student')
    await submit(w)
    expect(w.text()).toContain("관리자 계정입니다. 위의 '관리자'를 골라 로그인하세요.")
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
    const [e, p] = w.findAll('form input') // 탭(라디오)이 아니라 폼의 입력칸
    await e.setValue('a@mjc.ac.kr')
    await p.setValue('password1')
    await w.get('form').trigger('submit')
    await w.get('form').trigger('submit')
    expect(login).toHaveBeenCalledTimes(1)
    finish(out('student'))
    await flushPromises()
  })

  it('관리자 탭에는 하단 링크가 없다 — 가입은 CLI 뿐, 비밀번호 찾기도 두지 않는다(2026-10-28 결정). 자리는 남긴다', async () => {
    const { w } = await mountLogin('admin')
    expect(w.text()).not.toContain('가입 신청')
    expect(w.text()).not.toContain('비밀번호를 잊었어요')
    // 넓은 폭은 폼을 세로 가운데에 둔다 — 하단 줄이 없어지면 탭을 바꿀 때 폼이 위아래로 움직인다
    expect(w.find('.auth__footer').exists()).toBe(true)
  })

  it.each([
    ['student', '학생'],
    ['admin', '관리자'],
  ] as const)(
    '%s 앱 — 학생|관리자 탭은 같은 화면에서 바뀐다(주소 그대로), 그 앱 탭이 먼저 선택',
    async (app, on) => {
      const { w, router } = await mountLogin(app, '/login?next=/users')
      const group = w.get('[role="radiogroup"][aria-label="로그인 역할"]')
      const checked = () =>
        group.findAll('input').map((r) => (r.element as HTMLInputElement).checked)
      expect(group.find('label.seg__item--on').text()).toBe(on)
      const other = app === 'student' ? 1 : 0
      await group.findAll('input')[other].setValue(true)
      expect(checked()).toEqual(app === 'student' ? [false, true] : [true, false])
      expect(router.currentRoute.value.fullPath).toBe('/login?next=/users') // 새 주소로 가지 않는다
      // 탭에 따라 입력 이름과 하단 링크가 바뀐다
      const adminTab = app === 'student'
      expect(w.get('form label').text()).toContain(adminTab ? '이메일' : '학교 웹메일')
      expect(w.text().includes('가입 신청')).toBe(!adminTab)
    },
  )

  it('학생 앱에서 관리자 탭으로 로그인 — 관리자 앱 세션 칸에 넘기고 이 앱 세션은 만들지 않는다', async () => {
    login.mockResolvedValue(out('admin'))
    const { w } = await mountLogin('student')
    await w.findAll('[role="radiogroup"] input')[1].setValue(true)
    await submit(w)
    expect(session.value).toBeNull()
    expect(JSON.parse(sessionStorage.getItem('esc.session.admin')!).role).toBe('admin')
    sessionStorage.removeItem('esc.session.admin')
  })

  it('관리자 탭인데 학생 계정 — 탭을 가리키는 문구, 어디에도 세션을 남기지 않는다', async () => {
    login.mockResolvedValue(out('student'))
    const { w } = await mountLogin('student')
    await w.findAll('[role="radiogroup"] input')[1].setValue(true)
    await submit(w)
    expect(w.text()).toContain("학생 계정입니다. 위의 '학생'을 골라 로그인하세요.")
    expect(session.value).toBeNull()
    expect(sessionStorage.getItem('esc.session.admin')).toBeNull()
  })

  it.each(['student', 'admin'] as const)(
    '%s 앱 — 같은 틀·같은 제목이라 탭만 바뀐 것처럼 (관리자도 student 치수 · 좌우 분할)',
    async (app) => {
      const { w } = await mountLogin(app)
      // 제목은 스크린리더용으로만 — 탭·제출 버튼이 이미 '로그인'이라 화면에는 그리지 않는다 (auth.md, #95)
      expect(w.get('h1').text()).toBe('로그인')
      expect(w.get('h1').classes()).toContain('auth__title--sr')
      expect(w.get('.auth').attributes('data-surface')).toBe('student')
      expect(w.find('aside.auth__intro').exists()).toBe(true)
      // ‹ 는 메인 페이지 / 로 가는 진짜 링크 — 관리자 앱에서도 / (auth.md 「탭」)
      expect(w.get('a.auth__home').attributes('href')).toBe('/')
    },
  )
})
