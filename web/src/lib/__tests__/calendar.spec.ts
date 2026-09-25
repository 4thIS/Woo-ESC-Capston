import { describe, expect, it } from 'vitest'
import { addDays, dayOfDate, hm, md, mondayOf } from '@/lib/time'

describe('달력 날짜 (서버 date 필드 — KST 달력 문자열, 시간대 없이 센다)', () => {
  it('addDays — 달·해·윤년 경계', () => {
    expect(addDays('2026-09-28', 7)).toBe('2026-10-05')
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01')
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28')
    expect(addDays('2028-02-28', 1)).toBe('2028-02-29')
  })
  it('dayOfDate — 1=월 … 7=일 (SlotIn.day 와 같다)', () => {
    expect(dayOfDate('2026-09-21')).toBe(1)
    expect(dayOfDate('2026-09-25')).toBe(5)
    expect(dayOfDate('2026-09-27')).toBe(7)
  })
  it('mondayOf — 일요일은 그 전 월요일, 주가 달을 넘어도', () => {
    expect(mondayOf('2026-09-27')).toBe('2026-09-21')
    expect(mondayOf('2026-10-01')).toBe('2026-09-28')
    expect(mondayOf('2026-09-21')).toBe('2026-09-21')
  })
  it('hm · md', () => {
    expect(hm(9, 5)).toBe('09:05')
    expect(hm(21, 30)).toBe('21:30')
    expect(md('2026-10-05')).toBe('10/5')
  })
})
