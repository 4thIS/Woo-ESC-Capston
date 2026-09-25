import { describe, expect, it } from 'vitest'
import {
  blockBox,
  examDates,
  gridRange,
  layoutDay,
  needsNight,
  needsWeekend,
  timeRows,
  weekBlocks,
} from '@/admin/weekView'
import type { ResvWithRoom, SlotWithRoom } from '@/api/types'

const S = (o: Partial<SlotWithRoom>): SlotWithRoom => ({
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
const V = (o: Partial<ResvWithRoom>): ResvWithRoom => ({
  id: 7,
  room_id: 11,
  date: '2026-09-21',
  s_h: 11,
  s_m: 0,
  e_h: 12,
  e_m: 0,
  type: 5,
  subject: '특강',
  professor: '',
  status: 'approved',
  requester: null,
  pushed_at: null,
  ...o,
})
const monday = '2026-09-21'

describe('weekBlocks', () => {
  it('빈강의실(4)·거절·다른 주는 그리지 않는다 — 예약은 날짜의 요일, 점유는 사용중 슬롯·승인만', () => {
    const b = weekBlocks(
      [S({}), S({ id: 2, type: 4, day: 2 }), S({ id: 3, type: 3, day: 3 })],
      [
        V({}),
        V({ id: 8, date: '2026-09-23', status: 'requested' }),
        V({ id: 9, status: 'rejected' }),
        V({ id: 10, date: '2026-09-28' }),
      ],
      monday,
    )
    expect(b.map((x) => [x.key, x.day, x.busy])).toEqual([
      ['s11-1-10-0', 1, true],
      ['s11-3-10-0', 3, false],
      ['r7', 1, true],
      ['r8', 3, false],
    ])
  })
})

describe('layoutDay', () => {
  it('슬롯과 승인 예약이 겹치면 반씩 — 겹친 구간에만 막대 하나', () => {
    const { placed, overlaps } = layoutDay(weekBlocks([S({})], [V({})], monday))
    expect(placed.map((p) => [p.key, p.lane, p.lanes])).toEqual([
      ['s11-1-10-0', 0, 2],
      ['r7', 1, 2],
    ])
    expect(overlaps).toEqual([{ s: 660, e: 720, lane: 1, lanes: 2 }])
  })
  it('맞닿으면 한 줄, 휴강·신청과의 겹침은 나란히만 (막대 없음)', () => {
    const touch = weekBlocks([S({ e_h: 11 }), S({ id: 2, s_h: 11, e_h: 12 })], [], monday)
    expect(layoutDay(touch).placed.map((p) => p.lanes)).toEqual([1, 1])
    const soft = layoutDay(
      weekBlocks(
        [S({ type: 3 })],
        [V({}), V({ id: 8, s_h: 10, e_h: 11, status: 'requested' })],
        monday,
      ),
    )
    expect(soft.placed.map((p) => p.lanes)).toEqual([2, 2, 2])
    expect(soft.overlaps).toEqual([])
  })
  it('셋이 겹치면 1/3 씩 (디자인 미결 1 — 그대로 그린다)', () => {
    const three = layoutDay(
      weekBlocks([S({}), S({ id: 2, s_m: 30 }), S({ id: 3, s_h: 11 })], [], monday),
    )
    expect(three.placed.map((p) => [p.lane, p.lanes])).toEqual([
      [0, 3],
      [1, 3],
      [2, 3],
    ])
    expect(three.overlaps).toHaveLength(3)
  })
})

describe('격자', () => {
  it('기본 09:00~18:00, 야간 22:00, 09:00 전 블록이 있으면 그 30분부터', () => {
    expect(gridRange([], false)).toEqual({ from: 540, to: 1080 })
    expect(gridRange([], true)).toEqual({ from: 540, to: 1320 })
    const early = weekBlocks([S({ s_h: 7, s_m: 40, e_h: 9 })], [], monday)
    expect(gridRange(early, false)).toEqual({ from: 450, to: 1080 })
    expect(timeRows({ from: 540, to: 600 })).toEqual([540, 570])
    expect(timeRows(gridRange([], false))).toHaveLength(18)
    expect(timeRows(gridRange([], true))).toHaveLength(26)
  })
  it('격자 밖은 잘라 그리고 잘렸다고 알린다 (격자를 늘리지 않는다)', () => {
    expect(blockBox({ s: 1020, e: 1170 }, { from: 540, to: 1080 })).toEqual({
      top: 704,
      height: 88,
      cutEnd: true,
    })
    expect(blockBox({ s: 1110, e: 1170 }, { from: 540, to: 1080 })).toBeNull()
  })
  it('야간은 18:00 넘게 끝나는 블록, 주말은 토·일 블록이 있으면 자동', () => {
    expect(needsNight(weekBlocks([S({ e_h: 18, e_m: 30 })], [], monday))).toBe(true)
    expect(needsNight(weekBlocks([S({ e_h: 18 })], [], monday))).toBe(false)
    expect(needsWeekend(weekBlocks([S({ day: 6 })], [], monday))).toBe(true)
    expect(needsWeekend(weekBlocks([S({})], [], monday))).toBe(false)
  })
  it('시험기간 띠 — 달을 넘어도 그 주의 날짜만', () => {
    const on = examDates(
      [{ id: 1, date_start: '2026-09-30', date_end: '2026-10-02' }],
      '2026-09-28',
    )
    expect([...on]).toEqual(['2026-09-30', '2026-10-01', '2026-10-02'])
  })
})
