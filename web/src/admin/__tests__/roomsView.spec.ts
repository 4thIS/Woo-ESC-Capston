import { describe, expect, it } from 'vitest'
import { defaultPick, groupExams, resvDot, roomLabeler, roomsLabel } from '@/admin/roomsView'
import type { BuildingOut, ExamWithRoom, ResvWithRoom, RoomOut } from '@/api/types'

const B = (id: number, name: string, bld: string): BuildingOut => ({
  id,
  school_id: 1,
  name,
  bld,
  modem_id: null,
})
const R = (id: number, building_id: number, room: number): RoomOut => ({
  id,
  building_id,
  room,
  units: 1,
  reservable: false,
})
const buildings = [B(1, '공학관', 'E'), B(2, '사회관', 'S')]
const rooms = [R(13, 1, 501), R(11, 1, 401), R(12, 1, 402), R(21, 2, 101)]

describe('roomsView', () => {
  it('첫 진입 — 첫 건물의 첫 층 (방이 없는 건물은 건너뛴다)', () => {
    expect(defaultPick(buildings, rooms)).toEqual([11, 12])
    expect(defaultPick([B(9, '빈 건물', 'Z'), ...buildings], rooms)).toEqual([11, 12])
    expect(defaultPick(buildings, [])).toEqual([])
  })
  it('호수 칸 — 한 건물이면 호수만, 여러 건물이면 건물 글자를 붙인다', () => {
    expect(roomLabeler(buildings, [rooms[1]])(11)).toBe('401')
    const many = roomLabeler(buildings, [rooms[1], rooms[3]])
    expect(many(11)).toBe('E 401')
    expect(many(21)).toBe('S 101')
    expect(many(99)).toBe('—')
  })
})

describe('resvDot — 예약 행의 점', () => {
  const r = (o: Partial<ResvWithRoom>): ResvWithRoom => ({
    id: 7,
    room_id: 11,
    date: '2026-10-05',
    s_h: 10,
    s_m: 0,
    e_h: 11,
    e_m: 0,
    type: 5,
    subject: 'OT',
    professor: '',
    status: 'approved',
    requester: null,
    pushed_at: null,
    ...o,
  })
  it('창 밖이고 노드에 안 간 것(pushed_at null)만 예정 — 실패로 그리지 않는다', () => {
    expect(resvDot(r({}), undefined, '2026-09-25')).toBe('scheduled')
    expect(resvDot(r({ date: '2026-09-30' }), undefined, '2026-09-25')).toBeUndefined()
    expect(resvDot(r({ pushed_at: new Date() }), undefined, '2026-09-25')).toBeUndefined()
    expect(resvDot(r({ date: '2026-09-20' }), undefined, '2026-09-25')).toBeUndefined()
  })
  it('추적 중이면 그 상태가 먼저', () => {
    expect(resvDot(r({}), 'queued', '2026-09-25')).toBe('queued')
  })
})

describe('시험기간 묶기', () => {
  const X = (id: number, room_id: number, ds: string, de: string): ExamWithRoom => ({
    id,
    room_id,
    date_start: ds,
    date_end: de,
  })
  it('같은 시작일·종료일은 한 행 — 날짜순, 행 안은 트리 순서', () => {
    const order = (roomId: number) => [12, 11, 13].indexOf(roomId)
    const g = groupExams(
      [
        X(1, 11, '2026-10-19', '2026-10-23'),
        X(2, 12, '2026-10-19', '2026-10-23'),
        X(3, 13, '2026-10-12', '2026-10-16'),
      ],
      order,
    )
    expect(g.map((x) => x.id)).toEqual(['2026-10-12~2026-10-16', '2026-10-19~2026-10-23'])
    expect(g[1].items.map((x) => x.room_id)).toEqual([12, 11])
  })
  it('셋까지 나열, 넘으면 외 N곳', () => {
    expect(roomsLabel(['401', '402'])).toBe('401, 402')
    expect(roomsLabel(['401', '402', '405', '406', '407'])).toBe('401, 402, 405 외 2곳')
  })
})
