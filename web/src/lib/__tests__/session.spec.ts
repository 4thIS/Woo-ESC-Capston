import { beforeEach, describe, expect, it } from 'vitest'
import type { LoginOut } from '@/api/types'

const jwt = (exp: number) => `h.${btoa(JSON.stringify({ exp }))}.s`
const future = () => Math.floor(Date.now() / 1000) + 3600
const admin = (token = jwt(future())): LoginOut => ({
  token,
  role: 'admin',
  school_id: 1,
  name: '관리',
})

// 모듈 상태를 매번 새로 — 새로고침 = 모듈을 다시 읽는 것
const fresh = async () => {
  const { vi } = await import('vitest')
  vi.resetModules()
  return import('@/lib/session')
}

describe('session — 새로고침에도 남는다', () => {
  beforeEach(() => sessionStorage.clear())

  it('로그인 → 새로고침하면 되살아난다, 로그아웃하면 지워진다', async () => {
    let m = await fresh()
    m.restoreSession('admin')
    m.setSession(admin())
    m = await fresh()
    m.restoreSession('admin')
    expect(m.session.value?.name).toBe('관리')
    m.clearSession()
    m = await fresh()
    m.restoreSession('admin')
    expect(m.session.value).toBeNull()
  })

  it('다른 앱의 세션·만료된 토큰·깨진 값은 되살리지 않는다', async () => {
    let m = await fresh()
    m.restoreSession('admin')
    m.setSession(admin())
    m = await fresh()
    m.restoreSession('student')
    expect(m.session.value).toBeNull()

    sessionStorage.setItem('esc.session.admin', JSON.stringify(admin(jwt(1))))
    m = await fresh()
    m.restoreSession('admin')
    expect(m.session.value).toBeNull()
    expect(sessionStorage.getItem('esc.session.admin')).toBeNull()
    expect(m.authNotice.value).toBe('expired') // 만료는 말없이 버리지 않는다

    sessionStorage.setItem('esc.session.admin', '{broken')
    m = await fresh()
    m.restoreSession('admin')
    expect(m.session.value).toBeNull()
  })
})
