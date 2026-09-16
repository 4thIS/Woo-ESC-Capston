import { createRouter, createWebHistory } from 'vue-router'

// 화면은 docs/design/screens/*.md 스펙이 나온 뒤 채운다. 지금은 진입점 2개만.
export const routes = [
  { path: '/', redirect: '/admin' },
  { path: '/admin', name: 'admin', component: () => import('@/views/AdminHome.vue') },
  { path: '/student', name: 'student', component: () => import('@/views/StudentHome.vue') },
]

export default createRouter({ history: createWebHistory(), routes })
