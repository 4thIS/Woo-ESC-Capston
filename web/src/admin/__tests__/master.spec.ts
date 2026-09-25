import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import MasterView from '@/admin/views/MasterView.vue'
import { roomsApi } from '@/api/rooms'
import { loraApi } from '@/api/lora'
import { adminApi } from '@/api/admin'
import { ApiError, MESSAGES } from '@/api/client'
import type { BuildingOut, FailedOut, ModemOut, RoomOut } from '@/api/types'
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

const B = (id: number, name: string, bld: string, modem_id: string | null = null): BuildingOut => ({
  id,
  school_id: 1,
  name,
  bld,
  modem_id,
})
const R = (id: number, building_id: number, room: number): RoomOut => ({
  id,
  building_id,
  room,
  units: 1,
  reservable: true,
})
const M = (modem_id: string): ModemOut => ({
  modem_id,
  agent_ver: null,
  modem_fw: null,
  last_seen_at: null,
  connected: false,
  school_id: 1,
})

let w: VueWrapper
// teleport 스텁은 갱신마다 슬롯을 다시 그린다 — dialog 를 매번 다시 찾는다 (users.spec 과 같다)
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
const row = (name: string) => w.findAll('tbody tr').find((r) => r.text().includes(name))!

beforeEach(() => {
  Object.values(rooms).forEach((f) => f.mockReset())
  rooms.buildings.mockResolvedValue([B(1, '공학관', 'E', 'm1'), B(2, '사회관', 'S')])
  rooms.rooms.mockResolvedValue([R(11, 1, 401), R(12, 1, 402)])
  rooms.createBuilding.mockResolvedValue(B(3, '도서관', 'L'))
  rooms.patchBuilding.mockResolvedValue(B(1, '공학관', 'E', 'm2'))
  rooms.deleteBuilding.mockResolvedValue({ ok: true })
  lora.modems.mockResolvedValue([M('m1'), M('m2')])
  admin.nodes.mockResolvedValue([])
  setSession({ token: 't', role: 'admin', school_id: 1, name: '관리자1' })
  for (const t of [...toasts.value]) dismissToast(t.id)
})

