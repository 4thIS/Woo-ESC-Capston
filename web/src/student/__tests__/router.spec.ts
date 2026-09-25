import { describe, expect, it } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import { makeRouter } from '@/student/router'

describe('student router', () => {
  it('/ 는 세션 없이 /login 으로', async () => {
    const r = makeRouter(createMemoryHistory())
    await r.push('/')
    await r.isReady()
    expect(r.currentRoute.value.path).toBe('/login')
  })
})
