import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import SlotForm from '@/components/domain/SlotForm.vue'
import Modal from '@/components/ui/Modal.vue'
import { slotErrors, type SlotDraft } from '@/components/domain/slotForm'
import { roomsApi } from '@/api/rooms'
import { ApiError, MESSAGES } from '@/api/client'
import type { RoomOut, SlotWithRoom } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/rooms', () => ({ roomsApi: { putSlot: vi.fn(), deleteSlot: vi.fn() } }))
const api = vi.mocked(roomsApi)

const R = (id: number, room: number): RoomOut => ({
  id,
  building_id: 1,
  room,
  units: 1,
  reservable: false,
})
const rooms = [R(11, 401), R(12, 402)]
const slot = (o: Partial<SlotWithRoom> = {}): SlotWithRoom => ({
  id: 1,
  room_id: 11,
  day: 1,
  s_h: 9,
  s_m: 0,
  e_h: 11,
  e_m: 0,
  type: 1,
  subject: '캡스톤디자인',
  professor: '김교수',
  source: 2,
  ...o,
})
const draft = (o: Partial<SlotDraft> = {}): SlotDraft => ({
  roomId: 11,
  day: 1,
  start: '10:00',
  end: '12:00',
  type: 1,
  subject: '',
  professor: '',
  ...o,
})

// 저장 버튼은 form 속성으로 폼에 붙는다 — 문서 안에 있어야 이어진다(버튼 클릭 = 폼 submit)
let w: VueWrapper
async function mountForm(props: Record<string, unknown> = {}) {
  w = mount(SlotForm, {
    props: { open: true, rooms, ...props },
    global: { stubs: { teleport: true } },
    attachTo: document.body,
  })
  await flushPromises()
}
const control = (label: string) =>
  w
    .findAll('.field, .sel')
    .find(
      (f) => f.find('label').exists() && f.get('label').text().replace('*', '').trim() === label,
    )!
    .get('input, select')
const save = () =>
  w
    .findAll('button')
    .find((b) => b.text() === '저장')!
    .trigger('click')

beforeEach(() => {
  api.putSlot.mockReset().mockResolvedValue({ outbox_ids: [7], id: null })
  api.deleteSlot.mockReset().mockResolvedValue({ outbox_ids: [8], id: null })
  for (const t of [...toasts.value]) dismissToast(t.id)
})
afterEach(() => w?.unmount())

describe('slotErrors', () => {
  it('종료 ≤ 시작이면 막는다 (자정을 넘기는 슬롯은 없다)', () => {
    expect(slotErrors(draft({ start: '10:00', end: '10:00' }), [], null).end).toBe(
      '종료는 시작보다 늦어야 합니다 (자정을 넘기지 않습니다)',
    )
  })
  it('같은 방·같은 요일 구간이 겹치면 막는다 — 서버는 같은 키만 막는다', () => {
    expect(slotErrors(draft(), [slot()], null).end).toBe('겹칩니다: 09:00–11:00 캡스톤디자인')
  })
  it('자기 자신·다른 방·다른 요일·맞닿음은 겹침이 아니다', () => {
    expect(slotErrors(draft(), [slot()], slot())).toEqual({})
    expect(slotErrors(draft({ roomId: 12 }), [slot()], null)).toEqual({})
    expect(slotErrors(draft({ day: 2 }), [slot()], null)).toEqual({})
    expect(slotErrors(draft({ start: '11:00', end: '12:00' }), [slot()], null)).toEqual({})
  })
})

