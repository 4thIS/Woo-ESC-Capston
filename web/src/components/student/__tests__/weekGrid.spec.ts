import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { GridBlock } from '../grid'
import WeekGrid from '../WeekGrid.vue'

const range = { start: 540, end: 1080 }
const blocks: GridBlock[] = [
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
    day: 2,
    top: 0,
    height: 48,
    label: '운영체제',
    extra: '09:00–10:00',
    type: 3,
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
]
const props = {
  days: [1, 2, 3, 4, 5],
  blocks,
  rowHeight: 24 as const,
  range,
  todayIndex: 4,
  nowTop: 81.6,
}

describe('WeekGrid — 요일 가로 × 시간 세로, 겹침은 서버가 합친 것을 받는다', () => {
  it('요일 머리·오늘 열, 시각 라벨은 정시마다, 지금 선은 오늘 열에만', () => {
    const w = mount(WeekGrid, { props })
    const heads = w.findAll('.wg__day')
    expect(heads.map((d) => d.text())).toEqual(['월', '화', '수', '목', '금'])
    expect(heads[4].classes()).toContain('wg__day--today')
    expect(w.findAll('.wg__col')[4].classes()).toContain('wg__col--today')
    expect(w.findAll('.wg__time').map((t) => t.text())).toEqual([
      '09:00',
      '10:00',
      '11:00',
      '12:00',
      '13:00',
      '14:00',
      '15:00',
      '16:00',
      '17:00',
    ])
    expect(w.findAll('.wg__now')).toHaveLength(1)
    expect(w.findAll('.wg__col')[4].get('.wg__now').attributes('style')).toContain('top: 81.6px')
    expect(w.findAll('.wg__col')[0].attributes('style')).toContain('height: 432px')
  })

  it('블록 — 위치·높이, 읽는 이름, 사용중·휴강·내 신청 모양', () => {
    const w = mount(WeekGrid, { props })
    const algo = w.get('[aria-label="금 10:00–13:00 수업중 알고리즘 외 1건"]')
    expect(algo.attributes('role')).toBe('listitem')
    expect(algo.attributes('style')).toContain('top: 48px')
    expect(algo.attributes('style')).toContain('height: 144px')
    expect(algo.classes()).toContain('wg__blk--busy')
    const off = w.get('[aria-label="화 09:00–10:00 휴강 운영체제"]')
    expect(off.classes()).toContain('wg__blk--off')
    // 취소선은 안쪽 라벨에 — line-clamp 상자는 원자 요소라 바깥 text-decoration 이 전해지지 않는다
    expect(off.get('.wg__label').classes()).toContain('wg__label--off')
    // 선은 인라인 글자 상자(.wg__text)의 배경으로 그린다 — 줄마다 그어진다
    expect(off.get('.wg__label--off > .wg__text').text()).toBe('운영체제')
    const mine = w.get('[aria-label="금 15:00–16:00 대여중 캡스톤 스터디 대기중"]')
    expect(mine.classes()).toEqual(expect.arrayContaining(['wg__blk--mine', 'wg__blk--requested']))
    expect(w.findAll('.wg__col')[4].attributes('aria-label')).toBe('금요일')
  })

  it('좁은 폭(24)은 과목명만, 넓은 폭(32)은 유형 + 과목명 + 시각', async () => {
    const w = mount(WeekGrid, { props })
    const algo = () => w.get('[aria-label="금 10:00–13:00 수업중 알고리즘 외 1건"]')
    expect(algo().text()).toBe('알고리즘 외 1건')
    await w.setProps({ rowHeight: 32 })
    expect(w.classes()).toContain('wg--wide')
    expect(algo().get('.wg__type').text()).toBe('수업중')
    expect(algo().get('.wg__extra').text()).toBe('10:00–13:00')
  })

  it('오늘이 이 주에 없으면(todayIndex -1) 오늘 표시·지금 선이 없다', () => {
    const w = mount(WeekGrid, { props: { ...props, todayIndex: -1 } })
    expect(w.find('.wg__day--today').exists()).toBe(false)
    expect(w.find('.wg__now').exists()).toBe(false)
  })

  it('오늘이 주말 열이면 올릴 때 격자를 끝까지 가로 스크롤해 오늘이 보이게', () => {
    const set = vi.spyOn(Element.prototype, 'scrollLeft', 'set')
    mount(WeekGrid, { props: { ...props, days: [1, 2, 3, 4, 5, 6], todayIndex: 5 } })
    expect(set).toHaveBeenCalledTimes(1)
    set.mockClear()
    mount(WeekGrid, { props })
    expect(set).not.toHaveBeenCalled()
    set.mockRestore()
  })
})
