import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { routes } from '@/router'

describe('router', () => {
  it('/ 는 /admin 으로 리다이렉트', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes })
    await router.push('/')
    await router.isReady()
    expect(router.currentRoute.value.path).toBe('/admin')
  })

  it('/student 라우트가 있다', () => {
    expect(routes.some((r) => r.path === '/student')).toBe(true)
  })
})
