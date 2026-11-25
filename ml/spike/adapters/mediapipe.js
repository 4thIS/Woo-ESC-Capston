// MediaPipe tasks-genai LlmInference (LiteRT 계열 .task/.litertlm). 문법 강제 없음.
// MediaPipe LLM Inference 는 유지보수 모드 — 구글은 LiteRT-LM JS 로 옮기라고 안내한다(Step 7 확인 항목).
// generateResponse 는 원문 그대로 받으므로 Gemma 대화 틀을 직접 씌운다. 모델 카드의 chat template 과 다르면 PROMPT 한 줄만 고친다.
import { FilesetResolver, LlmInference } from 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-genai'

export const supportsGrammar = false
let llm = null
// Gemma 4 대화 틀(litert-community/gemma-4-E2B-it-litert-lm 의 chat_template.jinja) — 생각 모드 끔(<|think|> 없음).
// Gemma 3 의 <start_of_turn>/<end_of_turn> 과 다르다.
const PROMPT = (system, user) => `<|turn>system\n${system}<turn|>\n<|turn>user\n${user}<turn|>\n<|turn>model\n`

export async function defaultModel() {
  // 계획서의 litert-community/gemma-4-e2b-it/…-int4-web.task 는 401(없는 저장소) — 실제 공개 저장소 이름으로 고침
  return 'https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm/resolve/main/gemma-4-E2B-it-web.task'
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
