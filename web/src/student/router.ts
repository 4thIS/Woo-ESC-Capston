import { createRouter, createWebHistory, type RouteRecordRaw, type RouterHistory } from 'vue-router'
import { installAuth } from '@/auth/guard'

export const routes: RouteRecordRaw[] = [
  { path: '/', component: () => import('./views/HomeView.vue'), meta: { auth: true } },
  { path: '/login', component: () => import('@/auth/LoginView.vue'), props: { app: 'student' } },
  { path: '/signup', component: () => import('@/auth/SignupView.vue') },
  { path: '/verify', component: () => import('@/auth/VerifyView.vue') },
  { path: '/forgot', component: () => import('@/auth/ForgotView.vue') },
  { path: '/reset', component: () => import('@/auth/ResetView.vue') },
]

export function makeRouter(history: RouterHistory = createWebHistory('/')) {
  const router = createRouter({ history, routes })
  installAuth(router)
  return router
}
