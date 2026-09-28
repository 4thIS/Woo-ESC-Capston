import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { RouterView, createMemoryHistory, createRouter } from 'vue-router'
import WeekView from '@/admin/views/WeekView.vue'
import { picked, resetSelection, weekRoom } from '@/admin/selection'
import { roomsApi } from '@/api/rooms'
import { ApiError, MESSAGES } from '@/api/client'
import type { FailedOut, ResvWithRoom, RoomOut, SlotOut } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'
import { loraApi } from '@/api/lora'

vi.mock('@/api/rooms', () => ({
  roomsApi: {
    buildings: vi.fn(),
    rooms: vi.fn(),
    slots: vi.fn(),
    reservations: vi.fn(),
    exams: vi.fn(),
    buildingOutbox: vi.fn(),
    putSlot: vi.fn(),
    deleteSlot: vi.fn(),
    saveResv: vi.fn(),
  },
}))
vi.mock('@/api/lora', () => ({ loraApi: { syncRoom: vi.fn() } }))
const api = vi.mocked(roomsApi)

const R = (id: number, room: number): RoomOut => ({
  id,
  building_id: 1,
  room,
  units: 1,
  reservable: true,
})
const S = (o: Partial<SlotOut>): SlotOut => ({
  id: 1,
  day: 1,
  s_h: 10,
  s_m: 0,
  e_h: 12,
  e_m: 0,
  type: 1,
  subject: '캡스톤디자인',
  professor: '김교수',
  source: 2,
  ...o,
})
const V = (o: Partial<ResvWithRoom>): ResvWithRoom => ({
  id: 7,
  room_id: 11,
  date: '2026-09-21',
  s_h: 11,
  s_m: 0,
  e_h: 12,
  e_m: 0,
  type: 5,
  subject: '특강',
  professor: '학생처',
  status: 'approved',
  requester: null,
  pushed_at: new Date(),
  ...o,
})

// 저장 버튼은 form 속성으로 폼에 붙는다 — 문서 안에 있어야 이어진다(버튼 클릭 = 폼 submit)
let w: VueWrapper
async function mountAt(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/week', component: WeekView },
      { path: '/rooms/:roomId(\\d+)/week', component: WeekView, props: true },
      { path: '/:p(.*)*', component: { render: () => null } },
    ],
  })
  await router.push(path)
  await router.isReady()
  w = mount(
    { render: () => h(RouterView) },
    { global: { plugins: [router], stubs: { teleport: true } }, attachTo: document.body },
  )
  await flushPromises()
  return router
}
type Root = VueWrapper | DOMWrapper<Element>
const btn = (root: Root, text: string) => root.findAll('button').find((b) => b.text() === text)!
const dialog = (title: string) =>
  w.findAll('[role=dialog]').find((d) => d.get('h2').text() === title)
const control = (root: Root, label: string) =>
  root
    .findAll('.field, .sel')
    .find(
      (f) => f.find('label').exists() && f.get('label').text().replace('*', '').trim() === label,
    )!
    .get('input, select')
const labels = () => w.findAll('.wk__block .wk__label').map((l) => l.text())
const check = (label: string) =>
  w
    .findAll('.cb')
    .find((c) => c.text() === label)!
    .get('input')

beforeEach(() => {
  // KST 2026-09-25(금) 12:00 — 이번 주 월요일 9/21
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-09-25T03:00:00Z'))
  resetSelection()
  Object.values(api).forEach((f) => f.mockReset())
  api.buildings.mockResolvedValue([
    { id: 1, school_id: 1, name: '공학관', bld: 'E', modem_id: 'm1' },
  ])
  api.rooms.mockResolvedValue([R(11, 401), R(12, 402)])
  api.slots.mockResolvedValue([S({})])
  api.reservations.mockResolvedValue([
    V({}),
    V({
      id: 8,
      date: '2026-09-22',
      s_h: 13,
      e_h: 14,
      type: 6,
      subject: '스터디',
      status: 'requested',
      requester: { email: 's@mjc.ac.kr', name: '김민준', student_no: '1' },
    }),
    V({ id: 9, subject: '거절됨', status: 'rejected' }),
  ])
  api.exams.mockResolvedValue([{ id: 1, date_start: '2026-09-23', date_end: '2026-09-24' }])
  api.buildingOutbox.mockResolvedValue([])
  for (const t of [...toasts.value]) dismissToast(t.id)
})
afterEach(() => {
  w?.unmount()
  vi.useRealTimers()
})

