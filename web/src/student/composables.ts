import { onScopeDispose, ref } from 'vue'

/** 자동 새로고침 (student-room.md §상태) — 탭이 숨으면 usePolling 이 멈춘다 */
export const POLL_MS = 60_000
/** bp.tablet 이상 (tokens.md 640px) — 넓은 폭은 같은 라우트에서 더 보여준다 */
export const WIDE_QUERY = '(min-width: 640px)'

export function useWide() {
  const mq = window.matchMedia(WIDE_QUERY)
  const wide = ref(mq.matches)
  const on = (e: { matches: boolean }) => {
    wide.value = e.matches
  }
  mq.addEventListener('change', on)
  onScopeDispose(() => mq.removeEventListener('change', on))
  return wide
}

/** 화면 시계 — '지금' 행·체크인 창·지난 시작 시각. 네트워크 없이 흐른다 */
export function useNow(ms = 15_000) {
  const now = ref(new Date())
  const timer = setInterval(() => {
    now.value = new Date()
  }, ms)
  onScopeDispose(() => clearInterval(timer))
  return now
}
