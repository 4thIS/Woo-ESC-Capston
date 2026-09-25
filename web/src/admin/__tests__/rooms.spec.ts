import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import RoomsView from '@/admin/views/RoomsView.vue'
import { picked } from '@/admin/selection'
import { roomsApi } from '@/api/rooms'
import { loraApi } from '@/api/lora'
import type { BuildingOut, FailedOut, RoomOut, SlotWithRoom } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

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

let w: VueWrapper
async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:p(.*)*', component: { render: () => null } }],
  })
  await router.push('/rooms')
  w = mount(RoomsView, { global: { plugins: [router], stubs: { teleport: true } } })
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
  picked.value = []
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

  it('강의실이 하나도 없으면 건물 · 강의실로 보낸다', async () => {
    api.rooms.mockResolvedValue([])
    await mountView()
    expect(w.text()).toContain('강의실이 없습니다. 건물 · 강의실 화면에서 먼저 만드세요.')
  })
})
