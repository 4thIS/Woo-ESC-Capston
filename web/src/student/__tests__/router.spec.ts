import { describe, expect, it } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import { makeRouter } from '@/student/router'

const at = async (path: string) => {
  const r = makeRouter(createMemoryHistory())
  await r.push(path)
  await r.isReady()
  return r.currentRoute.value
}

describe('student router', () => {
  it('/ 는 세션 없이도 그 자리 — 로그인 벽은 앱이 그린다(meta.gate)', async () => {
    const r = await at('/')
    expect(r.path).toBe('/')
    expect(r.meta.gate).toBe(true)
  })

  it('인증 화면은 벽 없이', async () => {
    expect((await at('/login')).meta.gate).toBeUndefined()
    expect((await at('/signup')).meta.gate).toBeUndefined()
  })

  it('모르는 주소는 404 화면 (벽 없이 — 보여줄 데이터가 없다)', async () => {
    const r = await at('/no/such/page')
    expect(r.matched[0].path).toBe('/:pathMatch(.*)*')
    expect(r.meta.gate).toBeUndefined()
  })

  it('소문자 건물 글자는 대문자로 — 폰에서 흔한 오타, 쿼리는 그대로', async () => {
    expect((await at('/e')).path).toBe('/E')
    expect((await at('/e/401?x=1')).fullPath).toBe('/E/401?x=1')
    expect((await at('/no')).path).toBe('/no')
  })

  it('자식 라우트도 대소문자를 가린다 — 전역 sensitive 라야 /e/401 이 자식에 먼저 걸리지 않고 /E/401 로 간다', async () => {
    const r = makeRouter(createMemoryHistory())
    const Page = { render: () => null }
    r.addRoute({
      path: '/:bld([A-Z])',
      component: Page,
      children: [{ path: ':room', component: Page, meta: { gate: true } }],
    })
    await r.push('/e/401?x=1#top')
    await r.isReady()
    expect(r.currentRoute.value.fullPath).toBe('/E/401?x=1#top')
    expect(r.currentRoute.value.params.room).toBe('401')
  })

  it('/:bld — 대문자 한 글자만, 소문자는 대문자로 보낸다(대소문자 구분 라우트)', async () => {
    const r = await at('/E')
    expect(r.matched[0].path).toBe('/:bld([A-Z])')
    expect(r.meta.gate).toBe(true)
    expect((await at('/e')).matched[0].path).toBe('/:bld([A-Z])')
    expect((await at('/e')).path).toBe('/E')
    expect((await at('/me')).matched[0].path).not.toBe('/:bld([A-Z])')
  })
})
