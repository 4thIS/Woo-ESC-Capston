import { request } from './client'
import {
  MODEM_DATES,
  OUTBOX_DATES,
  PENDING_DATES,
  type Enqueued,
  type ModemOut,
  type OutboxOut,
  type PendingOut,
  type TokenOut,
} from './types'

export const loraApi = {
  modems: () => request<ModemOut[]>('GET', '/api/lora/modems', undefined, { dates: MODEM_DATES }),
  /** 응답의 token 은 이때 한 번만 받는다 — 서버가 다시 알려주지 않는다 */
  registerModem: (modemId: string) =>
    request<TokenOut>('POST', '/api/lora/modems', { modem_id: modemId }),
  rotateToken: (modemId: string) =>
    request<TokenOut>('POST', `/api/lora/modems/${encodeURIComponent(modemId)}/token`),
  pending: () =>
    request<PendingOut[]>('GET', '/api/lora/pending', undefined, { dates: PENDING_DATES }),
  provision: (mac: string, body: { bld: string; room: number; unit: number }) =>
    request<Enqueued>('POST', `/api/lora/pending/${encodeURIComponent(mac)}/provision`, body),
  /** 서버 전역 10분 1회 — 넘으면 429 */
  broadcastTime: () => request<{ modems: number }>('POST', '/api/lora/time'),
  /** 학교 스코프 최신 limit 건, id 오름차순으로 온다 */
  recentOutbox: (limit: number) =>
    request<OutboxOut[]>('GET', `/api/lora/outbox?limit=${limit}`, undefined, {
      dates: OUTBOX_DATES,
    }),
  /** 재전송은 방 단위 — 본문 {} = SyncIn 기본(schedule·resv·exam 전부) */
  syncRoom: (roomId: number) => request<Enqueued>('POST', `/api/rooms/${roomId}/sync`, {}),
}
