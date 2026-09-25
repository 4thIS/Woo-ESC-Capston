import { describe, expect, it } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import { makeRouter } from '@/admin/router'

describe('admin router', () => {
  it('/ 가 열린다', async () => {
    const r = makeRouter(createMemoryHistory())
    await r.push('/')
    await r.isReady()
    expect(r.currentRoute.value.matched.length).toBeGreaterThan(0)
  })
})
