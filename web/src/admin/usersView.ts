import type { UserOut, UserStatus } from '@/api/types'

/** 적색은 disabled 에만 — 대기·거절은 문제 상황이 아니다 (admin-users.md) */
export const STATUS_BADGE: Record<
  UserStatus,
  { label: string; tone: 'neutral' | 'danger'; variant: 'outline' | 'solid' }
> = {
  pending_approval: { label: '대기중', tone: 'neutral', variant: 'outline' },
  active: { label: '활성', tone: 'neutral', variant: 'solid' },
  rejected: { label: '거절됨', tone: 'neutral', variant: 'outline' },
  disabled: { label: '정지됨', tone: 'danger', variant: 'outline' },
}

export const FILTERS: { value: UserStatus | ''; label: string }[] = [
  { value: 'pending_approval', label: '승인 대기' },
  { value: '', label: '전체' },
  { value: 'active', label: '활성' },
  { value: 'rejected', label: '거절' },
  { value: 'disabled', label: '정지' },
]

/** 대기 건은 먼저 온 사람 먼저, 나머지는 최신순 */
export function sortUsers(users: UserOut[]): UserOut[] {
  const t = (x: UserOut) => x.created_at.getTime()
  const pending = users.filter((x) => x.status === 'pending_approval').sort((a, b) => t(a) - t(b))
  const rest = users.filter((x) => x.status !== 'pending_approval').sort((a, b) => t(b) - t(a))
  return [...pending, ...rest]
}

export function matchUser(u: UserOut, q: string): boolean {
  const s = q.trim().toLowerCase()
  if (!s) return true
  return [u.name, u.student_no ?? '', u.email].some((v) => v.toLowerCase().includes(s))
}
