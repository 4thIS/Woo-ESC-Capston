import { computed, onScopeDispose, ref } from 'vue'

/** 버튼 잠금 초 세기 — 429 뒤 10초, 메일 재전송 60초. 서버가 남은 시간을 주지 않아 고정값이다. */
export function useCooldown() {
  const remaining = ref(0)
  let timer: ReturnType<typeof setInterval> | null = null
  const clear = () => {
    if (timer) clearInterval(timer)
    timer = null
  }
  function start(sec: number) {
    clear()
    remaining.value = sec
    timer = setInterval(() => {
      remaining.value -= 1
      if (remaining.value <= 0) {
        remaining.value = 0
        clear()
      }
    }, 1000)
  }
  onScopeDispose(clear)
  return { remaining, active: computed(() => remaining.value > 0), start }
}
