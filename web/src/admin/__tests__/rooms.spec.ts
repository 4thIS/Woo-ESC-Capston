import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import RoomsView from '@/admin/views/RoomsView.vue'
import { picked, resetSelection } from '@/admin/selection'
import { roomsApi } from '@/api/rooms'
import { loraApi } from '@/api/lora'
import type { BuildingOut, FailedOut, RoomOut, SlotWithRoom } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'
import { ApiError, MESSAGES } from '@/api/client'

vi.mock('@/api/rooms', () => ({
  IMPORT_MAX_BYTES: 1024 * 1024,
  roomsApi: {
    buildings: vi.fn(),
    rooms: vi.fn(),
    buildingSlots: vi.fn(),
    buildingResv: vi.fn(),
    buildingExams: vi.fn(),
    buildingOutbox: vi.fn(),
    putSlot: vi.fn(),
    deleteSlot: vi.fn(),
    saveResv: vi.fn(),
    deleteResv: vi.fn(),
    saveExam: vi.fn(),
    deleteExam: vi.fn(),
    importSlots: vi.fn(),
  },
}))
vi.mock('@/api/lora', () => ({ loraApi: { syncRoom: vi.fn() } }))
vi.mock('@/api/admin', () => ({
  adminApi: {
    pendingResv: vi.fn(async () => []),
    approveResv: vi.fn(),
    rejectResv: vi.fn(),
    cancelResv: vi.fn(),
  },
}))
const api = vi.mocked(roomsApi)
const lora = vi.mocked(loraApi)

const B = (id: number, name: string, bld: string): BuildingOut => ({
  id,
  school_id: 1,
  name,
  bld,
  modem_id: 'm1',
})
const R = (id: number, building_id: number, room: number): RoomOut => ({
  id,
  building_id,
  room,
  units: 1,
  reservable: false,
})
const S = (room_id: number, day: number, s_h: number, subject: string): SlotWithRoom => ({
  id: room_id * 100 + day * 10 + s_h,
  room_id,
  day,
  s_h,
  s_m: 0,
  e_h: s_h + 1,
  e_m: 0,
  type: 1,
  subject,
  professor: '',
  source: 2,
})

// 저장 버튼은 form 속성으로 폼에 붙는다 — 문서 안에 있어야 이어진다(버튼 클릭 = 폼 submit)
let w: VueWrapper
async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:p(.*)*', component: { render: () => null } }],
  })
  await router.push('/rooms')
  w = mount(RoomsView, {
    global: { plugins: [router], stubs: { teleport: true } },
    attachTo: document.body,
  })
  await flushPromises()
}
type Root = VueWrapper | Omit<DOMWrapper<Element>, 'exists'>
const btn = (root: Root, text: string) => root.findAll('button').find((b) => b.text() === text)!
const dialog = (title: string) =>
  w.findAll('[role=dialog]').find((d) => d.get('h2').text() === title)!
const control = (root: Root, label: string) =>
  root
    .findAll('.field, .sel')
    .find(
      (f) => f.find('label').exists() && f.get('label').text().replace('*', '').trim() === label,
    )!
    .get('input, select')
const slotRows = () => w.get('[aria-labelledby=blk-slots]').findAll('tbody tr')

beforeEach(() => {
  resetSelection()
  Object.values(api).forEach((f) => f.mockReset())
  lora.syncRoom.mockReset()
  api.buildings.mockResolvedValue([B(1, '공학관', 'E'), B(2, '사회관', 'S')])
  api.rooms.mockResolvedValue([R(11, 1, 401), R(12, 1, 402), R(13, 1, 501), R(21, 2, 101)])
  api.buildingSlots.mockImplementation(async (b: number) =>
    b === 1 ? [S(11, 1, 9, '캡스톤디자인'), S(13, 2, 10, '운영체제')] : [S(21, 3, 9, '사회학개론')],
  )
  api.buildingResv.mockResolvedValue([])
  api.buildingExams.mockResolvedValue([])
  api.buildingOutbox.mockResolvedValue([])
  for (const t of [...toasts.value]) dismissToast(t.id)
})
afterEach(() => {
  w?.unmount() // picked 는 모듈 상태 — 앞 테스트의 화면이 남아 같이 조회하지 않게
  vi.useRealTimers()
})

