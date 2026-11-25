// Transformers.js (ONNX, WebGPU) — 문법 강제 없음. 생각 모드는 chat template 에 enable_thinking:false 로 끈다.
// 우리 변환본은 'models/<폴더>' (Task 10 갈래 C).
import { env, pipeline } from 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@4'

export const supportsGrammar = false
let gen = null

export async function defaultModel() {
  return 'onnx-community/gemma-4-E2B-it-ONNX'
}

export async function load(model, onProgress) {
  let id = model
  if (model.startsWith('models/')) {
    env.allowLocalModels = true
    env.allowRemoteModels = false
    env.localModelPath = new URL('models/', location.href).href
    id = model.slice('models/'.length)
  }
  gen = await pipeline('text-generation', id, {
    dtype: 'q4f16',
    device: 'webgpu',
    progress_callback: (p) => { if (p.status === 'progress') onProgress(p.progress / 100, p.file) },
  })
}

export async function generate(system, user) {
  const prompt = gen.tokenizer.apply_chat_template(
    [{ role: 'system', content: system }, { role: 'user', content: user }],
    { add_generation_prompt: true, tokenize: false, enable_thinking: false },
  )
  const out = await gen(prompt, { max_new_tokens: 256, do_sample: false, return_full_text: false })
  const text = out[0].generated_text
  return { text, tokens: gen.tokenizer.encode(text).length }
}
