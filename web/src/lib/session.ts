import { readonly, ref } from 'vue'
import type { LoginOut, Role } from '@/api/types'

// JWT 는 sessionStorage 에 (auth.md 미결 2) — 새로고침은 살고, 탭을 닫으면 사라진다. localStorage 는 여전히 금지.
// 앱마다 자기 키라 같은 탭에서 관리자·학생 세션이 섞이지 않는다.
export type AuthNotice = 'expired' | 'forbidden' | 'idle'

const current = ref<LoginOut | null>(null)
export const session = readonly(current)
export const authNotice = ref<AuthNotice | null>(null)
let key: string | null = null

let onFailure: ((n: AuthNotice) => void) | null = null
export function onAuthFailure(cb: (n: AuthNotice) => void): void {
  onFailure = cb
}

/** 토큰의 exp 가 지났으면 되살리지 않는다 — 첫 요청 401 로 화면이 한 번 번쩍이지 않게 */
function alive(s: LoginOut): boolean {
  try {
    const { exp } = JSON.parse(atob(s.token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return typeof exp !== 'number' || exp * 1000 > Date.now()
  } catch {
    return false
  }
}

/** 앱 진입점이 마운트 전에 한 번 — 새로고침한 탭의 세션을 되살린다. 역할이 다르면 버린다 */
export function restoreSession(app: Role): void {
  key = `esc.session.${app}`
  try {
    const s = JSON.parse(sessionStorage.getItem(key) ?? 'null') as LoginOut | null
    if (s && s.role === app && alive(s)) return void (current.value = s)
    sessionStorage.removeItem(key)
    // 이 앱의 토큰이 만료돼 버렸다 — 말없이 로그인 화면이 뜨지 않게 401 과 같은 안내
    if (s?.role === app) authNotice.value = 'expired'
  } catch {
    // 저장소가 막힌 창(사생활 보호 등) — 메모리 세션으로 동작한다
  }
}

export function setSession(s: LoginOut): void {
  current.value = s
  authNotice.value = null
  try {
    if (key) sessionStorage.setItem(key, JSON.stringify(s))
  } catch {
    // 위와 같다
  }
}

/** 로그아웃 API 는 없다 — 토큰을 버리는 것이 로그아웃이다. notice 가 있으면 앱이 로그인 화면으로 보낸다. */
export function clearSession(notice?: AuthNotice): void {
  current.value = null
  try {
    if (key) sessionStorage.removeItem(key)
  } catch {
    // 위와 같다
  }
  if (notice) {
    authNotice.value = notice
    onFailure?.(notice)
  }
}
