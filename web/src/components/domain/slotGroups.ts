// 연속 교시 묶음 (admin-rooms.md 「연속 교시 묶음」) — 저장은 교시마다 그대로, 관리자 목록에서만 묶어 보이고 묶음째 고친다.
// 문 앞 e-Paper 가 "수업 슬롯 사이 틈"으로 쉬는시간을 그려서 DB 는 교시 단위여야 한다(server room_state).
import type { SlotWithRoom } from '@/api/types'
import { hm } from '@/lib/time'
import { slotKey, spansOverlap, toMin } from './rules'

/** 쉬는시간 상한 — lora_proto LP_BREAK_GAP_MAX_MIN, e-Paper 오늘 목록 · 학생 주간표와 같은 규칙 */
export const BREAK_GAP_MAX_MIN = 15

export interface SlotGroup {
  /** 첫 교시의 slotKey — 목록 행 키 */
  key: string
  room_id: number
  day: number
  /** 분 (0..1440) */
  start: number
  end: number
  slots: SlotWithRoom[]
  /** 첫 교시 길이 · 첫 쉬는시간(한 교시짜리면 0) */
  periodMin: number
  gapMin: number
  /** 교시 길이 · 쉬는시간이 모두 같은가 — 묶음 수정의 '한 교시' 기본값을 그대로 쓸 수 있는가 */
  uniform: boolean
}

const startOf = (s: SlotWithRoom) => toMin(s.s_h, s.s_m)
const endOf = (s: SlotWithRoom) => toMin(s.e_h, s.e_m)
const same = (a: SlotWithRoom, b: SlotWithRoom) =>
  a.room_id === b.room_id &&
  a.day === b.day &&
  a.subject === b.subject &&
  a.professor === b.professor &&
  a.type === b.type &&
  a.source === b.source

/** 같은 방 · 요일 · 과목명(분반 포함) · 교수 · 유형 · 출처이고 틈이 0–15분이면 한 묶음 */
export function groupSlots(slots: SlotWithRoom[]): SlotGroup[] {
  const sorted = [...slots].sort(
    (a, b) => a.room_id - b.room_id || a.day - b.day || startOf(a) - startOf(b),
  )
  const runs: SlotWithRoom[][] = []
  for (const s of sorted) {
    const run = runs[runs.length - 1]
    const last = run?.[run.length - 1]
    const gap = last ? startOf(s) - endOf(last) : -1
    if (run && last && same(last, s) && gap >= 0 && gap <= BREAK_GAP_MAX_MIN) run.push(s)
    else runs.push([s])
  }
  return runs.map((run) => {
    const lens = run.map((s) => endOf(s) - startOf(s))
    const gaps = run.slice(1).map((s, i) => startOf(s) - endOf(run[i]))
    const first = run[0]
    return {
      key: slotKey(first),
      room_id: first.room_id,
      day: first.day,
      start: startOf(first),
      end: endOf(run[run.length - 1]),
      slots: run,
      periodMin: lens[0],
      gapMin: gaps[0] ?? 0,
      uniform: lens.every((l) => l === lens[0]) && gaps.every((g) => g === gaps[0]),
    }
  })
}

/** 시작(분) · 교시 수 · 한 교시 길이 · 쉬는시간으로 교시들을 만든다. 자정을 넘기면 null */
export function periodsFrom(start: number, count: number, len: number, gap: number) {
  const out = Array.from({ length: count }, (_, i) => {
    const s = start + i * (len + gap)
    const e = s + len
    return { s_h: Math.floor(s / 60), s_m: s % 60, e_h: Math.floor(e / 60), e_m: e % 60 }
  })
  const last = out[out.length - 1]
  return last && last.e_h < 24 ? out : null
}

/** 한 교시 = 수업 + 쉬는시간 (admin-rooms.md 「연속 교시 묶음」) — 학교마다 다를 수 있어 둘을 둔다 */
export const PERIOD_PATTERNS: [number, number][] = [
  [50, 10],
  [75, 15],
]
export const patternKey = ([len, gap]: [number, number]) => `${len}-${gap}`
export const patternLabel = ([len, gap]: [number, number]) =>
  gap ? `${len}분 + 쉬는 ${gap}분` : `${len}분 (쉬는시간 없음)`
export const COUNT_OPTIONS = Array.from({ length: 8 }, (_, i) => ({
  value: i + 1,
  label: `${i + 1}`,
}))

/** 시간 상자 값 — 시작 'HH:MM' · 교시 수 · 한 교시 'len-gap' */
export interface PeriodDraft {
  start: string
  count: number
  pattern: string
}
const HM = /^(\d{2}):(\d{2})$/
/** 시간 상자 → 교시들. 시작이 비었거나 자정을 넘기면 null */
export function periodsOf(d: PeriodDraft) {
  const m = HM.exec(d.start)
  if (!m) return null
  const [len, gap] = d.pattern.split('-').map(Number)
  return periodsFrom(Number(m[1]) * 60 + Number(m[2]), d.count, len, gap)
}

/** 같은 방 · 요일에서 교시들과 겹치는 첫 슬롯 문장 — 없으면 ''. exclude 는 지금 고치는 묶음의 교시 키 */
export function firstOverlap(
  existing: SlotWithRoom[],
  roomId: number,
  day: number,
  periods: { s_h: number; s_m: number; e_h: number; e_m: number }[],
  exclude: Set<string> = new Set(),
): string {
  const hit = existing.find(
    (x) =>
      x.room_id === roomId &&
      x.day === day &&
      !exclude.has(slotKey(x)) &&
      periods.some((p) => spansOverlap(x, p)),
  )
  return hit ? `겹칩니다: ${hm(hit.s_h, hit.s_m)}–${hm(hit.e_h, hit.e_m)} ${hit.subject}` : ''
}
