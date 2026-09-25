import { beforeEach, describe, expect, it, vi } from 'vitest'
import { adminApi } from '@/api/admin'
import { loraApi } from '@/api/lora'
import { clearSession } from '@/lib/session'
import nodes from '@/api/__fixtures__/nodes.json'
import modems from '@/api/__fixtures__/modems.json'
import pending from '@/api/__fixtures__/pending.json'
import outbox from '@/api/__fixtures__/outbox.json'
import failed from '@/api/__fixtures__/failed.json'
import latency from '@/api/__fixtures__/latency.json'

const json = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
const fetchMock = vi.fn<typeof fetch>()
const call = (i = 0) => ({ url: fetchMock.mock.calls[i][0], init: fetchMock.mock.calls[i][1]! })

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  clearSession()
})

describe('adminApi', () => {
  it('nodes — 시각 필드만 Date, 보고 없는 노드는 null 그대로', async () => {
    fetchMock.mockResolvedValue(json(nodes))
    const out = await adminApi.nodes()
    expect(call().url).toBe('/api/admin/nodes')
    expect(out[0].last_seen_at).toBeInstanceOf(Date)
    expect(out[0].last_seen_at!.toISOString()).toBe('2026-09-25T00:58:00.123Z')
    expect(out[0].last_status_at!.toISOString()).toBe('2026-09-24T19:00:00.000Z')
    expect(out[1].last_seen_at).toBeNull()
    expect(out[1].warnings).toEqual(['unseen'])
  })

  it('failed — days·limit 쿼리, 시각 Date', async () => {
    fetchMock.mockResolvedValue(json(failed))
    const out = await adminApi.failed(7)
    expect(call().url).toBe('/api/admin/outbox/failed?days=7&limit=500')
    expect(out[0].finished_at!.toISOString()).toBe('2026-09-24T23:45:00.000Z')
    expect(out[0].building).toBe('공학관')
  })

  it('latency — KST 날짜 from·to 와 type 쿼리', async () => {
    fetchMock.mockResolvedValue(json(latency))
    const out = await adminApi.latency({ from: '2026-09-19', to: '2026-09-25', type: 'all' })
    expect(call().url).toBe('/api/admin/analytics/latency?from=2026-09-19&to=2026-09-25&type=all')
    expect(out.bins.at(-1)).toEqual({ ge: 120, lt: null, count: 0 })
  })
})

describe('loraApi', () => {
  it('modems — last_seen_at Date, null 그대로', async () => {
    fetchMock.mockResolvedValue(json(modems))
    const out = await loraApi.modems()
    expect(call().url).toBe('/api/lora/modems')
    expect(out[0].last_seen_at!.toISOString()).toBe('2026-09-25T01:00:00.500Z')
    expect(out[1].last_seen_at).toBeNull()
  })

  it('pending — first·last Date', async () => {
    fetchMock.mockResolvedValue(json(pending))
    const out = await loraApi.pending()
    expect(out[0].first_seen_at.toISOString()).toBe('2026-09-24T22:00:00.000Z')
    expect(out[0].last_seen_at.toISOString()).toBe('2026-09-25T00:59:00.000Z')
  })

  it('recentOutbox — limit 쿼리, 끝나지 않은 작업의 finished_at 은 null', async () => {
    fetchMock.mockResolvedValue(json(outbox))
    const out = await loraApi.recentOutbox(7)
    expect(call().url).toBe('/api/lora/outbox?limit=7')
    expect(out[0].finished_at!.toISOString()).toBe('2026-09-25T00:00:18.400Z')
    expect(out[1].finished_at).toBeNull()
  })

  it('registerModem · rotateToken — 본문·경로', async () => {
    fetchMock.mockImplementation(async () => json({ modem_id: 'gonghak-02', token: 't' }))
    await loraApi.registerModem('gonghak-02')
    await loraApi.rotateToken('gonghak-02')
    expect(call(0).url).toBe('/api/lora/modems')
    expect(call(0).init.method).toBe('POST')
    expect(call(0).init.body).toBe('{"modem_id":"gonghak-02"}')
    expect(call(1).url).toBe('/api/lora/modems/gonghak-02/token')
    expect(call(1).init.body).toBeUndefined()
  })

  it('provision · syncRoom · broadcastTime — 경로와 본문', async () => {
    fetchMock.mockImplementation(async () => json({ outbox_ids: [1], id: null, modems: 0 }))
    await loraApi.provision('A1B2C3D4E5F6', { bld: 'E', room: 402, unit: 2 })
    await loraApi.syncRoom(11)
    await loraApi.broadcastTime()
    expect(call(0).url).toBe('/api/lora/pending/A1B2C3D4E5F6/provision')
    expect(call(0).init.body).toBe('{"bld":"E","room":402,"unit":2}')
    expect(call(1).url).toBe('/api/rooms/11/sync')
    expect(call(1).init.body).toBe('{}') // SyncIn 기본값 = 세 종류 전부
    expect(call(2).url).toBe('/api/lora/time')
    expect(call(2).init.method).toBe('POST')
  })
})
