import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import Table from '@/components/ui/Table.vue'

const columns = [
  { key: 'name', label: '이름', width: '96px' },
  { key: 'count', label: '건수', align: 'right' as const },
]
const rows = [
  { id: 'a', name: '김민준', count: 3 },
  { id: 'b', name: '이정민', count: 12 },
]

describe('Table', () => {
  it('헤더와 셀을 그린다, 숫자 열은 우측·tabular', () => {
    const w = mount(Table, { props: { columns, rows } })
    expect(w.findAll('th').map((t) => t.text())).toEqual(['이름', '건수'])
    expect(w.get('th').attributes('style')).toContain('width: 96px')
    const cells = w.findAll('tbody tr')[1].findAll('td')
    expect(cells.map((c) => c.text())).toEqual(['이정민', '12'])
    expect(cells[1].classes()).toEqual(expect.arrayContaining(['tbl__cell--right', 'num']))
  })

  it('cell 슬롯이 기본 표시를 대신한다', () => {
    const w = mount(Table, {
      props: { columns, rows },
      slots: { 'cell-name': '<template #cell-name="{ row }"><b>{{ row.name }}님</b></template>' },
    })
    expect(w.get('tbody b').text()).toBe('김민준님')
  })

  it('선택된 행', () => {
    const w = mount(Table, { props: { columns, rows, selected: ['b'] } })
    const trs = w.findAll('tbody tr')
    expect(trs[0].classes()).not.toContain('tbl__row--selected')
    expect(trs[1].classes()).toContain('tbl__row--selected')
  })

  it('loading 이면 헤더는 두고 Skeleton 행 5개', () => {
    const w = mount(Table, { props: { columns, rows, loading: true } })
    expect(w.findAll('th')).toHaveLength(2)
    expect(w.findAll('tbody tr')).toHaveLength(5)
    expect(w.text()).not.toContain('김민준')
  })

  it('행이 없으면 empty 문구, 슬롯이 있으면 슬롯', () => {
    expect(
      mount(Table, { props: { columns, rows: [], empty: '회원이 없습니다' } }).text(),
    ).toContain('회원이 없습니다')
    const w = mount(Table, {
      props: { columns, rows: [] },
      slots: { empty: '<p class="x">직접</p>' },
    })
    expect(w.find('.x').exists()).toBe(true)
  })

  it('expandable — 펼치면 expanded 슬롯', async () => {
    const w = mount(Table, {
      props: { columns, rows, expandable: true },
      slots: { expanded: '<template #expanded="{ row }"><i>{{ row.name }} 상세</i></template>' },
    })
    expect(w.find('i').exists()).toBe(false)
    const toggle = w.findAll('button.tbl__toggle')[0]
    expect(toggle.attributes('aria-expanded')).toBe('false')
    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(w.get('i').text()).toBe('김민준 상세')
  })

  it('tall — 두 줄 셀이 있는 표는 행 44px', () => {
    const w = mount(Table, { props: { columns, rows, tall: true } })
    expect(w.get('table').classes()).toContain('tbl--tall')
    const plain = mount(Table, { props: { columns, rows } })
    expect(plain.get('table').classes()).not.toContain('tbl--tall')
  })
})
