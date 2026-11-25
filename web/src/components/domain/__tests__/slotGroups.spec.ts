import { describe, expect, it } from 'vitest'
import type { SlotWithRoom } from '@/api/types'
import { groupSlots, periodsFrom } from '@/components/domain/slotGroups'

let id = 0
const s = (
  day: number,
  from: string,
  to: string,
  over: Partial<SlotWithRoom> = {},
): SlotWithRoom => {
  const [s_h, s_m] = from.split(':').map(Number)
  const [e_h, e_m] = to.split(':').map(Number)
  return {
    id: ++id,
    room_id: 1,
    day,
    s_h,
    s_m,
    e_h,
    e_m,
    type: 1,
    subject: '인공지능기초 102',
    professor: '정필성',
    source: 2,
    ...over,
  }
}

describe('groupSlots — 연속 교시 묶음 (admin-rooms.md)', () => {
  it('같은 과목·교수·유형·출처가 쉬는시간(15분 이하)으로 이어지면 한 묶음, 교시 길이·쉬는시간을 안다', () => {
    const g = groupSlots([s(2, '10:00', '10:50'), s(2, '09:00', '09:50'), s(2, '11:00', '11:50')])
    expect(g).toHaveLength(1)
    expect(g[0]).toMatchObject({
      day: 2,
      start: 540,
      end: 710,
      periodMin: 50,
      gapMin: 10,
      uniform: true,
    })
    expect(g[0].slots.map((x) => x.s_h)).toEqual([9, 10, 11])
  })

  it('분반(과목명)·교수·유형·출처·방·요일이 다르거나 틈이 15분을 넘으면 갈린다', () => {
    const g = groupSlots([
      s(2, '09:00', '09:50'),
      s(2, '10:00', '10:50', { subject: '인공지능기초 101' }),
      s(2, '11:00', '11:50', { subject: '인공지능기초 101', professor: '김' }),
      s(2, '12:00', '12:50', { subject: '인공지능기초 101', professor: '김', type: 3 }),
      s(2, '13:00', '13:50', { subject: '인공지능기초 101', professor: '김', type: 3, source: 3 }),
      s(2, '14:06', '14:50', { subject: '인공지능기초 101', professor: '김', type: 3, source: 3 }),
      s(3, '09:00', '09:50'),
      s(2, '09:00', '09:50', { room_id: 2 }),
    ])
    expect(g).toHaveLength(8)
  })

  it('틈이 정확히 15분이면 잇고, 맞닿기만 해도(틈 0) 잇는다', () => {
    expect(groupSlots([s(1, '09:00', '09:45'), s(1, '10:00', '10:45')])).toHaveLength(1)
    expect(groupSlots([s(1, '09:00', '10:00'), s(1, '10:00', '11:00')])).toHaveLength(1)
  })

  it('교시 길이·쉬는시간이 고르지 않으면 uniform=false', () => {
    const [g] = groupSlots([s(1, '09:00', '09:50'), s(1, '10:00', '11:15')])
    expect(g.uniform).toBe(false)
  })

  it('한 교시짜리도 묶음 하나 — 목록은 늘 묶음 단위로 그린다', () => {
    const [g] = groupSlots([s(3, '14:00', '17:00', { subject: '창업캡스톤2' })])
    expect(g.slots).toHaveLength(1)
    expect(g).toMatchObject({ start: 840, end: 1020 })
  })
})

describe('periodsFrom — 시작 · 교시 수 · 한 교시로 교시를 만든다', () => {
  it('10:00 부터 3교시, 50분 + 쉬는 10분', () => {
    expect(periodsFrom(600, 3, 50, 10)).toEqual([
      { s_h: 10, s_m: 0, e_h: 10, e_m: 50 },
      { s_h: 11, s_m: 0, e_h: 11, e_m: 50 },
      { s_h: 12, s_m: 0, e_h: 12, e_m: 50 },
    ])
  })
  it('자정을 넘기면 null — 하루 안에서만 만든다', () => {
    expect(periodsFrom(22 * 60, 3, 50, 10)).toBeNull()
  })
})
