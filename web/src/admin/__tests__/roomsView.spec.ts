import { describe, expect, it } from 'vitest'
import {
  defaultPick,
  groupExams,
  logResult,
  resvDot,
  resvUse,
  roomLabeler,
  roomsLabel,
  splitResv,
} from '@/admin/roomsView'
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
    checked_in_at: null,
    checked_out_at: null,
    reject_reason: null,
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

describe('resvUse — 예약 표의 상태 (사용중·조기 퇴실을 가린다)', () => {
  // 지금 = KST 2026-10-05(월) 10:42
  const NOW = new Date('2026-10-05T01:42:00Z')
  const who = { email: 's1@mjc.ac.kr', name: '김민준', student_no: '20231234' }
  const r = (o: Partial<ResvWithRoom>): ResvWithRoom => ({
    id: 7,
    room_id: 11,
    date: '2026-10-05',
    s_h: 10,
    s_m: 0,
    e_h: 12,
    e_m: 0,
    type: 6,
    subject: '스터디',
    professor: '',
    status: 'approved',
    requester: who,
    pushed_at: null,
    checked_in_at: null,
    checked_out_at: null,
    reject_reason: null,
    ...o,
  })
  const inAt = new Date('2026-10-05T01:01:00Z') // 10:01 체크인
  it('학생 예약 — 체크인·퇴실·시각으로 여섯 상태', () => {
    expect(resvUse(r({ s_h: 11 }), NOW)).toEqual({ label: '예정', tone: 'neutral' })
    expect(resvUse(r({ s_h: 10, s_m: 50 }), NOW)).toEqual({ label: '체크인 대기', tone: 'neutral' })
    expect(resvUse(r({ s_h: 10, s_m: 27 }), NOW)).toEqual({ label: '체크인 대기', tone: 'neutral' }) // s+15
    expect(resvUse(r({ s_h: 10, s_m: 26 }), NOW)).toEqual({ label: '미체크인', tone: 'neutral' }) // s+16
    expect(resvUse(r({ checked_in_at: inAt }), NOW)).toEqual({ label: '사용중', tone: 'busy' })
    expect(resvUse(r({ e_h: 10, e_m: 30, checked_in_at: inAt }), NOW)).toEqual({
      label: '사용 완료',
      tone: 'neutral',
    })
    const out = r({
      e_h: 10,
      e_m: 23,
      checked_in_at: inAt,
      checked_out_at: new Date('2026-10-05T01:23:00Z'),
    })
    expect(resvUse(out, NOW)).toEqual({ label: '조기 퇴실 10:23', tone: 'neutral' })
    expect(resvUse(r({ date: '2026-10-04', s_h: 9 }), NOW)).toEqual({
      label: '미체크인',
      tone: 'neutral',
    }) // 어제
    expect(resvUse(r({ date: '2026-10-06' }), NOW)).toEqual({ label: '예정', tone: 'neutral' }) // 내일
  })
  it('관리자가 넣은 예약은 체크인이 없다 — 상태 없음', () => {
    expect(resvUse(r({ requester: null }), NOW)).toBeNull()
  })
})

describe('예약 / 예약 로그 나누기', () => {
  // 지금 = KST 2026-10-05(월) 10:42
  const NOW = new Date('2026-10-05T01:42:00Z')
  const who = { email: 's1@mjc.ac.kr', name: '김민준', student_no: '20231234' }
  const inAt = new Date('2026-10-05T01:01:00Z')
  const r = (id: number, o: Partial<ResvWithRoom>): ResvWithRoom => ({
    id,
    room_id: 11,
    date: '2026-10-05',
    s_h: 10,
    s_m: 0,
    e_h: 12,
    e_m: 0,
    type: 6,
    subject: '스터디',
    professor: '',
    status: 'approved',
    requester: who,
    pushed_at: null,
    checked_in_at: null,
    checked_out_at: null,
    reject_reason: null,
    ...o,
  })
  const rows = [
    r(1, { s_h: 13, e_h: 14 }), // 예정 → 예약
    r(2, { checked_in_at: inAt }), // 사용중 → 예약
    r(3, {
      e_h: 10,
      e_m: 23,
      checked_in_at: inAt,
      checked_out_at: new Date('2026-10-05T01:23:00Z'),
    }), // 조기 퇴실 → 로그
    r(4, { date: '2026-10-04', checked_in_at: new Date('2026-10-04T01:01:00Z') }), // 어제 사용 완료 → 로그
    r(5, { status: 'cancelled', date: '2026-10-06' }), // 취소(미래여도) → 로그
    r(6, { status: 'rejected', reject_reason: '학과 행사' }),
    r(7, { status: 'expired', date: '2026-10-03' }),
    r(8, { status: 'requested', s_h: 15, e_h: 16 }), // 신청 대기는 어느 쪽도 아니다(위 블록)
    r(9, { date: '2026-08-01' }), // 30일보다 전 → 기본 범위 밖
    r(10, { requester: null, date: '2026-10-02' }), // 관리자가 넣은 지난 예약
  ]
  it('예약은 안 끝난 승인만, 로그는 끝난 승인·취소·거절·만료를 최근 것부터 (기본 30일)', () => {
    const { live, log } = splitResv(rows, NOW, false)
    expect(live.map((x) => x.id)).toEqual([2, 1]) // 시작 순
    // 최근 것부터: 날짜 → 시작 → id 내림차순 (5: 10/6, 6·3: 10/5 10:00, 4: 10/4, 7: 10/3, 10: 10/2)
    expect(log.map((x) => x.id)).toEqual([5, 6, 3, 4, 7, 10])
    expect(splitResv(rows, NOW, true).log.map((x) => x.id)).toContain(9) // 전체 보기
    expect(log.map((x) => x.id)).not.toContain(9)
  })
  it('로그의 결과 — 조기 퇴실·사용 완료·미체크인·취소·거절(사유)·만료·관리자 종료', () => {
    const res = (id: number) => logResult(rows.find((x) => x.id === id)!)
    expect(res(3)).toBe('조기 퇴실 10:23')
    expect(res(4)).toBe('사용 완료')
    expect(res(5)).toBe('취소됨')
    expect(res(6)).toBe('거절됨 · 학과 행사')
    expect(res(7)).toBe('만료됨')
    expect(res(10)).toBe('종료')
    expect(logResult(r(11, { date: '2026-10-04' }))).toBe('미체크인')
  })
})
