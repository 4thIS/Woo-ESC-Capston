import { createRouter, createWebHistory, type RouteRecordRaw, type RouterHistory } from 'vue-router'
import { installAuth } from '@/auth/guard'

export const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: () => import('./AdminShell.vue'),
    meta: { auth: true },
    children: [
      // 관리자 기본 화면은 전송 현황 (spec §5)
      { path: '', redirect: '/dashboard' },
      { path: 'nodes', component: () => import('./views/NodesView.vue') },
      { path: 'dashboard', component: () => import('./views/DashboardView.vue') },
      { path: 'users', component: () => import('./views/UsersView.vue') },
    ],
  },
  { path: '/login', component: () => import('@/auth/LoginView.vue'), props: { app: 'admin' } },
]

export function makeRouter(history: RouterHistory = createWebHistory('/admin/')) {
  const router = createRouter({ history, routes })
  installAuth(router)
  return router
}
