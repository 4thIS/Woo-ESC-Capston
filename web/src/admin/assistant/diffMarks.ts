import type { DiffOp, PreviewMark } from '@/api/types'
import type { Block } from '../weekView'

export interface BlockMark {
  op: DiffOp
  fields: string[]
}

const pad = (n: number) => String(n).padStart(2, '0')

/** 미리보기의 변경 표시(부록 §4 — 정규 시간표 d{요일}-{HHMM} · 예약 r{id} · 시험기간 e{id})를 격자 블록에 잇는다.
 * 연속 교시 묶음은 안의 교시 하나라도 바뀌면 묶음 전체가 바뀐 것으로 본다 (admin-assistant.md 「변경 표시」) */
export function markOf(b: Block, changes: PreviewMark[]): BlockMark | undefined {
  const keys = b.resv
    ? [`r${b.resv.id}`]
    : (b.group?.slots ?? (b.slot ? [b.slot] : [])).map(
        (s) => `d${s.day}-${pad(s.s_h)}${pad(s.s_m)}`,
      )
  const hit = changes.find((c) => c.entity !== 'exam' && keys.includes(c.key))
  return hit && { op: hit.op, fields: hit.fields }
}

/** 바뀐 칸 이름 — 격자 블록 title (admin-assistant.md 「변경 표시」 `바뀐 칸: 시작 · 이름`) */
const FIELD_LABEL: Record<string, string> = {
  s_h: '시작',
  s_m: '시작',
  e_h: '끝',
  e_m: '끝',
  subject: '이름',
  professor: '교수',
  type: '유형',
  date: '날짜',
  day: '요일',
}
export const fieldsText = (fields: string[]) =>
  [...new Set(fields.map((f) => FIELD_LABEL[f] ?? f))].join(' · ')
