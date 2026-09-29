// 서버 응답 타입 — 서버 스키마 이름 그대로, 여기에 한 번만 (web/CLAUDE.md). Date 필드는 *_DATES 에 적는다.
export type Role = 'admin' | 'student'
export type UserStatus = 'pending_approval' | 'active' | 'rejected' | 'disabled'

export interface UserOut {
  email: string
  school_id: number
  role: Role
  status: UserStatus
  name: string
  student_no: string | null
  created_at: Date
  approved_at: Date | null
}
export const USER_DATES = ['created_at', 'approved_at'] as const

export interface LoginOut {
  token: string
  role: Role
  school_id: number
  name: string
}

// ---- F3 모니터링 — S4b(노드·실패), S10 §4.3(지연), lora_service(모뎀·pending·outbox) ----
/** 서버 WARNING_ORDER 와 같은 순서 (S4b §2.1) — 판정은 서버가 한다 */
export type NodeWarning = 'unseen' | 'low_batt' | 'resync' | 'clock_stale'
export type OutboxState = 'queued' | 'dispatched' | 'acked' | 'failed' | 'cancelled'

export interface ModemOut {
  modem_id: string
  agent_ver: string | null
  modem_fw: string | null
  last_seen_at: Date | null
  connected: boolean
  school_id: number | null
}
export const MODEM_DATES = ['last_seen_at'] as const

export interface TokenOut {
  modem_id: string
  token: string
}

export interface NodeOut {
  room_id: number
  building_id: number
  building: string
  bld: string
  room: number
  unit: number
  modem_id: string | null
  mac: string | null
  fw: number | null
  batt_mv: number | null
  rssi: number | null
  snr: number | null
  sched_ver: number | null
  resv_ver: number | null
  exam_ver: number | null
  ident_ver: number | null
  layout: number | null
  clock_stale: boolean
  low_batt: boolean
  uptime_h: number | null
  last_seen_at: Date | null
  last_ack_at: Date | null
  last_status_at: Date | null
  sync_state: string
  warnings: NodeWarning[]
}
export const NODE_DATES = ['last_seen_at', 'last_ack_at', 'last_status_at'] as const

export interface PendingOut {
  mac: string
  modem_id: string | null
  fw: number | null
  batt_mv: number | null
  rssi: number | null
  first_seen_at: Date
  last_seen_at: Date
}
export const PENDING_DATES = ['first_seen_at', 'last_seen_at'] as const

export interface Enqueued {
  outbox_ids: number[]
  id: number | null
}

export interface OutboxOut {
  id: number
  modem_id: string | null
  bld: string
  room: number
  unit: number
  type: string
  payload: Record<string, unknown>
  priority: number
  new_ver: number | null
  state: OutboxState
  attempts: number
  ack_status: number | null
  ack_detail: number | null
  rssi: number | null
  snr: number | null
  last_error: string | null
  created_at: Date
  dispatched_at: Date | null
  finished_at: Date | null
}
export const OUTBOX_DATES = ['created_at', 'dispatched_at', 'finished_at'] as const

export interface FailedOut extends OutboxOut {
  room_id: number
  building: string
}

export interface LatencyBin {
  ge: number
  lt: number | null
  count: number
}
export interface LatencyOut {
  n: number
  bins: LatencyBin[]
  p50: number | null
  p95: number | null
  max: number | null
  within_30s: number
  within_90s: number
}
export type LatencyType = 'SLOT_SET' | 'RESV_SET' | 'all'

// ---- F2 관리자 운영 — S2(건물·강의실·시간표), S4b(건물 단위 조회·서버 채번), S10(신청), web A2 ----

