import { ref } from 'vue'

/** AI 비서가 변경을 적용할 때마다 1 씩 — 뒤 화면(주간 시간표·강의실 설정)이 지켜보다 다시 불러온다.
 * store.ts(모델·Worker 를 끌어온다)와 떼어 둔다 — 화면은 이 신호만 import 한다 */
export const appliedTick = ref(0)
