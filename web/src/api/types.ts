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
