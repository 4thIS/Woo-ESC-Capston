import { onScopeDispose, ref } from 'vue'

/** 지금 시각 — ms 마다 다시 잡는다. 시간에 따라 바뀌는 판정(체크인 창·사용중·로그로 넘김)이 화면을 켜 둔 채로도 넘어가게 */
export function useNow(ms = 15_000) {
  const now = ref(new Date())
  const timer = setInterval(() => {
    now.value = new Date()
  }, ms)
  onScopeDispose(() => clearInterval(timer))
  return now
}
