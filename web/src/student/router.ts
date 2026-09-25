import {
  createRouter,
  createWebHistory,
  type RouteLocationNormalized,
  type RouteRecordRaw,
  type RouterHistory,
} from 'vue-router'
import { installAuth } from '@/auth/guard'

/** '/e/401' → '/E/401' — 폰에서 소문자로 치는 일이 흔하다 */
export function upperBld(to: RouteLocationNormalized): string | true {
  return /^\/[a-z](\/|$)/.test(to.path)
    ? to.fullPath.replace(/^\/[a-z]/, (c) => c.toUpperCase())
    : true
}

// 학생 화면은 전부 로그인 필요(S10 §3) — meta.gate 면 StudentApp 이 그 주소 그대로 로그인 벽을 그린다.
// 세션 중 401 은 installAuth(F1)가 /login?next= 로 보낸다.
export const routes: RouteRecordRaw[] = [
  { path: '/', component: () => import('./views/HomeView.vue'), meta: { gate: true } },
  { path: '/login', component: () => import('@/auth/LoginView.vue'), props: { app: 'student' } },
  { path: '/signup', component: () => import('@/auth/SignupView.vue') },
  { path: '/verify', component: () => import('@/auth/VerifyView.vue') },
  { path: '/forgot', component: () => import('@/auth/ForgotView.vue') },
  { path: '/reset', component: () => import('@/auth/ResetView.vue') },
  // 건물 글자는 대문자 한 글자 — sensitive 로 소문자는 여기서 받지 않고 404 라우트가 대문자로 보낸다
  {
    path: '/:bld([A-Z])',
    sensitive: true,
    component: () => import('./views/BuildingLayout.vue'),
    meta: { gate: true },
    children: [],
  },
  // 없는 주소 — 벽 없이 404 (보여줄 데이터가 없다)
  {
    path: '/:pathMatch(.*)*',
    component: () => import('./views/NotFoundView.vue'),
    beforeEnter: upperBld,
  },
]

export function makeRouter(history: RouterHistory = createWebHistory('/')) {
  // 전역 sensitive — vue-router 는 부모의 sensitive 를 자식에 내려주지 않는다. 없으면 /e/401 이
  // /:bld([A-Z])/:room 에 대소문자 무시로 먼저 걸려 upperBld 가 돌지 않는다
  const router = createRouter({ history, routes, sensitive: true })
  installAuth(router)
  return router
}
