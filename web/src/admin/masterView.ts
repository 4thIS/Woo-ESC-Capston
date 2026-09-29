import type {
  BuildingOut,
  ExamWithRoom,
  ModemOut,
  NodeOut,
  ResvWithRoom,
  RoomOut,
  SlotWithRoom,
} from '@/api/types'
import { WARNING_LABEL } from '@/components/domain/NodeStateBadge.vue'
import { volts } from './nodesView'

/** bld 는 대문자 한 글자이고 학교가 달라도 겹칠 수 없다 — 건물은 26개가 상한 (admin-master.md) */
export const BLD_MAX = 26
/** 범위로 추가 한 번에 — 1–9999 를 잘못 넣어 9999번 POST 가 나가지 않게 (설계 판정) */
export const RANGE_MAX = 100
export const UNIT_OPTIONS = [
  { value: 1, label: '1 (문 하나)' },
  { value: 2, label: '2 (문 둘)' },
]
export const OTHER_SCHOOL_BLD = '다른 학교가 이미 쓰는 글자입니다. 다른 글자를 고르세요.'

/** 입력 칸은 친 글자를 대문자로 — 대소문자가 섞이면 CSV·e-Paper 푸터에서 헷갈린다 */
export const normalizeBld = (v: string) =>
  v
    .toUpperCase()
    .replace(/[^A-Z]/g, '')
    .slice(0, 1)

/** 내 학교 것만 미리 막는다 — 다른 학교 글자는 저장할 때 409 로만 안다 */
export function bldProblem(
  bld: string,
  buildings: BuildingOut[],
  selfId: number | null,
): string | null {
  if (!/^[A-Z]$/.test(bld)) return '영문 대문자 한 글자를 넣으세요.'
  if (buildings.some((b) => b.id !== selfId && b.bld.toUpperCase() === bld))
    return '이 학교가 이미 쓰는 글자입니다.'
  return null
}
export const usedBlds = (buildings: BuildingOut[]) => buildings.map((b) => b.bld).join(' ')

/** 그 학교 모뎀만 (서버가 이미 거른다). 다른 건물이 쓰는 모뎀도 고를 수 있지만 라벨로 알린다 */
export function modemOptions(modems: ModemOut[], buildings: BuildingOut[], selfId: number | null) {
  return [
    { value: '', label: '미배정' },
    ...modems.map((m) => {
      const other = buildings.find((b) => b.id !== selfId && b.modem_id === m.modem_id)
      return {
        value: m.modem_id,
        label: other ? `${m.modem_id} · ${other.name} 사용 중` : m.modem_id,
      }
    }),
  ]
}

/** 모뎀을 바꾸면 서버가 대기 전송을 옮기고 양쪽에 config 를 다시 내린다 — 건수를 숫자로 적는다 */
export function modemChangeText(
  queued: number | null,
  from: string | null,
  to: string | null,
): string {
  const n = queued === null ? '전송' : queued >= 500 ? '500건 이상' : `${queued}건`
  const move = to
    ? `대기 중 ${n}이 ${to} 로 옮겨집니다.`
    : `대기 중 ${n}이 보낼 모뎀 없이 남습니다.`
  const config =
    from && to
      ? `옛 모뎀(${from})과 새 모뎀 양쪽이 설정을 다시 받습니다.`
      : from
        ? `옛 모뎀(${from})이 설정을 다시 받고, 이 건물 강의실은 갱신을 받지 못합니다.`
        : `새 모뎀(${to})이 설정을 받습니다.`
  return `${move} ${config}`
}

/** 마스터 표의 노드 칸 — 판정은 서버(warnings), 문구는 노드 화면과 같다 */
export function roomNodeText(room: RoomOut, nodes: NodeOut[]): string {
  const mine = nodes.filter((n) => n.room_id === room.id)
  if (!mine.some((n) => n.last_seen_at)) return '단말 없음'
  if (mine.some((n) => n.warnings.includes('unseen'))) return WARNING_LABEL.unseen
  const mv = mine.map((n) => n.batt_mv).filter((v): v is number => v !== null)
  return mv.length ? `연결됨 · ${volts(Math.min(...mv))}` : '연결됨'
}

export interface RangeChip {
  room: number
  exists: boolean
}
export function rangeProblem(start: string, end: string): string | null {
  const ok = (v: string) => /^\d+$/.test(v) && Number(v) >= 1 && Number(v) <= 9999
  if (!ok(start) || !ok(end)) return '시작·끝 호수를 1~9999 로 넣으세요'
  if (Number(end) < Number(start)) return '끝 호수가 시작 호수보다 작습니다'
  if (Number(end) - Number(start) + 1 > RANGE_MAX)
    return `한 번에 ${RANGE_MAX}곳까지 만들 수 있습니다`
  return null
}
/** 범위 문법을 늘리지 않는다 — 칩으로 보이고 눌러서 뺀다. 이미 있는 호수는 표시만 (admin-master.md) */
export function rangeRooms(start: number, end: number, existing: number[]): RangeChip[] {
  return Array.from({ length: end - start + 1 }, (_, i) => ({
    room: start + i,
    exists: existing.includes(start + i),
  }))
}

export interface RoomCounts {
  slots: number
  resv: number
  exams: number
}
/** 강의실 삭제 확인에 적을 개수 — 건물 단위 조회를 room_id 로 센다 (admin-master.md 미결 3). 예약은 살아 있는 것만 */
export function countFor(
  roomId: number,
  slots: SlotWithRoom[],
  resv: ResvWithRoom[],
  exams: ExamWithRoom[],
): RoomCounts {
  return {
    slots: slots.filter((s) => s.room_id === roomId).length,
    resv: resv.filter(
      (r) => r.room_id === roomId && (r.status === 'approved' || r.status === 'requested'),
    ).length,
    exams: exams.filter((x) => x.room_id === roomId).length,
  }
}
export function roomDeleteLines(
  buildingName: string,
  room: RoomOut,
  counts: RoomCounts | null,
  nodes: NodeOut[],
): string[] {
  const lines = [`${buildingName} ${room.room}호를 지웁니다.`]
  if (!counts) lines.push('딸린 시간표·예약 수를 불러오지 못했습니다. 있으면 함께 지워집니다.')
  else {
    const parts = [
      counts.slots ? `시간표 ${counts.slots}건` : '',
      counts.resv ? `예약 ${counts.resv}건` : '',
      counts.exams ? `시험기간 ${counts.exams}건` : '',
    ].filter((x) => x)
    lines.push(
      parts.length
        ? `${parts.join(' · ')}이 함께 지워집니다.`
        : '딸린 시간표·예약·시험기간이 없습니다.',
    )
  }
  const units = nodes.filter((n) => n.room_id === room.id && n.mac).map((n) => n.unit)
  if (units.length) lines.push(`문 앞 단말(unit ${units.join(', ')})은 갱신을 받지 못하게 됩니다.`)
  return lines
}
