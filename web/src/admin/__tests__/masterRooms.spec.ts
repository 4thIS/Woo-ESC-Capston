import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import MasterView from '@/admin/views/MasterView.vue'
import { roomsApi } from '@/api/rooms'
import { loraApi } from '@/api/lora'
import { adminApi } from '@/api/admin'
import { ApiError, MESSAGES } from '@/api/client'
import type { NodeOut, ResvWithRoom, RoomOut, SlotWithRoom } from '@/api/types'
import { setSession } from '@/lib/session'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/rooms', () => ({
  roomsApi: {
    buildings: vi.fn(),
    rooms: vi.fn(),
    createBuilding: vi.fn(),
    patchBuilding: vi.fn(),
    deleteBuilding: vi.fn(),
    buildingOutbox: vi.fn(),
    createRoom: vi.fn(),
    patchRoom: vi.fn(),
    deleteRoom: vi.fn(),
    buildingSlots: vi.fn(),
    buildingResv: vi.fn(),
    buildingExams: vi.fn(),
  },
}))
vi.mock('@/api/lora', () => ({ loraApi: { modems: vi.fn() } }))
vi.mock('@/api/admin', () => ({ adminApi: { nodes: vi.fn() } }))
const rooms = vi.mocked(roomsApi)
const lora = vi.mocked(loraApi)
const admin = vi.mocked(adminApi)

const R = (id: number, room: number, o: Partial<RoomOut> = {}): RoomOut => ({
  id,
  building_id: 1,
  room,
  units: 1,
  reservable: false,
  ...o,
})
const N = (room_id: number, room: number, unit: number, o: Partial<NodeOut> = {}): NodeOut => ({
  room_id,
  building_id: 1,
  building: '공학관',
  bld: 'E',
  room,
  unit,
  modem_id: 'm1',
  mac: null,
  fw: null,
  batt_mv: null,
  rssi: null,
  snr: null,
  sched_ver: null,
  resv_ver: null,
  exam_ver: null,
  ident_ver: null,
  layout: null,
  clock_stale: false,
  low_batt: false,
  uptime_h: null,
  last_seen_at: null,
  last_ack_at: null,
  last_status_at: null,
  sync_state: 'unknown',
  warnings: [],
  ...o,
})

