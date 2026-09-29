import type { BuildingOut, ExamWithRoom, ResvWithRoom, RoomOut } from '@/api/types'
import type { DotState } from '@/components/domain/OutboxDot.vue'
import { buildTree } from '@/components/domain/roomTree'
import { CHECKIN_AFTER, CHECKIN_BEFORE, resvWindow } from '@/components/domain/rules'
import { formatHm, kstDateStr, kstMinutes } from '@/lib/time'

/** 첫 진입 — 첫 건물의 첫 층. 건물 전체는 행이 너무 많다 (admin-rooms.md "층이나 강의실 몇 개만 고르는 것이 기본") */
export function defaultPick(buildings: BuildingOut[], rooms: RoomOut[]): number[] {
  const first = buildTree(buildings, rooms).find((b) => b.ids.length)
  return first ? first.floors[0].rooms.map((r) => r.id) : []
}

/** 호수 칸 — 고른 방이 여러 건물에 걸치면 건물 글자를 붙인다 (같은 호수가 두 건물에 있을 수 있다) */
export function roomLabeler(
  buildings: BuildingOut[],
  rooms: RoomOut[],
): (roomId: number) => string {
  const many = new Set(rooms.map((r) => r.building_id)).size > 1
  return (roomId) => {
    const r = rooms.find((x) => x.id === roomId)
    if (!r) return '—'
    const b = buildings.find((x) => x.id === r.building_id)
    return many && b ? `${b.bld} ${r.room}` : String(r.room)
  }
}

/** 예약 행의 점 — 추적 중이면 그 상태, 아니면 창 밖이고 노드에 안 간 것만 '예정'. 빈 outbox_ids 는 실패가 아니다 */
export function resvDot(
  r: ResvWithRoom,
  tracked: DotState | undefined,
  today: string,
): DotState | undefined {
  if (tracked) return tracked
  return r.pushed_at === null && resvWindow(r.date, today) === 'later' ? 'scheduled' : undefined
}

export interface ExamGroup {
  id: string
  date_start: string
  date_end: string
  items: ExamWithRoom[]
}
/** 같은 시작일·종료일은 한 행으로 접는다 — 펼치면 방마다 (admin-rooms.md 시험기간). 수정·삭제는 펼친 행에서 */
export function groupExams(exams: ExamWithRoom[], order: (roomId: number) => number): ExamGroup[] {
  const map = new Map<string, ExamGroup>()
  for (const x of exams) {
    const id = `${x.date_start}~${x.date_end}`
    const g = map.get(id) ?? { id, date_start: x.date_start, date_end: x.date_end, items: [] }
    g.items.push(x)
    map.set(id, g)
  }
  const groups = [...map.values()].sort(
    (a, b) => a.date_start.localeCompare(b.date_start) || a.date_end.localeCompare(b.date_end),
  )
  for (const g of groups) g.items.sort((a, b) => order(a.room_id) - order(b.room_id))
  return groups
}

/** '401, 402, 405 외 4곳' */
export const roomsLabel = (labels: string[]) =>
  labels.length <= 3
    ? labels.join(', ')
    : `${labels.slice(0, 3).join(', ')} 외 ${labels.length - 3}곳`

export interface ResvUse {
  label: string
  /** busy = 지금 강의실이 실제로 쓰인다(room.busy 틴트) */
  tone: 'busy' | 'neutral'
}
const dayMin = (date: string) => Date.parse(`${date}T00:00:00Z`) / 60_000
/** 예약 표의 상태 — 학생 예약만(관리자가 넣은 예약은 체크인이 없다 → null). 'KST 달력 날짜의 분'으로 비교 */
export function resvUse(r: ResvWithRoom, now: Date): ResvUse | null {
  if (!r.requester) return null
  if (r.checked_out_at) return { label: `조기 퇴실 ${formatHm(r.checked_out_at)}`, tone: 'neutral' }
  const n = dayMin(kstDateStr(now)) + kstMinutes(now)
  const s = dayMin(r.date) + r.s_h * 60 + r.s_m
  const e = dayMin(r.date) + r.e_h * 60 + r.e_m
  if (r.checked_in_at)
    return n < e ? { label: '사용중', tone: 'busy' } : { label: '사용 완료', tone: 'neutral' }
  if (n < s - CHECKIN_BEFORE) return { label: '예정', tone: 'neutral' }
  return n <= s + CHECKIN_AFTER
    ? { label: '체크인 대기', tone: 'neutral' }
    : { label: '미체크인', tone: 'neutral' }
}

/** 예약 로그 기본 범위(일) — 한 학기면 수백 건이라 최근 것만. '전체 보기'로 펼친다 */
export const LOG_DAYS = 30
const endMin = (r: ResvWithRoom) => dayMin(r.date) + r.e_h * 60 + r.e_m
const startMin = (r: ResvWithRoom) => dayMin(r.date) + r.s_h * 60 + r.s_m

/** 예약(안 끝난 승인, 시작 순) / 예약 로그(끝난 승인·취소·거절·만료, 최근 것부터). 신청 대기는 어느 쪽도 아니다 */
export function splitResv(rows: ResvWithRoom[], now: Date, all: boolean) {
  const n = dayMin(kstDateStr(now)) + kstMinutes(now)
  const from = kstDateStr(now, -LOG_DAYS)
  const live = rows
    .filter((r) => r.status === 'approved' && endMin(r) > n)
    .sort((a, b) => startMin(a) - startMin(b) || a.room_id - b.room_id)
  const log = rows
    .filter((r) => (r.status === 'approved' ? endMin(r) <= n : r.status !== 'requested'))
    .filter((r) => all || r.date >= from)
    .sort((a, b) => startMin(b) - startMin(a) || b.id - a.id)
  return { live, log }
}

/** 예약 로그의 결과 한 줄 */
export function logResult(r: ResvWithRoom): string {
  if (r.status === 'cancelled') return '취소됨'
  if (r.status === 'rejected') return r.reject_reason ? `거절됨 · ${r.reject_reason}` : '거절됨'
  if (r.status === 'expired') return '만료됨'
  if (!r.requester) return '종료'
  if (r.checked_out_at) return `조기 퇴실 ${formatHm(r.checked_out_at)}`
  return r.checked_in_at ? '사용 완료' : '미체크인'
}
