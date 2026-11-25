// WebLLM — JSON Schema 문법 강제(response_format). 미리 만든 목록에 Gemma 4 가 없으면 '미지원'으로 기록한다.
// 우리 변환본은 'models/<폴더>' 로 넣는다: 폴더 안에 mlc-chat-config.json·가중치 조각·lib.wasm (Task 10 갈래 B).
import * as webllm from 'https://esm.run/@mlc-ai/web-llm'

export const supportsGrammar = true
let engine = null

export async function defaultModel() {
  const hit = webllm.prebuiltAppConfig.model_list.find((m) => /gemma-?4/i.test(m.model_id))
  return hit ? hit.model_id : ''
}

export async function load(model, onProgress) {
  const custom = model.startsWith('models/') || model.startsWith('http')
  const base = custom ? new URL(model.replace(/\/?$/, '/'), location.href).href : null
  const appConfig = custom
    ? {
        model_list: [
          {
            model: base,
            model_id: 'esc-custom',
            model_lib: base + 'lib.wasm',
            // Gemma 4 는 미리 만든 목록처럼 manifest 가 있어야 KV 캐시 ABI 를 고른다(없으면 'Invalid kv_cache ABI')
            model_manifest: 'mlc-model-manifest.json',
            overrides: { context_window_size: 4096 },
          },
        ],
      }
    : undefined
  engine = await webllm.CreateMLCEngine(custom ? 'esc-custom' : model, {
    appConfig,
    initProgressCallback: (r) => onProgress(r.progress ?? 0, r.text),
  })
}

export async function generate(system, user, constraint) {
  const r = await engine.chat.completions.create({
    messages: [{ role: 'system', content: system }, { role: 'user', content: user }],
    temperature: 0,
    max_tokens: 256,
    ...(constraint ? { response_format: { type: 'json_object', schema: JSON.stringify(constraint.json_schema) } } : {}),
  })
  return { text: r.choices[0].message.content ?? '', tokens: r.usage?.completion_tokens ?? null }
}
