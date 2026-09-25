import { describe, expect, it } from 'vitest'
import { ApiError, MESSAGES } from '@/api/client'
import {
  conflictMessage,
  examKey,
  floorLabel,
  floorOf,
  resvKey,
  resvWindow,
  slotKey,
  spansOverlap,
} from '@/components/domain/rules'

const span = (s: string, e: string) => {
  const [sh, sm] = s.split(':').map(Number)
  const [eh, em] = e.split(':').map(Number)
  return { s_h: sh, s_m: sm, e_h: eh, e_m: em }
}
const e409 = (detail: string) => new ApiError(409, MESSAGES[409], [], { detail })

describe('rules', () => {
  it('spansOverlap — 걸치면 겹침, 끝이 맞닿으면 아님', () => {
    expect(spansOverlap(span('09:00', '11:00'), span('10:00', '12:00'))).toBe(true)
    expect(spansOverlap(span('09:00', '12:00'), span('10:00', '11:00'))).toBe(true)
    expect(spansOverlap(span('09:00', '10:00'), span('10:00', '11:00'))).toBe(false)
  })

  it('resvWindow — 오늘~+7 은 in, 그 뒤 later(창 밖 — 실패 아님), 어제는 past', () => {
    expect(resvWindow('2026-09-24', '2026-09-25')).toBe('past')
    expect(resvWindow('2026-09-25', '2026-09-25')).toBe('in')
    expect(resvWindow('2026-10-02', '2026-09-25')).toBe('in')
    expect(resvWindow('2026-10-03', '2026-09-25')).toBe('later')
  })

  it('층은 호수 ÷ 100, 100 미만은 기타', () => {
    expect(floorOf(401)).toBe(4)
    expect(floorLabel(401)).toBe('4층')
    expect(floorLabel(1203)).toBe('12층')
    expect(floorOf(5)).toBeNull()
    expect(floorLabel(5)).toBe('기타')
  })

  it('행 키 — 슬롯은 방+요일+시작, 예약·시험기간은 서버 id', () => {
    expect(slotKey({ room_id: 11, day: 1, s_h: 9, s_m: 0 })).toBe('s11-1-9-0')
    expect(resvKey(7)).toBe('r7')
    expect(examKey(7)).toBe('x7')
  })

  it('409 원문을 사람 문장으로 — 모르는 409 는 공통 문장', () => {
    expect(conflictMessage(e409('source 2 슬롯은 source ≥ 2 로만 수정'))).toBe(
      '이 슬롯은 웹에서 수정된 행입니다. CSV로 덮어쓸 수 없습니다.',
    )
    expect(conflictMessage(e409('이 강의실은 이번 주 예약이 가득 찼습니다(노드 용량 24)'))).toBe(
      '이 강의실은 7일 안 예약이 가득 찼습니다(24건). 지난 예약을 정리하세요.',
    )
    expect(conflictMessage(e409('id 소진 — 지난 예약·시험기간을 정리하세요'))).toBe(
      'id 소진 — 지난 예약·시험기간을 정리하세요',
    )
    expect(
      conflictMessage(e409('id 가 다른 방의 것입니다 — 방을 옮기려면 삭제 후 다시 만드세요')),
    ).toBe('다른 강의실의 항목입니다. 목록을 새로 불러옵니다.')
    expect(conflictMessage(e409('신청 상태 예약은 승인 절차로 처리하세요'))).toBe(
      '학생 신청은 신청 대기에서 승인·거절로 처리하세요.',
    )
    expect(conflictMessage(e409('이미 시작 시각이 지난 신청입니다'))).toBe(
      '이미 시작 시각이 지난 신청입니다.',
    )
    expect(conflictMessage(e409('그 시간에 다른 예약·수업이 생겼습니다'))).toBe(
      '그 시간에 다른 예약이나 수업이 생겨 승인할 수 없습니다.',
    )
    expect(conflictMessage(e409('approved 상태에서는 불가'))).toBe('이미 처리된 신청입니다.')
    expect(conflictMessage(e409('constraint violation'))).toBe(MESSAGES[409])
    expect(conflictMessage(new ApiError(409, MESSAGES[409]))).toBe(MESSAGES[409])
  })
})
