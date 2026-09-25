// 도메인 규칙 한 곳 — 폼·표·격자가 같은 값을 쓴다 (components.md: 편집 경로마다 검증이 갈라지지 않게)
import type { ApiError } from '@/api/client'
import type { SlotSource, SlotType } from '@/api/types'
import { addDays } from '@/lib/time'

/** UTF-8 바이트 상한 — lora_proto LP_SUBJ_MAX / LP_PROF_MAX (서버 schemas._Span 과 같다) */
export const SUBJ_MAX = 20
export const PROF_MAX = 12
/** 예약은 오늘~+7 일만 노드로 간다 (서버 RESV_HORIZON_DAYS) */
export const RESV_HORIZON_DAYS = 7

export const DAYS = ['월', '화', '수', '목', '금', '토', '일'] as const
export const DAY_OPTIONS = DAYS.map((label, i) => ({ value: i + 1, label }))

/** 배지 라벨 (components.md TypeBadge) */
export const TYPE_LABEL: Record<SlotType, string> = {
  1: '수업중',
  2: '시험중',
  3: '휴강',
  4: '빈강의실',
  5: '특강',
  6: '대여중',
}
/** 폼 Select — CSV 의 type 이름과 같은 말 */
export const TYPE_OPTIONS: { value: SlotType; label: string }[] = [
  { value: 1, label: '수업' },
  { value: 2, label: '시험' },
  { value: 3, label: '휴강' },
  { value: 4, label: '빈강의실' },
  { value: 5, label: '특강' },
  { value: 6, label: '대여' },
]
/** 사용중 — 문 앞 e-Paper 의 RED. 넷을 색으로 나누지 않고 라벨로 가른다 */
export const BUSY_TYPES: readonly SlotType[] = [1, 2, 5, 6]
export const SOURCE_LABEL: Record<SlotSource, string> = { 1: '포털', 2: '수동', 3: '긴급' }

export interface Span {
  s_h: number
  s_m: number
  e_h: number
  e_m: number
}
export const toMin = (h: number, m: number) => h * 60 + m
/** 끝이 맞닿는 것(09–10 · 10–11)은 겹침이 아니다 */
export const spansOverlap = (a: Span, b: Span) =>
  toMin(a.s_h, a.s_m) < toMin(b.e_h, b.e_m) && toMin(b.s_h, b.s_m) < toMin(a.e_h, a.e_m)

export type ResvWindow = 'past' | 'in' | 'later'
/** later = 창 밖 — 저장은 되고 outbox_ids 가 빈 배열로 온다(실패 아님). 창에 들어오는 날 자동 전송 */
export function resvWindow(date: string, today: string): ResvWindow {
  if (date < today) return 'past'
  return date <= addDays(today, RESV_HORIZON_DAYS) ? 'in' : 'later'
}
export const LATER_HINT = '7일 이내로 들어오면 자동 전송됩니다'

/** 층은 서버에 없다 — 401 → 4, 1203 → 12, 100 미만은 null('기타'). 트리·마스터 표가 같은 규칙 */
export const floorOf = (room: number) => (room < 100 ? null : Math.floor(room / 100))
export function floorLabel(room: number): string {
  const f = floorOf(room)
  return f === null ? '기타' : `${f}층`
}

/** 저장한 행 — 화면이 이 key 의 OutboxDot 을 30초 따라간다 */
export interface SavedRow {
  roomId: number
  key: string
  outboxIds: number[]
}
export const slotKey = (s: { room_id: number; day: number; s_h: number; s_m: number }) =>
  `s${s.room_id}-${s.day}-${s.s_h}-${s.s_m}`
export const resvKey = (id: number) => `r${id}`
export const examKey = (id: number) => `x${id}`

/** 서버 오류 본문의 detail 문자열 (없으면 '') — 화면에 내지 않고 분기에만 쓴다 */
export function detailText(e: ApiError): string {
  const d = (e.detail as { detail?: unknown } | null)?.detail
  return typeof d === 'string' ? d : ''
}

// 409 원문 → 사람 문장 (spec §4.1 — 원문은 화면에 내지 않는다). 위에서부터 첫 일치
const CONFLICTS: [RegExp, string][] = [
  [/^source \d/, '이 슬롯은 웹에서 수정된 행입니다. CSV로 덮어쓸 수 없습니다.'],
  [/가득/, '이 강의실은 7일 안 예약이 가득 찼습니다(24건). 지난 예약을 정리하세요.'],
  [/id 소진/, 'id 소진 — 지난 예약·시험기간을 정리하세요'],
  [/다른 방/, '다른 강의실의 항목입니다. 목록을 새로 불러옵니다.'],
  [/신청 상태/, '학생 신청은 신청 대기에서 승인·거절로 처리하세요.'],
  [/시작 시각이 지난/, '이미 시작 시각이 지난 신청입니다.'],
  [/다른 예약·수업이 생겼/, '그 시간에 다른 예약이나 수업이 생겨 승인할 수 없습니다.'],
  [/상태에서는 불가/, '이미 처리된 신청입니다.'],
  [/다른 학교/, '이 bld 는 다른 학교가 쓰고 있습니다'],
  [/constraint violation/, '같은 bld·호수가 이미 있습니다'],
]
export function conflictMessage(e: ApiError): string {
  const t = detailText(e)
  return CONFLICTS.find(([re]) => re.test(t))?.[1] ?? e.message
}
