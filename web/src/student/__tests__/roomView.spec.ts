import { describe, expect, it } from 'vitest'
import type { BusySpan, RoomStateOut } from '@/api/types'
import { buildingsOf, nextFree, todayRows } from '@/student/roomView'

const room = (over: Partial<RoomStateOut>): RoomStateOut => ({
  room_id: 1,
  building_id: 3,
  building: '공학관',
  bld: 'E',
  room: 401,
  layout: 4,
  until: null,
  ...over,
})
const span = (from: string, to: string, over: Partial<BusySpan> = {}): BusySpan => ({
  from,
  to,
  label: '수업',
  type: 1,
  mine: false,
  status: null,
  ...over,
})

describe('roomView', () => {
  it('건물 — 방 목록에서 파생, 글자 순, 강의실 수·빈 곳 수', () => {
    const out = buildingsOf([
      room({ room_id: 1, building_id: 4, building: '운영관', bld: 'K', room: 101, layout: 1 }),
      room({ room_id: 2, room: 401, layout: 1 }),
      room({ room_id: 3, room: 402 }),
      room({ room_id: 4, room: 403, layout: 2 }),
    ])
    expect(out).toEqual([
      { id: 3, name: '공학관', bld: 'E', rooms: 3, free: 1 },
      { id: 4, name: '운영관', bld: 'K', rooms: 1, free: 0 },
    ])
  })

  it('오늘 목록 — 빈 구간도 행, 지금 행 하나, 내 신청 표시', () => {
    const rows = todayRows(
      [
        span('15:00', '16:00', {
          label: '캡스톤 스터디',
          type: 6,
          mine: true,
          status: 'requested',
        }),
        span('10:00', '13:00', { label: '알고리즘 외 1건' }),
      ],
      642,
    )
    expect(rows.map((r) => `${r.from}-${r.to} ${r.label}${r.now ? ' *' : ''}`)).toEqual([
      '09:00-10:00 비어있음',
      '10:00-13:00 알고리즘 외 1건 *',
      '13:00-15:00 비어있음',
      '15:00-16:00 캡스톤 스터디',
      '16:00-21:00 비어있음',
    ])
    expect(rows[0].type).toBeNull()
    expect(rows[3]).toMatchObject({ type: 6, mine: true, requested: true, now: false })
  })

  it('오늘 목록 — 운영 시간 밖 블록이면 창을 넓히고, 블록이 없으면 하루 전체가 빈 행 하나', () => {
    expect(todayRows([], 600)).toEqual([
      {
        from: '09:00',
        to: '21:00',
        label: '비어있음',
        type: null,
        mine: false,
        requested: false,
        now: true,
      },
    ])
    expect(todayRows([span('07:30', '09:30')], 480).map((r) => `${r.from}-${r.to}`)).toEqual([
      '07:30-09:30',
      '09:30-21:00',
    ])
    expect(todayRows([], 480).some((r) => r.now)).toBe(false)
  })

  it('다음 비는 시간 — 오늘(free 첫 날)의 첫 구간, 없으면 null', () => {
    expect(nextFree([{ date: '2026-10-23', spans: [{ from: '13:00', to: '15:00' }] }])).toEqual({
      from: '13:00',
      to: '15:00',
    })
    expect(nextFree([{ date: '2026-10-23', spans: [] }])).toBeNull()
    expect(nextFree([])).toBeNull()
  })
})
