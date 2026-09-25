// 서버 계약의 유일한 출입구 (spec §4.1). 화면은 fetch 를 직접 부르지 않는다.
import { parseUtc } from '@/lib/time'
import { clearSession, session } from '@/lib/session'

export const MESSAGES: Record<number, string> = {
  0: '서버에 연결할 수 없습니다. 네트워크를 확인해 주세요.',
  400: '요청을 처리할 수 없습니다.',
  401: '다시 로그인해 주세요.',
  403: '이 화면을 쓸 권한이 없습니다.',
  404: '찾을 수 없습니다.',
  409: '다른 사람이 먼저 바꿨습니다. 목록을 새로 불러옵니다.',
  422: '입력값을 확인해 주세요.',
  429: '잠시 후 다시 시도해 주세요.',
  500: '서버 오류가 났습니다. 잠시 후 다시 시도해 주세요.',
  503: '요청이 몰렸습니다. 잠시 후 다시 시도해 주세요.',
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public fields: string[] = [],
    public detail: unknown = null,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
export interface RequestOpts {
  auth?: boolean
  dates?: readonly string[]
  signal?: AbortSignal
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

function withDates(v: unknown, keys: readonly string[]): unknown {
  if (Array.isArray(v)) return v.map((x) => withDates(x, keys))
  if (v && typeof v === 'object') {
    const o: Record<string, unknown> = { ...(v as Record<string, unknown>) }
    for (const k of keys) if (typeof o[k] === 'string') o[k] = parseUtc(o[k] as string)
    return o
  }
  return v
}

function fieldNames(detail: unknown): string[] {
  const list = (detail as { detail?: unknown } | null)?.detail
  if (!Array.isArray(list)) return []
  return list
    .map((x) => {
      const loc = (x as { loc?: unknown[] }).loc
      return loc?.[loc.length - 1]
    })
    .filter((x): x is string => typeof x === 'string')
}

export async function request<T>(
  method: Method,
  path: string,
  body?: unknown,
  opts: RequestOpts = {},
): Promise<T> {
  const token = opts.auth === false ? null : (session.value?.token ?? null)
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['content-type'] = 'application/json'
  if (token) headers.authorization = `Bearer ${token}`

  let res: Response
  for (let attempt = 0; ; attempt++) {
    try {
      res = await fetch(path, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: opts.signal,
      })
    } catch (e) {
      if ((e as Error).name === 'AbortError') throw e
      throw new ApiError(0, MESSAGES[0])
    }
    // 멱등한 GET 만 1초 뒤 1회 (spec §4.1). 쓰기는 두 번 들어갈 수 있어 재시도하지 않는다
    if (res.status === 503 && method === 'GET' && attempt === 0) {
      await sleep(1000)
      continue
    }
    break
  }

  if (res.ok) {
    if (res.status === 204) return undefined as T
    const data: unknown = await res.clone().json()
    return (opts.dates ? withDates(data, opts.dates) : data) as T
  }

  const detail: unknown = await res
    .clone()
    .json()
    .catch(() => null)
  // 토큰을 보낸 요청만 — 로그인 실패 401(auth:false)은 세션 만료가 아니다
  if (token && res.status === 401) clearSession('expired')
  if (token && res.status === 403) {
    console.error('403 — 역할 불일치(정상 흐름이면 로그인 단계에서 막힌다)', path)
    clearSession('forbidden')
  }
  throw new ApiError(
    res.status,
    MESSAGES[res.status] ?? MESSAGES[500],
    res.status === 422 ? fieldNames(detail) : [],
    detail,
  )
}
