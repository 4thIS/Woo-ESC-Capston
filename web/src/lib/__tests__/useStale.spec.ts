import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope, shallowRef } from 'vue'
import { kstDateStr } from '@/lib/time'
import { useStale } from '@/lib/useStale'

afterEach(() => vi.useRealTimers())

describe('kstDateStr', () => {
  it('KST 자정 경계 — UTC 15:00 이 KST 다음 날 00:00', () => {
    expect(kstDateStr(new Date('2026-09-24T14:59:59Z'))).toBe('2026-09-24')
    expect(kstDateStr(new Date('2026-09-24T15:00:00Z'))).toBe('2026-09-25')
  })
  it('offsetDays 로 앞뒤 날짜 (월 경계 포함)', () => {
    expect(kstDateStr(new Date('2026-09-24T16:00:00Z'), -6)).toBe('2026-09-19')
    expect(kstDateStr(new Date('2026-09-24T16:00:00Z'), -29)).toBe('2026-08-27')
  })
})

describe('useStale', () => {
  it('5분이 지나면 stale, 새 갱신이 오면 풀린다', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
    vi.setSystemTime(new Date('2026-09-25T00:00:00Z'))
    const at = shallowRef<Date | null>(new Date())
    const scope = effectScope()
    const { stale } = scope.run(() => useStale(at))!
    expect(stale.value).toBe(false)
    vi.advanceTimersByTime(4 * 60_000 + 59_000) // 마지막 틱 4:45
    expect(stale.value).toBe(false)
    vi.advanceTimersByTime(15_000) // 5:00 틱
    expect(stale.value).toBe(true)
    at.value = new Date()
    expect(stale.value).toBe(false)
    scope.stop()
  })

  it('한 번도 받지 못했으면(null) stale 이 아니다 — 표시 자체가 없다', () => {
    const scope = effectScope()
    const { stale } = scope.run(() => useStale(() => null))!
    expect(stale.value).toBe(false)
    scope.stop()
  })
})
