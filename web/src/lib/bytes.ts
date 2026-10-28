const enc = new TextEncoder()
export const utf8Bytes = (s: string) => enc.encode(s).length

/** max 바이트 안에 드는 앞부분 — 코드 포인트 단위라 글자를 반으로 자르지 않는다 */
export function clipBytes(s: string, max: number): string {
  let out = ''
  let n = 0
  for (const ch of s) {
    n += utf8Bytes(ch)
    if (n > max) break
    out += ch
  }
  return out
}
