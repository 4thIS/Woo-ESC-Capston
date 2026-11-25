// 부록 §2 — 사용자 메시지 = 접두어 + 관리자 문장.
// 접두어는 첫 턴 manifest.first_prefix("관리자: "), 이어지는 턴은 서버 응답의 next_prefix

export function userMessage(prefix: string, utterance: string): string {
  return prefix + utterance.trim()
}

const FENCE = /^```(?:json)?\s*([\s\S]*?)\s*```$/
const isObj = (x: unknown): x is Record<string, unknown> =>
  !!x && typeof x === 'object' && !Array.isArray(x)

/** 모델 출력 → 양식 객체. 최소 모양(v 숫자 · intent 문자열 · target/set 객체)만 본다 — 규격 검증은 서버가 한다 */
export function parseForm(text: string): Record<string, unknown> | null {
  const t = text.trim()
  const body = FENCE.exec(t)?.[1] ?? t
  let v: unknown
  try {
    v = JSON.parse(body)
  } catch {
    return null
  }
  if (!isObj(v)) return null
  if (typeof v.v !== 'number' || typeof v.intent !== 'string') return null
  if (!isObj(v.target) || !isObj(v.set)) return null
  return v
}
