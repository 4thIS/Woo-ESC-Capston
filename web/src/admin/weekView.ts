import type { ExamOut, ResvWithRoom, SlotWithRoom } from '@/api/types'
import { BUSY_TYPES, resvKey, slotKey, toMin } from '@/components/domain/rules'
import { addDays, dayOfDate } from '@/lib/time'

/** 격자 — 30분 행, 44px 고정. 기본 09:00~18:00(18행), 야간 보기 22:00 까지(26행) (admin-schedule.md).
 * 웹의 표시 축일 뿐 단말(교시)과 무관하다 */
export const ROW_MIN = 30
export const ROW_PX = 44
export const DAY_START = 9 * 60
export const DAY_END = 18 * 60
export const NIGHT_END = 22 * 60

export interface Block {
  key: string
  /** 1=월 … 7=일 */
  day: number
  /** 자정부터 분 */
  s: number
  e: number
  /** 점유 — 사용중 슬롯(1·2·5·6)과 승인 예약. 겹침 막대는 둘 다 점유일 때만 */
  busy: boolean
  slot?: SlotWithRoom
  resv?: ResvWithRoom
}
export interface Placed extends Block {
  lane: number
  lanes: number
}
export interface Overlap {
  s: number
  e: number
  /** 막대는 이 lane 의 왼쪽 경계에 선다 */
  lane: number
  lanes: number
}
export interface Range {
  from: number
  to: number
}
export interface Box {
  top: number
  height: number
  cutEnd: boolean
}

/** 시간표는 요일 기반이라 주가 바뀌어도 같다 — 예약만 보고 있는 주로 거른다.
 * 빈강의실(4)은 그리지 않는다, 거절·취소·만료 예약도 그리지 않는다 */
export function weekBlocks(slots: SlotWithRoom[], resv: ResvWithRoom[], monday: string): Block[] {
  const sunday = addDays(monday, 6)
  const fromSlots: Block[] = slots
    .filter((s) => s.type !== 4)
    .map((s) => ({
      key: slotKey(s),
      day: s.day,
      s: toMin(s.s_h, s.s_m),
      e: toMin(s.e_h, s.e_m),
      busy: BUSY_TYPES.includes(s.type),
      slot: s,
    }))
  const fromResv: Block[] = resv
    .filter(
      (r) =>
        (r.status === 'approved' || r.status === 'requested') &&
        r.date >= monday &&
        r.date <= sunday,
    )
    .map((r) => ({
      key: resvKey(r.id),
      day: dayOfDate(r.date),
      s: toMin(r.s_h, r.s_m),
      e: toMin(r.e_h, r.e_m),
      busy: r.status === 'approved',
      resv: r,
    }))
  return [...fromSlots, ...fromResv]
}

/** 하루치 배치 — 겹치는 무리마다 lane 을 탐욕 배정, 폭은 무리의 lane 수로 균등 분할.
 * 겹친 두 블록이 둘 다 점유면 겹친 구간에만 막대 하나 (테두리 둘은 "경고 두 개"로 읽힌다) */
export function layoutDay(blocks: Block[]): { placed: Placed[]; overlaps: Overlap[] } {
  const sorted = [...blocks].sort((a, b) => a.s - b.s || a.e - b.e)
  const placed: Placed[] = []
  let cluster: Placed[] = []
  let laneEnds: number[] = []
  let clusterEnd = -1
  const flush = () => {
    for (const p of cluster) p.lanes = laneEnds.length
    cluster = []
    laneEnds = []
  }
  for (const b of sorted) {
    if (b.s >= clusterEnd) flush()
    let lane = laneEnds.findIndex((end) => end <= b.s)
    if (lane < 0) {
      lane = laneEnds.length
      laneEnds.push(b.e)
    } else laneEnds[lane] = b.e
    const p: Placed = { ...b, lane, lanes: 1 }
    cluster.push(p)
    placed.push(p)
    clusterEnd = Math.max(clusterEnd, b.e)
  }
  flush()
  const overlaps: Overlap[] = []
  for (let i = 0; i < placed.length; i++)
    for (let j = i + 1; j < placed.length; j++) {
      const a = placed[i]
      const b = placed[j]
      if (!a.busy || !b.busy) continue
      const s = Math.max(a.s, b.s)
      const e = Math.min(a.e, b.e)
      if (s < e) overlaps.push({ s, e, lane: Math.max(a.lane, b.lane), lanes: a.lanes })
    }
  return { placed, overlaps }
}

/** 09:00 전 블록이 있으면 그 30분부터 — 07:30 수업이 화면에 없으면 편집할 길이 없다 (설계 판정) */
export function gridRange(blocks: Block[], night: boolean): Range {
  const from = blocks.reduce((m, b) => Math.min(m, Math.floor(b.s / ROW_MIN) * ROW_MIN), DAY_START)
  return { from, to: night ? NIGHT_END : DAY_END }
}
export const timeRows = (r: Range) =>
  Array.from({ length: (r.to - r.from) / ROW_MIN }, (_, i) => r.from + i * ROW_MIN)

/** 보고 있는 주에 18:00 넘게 끝나는 블록 — 없으면 19시 수업이 화면에 없다 */
export const needsNight = (blocks: Block[]) => blocks.some((b) => b.e > DAY_END)
export const needsWeekend = (blocks: Block[]) => blocks.some((b) => b.day >= 6)

/** 세로 위치 — 격자 밖은 잘라 그린다. 22:00 넘게 걸친 블록은 하단에 ~HH:MM 을 적는다 */
export function blockBox(b: { s: number; e: number }, r: Range): Box | null {
  const s = Math.max(b.s, r.from)
  const e = Math.min(b.e, r.to)
  if (e <= s) return null
  return {
    top: ((s - r.from) / ROW_MIN) * ROW_PX,
    height: ((e - s) / ROW_MIN) * ROW_PX,
    cutEnd: b.e > r.to,
  }
}

/** 시험기간에 걸린 그 주의 날짜 — 요일 헤더 아래 얇은 띠 */
export function examDates(exams: ExamOut[], monday: string): Set<string> {
  const out = new Set<string>()
  for (let i = 0; i < 7; i++) {
    const d = addDays(monday, i)
    if (exams.some((x) => x.date_start <= d && d <= x.date_end)) out.add(d)
  }
  return out
}
