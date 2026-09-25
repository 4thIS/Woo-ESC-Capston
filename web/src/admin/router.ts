import { createRouter, createWebHistory, type RouteRecordRaw, type RouterHistory } from 'vue-router'

export const routes: RouteRecordRaw[] = [
  { path: '/', component: () => import('./views/PlaceholderView.vue') },
]

export function makeRouter(history: RouterHistory = createWebHistory('/admin/')) {
  return createRouter({ history, routes })
}
