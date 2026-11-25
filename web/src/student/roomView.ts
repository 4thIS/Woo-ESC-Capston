// 학생 화면 계산 (순수 함수) — 판정은 서버가 준 값(layout·busy·free)을 쓴다
import type { BusySpan, FreeDay, FreeRange, RoomStateOut, SlotType } from '@/api/types'
import { FREE_LAYOUT, hmToMin, isRed, minToHm } from '@/components/student/rules'
import { favKey } from './favorites'

export interface BuildingItem {
  id: number
  name: string
  bld: string
  rooms: number
  free: number
}
/** 건물 목록 — 학생용 건물 API 가 없다(spec §5 "rooms 에서 파생") */
export function buildingsOf(rooms: RoomStateOut[]): BuildingItem[] {
  const m = new Map<number, BuildingItem>()
  for (const r of rooms) {
    const b = m.get(r.building_id) ?? {
      id: r.building_id,
      name: r.building,
      bld: r.bld,
      rooms: 0,
      free: 0,
    }
    b.rooms += 1
    if (r.layout === FREE_LAYOUT) b.free += 1
    m.set(r.building_id, b)
  }
  return [...m.values()].sort((a, b) => a.bld.localeCompare(b.bld))
}

/** 운영 시간 (서버 reserve.OPEN_MIN·CLOSE_MIN) — 오늘 목록의 기본 창 */
export const OPEN_MIN = 9 * 60
export const CLOSE_MIN = 21 * 60

export interface TodayRow {
  from: string
  to: string
  label: string
  /** null = 빈 구간 행 */
  type: SlotType | null
  mine: boolean
  requested: boolean
  now: boolean
}
/** 오늘 목록 — 빈 구간도 행으로(학생이 언제 비는지 계산하지 않게). spans 는 서버가 합쳐 겹치지 않는다 */
export function todayRows(spans: BusySpan[], nowMin: number): TodayRow[] {
  const sorted = [...spans].sort((a, b) => hmToMin(a.from) - hmToMin(b.from))
  const start = Math.min(OPEN_MIN, ...sorted.map((s) => hmToMin(s.from)))
  const end = Math.max(CLOSE_MIN, ...sorted.map((s) => hmToMin(s.to)))
  const rows: TodayRow[] = []
  const isNow = (a: number, b: number) => a <= nowMin && nowMin < b
  const gap = (a: number, b: number) =>
    rows.push({
      from: minToHm(a),
      to: minToHm(b),
      label: '비어있음',
      type: null,
      mine: false,
      requested: false,
      now: isNow(a, b),
    })
  let cur = start
  for (const s of sorted) {
    const a = hmToMin(s.from)
    const b = hmToMin(s.to)
    if (a > cur) gap(cur, a)
    rows.push({
      from: s.from,
      to: s.to,
      label: s.label,
      type: s.type,
      mine: s.mine,
      requested: s.mine && s.status === 'requested',
      now: isNow(a, b),
    })
    cur = Math.max(cur, b)
  }
  if (cur < end) gap(cur, end)
  return rows
}

/** 넓은 폭 '다음 비는 시간' 카드 — 서버 free 의 오늘 첫 구간(지금 이후, 신청 가능한 것) */
export const nextFree = (free: FreeDay[]): FreeRange | null => free[0]?.spans[0] ?? null

/** 목록 숫자 칸 (student-room.md 「학생 앱 메뉴」) — 곧 비는 곳 = 사용중이고 다음 바뀌는 시각이 60분 안 */
export const SOON_MIN = 60
export function roomStats(rooms: RoomStateOut[], nowMin: number) {
  const busy = rooms.filter((r) => isRed(r.layout))
  return {
    free: rooms.filter((r) => r.layout === FREE_LAYOUT).length,
    busy: busy.length,
    soon: busy.filter((r) => r.until && hmToMin(r.until) - nowMin <= SOON_MIN).length,
  }
}

/** 넓은 폭 /{bld} 의 오른쪽 칸 — 즐겨찾기 순서의 첫 방 → 빈 첫 방 → 첫 방 */
export function defaultRoom(rooms: RoomStateOut[], favs: string[]): RoomStateOut | null {
  const byKey = new Map(rooms.map((r) => [favKey(r.bld, r.room), r]))
  const fav = favs.map((k) => byKey.get(k)).find((r) => r !== undefined)
  return fav ?? rooms.find((r) => r.layout === FREE_LAYOUT) ?? rooms[0] ?? null
}

/** 층 묶음 — 호수의 백의 자리. 층 · 호수 순 */
export function byFloor(rooms: RoomStateOut[]): { floor: number; rooms: RoomStateOut[] }[] {
  const m = new Map<number, RoomStateOut[]>()
  for (const r of [...rooms].sort((a, b) => a.room - b.room)) {
    const f = Math.floor(r.room / 100)
    m.set(f, [...(m.get(f) ?? []), r])
  }
  return [...m].sort(([a], [b]) => a - b).map(([floor, rooms]) => ({ floor, rooms }))
}

/** 인사 줄 '지금 공학관은' — 마지막 글자에 받침이 있으면 은, 없거나 한글이 아니면 는 */
export function topic(word: string): string {
  const c = word.charCodeAt(word.length - 1) - 0xac00
  return word + (c >= 0 && c < 11172 && c % 28 ? '은' : '는')
}
