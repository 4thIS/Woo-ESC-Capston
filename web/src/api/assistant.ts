import { ApiError, request } from './client'
import { parseUtc } from '@/lib/time'
import {
  CHANGE_DATES,
  RESV_DATES,
  type ApplyOut,
  type ChangeOut,
  type ModelManifest,
  type PreviewOut,
  type ResvWithRoom,
  type TurnIn,
  type TurnOut,
  type WeekData,
} from './types'

// 미리보기 안쪽(예약 행)까지 Date 로 — request 의 dates 는 맨 위 칸만 바꾼다. 모양은 바꾸지 않는다
function reviveResv(r: ResvWithRoom): ResvWithRoom {
  const o: Record<string, unknown> = { ...r }
  for (const k of RESV_DATES) if (typeof o[k] === 'string') o[k] = parseUtc(o[k] as string)
  return o as unknown as ResvWithRoom
}
const reviveWeek = (w: WeekData): WeekData => ({
  ...w,
  reservations: w.reservations.map(reviveResv),
})
export function revivePreview(p: PreviewOut): PreviewOut {
  const at = p.expires_at as unknown
  return {
    ...p,
    expires_at: typeof at === 'string' ? parseUtc(at) : (at as Date),
    rooms: p.rooms.map((r) => ({
      ...r,
      weeks: r.weeks.map((w) => ({
        ...w,
        before: reviveWeek(w.before),
        after: reviveWeek(w.after),
      })),
    })),
  }
}

// 관리자 전용 + 건물 범위 (spec §6). 범위 밖은 서버가 404
export const assistantApi = {
  /** 모델 안내 — 파일 목록·고정 지시문·출력 문법. 모델 파일 자체는 여기서 받지 않는다 */
  model: () => request<ModelManifest>('GET', '/api/assistant/model'),
  turn: async (t: TurnIn): Promise<TurnOut> => {
    const out = await request<TurnOut>('POST', '/api/assistant/turns', t)
    return out.preview ? { ...out, preview: revivePreview(out.preview) } : out
  },
  /** 저장된 확정 변경 목록을 적용 — 모델 출력을 다시 쓰지 않는다 */
  apply: (previewId: string) =>
    request<ApplyOut>('POST', `/api/assistant/previews/${encodeURIComponent(previewId)}/apply`),
  changes: (limit = 50) =>
    request<ChangeOut[]>('GET', `/api/assistant/changes?limit=${limit}`, undefined, {
      dates: CHANGE_DATES,
    }),
}

export type AssistantFailure =
  | { kind: 'schema_version' }
  | { kind: 'stale'; preview: PreviewOut }
  | { kind: 'expired' }
  | { kind: 'blocked'; blockers: string[] }
  | { kind: 'rate' }

/** 부록 §4 의 오류 본문을 가른다 — 모르는 오류는 null (화면은 e.message) */
export function classify(e: ApiError): AssistantFailure | null {
  const body = (e.detail ?? {}) as { detail?: unknown; preview?: PreviewOut; blockers?: unknown }
  if (e.status === 429) return { kind: 'rate' }
  if (e.status === 409 && body.detail === 'schema_version') return { kind: 'schema_version' }
  if (e.status === 409 && body.detail === 'stale' && body.preview)
    return { kind: 'stale', preview: revivePreview(body.preview) }
  // 404 = 없는·남의 미리보기 — 화면에서는 만료와 같게 다시 요청하라고 안내한다
  if (e.status === 410 || (e.status === 404 && body.detail === '미리보기 없음'))
    return { kind: 'expired' }
  if (e.status === 422 && body.detail === 'blocked' && Array.isArray(body.blockers))
    return { kind: 'blocked', blockers: body.blockers.map(String) }
  return null
}
