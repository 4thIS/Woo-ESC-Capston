import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DEVICE_REASON, checkDevice, checkStorage } from '@/admin/assistant/capability'
import {
  ModelIntegrityError,
  VERIFIED_CACHE,
  downloadFiles,
  fileUrl,
  missingFiles,
  pruneOld,
} from '@/admin/assistant/modelStore'
import { webllmCacheName } from '@/admin/assistant/adapters/webllmFiles'
import type { ModelManifestOn } from '@/api/types'

// sha256("abc")
const ABC = 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'

class FakeCache {
  map = new Map<string, Uint8Array<ArrayBuffer>>()
  async match(k: string) {
    const v = this.map.get(k)
    return v ? new Response(v) : undefined
  }
  async put(k: string, r: Response) {
    this.map.set(k, new Uint8Array(await r.arrayBuffer()))
  }
  async delete(k: string) {
    return this.map.delete(k)
  }
  async keys() {
    return [...this.map.keys()].map((u) => new Request(u))
  }
}
class FakeCaches {
  all = new Map<string, FakeCache>()
  async open(name: string) {
    if (!this.all.has(name)) this.all.set(name, new FakeCache())
    return this.all.get(name)! as unknown as Cache
  }
  async keys() {
    return [...this.all.keys()]
  }
}

const M = (o: Partial<ModelManifestOn> = {}): ModelManifestOn => ({
  enabled: true,
  schema_v: 1,
  runtime: 'webllm',
  repo: 'leemonta9482/esc-assistant-e2b',
  revision: 'a'.repeat(40),
  files: [
    { name: 'params_shard_0.bin', size: 3, sha256: ABC },
    { name: 'mlc-chat-config.json', size: 3, sha256: ABC },
  ],
  system_prompt: '',
  first_prefix: '관리자: ',
  json_schema: {},
  generation: { temperature: 0, max_tokens: 256 },
  ...o,
})
const body = (s: string) => new Response(new TextEncoder().encode(s))
let store: FakeCaches
let fetchMock: ReturnType<typeof vi.fn>
beforeEach(() => {
  store = new FakeCaches()
  fetchMock = vi.fn(async () => body('abc'))
  vi.stubGlobal('fetch', fetchMock)
})

describe('capability', () => {
  it('저장소 · WebGPU · 장치 · 메모리 순서로 본다', async () => {
    const adapter = { requestAdapter: async () => ({}) }
    expect(await checkDevice({ gpu: adapter, deviceMemory: 8 }, false)).toEqual({
      ok: false,
      reason: 'no-cache',
    })
    expect(await checkDevice({}, true)).toEqual({ ok: false, reason: 'no-webgpu' })
    expect(await checkDevice({ gpu: { requestAdapter: async () => null } }, true)).toEqual({
      ok: false,
      reason: 'no-adapter',
    })
    expect(await checkDevice({ gpu: adapter, deviceMemory: 2 }, true)).toEqual({
      ok: false,
      reason: 'low-memory',
    })
    expect(await checkDevice({ gpu: adapter }, true)).toEqual({ ok: true })
    expect(DEVICE_REASON['no-webgpu']).toContain('Chrome·Edge')
  })
  it('저장 공간 — 필요량의 1.1배가 남아야 ok, 모르면 ok', async () => {
    const nav = (quota: number, usage: number) => ({
      storage: { estimate: async () => ({ quota, usage }) },
    })
    expect(await checkStorage(100, nav(200, 50))).toEqual({ ok: true, free: 150 })
    expect(await checkStorage(100, nav(150, 50))).toEqual({ ok: false, free: 100 })
    expect(await checkStorage(100, {})).toEqual({ ok: true, free: null })
  })
})

