import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { markOf } from '@/admin/assistant/diffMarks'
import WeekGrid from '@/admin/views/week/WeekGrid.vue'
import { weekBlocks, type Placed } from '@/admin/weekView'
import type { PreviewMark, ResvWithRoom, SlotWithRoom } from '@/api/types'

const slot = (o: Partial<SlotWithRoom> = {}): SlotWithRoom => ({
  id: 5,
  room_id: 3,
  day: 5,
  s_h: 15,
  s_m: 0,
  e_h: 17,
  e_m: 0,
  type: 1,
  subject: '자료구조',
  professor: '김교수',
  source: 2,
  ...o,
})
const resv = (o: Partial<ResvWithRoom> = {}): ResvWithRoom => ({
  id: 17,
  room_id: 3,
  date: '2026-11-27',
  s_h: 15,
  s_m: 0,
  e_h: 18,
  e_m: 0,
  type: 5,
  subject: '알고리즘 특강',
  professor: '',
  status: 'approved',
  requester: null,
  pushed_at: null,
  checked_in_at: null,
  checked_out_at: null,
  reject_reason: null,
  ...o,
})
const MON = '2026-11-23'

describe('markOf — 미리보기 변경 표시를 격자 블록에 잇는다', () => {
  const changes: PreviewMark[] = [
    { entity: 'resv', key: 'r17', op: 'add', fields: [] },
    { entity: 'slot', key: 'd5-1600', op: 'change', fields: ['subject'] },
  ]
  it('예약은 r{id}, 시간표는 묶음 안 어느 교시든 d{요일}-{HHMM}', () => {
    const blocks = weekBlocks(
      // 금 15~16 · 16~17 은 이어진 묶음 하나 — 둘째 교시(d5-1600)만 바뀌어도 묶음 전체가 change
      [
        slot({ e_h: 16 }),
        slot({ id: 6, s_h: 16, e_h: 17 }),
        slot({ id: 7, day: 1, s_h: 9, e_h: 10 }),
      ],
      [resv()],
      MON,
    )
    const ops = blocks.map((b) => markOf(b as Placed, changes)?.op ?? null)
    expect(ops).toContain('add')
    expect(ops).toContain('change')
    expect(ops.filter((o) => o === null)).toHaveLength(1)
  })
})

describe('WeekGrid marks — 테두리 + 머리 태그 (admin-assistant.md 「변경 표시」)', () => {
  it('추가 블록에 + 추가 태그와 diff 클래스', () => {
    const blocks = weekBlocks([], [resv()], MON)
    const w = mount(WeekGrid, {
      props: {
        blocks,
        exams: [],
        monday: MON,
        night: false,
        weekend: false,
        marks: (p: Placed) => markOf(p, [{ entity: 'resv', key: 'r17', op: 'add', fields: [] }]),
      },
    })
    const b = w.get('.wk__block')
    expect(b.classes()).toContain('wk__block--diff-add')
    expect(b.get('.wk__tag').text()).toBe('+ 추가')
  })
  it('바뀐 칸은 title 에, 삭제는 과목 취소선 클래스', () => {
    const w = mount(WeekGrid, {
      props: {
        blocks: weekBlocks([slot()], [], MON),
        exams: [],
        monday: MON,
        night: false,
        weekend: false,
        marks: () => ({ op: 'remove' as const, fields: [] }),
      },
    })
    expect(w.get('.wk__block').classes()).toContain('wk__block--diff-remove')
    expect(w.get('.wk__tag').text()).toBe('− 삭제')
    const c = mount(WeekGrid, {
      props: {
        blocks: weekBlocks([slot()], [], MON),
        exams: [],
        monday: MON,
        night: false,
        weekend: false,
        marks: () => ({ op: 'change' as const, fields: ['s_h', 'subject'] }),
      },
    })
    expect(c.get('.wk__block').attributes('title')).toBe('바뀐 칸: 시작 · 이름')
  })
})
