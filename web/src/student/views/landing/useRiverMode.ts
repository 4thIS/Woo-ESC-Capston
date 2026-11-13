import { computed, onScopeDispose, ref, type ComputedRef, type Ref } from 'vue'

const PC = '(min-width: 1024px) and (hover: hover) and (pointer: fine)'
const WIDE = '(min-width: 1024px)'
const REDUCE = '(prefers-reduced-motion: reduce)'

function useMedia(query: string): Ref<boolean> {
  const matched = ref(false)
  if (typeof window.matchMedia !== 'function') return matched
  const list = window.matchMedia(query)
  const update = () => {
    matched.value = list.matches
  }
  update()
  list.addEventListener('change', update)
  onScopeDispose(() => list.removeEventListener('change', update))
  return matched
}

/** 메인 페이지 로고를 잡고 던질 수 있는가 — 마우스 쓰는 넓은 화면 + 움직임 줄이기 아님 (spec §3) */
export function useRiverMode(): ComputedRef<boolean> {
  const pc = useMedia(PC)
  const reduce = useMedia(REDUCE)
  return computed(() => pc.value && !reduce.value)
}

/** 넓은 화면 배치인가 — 넓은 터치 화면은 잡지 못해도 배치는 PC 와 같다 */
export function useRiverWide(): Ref<boolean> {
  return useMedia(WIDE)
}
