import { describe, expect, it, vi } from 'vitest'
import { parseForm, userMessage } from '@/admin/assistant/prompt'
import {
  WorkerRunner,
  type FromWorker,
  type GenerateReq,
  type ModelRunner,
  type ToWorker,
  type WorkerLike,
} from '@/admin/assistant/runner'
import { createHandler } from '@/admin/assistant/workerCore'
import {
  STUB_MANIFEST,
  StubRunner,
  manualOutput,
  readStubScript,
} from '@/admin/assistant/adapters/stub'

const REQ: GenerateReq = {
  system: 'S',
  user: '관리자: 801 배터리?',
  schema: {},
  generation: { temperature: 0, max_tokens: 256 },
}

class FakeWorker implements WorkerLike {
  sent: ToWorker[] = []
  onmessage: ((e: MessageEvent<FromWorker>) => void) | null = null
  onerror: ((e: ErrorEvent) => void) | null = null
  terminate = vi.fn()
  postMessage(m: ToWorker) {
    this.sent.push(m)
  }
  emit(m: FromWorker) {
    this.onmessage?.({ data: m } as MessageEvent<FromWorker>)
  }
}

describe('prompt', () => {
  it('userMessage — 접두어 + 다듬은 문장', () => {
    expect(userMessage('관리자: ', '  803 금 특강 ')).toBe('관리자: 803 금 특강')
  })
  it('parseForm — 객체·코드펜스는 통과, 깨진 JSON·모양 위반은 null', () => {
    const ok = '{"v":1,"intent":"fill","target":{},"set":{"subject":"알고리즘 특강"}}'
    expect(parseForm(ok)).toMatchObject({ intent: 'fill' })
    expect(parseForm('```json\n' + ok + '\n```')).toMatchObject({ v: 1 })
    expect(parseForm('{"v":1,"intent":"fill"')).toBeNull()
    expect(parseForm('{"v":"1","intent":"fill","target":{},"set":{}}')).toBeNull()
    expect(parseForm('{"v":1,"intent":"fill","target":[],"set":{}}')).toBeNull()
    expect(parseForm('[1]')).toBeNull()
  })
})

describe('WorkerRunner', () => {
  it('load → progress 콜백 → ready 로 끝난다, generate 는 id 로 짝짓는다', async () => {
    const fw = new FakeWorker()
    const r = new WorkerRunner(() => fw)
    const onProgress = vi.fn()
    const loading = r.load(STUB_MANIFEST, onProgress)
    expect(fw.sent[0]).toEqual({ type: 'load', manifest: STUB_MANIFEST })
    fw.emit({ type: 'progress', progress: { loaded: 1, total: 2, text: 'x' } })
    fw.emit({ type: 'ready' })
    await loading
    expect(onProgress).toHaveBeenCalledWith({ loaded: 1, total: 2, text: 'x' })
    const a = r.generate(REQ)
    const b = r.generate(REQ)
    const [ga, gb] = fw.sent.slice(1) as Extract<ToWorker, { type: 'generate' }>[]
    fw.emit({ type: 'result', id: gb.id, text: 'B' })
    fw.emit({ type: 'result', id: ga.id, text: 'A' })
    expect(await a).toBe('A')
    expect(await b).toBe('B')
  })

  it('load 오류(id null)는 load 를, generate 오류는 그 요청을 실패시킨다, dispose 는 남은 요청을 끝낸다', async () => {
    const fw = new FakeWorker()
    const r = new WorkerRunner(() => fw)
    const loading = r.load(STUB_MANIFEST, () => {})
    fw.emit({ type: 'error', id: null, message: 'no gpu' })
    await expect(loading).rejects.toThrow('no gpu')
    const g = r.generate(REQ)
    const id = (fw.sent[1] as Extract<ToWorker, { type: 'generate' }>).id
    fw.emit({ type: 'error', id, message: 'oom' })
    await expect(g).rejects.toThrow('oom')
    const pending = r.generate(REQ)
    await r.dispose()
    await expect(pending).rejects.toThrow('모델을 내렸습니다')
    expect(fw.terminate).toHaveBeenCalled()
    await expect(r.generate(REQ)).rejects.toThrow('모델을 먼저 불러오세요')
  })
})

describe('createHandler (Worker 안)', () => {
  it('load → progress·ready, generate → result, 불러오기 전 generate → 그 id 로 error', async () => {
    const posted: FromWorker[] = []
    const engine: ModelRunner = {
      load: async (_m, onProgress) => onProgress({ loaded: 5, total: 5, text: '끝' }),
      generate: async () => '{"v":1}',
      dispose: vi.fn(async () => {}),
    }
    const h = createHandler(
      (m) => posted.push(m),
      async () => engine,
    )
    await h({ type: 'generate', id: 1, req: REQ })
    expect(posted[0]).toEqual({ type: 'error', id: 1, message: '모델을 먼저 불러오세요' })
    await h({ type: 'load', manifest: STUB_MANIFEST })
    await h({ type: 'generate', id: 2, req: REQ })
    expect(posted.slice(1)).toEqual([
      { type: 'progress', progress: { loaded: 5, total: 5, text: '끝' } },
      { type: 'ready' },
      { type: 'result', id: 2, text: '{"v":1}' },
    ])
    await h({ type: 'dispose' })
    expect(engine.dispose).toHaveBeenCalled()
  })

  it('어댑터가 없으면 load 가 error(id null)', async () => {
    const posted: FromWorker[] = []
    const h = createHandler(
      (m) => posted.push(m),
      async (rt) => {
        throw new Error(`지원 안 함 ${rt}`)
      },
    )
    await h({ type: 'load', manifest: STUB_MANIFEST })
    expect(posted).toEqual([{ type: 'error', id: null, message: '지원 안 함 webllm' }])
  })
})

describe('StubRunner · readStubScript', () => {
  it('대본 — 마지막 "관리자: " 뒤 문장으로 찾고, 없으면 unknown', async () => {
    const r = new StubRunner({ '801 배터리?': { v: 1, intent: 'ask.node', target: {}, set: {} } })
    expect(JSON.parse(await r.generate(REQ)).intent).toBe('ask.node')
    const follow = { ...REQ, user: '상태: …\n질문: 이름?\n관리자: 처음 보는 말' }
    expect(JSON.parse(await r.generate(follow)).intent).toBe('unknown')
  })
  it('manual — 개발 화면 입력칸을 그대로 낸다', async () => {
    manualOutput.value = '{"v":1,"intent":"cancel","target":{},"set":{}}'
    expect(await new StubRunner('manual').generate(REQ)).toBe(manualOutput.value)
  })
  it('개발 서버가 아니면 대본을 읽지 않는다, 깨진 JSON 도 null', () => {
    const s = { getItem: () => '{"a":1}' }
    expect(readStubScript(s, false)).toBeNull()
    expect(readStubScript(s, true)).toEqual({ a: 1 })
    expect(readStubScript({ getItem: () => 'manual' }, true)).toBe('manual')
    expect(readStubScript({ getItem: () => '{oops' }, true)).toBeNull()
    expect(readStubScript({ getItem: () => null }, true)).toBeNull()
  })
})
