import { reactive, shallowRef, toRaw } from 'vue'
import { assistantApi } from '@/api/assistant'
import type { AssistantRuntime, ModelManifest, ModelManifestOn } from '@/api/types'
import { webllmCacheName } from './adapters/webllmFiles'
import { DEVICE_REASON, checkDevice, checkStorage } from './capability'
import {
  DEFAULT_CACHE,
  downloadFiles,
  missingFiles,
  pruneOld,
  type CacheNameOf,
} from './modelStore'
import { WorkerRunner, type LoadProgress, type ModelRunner } from './runner'

// 모델 상태 (admin-assistant.md 「모델 상태」) — 명령창을 닫아도, 다른 화면으로 가도 모듈에 남는다
export type ModelState =
  | 'loading' // 안내 받는 중
  | 'disabled' // enabled:false — 준비 중
  | 'unsupported' // 이 PC·이 판에서 못 씀 (reason)
  | 'need-download'
  | 'downloading'
  | 'starting' // 불러오는 중
  | 'ready'
  | 'no-space'
  | 'failed' // (reason)

export const model = reactive({
  state: 'loading' as ModelState,
  manifest: null as ModelManifest | null,
  reason: '',
  /** 받아야 할 바이트 */
  need: 0,
  /** 남은 저장 공간(모르면 null) */
  free: null as number | null,
  progress: { loaded: 0, total: 0, text: '' } as LoadProgress,
})

/** 준비된 모델 — 명령창이 이것으로 답을 만든다 */
export const engine = shallowRef<{ runner: ModelRunner; manifest: ModelManifestOn } | null>(null)

/** 0단계 결과로 고른 실행 도구 — worker.ts 의 adapterFor 와 같은 목록 */
export const SUPPORTED_RUNTIMES: AssistantRuntime[] = ['webllm']
export const cacheNameFor = (rt: AssistantRuntime): CacheNameOf =>
  rt === 'webllm' ? webllmCacheName : () => DEFAULT_CACHE

let aborter: AbortController | null = null
let inflight: Promise<void> | null = null

/** 원본 객체로 — Worker 로 postMessage 하므로 Vue 반응형(Proxy)이면 복제되지 않는다(DataCloneError) */
const enabledManifest = (): ModelManifestOn | null => {
  const m = toRaw(model.manifest)
  return m && m.enabled ? m : null
}
const message = (e: unknown) => (e instanceof Error ? e.message : String(e))

async function setEngine(next: { runner: ModelRunner; manifest: ModelManifestOn } | null) {
  const prev = engine.value
  engine.value = next
  if (prev && prev.runner !== next?.runner) await prev.runner.dispose().catch(() => {})
}

async function prepare(m: ModelManifestOn): Promise<void> {
  if (!SUPPORTED_RUNTIMES.includes(m.runtime)) {
    model.state = 'unsupported'
    model.reason = `이 판의 실행 도구(${m.runtime})를 아직 지원하지 않습니다.`
    return
  }
  const dev = await checkDevice()
  if (!dev.ok) {
    model.state = 'unsupported'
    model.reason = DEVICE_REASON[dev.reason]
    return
  }
  const missing = await missingFiles(m, cacheNameFor(m.runtime))
  if (!missing.length) return start(m)
  model.need = missing.reduce((s, f) => s + f.size, 0)
  const st = await checkStorage(model.need)
  model.free = st.free
  model.state = st.ok ? 'need-download' : 'no-space'
}

async function start(m: ModelManifestOn): Promise<void> {
  model.state = 'starting'
  model.progress = { loaded: 0, total: 0, text: '' }
  try {
    const runner = new WorkerRunner()
    await runner.load(m, (p) => (model.progress = p))
    await setEngine({ runner, manifest: m })
    await pruneOld(m, cacheNameFor(m.runtime)).catch(() => 0)
    model.state = 'ready'
  } catch (e) {
    model.state = 'failed'
    model.reason = message(e)
  }
}

/** 서버 안내를 받아 이 PC 에서 쓸 수 있는지 본다 — 이미 받은 모델이면 바로 불러온다 */
export function initModel(): Promise<void> {
  if (['downloading', 'starting', 'ready'].includes(model.state)) return Promise.resolve()
  inflight ??= (async () => {
    model.state = 'loading'
    model.reason = ''
    try {
      model.manifest = await assistantApi.model()
      const m = enabledManifest()
      if (!m) model.state = 'disabled'
      else await prepare(m)
    } catch (e) {
      model.state = 'failed'
      model.reason = message(e)
    } finally {
      inflight = null
    }
  })()
  return inflight
}

/** [AI 모델 받기] — 받는 동안 창을 닫거나 다른 화면으로 가도 계속 받는다 */
export async function downloadModel(): Promise<void> {
  const m = enabledManifest()
  if (!m || model.state !== 'need-download') return
  model.state = 'downloading'
  model.progress = { loaded: 0, total: model.need, text: '' }
  aborter = new AbortController()
  try {
    await (navigator as unknown as { storage?: { persist?(): Promise<boolean> } }).storage
      ?.persist?.()
      .catch(() => false)
    await downloadFiles(m, cacheNameFor(m.runtime), (p) => (model.progress = p), aborter.signal)
    await start(m)
  } catch (e) {
    if ((e as Error).name === 'AbortError') {
      model.state = 'need-download'
      return
    }
    model.state = 'failed'
    model.reason = message(e)
  } finally {
    aborter = null
  }
}

export function cancelDownload(): void {
  aborter?.abort()
}

/** 저장 공간 부족 · 실패 · 판 바뀜 뒤 처음부터 다시 */
export async function checkAgain(): Promise<void> {
  await setEngine(null)
  model.state = 'failed' // initModel 의 '이미 준비됨' 가드를 지나게
  await initModel()
}

/** 테스트용 — 모듈 상태를 처음으로 */
export async function resetModel(): Promise<void> {
  aborter?.abort()
  aborter = null
  inflight = null
  await setEngine(null)
  Object.assign(model, {
    state: 'loading',
    manifest: null,
    reason: '',
    need: 0,
    free: null,
    progress: { loaded: 0, total: 0, text: '' },
  })
}
