import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import WeekGrid from '@/admin/views/week/WeekGrid.vue'
import { weekBlocks } from '@/admin/weekView'
import type { ResvWithRoom, SlotWithRoom } from '@/api/types'

const S = (o: Partial<SlotWithRoom> = {}): SlotWithRoom => ({
  id: 1,
  room_id: 11,
  day: 1,
  s_h: 10,
  s_m: 0,
  e_h: 12,
  e_m: 0,
  type: 1,
  subject: '캡스톤디자인',
  professor: '김교수',
  source: 2,
  ...o,
})
const V = (o: Partial<ResvWithRoom> = {}): ResvWithRoom => ({
  id: 7,
  room_id: 11,
  date: '2026-09-23',
  s_h: 13,
  s_m: 0,
  e_h: 15,
  e_m: 0,
  type: 5,
  subject: '특강',
  professor: '학생처',
  status: 'approved',
  requester: null,
  pushed_at: null,
  checked_in_at: null,
  checked_out_at: null,
  reject_reason: null,
  ...o,
})
const MON = '2026-09-21'
const mk = (props: Record<string, unknown> = {}) =>
  mount(WeekGrid, {
    props: {
      blocks: weekBlocks([S()], [V()], MON),
      exams: [{ id: 3, room_id: 11, date_start: '2026-09-22', date_end: '2026-09-22' }],
      monday: MON,
      night: false,
      weekend: false,
      ...props,
    },
  })

describe('WeekGrid', () => {
  it('블록 두 개 · 라벨 · 시험기간 띠 · 5열', () => {
    const w = mk()
    expect(w.findAll('.wk__head')).toHaveLength(5)
    expect(w.findAll('.wk__block').map((b) => b.get('.wk__label').text())).toEqual([
      '수업중',
      '예약 · 특강',
    ])
    expect(w.findAll('.wk__exam')).toHaveLength(1)
  })

  it('editable 이 아니면 셀이 비활성, editable 이면 셀 클릭이 cell(day, t) 를 낸다', async () => {
    expect(mk().get('.wk__cell').attributes('disabled')).toBeDefined()
    const w = mk({ editable: true })
    await w.get('.wk__cell').trigger('click')
    expect(w.emitted('cell')?.[0]).toEqual([{ day: 1, t: 540 }])
  })

  it('블록 클릭 → block, clickable 이면 button 역할과 이름', async () => {
    const w = mk({ clickable: () => true })
    const b = w.get('.wk__block')
    expect(b.attributes('role')).toBe('button')
    expect(b.attributes('aria-label')).toBe('월 10:00–12:00 수업중 캡스톤디자인')
    await b.trigger('click')
    expect(w.emitted('block')).toHaveLength(1)
  })

  it('failed 면 실패 테두리 클래스, dot 슬롯은 블록마다', () => {
    const w = mount(WeekGrid, {
      props: {
        blocks: weekBlocks([S()], [], MON),
        exams: [],
        monday: MON,
        night: false,
        weekend: false,
        failed: () => true,
      },
      slots: { dot: '<i class="d" />' },
    })
    expect(w.get('.wk__block').classes()).toContain('wk__block--failed')
    expect(w.findAll('.wk__dot .d')).toHaveLength(1)
  })

  it('rangeBlocks 가 있으면 격자 범위를 그것으로 잡는다 (기존│수정 두 격자 맞춤)', () => {
    const early = weekBlocks([S({ s_h: 8, s_m: 0 })], [], MON)
    const w = mk({ rangeBlocks: early })
    expect(w.get('.wk__time').text()).toBe('08:00')
  })
})
