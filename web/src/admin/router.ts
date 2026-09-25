import { createRouter, createWebHistory, type RouteRecordRaw, type RouterHistory } from 'vue-router'
import { installAuth } from '@/auth/guard'

export const routes: RouteRecordRaw[] = [
  { path: '/', component: () => import('./views/PlaceholderView.vue'), meta: { auth: true } },
  { path: '/login', component: () => import('@/auth/LoginView.vue'), props: { app: 'admin' } },
]

export function makeRouter(history: RouterHistory = createWebHistory('/admin/')) {
  const router = createRouter({ history, routes })
  installAuth(router)
  return router
}
