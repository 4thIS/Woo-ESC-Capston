import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import ExamBlock from '@/admin/views/rooms/ExamBlock.vue'
import { roomsApi } from '@/api/rooms'
import type { ExamWithRoom, RoomOut } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/rooms', () => ({ roomsApi: { saveExam: vi.fn(), deleteExam: vi.fn() } }))
const api = vi.mocked(roomsApi)

const R = (id: number, room: number): RoomOut => ({
  id,
  building_id: 1,
  room,
  units: 1,
  reservable: false,
})
const rooms = [R(11, 401), R(12, 402), R(13, 405), R(14, 406)]
const X = (id: number, room_id: number): ExamWithRoom => ({
  id,
  room_id,
  date_start: '2026-10-19',
  date_end: '2026-10-23',
})
type Root = VueWrapper | DOMWrapper<Element>
const btn = (root: Root, text: string) =>
  root.findAll('button').find((b) => b.text().startsWith(text))!
let w: VueWrapper
const dialog = (title: string) =>
  w.findAll('[role=dialog]').find((d) => d.get('h2').text() === title)
async function mountBlock(exams: ExamWithRoom[]) {
  w = mount(ExamBlock, {
    props: {
      rooms,
      label: (id: number) => String(rooms.find((r) => r.id === id)!.room),
      exams,
      states: new Map(),
      loading: false,
    },
    global: { stubs: { teleport: true } },
  })
  await flushPromises()
}

beforeEach(() => {
  api.saveExam.mockReset()
  api.deleteExam.mockReset().mockResolvedValue({ outbox_ids: [3], id: null })
  for (const t of [...toasts.value]) dismissToast(t.id)
})

describe('시험기간 블록', () => {
  it('같은 기간은 한 행으로 접는다 — 호수 셋까지, 넘으면 외 N곳', async () => {
    await mountBlock([X(1, 11), X(2, 12), X(3, 13), X(4, 14)])
    const row = w.findAll('tbody tr')[0]
    expect(row.text()).toContain('401, 402, 405 외 1곳')
    expect(row.text()).toContain('4곳')
  })

  it('펼치면 방마다 수정·삭제 — 삭제는 확인 뒤 그 방의 그 id', async () => {
    await mountBlock([X(1, 11), X(2, 12)])
    await w.get('.tbl__toggle').trigger('click')
    const items = w.findAll('.blk__item')
    expect(items.map((i) => i.find('.num').text())).toEqual(['401호', '402호'])
    await btn(items[1], '삭제').trigger('click')
    const c = dialog('시험기간 삭제')!
    expect(c.text()).toContain('402호 시험기간 2026-10-19 ~ 2026-10-23')
    await btn(c, '삭제').trigger('click')
    await flushPromises()
    expect(api.deleteExam).toHaveBeenCalledWith(12, 2)
    expect(w.emitted('changed')).toHaveLength(1)
  })

  it('추가 버튼이 대상 수를 말하고, 폼은 고른 방 전부를 대상으로 연다', async () => {
    await mountBlock([])
    const add = btn(w, '+ 선택한 4곳에 기간 추가')
    await add.trigger('click')
    const d = dialog('시험기간 추가')!
    expect(d.text()).toContain('대상 4곳 · 401호, 402호, 405호, 406호')
  })
})
