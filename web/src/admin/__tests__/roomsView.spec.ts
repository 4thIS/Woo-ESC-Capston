import { describe, expect, it } from 'vitest'
import { defaultPick, roomLabeler } from '@/admin/roomsView'
import type { BuildingOut, RoomOut } from '@/api/types'

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
