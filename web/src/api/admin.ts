import { request } from './client'
import {
  NODE_DATES,
  OUTBOX_DATES,
  RESV_ADMIN_DATES,
  type FailedOut,
  type LatencyOut,
  type LatencyType,
  type NodeOut,
  type ResvAdminOut,
} from './types'

/** 실패 목록 한 번에 받는 상한 (서버 le=500). 이만큼 오면 화면은 "500+" */
export const FAILED_LIMIT = 500

export const adminApi = {
  /** 기대 노드(rooms × units) × 상태 — 경고는 서버 판정 (S4b §2.2) */
  nodes: () => request<NodeOut[]>('GET', '/api/admin/nodes', undefined, { dates: NODE_DATES }),
  failed: (days: number) =>
    request<FailedOut[]>(
      'GET',
      `/api/admin/outbox/failed?days=${days}&limit=${FAILED_LIMIT}`,
      undefined,
      { dates: OUTBOX_DATES },
    ),
  /** from·to 는 KST 날짜(양끝 포함), 90일 이내 (S10 §4.3) */
  latency: (q: { from: string; to: string; type: LatencyType }) =>
    request<LatencyOut>('GET', `/api/admin/analytics/latency?${new URLSearchParams(q)}`),

  /** 학생 신청 대기 — 학교 전체. 서버는 날짜순, '오래된 신청 먼저' 정렬은 화면이 */
  pendingResv: () =>
    request<ResvAdminOut[]>('GET', '/api/admin/reservations?status=requested', undefined, {
      dates: RESV_ADMIN_DATES,
    }),
  /** 겹침·용량(24)·시작 시각을 다시 본다 — 어긋나면 409 */
  approveResv: (id: number) =>
    request<ResvAdminOut>('POST', `/api/admin/reservations/${id}/approve`, undefined, {
      dates: RESV_ADMIN_DATES,
    }),
  /** 사유(1~200자)는 학생에게 그대로 보인다 */
  rejectResv: (id: number, reason: string) =>
    request<ResvAdminOut>(
      'POST',
      `/api/admin/reservations/${id}/reject`,
      { reason },
      { dates: RESV_ADMIN_DATES },
    ),
  /** 승인된 예약을 cancelled 로 — 행을 지우지 않아 학생 화면에 '취소됨'으로 남는다 */
  cancelResv: (id: number) =>
    request<ResvAdminOut>('POST', `/api/admin/reservations/${id}/cancel`, undefined, {
      dates: RESV_ADMIN_DATES,
    }),
}
