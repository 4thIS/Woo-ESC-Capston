import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { assistantApi, classify } from '@/api/assistant'
import { clearSession, setSession } from '@/lib/session'
import turnPreview from '@/api/__fixtures__/assistant-turn-preview.json'
import changes from '@/api/__fixtures__/assistant-changes.json'

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
const fetchMock = vi.fn<typeof fetch>()

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  clearSession()
  setSession({ token: 't', role: 'admin', school_id: 1, name: '관리자1' })
})

describe('assistantApi', () => {
  it('model — 안내를 그대로 (enabled:false 도)', async () => {
    fetchMock.mockResolvedValue(json(200, { enabled: false }))
    expect(await assistantApi.model()).toEqual({ enabled: false })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/assistant/model')
  })

  it('turn — 본문을 그대로 보내고, 미리보기 안쪽 날짜까지 Date 로', async () => {
    fetchMock.mockResolvedValue(json(200, turnPreview))
    const t = await assistantApi.turn({
      conversation_id: null,
      utterance: '803호 …',
      form: { v: 1, intent: 'event.add', target: {}, set: {} },
      choice: null,
    })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/assistant/turns')
    expect(init!.method).toBe('POST')
    expect(JSON.parse(String(init!.body))).toMatchObject({ conversation_id: null, choice: null })
    expect(t.preview!.expires_at).toBeInstanceOf(Date)
    const before = t.preview!.rooms[0].weeks[0].before.reservations[0]
    expect(before.pushed_at).toBeInstanceOf(Date)
    expect(t.preview!.rooms[0].weeks[0].after.reservations[1].pushed_at).toBeNull()
  })

  it('apply — preview_id 를 경로에, changes — applied_at 을 Date 로', async () => {
    fetchMock.mockResolvedValueOnce(json(200, { change_id: 41, outbox_ids: [512] }))
    expect(await assistantApi.apply('p_1')).toEqual({ change_id: 41, outbox_ids: [512] })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/assistant/previews/p_1/apply')
    fetchMock.mockResolvedValueOnce(json(200, changes))
    const c = await assistantApi.changes()
    expect(fetchMock.mock.calls[1][0]).toBe('/api/assistant/changes?limit=50')
    expect(c[0].applied_at).toBeInstanceOf(Date)
  })
})

describe('classify — 부록 §4 오류 본문', () => {
  const err = async (status: number, body: unknown) => {
    fetchMock.mockResolvedValueOnce(json(status, body))
    return (await assistantApi.apply('p_1').catch((e) => e)) as ApiError
  }
  it('409 schema_version · 409 stale(+새 미리보기) · 410 · 422 blocked · 429 · 그 밖은 null', async () => {
    expect(classify(await err(409, { detail: 'schema_version' }))).toEqual({
      kind: 'schema_version',
    })
    const stale = classify(await err(409, { detail: 'stale', preview: turnPreview.preview }))
    expect(stale?.kind).toBe('stale')
    expect(stale?.kind === 'stale' && stale.preview.expires_at).toBeInstanceOf(Date)
    expect(classify(await err(410, { detail: 'expired' }))).toEqual({ kind: 'expired' })
    expect(classify(await err(404, { detail: '미리보기 없음' }))).toEqual({ kind: 'expired' })
    expect(classify(await err(422, { detail: 'blocked', blockers: ['지난 날짜'] }))).toEqual({
      kind: 'blocked',
      blockers: ['지난 날짜'],
    })
    expect(classify(await err(429, { detail: 'slow down' }))).toEqual({ kind: 'rate' })
    expect(classify(await err(500, { detail: 'boom' }))).toBeNull()
    expect(classify(await err(409, { detail: '다른 사람이 먼저' }))).toBeNull()
  })
})
