import { vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ref, type Component, type DefineComponent } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { RoomStateOut } from '@/api/types'
import { BUILDING } from '@/student/building'

export const blank = { render: () => null }
export const roomState = (over: Partial<RoomStateOut> = {}): RoomStateOut => ({
  room_id: 11,
  building_id: 3,
  building: '공학관',
  bld: 'E',
  room: 401,
  layout: 4,
  until: '13:00',
  ...over,
})

/** pattern 경로에 component 를 둔 라우터로 path 에 간 뒤 올린다. rooms 를 주면 /:bld 레이아웃처럼 BUILDING 을 준다 */
export async function mountAt(
  component: Component,
  path: string,
  pattern: string,
  rooms?: RoomStateOut[],
) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: pattern, component },
      { path: '/:rest(.*)*', component: blank },
    ],
  })
  await router.push(path)
  await router.isReady()
  const provide = rooms
    ? {
        [BUILDING as symbol]: {
          rooms: ref(rooms),
          loaded: ref(true),
          reload: vi.fn(async () => {}),
        },
      }
    : {}
  const w = mount(component as DefineComponent, {
    global: { plugins: [router], provide, stubs: { teleport: true } },
  })
  await flushPromises()
  return { w, router }
}

/** jsdom 에 matchMedia 가 없다 — 넓은 폭 여부와 바뀜 알림 */
export function stubMedia(wide: boolean) {
  let listener: ((e: { matches: boolean }) => void) | null = null
  vi.stubGlobal('matchMedia', () => ({
    matches: wide,
    addEventListener: (_: string, l: (e: { matches: boolean }) => void) => {
      listener = l
    },
    removeEventListener: () => {},
  }))
  return { change: (matches: boolean) => listener?.({ matches }) }
}
