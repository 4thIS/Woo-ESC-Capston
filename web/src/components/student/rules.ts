// 학생 웹 규칙 한 곳 — 서버 S10 §2.4·§4.1(reserve.py) 과 같은 값.
// 판정(빈 구간·겹침·합치기)은 서버가 하고, 여기는 표시·고르기·문장만 (student-room.md §데이터)
import type { FreeRange, ResvMineOut } from '@/api/types'
import { DAYS } from '@/components/domain/rules'
import { dayOfDate, formatHm, hm, kstDateStr, kstMinutes, md } from '@/lib/time'

/** e-Paper layout (terminal-epaper.md) — 4 만 '비어있음'(예약 가능, 개수·필터) */
export const FREE_LAYOUT = 4
const LAYOUT_LABEL: Record<number, string> = {
  1: '수업중',
  2: '쉬는시간',
  3: '휴강',
  4: '비어있음',
  5: '시험중',
  6: '특강',
  7: '대여중',
  8: '설정 대기',
}
export const layoutLabel = (layout: number) => LAYOUT_LABEL[layout] ?? '확인 중'
/** 색 — RED(1·5·6·7) 만 room.busy (tokens.md). 가용성(FREE_LAYOUT)과 섞지 않는다 */
export const isRed = (layout: number) => [1, 5, 6, 7].includes(layout)
/** 목록 행 모양 — 4 만 빈 곳, 쉬는시간·휴강·설정 대기(2·3·8)는 예약할 수 없으니 빈 곳처럼 칠하지 않는다 */
export const rowState = (layout: number): 'busy' | 'free' | 'other' =>
  isRed(layout) ? 'busy' : layout === FREE_LAYOUT ? 'free' : 'other'
/** until = 다음 상태 변화. '비어요'로 단정하지 않는다 — 수업 뒤는 쉬는시간일 수 있다 */
export function untilText(layout: number, until: string | null): string {
  if (until) return `${until} 까지`
  return layout === FREE_LAYOUT ? '오늘 계속 비어 있어요' : '자정까지'
}

// 서버 reserve.py 와 같은 값
export const MAX_ACTIVE = 3
export const MIN_MIN = 15
export const MAX_MIN = 120
export const STEP_MIN = 5
export const CHECKIN_BEFORE = 10
export const CHECKIN_AFTER = 15

// 서버 원문 대신 (spec §4.1) — student-room.md §화면이 거는 제약
export const FULL_TEXT = '이 강의실은 예약이 다 찼어요'
export const CAP_TEXT = `신청은 ${MAX_ACTIVE}건까지 할 수 있어요`
export const DAILY_TEXT = '오늘은 더 신청할 수 없어요. 내일 다시 시도해 주세요'
/** 재조회가 실패하면 앞 문장만 — 새로 불러오지 못했는데 불러왔다고 하지 않는다 */
export const TAKEN_LEAD = '방금 다른 사람이 먼저 신청했어요.'
export const STALE_LEAD = '선택한 시간으로 신청할 수 없어요.'
const RELOADED = '비어 있는 시간을 새로 불러왔어요.'
export const TAKEN_TEXT = `${TAKEN_LEAD} ${RELOADED}`
export const STALE_TEXT = `${STALE_LEAD} ${RELOADED}`
export const CHANGED_TEXT = '이미 처리된 예약이에요. 목록을 새로 불러왔어요.'
export const CHECKIN_CLOSED_TEXT = '지금은 체크인할 수 없어요. 목록을 새로 불러왔어요.'
export const DOOR_HINT = '문 앞 화면에는 "학생 예약"으로만 표시돼요'

/** '10:05' → 605 */
export const hmToMin = (v: string) => Number(v.slice(0, 2)) * 60 + Number(v.slice(3, 5))
/** 605 → '10:05' */
export const minToHm = (m: number) => hm(Math.floor(m / 60), m % 60)
export function durationText(min: number): string {
  const h = Math.floor(min / 60)
  const m = min % 60
  if (h && m) return `${h}시간 ${m}분`
  return h ? `${h}시간` : `${m}분`
}
export const chipDay = (date: string) => DAYS[dayOfDate(date) - 1]
/** '2026-10-24' → '10월 24일 토' */
export const dateLabel = (date: string) =>
  `${Number(date.slice(5, 7))}월 ${Number(date.slice(8, 10))}일 ${chipDay(date)}`
