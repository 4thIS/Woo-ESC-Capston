import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { ApiError, MESSAGES } from '@/api/client'
import { mineResv } from '@/api/__fixtures__/mine'
import { studentApi } from '@/api/student'
import type { ResvMineOut } from '@/api/types'
import { CHANGED_TEXT, CHECKIN_CLOSED_TEXT } from '@/components/student/rules'
import { dismissToast, toasts } from '@/components/ui/toast'
import { clearSession, session, setSession } from '@/lib/session'
import MyView from '@/student/views/MyView.vue'
import { mountAt } from './support'

vi.mock('@/api/student', () => ({
  studentApi: {
    rooms: vi.fn(),
    week: vi.fn(),
    mine: vi.fn(),
    requestResv: vi.fn(),
    cancel: vi.fn(),
    checkin: vi.fn(),
  },
}))
const api = vi.mocked(studentApi, true)
enableAutoUnmount(afterEach)

// 공용 빌더(M1) — 오늘 10:50 시작, 결정 전 시각 없음
const resv = (over: Partial<ResvMineOut> = {}): ResvMineOut =>
  mineResv({ date: '2026-10-23', s_m: 50, requested_at: null, decided_at: null, ...over })
const texts = () => toasts.value.map((t) => t.message)
const cards = (w: VueWrapper) => w.findAll('article')
const confirm = async (w: VueWrapper) => {
  await w.findAll('[role="dialog"] .modal__footer button')[1].trigger('click')
  await flushPromises()
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-23T01:42:00Z')) // KST 금 10:42
  localStorage.clear()
  toasts.value.forEach((t) => dismissToast(t.id))
  api.mine.mockReset()
  api.cancel.mockReset()
  api.checkin.mockReset()
})
afterEach(() => {
  vi.useRealTimers()
  clearSession()
})

