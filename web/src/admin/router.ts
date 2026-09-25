import { createRouter, createWebHistory, type RouteRecordRaw, type RouterHistory } from 'vue-router'
import { installAuth } from '@/auth/guard'

export const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: () => import('./AdminShell.vue'),
    meta: { auth: true },
    children: [
      { path: '', redirect: '/users' },
      { path: 'nodes', component: () => import('./views/NodesView.vue') },
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
