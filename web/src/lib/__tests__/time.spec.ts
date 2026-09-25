import { describe, expect, it } from 'vitest'
import { formatHm, formatKst, parseUtc, relativeKo } from '@/lib/time'

describe('time', () => {
  it('naive UTC 를 UTC 로 읽는다 (브라우저 로컬 시간대와 무관)', () => {
    expect(parseUtc('2026-09-25T15:30:00').toISOString()).toBe('2026-09-25T15:30:00.000Z')
    expect(parseUtc('2026-09-25T15:30:00.123456').toISOString()).toBe('2026-09-25T15:30:00.123Z')
    expect(parseUtc('2026-09-25T15:30:00Z').toISOString()).toBe('2026-09-25T15:30:00.000Z')
    expect(parseUtc('2026-09-25T15:30:00+00:00').toISOString()).toBe('2026-09-25T15:30:00.000Z')
  })

  it('KST 로 표시 — 자정 경계에서 날짜가 넘어간다', () => {
    const d = parseUtc('2026-09-25T15:30:00')
    expect(formatKst(d)).toBe('2026-09-26 00:30')
    expect(formatHm(d)).toBe('00:30')
  })

  it('상대 시각 — KST 달력 기준', () => {
    const now = parseUtc('2026-09-25T03:00:00') // KST 12:00
    expect(relativeKo(parseUtc('2026-09-25T02:59:30'), now)).toBe('방금')
    expect(relativeKo(parseUtc('2026-09-25T02:15:00'), now)).toBe('45분 전')
    expect(relativeKo(parseUtc('2026-09-24T16:00:00'), now)).toBe('11시간 전') // KST 같은 날 01:00
    expect(relativeKo(parseUtc('2026-09-24T14:00:00'), now)).toBe('어제') // KST 전날 23:00
    expect(relativeKo(parseUtc('2026-09-21T03:00:00'), now)).toBe('4일 전')
    expect(relativeKo(parseUtc('2026-09-01T03:00:00'), now)).toBe('9월 1일')
    expect(relativeKo(parseUtc('2026-09-25T03:05:00'), now)).toBe('방금') // 시계 어긋남(미래)
  })
})
