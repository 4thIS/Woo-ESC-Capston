import { computed, onScopeDispose, ref } from 'vue'
import { session } from '@/lib/session'

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

export { useNow } from '@/lib/useNow'

/** 로그인 뒤 헤더·사이드바의 이름 — 그 학생의 학교. 학교 이름을 모르는 옛 세션·로그인 전은 'ESC' */
export const schoolTitle = computed(() => session.value?.school_name || 'ESC')
