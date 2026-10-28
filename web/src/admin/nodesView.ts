import type { NodeOut } from '@/api/types'

const seenAt = (n: NodeOut) => n.last_seen_at?.getTime() ?? Number.NEGATIVE_INFINITY

/** last_seen 오래된 순, 보고 없음(null) 먼저 (admin-nodes.md). 같으면 서버 순서(bld·room·unit) 유지 —
 * 서버 /summary 의 미리보기 정렬과 같은 키. 표시 순서일 뿐 데이터 보정이 아니다 */
export function sortNodes(nodes: NodeOut[]): NodeOut[] {
  return [...nodes].sort((a, b) => {
    const x = seenAt(a)
    const y = seenAt(b)
    return x === y ? 0 : x < y ? -1 : 1
  })
}

/** 방마다 노드 대수 (rooms.units — NodeOut 은 rooms × units 를 다 준다) */
export function unitsByRoom(nodes: NodeOut[]): Map<number, number> {
  const m = new Map<number, number>()
  for (const n of nodes) m.set(n.room_id, Math.max(m.get(n.room_id) ?? 0, n.unit))
  return m
}

/** 노드가 2대인 방만 401-1 · 401-2 (admin-nodes.md 미결 2 — 한 행 = 한 장치) */
export function roomLabel(n: NodeOut, units: Map<number, number>): string {
  return (units.get(n.room_id) ?? 1) > 1 ? `${n.room}-${n.unit}` : String(n.room)
}

/** V 로만 — 퍼센트 환산 금지 (방전 곡선을 모르는 채 환산하면 없는 정밀도를 만든다) */
export const volts = (mv: number | null) => (mv == null ? '—' : `${(mv / 1000).toFixed(2)} V`)

/** 버전 S/R/E/I 를 한 칸에 — 전부 없으면 — */
export function versions(n: NodeOut): string {
  const v = [n.sched_ver, n.resv_ver, n.exam_ver, n.ident_ver]
  return v.every((x) => x == null) ? '—' : v.map((x) => x ?? '—').join('/')
}

/** 건물 Select — 노드 목록에서 파생 (강의실이 없는 건물은 노드도 없다) */
export function buildingOptions(nodes: NodeOut[]): { value: number | ''; label: string }[] {
  const seen = new Map<number, string>()
  for (const n of nodes) seen.set(n.building_id, n.building)
  const list = [...seen]
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label, 'ko'))
  return [{ value: '', label: '전체' }, ...list]
}

/** 강의실 배정 Modal 의 선택지 — 기대 노드(rooms × units)가 곧 배정 가능한 (bld, room, unit) 전부다 */
export function provisionChoices(nodes: NodeOut[], bld: string, room: number | '') {
  const buildings = new Map<string, string>()
  const rooms = new Set<number>()
  for (const n of nodes) {
    buildings.set(n.bld, n.building)
    if (n.bld === bld) rooms.add(n.room)
  }
  return {
    buildings: [...buildings].map(([value, label]) => ({ value, label })),
    rooms: [...rooms].sort((a, b) => a - b).map((r) => ({ value: r, label: `${r}호` })),
    units: nodes
      .filter((n) => n.bld === bld && n.room === room)
      .map((n) => ({
        value: n.unit,
        label: n.mac ? `${n.unit}번 노드 — 사용 중` : `${n.unit}번 노드`,
        mac: n.mac,
      })),
  }
}
