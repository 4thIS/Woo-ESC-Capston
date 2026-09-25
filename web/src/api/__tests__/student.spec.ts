import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { studentApi } from '@/api/student'
import { clearSession } from '@/lib/session'
import week from '@/api/__fixtures__/week.json'
import mine from '@/api/__fixtures__/mine.json'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
const fetchMock = vi.fn<typeof fetch>()
const call = (i = 0) => ({ url: fetchMock.mock.calls[i][0], init: fetchMock.mock.calls[i][1]! })

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  clearSession()
})

describe('studentApi', () => {
  it('rooms — 학교의 예약 가능한 방 전부, until 은 문자열 그대로(null = 자정까지)', async () => {
    fetchMock.mockResolvedValue(
      json([
        {
          room_id: 11,
          building_id: 3,
          building: '공학관',
          bld: 'E',
          room: 401,
          layout: 4,
          until: null,
        },
      ]),
    )
    const out = await studentApi.rooms()
    expect(call().url).toBe('/api/student/rooms')
    expect(out[0].until).toBeNull()
    expect(out[0].layout).toBe(4)
  })

  it('week — busy·free·full 은 서버 계산 그대로, 날짜는 KST 달력 문자열', async () => {
    fetchMock.mockResolvedValue(json(week))
    const out = await studentApi.week(11)
    expect(call().url).toBe('/api/student/rooms/11/week')
    expect(out.week_start).toBe('2026-10-19')
    expect(out.busy[4]).toEqual({
      day: 5,
      spans: [
        {
          from: '10:00',
          to: '13:00',
          label: '알고리즘 외 1건',
          type: 1,
          mine: false,
          status: null,
        },
        {
          from: '15:00',
          to: '16:00',
          label: '캡스톤 스터디',
          type: 6,
          mine: true,
          status: 'requested',
        },
      ],
    })
    expect(out.free).toHaveLength(8)
    expect(out.free[0]).toEqual({
      date: '2026-10-23',
      spans: [
        { from: '13:00', to: '15:00' },
        { from: '16:00', to: '21:00' },
      ],
    })
    expect(out.full).toBe(false)
  })

  it('mine — 다섯 상태 전부를 묻고, *_at 만 Date', async () => {
    fetchMock.mockResolvedValue(json(mine))
    const out = await studentApi.mine()
    expect(call().url).toBe(
      '/api/student/me/reservations?status=requested,approved,rejected,cancelled,expired',
    )
    expect(out[0].decided_at!.toISOString()).toBe('2026-10-22T02:30:00.000Z')
    expect(out[0].checked_in_at).toBeNull()
    expect(out[0].date).toBe('2026-10-24')
    expect(out[1].reject_reason).toBe('학과 행사와 겹칩니다')
  })

  it('requestResv — 본문 그대로 POST (id·type·professor 는 보내지 않는다 — 서버가 정한다)', async () => {
    fetchMock.mockResolvedValue(json({ ...mine[0], status: 'requested' }, 201))
    const body = { date: '2026-10-24', s_h: 10, s_m: 0, e_h: 12, e_m: 0, subject: '캡스톤 스터디' }
    const out = await studentApi.requestResv(11, body)
    expect(call().url).toBe('/api/student/rooms/11/reservations')
    expect(call().init.method).toBe('POST')
    expect(JSON.parse(call().init.body as string)).toEqual(body)
    expect(out.status).toBe('requested')
    expect(out.requested_at).toBeInstanceOf(Date)
  })

  it('cancel · checkin — 경로', async () => {
    fetchMock.mockImplementation(async () => json(mine[0]))
    await studentApi.cancel(7)
    await studentApi.checkin(7)
    expect(call(0).url).toBe('/api/student/me/reservations/7/cancel')
    expect(call(1).url).toBe('/api/student/me/reservations/7/checkin')
    expect(call(1).init.method).toBe('POST')
  })

  it('409 — ApiError, 원문은 detail 에만 (화면이 문장을 고른다)', async () => {
    fetchMock.mockResolvedValue(json({ detail: '그 시간에는 이미 수업·예약이 있습니다' }, 409))
    const err = await studentApi
      .requestResv(11, {
        date: '2026-10-24',
        s_h: 10,
        s_m: 0,
        e_h: 11,
        e_m: 0,
        subject: 'x',
      })
      .catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(409)
    expect((err as ApiError).message).not.toContain('수업·예약')
  })
})
