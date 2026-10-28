import type { SlotType, SlotWithRoom } from '@/api/types'
import { hm } from '@/lib/time'
import { slotKey, spansOverlap, toMin } from './rules'

export interface SlotDraft {
  roomId: number
  day: number
  /** <input type="time"> 값 'HH:MM' */
  start: string
  end: string
  type: SlotType
  subject: string
  professor: string
}

const HM = /^(\d{2}):(\d{2})$/
export function parseHm(v: string): [number, number] | null {
  const m = HM.exec(v)
  return m ? [Number(m[1]), Number(m[2])] : null
}

/** 저장 전 검사 — 서버는 같은 키(요일+시작)만 막는다. 09–11 과 10–12 가 둘 다 들어가지 않게 여기서 (components.md) */
export function slotErrors(
  d: SlotDraft,
  existing: SlotWithRoom[],
  original: SlotWithRoom | null,
): { start?: string; end?: string } {
  const s = parseHm(d.start)
  if (!s) return { start: '시작 시각을 넣으세요' }
  const e = parseHm(d.end)
  if (!e) return { end: '종료 시각을 넣으세요' }
  if (toMin(...e) <= toMin(...s))
    return { end: '종료는 시작보다 늦어야 합니다 (자정을 넘기지 않습니다)' }
  const span = { s_h: s[0], s_m: s[1], e_h: e[0], e_m: e[1] }
  const self = original ? slotKey(original) : null
  const hit = existing.find(
    (x) =>
      x.room_id === d.roomId && x.day === d.day && slotKey(x) !== self && spansOverlap(x, span),
  )
  return hit
    ? { end: `겹칩니다: ${hm(hit.s_h, hit.s_m)}–${hm(hit.e_h, hit.e_m)} ${hit.subject}` }
    : {}
}
