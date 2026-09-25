import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { ApiError, MESSAGES } from '@/api/client'
import { studentApi } from '@/api/student'
import { favorites } from '@/student/favorites'
import BuildingLayout from '@/student/views/BuildingLayout.vue'
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

const ROOMS = [
  roomState({ room_id: 1, room: 401, layout: 1, until: '10:50' }),
  roomState({ room_id: 2, room: 402, layout: 4, until: '13:00' }),
  roomState({ room_id: 3, room: 403, layout: 4, until: null }),
  roomState({
    room_id: 4,
    building_id: 4,
    building: '운영관',
    bld: 'K',
    room: 101,
    layout: 6,
    until: '12:00',
  }),
]
const roomNames = (w: Awaited<ReturnType<typeof mountAt>>['w']) =>
  w.findAll('ul.rows .row__room').map((r) => r.text())

beforeEach(() => {
  localStorage.clear()
  favorites.value = []
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' })
  api.rooms.mockReset().mockResolvedValue(ROOMS)
})
afterEach(() => vi.useRealTimers())

describe('BuildingLayout — /:bld 강의실 목록', () => {
  it('맨 위는 빈 곳 개수, 빈 강의실만이 기본 — 끄면 전체, 상태를 먼저 말한다', async () => {
    const { w } = await mountAt(BuildingLayout, '/E', '/:bld')
    expect(w.get('.list__count').text()).toBe('2곳이 지금 비어 있어요')
    expect(w.get('.list__sub').text()).toMatch(/^공학관 3개 강의실 · \d\d:\d\d 기준$/)
    expect(roomNames(w)).toEqual(['402호', '403호'])
    expect(w.findAll('ul.rows .row__until').map((u) => u.text())).toEqual([
      '13:00 까지',
      '오늘 계속 비어 있어요',
    ])
    await w.get('input[type="checkbox"]').setValue(false)
    expect(roomNames(w)).toEqual(['401호', '402호', '403호'])
    const busy = w.findAll('ul.rows > li')[0]
    expect(busy.get('.badge').text()).toBe('수업중')
    expect(busy.get('a').attributes('href')).toBe('/E/401')
    expect(w.get('.rn').text()).toContain('갱신')
  })

  it('다른 건물로 — 헤더 Select 가 주소를 바꾸고, 모두 사용 중이면 전체 보기', async () => {
    const { w, router } = await mountAt(BuildingLayout, '/E', '/:bld')
    expect(localStorage.getItem('esc.lastBld')).toBe('E')
    await w.get('select').setValue('K')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/K')
    expect(localStorage.getItem('esc.lastBld')).toBe('K')
    expect(w.get('.list__count').text()).toBe('지금 비어 있는 강의실이 없어요')
    expect(w.text()).toContain('지금은 모든 강의실이 사용 중입니다')
    await w.get('.empty button').trigger('click')
    expect(roomNames(w)).toEqual(['101호'])
  })

  it('즐겨찾기 — 비어 있으면 섹션이 없고, ★ 을 누르면 생기며 esc.fav 에 남는다, 다른 건물은 이름을 붙인다', async () => {
    const { w } = await mountAt(BuildingLayout, '/E', '/:bld')
    expect(w.find('.fav').exists()).toBe(false)
    await w.findAll('ul.rows > li')[0].get('button').trigger('click')
    expect(localStorage.getItem('esc.fav')).toBe('["E-402"]')
    expect(w.findAll('a.fav__chip').map((a) => a.attributes('aria-label'))).toEqual([
      '402호 비어있음',
    ])
    favorites.value = ['K-101', 'E-402']
    await flushPromises()
    expect(w.findAll('a.fav__chip').map((a) => a.attributes('href'))).toEqual(['/E/402', '/K/101'])
    expect(w.findAll('a.fav__chip')[1].attributes('aria-label')).toBe('운영관 101호 특강')
  })

  it('쉬는시간·휴강·설정 대기는 예약할 수 없다 — 빈 곳으로 세지도, 칠하지도 않는다', async () => {
    api.rooms.mockResolvedValue([
      roomState({ room_id: 5, room: 501, layout: 2 }),
      roomState({ room_id: 6, room: 502, layout: 3 }),
      roomState({ room_id: 7, room: 503, layout: 8 }),
    ])
    const { w } = await mountAt(BuildingLayout, '/E', '/:bld')
    expect(w.get('.list__count').text()).toBe('지금 비어 있는 강의실이 없어요')
    await w.get('input[type="checkbox"]').setValue(false)
    expect(w.findAll('ul.rows .row__state').map((s) => s.text())).toEqual([
      '쉬는시간',
      '휴강',
      '설정 대기',
    ])
    expect(w.find('ul.rows .row__free').exists()).toBe(false)
    expect(w.findAll('ul.rows .row__other')).toHaveLength(3)
  })

  it('없는 건물 글자면 404 + 건물 목록 링크', async () => {
    const { w } = await mountAt(BuildingLayout, '/Q', '/:bld')
    expect(w.get('h2').text()).toBe('찾을 수 없는 주소예요')
    expect(w.get('a.nf__link').attributes('href')).toBe('/')
    expect(localStorage.getItem('esc.lastBld')).toBeNull()
  })

  it('조회 실패 — 이전 목록을 지우지 않고 danger Banner + 다시 시도', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    const { w } = await mountAt(BuildingLayout, '/E', '/:bld')
    api.rooms.mockRejectedValue(new ApiError(0, MESSAGES[0]))
    await vi.advanceTimersByTimeAsync(60_000)
    await flushPromises()
    expect(w.get('[role="alert"]').text()).toContain(MESSAGES[0])
    expect(roomNames(w)).toEqual(['402호', '403호'])
    api.rooms.mockResolvedValue(ROOMS)
    await w.get('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(w.find('[role="alert"]').exists()).toBe(false)
  })

  it('첫 조회가 실패하면 빈 목록이 아니라 다시 시도', async () => {
    api.rooms.mockRejectedValueOnce(new ApiError(503, MESSAGES[503]))
    const { w } = await mountAt(BuildingLayout, '/E', '/:bld')
    expect(w.text()).toContain('강의실 목록을 불러오지 못했어요')
    expect(w.find('ul.rows').exists()).toBe(false)
    await w.get('.empty button').trigger('click')
    await flushPromises()
    expect(roomNames(w)).toEqual(['402호', '403호'])
  })
})
