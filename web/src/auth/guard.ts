import type { Router } from 'vue-router'
import { onAuthFailure, session } from '@/lib/session'

/** 인증 라우트 가드 + 401/403 이면 로그인으로 (spec §4.2). 두 앱 라우터가 똑같이 부른다 */
export function installAuth(router: Router): void {
  router.beforeEach((to) =>
    to.meta.auth && !session.value ? { path: '/login', query: { next: to.fullPath } } : true,
  )
  onAuthFailure(() => {
    const cur = router.currentRoute.value
    if (cur.path !== '/login') void router.push({ path: '/login', query: { next: cur.fullPath } })
  })
}
