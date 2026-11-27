import { createSHA256 } from 'hash-wasm'
import type { ModelFile, ModelManifestOn } from '@/api/types'
import type { LoadProgress } from './runner'

/** 검증을 마친 파일 표시 — 파일 캐시와 따로 둔다(내려받는 도중 꺼진 파일을 '받음'으로 보지 않게) */
export const VERIFIED_CACHE = 'esc-assistant-verified'
/** 실행 도구가 따로 캐시 이름을 정하지 않으면 */
export const DEFAULT_CACHE = 'esc-assistant-model'
export type CacheNameOf = (f: ModelFile) => string

export class ModelIntegrityError extends Error {
  constructor(public file: string) {
    super(`모델 파일 검증에 실패했습니다(${file}). 다시 받아 주세요.`)
    this.name = 'ModelIntegrityError'
  }
}

/** 모델 파일 주소의 앞부분 — 개발 서버에서만 VITE_ASSISTANT_MODEL_HOST 로 HF 대신 로컬 폴더를 쓴다
 * (올리기 전 변환본 확인용. 운영 빌드에서는 늘 HF) */
const host = () =>
  (import.meta.env.DEV && import.meta.env.VITE_ASSISTANT_MODEL_HOST) || 'https://huggingface.co'

/** 커밋 해시로 고정한 판의 폴더 (부록 §4.1) */
export const modelBase = (m: ModelManifestOn) => `${host()}/${m.repo}/resolve/${m.revision}/`
export const fileUrl = (m: ModelManifestOn, name: string) => modelBase(m) + encodeURI(name)

const realStore = () => caches

export async function missingFiles(
  m: ModelManifestOn,
  cacheName: CacheNameOf,
  store: CacheStorage = realStore(),
): Promise<ModelFile[]> {
  const ok = await store.open(VERIFIED_CACHE)
  const out: ModelFile[] = []
  for (const f of m.files) {
    const url = fileUrl(m, f.name)
    const mark = await ok.match(url)
    const file = mark && (await (await store.open(cacheName(f))).match(url))
    if (!mark || !file || (await mark.text()) !== f.sha256) out.push(f)
  }
  return out
}

/** 빠진 파일만 차례로 받는다 — 스트림을 둘로 나눠 하나는 캐시로, 하나는 SHA-256 으로 (메모리에 통째로 올리지 않는다) */
export async function downloadFiles(
  m: ModelManifestOn,
  cacheName: CacheNameOf,
  onProgress: (p: LoadProgress) => void,
  signal?: AbortSignal,
  store: CacheStorage = realStore(),
): Promise<void> {
  const todo = await missingFiles(m, cacheName, store)
  const total = todo.reduce((s, f) => s + f.size, 0)
  let loaded = 0
  const ok = await store.open(VERIFIED_CACHE)
  for (const f of todo) {
    const url = fileUrl(m, f.name)
    const res = await fetch(url, { signal })
    if (!res.ok || !res.body)
      throw new Error(`모델 파일을 받지 못했습니다(${f.name}, ${res.status})`)
    const cache = await store.open(cacheName(f))
    const [toCache, toHash] = res.body.tee()
    const putting = cache.put(
      url,
      new Response(toCache, {
        headers: { 'content-type': res.headers.get('content-type') ?? 'application/octet-stream' },
      }),
    )
    const h = await createSHA256()
    h.init()
    const reader = toHash.getReader()
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      h.update(value)
      loaded += value.byteLength
      onProgress({ loaded, total, text: f.name })
    }
    await putting
    const got = h.digest('hex')
    if (got !== f.sha256) {
      await cache.delete(url)
      throw new ModelIntegrityError(f.name)
    }
    await ok.put(url, new Response(got))
  }
}

/** 지금 판의 파일 주소가 아닌 키를 지운다 — 판이 바뀌면 1.5 GB 가 두 벌 쌓이지 않게. 지운 개수를 돌려준다 */
export async function pruneOld(
  m: ModelManifestOn,
  cacheName: CacheNameOf,
  store: CacheStorage = realStore(),
): Promise<number> {
  const keep = new Set(m.files.map((f) => fileUrl(m, f.name)))
  const names = new Set([VERIFIED_CACHE, DEFAULT_CACHE, ...m.files.map(cacheName)])
  let n = 0
  for (const name of names) {
    const c = await store.open(name)
    for (const req of await c.keys())
      if (req.url.startsWith(host()) && !keep.has(req.url)) {
        await c.delete(req.url)
        n++
      }
  }
  return n
}