describe('주간 시간표', () => {
  it('/week — 마지막 강의실 → 트리 첫 방 → 첫 강의실로 바꿔 간다', async () => {
    picked.value = [12]
    let router = await mountAt('/week')
    expect(router.currentRoute.value.path).toBe('/rooms/12/week')
    expect(weekRoom.value).toBe(12)
    w.unmount()
    weekRoom.value = null
    picked.value = []
    router = await mountAt('/week')
    expect(router.currentRoute.value.path).toBe('/rooms/11/week')
  })

  it('블록 — 슬롯은 유형 라벨, 예약은 "예약 · ", 신청은 "신청 · " 점선, 겹친 구간에 막대 하나, 시험기간 띠', async () => {
    await mountAt('/rooms/11/week')
    expect(w.get('.tree__trigger').text()).toContain('공학관 401호')
    expect(w.get('.wk__range').text()).toBe('9/21~9/27')
    expect(labels()).toEqual(['수업중', '예약 · 특강', '신청 · 대여중'])
    const requested = w.findAll('.wk__block').find((b) => b.text().includes('스터디'))!
    expect(requested.classes()).toContain('wk__block--requested')
    expect(w.findAll('.wk__overlap-label').map((l) => l.text())).toEqual(['겹침 11:00–12:00'])
    const heads = w.findAll('.wk__head').map((x) => x.text())
    expect(heads[2]).toContain('시험기간')
    expect(heads[3]).toContain('시험기간')
    expect(heads[0]).not.toContain('시험기간')
  })

  it('빈 칸을 누르면 그 요일·시각으로 슬롯 추가 — 종료는 +1시간', async () => {
    await mountAt('/rooms/11/week')
    await w.get('button[aria-label="수 14:00 슬롯 추가"]').trigger('click')
    const d = dialog('슬롯 추가')!
    expect((control(d, '요일').element as HTMLSelectElement).value).toBe('3')
    expect((control(d, '시작').element as HTMLInputElement).value).toBe('14:00')
    expect((control(d, '종료').element as HTMLInputElement).value).toBe('15:00')
  })

  it('주 이동은 서버를 다시 부르지 않는다 — 시간표는 그대로, 예약만 다시 걸러진다', async () => {
    await mountAt('/rooms/11/week')
    await w.get('button[aria-label="다음 주"]').trigger('click')
    expect(w.get('.wk__range').text()).toBe('9/28~10/4')
    expect(labels()).toEqual(['수업중'])
    expect(w.findAll('.wk__overlap-label')).toHaveLength(0)
    expect(api.slots).toHaveBeenCalledTimes(1)
    expect(api.reservations).toHaveBeenCalledTimes(1)
  })

  it('야간·주말 — 필요한 블록이 있으면 켠 채 시작, 사용자가 끄면 그 선택을 유지', async () => {
    api.slots.mockResolvedValue([S({}), S({ id: 2, day: 6, s_h: 19, e_h: 20, e_m: 30 })])
    await mountAt('/rooms/11/week')
    expect((check('야간').element as HTMLInputElement).checked).toBe(true)
    expect((check('주말').element as HTMLInputElement).checked).toBe(true)
    expect(w.findAll('.wk__time')).toHaveLength(26)
    expect(w.findAll('.wk__head')).toHaveLength(7)
    await check('야간').setValue(false)
    expect(w.findAll('.wk__time')).toHaveLength(18)
    w.unmount()
    await mountAt('/rooms/11/week')
    expect((check('야간').element as HTMLInputElement).checked).toBe(false)
  })

  it('다른 학교·없는 강의실(404) — "찾을 수 없습니다", 오류 Toast 없음', async () => {
    api.slots.mockRejectedValue(new ApiError(404, MESSAGES[404]))
    api.reservations.mockRejectedValue(new ApiError(404, MESSAGES[404]))
    api.exams.mockRejectedValue(new ApiError(404, MESSAGES[404]))
    await mountAt('/rooms/99/week')
    expect(w.text()).toContain('강의실을 찾을 수 없습니다. 위에서 다른 강의실을 고르세요.')
    expect(toasts.value).toHaveLength(0)
  })

  it('시간표가 없으면 격자는 두고 가운데 안내', async () => {
    api.slots.mockResolvedValue([])
    api.reservations.mockResolvedValue([])
    await mountAt('/rooms/11/week')
    expect(w.findAll('.wk__cell').length).toBeGreaterThan(0)
    expect(w.text()).toContain('이 강의실에 등록된 시간표가 없습니다')
  })

  it('슬롯을 누르면 수정 폼 — 거기서 삭제(확인), 신청 블록은 열지 않는다', async () => {
    await mountAt('/rooms/11/week')
    await w
      .findAll('.wk__block')
      .find((b) => b.text().includes('스터디'))!
      .trigger('click')
    expect(w.findAll('[role=dialog]')).toHaveLength(0)
    await w
      .findAll('.wk__block')
      .find((b) => b.text().includes('캡스톤디자인'))!
      .trigger('click')
    await btn(dialog('슬롯 수정')!, '삭제').trigger('click')
    const c = dialog('슬롯 삭제')!
    expect(c.text()).toContain('401호 월 10:00 캡스톤디자인')
  })

  it('첫 불러오기 실패 — 빈 시간표로 보이지 않고 오류 안내 + 다시 불러오기', async () => {
    api.slots.mockRejectedValueOnce(new ApiError(500, MESSAGES[500]))
    await mountAt('/rooms/11/week')
    expect(w.text()).not.toContain('이 강의실에 등록된 시간표가 없습니다')
    expect(w.text()).toContain('시간표·예약·시험기간을 불러오지 못했습니다')
    await btn(w, '다시 불러오기').trigger('click')
    await flushPromises()
    expect(labels()).toEqual(['수업중', '예약 · 특강', '신청 · 대여중'])
  })

  it('강의실을 바꾸면 새 방을 불러오는 동안 옛 방의 블록을 그리지 않는다', async () => {
    const router = await mountAt('/rooms/11/week')
    expect(labels()).toHaveLength(3)
    let done!: (v: SlotOut[]) => void
    api.slots.mockReturnValueOnce(new Promise((r) => (done = r)))
    await router.push('/rooms/12/week')
    await flushPromises()
    expect(w.findAll('.wk__block')).toHaveLength(0)
    expect(w.find('.wk__overlay .sk').exists()).toBe(true)
    done([S({ subject: '운영체제' })])
    await flushPromises()
    expect(w.findAll('.wk__block').map((b) => b.text())).toEqual(
      expect.arrayContaining([expect.stringContaining('운영체제')]),
    )
  })

  it('폼을 열면 슬롯을 다시 불러 겹침 검사가 최신 목록을 본다', async () => {
    await mountAt('/rooms/11/week')
    expect(api.slots).toHaveBeenCalledTimes(1)
    await w.get('button[aria-label="수 14:00 슬롯 추가"]').trigger('click')
    await flushPromises()
    expect(api.slots).toHaveBeenCalledTimes(2)
  })

  it('재전송은 블록 밖 형제 — Enter 가 편집을 열지 않고, 누르면 방 단위 재전송', async () => {
    vi.useRealTimers() // beforeEach 가 Date 만 속였다 — 폴링 타이머까지 다시 건다
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
    vi.setSystemTime(new Date('2026-09-25T03:00:00Z'))
    api.putSlot.mockResolvedValue({ outbox_ids: [7], id: null })
    vi.mocked(loraApi.syncRoom)
      .mockReset()
      .mockResolvedValue({ outbox_ids: [9], id: null })
    await mountAt('/rooms/11/week')
    await w.get('button[aria-label="수 14:00 슬롯 추가"]').trigger('click')
    await flushPromises()
    const d = () => dialog('슬롯 추가')!
    await control(d(), '과목명').setValue('자료구조')
    api.slots.mockResolvedValue([
      S({}),
      S({ id: 2, day: 3, s_h: 14, e_h: 15, subject: '자료구조' }),
    ])
    await btn(d(), '저장').trigger('click')
    await flushPromises()
    api.buildingOutbox.mockResolvedValue([
      { id: 7, state: 'failed', last_error: 'max_retries' } as unknown as FailedOut,
    ])
    await vi.advanceTimersByTimeAsync(3_000)
    const again = w.findAll('button').find((b) => b.text() === '재전송')!
    expect(again.element.closest('.wk__block')).toBeNull()
    await again.trigger('keydown', { key: 'Enter' })
    expect(w.findAll('[role=dialog]')).toHaveLength(0)
    await again.trigger('click')
    await flushPromises()
    expect(loraApi.syncRoom).toHaveBeenCalledWith(11)
    expect(w.findAll('[role=dialog]')).toHaveLength(0)
  })

  it('블록은 Space 로도 열리고, 무엇인지 말하는 이름이 있다', async () => {
    await mountAt('/rooms/11/week')
    const b = w.get('.wk__block[aria-label="월 10:00–12:00 수업중 캡스톤디자인"]')
    await b.trigger('keydown', { key: ' ' })
    expect(dialog('슬롯 수정')).toBeTruthy()
  })

  it('없는 강의실 주소는 마지막 강의실로 기억하지 않는다', async () => {
    await mountAt('/rooms/99/week')
    expect(weekRoom.value).toBeNull()
  })

  it('404 강의실에서 있는 강의실로 옮기면 불러오는 동안 "찾을 수 없습니다"가 아니라 로딩', async () => {
    api.slots.mockRejectedValueOnce(new ApiError(404, MESSAGES[404]))
    const router = await mountAt('/rooms/99/week')
    expect(w.text()).toContain('강의실을 찾을 수 없습니다')
    api.slots.mockReturnValueOnce(new Promise(() => {}))
    await router.push('/rooms/11/week')
    await flushPromises()
    expect(w.text()).not.toContain('강의실을 찾을 수 없습니다')
    expect(w.find('.wk__overlay .sk').exists()).toBe(true)
  })

  it('주 라벨을 누르면 이번 주로', async () => {
    await mountAt('/rooms/11/week')
    await w.get('button[aria-label="다음 주"]').trigger('click')
    await w.get('button[aria-label="다음 주"]').trigger('click')
    expect(w.get('.wk__range').text()).toBe('10/5~10/11')
    expect(w.get('.wk__range').attributes('title')).toBe('이번 주로')
    await w.get('.wk__range').trigger('click')
    expect(w.get('.wk__range').text()).toBe('9/21~9/27')
  })
})
