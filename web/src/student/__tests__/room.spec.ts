import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { ApiError, MESSAGES } from '@/api/client'
import { studentApi } from '@/api/student'
import type { WeekOut } from '@/api/types'
import week from '@/api/__fixtures__/week.json'
import { favorites } from '@/student/favorites'
import RoomView from '@/student/views/RoomView.vue'
import WeekView from '@/student/views/WeekView.vue'
import { mountAt, roomState, stubMedia } from './support'

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
const ROOMS = [roomState({ room_id: 11, room: 401, layout: 1, until: '10:50' })]

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-23T01:42:00Z')) // KST 금 10:42 — 픽스처의 오늘
  favorites.value = []
  localStorage.clear()
  api.week.mockReset().mockResolvedValue(WEEK)
  stubMedia(false)
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('RoomView — /:bld/:room', () => {
  it('오늘 — 빈 구간도 행, 지금 행에 지금 배지(brand), 내 신청 표시, ‹ 는 목록 링크', async () => {
    const { w } = await mountAt(RoomView, '/E/401', '/:bld/:room', ROOMS)
    expect(api.week).toHaveBeenCalledWith(11)
    expect(w.get('h1').text()).toBe('공학관 401호')
    expect(w.get('#today-h').text()).toContain('10월 23일 금')
    const rows = w.findAll('.today__row')
    expect(rows.map((r) => r.get('.today__label').text())).toEqual([
      '비어있음 —10:00',
      '알고리즘 외 1건',
      '비어있음 —15:00',
      '캡스톤 스터디',
      '비어있음 —21:00',
    ])
    const now = w.get('.today__row--now')
    expect(now.get('.today__label').text()).toBe('알고리즘 외 1건')
    expect(now.findAll('.badge').map((b) => b.text())).toEqual(['수업중', '지금 10:42'])
    expect(now.findAll('.badge')[1].classes()).toEqual(
      expect.arrayContaining(['badge--brand', 'badge--solid']),
    )
    expect(w.findAll('.today__row--now')).toHaveLength(1)
    expect(rows[3].get('.today__label').classes()).toContain('today__label--mine')
    const back = w.get('a.sh__back')
    expect(back.attributes('href')).toBe('/E')
    expect(back.attributes('aria-label')).toBe('강의실 목록')
    expect(w.get('a.room__week').attributes('href')).toBe('/E/401/week')
    expect(w.get('.room__cta a.cta').attributes('href')).toBe('/E/401/reserve')
    expect(w.find('.wg').exists()).toBe(false)
  })

  it('헤더 ★ — 즐겨찾기 토글, esc.fav 에 남는다', async () => {
    const { w } = await mountAt(RoomView, '/E/401', '/:bld/:room', ROOMS)
    await w.get('.sh button').trigger('click')
    expect(localStorage.getItem('esc.fav')).toBe('["E-401"]')
    expect(w.get('.sh button').attributes('aria-label')).toBe('즐겨찾기')
    expect(w.get('.sh button').attributes('aria-pressed')).toBe('true')
  })

  it('넓은 폭 — 다음 비는 시간 카드, 같은 격자(32, 오늘 금), 예약은 헤더 오른쪽 40px', async () => {
    stubMedia(true)
    const { w } = await mountAt(RoomView, '/E/401', '/:bld/:room', ROOMS)
    expect(w.get('.room__next-v').text()).toBe('13:00 – 15:00 · 2시간')
    expect(w.find('.wg--wide').exists()).toBe(true)
    expect(w.get('.wg__day--today').text()).toBe('금')
    expect(w.find('.room__cta').exists()).toBe(false)
    expect(w.find('a.room__week').exists()).toBe(false)
    const cta = w.get('.sh a.cta')
    expect(cta.attributes('href')).toBe('/E/401/reserve')
    expect(cta.classes()).toContain('cta--compact')
  })

  it('목록에 없는 호수·주간 404 면 404 화면 + 강의실 목록 링크', async () => {
    const missing = await mountAt(RoomView, '/E/499', '/:bld/:room', ROOMS)
    expect(missing.w.get('h2').text()).toBe('찾을 수 없는 주소예요')
    expect(missing.w.get('a.nf__link').attributes('href')).toBe('/E')
    expect(api.week).not.toHaveBeenCalled()
    api.week.mockRejectedValue(new ApiError(404, MESSAGES[404]))
    const gone = await mountAt(RoomView, '/E/401', '/:bld/:room', ROOMS)
    expect(gone.w.get('h2').text()).toBe('찾을 수 없는 주소예요')
  })

  it('방을 바꾸면 이전 방 시간표를 지운다 — 402 가 실패하면 401 목록이 아니라 다시 시도', async () => {
    const rooms = [...ROOMS, roomState({ room_id: 12, room: 402 })]
    const { w, router } = await mountAt(RoomView, '/E/401', '/:bld/:room', rooms)
    expect(w.findAll('.today__row')).toHaveLength(5)
    api.week.mockRejectedValue(new ApiError(0, MESSAGES[0]))
    await router.push('/E/402')
    await flushPromises()
    expect(api.week).toHaveBeenLastCalledWith(12)
    expect(w.get('h1').text()).toBe('공학관 402호')
    expect(w.findAll('.today__row')).toHaveLength(0)
    expect(w.text()).toContain('시간표를 불러오지 못했어요')
    expect(w.find('.banner').exists()).toBe(false)
  })

  it('레이아웃 방 목록 첫 조회 실패 — 끝없는 Skeleton 이 아니라 다시 시도(목록을 다시 부른다)', async () => {
    const reload = vi.fn(async () => {})
    const { w } = await mountAt(RoomView, '/E/401', '/:bld/:room', ROOMS, {
      rooms: ref(undefined),
      loaded: ref(false),
      error: ref(new ApiError(0, MESSAGES[0])),
      reload,
    })
    expect(api.week).not.toHaveBeenCalled()
    await w.get('.empty button').trigger('click')
    expect(reload).toHaveBeenCalled()
  })

  it('서버 주간이 이번 주가 아니면(자정 직후) 오늘 목록을 세우지 않는다', async () => {
    api.week.mockResolvedValue({ ...WEEK, week_start: '2026-10-12' })
    const { w } = await mountAt(RoomView, '/E/401', '/:bld/:room', ROOMS)
    expect(w.findAll('.today__row')).toHaveLength(0)
  })

  it('주간 첫 조회 실패 — 오늘 목록 자리에 다시 시도', async () => {
    api.week.mockRejectedValueOnce(new ApiError(0, MESSAGES[0]))
    const { w } = await mountAt(RoomView, '/E/401', '/:bld/:room', ROOMS)
    expect(w.text()).toContain('시간표를 불러오지 못했어요')
    await w.get('.empty button').trigger('click')
    await flushPromises()
    expect(w.findAll('.today__row')).toHaveLength(5)
  })
})

