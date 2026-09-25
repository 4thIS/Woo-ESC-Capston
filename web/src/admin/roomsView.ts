import type { BuildingOut, ExamWithRoom, ResvWithRoom, RoomOut } from '@/api/types'
import type { DotState } from '@/components/domain/OutboxDot.vue'
import { buildTree } from '@/components/domain/roomTree'
import { resvWindow } from '@/components/domain/rules'

/** 첫 진입 — 첫 건물의 첫 층. 건물 전체는 행이 너무 많다 (admin-rooms.md "층이나 강의실 몇 개만 고르는 것이 기본") */
export function defaultPick(buildings: BuildingOut[], rooms: RoomOut[]): number[] {
  const first = buildTree(buildings, rooms).find((b) => b.ids.length)
  return first ? first.floors[0].rooms.map((r) => r.id) : []
}

/** 호수 칸 — 고른 방이 여러 건물에 걸치면 건물 글자를 붙인다 (같은 호수가 두 건물에 있을 수 있다) */
export function roomLabeler(
  buildings: BuildingOut[],
  rooms: RoomOut[],
): (roomId: number) => string {
  const many = new Set(rooms.map((r) => r.building_id)).size > 1
  return (roomId) => {
    const r = rooms.find((x) => x.id === roomId)
    if (!r) return '—'
    const b = buildings.find((x) => x.id === r.building_id)
    return many && b ? `${b.bld} ${r.room}` : String(r.room)
  }
}

/** 예약 행의 점 — 추적 중이면 그 상태, 아니면 창 밖이고 노드에 안 간 것만 '예정'. 빈 outbox_ids 는 실패가 아니다 */
export function resvDot(
  r: ResvWithRoom,
  tracked: DotState | undefined,
  today: string,
): DotState | undefined {
  if (tracked) return tracked
  return r.pushed_at === null && resvWindow(r.date, today) === 'later' ? 'scheduled' : undefined
}

export interface ExamGroup {
  id: string
  date_start: string
  date_end: string
  items: ExamWithRoom[]
}
/** 같은 시작일·종료일은 한 행으로 접는다 — 펼치면 방마다 (admin-rooms.md 시험기간). 수정·삭제는 펼친 행에서 */
export function groupExams(exams: ExamWithRoom[], order: (roomId: number) => number): ExamGroup[] {
  const map = new Map<string, ExamGroup>()
  for (const x of exams) {
    const id = `${x.date_start}~${x.date_end}`
    const g = map.get(id) ?? { id, date_start: x.date_start, date_end: x.date_end, items: [] }
    g.items.push(x)
    map.set(id, g)
  }
  const groups = [...map.values()].sort(
    (a, b) => a.date_start.localeCompare(b.date_start) || a.date_end.localeCompare(b.date_end),
  )
  for (const g of groups) g.items.sort((a, b) => order(a.room_id) - order(b.room_id))
  return groups
}

/** '401, 402, 405 외 4곳' */
export const roomsLabel = (labels: string[]) =>
  labels.length <= 3
    ? labels.join(', ')
    : `${labels.slice(0, 3).join(', ')} 외 ${labels.length - 3}곳`
