import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { ApiError, MESSAGES } from '@/api/client'
import { mineResv } from '@/api/__fixtures__/mine'
import { studentApi } from '@/api/student'
import type { ResvMineOut, WeekOut } from '@/api/types'
import week from '@/api/__fixtures__/week.json'
import { CAP_TEXT, DAILY_TEXT, FULL_TEXT, STALE_TEXT, TAKEN_TEXT } from '@/components/student/rules'
import { dismissToast, toasts } from '@/components/ui/toast'
import ReserveSheet from '@/components/student/ReserveSheet.vue'
import ReserveView from '@/student/views/ReserveView.vue'
import { mountAt, roomState } from './support'

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

const WEEK = week as WeekOut
const ROOMS = [roomState({ room_id: 11, room: 401 })]
const PATH = ['/E/401/reserve', '/:bld/:room/reserve'] as const
/** 공용 빌더(M1)의 대기중 신청 한 건 */
const reqResv = (over: Partial<ResvMineOut> = {}): ResvMineOut =>
  mineResv({ status: 'requested', decided_at: null, s_h: 10, e_h: 11, subject: '스터디', ...over })
const THREE = [
  reqResv({ id: 1 }),
  reqResv({ id: 2, s_h: 12, e_h: 13 }),
  reqResv({ id: 3, s_h: 14, e_h: 15 }),
]
const texts = () => toasts.value.map((t) => t.message)
const submitBtn = (w: VueWrapper) => w.get<HTMLButtonElement>('button[type="submit"]')
/** 오늘(10-23) 첫 구간 13:00–15:00 → 13:00–14:00, 목적 '스터디' 로 제출 */
async function fillAndSubmit(w: VueWrapper) {
  await w.findAll('input[type="radio"]')[0].setValue()
  await w.get('.field__control').setValue('스터디')
  await w.get('form').trigger('submit')
  await flushPromises()
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-23T01:42:00Z')) // KST 금 10:42
  toasts.value.forEach((t) => dismissToast(t.id))
  api.week.mockReset().mockResolvedValue(WEEK)
  api.mine.mockReset().mockResolvedValue([])
  api.requestResv.mockReset()
})
afterEach(() => vi.useRealTimers())

