import type { ResvMineOut } from '../types'

/** 공용 ResvMineOut 빌더 (M1) — 화면·훅 테스트가 studentApi.mine() 결과 모양을 복붙하지 않고 이걸 쓴다 */
export function mineResv(overrides: Partial<ResvMineOut> = {}): ResvMineOut {
  return {
    id: 7,
    date: '2026-10-24',
    s_h: 10,
    s_m: 0,
    e_h: 12,
    e_m: 0,
    type: 6,
    subject: '캡스톤 스터디',
    professor: '',
    status: 'approved',
    requested_at: new Date('2026-10-22T01:00:00Z'),
    decided_at: new Date('2026-10-22T02:30:00Z'),
    reject_reason: null,
    checked_in_at: null,
    cancelled_at: null,
    room_id: 11,
    building: '공학관',
    room: 401,
    ...overrides,
  }
}