describe('MyView — /me', () => {
  it('진행 중이 위 — 창 안이면 체크인, 누르면 다시 불러와 시각이 뜬다', async () => {
    const open = resv({ id: 7 })
    const rejected = resv({
      id: 9,
      date: '2026-10-20',
      status: 'rejected',
      reject_reason: '학과 행사와 겹칩니다',
    })
    const done = { ...open, checked_in_at: new Date('2026-10-23T01:42:00Z') }
    api.mine.mockResolvedValueOnce([rejected, open]).mockResolvedValue([done, rejected])
    api.checkin.mockResolvedValue(done)
    const { w } = await mountAt(MyView, '/me', '/me')
    expect(cards(w).map((c) => c.get('.badge').text())).toEqual(['승인됨', '거절됨'])
    expect(cards(w)[1].get('.mc__note').text()).toBe('사유: 학과 행사와 겹칩니다')
    await cards(w)[0].get('button').trigger('click')
    await flushPromises()
    expect(api.checkin).toHaveBeenCalledWith(7)
    expect(api.mine).toHaveBeenCalledTimes(2)
    expect(texts()).toContain('체크인했어요')
    expect(cards(w)[0].get('.mc__done').text()).toBe('✓ 10:42 체크인')
  })

  it('신청 취소 — 확인 Modal 에 "기록이 남지 않습니다", 확인하면 cancel + 재조회로 사라진다', async () => {
    const req = resv({ id: 5, status: 'requested', s_h: 14, s_m: 0, e_h: 15 })
    api.mine.mockResolvedValueOnce([req]).mockResolvedValue([])
    api.cancel.mockResolvedValue({ ...req, status: 'cancelled' })
    const { w } = await mountAt(MyView, '/me', '/me')
    await cards(w)[0].get('button').trigger('click')
    const dlg = w.get('[role="dialog"]')
    expect(dlg.get('h2').text()).toBe('신청 취소')
    expect(dlg.text()).toContain('신청을 거두면 기록이 남지 않습니다.')
    expect(api.cancel).not.toHaveBeenCalled()
    await confirm(w)
    expect(api.cancel).toHaveBeenCalledWith(5)
    expect(cards(w)).toHaveLength(0)
    expect(w.text()).toContain('아직 신청한 예약이 없어요')
  })

  it('승인 예약 취소 — 제목·문구가 다르고, 닫기면 아무것도 보내지 않는다', async () => {
    api.mine.mockResolvedValue([resv({ s_h: 11, s_m: 0 })])
    const { w } = await mountAt(MyView, '/me', '/me')
    const cancel = cards(w)[0]
      .findAll('button')
      .find((b) => b.text() === '취소')!
    await cancel.trigger('click')
    const dlg = w.get('[role="dialog"]')
    expect(dlg.get('h2').text()).toBe('예약 취소')
    expect(dlg.text()).toContain('취소하면 문 앞 화면에서도 지워져요.')
    await dlg.findAll('.modal__footer button')[0].trigger('click')
    expect(w.find('[role="dialog"]').exists()).toBe(false)
    expect(api.cancel).not.toHaveBeenCalled()
  })

  it('취소 경합 — 관리자가 먼저 거절했으면 409: 이유 문장 + 재조회, 버튼이 잠긴 채 남지 않는다', async () => {
    const req = resv({ id: 5, status: 'requested', s_h: 14, s_m: 0, e_h: 15 })
    api.mine
      .mockResolvedValueOnce([req])
      .mockResolvedValue([{ ...req, status: 'rejected', reject_reason: '정원 초과' }])
    api.cancel.mockRejectedValue(new ApiError(409, MESSAGES[409]))
    const { w } = await mountAt(MyView, '/me', '/me')
    await cards(w)[0].get('button').trigger('click')
    await confirm(w)
    expect(texts()).toContain(CHANGED_TEXT)
    expect(texts()).not.toContain(MESSAGES[409])
    expect(api.mine).toHaveBeenCalledTimes(2)
    expect(cards(w)[0].get('.badge').text()).toBe('거절됨')
    expect(cards(w)[0].findAll('button')).toHaveLength(0)
  })

  it('체크인 409(서버와 시계가 어긋남) — 문장 + 재조회, 버튼이 다시 눌린다', async () => {
    api.mine.mockResolvedValue([resv()])
    api.checkin.mockRejectedValue(new ApiError(409, MESSAGES[409]))
    const { w } = await mountAt(MyView, '/me', '/me')
    await cards(w)[0].get('button').trigger('click')
    await flushPromises()
    expect(texts()).toContain(CHECKIN_CLOSED_TEXT)
    expect(api.mine).toHaveBeenCalledTimes(2)
    expect((cards(w)[0].get('button').element as HTMLButtonElement).disabled).toBe(false)
  })

  it('비어 있으면 강의실 보러 가기(최근 건물로), 로그아웃은 토큰을 버린다', async () => {
    localStorage.setItem('esc.lastBld', 'E')
    setSession({ token: 't', role: 'student', school_id: 1, name: '김민준' })
    api.mine.mockResolvedValue([])
    const { w, router } = await mountAt(MyView, '/me', '/me')
    expect(w.get('a.sh__back').attributes('href')).toBe('/E')
    await w.get('.empty button').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/E')
    const logout = w.findAll('button').find((b) => b.text() === '로그아웃')!
    await logout.trigger('click')
    await flushPromises()
    expect(session.value).toBeNull()
    expect(router.currentRoute.value.path).toBe('/login')
  })

  it('체크인 두 번 연속 — busy 를 await 전에 세워 한 번만 보낸다', async () => {
    api.mine.mockResolvedValue([resv()])
    api.checkin.mockReturnValue(new Promise(() => {}))
    const { w } = await mountAt(MyView, '/me', '/me')
    const btn = cards(w)[0].get('button')
    void btn.trigger('click')
    void btn.trigger('click')
    await flushPromises()
    expect(api.checkin).toHaveBeenCalledTimes(1)
  })

  it('첫 조회 실패 — 빈 목록이 아니라 다시 시도, 누르면 다시 부른다', async () => {
    api.mine.mockRejectedValueOnce(new ApiError(0, MESSAGES[0])).mockResolvedValue([resv()])
    const { w } = await mountAt(MyView, '/me', '/me')
    expect(w.text()).toContain('내 예약을 불러오지 못했어요')
    expect(w.text()).not.toContain('아직 신청한 예약이 없어요')
    await w.get('.empty button').trigger('click')
    await flushPromises()
    expect(cards(w)).toHaveLength(1)
  })

  it('체크인 성공 뒤 재조회가 끝날 때까지 카드가 잠긴다 — 옛 체크인 버튼이 다시 눌리지 않게', async () => {
    let done!: (v: ResvMineOut[]) => void
    api.mine.mockResolvedValueOnce([resv()]).mockReturnValueOnce(new Promise((ok) => (done = ok)))
    api.checkin.mockResolvedValue(resv())
    const { w } = await mountAt(MyView, '/me', '/me')
    await cards(w)[0].get('button').trigger('click')
    await flushPromises()
    expect(api.mine).toHaveBeenCalledTimes(2)
    const btns = () =>
      cards(w)[0]
        .findAll('button')
        .map((b) => (b.element as HTMLButtonElement).disabled)
    expect(btns().every(Boolean)).toBe(true)
    done([resv({ checked_in_at: new Date('2026-10-23T01:42:00Z') })])
    await flushPromises()
    expect(cards(w)[0].get('.mc__done').text()).toBe('✓ 10:42 체크인')
    expect(btns().every((d) => !d)).toBe(true)
  })
})
