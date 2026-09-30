import { request } from './client'
import { USER_DATES, type UserOut, type UserStatus } from './types'

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
}