let w: VueWrapper
async function mountView() {
  w = mount(MasterView, { global: { stubs: { teleport: true } } })
  await flushPromises()
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
const panel = () => w.find('[aria-labelledby=master-room]')
const row = (room: number) =>
  panel()
    .findAll('tbody tr')
    .find((r) => r.find('td').text() === String(room))!

beforeEach(() => {
  Object.values(rooms).forEach((f) => f.mockReset())
  rooms.buildings.mockResolvedValue([
    { id: 1, school_id: 1, name: '공학관', bld: 'E', modem_id: 'm1' },
  ])
  rooms.rooms.mockResolvedValue([
    R(11, 401, { reservable: true }),
    R(12, 402, { units: 2 }),
    R(13, 5),
  ])
  rooms.createRoom.mockResolvedValue(R(14, 403))
  rooms.patchRoom.mockResolvedValue(R(12, 402))
  rooms.deleteRoom.mockResolvedValue({ ok: true })
  lora.modems.mockResolvedValue([])
  const seen = new Date()
  admin.nodes.mockResolvedValue([
    N(11, 401, 1, { mac: 'AA', last_seen_at: seen, batt_mv: 3980 }),
    N(12, 402, 1, { mac: 'BB', last_seen_at: seen, batt_mv: 3700 }),
    N(12, 402, 2, { warnings: ['unseen'] }),
    N(13, 5, 1, { warnings: ['unseen'] }),
  ])
  setSession({ token: 't', role: 'admin', school_id: 1, name: '관리자1' })
  for (const t of [...toasts.value]) dismissToast(t.id)
})

describe('강의실 패널', () => {
  it('헤더에 곳 수·학생 웹에 보이는 곳, 층은 호수 ÷ 100, 노드 칸은 서버 판정 문구', async () => {
    await mountView()
    expect(panel().get('h2').text()).toBe('공학관 강의실')
    expect(panel().text()).toContain('3곳 · 학생 웹에 보이는 곳 1')
    expect(row(401).text()).toContain('4층')
    expect(row(401).text()).toContain('연결됨 · 3.98 V')
    expect(row(402).text()).toContain('응답 없음')
    expect(row(5).text()).toContain('기타')
    expect(row(5).text()).toContain('단말 없음')
  })

  it('학생 예약 체크박스는 누르는 즉시 부분 PATCH — 응답 전에도 누른 값을 보인다', async () => {
    rooms.patchRoom.mockReturnValue(new Promise(() => {}))
    await mountView()
    await row(402).get('input[type=checkbox]').setValue(true)
    expect(rooms.patchRoom).toHaveBeenCalledWith(12, { reservable: true })
    expect(row(402).text()).toContain('받음')
    expect(panel().text()).toContain('학생 웹에 보이는 곳 2')
    expect((row(402).get('input[type=checkbox]').element as HTMLInputElement).disabled).toBe(true)
  })

  it('실패하면 체크를 되돌리고 Toast', async () => {
    rooms.patchRoom.mockRejectedValue(new ApiError(500, MESSAGES[500]))
    await mountView()
    await row(402).get('input[type=checkbox]').setValue(true)
    await flushPromises()
    expect(row(402).text()).toContain('안 받음')
    expect(toasts.value.at(-1)).toMatchObject({
      tone: 'danger',
      message: '402호 학생 예약 설정을 바꾸지 못했습니다.',
    })
  })

  it('학교 전체에 받는 방이 0곳이면 Banner', async () => {
    rooms.rooms.mockResolvedValue([R(11, 401), R(12, 402)])
    await mountView()
    expect(w.text()).toContain('학생 예약을 받는 강의실이 없습니다. 학생 웹 목록이 비어 있습니다.')
  })

  it('한 곳 추가 — 호수 범위·중복은 저장 전에, 층 입력 칸은 없다', async () => {
    await mountView()
    await btn(panel(), '+ 강의실').trigger('click')
    const d = () => dialog('강의실 추가')!
    expect(d().text()).not.toContain('층')
    await control(d(), '호수').setValue('401')
    await btn(d(), '저장').trigger('click')
    expect(d().text()).toContain('이미 있는 호수입니다')
    await control(d(), '호수').setValue('10000')
    await btn(d(), '저장').trigger('click')
    expect(d().text()).toContain('호수는 1~9999 정수입니다')
    expect(rooms.createRoom).not.toHaveBeenCalled()
    await control(d(), '호수').setValue('403')
    await btn(d(), '저장').trigger('click')
    await flushPromises()
    expect(rooms.createRoom).toHaveBeenCalledWith({
      building_id: 1,
      room: 403,
      units: 1,
      reservable: false,
    })
  })

  it('수정 — 호수는 읽기 전용, 유닛 2→1 만 묻고(단말을 떼라), 늘리는 쪽은 묻지 않는다', async () => {
    await mountView()
    await btn(row(402), '수정').trigger('click')
    const d = () => dialog('강의실 수정')!
    expect(control(d(), '호수').attributes('readonly')).toBeDefined()
    expect(d().text()).toContain(
      '호수를 바꾸려면 강의실을 지우고 다시 만든 뒤, 문 앞 단말을 다시 등록하세요.',
    )
    await control(d(), '유닛').setValue('1')
    await btn(d(), '저장').trigger('click')
    const c = dialog('유닛 줄이기')!
    expect(c.text()).toContain('402호의 2번 단말이 목록에서 사라집니다. 벽에서 떼어 주세요.')
    expect(rooms.patchRoom).not.toHaveBeenCalled()
    await btn(c, '줄이기').trigger('click')
    await flushPromises()
    expect(rooms.patchRoom).toHaveBeenCalledWith(12, { units: 1 })
    rooms.patchRoom.mockClear()
    await btn(row(401), '수정').trigger('click')
    await control(dialog('강의실 수정')!, '유닛').setValue('2')
    await btn(dialog('강의실 수정')!, '저장').trigger('click')
    await flushPromises()
    expect(dialog('유닛 줄이기')).toBeUndefined()
    expect(rooms.patchRoom).toHaveBeenCalledWith(11, { units: 2 })
  })

  it('삭제 — 함께 지워질 개수와 단말을 적는다 (이름 입력은 요구하지 않는다)', async () => {
    rooms.buildingSlots.mockResolvedValue([{ room_id: 11 }, { room_id: 11 }] as SlotWithRoom[])
    rooms.buildingResv.mockResolvedValue([
      { room_id: 11, status: 'approved' },
      { room_id: 11, status: 'cancelled' },
    ] as ResvWithRoom[])
    rooms.buildingExams.mockResolvedValue([])
    await mountView()
    await btn(row(401), '삭제').trigger('click')
    await flushPromises()
    const c = dialog('강의실 삭제')!
    expect(c.findAll('p').map((p) => p.text())).toEqual([
      '공학관 401호를 지웁니다.',
      '시간표 2건 · 예약 1건이 함께 지워집니다.',
      '문 앞 단말(unit 1)은 갱신을 받지 못하게 됩니다.',
    ])
    expect(c.find('input').exists()).toBe(false)
    await btn(c, '삭제').trigger('click')
    await flushPromises()
    expect(rooms.deleteRoom).toHaveBeenCalledWith(11)
  })
})