describe('modelStore', () => {
  const cacheName = webllmCacheName
  it('WebLLM 캐시 이름 — 가중치와 그 목록은 model, 설정·토크나이저는 config, 라이브러리는 wasm', () => {
    const f = (name: string) => webllmCacheName({ name, size: 1, sha256: '' })
    expect(f('params_shard_3.bin')).toBe('webllm/model')
    expect(f('tensor-cache.json')).toBe('webllm/model')
    expect(f('mlc-chat-config.json')).toBe('webllm/config')
    expect(f('tokenizer.json')).toBe('webllm/config')
    expect(f('lib.wasm')).toBe('webllm/wasm')
  })

  it('fileUrl — 커밋 해시로 고정한 resolve 주소', () => {
    expect(fileUrl(M(), 'a b.bin')).toBe(
      `https://huggingface.co/leemonta9482/esc-assistant-e2b/resolve/${'a'.repeat(40)}/a%20b.bin`,
    )
  })

  it('fileUrl — 개발 서버에서만 VITE_ASSISTANT_MODEL_HOST 로 HF 대신 로컬 주소', () => {
    vi.stubEnv('VITE_ASSISTANT_MODEL_HOST', 'http://127.0.0.1:8770')
    expect(fileUrl(M(), 'x.bin')).toBe(
      `http://127.0.0.1:8770/leemonta9482/esc-assistant-e2b/resolve/${'a'.repeat(40)}/x.bin`,
    )
    vi.stubEnv('DEV', false)
    expect(fileUrl(M(), 'x.bin')).toMatch(/^https:\/\/huggingface\.co\//)
    vi.unstubAllEnvs()
  })

  it('받기 — 파일마다 검증 표시, 진행률, 이미 받은 파일은 건너뛴다', async () => {
    const m = M()
    expect(await missingFiles(m, cacheName, store as unknown as CacheStorage)).toHaveLength(2)
    const seen: number[] = []
    await downloadFiles(
      m,
      cacheName,
      (p) => seen.push(p.loaded),
      undefined,
      store as unknown as CacheStorage,
    )
    expect(seen.at(-1)).toBe(6)
    expect(await missingFiles(m, cacheName, store as unknown as CacheStorage)).toEqual([])
    expect(store.all.get('webllm/model')!.map.has(fileUrl(m, 'params_shard_0.bin'))).toBe(true)
    expect(store.all.get('webllm/config')!.map.has(fileUrl(m, 'mlc-chat-config.json'))).toBe(true)
    expect(store.all.get(VERIFIED_CACHE)!.map.size).toBe(2)
    fetchMock.mockClear()
    await downloadFiles(m, cacheName, () => {}, undefined, store as unknown as CacheStorage)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('SHA-256 이 다르면 그 파일을 지우고 ModelIntegrityError', async () => {
    fetchMock.mockImplementation(async () => body('abd'))
    const m = M({ files: [{ name: 'params_shard_0.bin', size: 3, sha256: ABC }] })
    await expect(
      downloadFiles(m, cacheName, () => {}, undefined, store as unknown as CacheStorage),
    ).rejects.toBeInstanceOf(ModelIntegrityError)
    expect(store.all.get('webllm/model')!.map.size).toBe(0)
    expect(await missingFiles(m, cacheName, store as unknown as CacheStorage)).toHaveLength(1)
  })

  it('HTTP 오류면 멈춘다', async () => {
    fetchMock.mockResolvedValue(new Response('no', { status: 404 }))
    await expect(
      downloadFiles(M(), cacheName, () => {}, undefined, store as unknown as CacheStorage),
    ).rejects.toThrow('404')
  })

  it('옛 판 삭제 — 지금 판의 파일 주소가 아닌 키를 모두 지운다', async () => {
    const old = M({ revision: 'b'.repeat(40) })
    await downloadFiles(old, cacheName, () => {}, undefined, store as unknown as CacheStorage)
    const now = M()
    await downloadFiles(now, cacheName, () => {}, undefined, store as unknown as CacheStorage)
    expect(await pruneOld(now, cacheName, store as unknown as CacheStorage)).toBe(4)
    expect(await missingFiles(now, cacheName, store as unknown as CacheStorage)).toEqual([])
    expect(await missingFiles(old, cacheName, store as unknown as CacheStorage)).toHaveLength(2)
  })
})
