import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import CsvImport from '@/admin/views/rooms/CsvImport.vue'
import { roomsApi } from '@/api/rooms'
import { ApiError, MESSAGES } from '@/api/client'
import type { ImportSummary } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/rooms', () => ({
  IMPORT_MAX_BYTES: 1024 * 1024,
  roomsApi: { importSlots: vi.fn() },
}))
const api = vi.mocked(roomsApi)

const summary = (o: Partial<ImportSummary> = {}): ImportSummary => ({
  rooms: 1,
  added: 1,
  updated: 0,
  deleted: 0,
  skipped: [{ row: 2, reason: '수동 슬롯 있음 (source=2)' }],
  outbox_ids: [],
  ...o,
})
let w: VueWrapper
const dialog = (title: string) =>
  w.findAll('[role=dialog]').find((d) => d.get('h2').text() === title)
const btn = (root: VueWrapper | DOMWrapper<Element>, text: string) =>
  root.findAll('button').find((b) => b.text() === text)!
/** jsdom 의 File 은 arrayBuffer 가 없을 수 있어 같은 모양의 객체로 넘긴다 (코드가 쓰는 것은 name·size·arrayBuffer) */
async function choose(size = 20) {
  const input = w.get('input[type=file]')
  const file = { name: 'slots.csv', size, arrayBuffer: async () => new ArrayBuffer(size) }
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
  await flushPromises()
}

beforeEach(() => {
  api.importSlots.mockReset()
  for (const t of [...toasts.value]) dismissToast(t.id)
  w = mount(CsvImport, { global: { stubs: { teleport: true } } })
})

describe('CSV 가져오기', () => {
  it('먼저 dry_run 요약 — 건너뛸 행(웹에서 고친 행)을 표로, 적용하면 실제로 보낸다', async () => {
    api.importSlots
      .mockResolvedValueOnce(summary())
      .mockResolvedValueOnce(summary({ outbox_ids: [3] }))
    await choose()
    expect(api.importSlots.mock.calls[0][1]).toBe(true)
    const d = dialog('CSV 가져오기 — slots.csv')!
    expect(d.text()).toContain('강의실 1곳 · 추가 1 · 수정 0 · 삭제 0')
    expect(d.text()).toContain('수동 슬롯 있음 (source=2)')
    await btn(d, '적용').trigger('click')
    await flushPromises()
    expect(api.importSlots.mock.calls[1][1]).toBe(false)
    expect(toasts.value.at(-1)?.message).toBe(
      '시간표를 가져왔습니다 — 강의실 1곳에 보냅니다. 웹에서 고친 1행은 건너뛰었습니다.',
    )
    expect(w.emitted('applied')).toHaveLength(1)
    expect(dialog('CSV 가져오기 — slots.csv')).toBeUndefined()
  })

  it('행 오류 400 — 아무것도 적용되지 않았다고 말하고 행 번호·사유를 표로 (0행은 —)', async () => {
    api.importSlots.mockRejectedValue(
      new ApiError(400, MESSAGES[400], [], {
        errors: [
          { row: 2, error: 'room: 999 없음 (우송대 K)' },
          { row: 0, error: '헤더에 없는 컬럼: professor' },
        ],
      }),
    )
    await choose()
    const d = dialog('CSV 오류 — 아무것도 적용되지 않았습니다')!
    const rows = d.findAll('tbody tr').map((r) => r.findAll('td').map((c) => c.text()))
    expect(rows).toEqual([
      ['2', 'room: 999 없음 (우송대 K)'],
      ['—', '헤더에 없는 컬럼: professor'],
    ])
  })

  it('UTF-8 이 아니면(400, errors 없음) 저장 형식을 말한다', async () => {
    api.importSlots.mockRejectedValue(
      new ApiError(400, MESSAGES[400], [], { detail: 'UTF-8 로 저장하세요 (엑셀: CSV UTF-8)' }),
    )
    await choose()
    expect(toasts.value.at(-1)).toMatchObject({
      tone: 'danger',
      message: 'CSV 를 UTF-8 로 저장해 주세요 (엑셀: CSV UTF-8).',
    })
  })

  it('1 MB 가 넘으면 보내지 않는다', async () => {
    await choose(1024 * 1024 + 1)
    expect(api.importSlots).not.toHaveBeenCalled()
    expect(toasts.value.at(-1)?.message).toBe('1 MB 를 넘는 파일은 가져올 수 없습니다.')
  })

  it('바뀌는 것이 없으면 적용 버튼이 잠긴다', async () => {
    api.importSlots.mockResolvedValue(summary({ added: 0, rooms: 0 }))
    await choose()
    const d = dialog('CSV 가져오기 — slots.csv')!
    expect(d.text()).toContain('바뀌는 것이 없습니다.')
    expect((btn(d, '적용').element as HTMLButtonElement).disabled).toBe(true)
  })
})
