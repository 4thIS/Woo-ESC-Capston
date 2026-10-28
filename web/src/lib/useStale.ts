import { computed, onScopeDispose, ref, toValue, type MaybeRefOrGetter } from 'vue'

/** 마지막 갱신이 이만큼 지나면 danger (spec §4.3 — student-room 규칙, 관리자도 같다) */
export const STALE_MS = 5 * 60_000

/** refreshedAt 이 STALE_MS 이상 지났는가. 시계는 tickMs 마다 한 번 본다 — 폴링이 멈춰도(끊김·숨김) 판정은 흐른다 */
export function useStale(at: MaybeRefOrGetter<Date | null>, tickMs = 15_000) {
  const now = ref(Date.now())
  const timer = setInterval(() => (now.value = Date.now()), tickMs)
  onScopeDispose(() => clearInterval(timer))
  const stale = computed(() => {
    const t = toValue(at)
    return !!t && now.value - t.getTime() >= STALE_MS
  })
  return { stale }
}
