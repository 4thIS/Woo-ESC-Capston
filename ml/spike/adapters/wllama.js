// wllama (llama.cpp WASM) — GBNF 문법 강제. 업스트림은 CPU(WASM SIMD·멀티스레드)다 — WebGPU 아님을 표에 적는다.
// 모델 칸: GGUF URL. 조각(split)이면 쉼표로 여러 개.
import { Wllama } from 'https://cdn.jsdelivr.net/npm/@wllama/wllama@2/esm/index.js'

const CDN = 'https://cdn.jsdelivr.net/npm/@wllama/wllama@2/esm'
export const supportsGrammar = true
let w = null

export async function load(model, onProgress) {
  w = new Wllama({
    'single-thread/wllama.wasm': `${CDN}/single-thread/wllama.wasm`,
    'multi-thread/wllama.wasm': `${CDN}/multi-thread/wllama.wasm`,
  })
  const urls = model.split(',').map((s) => new URL(s.trim(), location.href).href)
  await w.loadModelFromUrl(urls.length === 1 ? urls[0] : urls, {
    progressCallback: ({ loaded, total }) => onProgress(total ? loaded / total : 0, '내려받는 중'),
  })
}

export async function generate(system, user, constraint) {
  const text = await w.createChatCompletion(
    [{ role: 'system', content: system }, { role: 'user', content: user }],
    { nPredict: 256, sampling: { temp: 0, ...(constraint?.gbnf ? { grammar: constraint.gbnf } : {}) } },
  )
  return { text, tokens: (await w.tokenize(text)).length }
}
