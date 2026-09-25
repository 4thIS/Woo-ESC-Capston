import { inject, type InjectionKey, type Ref } from 'vue'
import type { RoomStateOut } from '@/api/types'

/** /:bld 레이아웃이 학교 방 목록을 한 번 불러 자식 화면(강의실·주간·예약)에 준다 — room_id 를 푸는 한 곳 */
export interface BuildingCtx {
  rooms: Readonly<Ref<RoomStateOut[] | undefined>>
  loaded: Readonly<Ref<boolean>>
  reload: () => Promise<void>
}
export const BUILDING: InjectionKey<BuildingCtx> = Symbol('building')

export function useBuilding(): BuildingCtx {
  const ctx = inject(BUILDING)
  if (!ctx) throw new Error('useBuilding 은 /:bld 레이아웃 안에서만 쓴다')
  return ctx
}
