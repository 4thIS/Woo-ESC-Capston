import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { readFragmentToken } from '@/auth/fragment'
import SignupView from '@/auth/SignupView.vue'
import VerifyView from '@/auth/VerifyView.vue'
import ResetView from '@/auth/ResetView.vue'
import { ApiError, MESSAGES } from '@/api/client'
import { authApi } from '@/api/auth'

vi.mock('@/api/auth', () => ({
  authApi: {
    signup: vi.fn(),
    verifyOpen: vi.fn(),
    verify: vi.fn(),
    reset: vi.fn(),
    forgot: vi.fn(),
  },
}))
const api = vi.mocked(authApi)
const err = (s: number, fields: string[] = []) => new ApiError(s, MESSAGES[s], fields)
const Empty = { template: '<div />' }

async function mountView(C: object) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: ['/login', '/signup', '/verify', '/forgot', '/reset'].map((path) => ({
      path,
      component: Empty,
    })),
  })
  await router.push('/signup')
  const w = mount(C, { global: { plugins: [router] } })
  await flushPromises()
  return { w, router }
}
const setHash = (h: string) => history.replaceState(null, '', `/verify${h}`)

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset())
  setHash('')
})

describe('readFragmentToken', () => {
  it('읽자마자 주소에서 지운다', () => {
    setHash('#token=abc_DEF-123')
    expect(readFragmentToken()).toBe('abc_DEF-123')
    expect(location.hash).toBe('')
    expect(location.pathname).toBe('/verify')
  })
  it('없거나 모양이 다르면 null (그래도 지운다)', () => {
    expect(readFragmentToken()).toBeNull()
    setHash('#token=<script>')
    expect(readFragmentToken()).toBeNull()
    expect(location.hash).toBe('')
  })
})

describe('SignupView', () => {
  it('400 → 입력 칸 에러, 단계 안내는 그대로', async () => {
    api.signup.mockRejectedValue(err(400))
    const { w } = await mountView(SignupView)
    await w.get('input').setValue('a@gmail.com')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(w.text()).toContain('학교 웹메일로만 가입할 수 있어요')
    expect(w.text()).toContain('메일로 링크를 보냅니다')
  })

  it('202 → 보냈어요 + 60초 동안 다시 보내기 잠금 + 이미 가입 안내', async () => {
    vi.useFakeTimers()
    api.signup.mockResolvedValue({ status: 'sent' })
    const { w } = await mountView(SignupView)
    await w.get('input').setValue(' s1@wsu.ac.kr ')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(api.signup).toHaveBeenCalledWith('s1@wsu.ac.kr')
    expect(w.text()).toContain('s1@wsu.ac.kr 로 보냈어요')
    expect(w.text()).toContain('이미 가입한 메일이면 메일이 오지 않습니다. 로그인해 보세요.')
    const resend = () => w.get('button').element as HTMLButtonElement
    expect(resend().disabled).toBe(true)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(resend().disabled).toBe(false)
    vi.useRealTimers()
  })
})

describe('VerifyView', () => {
  it('토큰이 없으면 서버를 부르지 않고 만료 안내 (Review Focus 2)', async () => {
    const { w } = await mountView(VerifyView)
    expect(api.verifyOpen).not.toHaveBeenCalled()
    expect(w.text()).toContain('링크가 만료되었거나 잘못되었습니다')
  })

  it('열자마자 verify/open, 이메일은 읽기 전용으로', async () => {
    setHash('#token=tok1')
    api.verifyOpen.mockResolvedValue({ email: 's1@wsu.ac.kr' })
    const { w } = await mountView(VerifyView)
    expect(api.verifyOpen).toHaveBeenCalledWith('tok1')
    expect(w.text()).toContain('s1@wsu.ac.kr')
    expect(w.findAll('input')).toHaveLength(3) // 이름·학번·비밀번호 — 이메일은 입력이 아니다
  })

  it('409 → 학번 칸만 에러, 나머지 입력은 유지', async () => {
    setHash('#token=tok1')
    api.verifyOpen.mockResolvedValue({ email: 's1@wsu.ac.kr' })
    api.verify.mockRejectedValue(err(409))
    const { w } = await mountView(VerifyView)
    const [name, no, pw] = w.findAll('input')
    await name.setValue('김민준')
    await no.setValue('20231234')
    await pw.setValue('password1')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(w.text()).toContain('이미 등록된 학번입니다')
    expect((name.element as HTMLInputElement).value).toBe('김민준')
    expect(api.verify).toHaveBeenCalledWith({
      token: 'tok1',
      name: '김민준',
      student_no: '20231234',
      password: 'password1',
    })
  })

  it('학번 형식·비밀번호 길이는 보내기 전에 막는다', async () => {
    setHash('#token=tok1')
    api.verifyOpen.mockResolvedValue({ email: 's1@wsu.ac.kr' })
    const { w } = await mountView(VerifyView)
    const [name, no, pw] = w.findAll('input')
    await name.setValue('김민준')
    await no.setValue('2023 1234')
    await pw.setValue('short')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(api.verify).not.toHaveBeenCalled()
    expect(w.text()).toContain('학번은 영문·숫자·하이픈만 쓸 수 있어요')
    expect(w.text()).toContain('8자 이상 입력해 주세요')
  })

  it('성공 → 승인 대기 화면', async () => {
    setHash('#token=tok1')
    api.verifyOpen.mockResolvedValue({ email: 's1@wsu.ac.kr' })
    api.verify.mockResolvedValue({ status: 'pending_approval' })
    const { w } = await mountView(VerifyView)
    const [name, no, pw] = w.findAll('input')
    await name.setValue('김민준')
    await no.setValue('20231234')
    await pw.setValue('password1')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(w.text()).toContain('승인을 기다리는 중입니다')
    expect(w.find('form').exists()).toBe(false)
  })
})

describe('ResetView', () => {
  it('성공 → 다른 기기 로그아웃 안내 + 관리자 안내 한 줄', async () => {
    setHash('#token=r1')
    api.reset.mockResolvedValue({ status: 'ok' })
    const { w } = await mountView(ResetView)
    await w.get('input').setValue('newpassword1')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(api.reset).toHaveBeenCalledWith('r1', 'newpassword1')
    expect(w.text()).toContain('다른 기기에서 로그인해 있던 곳은 모두 로그아웃됩니다')
    expect(w.text()).toContain('관리자 계정이면 관리자 웹 주소에서 로그인하세요.')
  })

  it('400 → 비밀번호를 잊었어요로 되돌린다', async () => {
    setHash('#token=r1')
    api.reset.mockRejectedValue(err(400))
    const { w } = await mountView(ResetView)
    await w.get('input').setValue('newpassword1')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(w.text()).toContain('링크가 만료되었거나 잘못되었습니다')
    expect(w.find('a[href="/forgot"]').exists()).toBe(true)
  })
})
