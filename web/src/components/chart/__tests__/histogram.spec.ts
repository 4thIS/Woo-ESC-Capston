import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import Histogram, { niceStep } from '@/components/chart/Histogram.vue'

const B = (label: string, ...values: number[]) => ({ label, values })

describe('niceStep', () => {
  it('최댓값을 세 칸에 담는 1·2·5 간격, 건수라 1 미만은 없다', () => {
    expect([0, 1, 2, 7, 30, 95].map(niceStep)).toEqual([1, 1, 1, 5, 10, 50])
  })
})

describe('Histogram', () => {
  it('두 계열 — 막대 폭 15·간격 2, bucket 가운데 정렬, 계열 색은 고정 순서 클래스', () => {
    const w = mount(Histogram, {
      props: { buckets: [B('0–10', 3, 1)], series: [{ label: 'A' }, { label: 'B' }] },
    })
    const paths = w.findAll('path')
    expect(paths.map((p) => p.attributes('d')!.split(',')[0])).toEqual(['M52', 'M69'])
    expect(paths.map((p) => p.classes().find((c) => c.startsWith('hist__bar--')))).toEqual([
      'hist__bar--1',
      'hist__bar--2',
    ])
  })

  it('0 인 값은 막대를 그리지 않고, 값 라벨은 계열마다 가장 큰 막대(첫 것) 하나에만', () => {
    const w = mount(Histogram, {
      props: {
        buckets: [B('a', 1, 0), B('b', 3, 2), B('c', 3, 5)],
        series: [{ label: 'A' }, { label: 'B' }],
      },
    })
    expect(w.findAll('path')).toHaveLength(5)
    expect(w.findAll('.hist__value').map((t) => t.text())).toEqual(['3', '5'])
  })

  it('한 계열 — 막대 하나가 bucket 가운데', () => {
    const w = mount(Histogram, { props: { buckets: [B('a', 2)], series: [{ label: 'A' }] } })
    expect(w.get('path').attributes('d')!.startsWith('M60.5,')).toBe(true)
  })

  it('marker — bucket 경계에 세로 점선 + 라벨, 격자선은 두 줄', () => {
    const w = mount(Histogram, {
      props: {
        buckets: [B('0–10', 1), B('10–20', 30), B('20–30', 2), B('30–45', 1)],
        series: [{ label: 'A' }],
        marker: { at: 3, label: 'SLA 30초' },
      },
    })
    expect(w.get('.hist__marker line').attributes('x1')).toBe('248')
    expect(w.get('.hist__marker text').text()).toBe('SLA 30초')
    expect(w.findAll('.hist__grid line')).toHaveLength(2)
    expect(w.findAll('.hist__ticks text').map((t) => t.text())).toEqual(['10', '20'])
    expect(w.findAll('.hist__label').map((t) => t.text())).toEqual([
      '0–10',
      '10–20',
      '20–30',
      '30–45',
    ])
  })

  it('데이터가 전부 0 이어도 깨지지 않는다 — 막대·값 라벨 없음', () => {
    const w = mount(Histogram, {
      props: { buckets: [B('a', 0), B('b', 0)], series: [{ label: 'A' }] },
    })
    expect(w.findAll('path')).toHaveLength(0)
    expect(w.findAll('.hist__value')).toHaveLength(0)
    expect(w.get('svg').attributes('width')).toBe('184')
  })
})