describe('ReserveView — /:bld/:room/reserve', () => {
  it('신청 — 서버 모양으로 한 번, 성공하면 Toast 와 /me', async () => {
    api.requestResv.mockResolvedValue(reqResv({ date: '2026-10-23', s_h: 13, e_h: 14 }))
    const { w, router } = await mountAt(ReserveView, ...PATH, ROOMS)
    expect(w.get('h1').text()).toBe('공학관 401호 예약')
    const close = w.get('a.sh__back')
    expect(close.attributes('aria-label')).toBe('닫기')
    expect(close.attributes('href')).toBe('/E/401')
    await fillAndSubmit(w)
    expect(api.requestResv).toHaveBeenCalledWith(11, {
      date: '2026-10-23',
      s_h: 13,
      s_m: 0,
      e_h: 14,
      e_m: 0,
      subject: '스터디',
    })
    expect(texts()).toContain('예약을 신청했어요. 관리자 승인 뒤 확정돼요.')
    expect(router.currentRoute.value.path).toBe('/me')
  })

  it('409 — 재조회한 full 이 false 면 먼저 신청한 사람, 사라진 구간은 선택이 풀린다', async () => {
    api.requestResv.mockRejectedValue(new ApiError(409, MESSAGES[409]))
    const taken: WeekOut = {
      ...WEEK,
      free: WEEK.free.map((d) =>
        d.date === '2026-10-23' ? { ...d, spans: [{ from: '16:00', to: '21:00' }] } : d,
      ),
    }
    api.week.mockResolvedValueOnce(WEEK).mockResolvedValue(taken)
    const { w, router } = await mountAt(ReserveView, ...PATH, ROOMS)
    await fillAndSubmit(w)
    expect(texts()).toEqual([TAKEN_TEXT])
    expect(api.week).toHaveBeenCalledTimes(2)
    expect(router.currentRoute.value.path).toBe('/E/401/reserve')
    expect(w.findAll('.rs__span .num').map((s) => s.text())).toEqual(['16:00 – 21:00'])
    expect(submitBtn(w).element.disabled).toBe(true)
  })

  it('409 — 재조회한 full 이 true 면 방이 찼다', async () => {
    api.requestResv.mockRejectedValue(new ApiError(409, MESSAGES[409]))
    api.week
      .mockResolvedValueOnce(WEEK)
      .mockResolvedValue({ ...WEEK, full: true, free: WEEK.free.map((d) => ({ ...d, spans: [] })) })
    const { w } = await mountAt(ReserveView, ...PATH, ROOMS)
    await fillAndSubmit(w)
    expect(texts()).toEqual([FULL_TEXT])
    expect(w.get('.rs__blocker').text()).toBe(FULL_TEXT)
  })

  it('429 — Toast 뒤 이 화면에 있는 동안 잠금 (하루 상한 — 10초 뒤 풀어도 또 429)', async () => {
    api.requestResv.mockRejectedValue(new ApiError(429, MESSAGES[429]))
    const { w } = await mountAt(ReserveView, ...PATH, ROOMS)
    await fillAndSubmit(w)
    expect(texts()).toEqual([DAILY_TEXT])
    expect(w.get('.rs__blocker').text()).toBe(DAILY_TEXT)
    expect(submitBtn(w).element.disabled).toBe(true)
  })

  it('400 — 재조회해 진행 중이 3건이면 CAP, 아니면 STALE', async () => {
    api.requestResv.mockRejectedValue(new ApiError(400, MESSAGES[400]))
    api.mine.mockResolvedValueOnce([]).mockResolvedValue(THREE)
    const cap = await mountAt(ReserveView, ...PATH, ROOMS)
    await fillAndSubmit(cap.w)
    expect(texts()).toEqual([CAP_TEXT])
    expect(cap.w.get('.rs__blocker').text()).toBe(CAP_TEXT)
    toasts.value.forEach((t) => dismissToast(t.id))
    api.mine.mockReset().mockResolvedValue([])
    const stale = await mountAt(ReserveView, ...PATH, ROOMS)
    await fillAndSubmit(stale.w)
    expect(texts()).toEqual([STALE_TEXT])
  })

  it('이미 진행 중 3건이면 처음부터 잠겨 있다', async () => {
    api.mine.mockResolvedValue(THREE)
    const { w } = await mountAt(ReserveView, ...PATH, ROOMS)
    expect(w.get('.rs__blocker').text()).toBe(CAP_TEXT)
  })

  it('두 번 눌러도 한 번 — 응답을 기다리는 동안 loading', async () => {
    let resolve!: (v: ResvMineOut) => void
    api.requestResv.mockReturnValue(
      new Promise<ResvMineOut>((r) => {
        resolve = r
      }),
    )
    const { w } = await mountAt(ReserveView, ...PATH, ROOMS)
    await fillAndSubmit(w)
    await w.get('form').trigger('submit')
    expect(api.requestResv).toHaveBeenCalledTimes(1)
    expect(submitBtn(w).attributes('aria-busy')).toBe('true')
    resolve(reqResv({}))
    await flushPromises()
  })

  it('같은 틱에 두 번 와도 한 번 — 시트의 submitting prop 은 한 렌더 늦으니 화면이 동기로 막는다', async () => {
    api.requestResv.mockReturnValue(new Promise<ResvMineOut>(() => {}))
    const { w } = await mountAt(ReserveView, ...PATH, ROOMS)
    const sheet = w.findComponent(ReserveSheet)
    const body = { date: '2026-10-23', s_h: 13, s_m: 0, e_h: 14, e_m: 0, subject: '스터디' }
    sheet.vm.$emit('submit', body)
    sheet.vm.$emit('submit', body)
    await flushPromises()
    expect(api.requestResv).toHaveBeenCalledTimes(1)
  })

  it('그새 예약을 받지 않게 된 방(404) — 404 화면', async () => {
    api.requestResv.mockRejectedValue(new ApiError(404, MESSAGES[404]))
    api.week.mockResolvedValueOnce(WEEK).mockRejectedValue(new ApiError(404, MESSAGES[404]))
    const { w } = await mountAt(ReserveView, ...PATH, ROOMS)
    await fillAndSubmit(w)
    expect(w.get('h2').text()).toBe('찾을 수 없는 주소예요')
  })
})
