import { describe, expect, it, vi } from 'vitest'
import { MODEL_ID, WebLlmRunner, appConfig } from '@/admin/assistant/adapters/webllm'
import type { ModelManifestOn } from '@/api/types'

// vi.mock 은 파일 맨 위로 끌어올려진다 — 그 안에서 쓰는 가짜는 vi.hoisted 로 먼저 만든다
const { create, unload } = vi.hoisted(() => ({ create: vi.fn(), unload: vi.fn() }))
vi.mock('@mlc-ai/web-llm', () => ({
  CreateMLCEngine: vi.fn(
    async (_id: string, cfg: { initProgressCallback: (r: unknown) => void }) => {
      cfg.initProgressCallback({ progress: 0.5, timeElapsed: 1, text: '반' })
      return { chat: { completions: { create } }, unload }
    },
  ),
}))

const M: ModelManifestOn = {
  enabled: true,
  schema_v: 1,
  runtime: 'webllm',
  repo: 'leemonta9482/esc-assistant-e2b',
  revision: 'a'.repeat(40),
  files: [
    { name: 'esc-assistant-webgpu.wasm', size: 1, sha256: 'x' },
    { name: 'params_shard_0.bin', size: 1, sha256: 'y' },
  ],
  system_prompt: 'SYS',
  first_prefix: '관리자: ',
  json_schema: { type: 'object' },
  generation: { temperature: 0, max_tokens: 256 },
}

describe('WebLLM 어댑터', () => {
  it('appConfig — 모델·라이브러리 모두 고정 판 HF 주소', () => {
    const c = appConfig(M)
    expect(c.model_list[0]).toEqual({
      model: `https://huggingface.co/leemonta9482/esc-assistant-e2b/resolve/${'a'.repeat(40)}/`,
      model_id: MODEL_ID,
      model_lib: `https://huggingface.co/leemonta9482/esc-assistant-e2b/resolve/${'a'.repeat(40)}/esc-assistant-webgpu.wasm`,
      // Gemma 4 는 manifest 가 있어야 KV 캐시 ABI 를 고른다 · 긴 문맥(131072)은 메모리만 쓴다 (02 spike.md Step 9)
      model_manifest: 'mlc-model-manifest.json',
      overrides: { context_window_size: 4096 },
    })
    expect(() => appConfig({ ...M, files: [] })).toThrow('.wasm')
  })

  it('load 진행률 · generate 는 system/user + json_schema 문법 강제 · dispose 는 unload', async () => {
    const r = new WebLlmRunner()
    const seen: unknown[] = []
    await r.load(M, (p) => seen.push(p))
    expect(seen[0]).toEqual({ loaded: 500, total: 1000, text: '반' })
    create.mockResolvedValue({ choices: [{ message: { content: '{"v":1}' } }] })
    const out = await r.generate({
      system: 'SYS',
      user: '관리자: 801 배터리?',
      schema: { type: 'object' },
      generation: { temperature: 0, max_tokens: 256 },
    })
    expect(out).toBe('{"v":1}')
    expect(create).toHaveBeenCalledWith({
      messages: [
        { role: 'system', content: 'SYS' },
        { role: 'user', content: '관리자: 801 배터리?' },
      ],
      temperature: 0,
      max_tokens: 256,
      response_format: { type: 'json_object', schema: '{"type":"object"}' },
    })
    await r.dispose()
    expect(unload).toHaveBeenCalled()
  })
})
