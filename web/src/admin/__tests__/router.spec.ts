import { describe, expect, it } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import { makeRouter } from '@/admin/router'

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
    expect(r.resolve('/rooms/x/week').matched).toHaveLength(0)
  })
})
