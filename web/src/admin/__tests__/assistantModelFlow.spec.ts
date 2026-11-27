import { beforeEach, describe, expect, it, vi } from 'vitest'
import { assistantApi } from '@/api/assistant'
import type { ModelManifestOn } from '@/api/types'
import { checkDevice, checkStorage } from '@/admin/assistant/capability'
import { downloadFiles, missingFiles } from '@/admin/assistant/modelStore'
import {
  cacheNameFor,
  checkAgain,
  downloadModel,
  initModel,
  model,
  resetModel,
} from '@/admin/assistant/model'

vi.mock('@/api/assistant', () => ({
  assistantApi: { model: vi.fn(), turn: vi.fn(), apply: vi.fn(), changes: vi.fn() },
  classify: vi.fn(() => null),
}))
vi.mock('@/admin/assistant/capability', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/admin/assistant/capability')>()),
  checkDevice: vi.fn(),
  checkStorage: vi.fn(),
}))
vi.mock('@/admin/assistant/modelStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/admin/assistant/modelStore')>()),
  missingFiles: vi.fn(),
  downloadFiles: vi.fn(async () => {}),
  pruneOld: vi.fn(async () => 0),
}))
vi.mock('@/admin/assistant/runner', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/admin/assistant/runner')>()
  class FakeRunner {
    load = vi.fn(async () => {})
    generate = vi.fn(async () => '')
    dispose = vi.fn(async () => {})
  }
  return { ...real, WorkerRunner: FakeRunner }
})

const M = (o: Partial<ModelManifestOn> = {}): ModelManifestOn => ({
  enabled: true,
  schema_v: 1,
  runtime: 'webllm',
  repo: 'leemonta9482/esc-assistant-e2b',
  revision: 'a'.repeat(40),
  files: [
    { name: 'params_shard_0.bin', size: 3, sha256: 'x' },
    { name: 'mlc-chat-config.json', size: 3, sha256: 'y' },
  ],
  system_prompt: '',
  first_prefix: '관리자: ',
  json_schema: {},
  generation: { temperature: 0, max_tokens: 256 },
  ...o,
})

beforeEach(async () => {
  await resetModel()
  localStorage.clear()
  vi.mocked(assistantApi.model).mockResolvedValue(M())
  vi.mocked(checkDevice).mockResolvedValue({ ok: true })
  vi.mocked(checkStorage).mockResolvedValue({ ok: true, free: 10 ** 10 })
  vi.mocked(downloadFiles).mockClear()
})

describe('model 흐름', () => {
  it('빠진 파일이 있으면 받기 버튼 → 받기 → 불러오기 → 준비됨', async () => {
    vi.mocked(missingFiles).mockResolvedValue(M().files)
    await initModel()
    expect(model.state).toBe('need-download')
    expect(model.need).toBe(6)
    await downloadModel()
    expect(downloadFiles).toHaveBeenCalled()
    expect(model.state).toBe('ready')
  })

  it('이미 받았으면 바로 불러온다, 기기 미지원이면 이유', async () => {
    vi.mocked(missingFiles).mockResolvedValue([])
    await initModel()
    expect(model.state).toBe('ready')
    expect(downloadFiles).not.toHaveBeenCalled()
    vi.mocked(checkDevice).mockResolvedValue({ ok: false, reason: 'no-webgpu' })
    await checkAgain()
    expect(model.state).toBe('unsupported')
    expect(model.reason).toContain('WebGPU')
  })

  it('저장 공간 부족 · 지원하지 않는 실행 도구', async () => {
    vi.mocked(missingFiles).mockResolvedValue(M().files)
    vi.mocked(checkStorage).mockResolvedValue({ ok: false, free: 1 })
    await initModel()
    expect(model.state).toBe('no-space')
    vi.mocked(assistantApi.model).mockResolvedValue(M({ runtime: 'wllama' }))
    await checkAgain()
    expect(model.state).toBe('unsupported')
    expect(cacheNameFor('wllama')(M().files[0])).toBe('esc-assistant-model')
  })
})
