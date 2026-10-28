import { request } from './client'
import { USER_DATES, type LoginOut, type UserOut } from './types'

const pub = { auth: false } as const

export const authApi = {
  signup: (email: string) =>
    request<{ status: 'sent' }>('POST', '/api/auth/signup', { email }, pub),
  verifyOpen: (token: string) =>
    request<{ email: string }>('POST', '/api/auth/verify/open', { token }, pub),
  verify: (b: { token: string; name: string; student_no: string; password: string }) =>
    request<{ status: 'pending_approval' }>('POST', '/api/auth/verify', b, pub),
  login: (email: string, password: string) =>
    request<LoginOut>('POST', '/api/auth/login', { email, password }, pub),
  forgot: (email: string) =>
    request<{ status: 'sent' }>('POST', '/api/auth/forgot', { email }, pub),
  reset: (token: string, password: string) =>
    request<{ status: 'ok' }>('POST', '/api/auth/reset', { token, password }, pub),
  me: () => request<UserOut>('GET', '/api/auth/me', undefined, { dates: USER_DATES }),
}
