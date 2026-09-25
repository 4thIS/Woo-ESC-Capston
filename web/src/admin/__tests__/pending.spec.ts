import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import PendingPanel from '@/admin/views/nodes/PendingPanel.vue'
import { loraApi } from '@/api/lora'
import { ApiError, MESSAGES } from '@/api/client'
import type { NodeOut, PendingOut } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/lora', () => ({ loraApi: { provision: vi.fn() } }))
const provision = vi.mocked(loraApi.provision)

const node = (over: Partial<NodeOut> = {}): NodeOut => ({
  room_id: 1,
  building_id: 1,
  building: '공학관',
  bld: 'E',
  room: 401,
  unit: 1,
  modem_id: 'm1',
  mac: '0A1B2C3D4E01',
  fw: 3,
  batt_mv: 3980,
  rssi: -71,
  snr: 7.5,
  sched_ver: 41,
  resv_ver: 12,
  exam_ver: 3,
  ident_ver: 2,
  layout: 1,
  clock_stale: false,
  low_batt: false,
  uptime_h: 10,
  last_seen_at: new Date('2026-09-25T00:00:00Z'),
  last_ack_at: null,
  last_status_at: null,
  sync_state: 'synced',
  warnings: [],
  ...over,
})
const NODES: NodeOut[] = [
  node(),
  node({ room_id: 2, room: 402, unit: 1, mac: '0A1B2C3D4E02' }),
  node({ room_id: 2, room: 402, unit: 2, mac: null, last_seen_at: null, warnings: ['unseen'] }),
  node({ room_id: 3, building_id: 2, building: '사회관', bld: 'S', room: 101, mac: null }),
]
const p = (over: Partial<PendingOut> = {}): PendingOut => ({
  mac: 'A1B2C3D4E5F6',
  modem_id: 'gonghak-01',
  fw: 3,
  batt_mv: 4100,
  rssi: -68,
  first_seen_at: new Date('2026-09-24T22:00:00Z'),
  last_seen_at: new Date('2026-09-25T00:59:00Z'),
  ...over,
})
const mountPanel = (pending: PendingOut[] | undefined, nodes = NODES) =>
  mount(PendingPanel, {
    props: { pending, nodes, loading: false },
    global: { stubs: { teleport: true } },
  })
const button = (w: VueWrapper, text: string) => w.findAll('button').find((b) => b.text() === text)!
const selects = (w: VueWrapper) => w.findAll('[role="dialog"] select')
const optionTexts = (w: VueWrapper, i: number) =>
  selects(w)
    [i].findAll('option')
    .map((o) => o.text())

beforeEach(() => {
  toasts.value.forEach((t) => dismissToast(t.id))
  provision.mockReset().mockResolvedValue({ outbox_ids: [77], id: null })
})

describe('PendingPanel', () => {
  it('행 — MAC · 모뎀 · FW · V · dBm, 처음·마지막 발견 KST 툴팁', () => {
    const w = mountPanel([p()])
    const row = w.get('tbody tr')
    expect(row.text()).toContain('A1B2C3D4E5F6')
    expect(row.text()).toContain('gonghak-01')
    expect(row.text()).toContain('4.10 V')
    expect(row.text()).toContain('−68 dBm')
    const titles = row.findAll('span[title]').map((s) => s.attributes('title'))
    expect(titles).toEqual(['2026-09-25 07:00', '2026-09-25 09:59'])
  })

  it('비어 있으면(정상) 빈 상태 문구', () => {
    expect(mountPanel([]).text()).toContain('등록을 기다리는 장치가 없습니다.')
  })

  it('배정 — 건물 → 호수 → 노드, 1대뿐인 방은 자동 선택, 사용 중 표시, 제출', async () => {
    const w = mountPanel([p()])
    await button(w, '강의실 배정').trigger('click')
    expect(button(w, '배정').attributes('disabled')).toBeDefined()
    expect(optionTexts(w, 0)).toEqual(['건물 선택', '공학관', '사회관'])
    await selects(w)[0].setValue('E')
    expect(optionTexts(w, 1)).toEqual(['호수 선택', '401호', '402호'])
    await selects(w)[1].setValue('401')
    expect((selects(w)[2].element as HTMLSelectElement).value).toBe('1')
    expect(w.text()).toContain('이 자리에는 이미 노드 0A1B2C3D4E01 가 있습니다.')
    await selects(w)[1].setValue('402')
    expect(optionTexts(w, 2)).toEqual(['노드 선택', '1번 노드 — 사용 중', '2번 노드'])
    await selects(w)[2].setValue('2')
    expect(w.text()).not.toContain('이 자리에는 이미 노드')
    await button(w, '배정').trigger('click')
    await flushPromises()
    expect(provision).toHaveBeenCalledWith('A1B2C3D4E5F6', { bld: 'E', room: 402, unit: 2 })
    expect(toasts.value.at(-1)?.message).toBe(
      '공학관 402호에 배정했습니다. 장치가 다음에 깨어나면 적용됩니다.',
    )
    expect(w.emitted('changed')).toHaveLength(1)
    expect(w.find('[role="dialog"]').exists()).toBe(false)
  })

  it('건물을 바꾸면 호수·노드 선택이 풀린다', async () => {
    const w = mountPanel([p()])
    await button(w, '강의실 배정').trigger('click')
    await selects(w)[0].setValue('E')
    await selects(w)[1].setValue('401')
    await selects(w)[0].setValue('S')
    expect((selects(w)[1].element as HTMLSelectElement).value).toBe('')
    expect(button(w, '배정').attributes('disabled')).toBeDefined()
  })

  it('404(다른 관리자가 먼저 배정·방 삭제) — 안내 + changed, Modal 닫힘', async () => {
    provision.mockRejectedValue(new ApiError(404, MESSAGES[404]))
    const w = mountPanel([p()])
    await button(w, '강의실 배정').trigger('click')
    await selects(w)[0].setValue('E')
    await selects(w)[1].setValue('401')
    await button(w, '배정').trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe(
      '장치 또는 강의실이 사라졌습니다. 목록을 새로 불러옵니다.',
    )
    expect(w.emitted('changed')).toHaveLength(1)
    expect(w.find('[role="dialog"]').exists()).toBe(false)
  })

  it('강의실이 하나도 없으면 먼저 등록하라고, 배정 버튼 잠금', async () => {
    const w = mountPanel([p()], [])
    await button(w, '강의실 배정').trigger('click')
    expect(w.get('[role="dialog"]').text()).toContain('먼저 건물 · 강의실을 등록해 주세요.')
    expect(button(w, '배정').attributes('disabled')).toBeDefined()
  })
})