describe('건물 패널', () => {
  it('n / 26, 미배정은 적색 테두리 배지, 첫 건물이 골라져 있다', async () => {
    await mountView()
    expect(w.get('#master-bld').text()).toBe('건물')
    expect(w.text()).toContain('2 / 26')
    const badge = row('사회관').get('.badge')
    expect(badge.text()).toBe('미배정')
    expect(badge.classes()).toEqual(expect.arrayContaining(['badge--danger', 'badge--outline']))
    expect(btn(row('공학관'), '공학관').attributes('aria-pressed')).toBe('true')
  })

  it('추가 — 친 글자는 대문자로, school_id 는 로그인 응답의 것', async () => {
    await mountView()
    await btn(w, '+ 건물').trigger('click')
    const d = () => dialog('건물 추가')!
    await control(d(), '이름').setValue('도서관')
    await control(d(), '글자').setValue('l')
    expect((control(d(), '글자').element as HTMLInputElement).value).toBe('L')
    await btn(d(), '저장').trigger('click')
    await flushPromises()
    expect(rooms.createBuilding).toHaveBeenCalledWith({
      school_id: 1,
      name: '도서관',
      bld: 'L',
      modem_id: null,
    })
    expect(dialog('건물 추가')).toBeUndefined()
    expect(rooms.buildings).toHaveBeenCalledTimes(2)
  })

  it('이 학교가 쓰는 글자는 저장 전에 막는다 — 쓰는 중 글자를 적어 둔다', async () => {
    await mountView()
    await btn(w, '+ 건물').trigger('click')
    const d = () => dialog('건물 추가')!
    expect(d().text()).toContain('쓰는 중: E S')
    await control(d(), '이름').setValue('별관')
    await control(d(), '글자').setValue('e')
    await btn(d(), '저장').trigger('click')
    await flushPromises()
    expect(rooms.createBuilding).not.toHaveBeenCalled()
    expect(d().text()).toContain('이 학교가 이미 쓰는 글자입니다.')
  })

  it('다른 학교가 쓰는 글자는 409 — Toast 가 아니라 글자 칸에, 나머지 입력은 그대로', async () => {
    rooms.createBuilding.mockRejectedValue(
      new ApiError(409, MESSAGES[409], [], {
        detail: "bld 'Z' 는 다른 학교가 쓰고 있습니다 (공중 주소는 전역)",
      }),
    )
    await mountView()
    await btn(w, '+ 건물').trigger('click')
    const d = () => dialog('건물 추가')!
    await control(d(), '이름').setValue('타학교관')
    await control(d(), '글자').setValue('z')
    await btn(d(), '저장').trigger('click')
    await flushPromises()
    expect(dialog('건물 추가')!.text()).toContain(
      '다른 학교가 이미 쓰는 글자입니다. 다른 글자를 고르세요.',
    )
    expect((control(dialog('건물 추가')!, '이름').element as HTMLInputElement).value).toBe(
      '타학교관',
    )
    expect(toasts.value).toHaveLength(0)
  })

  it('강의실이 있는 건물은 글자 칸이 읽기 전용 — 바꾸는 길을 적는다', async () => {
    await mountView()
    await btn(row('공학관'), '수정').trigger('click')
    const d = () => dialog('건물 수정')!
    expect(control(d(), '글자').attributes('readonly')).toBeDefined()
    expect(d().text()).toContain('강의실이 있는 건물은 글자를 바꿀 수 없습니다.')
  })

  it('모뎀이 바뀌면 대기 건수로 확인 — 확인해야 modem_id 만 보낸다', async () => {
    rooms.buildingOutbox.mockResolvedValue(Array.from({ length: 7 }, () => ({}) as FailedOut))
    await mountView()
    await btn(row('공학관'), '수정').trigger('click')
    const d = () => dialog('건물 수정')!
    await control(d(), '모뎀').setValue('m2')
    await btn(d(), '저장').trigger('click')
    await flushPromises()
    expect(rooms.buildingOutbox).toHaveBeenCalledWith(1, 'queued')
    const c = dialog('모뎀 변경')!
    expect(c.text()).toContain(
      '대기 중 7건이 m2 로 옮겨집니다. 옛 모뎀(m1)과 새 모뎀 양쪽이 설정을 다시 받습니다.',
    )
    expect(rooms.patchBuilding).not.toHaveBeenCalled()
    await btn(c, '바꾸기').trigger('click')
    await flushPromises()
    expect(rooms.patchBuilding).toHaveBeenCalledWith(1, { modem_id: 'm2' })
    expect(dialog('모뎀 변경')).toBeUndefined()
    expect(dialog('건물 수정')).toBeUndefined()
  })

  it('이름만 바꾸면 묻지 않는다', async () => {
    await mountView()
    await btn(row('공학관'), '수정').trigger('click')
    const d = () => dialog('건물 수정')!
    await control(d(), '이름').setValue('공학1관')
    await btn(d(), '저장').trigger('click')
    await flushPromises()
    expect(dialog('모뎀 변경')).toBeUndefined()
    expect(rooms.buildingOutbox).not.toHaveBeenCalled()
    expect(rooms.patchBuilding).toHaveBeenCalledWith(1, { name: '공학1관' })
  })

  it('삭제 — 강의실이 있으면 잠기고 이유는 툴팁, 없으면 확인 뒤 지운다', async () => {
    await mountView()
    const locked = btn(row('공학관'), '삭제')
    expect((locked.element as HTMLButtonElement).disabled).toBe(true)
    expect(locked.element.parentElement!.getAttribute('title')).toBe('강의실을 먼저 지우세요 (2곳)')
    await btn(row('사회관'), '삭제').trigger('click')
    const c = dialog('건물 삭제')!
    expect(c.text()).toContain('사회관(S) 건물을 지웁니다.')
    await btn(c, '삭제').trigger('click')
    await flushPromises()
    expect(rooms.deleteBuilding).toHaveBeenCalledWith(2)
  })

  it('26개면 + 건물 잠금, 0개면 설치 순서 안내', async () => {
    rooms.buildings.mockResolvedValue(
      Array.from({ length: 26 }, (_, i) => B(i + 1, `건물${i}`, String.fromCharCode(65 + i))),
    )
    await mountView()
    expect((btn(w, '+ 건물').element as HTMLButtonElement).disabled).toBe(true)
    w.unmount()
    rooms.buildings.mockResolvedValue([])
    rooms.rooms.mockResolvedValue([])
    await mountView()
    expect(w.text()).toContain('건물을 먼저 만드세요')
    expect(w.text()).toContain('강의실을 범위로 추가합니다.')
  })
})
