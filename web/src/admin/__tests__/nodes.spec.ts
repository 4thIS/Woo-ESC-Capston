import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import NodesView from '@/admin/views/NodesView.vue'
import {
  buildingOptions,
  roomLabel,
  sortNodes,
  unitsByRoom,
  versions,
  volts,
} from '@/admin/nodesView'
import { adminApi } from '@/api/admin'
import { loraApi } from '@/api/lora'
import { ApiError, MESSAGES } from '@/api/client'
import type { Enqueued, NodeOut } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/admin', () => ({ adminApi: { nodes: vi.fn() } }))
vi.mock('@/api/lora', () => ({
  loraApi: {
    modems: vi.fn(),
    pending: vi.fn(),
    syncRoom: vi.fn(),
    broadcastTime: vi.fn(),
    registerModem: vi.fn(),
    rotateToken: vi.fn(),
    provision: vi.fn(),
  },
}))
const nodesApi = vi.mocked(adminApi.nodes)
const lora = vi.mocked(loraApi, true)

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
const never = (over: Partial<NodeOut> = {}) =>
  node({
    mac: null,
    fw: null,
    batt_mv: null,
    rssi: null,
    snr: null,
    sched_ver: null,
    resv_ver: null,
    exam_ver: null,
    ident_ver: null,
    last_seen_at: null,
    sync_state: 'unknown',
    warnings: ['unseen'],
    ...over,
  })

let visibility: DocumentVisibilityState = 'visible'
beforeEach(() => {
  visibility = 'visible'
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => visibility })
  toasts.value.forEach((t) => dismissToast(t.id))
  nodesApi.mockReset().mockResolvedValue([node(), never({ room_id: 2, room: 402 })])
  lora.modems.mockReset().mockResolvedValue([])
  lora.pending.mockReset().mockResolvedValue([])
  lora.syncRoom.mockReset().mockResolvedValue({ outbox_ids: [1], id: null })
  lora.broadcastTime.mockReset()
})
afterEach(() => vi.useRealTimers())
// 앞 테스트의 화면이 남아 있으면 그 visibilitychange 리스너까지 nodesApi 를 부른다
enableAutoUnmount(afterEach)

async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { render: () => null } }],
  })
  const w = mount(NodesView, { global: { plugins: [router], stubs: { teleport: true } } })
  await flushPromises()
  return w
}
const esp = (w: VueWrapper) => w.get('section[aria-labelledby="nodes-esp"]')
const firstCells = (w: VueWrapper) =>
  esp(w)
    .findAll('tbody tr')
    .map((r) => r.get('td').text())
const button = (w: VueWrapper, text: string) => w.findAll('button').find((b) => b.text() === text)!

describe('nodesView', () => {
  it('sortNodes — 보고 없음(null) 먼저, 그다음 오래된 순, 같으면 서버 순서', () => {
    const a = node({ room: 1, last_seen_at: new Date('2026-09-25T01:00:00Z') })
    const b = never({ room: 2 })
    const c = node({ room: 3, last_seen_at: new Date('2026-09-23T01:00:00Z') })
    const d = never({ room: 4 })
    expect(sortNodes([a, b, c, d]).map((n) => n.room)).toEqual([2, 4, 3, 1])
  })
  it('roomLabel — 노드가 2대인 방만 -unit', () => {
    const ns = [
      node({ room_id: 1, room: 401 }),
      node({ room_id: 2, room: 402, unit: 1 }),
      node({ room_id: 2, room: 402, unit: 2 }),
    ]
    const u = unitsByRoom(ns)
    expect(ns.map((n) => roomLabel(n, u))).toEqual(['401', '402-1', '402-2'])
  })
  it('volts·versions — 퍼센트로 바꾸지 않고, null 은 —', () => {
    expect(volts(3980)).toBe('3.98 V')
    expect(volts(null)).toBe('—')
    expect(versions(node())).toBe('41/12/3/2')
    expect(versions(node({ exam_ver: null }))).toBe('41/12/—/2')
    expect(versions(never())).toBe('—')
  })
  it('buildingOptions — 전체 + 이름순, 중복 없음', () => {
    const ns = [
      node({ building_id: 2, building: '사회관' }),
      node({ building_id: 1, building: '공학관' }),
      node({ building_id: 2, building: '사회관' }),
    ]
    expect(buildingOptions(ns)).toEqual([
      { value: '', label: '전체' },
      { value: 1, label: '공학관' },
      { value: 2, label: '사회관' },
    ])
  })
})

