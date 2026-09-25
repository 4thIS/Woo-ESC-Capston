import { createRouter, createWebHistory, type RouteRecordRaw, type RouterHistory } from 'vue-router'

export const routes: RouteRecordRaw[] = [
  { path: '/', component: () => import('./views/HomeView.vue') },
]

export function makeRouter(history: RouterHistory = createWebHistory('/')) {
  return createRouter({ history, routes })
}
