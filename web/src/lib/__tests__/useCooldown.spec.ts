import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import { useCooldown } from '@/lib/useCooldown'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('useCooldown', () => {
  it('10초 잠갔다가 풀린다 (Review Focus 5)', async () => {
    const scope = effectScope()
    const c = scope.run(() => useCooldown())!
    c.start(10)
    expect(c.active.value).toBe(true)
    expect(c.remaining.value).toBe(10)
    await vi.advanceTimersByTimeAsync(9000)
    expect(c.remaining.value).toBe(1)
    await vi.advanceTimersByTimeAsync(1000)
    expect(c.active.value).toBe(false)
    expect(c.remaining.value).toBe(0)
    scope.stop()
  })

  it('다시 start 하면 처음부터', async () => {
    const scope = effectScope()
    const c = scope.run(() => useCooldown())!
    c.start(60)
    await vi.advanceTimersByTimeAsync(30_000)
    c.start(60)
    expect(c.remaining.value).toBe(60)
    scope.stop()
  })
})
