import { request } from './client'
import {
  RESV_MINE_DATES,
  type ResvMineOut,
  type ResvStatus,
  type RoomStateOut,
  type StudentResvIn,
  type WeekOut,
} from './types'

const mineOpts = { dates: RESV_MINE_DATES }

/** /me 는 다섯 상태 전부 — 서버 기본(requested·approved)이면 거절 사유·취소 기록을 못 본다 */
export const ALL_STATUSES: readonly ResvStatus[] = [
  'requested',
  'approved',
  'rejected',
  'cancelled',
  'expired',
]

// 전부 require_student + 내 학교의 reservable 방 — 아니면 404 (S10 §3)
export const studentApi = {
  /** 학교 전체 — 건물·개수·목록을 이 하나에서 만든다 */
  rooms: () => request<RoomStateOut[]>('GET', '/api/student/rooms'),
  /** 이번 주(서버 KST 오늘 기준) + 오늘~+7 free + full */
  week: (roomId: number) => request<WeekOut>('GET', `/api/student/rooms/${roomId}/week`),
  /** 201 → requested. 400 창·길이·지난 시각·3건 / 409 겹침·가득 / 429 하루 10회 */
  requestResv: (roomId: number, body: StudentResvIn) =>
    request<ResvMineOut>('POST', `/api/student/rooms/${roomId}/reservations`, body, mineOpts),
  mine: () =>
    request<ResvMineOut[]>(
      'GET',
      `/api/student/me/reservations?status=${ALL_STATUSES.join(',')}`,
      undefined,
      mineOpts,
    ),
  /** requested → 행 삭제(철회), approved → 시작 전 취소. 그 밖 409 */
  cancel: (id: number) =>
    request<ResvMineOut>('POST', `/api/student/me/reservations/${id}/cancel`, undefined, mineOpts),
  /** 시작 −10 ~ +15분 안의 approved 만. 그 밖·이미 함 409 */
  checkin: (id: number) =>
    request<ResvMineOut>('POST', `/api/student/me/reservations/${id}/checkin`, undefined, mineOpts),
}
