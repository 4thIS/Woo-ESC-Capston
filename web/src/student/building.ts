import { computed, inject, watch, type InjectionKey, type Ref } from 'vue'
import { useRoute } from 'vue-router'
import { studentApi } from '@/api/student'
import type { RoomStateOut, WeekOut } from '@/api/types'
import { gridRange, nowTop, visibleDays, weekBlocks } from '@/components/student/grid'
import { dayOfDate, kstDateStr, kstMinutes, mondayOf } from '@/lib/time'
import { usePolling } from '@/lib/usePolling'
import { useResource } from '@/lib/useResource'
import { POLL_MS, useNow } from './composables'

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

/** 자식 화면 공용 — 주소의 글자·호수를 레이아웃 목록에서 room_id 로 풀고 주간을 부른다.
 * 목록에 없으면(없는 호수·예약 안 받는 방·다른 학교) 또는 주간이 404 면 notFound */
export function useRoomWeek(opts: { poll: boolean }) {
  const ctx = useBuilding()
  const route = useRoute()
  const bld = computed(() => String(route.params.bld))
  const roomNo = computed(() => Number(route.params.room))
  const room = computed(
    () => ctx.rooms.value?.find((r) => r.bld === bld.value && r.room === roomNo.value) ?? null,
  )
  const now = useNow()
  // room 이 있을 때만 부른다(아래 watch) — 방을 바꾸면 늦게 온 옛 방 응답은 useResource 가 버린다
  const { data, error, refreshedAt, reload } = useResource(
    () => studentApi.week(room.value!.room_id),
    { immediate: false },
  )
  watch(
    () => room.value?.room_id,
    (id) => {
      if (id !== undefined) void reload()
    },
    { immediate: true },
  )
  if (opts.poll)
    usePolling(async () => {
      if (room.value) await reload()
    }, POLL_MS)
  const notFound = computed(() => (ctx.loaded.value && !room.value) || error.value?.status === 404)
  const title = computed(() => `${room.value?.building ?? ''} ${roomNo.value}호`.trim())
  return {
    bld,
    roomNo,
    room,
    now,
    notFound,
    title,
    week: data,
    weekError: error,
    refreshedAt,
    reload,
  }
}

/** 주간 격자 입력 — '오늘' 표시는 서버 week_start 가 오늘의 월요일일 때만(자정 직후 한 번의 폴링 사이 어긋남) */
export function useWeekGrid(
  week: Readonly<Ref<WeekOut | undefined>>,
  now: Readonly<Ref<Date>>,
  rowPx: 24 | 32,
) {
  const busy = computed(() => week.value?.busy ?? [])
  const range = computed(() => gridRange(busy.value))
  const days = computed(() => visibleDays(busy.value))
  const blocks = computed(() => weekBlocks(busy.value, range.value, rowPx))
  const today = computed(() => kstDateStr(now.value))
  const todayIndex = computed(() =>
    week.value?.week_start === mondayOf(today.value)
      ? days.value.indexOf(dayOfDate(today.value))
      : -1,
  )
  const nowY = computed(() =>
    todayIndex.value < 0 ? null : nowTop(kstMinutes(now.value), range.value, rowPx),
  )
  return { days, blocks, range, todayIndex, nowY }
}
