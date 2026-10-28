// 주간 격자 배치 — 겹침 합치기는 서버(WeekOut.busy)가 이미 했다. 여기는 위치만 (student-room.md §겹침)
import type { BusyDay, BusySpan, SlotType } from '@/api/types'
import { hmToMin } from './rules'

export const ROW_MIN = 30
const GRID_START = 9 * 60
const GRID_END = 18 * 60

export interface GridRange {
  start: number
  end: number
}
export interface GridBlock {
  day: number
  top: number
  height: number
  label: string
  /** 'HH:MM–HH:MM' */
  extra: string
  type: SlotType
  mine: boolean
  /** 내 신청(대기) — brand 점선 테두리 */
  requested: boolean
}

/** 빈강의실(4)은 칠하지 않는다 (tokens.md 「비어있음은 칠하지 않는다」) */
const drawn = (s: BusySpan) => s.type !== 4

/** 09–18 이 기본, 벗어난 블록이 있으면 30분 단위로 편다 ("해당 슬롯이 있으면 자동으로 편다") */
export function gridRange(busy: BusyDay[]): GridRange {
  const spans = busy.flatMap((d) => d.spans.filter(drawn))
  return {
    start: Math.min(
      GRID_START,
      ...spans.map((s) => Math.floor(hmToMin(s.from) / ROW_MIN) * ROW_MIN),
    ),
    end: Math.max(GRID_END, ...spans.map((s) => Math.ceil(hmToMin(s.to) / ROW_MIN) * ROW_MIN)),
  }
}
export const gridRows = (r: GridRange) => (r.end - r.start) / ROW_MIN

/** 주중 5열 + 그릴 블록이 있는 주말 */
export function visibleDays(busy: BusyDay[]): number[] {
  const weekend = [6, 7].filter((d) => busy.some((b) => b.day === d && b.spans.some(drawn)))
  return [1, 2, 3, 4, 5, ...weekend]
}

export function weekBlocks(busy: BusyDay[], range: GridRange, rowPx: number): GridBlock[] {
  const px = (m: number) => ((m - range.start) / ROW_MIN) * rowPx
  return busy.flatMap((d) =>
    d.spans.filter(drawn).map((s) => ({
      day: d.day,
      top: px(hmToMin(s.from)),
      height: px(hmToMin(s.to)) - px(hmToMin(s.from)),
      label: s.label,
      extra: `${s.from}–${s.to}`,
      type: s.type,
      mine: s.mine,
      requested: s.mine && s.status === 'requested',
    })),
  )
}

/** 오늘 열의 brand 2px 선 — 범위 밖이면 긋지 않는다 */
export function nowTop(nowMin: number, range: GridRange, rowPx: number): number | null {
  if (nowMin < range.start || nowMin >= range.end) return null
  return ((nowMin - range.start) / ROW_MIN) * rowPx
}
