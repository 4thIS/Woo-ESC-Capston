import { computed } from 'vue'
import { assistantApi } from '@/api/assistant'
import { STUB_MANIFEST } from './adapters/stub'
import { DevRuleRunner } from './dev/devRule'
import { engine, model } from './model'
import { useAssistant } from './useAssistant'
import { appliedTick } from './applied'

export { appliedTick }

/** 개발 서버에서 배포된 모델이 없을 때(enabled:false) — 규칙 해석기로 대화 흐름을 만든다 */
const devFallback = computed(
  () => import.meta.env.DEV && (model.state === 'loading' || model.state === 'disabled'),
)

/** 사이드 메뉴 버튼이 보일지 — 모델이 배포되기 전(서버 model.json `enabled: false`)에는 개발 서버에서만.
 * 운영 화면에 아직 쓸 수 없는 버튼을 두지 않는다 */
export const assistantVisible = computed(
  () => import.meta.env.DEV || (model.state !== 'loading' && model.state !== 'disabled'),
)

/** 입력칸을 쓸 수 있는지 — 모델이 준비됐거나 개발용 대역일 때. 아니면 명령창에 모델 상태가 선다 */
export const canType = computed(() => engine.value !== null || devFallback.value)

let instance: ReturnType<typeof useAssistant> | null = null

/** 관리자 셸에 하나 — 사이드 메뉴 버튼 · Ctrl K · 명령창이 같은 상태를 본다.
 * 답은 이 PC 에서 돈 모델(model.ts 의 engine, Web Worker)이 만들고, 서버는 실제 API(/api/assistant/*) */
export function assistantStore() {
  if (instance) return instance
  const dev = new DevRuleRunner()
  instance = useAssistant({
    api: assistantApi,
    // 보낼 때마다 지금 준비된 모델을 본다 — 받기·불러오기가 명령창을 연 뒤에 끝나도 된다
    get runner() {
      return engine.value?.runner ?? dev
    },
    get manifest() {
      return engine.value?.manifest ?? STUB_MANIFEST
    },
    onApplied: () => appliedTick.value++,
  })
  return instance
}
