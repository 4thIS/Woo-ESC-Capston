import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'

const items = [
  { value: 'student', label: '학생', href: '/login' },
  { value: 'admin', label: '관리자', href: '/admin/login' },
]

describe('SegmentedControl — href 면 링크 줄 (components.md)', () => {
  it('nav[aria-label] 안의 진짜 <a href> — 라우터 이동이 아니라 페이지를 새로 연다', () => {
    const w = mount(SegmentedControl, { props: { items, value: 'student', label: '로그인 역할' } })
    expect(w.get('nav').attributes('aria-label')).toBe('로그인 역할')
    const links = w.findAll('a')
    expect(links.map((a) => [a.text(), a.attributes('href')])).toEqual([
      ['학생', '/login'],
      ['관리자', '/admin/login'],
    ])
  })

  it('선택된 칸에만 aria-current="page" — 색(brand)이 아니라 면과 굵기로 (클래스)', () => {
    const w = mount(SegmentedControl, { props: { items, value: 'admin', label: '로그인 역할' } })
    const [student, admin] = w.findAll('a')
    expect(student.attributes('aria-current')).toBeUndefined()
    expect(admin.attributes('aria-current')).toBe('page')
    expect(admin.classes()).toContain('seg__item--on')
    expect(student.classes()).not.toContain('seg__item--on')
  })
})
