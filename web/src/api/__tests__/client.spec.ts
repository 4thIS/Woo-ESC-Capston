import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, MESSAGES, request } from '@/api/client'
import { USER_DATES, type UserOut } from '@/api/types'
import { authNotice, clearSession, onAuthFailure, session, setSession } from '@/lib/session'
import users from '@/api/__fixtures__/users.json'
import login from '@/api/__fixtures__/login.json'
import err422 from '@/api/__fixtures__/error-422.json'

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
const fetchMock = vi.fn<typeof fetch>()

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  clearSession()
  authNotice.value = null
})
afterEach(() => vi.useRealTimers())

describe('request', () => {
  it('표시한 필드만 Date 로 바꾼다', async () => {
    fetchMock.mockResolvedValue(json(200, users))
    const out = await request<UserOut[]>('GET', '/api/admin/users', undefined, {
      dates: USER_DATES,
    })
    expect(out[0].created_at).toBeInstanceOf(Date)
    expect(out[0].created_at.toISOString()).toBe('2026-09-25T01:00:00.123Z')
    expect(out[0].approved_at).toBeNull()
    expect(out[0].email).toBe('s1@wsu.ac.kr')
  })

  it('세션이 있으면 Bearer, auth:false 면 붙이지 않는다', async () => {
    setSession(login as never)
    fetchMock.mockResolvedValue(json(200, {}))
    await request('GET', '/a')
    await request('POST', '/b', { x: 1 }, { auth: false })
    const h = (i: number) => new Headers(fetchMock.mock.calls[i][1]!.headers)
    expect(h(0).get('authorization')).toBe('Bearer eyJ.test.sig')
    expect(h(1).get('authorization')).toBeNull()
    expect(h(1).get('content-type')).toBe('application/json')
    expect(fetchMock.mock.calls[1][1]!.body).toBe('{"x":1}')
  })

  it('토큰을 보낸 요청의 401 → 세션 폐기 + expired 알림', async () => {
    const onFail = vi.fn()
    onAuthFailure(onFail)
    setSession(login as never)
    fetchMock.mockResolvedValue(json(401, { detail: 'invalid token' }))
    const e = (await request('GET', '/a').catch((x) => x)) as ApiError
    expect(e).toBeInstanceOf(ApiError)
    expect(e.status).toBe(401)
    expect(e.message).toBe(MESSAGES[401])
    expect(session.value).toBeNull()
    expect(authNotice.value).toBe('expired')
    expect(onFail).toHaveBeenCalledWith('expired')
  })

  it('로그인 실패 401(auth:false)은 세션을 건드리지 않는다', async () => {
    const onFail = vi.fn()
    onAuthFailure(onFail)
    fetchMock.mockResolvedValue(json(401, { detail: '이메일 또는 비밀번호가 틀립니다' }))
    const e = (await request('POST', '/api/auth/login', {}, { auth: false }).catch(
      (x) => x,
    )) as ApiError
    expect(e.status).toBe(401)
    expect(onFail).not.toHaveBeenCalled()
    expect(authNotice.value).toBeNull()
  })

  it('403 → forbidden 알림', async () => {
    onAuthFailure(() => {})
    setSession(login as never)
    fetchMock.mockResolvedValue(json(403, { detail: 'admin only' }))
    await request('GET', '/a').catch(() => {})
    expect(authNotice.value).toBe('forbidden')
    expect(session.value).toBeNull()
  })

  it('422 → 필드 이름 목록', async () => {
    fetchMock.mockResolvedValue(json(422, err422))
    const e = (await request('POST', '/v', {}, { auth: false }).catch((x) => x)) as ApiError
    expect(e.fields).toEqual(['student_no'])
  })

  it('서버 원문을 message 로 내지 않는다', async () => {
    fetchMock.mockResolvedValue(json(409, { detail: 'constraint violation' }))
    const e = (await request('POST', '/x').catch((x) => x)) as ApiError
    expect(e.message).toBe(MESSAGES[409])
    expect(e.detail).toEqual({ detail: 'constraint violation' })
  })

  it('503 GET 은 1초 뒤 한 번 재시도', async () => {
    vi.useFakeTimers()
    fetchMock.mockResolvedValueOnce(json(503, {})).mockResolvedValueOnce(json(200, { ok: 1 }))
    const p = request<{ ok: number }>('GET', '/g')
    await vi.advanceTimersByTimeAsync(1000)
    await expect(p).resolves.toEqual({ ok: 1 })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('503 쓰기는 재시도하지 않는다', async () => {
    fetchMock.mockResolvedValue(json(503, {}))
    const e = (await request('POST', '/p').catch((x) => x)) as ApiError
    expect(e.status).toBe(503)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('네트워크 오류 → status 0', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const e = (await request('GET', '/n').catch((x) => x)) as ApiError
    expect(e).toBeInstanceOf(ApiError)
    expect(e.status).toBe(0)
  })

  it('abort 는 ApiError 로 바꾸지 않는다', async () => {
    fetchMock.mockRejectedValue(new DOMException('aborted', 'AbortError'))
    const e = (await request('GET', '/n').catch((x) => x)) as Error
    expect(e.name).toBe('AbortError')
  })

  it('204 는 undefined', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))
    await expect(request('DELETE', '/d')).resolves.toBeUndefined()
  })
})
