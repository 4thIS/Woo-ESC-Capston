import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import SlotGroupForm from '@/components/domain/SlotGroupForm.vue'
import { roomsApi } from '@/api/rooms'
import { ApiError, MESSAGES } from '@/api/client'
import type { SlotWithRoom } from '@/api/types'
import { groupSlots } from '@/components/domain/slotGroups'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/rooms', () => ({ roomsApi: { replaceSlots: vi.fn() } }))
const api = vi.mocked(roomsApi)

const slot = (h: number, over: Partial<SlotWithRoom> = {}): SlotWithRoom => ({
  id: h,
  room_id: 1,
  day: 2,
  s_h: h,
  s_m: 0,
  e_h: h,
  e_m: 50,
  type: 1,
  subject: '인공지능기초 102',
  professor: '정필성',
  source: 2,
  ...over,
})
const PERIODS = [slot(9), slot(10), slot(11)]
const group = groupSlots(PERIODS)[0]

let w: VueWrapper
async function mountForm(existing: SlotWithRoom[] = PERIODS) {
  w = mount(SlotGroupForm, {
    props: { open: true, group, roomLabel: 'E 803호', existing },
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
const button = (text: string) => w.findAll('button').find((b) => b.text() === text)

beforeEach(() => {
  api.replaceSlots.mockReset().mockResolvedValue({ outbox_ids: [7, 8], id: null })
  for (const t of [...toasts.value]) dismissToast(t.id)
})
afterEach(() => w?.unmount())

describe('SlotGroupForm — 교시 묶음 수정 (admin-rooms.md)', () => {
  it('지금 묶음으로 채운다 — 시작 · 교시 수 · 한 교시, 끝은 자동, 교시 칩', async () => {
    await mountForm()
    expect((control('시작').element as HTMLInputElement).value).toBe('09:00')
    expect((control('교시 수').element as HTMLSelectElement).value).toBe('3')
    expect(w.text()).toContain('끝 11:50')
    expect(w.findAll('.pf__chip').map((c) => c.text())).toEqual([
      '1교시 09:00–09:50',
      '2교시 10:00–10:50',
      '3교시 11:00–11:50',
    ])
    expect(button('3교시 저장')).toBeTruthy()
  })

  it('시작을 한 시간 늦추면 교시들이 함께 옮겨 가고, 지금 시간을 취소선으로 보인다 → 한 번에 저장', async () => {
    await mountForm()
    await control('시작').setValue('10:00')
    expect(w.text()).toContain('끝 12:50')
    expect(w.get('.gf__before').text()).toContain('09:00–09:50 · 10:00–10:50 · 11:00–11:50')
    await button('3교시 저장')!.trigger('click')
    await flushPromises()
    expect(api.replaceSlots).toHaveBeenCalledWith(1, {
      remove: [
        { day: 2, s_h: 9, s_m: 0 },
        { day: 2, s_h: 10, s_m: 0 },
        { day: 2, s_h: 11, s_m: 0 },
      ],
      put: [10, 11, 12].map((h) => ({
        day: 2,
        s_h: h,
        s_m: 0,
        e_h: h,
        e_m: 50,
        type: 1,
        subject: '인공지능기초 102',
        professor: '정필성',
        source: 2,
      })),
    })
    expect(w.emitted('saved')![0][0]).toMatchObject({
      roomId: 1,
      key: 's1-2-10-0',
      outboxIds: [7, 8],
    })
    expect(w.emitted('close')).toHaveLength(1)
  })

  it('교시 수를 줄이면 칩도 준다, 다른 수업과 겹치면 저장 잠금', async () => {
    await mountForm([...PERIODS, slot(13, { subject: '다른 수업' })])
    await control('교시 수').setValue('2')
    expect(w.findAll('.pf__chip')).toHaveLength(2)
    await control('교시 수').setValue('5')
    expect(w.text()).toContain('겹칩니다: 13:00–13:50 다른 수업')
    expect(button('5교시 저장')!.attributes('disabled')).toBeDefined()
  })

  it('자정을 넘기면 저장 잠금', async () => {
    await mountForm()
    await control('시작').setValue('22:00')
    expect(w.text()).toContain('자정을 넘깁니다')
  })

  it('긴급(3) 교시가 섞여 있으면 긴급으로 보낸다 — 낮은 출처로 덮지 않게', async () => {
    const g = groupSlots([slot(9, { source: 3 }), slot(10, { source: 3 })])[0]
    w = mount(SlotGroupForm, {
      props: { open: true, group: g, roomLabel: 'E 803호', existing: [] },
      global: { stubs: { teleport: true } },
      attachTo: document.body,
    })
    await flushPromises()
    await button('2교시 저장')!.trigger('click')
    await flushPromises()
    expect(api.replaceSlots.mock.calls[0][1].put.every((p) => p.source === 3)).toBe(true)
  })

  it('409 · 422 — 문장으로 알리고 창은 열어 둔다, 묶음 삭제는 부모에게', async () => {
    api.replaceSlots.mockRejectedValue(new ApiError(422, MESSAGES[422], ['body']))
    await mountForm()
    await button('3교시 저장')!.trigger('click')
    await flushPromises()
    expect(w.text()).toContain(MESSAGES[422])
    expect(w.emitted('close')).toBeUndefined()
    await button('묶음 삭제')!.trigger('click')
    expect(w.emitted('remove')).toHaveLength(1)
  })
})