describe('WeekView — /:bld/:room/week', () => {
  it('레이아웃 방 목록 첫 조회 실패 — 다시 시도', async () => {
    const reload = vi.fn(async () => {})
    const { w } = await mountAt(WeekView, '/E/401/week', '/:bld/:room/week', ROOMS, {
      rooms: ref(undefined),
      loaded: ref(false),
      error: ref(new ApiError(0, MESSAGES[0])),
      reload,
    })
    await w.get('.empty button').trigger('click')
    expect(reload).toHaveBeenCalled()
  })

  it('좁은 폭 — 24px 격자, 제목, 강의실로 돌아가는 링크', async () => {
    const { w } = await mountAt(WeekView, '/E/401/week', '/:bld/:room/week', ROOMS)
    expect(w.get('h1').text()).toBe('공학관 401호 · 이번 주')
    expect(w.get('a.sh__back').attributes('href')).toBe('/E/401')
    expect(w.find('.wg--wide').exists()).toBe(false)
    expect(
      w.get('[aria-label="금 10:00–13:00 수업중 알고리즘 외 1건"]').attributes('style'),
    ).toContain('height: 144px')
    expect(w.get('.wg__day--today').text()).toBe('금')
  })

  it('넓은 폭이면(처음부터든 바뀌든) /:bld/:room 으로 replace — 이미 그 안에 있다', async () => {
    const media = stubMedia(false)
    const { router } = await mountAt(WeekView, '/E/401/week', '/:bld/:room/week', ROOMS)
    expect(router.currentRoute.value.path).toBe('/E/401/week')
    media.change(true)
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/E/401')
    stubMedia(true)
    const wide = await mountAt(WeekView, '/E/401/week', '/:bld/:room/week', ROOMS)
    expect(wide.router.currentRoute.value.path).toBe('/E/401')
  })
})
