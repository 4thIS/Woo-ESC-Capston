// 개발 서버 전용 — 학습한 모델이 나오기 전, 관리자 문장을 양식(부록 §1)으로 옮기는 규칙 해석기.
// 모델처럼 "문장 속 표현을 그대로" 옮기기만 한다(날짜·시각 계산은 서버 몫). 운영 빌드에서는 쓰지 않는다.
import type { GenerateReq, LoadProgress, ModelRunner } from '../runner'
import type { ModelManifestOn } from '@/api/types'

type Form = { v: 1; intent: string; target: Record<string, unknown>; set: Record<string, unknown> }

const ROOM = /(\d{3,4})\s*호?/
// '지금'의 '금'처럼 낱말 안의 요일 글자는 잡지 않는다 — 앞은 처음·공백, 뒤는 '요일'·공백·끝
const DAY = /(?:^|\s)((?:이번\s*주|다음\s*주)\s+)?([월화수목금토일])(요일)?(?=\s|$)/
const TIME =
  /\d{1,2}\s*시(?:\s*(?:반|\d{1,2}\s*분))?\s*(?:부터|~|-)\s*\d{1,2}\s*시(?:\s*(?:반|\d{1,2}\s*분))?(?:\s*까지)?/
const TYPES: [RegExp, string][] = [
  [/특강|세미나/, '특강'],
  [/대관|대여/, '대여'],
  [/휴강/, '휴강'],
  [/시험/, '시험'],
]

export function parseSentence(text: string): Form {
  const t = text.trim()
  if (/^취소/.test(t)) return { v: 1, intent: 'cancel', target: {}, set: {} }
  const set: Record<string, unknown> = {}
  let rest = t
  const room = ROOM.exec(rest)
  if (room) {
    set.rooms = [room[1]]
    rest = rest.replace(room[0], ' ')
  }
  const day = DAY.exec(rest)
  if (day) {
    set.when = `${day[1] ?? ''}${day[2]}${day[3] ?? ''}`.trim()
    rest = rest.replace(day[0], ' ')
  }
  const time = TIME.exec(rest)
  if (time) {
    set.time = time[0].trim()
    rest = rest.replace(time[0], ' ')
  }
  const kind = TYPES.find(([re]) => re.test(rest))
  if (kind) {
    set.type = kind[1]
    // 유형 낱말 바로 앞 낱말이 이름 — 특강은 '알고리즘 특강'처럼 붙여 부른다
    const word = new RegExp(`(\\S+)\\s*(?:${kind[0].source})`).exec(rest)?.[1]
    if (word) set.subject = kind[1] === '특강' ? `${word} 특강` : word
  }
  if (!set.rooms && !set.time) return { v: 1, intent: 'unknown', target: {}, set: {} }
  return { v: 1, intent: 'event.add', target: {}, set }
}

const PREFIX = '관리자: '
const lastUtterance = (user: string) => {
  const i = user.lastIndexOf(PREFIX)
  return (i < 0 ? user : user.slice(i + PREFIX.length)).trim()
}

/** 개발용 실행 도구 — 첫 턴은 문장 해석, 되물음 뒤("질문:" 이 있는 접두어)는 답을 fill 로 */
export class DevRuleRunner implements ModelRunner {
  async load(_m: ModelManifestOn, onProgress: (p: LoadProgress) => void): Promise<void> {
    onProgress({ loaded: 1, total: 1, text: '개발용 규칙 해석기' })
  }

  async generate(req: GenerateReq): Promise<string> {
    const u = lastUtterance(req.user)
    if (req.user.includes('질문:')) {
      const form: Form = /^취소/.test(u)
        ? { v: 1, intent: 'cancel', target: {}, set: {} }
        : { v: 1, intent: 'fill', target: {}, set: { subject: u } }
      return JSON.stringify(form)
    }
    return JSON.stringify(parseSentence(u))
  }

  async dispose(): Promise<void> {}
}
