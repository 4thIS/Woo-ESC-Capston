import { request } from './client'
import { USER_DATES, type RoleIn, type UserOut, type UserStatus } from './types'

const d = { dates: USER_DATES }
const path = (email: string, act: string) => `/api/admin/users/${encodeURIComponent(email)}/${act}`

export const usersApi = {
  list: (status?: UserStatus) =>
    request<UserOut[]>('GET', `/api/admin/users${status ? `?status=${status}` : ''}`, undefined, d),
  approve: (email: string) => request<UserOut>('POST', path(email, 'approve'), undefined, d),
  reject: (email: string, reason: string) =>
    request<UserOut>('POST', path(email, 'reject'), { reason }, d),
  disable: (email: string) => request<UserOut>('POST', path(email, 'disable'), undefined, d),
  enable: (email: string) => request<UserOut>('POST', path(email, 'enable'), undefined, d),
  /** #160 — 건물 관리자 지정·건물 바꾸기·해제 (최고 관리자만). 바뀌면 그 사람은 다시 로그인한다 */
  setRole: (email: string, body: RoleIn) => request<UserOut>('PUT', path(email, 'role'), body, d),
}
