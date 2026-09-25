import { describe, expect, it } from 'vitest'
import { nextTick, ref } from 'vue'
import { ApiError } from '@/api/client'
import { useResource } from '@/lib/useResource'

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((a, b) => ((resolve = a), (reject = b)))
  return { promise, resolve, reject }
}
const flush = () => new Promise((r) => setTimeout(r))

describe('useResource', () => {
  it('늦게 온 옛 응답은 버린다 (Review Focus 3)', async () => {
    const calls: ReturnType<typeof deferred<string>>[] = []
    const r = useResource(() => {
      const d = deferred<string>()
      calls.push(d)
      return d.promise
    })
    void r.reload() // 두 번째 요청
    calls[1].resolve('new')
    await flush()
    calls[0].resolve('old')
    await flush()
    expect(r.data.value).toBe('new')
    expect(r.loading.value).toBe(false)
  })

  it('오류여도 이전 data 를 지킨다', async () => {
    let fail = false
    const r = useResource(async () => {
      if (fail) throw new ApiError(0, 'x')
      return 1
    })
    await flush()
    const first = r.refreshedAt.value
    fail = true
    await r.reload()
    expect(r.data.value).toBe(1)
    expect(r.error.value?.status).toBe(0)
    expect(r.refreshedAt.value).toBe(first)
  })

  it('성공하면 error 를 지운다', async () => {
    let fail = true
    const r = useResource(async () => {
      if (fail) throw new ApiError(500, 'x')
      return 2
    })
    await flush()
    fail = false
    await r.reload()
    expect(r.error.value).toBeNull()
    expect(r.data.value).toBe(2)
  })

  it('deps 가 바뀌면 다시 부른다, immediate:false 면 처음엔 안 부른다', async () => {
    const q = ref('a')
    const seen: string[] = []
    useResource(async () => seen.push(q.value), { deps: q, immediate: false })
    await flush()
    expect(seen).toEqual([])
    q.value = 'b'
    await nextTick()
    await flush()
    expect(seen).toEqual(['b'])
  })
})
