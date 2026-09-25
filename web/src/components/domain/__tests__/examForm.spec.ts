import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ExamForm from '@/components/domain/ExamForm.vue'
import Modal from '@/components/ui/Modal.vue'
import { roomsApi } from '@/api/rooms'
import { ApiError, MESSAGES } from '@/api/client'
import type { Enqueued, RoomOut } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/rooms', () => ({ roomsApi: { saveExam: vi.fn() } }))
const api = vi.mocked(roomsApi)

const R = (id: number, room: number): RoomOut => ({
  id,
  building_id: 1,
  room,
  units: 1,
  reservable: false,
})
const rooms = [R(11, 401), R(12, 402), R(13, 405)]
const body = { date_start: '2026-10-19', date_end: '2026-10-23' }

let w: VueWrapper
async function mountForm(props: Record<string, unknown> = {}) {
  w = mount(ExamForm, {
    props: { open: true, rooms, ...props },
    global: { stubs: { teleport: true } },
  })
  await flushPromises()
}
const control = (label: string) =>
  w
    .findAll('.field')
    .find((f) => f.get('label').text().replace('*', '').trim() === label)!
    .get('input')
const submit = () => w.get('.form__submit').trigger('click')
async function fill() {
  await control('시작일').setValue(body.date_start)
  await control('종료일').setValue(body.date_end)
}

beforeEach(() => {
  api.saveExam
    .mockReset()
    .mockImplementation(async (roomId: number) => ({ outbox_ids: [roomId * 10], id: roomId + 100 }))
  for (const t of [...toasts.value]) dismissToast(t.id)
})

describe('ExamForm', () => {
  it('고른 방마다 id 없이 POST (서버 채번) — 방마다 saved, 끝나면 done·close·Toast', async () => {
    await mountForm()
    expect(w.get('.form__submit').text()).toContain('선택한 3곳에 기간 추가')
    await fill()
    await submit()
    await flushPromises()
    expect(api.saveExam.mock.calls).toEqual([
      [11, body],
      [12, body],
      [13, body],
    ])
    expect(w.emitted('saved')!.map((e) => e[0])).toEqual([
      { roomId: 11, key: 'x111', outboxIds: [110] },
      { roomId: 12, key: 'x112', outboxIds: [120] },
      { roomId: 13, key: 'x113', outboxIds: [130] },
    ])
    expect(w.emitted('done')).toHaveLength(1)
    expect(w.emitted('close')).toHaveLength(1)
    expect(toasts.value.at(-1)?.message).toBe('3곳에 시험기간을 넣었습니다.')
  })

  it('진행 라벨 — 한 곳이 끝날 때마다 n/3, 진행 중에는 닫히지 않는다', async () => {
    const release: (() => void)[] = []
    api.saveExam.mockImplementation(
      () => new Promise<Enqueued>((res) => release.push(() => res({ outbox_ids: [1], id: 5 }))),
    )
    await mountForm()
    await fill()
    await submit()
    await flushPromises()
    expect(w.get('.btn__progress').text()).toBe('0/3 적용 중')
    expect(w.findComponent(Modal).props('closeOnBackdrop')).toBe(false)
    release[0]()
    await flushPromises()
    expect(w.get('.btn__progress').text()).toBe('1/3 적용 중')
  })

  it('일부 실패 — 되돌리지 않고 실패한 방을 말하고, 재시도는 실패한 방만', async () => {
    api.saveExam.mockImplementation(async (roomId: number) => {
      if (roomId === 12) throw new ApiError(500, MESSAGES[500])
      return { outbox_ids: [1], id: roomId + 100 }
    })
    await mountForm()
    await fill()
    await submit()
    await flushPromises()
    const t = toasts.value.at(-1)!
    expect(t).toMatchObject({ tone: 'danger', message: '3개 중 2개 적용 · 402호 실패' })
    api.saveExam.mockClear()
    api.saveExam.mockResolvedValue({ outbox_ids: [1], id: 112 })
    t.action!.onClick()
    await flushPromises()
    expect(api.saveExam.mock.calls).toEqual([[12, body]])
    expect(toasts.value.at(-1)?.message).toBe('저장했습니다.')
  })

  it('409 는 사유를 Toast 에 붙인다 (id 소진)', async () => {
    api.saveExam.mockImplementation(async (roomId: number) => {
      if (roomId === 13) throw new ApiError(409, MESSAGES[409], [], { detail: 'id 소진' })
      return { outbox_ids: [1], id: roomId + 100 }
    })
    await mountForm()
    await fill()
    await submit()
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe(
      '3개 중 2개 적용 · 405호 실패 · id 소진 — 지난 예약·시험기간을 정리하세요',
    )
  })

  it('수정 — 그 id 로, 넘겨받은 그 방 하나만', async () => {
    await mountForm({
      rooms: [rooms[1]],
      value: { id: 40, room_id: 12, date_start: '2026-10-19', date_end: '2026-10-20' },
    })
    expect(w.get('.form__submit').text()).toContain('저장')
    await control('종료일').setValue('2026-10-23')
    await submit()
    await flushPromises()
    expect(api.saveExam.mock.calls).toEqual([
      [12, { id: 40, date_start: '2026-10-19', date_end: '2026-10-23' }],
    ])
  })

  it('종료일이 시작일보다 앞이면 막는다', async () => {
    await mountForm()
    await control('시작일').setValue('2026-10-23')
    await control('종료일').setValue('2026-10-19')
    await submit()
    await flushPromises()
    expect(api.saveExam).not.toHaveBeenCalled()
    expect(w.text()).toContain('종료일은 시작일과 같거나 뒤여야 합니다')
  })

  it('고른 방이 없으면 버튼이 잠긴다', async () => {
    await mountForm({ rooms: [] })
    expect((w.get('.form__submit').element as HTMLButtonElement).disabled).toBe(true)
  })
})