export const spanKey = (s: FreeRange) => `${s.from}-${s.to}`

/** 시작 후보 — 5분 단위, 끝 15분 전까지. after(오늘의 지금 분)가 있으면 그보다 뒤만 */
export function startOptions(span: FreeRange, after: number | null): number[] {
  const out: number[] = []
  for (let m = hmToMin(span.from); m + MIN_MIN <= hmToMin(span.to); m += STEP_MIN)
    if (after === null || m > after) out.push(m)
  return out
}
/** 끝 후보 — 시작 +15 ~ +120, 구간 끝을 넘지 않는다 */
export function endOptions(start: number, span: FreeRange): number[] {
  const out: number[] = []
  for (let m = start + MIN_MIN; m <= Math.min(start + MAX_MIN, hmToMin(span.to)); m += STEP_MIN)
    out.push(m)
  return out
}
export const defaultEnd = (start: number, span: FreeRange) => Math.min(start + 60, hmToMin(span.to))

// ---- 내 예약 — 'KST 달력 날짜의 분'으로 비교 (서버 local_dt 와 같은 축) ----
const dayMin = (date: string) => Date.parse(`${date}T00:00:00Z`) / 60_000
const startAt = (r: ResvMineOut) => dayMin(r.date) + r.s_h * 60 + r.s_m
const endAt = (r: ResvMineOut) => dayMin(r.date) + r.e_h * 60 + r.e_m
const nowAt = (now: Date) => dayMin(kstDateStr(now)) + kstMinutes(now)

/** 서버 MAX_ACTIVE 판정과 같다 — 시작 전 신청 + 끝나지 않은 승인 */
export function activeCount(list: ResvMineOut[], now: Date): number {
  const n = nowAt(now)
  return list.filter((r) =>
    r.status === 'requested' ? startAt(r) > n : r.status === 'approved' && endAt(r) > n,
  ).length
}

export type CheckinState =
  | { kind: 'done'; at: string }
  | { kind: 'open' }
  | { kind: 'before'; from: string }
  | { kind: 'after' }
/** 승인 예약만. 끝난 예약은 null(버튼 없음). 서버와 시계가 어긋나면 409 — 화면이 문장+재조회 */
export function checkinState(r: ResvMineOut, now: Date): CheckinState | null {
  if (r.status !== 'approved') return null
  if (r.checked_in_at) return { kind: 'done', at: formatHm(r.checked_in_at) }
  const n = nowAt(now)
  const s = startAt(r)
  if (n > endAt(r)) return null
  if (n < s - CHECKIN_BEFORE)
    return { kind: 'before', from: minToHm((((s - CHECKIN_BEFORE) % 1440) + 1440) % 1440) }
  return n <= s + CHECKIN_AFTER ? { kind: 'open' } : { kind: 'after' }
}

export type CancelKind = 'withdraw' | 'cancel'
/** requested → 철회(행 삭제), approved → 시작 전만 취소 (S10 §2.1) */
export function cancelKind(r: ResvMineOut, now: Date): CancelKind | null {
  if (r.status === 'requested') return 'withdraw'
  return r.status === 'approved' && startAt(r) > nowAt(now) ? 'cancel' : null
}

/** 진행 중(대기 · 안 끝난 승인)은 가까운 순, 나머지는 최근 순 */
export function sortMine(list: ResvMineOut[], now: Date): ResvMineOut[] {
  const n = nowAt(now)
  const live = (r: ResvMineOut) =>
    r.status === 'requested' || (r.status === 'approved' && endAt(r) > n)
  return [
    ...list.filter(live).sort((a, b) => startAt(a) - startAt(b)),
    ...list.filter((r) => !live(r)).sort((a, b) => startAt(b) - startAt(a)),
  ]
}

/** '10/24 토 10:00–12:00' */
export const resvWhen = (r: ResvMineOut) =>
  `${md(r.date)} ${chipDay(r.date)} ${hm(r.s_h, r.s_m)}–${hm(r.e_h, r.e_m)}`
