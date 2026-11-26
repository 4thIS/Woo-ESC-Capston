import type { AssistantRuntime } from '@/api/types'
import type { FromWorker, ModelRunner, ToWorker } from './runner'

export type AdapterFactory = (runtime: AssistantRuntime) => Promise<ModelRunner>

/** Worker 안의 메시지 처리 — worker.ts 는 이것을 self 에 잇기만 한다(테스트는 이것을 직접 부른다) */
export function createHandler(post: (m: FromWorker) => void, adapterFor: AdapterFactory) {
  let engine: ModelRunner | null = null
  return async (msg: ToWorker): Promise<void> => {
    try {
      if (msg.type === 'load') {
        await engine?.dispose()
        engine = null
        const next = await adapterFor(msg.manifest.runtime)
        await next.load(msg.manifest, (progress) => post({ type: 'progress', progress }))
        engine = next
        post({ type: 'ready' })
      } else if (msg.type === 'generate') {
        if (!engine) throw new Error('모델을 먼저 불러오세요')
        post({ type: 'result', id: msg.id, text: await engine.generate(msg.req) })
      } else {
        await engine?.dispose()
        engine = null
      }
    } catch (e) {
      post({
        type: 'error',
        id: msg.type === 'generate' ? msg.id : null,
        message: e instanceof Error ? e.message : String(e),
      })
    }
  }
}
