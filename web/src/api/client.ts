// 서버 계약 소비 계층의 진입점. 응답 타입은 이 폴더에 한 번만 선언한다 (web/CLAUDE.md).
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(`API ${status}`)
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'content-type': 'application/json', ...init?.headers },
  })
  if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => null))
  return (await res.json()) as T
}
