import { request } from './client'
import {
  NODE_DATES,
  OUTBOX_DATES,
  type FailedOut,
  type LatencyOut,
  type LatencyType,
  type NodeOut,
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
}
