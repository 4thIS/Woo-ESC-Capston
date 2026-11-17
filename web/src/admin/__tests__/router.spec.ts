import { describe, expect, it } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import { makeRouter, prefetchViews, routes, views } from '@/admin/router'

describe('admin router', () => {
  it('/ 는 세션 없이 /login 으로', async () => {
    const r = makeRouter(createMemoryHistory())
    await r.push('/')
    await r.isReady()
    expect(r.currentRoute.value.path).toBe('/login')
  })

  it('주간 시간표 — /week 와 /rooms/:roomId(숫자)/week 가 잡힌다 (페이지1 호수 링크)', () => {
    const r = makeRouter(createMemoryHistory())
    const at = r.resolve('/rooms/12/week')
    expect(at.matched).toHaveLength(2)
    expect(at.params.roomId).toBe('12')
    expect(r.resolve('/week').matched).toHaveLength(2)
    expect(r.resolve('/rooms/x/week').params.roomId).toBeUndefined()
  })

  it('셸 안의 화면은 모두 미리 받기 목록에 있다 — 새 메뉴를 더하고 빠뜨리면 첫 클릭이 다시 느려진다', () => {
    const lazy = routes[0].children!.map((c) => c.component).filter((c) => typeof c === 'function')
    expect(lazy.length).toBeGreaterThanOrEqual(7)
    const listed = new Set<unknown>(Object.values(views))
    for (const load of lazy) expect(listed.has(load)).toBe(true)
  })

  it('prefetchViews — 화면 청크를 모두 받는다, 하나가 실패해도 나머지는 받고 던지지 않는다', async () => {
    await expect(prefetchViews()).resolves.toBeUndefined()
  })

  it('없는 주소도 로그인 먼저 — 세션 없이 /login 으로 (#70)', async () => {
    const r = makeRouter(createMemoryHistory())
    await r.push('/nope')
    await r.isReady()
    expect(r.currentRoute.value.path).toBe('/login')
  })
})
