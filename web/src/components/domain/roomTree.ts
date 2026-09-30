import type { BuildingOut, RoomOut } from '@/api/types'
import { floorLabel, floorOf } from './rules'

export interface FloorNode {
  key: string
  label: string
  rooms: RoomOut[]
}
export interface BuildingNode {
  key: string
  building: BuildingOut
  floors: FloorNode[]
  ids: number[]
}

/** 건물 → 층 → 호수. 층은 서버에 없어 호수에서 파생한다. query 는 호수 숫자만 거른다 (components.md RoomTree) */
export function buildTree(buildings: BuildingOut[], rooms: RoomOut[], query = ''): BuildingNode[] {
  const q = query.trim()
  const out: BuildingNode[] = []
  for (const b of buildings) {
    const mine = rooms
      .filter((r) => r.building_id === b.id && String(r.room).includes(q))
      .sort((x, y) => x.room - y.room)
    if (q && !mine.length) continue
    const floors: FloorNode[] = []
    for (const r of mine) {
      const key = `${b.id}:${floorOf(r.room) ?? 'etc'}`
      let f = floors.find((x) => x.key === key)
      if (!f) {
        f = { key, label: floorLabel(r.room), rooms: [] }
        floors.push(f)
      }
      f.rooms.push(r)
    }
    out.push({ key: `b${b.id}`, building: b, floors, ids: mine.map((r) => r.id) })
  }
  return out
}

export type Check = 'all' | 'some' | 'none'
export function checkOf(ids: number[], selected: readonly number[]): Check {
  const n = ids.filter((i) => selected.includes(i)).length
  if (n === 0) return 'none'
  return n === ids.length ? 'all' : 'some'
}

/** 건물·층을 누르면 — 전부 골라져 있으면 전부 해제, 아니면 전부 선택 */
export function toggleGroup(ids: number[], selected: readonly number[]): number[] {
  if (checkOf(ids, selected) === 'all') return selected.filter((i) => !ids.includes(i))
  return [...selected, ...ids.filter((i) => !selected.includes(i))]
}

/** 버튼 라벨이 곧 현재 선택 — 닫혀 있어도 읽힌다 (admin-rooms.md) */
export function selectionLabel(
  buildings: BuildingOut[],
  rooms: RoomOut[],
  selected: readonly number[],
  mode: 'multi' | 'single',
): string {
  const order = (r: RoomOut) => buildings.findIndex((b) => b.id === r.building_id)
  const picked = rooms
    .filter((r) => selected.includes(r.id))
    .sort((a, b) => order(a) - order(b) || a.room - b.room)
  if (!picked.length) return '강의실 선택'
  const name = buildings.find((b) => b.id === picked[0].building_id)?.name ?? ''
  if (mode === 'single') return `${name} ${picked[0].room}호`
  const oneBuilding = picked.every((r) => r.building_id === picked[0].building_id)
  if (oneBuilding && picked.length <= 3) return `${name} ${picked.map((r) => r.room).join(' · ')}`
  return `${name} ${picked[0].room} 외 ${picked.length - 1}곳`
}
