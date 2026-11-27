import type { ModelFile } from '@/api/types'

/** WebLLM 이 같은 URL 을 찾는 Cache API 이름 — 미리 넣어 두면 WebLLM 이 다시 받지 않는다.
 * @mlc-ai/web-llm 0.2.87 의 이름: 가중치 조각과 그 목록(tensor-cache.json)은 webllm/model,
 * 설정·토크나이저는 webllm/config, 모델 라이브러리는 webllm/wasm.
 * 다르면 WebLLM 이 한 번 더 받을 뿐 깨지지 않는다 */
export function webllmCacheName(f: ModelFile): string {
  if (f.name.endsWith('.wasm')) return 'webllm/wasm'
  if (f.name.startsWith('tensor-cache')) return 'webllm/model'
  if (f.name.endsWith('.json')) return 'webllm/config'
  return 'webllm/model'
}
