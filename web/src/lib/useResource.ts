import { ref, shallowRef, watch, type WatchSource } from 'vue'
import { ApiError } from '@/api/client'

/** 읽기 전용 리소스. 새 요청이 나가면 옛 응답은 버리고(요청 번호), 오류여도 이전 data 를 지킨다 (spec §4.3). */
export function useResource<T>(
  fetcher: () => Promise<T>,
  opts: { immediate?: boolean; deps?: WatchSource | WatchSource[] } = {},
) {
  const data = shallowRef<T>()
  const error = shallowRef<ApiError | null>(null)
  const loading = ref(false)
  const refreshedAt = shallowRef<Date | null>(null)
  let seq = 0

  async function reload(): Promise<void> {
    const mine = ++seq
    loading.value = true
    try {
      const v = await fetcher()
      if (mine !== seq) return
      data.value = v
      error.value = null
      refreshedAt.value = new Date()
    } catch (e) {
      if (mine !== seq) return
      if (!(e instanceof ApiError)) throw e // 버그는 삼키지 않는다
      error.value = e
    } finally {
      if (mine === seq) loading.value = false
    }
  }

  if (opts.deps) watch(opts.deps, () => void reload())
  if (opts.immediate !== false) void reload()
  return { data, error, loading, refreshedAt, reload }
}
