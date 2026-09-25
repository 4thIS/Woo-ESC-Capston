import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { ResvStatus } from '@/api/types'
import FavoriteStar from '../FavoriteStar.vue'
import ResvStatusBadge from '../ResvStatusBadge.vue'
import RoomListRow from '../RoomListRow.vue'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/:rest(.*)*', component: { render: () => null } }],
})

describe('ResvStatusBadge — 색이 아니라 라벨이 진다, 적색은 승인(방이 쓰인다)만', () => {
  it.each<[ResvStatus, string, string, string]>([
    ['requested', '대기중', 'badge--neutral', 'badge--outline'],
    ['approved', '승인됨', 'badge--busy', 'badge--tint'],
    ['rejected', '거절됨', 'badge--neutral', 'badge--outline'],
    ['cancelled', '취소됨', 'badge--neutral', 'badge--outline'],
    ['expired', '만료됨', 'badge--neutral', 'badge--outline'],
  ])('%s → %s', (status, label, tone, variant) => {
    const b = mount(ResvStatusBadge, { props: { status } }).get('.badge')
    expect(b.text()).toBe(label)
    expect(b.classes()).toEqual(expect.arrayContaining([tone, variant]))
  })
})

describe('FavoriteStar', () => {
  it('모양과 이름이 함께 바뀐다, 누르면 toggle', async () => {
    const w = mount(FavoriteStar, { props: { on: false } })
    const b = w.get('button')
    expect(b.text()).toBe('☆')
    expect(b.attributes('aria-label')).toBe('즐겨찾기 추가')
    await b.trigger('click')
    expect(w.emitted('toggle')).toHaveLength(1)
    await w.setProps({ on: true })
    expect(b.text()).toBe('★')
    expect(b.attributes('aria-label')).toBe('즐겨찾기 해제')
    expect(b.classes()).toContain('star--on')
  })
})

describe('RoomListRow', () => {
  const props = {
    to: '/E/401',
    room: 401,
    state: 'busy' as const,
    label: '수업중',
    until: '10:50 까지',
    fav: false,
  }

  it('왼쪽 대부분이 링크 — 호수·상태·언제, ★ 은 링크 밖 버튼', () => {
    const w = mount(RoomListRow, { props, global: { plugins: [router] } })
    const a = w.get('a.row__link')
    expect(a.attributes('href')).toBe('/E/401')
    // 칸이 붙어 읽히지 않게 링크 이름을 한 문장으로 ("401호수업중" 방지)
    expect(a.attributes('aria-label')).toBe('401호 수업중 10:50 까지')
    expect(a.get('.row__room').text()).toBe('401호')
    expect(a.get('.row__state .badge').text()).toBe('수업중')
    expect(a.get('.row__state .badge').classes()).toContain('badge--busy')
    expect(a.get('.row__until').text()).toBe('10:50 까지')
    expect(a.find('button').exists()).toBe(false)
    expect(w.get('li > button').attributes('aria-label')).toBe('즐겨찾기 추가')
  })

  it('비어 있으면 칠하지 않는다 — 라벨만, ★ 을 누르면 toggleFav', async () => {
    const w = mount(RoomListRow, {
      props: { ...props, state: 'free', label: '비어있음', until: '13:00 까지', fav: true },
      global: { plugins: [router] },
    })
    expect(w.find('.row__state .badge').exists()).toBe(false)
    expect(w.get('.row__free').text()).toBe('비어있음')
    await w.get('li > button').trigger('click')
    expect(w.emitted('toggleFav')).toHaveLength(1)
  })
})
