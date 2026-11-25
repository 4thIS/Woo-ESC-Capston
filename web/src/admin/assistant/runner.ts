import type { ModelGeneration, ModelManifestOn } from '@/api/types'

export interface GenerateReq {
  system: string
  user: string
  /** 출력 문법 강제(JSON Schema) — 지원하는 실행 도구만 쓴다 */
  schema: Record<string, unknown>
  generation: ModelGeneration
}
export interface LoadProgress {
  loaded: number
  total: number
  text: string
}
/** 실행 도구 하나 — Worker 안의 어댑터와 화면 쪽 WorkerRunner·StubRunner 가 같은 모양 */
export interface ModelRunner {
  load(m: ModelManifestOn, onProgress: (p: LoadProgress) => void): Promise<void>
  generate(req: GenerateReq): Promise<string>
  dispose(): Promise<void>
}

export type ToWorker =
  | { type: 'load'; manifest: ModelManifestOn }
  | { type: 'generate'; id: number; req: GenerateReq }
  | { type: 'dispose' }
export type FromWorker =
  | { type: 'progress'; progress: LoadProgress }
  | { type: 'ready' }
  | { type: 'result'; id: number; text: string }
  /** id null = 불러오기 실패 */
  | { type: 'error'; id: number | null; message: string }

export interface WorkerLike {
  postMessage(m: ToWorker): void
  terminate(): void
  onmessage: ((e: MessageEvent<FromWorker>) => void) | null
  onerror: ((e: ErrorEvent) => void) | null
}
const makeWorker = (): WorkerLike =>
  new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' }) as unknown as WorkerLike

/** 화면 쪽 — 모델은 Web Worker 에서 돈다(답을 만드는 동안 화면이 멈추지 않게). 요청은 id 로 짝짓는다 */
export class WorkerRunner implements ModelRunner {
  private w: WorkerLike | null = null
  private seq = 0
  private waiting = new Map<number, { ok: (t: string) => void; fail: (e: Error) => void }>()
  private loading: { ok: () => void; fail: (e: Error) => void } | null = null
  private onProgress: (p: LoadProgress) => void = () => {}

  constructor(private make: () => WorkerLike = makeWorker) {}

  load(m: ModelManifestOn, onProgress: (p: LoadProgress) => void): Promise<void> {
    const w = (this.w ??= this.attach(this.make()))
    this.onProgress = onProgress
    return new Promise<void>((ok, fail) => {
      this.loading = { ok, fail }
      w.postMessage({ type: 'load', manifest: m })
    })
  }

  generate(req: GenerateReq): Promise<string> {
    const w = this.w
    if (!w) return Promise.reject(new Error('모델을 먼저 불러오세요'))
    const id = ++this.seq
    return new Promise<string>((ok, fail) => {
      this.waiting.set(id, { ok, fail })
      w.postMessage({ type: 'generate', id, req })
    })
  }

  async dispose(): Promise<void> {
    if (this.w) {
      this.w.postMessage({ type: 'dispose' })
      this.w.terminate()
    }
    this.w = null
    this.failAll(new Error('모델을 내렸습니다'))
  }

  private attach(w: WorkerLike): WorkerLike {
    w.onmessage = (e) => this.receive(e.data)
    w.onerror = (e) => this.failAll(new Error(e.message || '모델 작업 공간 오류'))
    return w
  }

  private receive(m: FromWorker) {
    if (m.type === 'progress') this.onProgress(m.progress)
    else if (m.type === 'ready') {
      this.loading?.ok()
      this.loading = null
    } else if (m.type === 'result') {
      this.waiting.get(m.id)?.ok(m.text)
      this.waiting.delete(m.id)
    } else if (m.id === null) {
      this.loading?.fail(new Error(m.message))
      this.loading = null
    } else {
      this.waiting.get(m.id)?.fail(new Error(m.message))
      this.waiting.delete(m.id)
    }
  }

  private failAll(e: Error) {
    this.loading?.fail(e)
    this.loading = null
    for (const p of this.waiting.values()) p.fail(e)
    this.waiting.clear()
  }
}
