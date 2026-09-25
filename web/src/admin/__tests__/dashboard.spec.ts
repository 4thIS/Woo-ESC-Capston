import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import DashboardView from '@/admin/views/DashboardView.vue'
import { binLabel, histogram, kpis, recentRows } from '@/admin/dashboardView'
import { adminApi } from '@/api/admin'
import { loraApi } from '@/api/lora'
import { ApiError, MESSAGES } from '@/api/client'
import type { FailedOut, LatencyOut, OutboxOut } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/admin', () => ({
  FAILED_LIMIT: 500,
  adminApi: { latency: vi.fn(), failed: vi.fn() },
}))
vi.mock('@/api/lora', () => ({ loraApi: { recentOutbox: vi.fn() } }))
const latencyApi = vi.mocked(adminApi.latency)
const failedApi = vi.mocked(adminApi.failed)
const recentApi = vi.mocked(loraApi.recentOutbox)

const BINS = [0, 10, 20, 30, 45, 60, 90, 120].map((ge, i, a) => ({
  ge,
  lt: a[i + 1] ?? null,
  count: 0,
}))
const lat = (over: Partial<LatencyOut> = {}): LatencyOut => ({
  n: 8,
  bins: BINS,
  p50: 25,
  p95: 50,
  max: 95,
  within_30s: 0.625,
  within_90s: 0.875,
  ...over,
})
const counts = (c: number[]) => lat({ bins: BINS.map((b, i) => ({ ...b, count: c[i] ?? 0 })) })
const EMPTY = lat({ n: 0, p50: null, p95: null, max: null, within_30s: 0, within_90s: 0 })
const o = (over: Partial<OutboxOut> = {}): OutboxOut => ({
  id: 1,
  modem_id: 'm1',
  bld: 'E',
  room: 401,
  unit: 1,
  type: 'SLOT_SET',
  payload: {},
  priority: 3,
  new_ver: 1,
  state: 'acked',
  attempts: 1,
  ack_status: 0,
  ack_detail: null,
  rssi: null,
  snr: null,
  last_error: null,
  created_at: new Date('2026-09-25T00:00:00Z'),
  dispatched_at: null,
  finished_at: new Date('2026-09-25T00:00:31.5Z'),
  ...over,
})

let visibility: DocumentVisibilityState = 'visible'
beforeEach(() => {
  visibility = 'visible'
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => visibility })
  toasts.value.forEach((t) => dismissToast(t.id))
  latencyApi
    .mockReset()
    .mockImplementation(async ({ type }) =>
      type === 'SLOT_SET'
        ? counts([1, 1, 2, 0, 0, 0, 1, 0])
        : type === 'RESV_SET'
          ? counts([0, 1, 0, 1, 1, 0, 0, 0])
          : lat(),
    )
  failedApi.mockReset().mockResolvedValue([{} as FailedOut])
  recentApi
    .mockReset()
    .mockResolvedValue([o({ id: 1 }), o({ id: 2, state: 'queued', finished_at: null })])
})
afterEach(() => vi.useRealTimers())

describe('dashboardView', () => {
  it('kpis — 값·단위·목표와 판정 문장, 실패는 값만 danger', () => {
    expect(kpis(lat(), 1, 7)).toEqual([
      {
        label: 'p50 반영 지연',
        value: '25',
        unit: '초',
        sub: 'p95 50초 · 최대 95초',
        tone: 'neutral',
      },
      {
        label: '30초 이내 비율',
        value: '62.5',
        unit: '%',
        sub: '목표 95% · 미달',
        tone: 'neutral',
      },
      {
        label: '90초 이내 비율',
        value: '87.5',
        unit: '%',
        sub: '목표 전부 · 미달',
        tone: 'neutral',
      },
      { label: '전송 실패', value: '1', unit: '건', sub: '최근 7일 · 모든 작업', tone: 'danger' },
    ])
    const ok = kpis(lat({ within_30s: 0.95, within_90s: 1, p50: 18.44 }), 0, 30)
    expect(ok[0].value).toBe('18.4')
    expect(ok[1].sub).toBe('목표 95% · 충족')
    expect(ok[2].sub).toBe('목표 전부 · 충족')
    expect(ok[3]).toMatchObject({ value: '0', tone: 'neutral', sub: '최근 30일 · 모든 작업' })
  })

  it('kpis — 전송 0건이면 —, 0% 가 아니다 (Review Focus 3)', () => {
    const k = kpis(EMPTY, 0, 7)
    expect(k.slice(0, 3).map((x) => [x.value, x.unit])).toEqual([
      ['—', undefined],
      ['—', undefined],
      ['—', undefined],
    ])
    expect(k.map((x) => x.sub)).toEqual([
      '전송 기록 없음',
      '목표 95%',
      '목표 전부',
      '최근 7일 · 모든 작업',
    ])
  })

  it('kpis — 실패가 상한(500)이면 500+', () => {
    expect(kpis(lat(), 500, 90)[3].value).toBe('500+')
  })

  it('binLabel · histogram — 서버 구간 그대로, SLA 선은 ge=30 경계', () => {
    expect(binLabel({ ge: 20, lt: 30, count: 0 })).toBe('20–30')
    expect(binLabel({ ge: 120, lt: null, count: 0 })).toBe('120+')
    const h = histogram(counts([1, 0, 2]), counts([0, 3]))
    expect(h.buckets.slice(0, 3)).toEqual([
      { label: '0–10', values: [1, 0] },
      { label: '10–20', values: [0, 3] },
      { label: '20–30', values: [2, 0] },
    ])
    expect(h.marker).toEqual({ at: 3, label: 'SLA 30초' })
  })

  it('recentRows — 최신이 위, 지연·대기·실패 문구, 30초 초과만 slow, 시각은 KST', () => {
    const rows = recentRows([
      o({ id: 1 }),
      o({ id: 2, state: 'failed' }),
      o({ id: 3, type: 'RESV_SET', room: 402, state: 'queued', finished_at: null }),
      o({ id: 4, type: 'SET_ROOM', state: 'cancelled', finished_at: null }),
    ])
    expect(rows.map((r) => [r.id, r.room, r.kind, r.delay, r.slow, r.failed])).toEqual([
      [4, 'E 401', '강의실 배정', '취소', false, false],
      [3, 'E 402', '예약', '대기', false, false],
      [2, 'E 401', '시간표', '실패', false, true],
      [1, 'E 401', '시간표', '31.5초', true, false],
    ])
    expect(rows[3]).toMatchObject({ time: '09:00', when: '2026-09-25 09:00', state: 'acked' })
  })
})

