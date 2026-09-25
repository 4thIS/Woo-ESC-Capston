import { describe, expect, it } from 'vitest'
import type { ResvMineOut } from '@/api/types'
import {
  activeCount,
  cancelKind,
  checkinState,
  chipDay,
  dateLabel,
  defaultEnd,
  durationText,
  endOptions,
  hmToMin,
  isRed,
  layoutLabel,
  minToHm,
  resvWhen,
  sortMine,
  spanKey,
  startOptions,
  untilText,
} from '../rules'
import { kstMinutes } from '@/lib/time'

const NOW = new Date('2026-10-23T01:42:00Z') // KST 2026-10-23(금) 10:42
const resv = (over: Partial<ResvMineOut> = {}): ResvMineOut => ({
  id: 1,
  date: '2026-10-23',
  s_h: 10,
  s_m: 50,
  e_h: 12,
  e_m: 0,
  type: 6,
  subject: '캡스톤 스터디',
  professor: '',
  status: 'approved',
  requested_at: null,
  decided_at: null,
  reject_reason: null,
  checked_in_at: null,
  cancelled_at: null,
  room_id: 11,
  building: '공학관',
  room: 401,
  ...over,
})

describe('kstMinutes', () => {
  it('KST 자정 경계 — UTC 15:00 은 KST 다음 날 00:00', () => {
    expect(kstMinutes(NOW)).toBe(642)
    expect(kstMinutes(new Date('2026-10-22T15:00:00Z'))).toBe(0)
    expect(kstMinutes(new Date('2026-10-22T14:59:00Z'))).toBe(1439)
  })
})

describe('상태 줄', () => {
  it('layout → 라벨, 색은 RED(1·5·6·7) 만 — 가용성(4)과 따로', () => {
    expect([1, 2, 3, 4, 5, 6, 7, 8].map(layoutLabel)).toEqual([
      '수업중',
      '쉬는시간',
      '휴강',
      '비어있음',
      '시험중',
      '특강',
      '대여중',
      '설정 대기',
    ])
    expect(layoutLabel(99)).toBe('확인 중')
    expect([1, 2, 3, 4, 5, 6, 7, 8].filter(isRed)).toEqual([1, 5, 6, 7])
  })

  it('until — "비어요"로 단정하지 않는다, null 은 자정까지', () => {
    expect(untilText(1, '10:50')).toBe('10:50 까지')
    expect(untilText(4, '13:00')).toBe('13:00 까지')
    expect(untilText(4, null)).toBe('오늘 계속 비어 있어요')
    expect(untilText(6, null)).toBe('자정까지')
  })
})

describe('시간 고르기', () => {
  it('hm ↔ 분, 길이 문장, 날짜 라벨', () => {
    expect(hmToMin('10:05')).toBe(605)
    expect(minToHm(605)).toBe('10:05')
    expect(durationText(180)).toBe('3시간')
    expect(durationText(90)).toBe('1시간 30분')
    expect(durationText(45)).toBe('45분')
    expect(dateLabel('2026-10-24')).toBe('10월 24일 토')
    expect(chipDay('2026-10-26')).toBe('월')
    expect(spanKey({ from: '10:00', to: '13:00' })).toBe('10:00-13:00')
  })

  it('시작 — 5분 단위, 끝 15분 전까지, 오늘은 지금 이후만', () => {
    const span = { from: '10:00', to: '10:30' }
    expect(startOptions(span, null).map(minToHm)).toEqual(['10:00', '10:05', '10:10', '10:15'])
    expect(startOptions(span, hmToMin('10:07')).map(minToHm)).toEqual(['10:10', '10:15'])
    expect(startOptions(span, hmToMin('10:15'))).toEqual([])
  })

  it('끝 — 시작 +15 ~ +120, 구간 끝을 넘지 않는다. 기본은 +60', () => {
    expect(endOptions(600, { from: '10:00', to: '10:30' }).map(minToHm)).toEqual([
      '10:15',
      '10:20',
      '10:25',
      '10:30',
    ])
    const long = endOptions(600, { from: '10:00', to: '21:00' })
    expect(minToHm(long[0])).toBe('10:15')
    expect(minToHm(long[long.length - 1])).toBe('12:00')
    expect(long).toHaveLength(22)
    expect(defaultEnd(600, { from: '10:00', to: '10:30' })).toBe(630)
    expect(defaultEnd(600, { from: '10:00', to: '21:00' })).toBe(660)
  })
})

