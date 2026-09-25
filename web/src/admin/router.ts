import { createRouter, createWebHistory, type RouteRecordRaw, type RouterHistory } from 'vue-router'
import { installAuth } from '@/auth/guard'
import LoginView from '@/auth/LoginView.vue'

export const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: () => import('./AdminShell.vue'),
    meta: { auth: true },
    children: [
      { path: '', redirect: '/users' },
      { path: 'users', component: () => import('./views/UsersView.vue') },
    ],
  },
  // 로그아웃 등 인증 실패 시 즉시 넘어가야 하는 화면 — 지연 로드하지 않는다(코드 분할보다 응답성 우선)
  { path: '/login', component: LoginView, props: { app: 'admin' } },
]

export function makeRouter(history: RouterHistory = createWebHistory('/admin/')) {
  const router = createRouter({ history, routes })
  installAuth(router)
  return router
}
