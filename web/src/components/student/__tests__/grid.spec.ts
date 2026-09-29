import { describe, expect, it } from 'vitest'
import type { BusySpan } from '@/api/types'
import { gridRange, gridRows, nowTop, visibleDays, weekBlocks } from '../grid'

const span = (from: string, to: string, over: Partial<BusySpan> = {}): BusySpan => ({
  from,
  to,
  label: '수업',
  type: 1,
  mine: false,
  status: null,
  ...over,
})
const BASE = { start: 540, end: 1080 }

describe('grid', () => {
  it('범위 — 기본 09–18, 벗어난 블록이 있으면 30분 단위로 편다, 빈강의실(4)은 무시', () => {
    expect(gridRange([])).toEqual(BASE)
    expect(
      gridRange([{ day: 1, spans: [span('08:10', '09:00'), span('17:00', '19:40')] }]),
    ).toEqual({ start: 480, end: 1200 })
    expect(gridRange([{ day: 1, spans: [span('06:00', '07:00', { type: 4 })] }])).toEqual(BASE)
    expect(gridRows(BASE)).toBe(18)
  })

  it('요일 — 월~금, 토·일은 그 요일에 그릴 블록이 있을 때만', () => {
    expect(visibleDays([{ day: 6, spans: [] }])).toEqual([1, 2, 3, 4, 5])
    expect(visibleDays([{ day: 7, spans: [span('10:00', '11:00')] }])).toEqual([1, 2, 3, 4, 5, 7])
    expect(visibleDays([{ day: 6, spans: [span('10:00', '11:00', { type: 4 })] }])).toEqual([
      1, 2, 3, 4, 5,
    ])
  })

  it('블록 — 30분 행 높이 기준 위치, 서버가 합친 라벨 그대로, 내 신청 표시, 빈강의실은 없음', () => {
    const b = weekBlocks(
      [
        {
          day: 5,
          spans: [
            span('10:00', '13:00', { label: '알고리즘 외 1건' }),
            span('15:00', '16:00', {
              label: '캡스톤 스터디',
              type: 6,
              mine: true,
              status: 'requested',
            }),
            span('17:00', '17:30', { type: 4 }),
          ],
        },
      ],
      BASE,
      24,
    )
    expect(b).toEqual([
      {
        day: 5,
        top: 48,
        height: 144,
        label: '알고리즘 외 1건',
        extra: '10:00–13:00',
        type: 1,
        mine: false,
        requested: false,
      },
      {
        day: 5,
        top: 288,
        height: 48,
        label: '캡스톤 스터디',
        extra: '15:00–16:00',
        type: 6,
        mine: true,
        requested: true,
      },
    ])
  })

  it('지금 선 — 범위 안에서만', () => {
    expect(nowTop(642, BASE, 32)).toBeCloseTo(108.8)
    expect(nowTop(500, BASE, 32)).toBeNull()
    expect(nowTop(1080, BASE, 32)).toBeNull()
  })
})
