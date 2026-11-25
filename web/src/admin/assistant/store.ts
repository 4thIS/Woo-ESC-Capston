import { ref } from 'vue'
import { STUB_MANIFEST } from './adapters/stub'
import { DevRuleRunner } from './dev/devRule'
import { createFakeAssistantApi } from './dev/fakeServer'
import { useAssistant } from './useAssistant'

/** 적용이 끝날 때마다 1 씩 — 뒤 화면(주간 시간표 등)이 지켜보다 다시 불러온다 */
export const appliedTick = ref(0)

/** 사이드 메뉴 버튼이 보일지 — 서버 API(01 PR B)·모델 배포 전에는 개발 서버에서만 (운영 화면에 고장 난 버튼을 두지 않는다) */
export const assistantEnabled = import.meta.env.DEV

let instance: ReturnType<typeof useAssistant> | null = null

/** 관리자 셸에 하나 — 사이드 메뉴 버튼 · Ctrl K · 명령창이 같은 상태를 본다.
 * 지금은 개발용 대역뿐: 규칙 해석기(모델 대신) + 가짜 서버(01 PR B 대신, 실제 DB 를 읽고 예약 API 로 적용) */
export function assistantStore() {
  instance ??= useAssistant({
    api: createFakeAssistantApi(),
    runner: new DevRuleRunner(),
    manifest: STUB_MANIFEST,
    onApplied: () => appliedTick.value++,
  })
  return instance
}
