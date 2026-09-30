/** 로그인 뒤 돌아갈 경로 — 앱 안의 경로만. `//evil.com`·`/\evil.com` 은 브라우저가 외부 주소로 읽는다 */
export function safeNext(v: unknown, fallback: string): string {
  if (typeof v !== 'string' || !v.startsWith('/') || v.startsWith('//') || v.startsWith('/\\'))
    return fallback
  return v
}