describe('내 예약', () => {
  it('진행 중 — 시작 전 신청 + 끝나지 않은 승인만 (서버 MAX_ACTIVE 규칙)', () => {
    const list = [
      resv({ id: 1, status: 'requested', s_h: 11, s_m: 0, e_h: 12 }),
      resv({ id: 2, status: 'requested', s_h: 10, s_m: 0, e_h: 11 }),
      resv({ id: 3, status: 'approved', s_h: 10, s_m: 0, e_h: 11 }),
      resv({ id: 4, status: 'approved', s_h: 9, s_m: 0, e_h: 10 }),
      resv({ id: 5, status: 'rejected', date: '2026-10-25' }),
      resv({ id: 6, status: 'approved', date: '2026-10-22', s_h: 23, s_m: 0, e_h: 23, e_m: 50 }),
    ]
    expect(activeCount(list, NOW)).toBe(2)
  })

  it('체크인 창 — 시작 −10 ~ +15분, 밖이면 언제부터인지, 끝난 예약은 없음', () => {
    expect(checkinState(resv({ s_h: 10, s_m: 50 }), NOW)).toEqual({ kind: 'open' })
    expect(checkinState(resv({ s_h: 11, s_m: 0 }), NOW)).toEqual({ kind: 'before', from: '10:50' })
    expect(checkinState(resv({ s_h: 10, s_m: 20 }), NOW)).toEqual({ kind: 'after' })
    expect(checkinState(resv({ date: '2026-10-24', s_h: 10, s_m: 0 }), NOW)).toEqual({
      kind: 'before',
      from: '09:50',
    })
    expect(checkinState(resv({ checked_in_at: new Date('2026-10-23T01:52:00Z') }), NOW)).toEqual({
      kind: 'done',
      at: '10:52',
    })
    expect(checkinState(resv({ s_h: 9, s_m: 0, e_h: 10, e_m: 0 }), NOW)).toBeNull()
    expect(checkinState(resv({ status: 'requested' }), NOW)).toBeNull()
  })

  it('취소 — 신청은 철회(시작 뒤에도), 승인은 시작 전만, 그 밖엔 없음', () => {
    expect(cancelKind(resv({ status: 'requested', s_h: 9 }), NOW)).toBe('withdraw')
    expect(cancelKind(resv(), NOW)).toBe('cancel')
    expect(cancelKind(resv({ s_h: 10, s_m: 0 }), NOW)).toBeNull()
    expect(cancelKind(resv({ status: 'rejected' }), NOW)).toBeNull()
  })

  it('정렬 — 진행 중은 가까운 순, 나머지는 최근 순', () => {
    const a = resv({ id: 1, date: '2026-10-24', s_h: 10, s_m: 0 })
    const b = resv({ id: 2, status: 'requested', s_h: 11, s_m: 0 })
    const c = resv({ id: 3, status: 'rejected', date: '2026-10-20' })
    const d = resv({ id: 4, status: 'cancelled', date: '2026-10-22' })
    const e = resv({ id: 5, s_h: 9, s_m: 0, e_h: 10, e_m: 0 })
    expect(sortMine([c, a, e, d, b], NOW).map((r) => r.id)).toEqual([2, 1, 5, 4, 3])
  })

  it('카드 한 줄 시각', () => {
    expect(resvWhen(resv({ date: '2026-10-24', s_h: 10, s_m: 0, e_h: 12, e_m: 0 }))).toBe(
      '10/24 토 10:00–12:00',
    )
  })
})