describe('NodesView', () => {
  it('보고 없는 노드가 먼저, 빈 칸은 —, 응답 없음 배지 · 값은 V·dBm·버전', async () => {
    const w = await mountView()
    expect(firstCells(w)).toEqual(['공학관 402', '공학관 401'])
    const [first, second] = esp(w).findAll('tbody tr')
    expect(first.text()).toContain('응답 없음')
    expect(first.findAll('td')[1].text()).toBe('—')
    expect(second.text()).toContain('3.98 V')
    expect(second.text()).toContain('−71 dBm')
    expect(second.text()).toContain('41/12/3/2')
    expect(second.text()).toContain('동기화됨')
  })

  it('배터리 경고(low_batt)면 V 값을 busy 틴트 배지로', async () => {
    nodesApi.mockResolvedValue([node({ warnings: ['low_batt'], batt_mv: 3420 })])
    const w = await mountView()
    expect(esp(w).get('.badge--busy').text()).toBe('3.42 V')
  })

  it('문제 있는 것만 · 건물 필터', async () => {
    nodesApi.mockResolvedValue([
      node({ room_id: 1, room: 401 }),
      node({ room_id: 2, room: 402, warnings: ['resync'] }),
      node({ room_id: 3, building_id: 2, building: '사회관', room: 101 }),
    ])
    const w = await mountView()
    await esp(w).get('input[type="checkbox"]').setValue(true)
    expect(firstCells(w)).toEqual(['공학관 402'])
    await esp(w).get('input[type="checkbox"]').setValue(false)
    await w.get('.nodes__filter select').setValue('2')
    expect(firstCells(w)).toEqual(['사회관 101'])
  })

  it('강의실이 없으면 빈 상태 — master 화면이 아직 없으면 링크 버튼도 없다', async () => {
    nodesApi.mockResolvedValue([])
    const w = await mountView()
    expect(esp(w).text()).toContain('이 건물에 강의실이 없습니다')
    expect(esp(w).find('.empty button').exists()).toBe(false)
  })

  it('첫 조회 실패 — "강의실 없음"으로 오독되지 않게 불러오지 못했다고 말한다', async () => {
    nodesApi.mockRejectedValue(new ApiError(500, MESSAGES[500]))
    const w = await mountView()
    expect(esp(w).text()).toContain('노드 목록을 불러오지 못했습니다')
    expect(esp(w).text()).not.toContain('이 건물에 강의실이 없습니다')
  })

  it('새로고침 버튼 — 배경 폴링 중엔 spin/disable 안 되고, 수동 클릭 때만', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    let resolve!: () => void
    nodesApi.mockReset().mockReturnValueOnce(
      new Promise((r) => {
        resolve = () => r([node()])
      }),
    )
    const w = await mountView()
    resolve()
    await flushPromises()
    nodesApi.mockReturnValueOnce(new Promise(() => {})) // 배경 폴링은 응답이 안 와도
    vi.advanceTimersByTime(30_000)
    await flushPromises()
    expect(button(w, '새로고침').attributes('disabled')).toBeUndefined()
    let manualResolve!: () => void
    nodesApi.mockReturnValueOnce(
      new Promise((r) => {
        manualResolve = () => r([node()])
      }),
    )
    await button(w, '새로고침').trigger('click')
    expect(button(w, '새로고침').attributes('disabled')).toBeDefined()
    manualResolve()
    await flushPromises()
    expect(button(w, '새로고침').attributes('disabled')).toBeUndefined()
    w.unmount()
  })

  it('30초마다 다시 읽고, 화면을 떠나면 멈춘다', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    const w = await mountView()
    expect(nodesApi).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(30_000)
    await flushPromises()
    expect(nodesApi).toHaveBeenCalledTimes(2)
    w.unmount()
    vi.advanceTimersByTime(90_000)
    await flushPromises()
    expect(nodesApi).toHaveBeenCalledTimes(2)
  })

  it('숨긴 탭에서는 읽지 않고, 다시 보이면 즉시 1회', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    const w = await mountView()
    visibility = 'hidden'
    document.dispatchEvent(new Event('visibilitychange'))
    vi.advanceTimersByTime(120_000)
    await flushPromises()
    expect(nodesApi).toHaveBeenCalledTimes(1)
    visibility = 'visible'
    document.dispatchEvent(new Event('visibilitychange'))
    await flushPromises()
    expect(nodesApi).toHaveBeenCalledTimes(2)
    w.unmount()
  })

  it('갱신 실패 — 표를 지우지 않고, 끊긴 동안 Toast 는 한 번', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    const w = await mountView()
    nodesApi.mockRejectedValue(new ApiError(0, MESSAGES[0]))
    for (let i = 0; i < 3; i++) {
      vi.advanceTimersByTime(30_000)
      await flushPromises()
    }
    expect(esp(w).findAll('tbody tr')).toHaveLength(2)
    expect(toasts.value.filter((t) => t.tone === 'danger').map((t) => t.message)).toEqual([
      MESSAGES[0],
    ])
    w.unmount()
  })

  it('재전송 — 방 id 로 요청, 처리 중에는 다시 누를 수 없다', async () => {
    let resolve!: (v: Enqueued) => void
    lora.syncRoom.mockReturnValue(new Promise((r) => (resolve = r)))
    const w = await mountView()
    const btn = esp(w).findAll('tbody tr')[1].get('button')
    await btn.trigger('click')
    await btn.trigger('click')
    expect(lora.syncRoom).toHaveBeenCalledTimes(1)
    expect(lora.syncRoom).toHaveBeenCalledWith(1)
    resolve({ outbox_ids: [9], id: null })
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe('공학관 401호 재전송을 요청했습니다.')
  })

  it('재전송 404(강의실 삭제됨) — 안내 문구 + 목록을 다시 읽는다', async () => {
    lora.syncRoom.mockRejectedValueOnce(new ApiError(404, MESSAGES[404]))
    const w = await mountView()
    await esp(w).findAll('tbody tr')[1].get('button').trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe(
      '강의실이 이미 삭제되었습니다. 목록을 새로 불러옵니다.',
    )
    expect(toasts.value.at(-1)?.tone).not.toBe('danger')
    expect(nodesApi).toHaveBeenCalledTimes(2)
    w.unmount()
  })

  it('재전송 5xx — danger Toast + 재시도 액션', async () => {
    lora.syncRoom.mockRejectedValueOnce(new ApiError(500, MESSAGES[500]))
    const w = await mountView()
    await esp(w).findAll('tbody tr')[1].get('button').trigger('click')
    await flushPromises()
    const t = toasts.value.at(-1)!
    expect(t.tone).toBe('danger')
    expect(t.message).toBe(MESSAGES[500])
    expect(t.action?.label).toBe('재시도')
    lora.syncRoom.mockResolvedValueOnce({ outbox_ids: [9], id: null })
    t.action!.onClick()
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe('공학관 401호 재전송을 요청했습니다.')
    w.unmount()
  })

  it('시각 브로드캐스트 — 0대 · 429 · 성공 문구', async () => {
    const w = await mountView()
    lora.broadcastTime.mockResolvedValueOnce({ modems: 0 })
    await button(w, '시각 브로드캐스트').trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe('연결된 모뎀Pi가 없어 보내지 못했습니다.')
    lora.broadcastTime.mockRejectedValueOnce(new ApiError(429, MESSAGES[429]))
    await button(w, '시각 브로드캐스트').trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe(
      '시각 브로드캐스트는 10분에 한 번만 보낼 수 있습니다.',
    )
    lora.broadcastTime.mockResolvedValueOnce({ modems: 2 })
    await button(w, '시각 브로드캐스트').trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe('모뎀Pi 2대에 시각을 보냈습니다.')
  })
})
