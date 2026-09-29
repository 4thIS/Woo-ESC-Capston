import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import { usePolling } from '@/lib/usePolling'

let visibility: DocumentVisibilityState = 'visible'
beforeEach(() => {
  vi.useFakeTimers()
  visibility = 'visible'
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => visibility })
})
afterEach(() => vi.useRealTimers())
const setVisibility = (v: DocumentVisibilityState) => {
  visibility = v
  document.dispatchEvent(new Event('visibilitychange'))
}

describe('usePolling', () => {
  it('주기마다 부르고, 숨김이면 건너뛴다', async () => {
    const fn = vi.fn().mockResolvedValue(undefined)
    const scope = effectScope()
    scope.run(() => usePolling(fn, 1000))
    await vi.advanceTimersByTimeAsync(1000)
    expect(fn).toHaveBeenCalledTimes(1)
    setVisibility('hidden')
    await vi.advanceTimersByTimeAsync(3000)
    expect(fn).toHaveBeenCalledTimes(1)
    scope.stop()
  })

  it('다시 보이면 즉시 1회', async () => {
    const fn = vi.fn().mockResolvedValue(undefined)
    const scope = effectScope()
    scope.run(() => usePolling(fn, 60_000))
    setVisibility('hidden')
    setVisibility('visible')
    await vi.advanceTimersByTimeAsync(0)
    expect(fn).toHaveBeenCalledTimes(1)
    scope.stop()
  })

  it('이전 호출이 안 끝났으면 이번 틱은 건너뛴다 (겹침 금지)', async () => {
    let finish!: () => void
    const fn = vi.fn(() => new Promise<void>((r) => (finish = r)))
    const scope = effectScope()
    scope.run(() => usePolling(fn, 1000))
    await vi.advanceTimersByTimeAsync(3000)
    expect(fn).toHaveBeenCalledTimes(1)
    finish()
    await vi.advanceTimersByTimeAsync(1000)
    expect(fn).toHaveBeenCalledTimes(2)
    scope.stop()
  })

  it('scope 가 끝나면 멈추고 리스너도 뗀다', async () => {
    const fn = vi.fn().mockResolvedValue(undefined)
    const scope = effectScope()
    scope.run(() => usePolling(fn, 1000))
    scope.stop()
    setVisibility('visible')
    await vi.advanceTimersByTimeAsync(5000)
    expect(fn).not.toHaveBeenCalled()
  })
})
