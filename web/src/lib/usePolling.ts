import { onScopeDispose } from 'vue'

/** 숨김이면 건너뛰고, 보이면 즉시 1회. 이전 호출이 안 끝났으면 이번 틱은 건너뛴다 (spec §4.3). */
export function usePolling(fn: () => Promise<unknown>, ms: number) {
  let running = false
  const tick = async () => {
    if (running || document.visibilityState === 'hidden') return
    running = true
    try {
      await fn()
    } catch (e) {
      console.error(e)
    } finally {
      running = false
    }
  }
  const timer = setInterval(() => void tick(), ms)
  const onVisible = () => {
    if (document.visibilityState === 'visible') void tick()
  }
  document.addEventListener('visibilitychange', onVisible)
  const stop = () => {
    clearInterval(timer)
    document.removeEventListener('visibilitychange', onVisible)
  }
  onScopeDispose(stop)
  return { stop }
}