describe('DashboardView', () => {
  it('KPI 4 · 분포(막대 7개·SLA 선·범례) · 최근 전송(최신 위)', async () => {
    const w = mount(DashboardView)
    await flushPromises()
    const tiles = w.findAll('.stat')
    expect(tiles).toHaveLength(4)
    expect(tiles[0].text()).toContain('25초')
    expect(tiles[3].get('.stat__value').classes()).toContain('stat__value--danger')
    expect(w.findAll('svg.hist path')).toHaveLength(7)
    expect(w.get('.hist__marker text').text()).toBe('SLA 30초')
    expect(w.findAll('.legend__item').map((l) => l.text())).toEqual(['SLOT_SET', 'RESV_SET'])
    expect(w.findAll('tbody tr').map((r) => r.findAll('td')[2].text())).toEqual(['대기', '31.5초'])
    expect(w.get('tbody tr:last-child .dash__slow').text()).toBe('31.5초')
    w.unmount()
  })

  it('전송 0건 — KPI 는 —, 차트 자리에 빈 상태, 막대 없음', async () => {
    latencyApi.mockResolvedValue(EMPTY)
    failedApi.mockResolvedValue([])
    recentApi.mockResolvedValue([])
    const w = mount(DashboardView)
    await flushPromises()
    expect(w.findAll('.stat__value').map((v) => v.text())).toEqual(['—', '—', '—', '0건'])
    expect(w.text()).toContain('아직 전송된 작업이 없습니다')
    expect(w.find('svg.hist').exists()).toBe(false)
    w.unmount()
  })

  it('기간 — 기본 최근 7일(KST 날짜), 30일로 바꾸면 from 이 29일 앞', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-09-24T16:00:00Z')) // KST 9/25 01:00 — UTC 로는 아직 9/24
    const w = mount(DashboardView)
    await flushPromises()
    expect(latencyApi).toHaveBeenCalledWith({ from: '2026-09-19', to: '2026-09-25', type: 'all' })
    expect(failedApi).toHaveBeenCalledWith(7)
    expect(recentApi).toHaveBeenCalledWith(7)
    await w.get('select').setValue('30')
    await flushPromises()
    expect(latencyApi).toHaveBeenLastCalledWith({
      from: '2026-08-27',
      to: '2026-09-25',
      type: 'RESV_SET',
    })
    expect(failedApi).toHaveBeenLastCalledWith(30)
    w.unmount()
  })

  it('60초마다 다시 읽고, 떠나면 멈춘다', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    const w = mount(DashboardView)
    await flushPromises()
    expect(failedApi).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(60_000)
    await flushPromises()
    expect(failedApi).toHaveBeenCalledTimes(2)
    w.unmount()
    vi.advanceTimersByTime(180_000)
    await flushPromises()
    expect(failedApi).toHaveBeenCalledTimes(2)
  })

  it('갱신 실패 — 숫자를 지우지 않고 Toast 는 한 번 (Review Focus 1)', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    const w = mount(DashboardView)
    await flushPromises()
    failedApi.mockRejectedValue(new ApiError(0, MESSAGES[0]))
    for (let i = 0; i < 3; i++) {
      vi.advanceTimersByTime(60_000)
      await flushPromises()
    }
    expect(w.findAll('.stat')[0].text()).toContain('25초')
    expect(toasts.value.filter((t) => t.tone === 'danger')).toHaveLength(1)
    w.unmount()
  })
})
