import type { ResvWithRoom, SlotType } from '@/api/types'
import { hm } from '@/lib/time'
import { spansOverlap, toMin } from './rules'
import { parseHm } from './slotForm'

export interface ResvDraft {
  roomId: number
  /** <input type="date"> 값 'YYYY-MM-DD' (KST 달력) */
  date: string
  start: string
  end: string
  type: SlotType
  subject: string
  professor: string
}

/** 예약끼리의 겹침만 막는다 — 슬롯과의 겹침은 의도(휴강 위 특강)일 수 있어 페이지2가 보여 준다 (설계 판정) */
export function resvErrors(
  d: ResvDraft,
  existing: ResvWithRoom[],
  originalId: number | null,
  today: string,
): { date?: string; start?: string; end?: string } {
  if (!d.date) return { date: '날짜를 고르세요' }
  if (d.date < today) return { date: '오늘 이전 날짜에는 만들 수 없습니다' }
  const s = parseHm(d.start)
  if (!s) return { start: '시작 시각을 넣으세요' }
  const e = parseHm(d.end)
  if (!e) return { end: '종료 시각을 넣으세요' }
  if (toMin(...e) <= toMin(...s))
    return { end: '종료는 시작보다 늦어야 합니다 (자정을 넘기지 않습니다)' }
  const span = { s_h: s[0], s_m: s[1], e_h: e[0], e_m: e[1] }
  const hit = existing.find(
    (x) =>
      x.room_id === d.roomId &&
      x.date === d.date &&
      x.id !== originalId &&
      (x.status === 'approved' || x.status === 'requested') &&
      spansOverlap(x, span),
  )
  if (!hit) return {}
  const tag = hit.status === 'requested' ? '신청 · ' : ''
  return { end: `겹칩니다: ${hm(hit.s_h, hit.s_m)}–${hm(hit.e_h, hit.e_m)} ${tag}${hit.subject}` }
}
