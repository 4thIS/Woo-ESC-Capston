// 학생 화면 계산 (순수 함수) — 판정은 서버가 준 값(layout·busy·free)을 쓴다
import type { BusySpan, FreeDay, FreeRange, RoomStateOut, SlotType } from '@/api/types'
import { FREE_LAYOUT, hmToMin, minToHm } from '@/components/student/rules'

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
