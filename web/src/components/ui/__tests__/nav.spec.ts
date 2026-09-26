import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import SidebarNav from '@/components/ui/SidebarNav.vue'
import StatTile from '@/components/ui/StatTile.vue'
import Legend from '@/components/ui/Legend.vue'

const Empty = { template: '<div />' }
async function withRouter(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/users', component: Empty },
      { path: '/nodes', component: Empty },
    ],
  })
  await router.push(path)
  await router.isReady()
  return router
}

describe('SidebarNav', () => {
  it('현재 경로 항목이 활성, badge 는 0 이면 숨김', async () => {
    const router = await withRouter('/users')
    const w = mount(SidebarNav, {
      props: {
        items: [
          { to: '/nodes', label: '노드 상태', badge: 0 },
          { to: '/users', label: '회원', badge: 5 },
        ],
      },
      slots: { footer: '<p class="f">명지전문대학</p>' },
      global: { plugins: [router] },
    })
    const links = w.findAll('a')
    expect(links[1].attributes('aria-current')).toBe('page')
    expect(links[0].attributes('aria-current')).toBeUndefined()
    expect(links[1].text()).toContain('5')
    expect(links[0].find('.badge').exists()).toBe(false)
    expect(w.find('.f').exists()).toBe(true)
  })

  it('시안 A — 묶음 제목은 바뀔 때 한 번, 아이콘, 머리 슬롯, 대기 숫자 배지', async () => {
    const router = await withRouter('/nodes')
    const w = mount(SidebarNav, {
      props: {
        items: [
          { to: '/users', label: '회원', group: '사람', icon: 'users', badge: 2 },
          { to: '/nodes', label: '노드 상태', group: '모니터링', icon: 'node' },
        ],
      },
      slots: { header: '<p class="h">MJC ESC</p>' },
      global: { plugins: [router] },
    })
    expect(w.findAll('.nav__group').map((g) => g.text())).toEqual(['사람', '모니터링'])
    expect(w.findAll('a svg.nav__icon')).toHaveLength(2)
    expect(w.find('.h').exists()).toBe(true)
    expect(w.get('.nav__count').text()).toBe('2')
    expect(w.get('.nav__count').attributes('aria-label')).toBe('대기 2건')
  })

  it('선택 표시(pill)는 하나 — 움직임은 CSS 로, 움직임 줄이기면 끈다', async () => {
    const router = await withRouter('/users')
    const w = mount(SidebarNav, {
      props: { items: [{ to: '/users', label: '회원' }] },
      global: { plugins: [router] },
    })
    expect(w.findAll('.nav__pill')).toHaveLength(1)
    expect(w.get('.nav__pill').attributes('aria-hidden')).toBe('true')
  })
})

describe('StatTile', () => {
  it('danger 는 값 글자만', () => {
    const w = mount(StatTile, {
      props: { label: '수신률', value: 91.2, unit: '%', sub: '목표 95% · 미달', tone: 'danger' },
    })
    expect(w.text()).toContain('91.2')
    expect(w.get('.stat__value').classes()).toContain('stat__value--danger')
    expect(w.classes()).not.toContain('stat--danger')
  })
})

describe('Legend', () => {
  it('2개 이상일 때만 그린다', () => {
    const one = mount(Legend, {
      props: { series: [{ label: 'A', color: 'var(--chart-series-1)' }] },
    })
    expect(one.find('.legend').exists()).toBe(false)
    const two = mount(Legend, {
      props: {
        series: [
          { label: '이번 주', color: 'var(--chart-series-1)' },
          { label: '지난주', color: 'var(--chart-series-2)' },
        ],
      },
    })
    expect(two.findAll('.legend__item').map((x) => x.text())).toEqual(['이번 주', '지난주'])
    expect(two.get('.legend__mark').attributes('style')).toContain('var(--chart-series-1)')
  })
})
