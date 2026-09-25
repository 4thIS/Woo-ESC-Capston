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
