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
      slots: { footer: '<p class="f">우송대</p>' },
      global: { plugins: [router] },
    })
    const links = w.findAll('a')
    expect(links[1].attributes('aria-current')).toBe('page')
    expect(links[0].attributes('aria-current')).toBeUndefined()
    expect(links[1].text()).toContain('5')
    expect(links[0].find('.badge').exists()).toBe(false)
    expect(w.find('.f').exists()).toBe(true)
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
