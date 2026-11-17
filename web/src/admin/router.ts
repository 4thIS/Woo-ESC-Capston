import { createRouter, createWebHistory, type RouteRecordRaw, type RouterHistory } from 'vue-router'
import { installAuth } from '@/auth/guard'

// 셸 안의 화면 청크 — 라우트와 미리 받기(prefetchViews)가 같은 import 를 쓴다
export const views = {
  master: () => import('./views/MasterView.vue'),
  rooms: () => import('./views/RoomsView.vue'),
  week: () => import('./views/WeekView.vue'),
  nodes: () => import('./views/NodesView.vue'),
  dashboard: () => import('./views/DashboardView.vue'),
  users: () => import('./views/UsersView.vue'),
  notFound: () => import('./views/NotFoundView.vue'),
}

/** 지연 로딩한 화면은 처음 누를 때 청크를 받을 때까지 이전 화면에 멈춰 있다(왕복 400ms 망에서 약 0.5~1 s).
 * 셸이 뜬 뒤 미리 받아 두면 첫 클릭도 캐시에서 바로 바뀐다. 실패해도 그 화면을 누를 때 다시 받는다 */
export async function prefetchViews(): Promise<void> {
  await Promise.allSettled(Object.values(views).map((load) => load()))
}

export const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: () => import('./AdminShell.vue'),
    meta: { auth: true },
    children: [
      // 관리자 기본 화면은 전송 현황 (spec §5)
      { path: '', redirect: '/dashboard' },
      { path: 'master', component: views.master },
      { path: 'rooms', component: views.rooms },
      { path: 'week', component: views.week },
      { path: 'rooms/:roomId(\\d+)/week', component: views.week, props: true },
      { path: 'nodes', component: views.nodes },
      { path: 'dashboard', component: views.dashboard },
      { path: 'users', component: views.users },
      { path: ':pathMatch(.*)*', component: views.notFound },
    ],
  },
  { path: '/login', component: () => import('@/auth/LoginView.vue'), props: { app: 'admin' } },
]

export function makeRouter(history: RouterHistory = createWebHistory('/admin/')) {
  const router = createRouter({ history, routes })
  installAuth(router)
  return router
}