describe('SlotForm', () => {
  it('Enter 로 저장 — 저장 버튼이 폼의 submit 이라 폼 submit 한 번이 저장 한 번', async () => {
    await mountForm({ preset: { room_id: 12, day: 3, s_h: 14, s_m: 0 } })
    const form = w.get('form')
    const button = w.findAll('button').find((b) => b.text() === '저장')!
    expect(button.attributes('type')).toBe('submit')
    expect(button.attributes('form')).toBe(form.attributes('id'))
    await control('과목명').setValue('캡스톤디자인')
    api.putSlot.mockReturnValue(new Promise(() => {}))
    await form.trigger('submit')
    await form.trigger('submit') // 저장 중 두 번째 Enter 는 무시
    await flushPromises()
    expect(api.putSlot).toHaveBeenCalledTimes(1)
  })

  it('추가 — 누른 자리로 채우고(종료 +1시간), source 2 로 저장, 행 키를 알린다', async () => {
    await mountForm({ preset: { room_id: 12, day: 3, s_h: 14, s_m: 0 } })
    expect((control('요일').element as HTMLSelectElement).value).toBe('3')
    expect((control('시작').element as HTMLInputElement).value).toBe('14:00')
    expect((control('종료').element as HTMLInputElement).value).toBe('15:00')
    await control('과목명').setValue('캡스톤디자인')
    await save()
    await flushPromises()
    expect(api.putSlot).toHaveBeenCalledWith(12, {
      day: 3,
      s_h: 14,
      s_m: 0,
      e_h: 15,
      e_m: 0,
      type: 1,
      subject: '캡스톤디자인',
      professor: '',
      source: 2,
    })
    expect(api.deleteSlot).not.toHaveBeenCalled()
    expect(w.emitted('saved')![0]).toEqual([{ roomId: 12, key: 's12-3-14-0', outboxIds: [7] }])
    expect(w.emitted('close')).toHaveLength(1)
  })

  it('키가 바뀌면 새 행을 먼저 넣고 옛 행을 지운다 (PUT 은 키로 찾는다 — 옛 행이 남지 않게)', async () => {
    await mountForm({ mode: 'edit', value: slot() })
    await control('시작').setValue('13:00')
    await control('종료').setValue('15:00')
    await save()
    await flushPromises()
    expect(api.putSlot).toHaveBeenCalledWith(11, expect.objectContaining({ s_h: 13, e_h: 15 }))
    expect(api.deleteSlot).toHaveBeenCalledWith(
      11,
      expect.objectContaining({ day: 1, s_h: 9, s_m: 0 }),
    )
    expect(api.putSlot.mock.invocationCallOrder[0]).toBeLessThan(
      api.deleteSlot.mock.invocationCallOrder[0],
    )
    expect(w.emitted('saved')![0]).toEqual([{ roomId: 11, key: 's11-1-13-0', outboxIds: [7] }])
  })

  it('키가 같으면 지우지 않는다', async () => {
    await mountForm({ mode: 'edit', value: slot() })
    await control('과목명').setValue('캡스톤디자인2')
    await save()
    await flushPromises()
    expect(api.deleteSlot).not.toHaveBeenCalled()
  })

  it('옛 행 지우기 실패 — 새 행은 두고, 알리고, 목록을 새로 부르게 한다', async () => {
    api.deleteSlot.mockRejectedValue(new ApiError(500, MESSAGES[500]))
    await mountForm({ mode: 'edit', value: slot() })
    await control('시작').setValue('13:00')
    await control('종료').setValue('15:00')
    await save()
    await flushPromises()
    expect(w.emitted('saved')).toHaveLength(1)
    expect(w.emitted('stale')).toHaveLength(1)
    expect(toasts.value.at(-1)).toMatchObject({
      tone: 'danger',
      message: '새 슬롯은 저장했지만 옛 슬롯을 지우지 못했습니다. 목록에서 지워 주세요.',
    })
  })

  it('포털(1) 슬롯은 수동(2)으로 올린다고 알리고, 긴급(3)은 3 그대로 보낸다', async () => {
    await mountForm({ mode: 'edit', value: slot({ source: 1 }) })
    expect(w.text()).toContain(
      '저장하면 이 슬롯은 수동 편집으로 바뀌어 CSV 임포트에 덮이지 않습니다.',
    )
    await save()
    await flushPromises()
    expect(api.putSlot.mock.calls[0][1].source).toBe(2)
    w.unmount()
    await mountForm({ mode: 'edit', value: slot({ source: 3 }) })
    await save()
    await flushPromises()
    expect(api.putSlot.mock.calls[1][1].source).toBe(3)
  })

  it('겹치면 저장 전에 막는다 — 서버를 부르지 않는다', async () => {
    await mountForm({ existing: [slot()], preset: { room_id: 11, day: 1, s_h: 10, s_m: 0 } })
    await save()
    await flushPromises()
    expect(api.putSlot).not.toHaveBeenCalled()
    expect(w.text()).toContain('겹칩니다: 09:00–11:00 캡스톤디자인')
  })

  it('409 — 사람 문장 Toast, 목록 새로 고침, 폼은 열어 둔다', async () => {
    api.putSlot.mockRejectedValue(
      new ApiError(409, MESSAGES[409], [], { detail: 'source 3 슬롯은 source ≥ 3 로만 수정' }),
    )
    await mountForm({ preset: { room_id: 11 } })
    await save()
    await flushPromises()
    expect(toasts.value.at(-1)).toMatchObject({
      tone: 'danger',
      message: '이 슬롯은 웹에서 수정된 행입니다. CSV로 덮어쓸 수 없습니다.',
    })
    expect(w.emitted('stale')).toHaveLength(1)
    expect(w.emitted('close')).toBeUndefined()
  })

  it('연타해도 한 번만 보낸다', async () => {
    api.putSlot.mockReturnValue(new Promise(() => {}))
    await mountForm({ preset: { room_id: 11 } })
    await save()
    await save()
    await flushPromises()
    expect(api.putSlot).toHaveBeenCalledTimes(1)
  })

  it('입력을 바꾸면 배경 클릭으로 닫히지 않는다', async () => {
    await mountForm({ preset: { room_id: 11 } })
    expect(w.findComponent(Modal).props('closeOnBackdrop')).toBe(true)
    await control('과목명').setValue('x')
    expect(w.findComponent(Modal).props('closeOnBackdrop')).toBe(false)
  })
})
