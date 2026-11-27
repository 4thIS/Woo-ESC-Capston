import type { MLCEngineInterface } from '@mlc-ai/web-llm'
import type { ModelManifestOn } from '@/api/types'
import { fileUrl, modelBase } from '../modelStore'
import type { GenerateReq, LoadProgress, ModelRunner } from '../runner'

// Worker 안에서만 import 한다(worker.ts 의 동적 import) — 화면 청크에 들어가지 않는다
export const MODEL_ID = 'esc-assistant'

/** 모델 폴더와 모델 라이브러리(.wasm) 모두 고정 판 HF 주소 — WebLLM 기본(GitHub raw) 라이브러리를 쓰지 않는다 */
export function appConfig(m: ModelManifestOn) {
  const lib = m.files.find((f) => f.name.endsWith('.wasm'))
  if (!lib) throw new Error('모델 안내에 .wasm 모델 라이브러리가 없습니다')
  return {
    model_list: [
      {
        model: modelBase(m),
        model_id: MODEL_ID,
        model_lib: fileUrl(m, lib.name),
        // Gemma 4 는 manifest 가 있어야 KV 캐시 ABI 를 고른다(없으면 'Invalid kv_cache ABI') ·
        // 설정의 긴 문맥(131072)은 메모리만 쓴다 — 지시문+문장+답은 1천 토큰 안 (02 spike.md Step 9)
        model_manifest: 'mlc-model-manifest.json',
        overrides: { context_window_size: 4096 },
      },
    ],
  }
}

export class WebLlmRunner implements ModelRunner {
  private engine: MLCEngineInterface | null = null

  async load(m: ModelManifestOn, onProgress: (p: LoadProgress) => void): Promise<void> {
    const webllm = await import('@mlc-ai/web-llm')
    this.engine = await webllm.CreateMLCEngine(MODEL_ID, {
      appConfig: appConfig(m),
      initProgressCallback: (r) =>
        onProgress({ loaded: Math.round(r.progress * 1000), total: 1000, text: r.text }),
    })
  }

  async generate(req: GenerateReq): Promise<string> {
    if (!this.engine) throw new Error('모델을 먼저 불러오세요')
    const r = await this.engine.chat.completions.create({
      messages: [
        { role: 'system', content: req.system },
        { role: 'user', content: req.user },
      ],
      temperature: req.generation.temperature,
      max_tokens: req.generation.max_tokens,
      // 출력 문법 강제 — 양식 밖 글자를 만들 수 없다 (spec §8.1 1순위 이유)
      response_format: { type: 'json_object', schema: JSON.stringify(req.schema) },
    })
    return r.choices[0]?.message?.content ?? ''
  }

  async dispose(): Promise<void> {
    await this.engine?.unload()
    this.engine = null
  }
}
