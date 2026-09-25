import { readonly, ref } from 'vue'
import type { LoginOut } from '@/api/types'

// JWT 는 메모리에만 (auth.md). 앱(페이지)마다 모듈이 따로라 관리자·학생 세션이 섞이지 않는다.
export type AuthNotice = 'expired' | 'forbidden'

const current = ref<LoginOut | null>(null)
export const session = readonly(current)
export const authNotice = ref<AuthNotice | null>(null)

let onFailure: ((n: AuthNotice) => void) | null = null
export function onAuthFailure(cb: (n: AuthNotice) => void): void {
  onFailure = cb
}

export function setSession(s: LoginOut): void {
  current.value = s
  authNotice.value = null
}

/** 로그아웃 API 는 없다 — 토큰을 버리는 것이 로그아웃이다. notice 가 있으면 앱이 로그인 화면으로 보낸다. */
export function clearSession(notice?: AuthNotice): void {
  current.value = null
  if (notice) {
    authNotice.value = notice
    onFailure?.(notice)
  }
}
