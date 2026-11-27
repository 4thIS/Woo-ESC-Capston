import { ref } from 'vue'
import { assistantApi } from '@/api/assistant'
import { STUB_MANIFEST } from './adapters/stub'
import { DevRuleRunner } from './dev/devRule'
import { useAssistant } from './useAssistant'

/** 적용이 끝날 때마다 1 씩 — 뒤 화면(주간 시간표 등)이 지켜보다 다시 불러온다 */
export const appliedTick = ref(0)

/** 사이드 메뉴 버튼이 보일지 — 학습한 모델이 배포되기 전(서버 model.json `enabled: false`)에는 개발 서버에서만.
 * 운영 화면에 아직 쓸 수 없는 버튼을 두지 않는다 */
export const assistantEnabled = import.meta.env.DEV

let instance: ReturnType<typeof useAssistant> | null = null

/** 관리자 셸에 하나 — 사이드 메뉴 버튼 · Ctrl K · 명령창이 같은 상태를 본다.
 * 서버는 실제 API(/api/assistant/*, #181). 모델 자리는 아직 개발용 규칙 해석기 — 모델 릴리스 뒤 WorkerRunner 로 바꾼다 */
export function assistantStore() {
  instance ??= useAssistant({
    api: assistantApi,
    runner: new DevRuleRunner(),
    manifest: STUB_MANIFEST,
    onApplied: () => appliedTick.value++,
  })
  return instance
}
