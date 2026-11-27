import type { AssistantRuntime } from '@/api/types'
import type { FromWorker, ModelRunner, ToWorker } from './runner'
import { createHandler } from './workerCore'

// DOM 타입 안에서 쓰는 Worker 전역 — tsconfig 에 WebWorker lib 를 더하면 DOM 과 겹친다
const ctx = self as unknown as {
  postMessage(m: FromWorker): void
  onmessage: ((e: MessageEvent<ToWorker>) => void) | null
}

// 실행 도구 라이브러리는 여기서만 동적 import 한다 — 화면 청크(prefetchViews)에 들어가지 않게.
// model.ts 의 SUPPORTED_RUNTIMES 와 같은 목록
async function adapterFor(runtime: AssistantRuntime): Promise<ModelRunner> {
  switch (runtime) {
    case 'webllm':
      return new (await import('./adapters/webllm')).WebLlmRunner()
    default:
      throw new Error(`이 실행 도구(${runtime})는 아직 지원하지 않습니다`)
  }
}

const handle = createHandler((m) => ctx.postMessage(m), adapterFor)
ctx.onmessage = (e) => void handle(e.data)