export interface SchoolOut {
  id: number
  name: string
  net_id: number
}
export interface BuildingIn {
  school_id: number
  name: string
  /** 대문자 한 글자 — 무선 주소라 학교가 달라도 겹칠 수 없다 (409) */
  bld: string
  modem_id: string | null
}
export interface BuildingOut extends BuildingIn {
  id: number
}
/** 부분 수정 — 보낸 필드만 바뀐다. modem_id: null = 배정 해제 */
export interface BuildingPatch {
  name?: string
  bld?: string
  modem_id?: string | null
}
export interface RoomIn {
  building_id: number
  room: number
  units: number
  reservable: boolean
}
export interface RoomOut extends RoomIn {
  id: number
}
/** 호수(room)는 무선 주소라 화면이 보내지 않는다 (admin-master.md — 수정 폼에서 잠금) */
export interface RoomPatch {
  units?: number
  reservable?: boolean
}
/** 1 수업 · 2 시험 · 3 휴강 · 4 빈강의실 · 5 특강 · 6 대여 (lora_proto LP_SLOTTYPE_*) */
export type SlotType = 1 | 2 | 3 | 4 | 5 | 6
/** 1 포털(CSV) · 2 수동(웹) · 3 긴급 — 낮은 출처는 높은 출처를 덮지 못한다 (409) */
export type SlotSource = 1 | 2 | 3
export interface SlotIn {
  day: number
  s_h: number
  s_m: number
  e_h: number
  e_m: number
  type: SlotType
  subject: string
  professor: string
  source: SlotSource
}
export interface SlotOut extends SlotIn {
  id: number
}
export interface SlotWithRoom extends SlotOut {
  room_id: number
}
export type ResvStatus = 'requested' | 'approved' | 'rejected' | 'cancelled' | 'expired'
/** id 를 빼면 서버가 채번한다 (S4b §2.5). date 는 KST 달력 'YYYY-MM-DD' — Date 로 바꾸지 않는다 */
export interface ResvIn {
  id?: number
  date: string
  s_h: number
  s_m: number
  e_h: number
  e_m: number
  type: SlotType
  subject: string
  professor: string
}
export interface ResvOut extends ResvIn {
  id: number
  status: ResvStatus
}
export interface RequesterOut {
  email: string
  name: string
  student_no: string | null
}
/** 건물·방 예약 목록 (web A2) — requester 는 학생 신청만, pushed_at null = 노드에 없음 */
export interface ResvWithRoom extends ResvOut {
  room_id: number
  requester: RequesterOut | null
  pushed_at: Date | null
}
export const RESV_DATES = ['pushed_at'] as const
/** 관리자 신청 목록·승인·거절·취소 응답 (S10 §4.2 + web A2) */
export interface ResvAdminOut extends ResvOut {
  requested_at: Date | null
  decided_at: Date | null
  reject_reason: string | null
  checked_in_at: Date | null
  cancelled_at: Date | null
  room_id: number
  building: string
  room: number
  requester: RequesterOut | null
  pushed_at: Date | null
}
export const RESV_ADMIN_DATES = [
  'requested_at',
  'decided_at',
  'checked_in_at',
  'cancelled_at',
  'pushed_at',
] as const
export interface ExamIn {
  id?: number
  date_start: string
  date_end: string
}
export interface ExamOut extends ExamIn {
  id: number
}
export interface ExamWithRoom extends ExamOut {
  room_id: number
}
export interface ImportSkipped {
  row: number
  reason: string
}
export interface ImportSummary {
  rooms: number
  added: number
  updated: number
  deleted: number
  skipped: ImportSkipped[]
  outbox_ids: number[]
}
export interface ImportRowError {
  row: number
  error: string
}
export interface ImportErrors {
  errors: ImportRowError[]
}

// ---- F4 학생 웹 — S10 §4.1 + web A3 (busy·free·full) ----

/** 학생 목록의 방 하나 + 지금 상태 (reservable 방만 — S10 §3) */
export interface RoomStateOut {
  room_id: number
  building_id: number
  building: string
  bld: string
  room: number
  /** e-Paper layout 1~8 — 4 만 '비어있음'(예약 가능). 색은 RED(1·5·6·7) */
  layout: number
  /** 다음 상태 변화 'HH:MM' (KST). null = 자정까지 그대로 */
  until: string | null
}
/** 주간 표의 승인 예약 원본 — 남의 학생 예약 label 은 '예약됨' */
export interface ResvPublicOut {
  id: number
  date: string
  s_h: number
  s_m: number
  e_h: number
  e_m: number
  mine: boolean
  label: string
}
/** 'HH:MM' 구간 — 서버 alias 그대로 from/to */
export interface FreeRange {
  from: string
  to: string
}
/** 서버가 room_state 규칙으로 합친 사용 구간 (web A3). 남의 것은 label '예약됨'·status null */
export interface BusySpan extends FreeRange {
  label: string
  type: SlotType
  mine: boolean
  /** 내 예약만 — 격자가 '내 신청(대기)'과 '내 예약'을 가른다 */
  status: 'requested' | 'approved' | null
}
export interface BusyDay {
  /** 1=월 … 7=일 */
  day: number
  spans: BusySpan[]
}
/** 신청 가능한 구간 — KST 오늘~+7 여덟 날. 오늘은 지금 이후만, full 이면 전부 빈 목록 */
export interface FreeDay {
  date: string
  spans: FreeRange[]
}
export interface WeekOut {
  room: RoomStateOut
  week_start: string
  slots: SlotOut[]
  reservations: ResvPublicOut[]
  exams: ExamOut[]
  busy: BusyDay[]
  free: FreeDay[]
  /** 창(오늘~+7) 안 approved+requested 가 노드 용량(24)에 찼다 */
  full: boolean
}
/** 학생 신청 — type(6 대여)·professor('')·id 는 서버가 정한다 */
export interface StudentResvIn {
  date: string
  s_h: number
  s_m: number
  e_h: number
  e_m: number
  subject: string
}
/** 내 예약 (S10 §4.1 _mine_out) */
export interface ResvMineOut extends ResvOut {
  requested_at: Date | null
  decided_at: Date | null
  reject_reason: string | null
  checked_in_at: Date | null
  cancelled_at: Date | null
  room_id: number
  building: string
  room: number
}
export const RESV_MINE_DATES = [
  'requested_at',
  'decided_at',
  'checked_in_at',
  'cancelled_at',
] as const
