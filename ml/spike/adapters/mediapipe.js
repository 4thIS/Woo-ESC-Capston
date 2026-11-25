// MediaPipe tasks-genai LlmInference (LiteRT 계열 .task/.litertlm). 문법 강제 없음.
// MediaPipe LLM Inference 는 유지보수 모드 — 구글은 LiteRT-LM JS 로 옮기라고 안내한다(Step 7 확인 항목).
// generateResponse 는 원문 그대로 받으므로 Gemma 대화 틀을 직접 씌운다. 모델 카드의 chat template 과 다르면 PROMPT 한 줄만 고친다.
import { FilesetResolver, LlmInference } from 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-genai'

export const supportsGrammar = false
let llm = null
const PROMPT = (system, user) => `<start_of_turn>user\n${system}\n\n${user}<end_of_turn>\n<start_of_turn>model\n`

export async function defaultModel() {
  return 'https://huggingface.co/litert-community/gemma-4-e2b-it/resolve/main/gemma-4-e2b-it-int4-web.task'
}

export async function load(model, onProgress) {
  const genai = await FilesetResolver.forGenAiTasks('https://cdn.jsdelivr.net/npm/@mediapipe/tasks-genai/wasm')
  onProgress(0, '내려받는 중(진행률 없음)')
  llm = await LlmInference.createFromOptions(genai, {
    baseOptions: { modelAssetPath: model },
    maxTokens: 2048,
    topK: 1,
    temperature: 0,
  })
  onProgress(1, '완료')
}

export async function generate(system, user) {
  const text = await llm.generateResponse(PROMPT(system, user))
  return { text, tokens: llm.sizeInTokens(text) }
}
