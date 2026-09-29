import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import RangeAddModal from '@/admin/views/master/RangeAddModal.vue'
import { roomsApi } from '@/api/rooms'
import { ApiError, MESSAGES } from '@/api/client'
import type { BuildingOut, RoomOut } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/rooms', () => ({ roomsApi: { createRoom: vi.fn() } }))
const api = vi.mocked(roomsApi)

const building: BuildingOut = { id: 1, school_id: 1, name: '공학관', bld: 'E', modem_id: 'm1' }
const existing: RoomOut[] = [{ id: 13, building_id: 1, room: 503, units: 1, reservable: true }]

let w: VueWrapper
async function mountModal(rooms = existing) {
  w = mount(RangeAddModal, {
    props: { open: true, building, rooms },
    global: { stubs: { teleport: true } },
  })
  await flushPromises()
}
const control = (label: string) =>
  w
    .findAll('.field')
    .find((f) => f.get('label').text().replace('*', '').trim() === label)!
    .get('input')
const chip = (room: number) => w.findAll('button.chip').find((c) => c.text() === String(room))!
const submit = () => w.get('.range__submit')
async function range(a: string, b: string) {
  await control('시작 호수').setValue(a)
  await control('끝 호수').setValue(b)
}

beforeEach(() => {
  api.createRoom.mockReset().mockImplementation(async (r) => ({ id: r.room, ...r }))
  for (const t of [...toasts.value]) dismissToast(t.id)
})

describe('범위로 추가', () => {
  it('이미 있는 호수는 점선·잠김으로 보이고 빠진다 — 칩을 눌러 빼면 라벨이 실제 개수를 말한다', async () => {
    await mountModal()
    await range('501', '505')
    expect(w.text()).toContain('만들어질 방 5곳 중 4곳 · 이미 있는 1곳은 건너뛴다')
    expect(chip(503).classes()).toContain('chip--exists')
    expect((chip(503).element as HTMLButtonElement).disabled).toBe(true)
    expect(submit().text()).toContain('4곳 만들기')
    await chip(505).trigger('click')
    expect(chip(505).attributes('aria-pressed')).toBe('false')
    expect(submit().text()).toContain('3곳 만들기')
  })

  it('한 곳씩 POST(벌크 없음) — 끝나면 모뎀에 설정이 다시 내려갔다고 알리고 닫는다', async () => {
    await mountModal()
    await range('501', '504')
    await submit().trigger('click')
    await flushPromises()
    expect(api.createRoom.mock.calls.map((c) => c[0].room)).toEqual([501, 502, 504])
    expect(api.createRoom.mock.calls[0][0]).toEqual({
      building_id: 1,
      room: 501,
      units: 1,
      reservable: true,
    })
    expect(toasts.value.at(-1)?.message).toBe(
      '3곳을 만들었습니다. 공학관 모뎀Pi 에 설정이 다시 내려갔습니다.',
    )
    expect(w.emitted('changed')).toHaveLength(1)
    expect(w.emitted('close')).toHaveLength(1)
  })

  it('진행 라벨 — n / N 만드는 중', async () => {
    const release: (() => void)[] = []
    api.createRoom.mockImplementation(
      (r) => new Promise((res) => release.push(() => res({ id: r.room, ...r }))),
    )
    await mountModal()
    await range('501', '502')
    await submit().trigger('click')
    await flushPromises()
    expect(w.get('.btn__progress').text()).toBe('0 / 2 만드는 중')
    release[0]()
    await flushPromises()
    expect(w.get('.btn__progress').text()).toBe('1 / 2 만드는 중')
  })

  it('일부 실패 — 되돌리지 않고 실패한 호수만 남겨 재시도, 409(그사이 생김)는 실패가 아니다', async () => {
    api.createRoom.mockImplementation(async (r) => {
      if (r.room === 502) throw new ApiError(500, MESSAGES[500])
      if (r.room === 504) throw new ApiError(409, MESSAGES[409])
      return { id: r.room, ...r }
    })
    await mountModal()
    await range('501', '504')
    await submit().trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)).toMatchObject({
      tone: 'danger',
      message: '3곳 중 2곳 만듦 · 502호 실패',
    })
    expect(w.emitted('close')).toBeUndefined()
    expect(chip(502).classes()).toContain('chip--failed')
    expect(submit().text()).toContain('실패한 1곳 재시도')
    api.createRoom.mockClear()
    api.createRoom.mockImplementation(async (r) => ({ id: r.room, ...r }))
    await submit().trigger('click')
    await flushPromises()
    expect(api.createRoom.mock.calls.map((c) => c[0].room)).toEqual([502])
    expect(w.emitted('close')).toHaveLength(1)
  })

  it('100곳 넘게·거꾸로는 칩 없이 문장, 버튼 잠김', async () => {
    await mountModal()
    await range('101', '201')
    expect(w.text()).toContain('한 번에 100곳까지 만들 수 있습니다')
    expect(w.findAll('button.chip')).toHaveLength(0)
    expect((submit().element as HTMLButtonElement).disabled).toBe(true)
    await range('505', '501')
    expect(w.text()).toContain('끝 호수가 시작 호수보다 작습니다')
  })

  it('모뎀Pi 가 없는 건물 — 문 앞 화면은 갱신되지 않는다고 알린다', async () => {
    w = mount(RangeAddModal, {
      props: { open: true, building: { ...building, modem_id: null }, rooms: [] },
      global: { stubs: { teleport: true } },
    })
    await range('101', '101')
    await submit().trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe(
      '1곳을 만들었습니다. 모뎀Pi 가 배정되지 않아 문 앞 화면은 갱신되지 않습니다.',
    )
  })
})
