import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import { authNotice, clearSession, session, setSession } from '@/lib/session'
import { IDLE_MS, WARN_MS, expireIfIdle, mmss, useIdleLogout } from '../idle'

const start = () => {
  const scope = effectScope()
  const idle = scope.run(useIdleLogout)!
  return { idle, stop: () => scope.stop() }
}
const click = () => window.dispatchEvent(new Event('pointerdown'))

describe('관리자 10분 자동 로그아웃', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    sessionStorage.clear()
    setSession({ token: 'tok-a', role: 'admin', school_id: 1, name: '관리' })
  })
  afterEach(() => {
    clearSession()
    authNotice.value = null
    vi.useRealTimers()
  })

  it('활동이 없으면 10분 뒤 로그아웃, 마지막 1분은 경고', () => {
    const { idle, stop } = start()
    vi.advanceTimersByTime(IDLE_MS - WARN_MS - 1000)
    expect(idle.warning.value).toBe(false)
    vi.advanceTimersByTime(2000)
    expect(idle.warning.value).toBe(true)
    expect(session.value).not.toBeNull()
    vi.advanceTimersByTime(WARN_MS)
    expect(session.value).toBeNull()
    expect(authNotice.value).toBe('idle')
    stop()
  })

  it('활동은 연장하지만 경고 중에는 버튼만 연장한다', () => {
    const { idle, stop } = start()
    vi.advanceTimersByTime(5 * 60_000)
    click()
    vi.advanceTimersByTime(8 * 60_000) // 처음부터 13분 — 클릭 뒤로는 8분
    expect(session.value).not.toBeNull()
    vi.advanceTimersByTime(90_000) // 경고 중
    click()
    expect(idle.warning.value).toBe(true)
    idle.extend()
    expect(idle.warning.value).toBe(false)
    expect(idle.remaining.value).toBe(IDLE_MS)
    stop()
  })

  it('새로고침해도 이어서 센다, 새 로그인은 새로 센다', () => {
    let s = start()
    vi.advanceTimersByTime(4 * 60_000)
    s.stop()
    s = start() // 새로고침
    expect(s.idle.remaining.value).toBe(6 * 60_000)
    s.stop()
    setSession({ token: 'tok-b', role: 'admin', school_id: 1, name: '관리' })
    s = start()
    expect(s.idle.remaining.value).toBe(IDLE_MS)
    s.stop()
  })

  it('마감이 지난 탭을 새로고침하면 그리기 전에 로그아웃', () => {
    start().stop()
    vi.advanceTimersByTime(IDLE_MS - 1000)
    expireIfIdle()
    expect(session.value).not.toBeNull()
    vi.advanceTimersByTime(1000)
    expireIfIdle()
    expect(session.value).toBeNull()
    expect(authNotice.value).toBe('idle')
  })

  it('숨긴 탭에서 마감이 지난 뒤 첫 움직임은 연장이 아니라 로그아웃', () => {
    const { stop } = start()
    vi.setSystemTime(Date.now() + IDLE_MS + 5000) // 타이머는 안 돌고 시계만 — 멈춘 탭
    click()
    expect(session.value).toBeNull()
    stop()
  })

  it('mm:ss', () => {
    expect(mmss(IDLE_MS)).toBe('10:00')
    expect(mmss(59_001)).toBe('01:00')
    expect(mmss(0)).toBe('00:00')
  })
})
