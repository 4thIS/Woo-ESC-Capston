import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount } from '@vue/test-utils'
import { studentApi } from '@/api/student'
import HomeView from '@/student/views/HomeView.vue'
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

const E = [roomState({ room_id: 1, room: 401, layout: 1 }), roomState({ room_id: 2, room: 402 })]
const K = roomState({
  room_id: 3,
  building_id: 4,
  building: '운영관',
  bld: 'K',
  room: 101,
  layout: 6,
})

beforeEach(() => {
  localStorage.clear()
  api.rooms.mockReset()
})

describe('HomeView — / 첫 진입 (student-room.md 미결 3)', () => {
  it('최근 건물이 있으면 그리로', async () => {
    localStorage.setItem('esc.lastBld', 'K')
    api.rooms.mockResolvedValue([...E, K])
    const { router } = await mountAt(HomeView, '/', '/')
    expect(router.currentRoute.value.path).toBe('/K')
  })

  it('건물이 하나뿐이면 바로 그 건물', async () => {
    api.rooms.mockResolvedValue(E)
    const { router } = await mountAt(HomeView, '/', '/')
    expect(router.currentRoute.value.path).toBe('/E')
  })

  it('여럿이면 건물 목록 — 이름·강의실 수·빈 곳, 최근 건물이 사라졌어도 목록', async () => {
    localStorage.setItem('esc.lastBld', 'Z')
    api.rooms.mockResolvedValue([...E, K])
    const { w, router } = await mountAt(HomeView, '/', '/')
    expect(router.currentRoute.value.path).toBe('/')
    const rows = w.findAll('a.home__row')
    expect(rows.map((a) => a.attributes('href'))).toEqual(['/E', '/K'])
    expect(rows.map((a) => a.attributes('aria-label'))).toEqual([
      '공학관 2개 강의실 · 지금 1곳 비어 있어요',
      '운영관 1개 강의실 · 지금 0곳 비어 있어요',
    ])
    expect(w.get('a.sh__me').attributes('href')).toBe('/me')
  })

  it('예약 가능한 방이 없으면 EmptyState, 조회 실패면 다시 시도', async () => {
    api.rooms.mockResolvedValue([])
    const empty = await mountAt(HomeView, '/', '/')
    expect(empty.w.text()).toContain('예약할 수 있는 강의실이 없습니다')
    const { ApiError, MESSAGES } = await import('@/api/client')
    api.rooms.mockRejectedValueOnce(new ApiError(0, MESSAGES[0])).mockResolvedValue(E)
    const failed = await mountAt(HomeView, '/', '/')
    expect(failed.w.text()).toContain('건물 목록을 불러오지 못했어요')
    await failed.w.get('.empty button').trigger('click')
    await vi.waitFor(() => expect(failed.router.currentRoute.value.path).toBe('/E'))
  })
})
