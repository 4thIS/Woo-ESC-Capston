import { beforeEach, describe, expect, it, vi } from 'vitest'
import { roomsApi } from '@/api/rooms'
import { adminApi } from '@/api/admin'
import { ApiError } from '@/api/client'
import { clearSession } from '@/lib/session'
import buildingResv from '@/api/__fixtures__/building-resv.json'
import pendingResv from '@/api/__fixtures__/pending-resv.json'
import importErrors from '@/api/__fixtures__/import-errors.json'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
const fetchMock = vi.fn<typeof fetch>()
const call = (i = 0) => ({ url: fetchMock.mock.calls[i][0], init: fetchMock.mock.calls[i][1]! })
const header = (i: number, k: string) => (call(i).init.headers as Record<string, string>)[k]

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  clearSession()
})

describe('roomsApi', () => {
  it('건물 추가는 BuildingIn 그대로, 수정은 보낸 필드만 (modem_id null = 배정 해제)', async () => {
    fetchMock.mockImplementation(async () =>
      json({ id: 3, school_id: 1, name: '공학관', bld: 'E', modem_id: null }),
    )
    await roomsApi.createBuilding({ school_id: 1, name: '공학관', bld: 'E', modem_id: null })
    await roomsApi.patchBuilding(3, { modem_id: null })
    expect(call(0).url).toBe('/api/buildings')
    expect(call(0).init.body).toBe('{"school_id":1,"name":"공학관","bld":"E","modem_id":null}')
    expect(call(1).url).toBe('/api/buildings/3')
    expect(call(1).init.method).toBe('PATCH')
    expect(call(1).init.body).toBe('{"modem_id":null}')
  })

  it('강의실 부분 수정 — reservable 만 보낸다 (다른 탭의 units 를 덮지 않게)', async () => {
    fetchMock.mockResolvedValue(
      json({ id: 11, building_id: 3, room: 401, units: 2, reservable: true }),
    )
    await roomsApi.patchRoom(11, { reservable: true })
    expect(call().url).toBe('/api/rooms/11')
    expect(call().init.body).toBe('{"reservable":true}')
  })

  it('건물 예약 — pushed_at 만 Date, date 는 달력 문자열 그대로, requester null 그대로', async () => {
    fetchMock.mockResolvedValue(json(buildingResv))
    const out = await roomsApi.buildingResv(3)
    expect(call().url).toBe('/api/buildings/3/reservations')
    expect(out[0].pushed_at!.toISOString()).toBe('2026-10-20T01:00:00.500Z')
    expect(out[0].date).toBe('2026-10-24')
    expect(out[0].requester?.name).toBe('김민준')
    expect(out[1].pushed_at).toBeNull()
    expect(out[1].requester).toBeNull()
  })

  it('건물 outbox — state·limit 쿼리', async () => {
    fetchMock.mockImplementation(async () => json([]))
    await roomsApi.buildingOutbox(3, 'queued')
    await roomsApi.buildingOutbox(3)
    expect(call(0).url).toBe('/api/buildings/3/outbox?state=queued&limit=500')
    expect(call(1).url).toBe('/api/buildings/3/outbox?limit=500')
  })

  it('슬롯 삭제는 키 경로, 예약 추가는 id 없이 (서버 채번) — 응답 id 를 돌려준다', async () => {
    fetchMock.mockImplementation(async () => json({ outbox_ids: [5], id: 12 }))
    await roomsApi.deleteSlot(11, { day: 1, s_h: 9, s_m: 0 })
    const out = await roomsApi.saveResv(11, {
      date: '2026-10-24',
      s_h: 10,
      s_m: 0,
      e_h: 12,
      e_m: 0,
      type: 5,
      subject: 'OT',
      professor: '학생처',
    })
    expect(call(0).url).toBe('/api/rooms/11/slots/1/9/0')
    expect(call(0).init.method).toBe('DELETE')
    expect(call(1).url).toBe('/api/rooms/11/reservations')
    expect(JSON.parse(call(1).init.body as string)).not.toHaveProperty('id')
    expect(out.id).toBe(12)
  })

  it('CSV — 본문을 바이트 그대로 text/csv, dry_run 쿼리', async () => {
    fetchMock.mockResolvedValue(
      json({ rooms: 1, added: 2, updated: 0, deleted: 0, skipped: [], outbox_ids: [] }),
    )
    const bytes = new TextEncoder().encode('school,building\n').buffer
    await roomsApi.importSlots(bytes, true)
    expect(call().url).toBe('/api/import/slots?dry_run=true')
    expect(call().init.method).toBe('POST')
    expect(header(0, 'content-type')).toBe('text/csv')
    expect(call().init.body).toBe(bytes)
  })

  it('CSV 검증 실패 400 — errors[] 는 ApiError.detail 로 온다 (화면이 표로 그린다)', async () => {
    fetchMock.mockResolvedValue(json(importErrors, 400))
    const e = (await roomsApi.importSlots(new ArrayBuffer(0), false).catch((x) => x)) as ApiError
    expect(e).toBeInstanceOf(ApiError)
    expect(e.status).toBe(400)
    expect((e.detail as typeof importErrors).errors[0]).toEqual({
      row: 2,
      error: 'room: 999 없음 (명지전문대학 K)',
    })
  })
})

describe('adminApi — 신청', () => {
  it('신청 대기 — status=requested, requested_at Date', async () => {
    fetchMock.mockResolvedValue(json(pendingResv))
    const out = await adminApi.pendingResv()
    expect(call().url).toBe('/api/admin/reservations?status=requested')
    expect(out[0].requested_at!.toISOString()).toBe('2026-10-23T05:00:00.000Z')
    expect(out[0].building).toBe('공학관')
    expect(out[0].room).toBe(401)
  })

  it('승인·거절·취소 — 경로와 본문', async () => {
    fetchMock.mockImplementation(async () => json(pendingResv[0]))
    await adminApi.approveResv(9)
    await adminApi.rejectResv(9, '겹치는 수업이 있습니다')
    await adminApi.cancelResv(9)
    expect(call(0).url).toBe('/api/admin/reservations/9/approve')
    expect(call(0).init.body).toBeUndefined()
    expect(call(1).url).toBe('/api/admin/reservations/9/reject')
    expect(call(1).init.body).toBe('{"reason":"겹치는 수업이 있습니다"}')
    expect(call(2).url).toBe('/api/admin/reservations/9/cancel')
  })
})
