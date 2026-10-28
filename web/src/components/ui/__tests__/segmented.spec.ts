import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'

const items = [
  { value: 'student', label: '학생' },
  { value: 'admin', label: '관리자' },
]

describe('SegmentedControl — 라디오 줄 (components.md)', () => {
  it('radiogroup[aria-label] 안의 네이티브 라디오 — 한 번의 Tab 멈춤, 화살표로 옮긴다', () => {
    const w = mount(SegmentedControl, { props: { items, value: 'student', label: '로그인 역할' } })
    expect(w.get('[role="radiogroup"]').attributes('aria-label')).toBe('로그인 역할')
    const radios = w.findAll('input[type="radio"]')
    expect(radios.map((r) => (r.element as HTMLInputElement).checked)).toEqual([true, false])
    expect(new Set(radios.map((r) => r.attributes('name'))).size).toBe(1)
    expect(w.findAll('label').map((l) => l.text())).toEqual(['학생', '관리자'])
    expect(w.find('a').exists()).toBe(false) // 주소를 바꾸지 않는다
  })

  it('고르면 update:value — 선택 칸은 색(brand)이 아니라 면과 굵기(클래스)', async () => {
    const w = mount(SegmentedControl, { props: { items, value: 'student', label: '로그인 역할' } })
    expect(w.findAll('label')[0].classes()).toContain('seg__item--on')
    await w.findAll('input')[1].setValue(true)
    expect(w.emitted('update:value')).toEqual([['admin']])
  })
})
