import { ref, watch } from 'vue'
import { session } from '@/lib/session'

// 관리자 화면 사이에서 이어지는 선택 — 모듈 메모리라 다른 화면을 다녀와도 남는다.
// 세션과 같은 수명: 로그아웃·만료(세션이 비면) 지운다 — 같은 탭의 다음 관리자(다른 학교일 수 있다)에게
// 앞 사람의 강의실·주가 남지 않게. 새로고침도 JWT 가 메모리에만 있어 재로그인이라 함께 사라진다

/** 페이지1 트리에서 고른 강의실 id — 비면 첫 건물의 첫 층으로 채운다 */
export const picked = ref<number[]>([])
/** 페이지2 — 마지막으로 본 강의실(메뉴 링크), 보고 있는 주의 월요일(강의실을 바꿔도 유지) */
export const weekRoom = ref<number | null>(null)
export const weekMonday = ref<string | null>(null)
/** 야간·주말 보기 — null 이면 자동(필요한 블록이 있으면 켬), 사용자가 누르면 그 선택을 유지 */
export const nightPref = ref<boolean | null>(null)
export const weekendPref = ref<boolean | null>(null)

export function resetSelection(): void {
  picked.value = []
  weekRoom.value = null
  weekMonday.value = null
  nightPref.value = null
  weekendPref.value = null
}
watch(session, (s) => !s && resetSelection(), { flush: 'sync' })
