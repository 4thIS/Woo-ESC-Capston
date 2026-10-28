import { ref } from 'vue'
import { usersApi } from '@/api/users'
import { ApiError } from '@/api/client'

/** 사이드 메뉴 `회원` 옆 대기 건수 (admin-users.md) — 이 화면이 막히면 학생 웹 전체가 막힌다 */
export const pendingCount = ref(0)

export async function refreshPending(): Promise<void> {
  try {
    pendingCount.value = (await usersApi.list('pending_approval')).length
  } catch (e) {
    if (!(e instanceof ApiError)) throw e // 네트워크·401 은 client 가 처리 — 배지는 옛 값을 둔다
  }
}
