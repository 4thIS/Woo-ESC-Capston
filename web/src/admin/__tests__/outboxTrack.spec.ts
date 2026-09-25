import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import { dotOf, useOutboxTracker, worst } from '@/admin/outboxTrack'
import { roomsApi } from '@/api/rooms'
import { loraApi } from '@/api/lora'
import { ApiError, MESSAGES } from '@/api/client'
import type { FailedOut } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/rooms', () => ({ roomsApi: { buildingOutbox: vi.fn() } }))
vi.mock('@/api/lora', () => ({ loraApi: { syncRoom: vi.fn() } }))
const api = vi.mocked(roomsApi)
const lora = vi.mocked(loraApi)
const row = (id: number, state: string, last_error: string | null = null) =>
  ({ id, state, last_error }) as unknown as FailedOut

let scope: ReturnType<typeof effectScope>
function start() {
  scope = effectScope()
  return scope.run(() => useOutboxTracker())!
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
  api.buildingOutbox.mockReset()
  lora.syncRoom.mockReset()
  for (const t of [...toasts.value]) dismissToast(t.id)
})
afterEach(() => {
  scope?.stop()
  vi.useRealTimers()
})

describe('dotOf · worst', () => {
  it('관리자 취소는 두 모양(queued→cancelled, dispatched 뒤 failed+cancelled)을 같게 그린다', () => {
    expect(dotOf(row(1, 'cancelled'))).toBe('cancelled')
    expect(dotOf(row(1, 'failed', 'cancelled'))).toBe('cancelled')
    expect(dotOf(row(1, 'failed', 'max_retries'))).toBe('failed')
  })
  it('한 저장이 작업 여럿이면 — 실패 > 취소 > 대기 > 전송 중 > 반영됨', () => {
    expect(worst(['acked', 'queued'])).toBe('queued')
    expect(worst(['acked', 'dispatched'])).toBe('dispatched')
    expect(worst(['acked', 'failed', 'queued'])).toBe('failed')
    expect(worst(['acked', 'acked'])).toBe('acked')
  })
})

describe('useOutboxTracker', () => {
  it('track → 대기로 시작, 3초마다 건물 outbox 에서 찾고, 끝난 상태면 더 묻지 않는다', async () => {
    const t = start()
    api.buildingOutbox.mockResolvedValue([row(7, 'dispatched')])
    t.track('s11-1-9-0', 3, [7])
    expect(t.states.get('s11-1-9-0')).toBe('queued')
    await vi.advanceTimersByTimeAsync(3_000)
    expect(api.buildingOutbox).toHaveBeenCalledWith(3)
    expect(t.states.get('s11-1-9-0')).toBe('dispatched')
    api.buildingOutbox.mockResolvedValue([row(7, 'acked')])
    await vi.advanceTimersByTimeAsync(3_000)
    expect(t.states.get('s11-1-9-0')).toBe('acked')
    api.buildingOutbox.mockClear()
    await vi.advanceTimersByTimeAsync(9_000)
    expect(api.buildingOutbox).not.toHaveBeenCalled()
  })

  it('30초가 지나면 멈추고 점은 마지막 상태로 남는다', async () => {
    const t = start()
    api.buildingOutbox.mockResolvedValue([row(7, 'queued')])
    t.track('r7', 3, [7])
    await vi.advanceTimersByTimeAsync(33_000)
    expect(api.buildingOutbox).toHaveBeenCalledTimes(10)
    api.buildingOutbox.mockClear()
    await vi.advanceTimersByTimeAsync(9_000)
    expect(api.buildingOutbox).not.toHaveBeenCalled()
    expect(t.states.get('r7')).toBe('queued')
  })

  it('빈 outbox_ids 는 추적하지 않는다 — 예정 판정은 화면이 (pushed_at·날짜)', async () => {
    const t = start()
    t.track('r8', 3, [])
    expect(t.states.has('r8')).toBe(false)
    await vi.advanceTimersByTimeAsync(3_000)
    expect(api.buildingOutbox).not.toHaveBeenCalled()
  })

  it('조회가 실패하면 다음 틱에 다시', async () => {
    const t = start()
    api.buildingOutbox
      .mockRejectedValueOnce(new ApiError(0, MESSAGES[0]))
      .mockResolvedValue([row(7, 'failed', 'max_retries')])
    t.track('x7', 3, [7])
    await vi.advanceTimersByTimeAsync(3_000)
    expect(t.states.get('x7')).toBe('queued')
    await vi.advanceTimersByTimeAsync(3_000)
    expect(t.states.get('x7')).toBe('failed')
  })

  it('재전송 — 방 단위 sync 뒤 새 작업을 대기부터 다시 따라간다', async () => {
    const t = start()
    lora.syncRoom.mockResolvedValue({ outbox_ids: [9, 10], id: null })
    await t.resync(['s11-1-9-0'], 11, 3)
    expect(lora.syncRoom).toHaveBeenCalledWith(11)
    expect(t.states.get('s11-1-9-0')).toBe('queued')
    expect(toasts.value.at(-1)?.message).toBe('다시 보냈습니다.')
    lora.syncRoom.mockRejectedValue(new ApiError(500, MESSAGES[500]))
    await t.resync(['s11-1-9-0'], 11, 3)
    expect(toasts.value.at(-1)).toMatchObject({ tone: 'danger', message: MESSAGES[500] })
  })

  it('재전송 중에는 같은 방을 다시 보내지 않고, 넘긴 행 전부를 새 작업으로 따라간다', async () => {
    const t = start()
    let done!: (v: { outbox_ids: number[]; id: null }) => void
    lora.syncRoom.mockReturnValue(new Promise((r) => (done = r)))
    const first = t.resync(['s11-1-9-0', 'r5'], 11, 3)
    expect(t.resyncing.has(11)).toBe(true)
    await t.resync(['s11-1-9-0'], 11, 3)
    expect(lora.syncRoom).toHaveBeenCalledTimes(1)
    done({ outbox_ids: [9], id: null })
    await first
    expect(t.resyncing.has(11)).toBe(false)
    expect([t.states.get('s11-1-9-0'), t.states.get('r5')]).toEqual(['queued', 'queued'])
  })
})