describe('강의실 설정 — 트리와 시간표', () => {
  it('첫 진입 — 첫 건물의 첫 층을 고르고 그 방들 슬롯만, 건물 단위로 한 번', async () => {
    await mountView()
    expect(picked.value).toEqual([11, 12])
    expect(w.get('.tree__trigger').text()).toContain('공학관 401 · 402')
    expect(slotRows()).toHaveLength(1)
    expect(slotRows()[0].text()).toContain('캡스톤디자인')
    expect(api.buildingSlots.mock.calls).toEqual([[1]])
  })

  it('같은 건물 안에서 바꾸면 다시 부르지 않고, 다른 건물을 더하면 호수에 건물 글자', async () => {
    await mountView()
    picked.value = [11, 13]
    await flushPromises()
    expect(slotRows()).toHaveLength(2)
    expect(api.buildingSlots).toHaveBeenCalledTimes(1)
    picked.value = [11, 21]
    await flushPromises()
    expect(api.buildingSlots.mock.calls.slice(1)).toEqual([[1], [2]])
    expect(slotRows().map((r) => r.find('td').text())).toEqual(['E 401', 'S 101'])
  })

  it('다 해제하면 "위에서 강의실을 고르세요"', async () => {
    await mountView()
    picked.value = []
    await flushPromises()
    expect(w.get('[aria-labelledby=blk-slots]').text()).toContain('위에서 강의실을 고르세요')
  })

  it('저장하면 대기 점 → 실패로 바뀌면 재전송(방 단위) → 다시 대기', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
    api.putSlot.mockResolvedValue({ outbox_ids: [7], id: null })
    await mountView()
    await btn(w.get('[aria-labelledby=blk-slots]'), '+ 슬롯 추가').trigger('click')
    // 매번 다시 찾는다 — 폼 값이 바뀌면 Modal 안 요소가 새로 그려져 잡아 둔 요소가 떨어진다
    const d = () => dialog('슬롯 추가')
    await control(d(), '요일').setValue('3')
    await control(d(), '시작').setValue('14:00')
    await control(d(), '종료').setValue('15:00')
    await control(d(), '과목명').setValue('자료구조')
    api.buildingSlots.mockImplementation(async () => [
      S(11, 1, 9, '캡스톤디자인'),
      S(11, 3, 14, '자료구조'),
    ])
    await btn(d(), '저장').trigger('click')
    await flushPromises()
    const row = () => slotRows().find((r) => r.text().includes('자료구조'))!
    expect(row().get('.dot').attributes('title')).toBe('대기')
    api.buildingOutbox.mockResolvedValue([
      { id: 7, state: 'failed', last_error: 'max_retries' } as unknown as FailedOut,
    ])
    await vi.advanceTimersByTimeAsync(3_000)
    expect(row().get('.dot').attributes('title')).toBe('실패')
    let done!: (v: { outbox_ids: number[]; id: null }) => void
    lora.syncRoom.mockReturnValue(new Promise((r) => (done = r)))
    api.buildingOutbox.mockResolvedValue([])
    await btn(row(), '재전송').trigger('click')
    // 응답 전 — 버튼이 잠겨 두 번 보내지 않는다
    expect(btn(row(), '재전송').attributes('disabled')).toBeDefined()
    await btn(row(), '재전송').trigger('click')
    expect(lora.syncRoom).toHaveBeenCalledTimes(1)
    done({ outbox_ids: [9], id: null })
    await flushPromises()
    expect(lora.syncRoom).toHaveBeenCalledWith(11)
    expect(row().get('.dot').attributes('title')).toBe('대기')
  })

  it('첫 불러오기 실패 — 빈 시간표로 보이지 않고 다시 불러오기, 누르면 채운다', async () => {
    api.buildingSlots.mockRejectedValueOnce(new ApiError(500, MESSAGES[500]))
    await mountView()
    const blocks = () => w.get('.rooms').text()
    expect(blocks()).not.toContain('등록된 시간표가 없습니다')
    expect(blocks()).not.toContain('등록된 항목이 없습니다')
    await btn(w, '다시 불러오기').trigger('click')
    await flushPromises()
    expect(slotRows()).toHaveLength(1)
    expect(btn(w, '다시 불러오기')).toBeUndefined()
  })

  it('건물·강의실 목록을 불러오는 동안 — "강의실을 고르세요"가 아니라 Skeleton', async () => {
    let done!: (v: RoomOut[]) => void
    api.rooms.mockImplementationOnce(() => new Promise<RoomOut[]>((r) => (done = r)))
    await mountView()
    expect(w.get('.rooms').text()).not.toContain('위에서 강의실을 고르세요')
    expect(slotRows()[0].findComponent({ name: 'Skeleton' }).exists()).toBe(true)
    done([R(11, 1, 401)])
    await flushPromises()
    expect(slotRows()[0].text()).toContain('캡스톤디자인')
  })

  it('건물·강의실 목록 실패 — 빈 트리로 멈추지 않고 다시 불러오기, 누르면 목록부터 다시', async () => {
    api.rooms.mockRejectedValueOnce(new ApiError(500, MESSAGES[500]))
    await mountView()
    expect(w.get('.rooms').text()).not.toContain('위에서 강의실을 고르세요')
    await btn(w, '다시 불러오기').trigger('click')
    await flushPromises()
    expect(api.rooms).toHaveBeenCalledTimes(2)
    expect(slotRows()).toHaveLength(1)
    expect(btn(w, '다시 불러오기')).toBeUndefined()
  })

  it('다시 불러오기도 실패하면 오류 Toast 를 쌓지 않는다 — 처음 한 번', async () => {
    api.buildingSlots.mockImplementation(() => Promise.reject(new ApiError(500, MESSAGES[500])))
    await mountView()
    await btn(w, '다시 불러오기').trigger('click')
    await flushPromises()
    await btn(w, '다시 불러오기').trigger('click')
    await flushPromises()
    expect(toasts.value.filter((t) => t.tone === 'danger')).toHaveLength(1)
  })

  it('아직 안 불러온 건물로 바꾸는 동안 — 빈 시간표가 아니라 불러오는 중', async () => {
    await mountView()
    let done!: (v: SlotWithRoom[]) => void
    api.buildingSlots.mockImplementation(
      (b: number) => new Promise<SlotWithRoom[]>((r) => (b === 2 ? (done = r) : r([]))),
    )
    picked.value = [21]
    await flushPromises()
    expect(w.get('[aria-labelledby=blk-slots]').text()).not.toContain('등록된 시간표가 없습니다')
    expect(w.get('[aria-labelledby=blk-resv]').text()).not.toContain('등록된 항목이 없습니다')
    // 불러오는 동안은 Skeleton 행 — 옛 건물(공학관) 행이 남아 있지도 않다
    expect(
      slotRows()
        .map((r) => r.text())
        .join(),
    ).not.toContain('캡스톤디자인')
    expect(slotRows()[0].findComponent({ name: 'Skeleton' }).exists()).toBe(true)
    done([S(21, 3, 9, '사회학개론')])
    await flushPromises()
    expect(slotRows()[0].text()).toContain('사회학개론')
  })

  it('폼을 열면 최신 슬롯을 다시 읽는다 — 다른 관리자가 넣은 같은 키를 모르고 덮지 않게', async () => {
    await mountView()
    expect(api.buildingSlots).toHaveBeenCalledTimes(1)
    await btn(w.get('[aria-labelledby=blk-slots]'), '+ 슬롯 추가').trigger('click')
    await flushPromises()
    expect(api.buildingSlots).toHaveBeenCalledTimes(2)
    await btn(dialog('슬롯 추가'), '취소').trigger('click')
    await btn(w.get('[aria-labelledby=blk-resv]'), '+ 예약 추가').trigger('click')
    await flushPromises()
    expect(api.buildingResv).toHaveBeenCalledTimes(3)
  })

  it('저장한 행이 요일 필터에 가려지면 필터를 푼다', async () => {
    api.putSlot.mockResolvedValue({ outbox_ids: [7], id: null })
    await mountView()
    const blk = () => w.get('[aria-labelledby=blk-slots]')
    await control(blk(), '요일').setValue('1')
    expect(slotRows()).toHaveLength(1)
    await btn(blk(), '+ 슬롯 추가').trigger('click')
    await flushPromises()
    const d = () => dialog('슬롯 추가')
    await control(d(), '요일').setValue('3')
    await control(d(), '과목명').setValue('자료구조')
    api.buildingSlots.mockImplementation(async () => [
      S(11, 1, 9, '캡스톤디자인'),
      S(11, 3, 9, '자료구조'),
    ])
    await btn(d(), '저장').trigger('click')
    await flushPromises()
    expect(
      slotRows()
        .map((r) => r.text())
        .join(),
    ).toContain('자료구조')
    expect((control(blk(), '요일').element as HTMLSelectElement).selectedIndex).toBe(0)
  })

  it('재전송은 강의실 단위 — 같은 방의 실패 행이 모두 대기로, 도는 동안 그 방 버튼 전부 잠금', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
    await mountView()
    const d = () => dialog('슬롯 추가')
    const blk = () => w.get('[aria-labelledby=blk-slots]')
    for (const [id, day, subject] of [
      [7, '3', '자료구조'],
      [8, '4', '운영체제'],
    ] as const) {
      api.putSlot.mockResolvedValueOnce({ outbox_ids: [id], id: null })
      await btn(blk(), '+ 슬롯 추가').trigger('click')
      await flushPromises()
      await control(d(), '요일').setValue(day)
      await control(d(), '과목명').setValue(subject)
      await btn(d(), '저장').trigger('click')
      await flushPromises()
    }
    api.buildingSlots.mockImplementation(async () => [
      S(11, 1, 9, '캡스톤디자인'),
      S(11, 3, 9, '자료구조'),
      S(11, 4, 9, '운영체제'),
    ])
    await btn(blk(), '+ 슬롯 추가').trigger('click') // 폼을 열면 다시 읽는다 — 새 두 행이 표에
    await flushPromises()
    await btn(d(), '취소').trigger('click')
    api.buildingOutbox.mockResolvedValue([
      { id: 7, state: 'failed', last_error: 'max_retries' },
      { id: 8, state: 'failed', last_error: 'cancelled' },
    ] as unknown as FailedOut[])
    await vi.advanceTimersByTimeAsync(3_000)
    const row = (t: string) => slotRows().find((r) => r.text().includes(t))!
    expect(row('자료구조').get('.dot').attributes('title')).toBe('실패')
    expect(row('운영체제').get('.dot').attributes('title')).toBe('취소됨 — 노드에 반영 안 됨')
    let done!: (v: { outbox_ids: number[]; id: null }) => void
    lora.syncRoom.mockReturnValue(new Promise((r) => (done = r)))
    api.buildingOutbox.mockResolvedValue([])
    await btn(row('자료구조'), '재전송').trigger('click')
    expect(btn(row('운영체제'), '재전송').attributes('disabled')).toBeDefined()
    await btn(row('운영체제'), '재전송').trigger('click')
    expect(lora.syncRoom).toHaveBeenCalledTimes(1)
    done({ outbox_ids: [9], id: null })
    await flushPromises()
    expect(row('자료구조').get('.dot').attributes('title')).toBe('대기')
    expect(row('운영체제').get('.dot').attributes('title')).toBe('대기')
  })

  it('강의실이 하나도 없으면 건물 · 강의실로 보낸다', async () => {
    api.rooms.mockResolvedValue([])
    await mountView()
    expect(w.text()).toContain('강의실이 없습니다. 건물 · 강의실 화면에서 먼저 만드세요.')
  })

  it('선택한 곳 동기화 — 고른 방마다 보내고, 일부 실패는 그 방을 말한다', async () => {
    lora.syncRoom.mockImplementation(async (roomId: number) => {
      if (roomId === 12) throw new ApiError(500, MESSAGES[500])
      return { outbox_ids: [1], id: null }
    })
    await mountView()
    await btn(w, '선택한 곳 동기화').trigger('click')
    await flushPromises()
    expect(lora.syncRoom.mock.calls).toEqual([[11], [12]])
    expect(toasts.value.at(-1)).toMatchObject({
      tone: 'danger',
      message: '2곳 중 1곳 보냄 · 402호 실패',
    })
  })
})
