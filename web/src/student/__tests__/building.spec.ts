import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { ApiError, MESSAGES } from '@/api/client'
import { studentApi } from '@/api/student'
import { clearSession, session, setSession } from '@/lib/session'
import { favorites } from '@/student/favorites'
import BuildingLayout from '@/student/views/BuildingLayout.vue'
import { mineResv } from '@/api/__fixtures__/mine'
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
const chip = (w: Awaited<ReturnType<typeof mountAt>>['w'], label: string) =>
  w.findAll('.chips__chip').find((b) => b.text() === label)!
const stats = (w: Awaited<ReturnType<typeof mountAt>>['w']) =>
  w.findAll('.stats dd').map((d) => d.text())
const roomNames = (w: Awaited<ReturnType<typeof mountAt>>['w']) =>
  w.findAll('ul.rows .row__room').map((r) => r.text())

beforeEach(() => {
  stubMedia(false)
  localStorage.clear()
  favorites.value = []
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' })
  api.rooms.mockReset().mockResolvedValue(ROOMS)
  api.mine.mockReset().mockResolvedValue([])
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('BuildingLayout — /:bld 강의실 목록', () => {
  it('폰 — 숫자 칸(빈 곳 · 사용중), 제목은 강의실, 빈 곳이 기본 — 전체를 누르면 전체, 상태를 먼저 말한다', async () => {
    const { w } = await mountAt(BuildingLayout, '/E', '/:bld')
    // 내 예약 링크 · 로그아웃은 메뉴(StudentNav)로 옮겼다
    expect(w.find('a.me__link').exists()).toBe(false)
    expect(stats(w).slice(0, 2)).toEqual(['2', '1'])
    expect(w.get('.list__count').text()).toBe('강의실')
    expect(chip(w, '빈 곳').attributes('aria-pressed')).toBe('true')
    expect(roomNames(w)).toEqual(['402호', '403호'])
    expect(w.findAll('ul.rows .row__until').map((u) => u.text())).toEqual([
      '13:00 까지',
      '오늘 계속 비어 있어요',
    ])
    await chip(w, '전체').trigger('click')
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
    expect(stats(w).slice(0, 2)).toEqual(['0', '1'])
    expect(w.text()).toContain('지금은 모든 강의실이 사용 중입니다')
    await w.get('.empty button').trigger('click')
    expect(roomNames(w)).toEqual(['101호'])
  })

  it('즐겨찾기 보기 — 비어 있으면 안내, ★ 을 누르면 esc.fav 에 남고 다른 건물은 이름을 붙인다', async () => {
    const { w } = await mountAt(BuildingLayout, '/E', '/:bld')
    await chip(w, '★ 즐겨찾기').trigger('click')
    expect(w.text()).toContain('★ 을 눌러 자주 가는 강의실을 모아두세요')
    await chip(w, '빈 곳').trigger('click')
    await w.findAll('ul.rows > li')[0].get('button').trigger('click')
    expect(localStorage.getItem('esc.fav')).toBe('["E-402"]')
    favorites.value = ['K-101', 'E-402']
    await chip(w, '★ 즐겨찾기').trigger('click')
    expect(w.findAll('ul.rows a').map((a) => a.attributes('href'))).toEqual(['/E/402', '/K/101'])
    expect(w.findAll('ul.rows a')[1].attributes('aria-label')).toBe('운영관 101호 특강 12:00 까지')
  })

  it('지금 보는 강의실 행 — 주간·예약 화면(형제 라우트)에서도 켜진다', async () => {
    const { w } = await mountAt(BuildingLayout, '/E/402/week', '/:bld/:room/week')
    const rows = w.findAll('ul.rows > li')
    expect(rows.map((r) => r.classes().includes('row--current'))).toEqual([true, false])
  })

  it('폰 머리말 — ESC · 학교 · 건물 선택, 인사 줄은 이름과 건물(조사), 지금 시각. 로그아웃은 내 정보로', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-23T01:42:00Z')) // KST 금 10:42
    setSession({
      token: 't',
      role: 'student',
      school_id: 1,
      school_name: '명지전문대학',
      name: '김민준',
    })
    const { w } = await mountAt(BuildingLayout, '/E', '/:bld')
    expect(w.get('.top').text()).toContain('ESC')
    expect(w.get('.top').text()).toContain('명지전문대학')
    expect(w.find('.top select').exists()).toBe(true)
    expect(w.get('.hello').text()).toContain('10월 23일 금요일')
    expect(w.get('.hello').text()).toContain('김민준님, 지금 공학관은')
    expect(w.get('.hello__clock').text()).toBe('10:42')
    // 401 은 10:50 에 바뀐다 — 60분 안이라 곧 비는 곳
    expect(stats(w)).toEqual(['2', '1', '1'])
    expect(w.find('.foot button').exists()).toBe(false)
    expect(session.value?.name).toBe('김민준')
    clearSession()
  })

  it('층 제목 — 빈 곳 · 전체는 호수 앞자리로 묶고, 즐겨찾기는 묶지 않는다', async () => {
    api.rooms.mockResolvedValue([
      roomState({ room_id: 1, room: 501 }),
      roomState({ room_id: 2, room: 401 }),
      roomState({ room_id: 3, room: 402, layout: 1 }),
    ])
    const { w } = await mountAt(BuildingLayout, '/E', '/:bld')
    await chip(w, '전체').trigger('click')
    expect(w.findAll('.floor').map((f) => f.text())).toEqual(['4층', '5층'])
    expect(roomNames(w)).toEqual(['401호', '402호', '501호'])
    favorites.value = ['E-501']
    await chip(w, '★ 즐겨찾기').trigger('click')
    expect(w.find('.floor').exists()).toBe(false)
  })

  it('넓은 폭 — 머리말 · 숫자 칸 없이 개수 제목, /{bld} 는 즐겨찾기 → 빈 곳 첫 강의실을 열어 둔다', async () => {
    stubMedia(true)
    favorites.value = ['E-403']
    const { w, router } = await mountAt(BuildingLayout, '/E', '/:bld')
    expect(router.currentRoute.value.path).toBe('/E/403')
    w.unmount()
    favorites.value = []
    const next = await mountAt(BuildingLayout, '/E/402/week', '/:bld/:room/week')
    expect(next.w.find('.top').exists()).toBe(false)
    expect(next.w.find('.stats').exists()).toBe(false)
    expect(next.w.get('.list__count').text()).toBe('2곳이 지금 비어 있어요')
    const again = await mountAt(BuildingLayout, '/E', '/:bld')
    expect(again.router.currentRoute.value.path).toBe('/E/402')
  })

  it('건물을 바꾸면 보기가 빈 곳으로 돌아온다', async () => {
    const { w } = await mountAt(BuildingLayout, '/E', '/:bld')
    await chip(w, '전체').trigger('click')
    await w.get('select').setValue('K')
    await flushPromises()
    expect(chip(w, '빈 곳').attributes('aria-pressed')).toBe('true')
    expect(w.text()).toContain('지금은 모든 강의실이 사용 중입니다')
  })

  it('다음 예약 — 진행 중인 것 중 가장 이른 것, 누르면 내 예약. 없으면 카드가 없다', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-23T01:42:00Z')) // KST 금 10:42
    api.mine.mockResolvedValue([
      mineResv({ id: 1, date: '2026-10-24', status: 'requested' }),
      mineResv({ id: 2, date: '2026-10-23', s_m: 40, status: 'approved' }), // 10:40 시작 — 창 안
      mineResv({ id: 3, date: '2026-10-20', status: 'rejected' }),
    ])
    const { w } = await mountAt(BuildingLayout, '/E', '/:bld')
    const card = w.get('a.nr')
    expect(card.attributes('href')).toBe('/E/me')
    expect(card.text()).toContain('승인됨')
    expect(card.text()).toContain('지금 체크인할 수 있어요')
    api.mine.mockResolvedValue([])
    const empty = await mountAt(BuildingLayout, '/E', '/:bld')
    expect(empty.w.find('a.nr').exists()).toBe(false)
  })

  it('최근 건물은 글자가 바뀔 때만 적는다 — 폴링마다 쓰지 않는다', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    await mountAt(BuildingLayout, '/E', '/:bld')
    expect(localStorage.getItem('esc.lastBld')).toBe('E')
    localStorage.removeItem('esc.lastBld')
    api.rooms.mockResolvedValue([...ROOMS])
    await vi.advanceTimersByTimeAsync(60_000)
    await flushPromises()
    expect(api.rooms).toHaveBeenCalledTimes(2)
    expect(localStorage.getItem('esc.lastBld')).toBeNull()
  })

  it('쉬는시간·휴강·설정 대기는 예약할 수 없다 — 빈 곳으로 세지도, 칠하지도 않는다', async () => {
    api.rooms.mockResolvedValue([
      roomState({ room_id: 5, room: 501, layout: 2 }),
      roomState({ room_id: 6, room: 502, layout: 3 }),
      roomState({ room_id: 7, room: 503, layout: 8 }),
    ])
    const { w } = await mountAt(BuildingLayout, '/E', '/:bld')
    expect(stats(w).slice(0, 2)).toEqual(['0', '0'])
    await chip(w, '전체').trigger('click')
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
