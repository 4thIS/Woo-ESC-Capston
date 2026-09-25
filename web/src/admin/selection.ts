import { ref } from 'vue'

// 관리자 화면 사이에서 이어지는 선택 — 모듈 메모리라 다른 화면을 다녀와도 남고, 새로고침이면 사라진다
// (JWT 가 메모리에만 있어 새로고침 = 재로그인이라 같은 수명이다)

/** 페이지1 트리에서 고른 강의실 id — 비면 첫 건물의 첫 층으로 채운다 */
export const picked = ref<number[]>([])
/** 페이지2 — 마지막으로 본 강의실(메뉴 링크), 보고 있는 주의 월요일(강의실을 바꿔도 유지) */
export const weekRoom = ref<number | null>(null)
export const weekMonday = ref<string | null>(null)
/** 야간·주말 보기 — null 이면 자동(필요한 블록이 있으면 켬), 사용자가 누르면 그 선택을 유지 */
export const nightPref = ref<boolean | null>(null)
export const weekendPref = ref<boolean | null>(null)
