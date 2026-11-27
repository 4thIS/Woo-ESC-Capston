import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { useAssistant } from '@/admin/assistant/useAssistant'
import { DevRuleRunner } from '@/admin/assistant/dev/devRule'
import { STUB_MANIFEST } from '@/admin/assistant/adapters/stub'
import type { PreviewOut, TurnIn, TurnOut } from '@/api/types'

// 서버(#181) 응답 모양 그대로 — server/app/assistant/service.py 의 _out
const out = (o: Partial<TurnOut>): TurnOut => ({
  conversation_id: 'c1',
  kind: 'answer',
  message: '',
  choices: [],
  next_prefix: null,
  closed: false,
  preview: null,
  answer: null,
  ...o,
})
const PREVIEW: PreviewOut = {
  preview_id: 'p1',
  expires_at: new Date('2026-11-27T10:10:00Z'),
  summary: ['+ 11/27(금) 15:00–18:00 특강 "알고리즘 특강" (공학관 803)'],
  blockers: [],
  warnings: [],
  notices: [],
  rooms: [],
}
const ASK = out({
  kind: 'ask',
  message: '특강 이름은 무엇인가요?',
  next_prefix: '상태: event.add | 이름 ?\n질문: 특강 이름은 무엇인가요?\n관리자: ',
})

/** 차례로 답하는 서버 — 받은 요청은 calls 에 남는다 */
function scripted(...replies: (TurnOut | Error)[]) {
  const calls: TurnIn[] = []
  const turn = vi.fn(async (t: TurnIn) => {
    calls.push(t)
    const r = replies.shift()
    if (!r) throw new Error('더 답할 것 없음')
    if (r instanceof Error) throw r
    return r
  })
  const apply = vi.fn(async () => ({ change_id: 17, outbox_ids: [512] }))
  return { calls, api: { turn, apply } }
}
const make = (api: ReturnType<typeof scripted>['api'], onApplied?: () => void) =>
  useAssistant({ api, runner: new DevRuleRunner(), manifest: STUB_MANIFEST, onApplied })

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('useAssistant — 명령창 흐름 (admin-assistant.md 「흐름」, 서버 #181)', () => {
  it('보내기 → 되묻기 → 답 → 확인 → 적용 → 3초 뒤 닫힘, 다음 대화는 conversation_id null', async () => {
    const s = scripted(
      ASK,
      out({ kind: 'preview', message: '확인해 주세요', preview: PREVIEW, next_prefix: 'x' }),
      ASK,
    )
    const onApplied = vi.fn()
    const a = make(s.api, onApplied)
    a.open()
    await a.send('803 금요일 15시부터 18시 특강')
    expect(a.phase.value).toBe('ask')
    expect(a.sent.value).toBe('803 금요일 15시부터 18시 특강')
    expect(s.calls[0]).toMatchObject({ conversation_id: null, choice: null })
    expect(s.calls[0].form).toMatchObject({ intent: 'event.add' })

    await a.send('알고리즘 특강')
    // 되묻기 뒤에는 서버가 준 대화 번호로, 답은 fill 양식으로
    expect(s.calls[1]).toMatchObject({ conversation_id: 'c1', utterance: '알고리즘 특강' })
    expect(s.calls[1].form).toMatchObject({ intent: 'fill', set: { subject: '알고리즘 특강' } })
    expect(a.phase.value).toBe('preview')

    await a.apply()
    expect(s.api.apply).toHaveBeenCalledWith('p1')
    expect(a.phase.value).toBe('applied')
    expect(onApplied).toHaveBeenCalledOnce()
    vi.advanceTimersByTime(3000)
    expect(a.phase.value).toBe('closed')

    // 적용하면 서버가 대화를 닫는다 — 다음 턴은 새 대화
    a.open()
    await a.send('803 금요일 15시부터 18시 특강')
    expect(s.calls[2].conversation_id).toBeNull()
  })

  it('선택지를 누르면 모델을 거치지 않고 choice 로 보낸다(utterance 는 라벨)', async () => {
    const s = scripted(
      out({
        kind: 'ask',
        message: '어느 것인가요?',
        choices: [
          { id: 'r12', label: '11/27 15:00 알고리즘 특강' },
          { id: 'r13', label: '11/28 10:00 세미나' },
        ],
        next_prefix: '상태: …\n질문: 어느 것인가요?\n관리자: ',
      }),
      out({ kind: 'preview', preview: PREVIEW }),
    )
    const a = make(s.api)
    a.open()
    await a.send('803 특강 지워줘')
    expect(a.turn.value?.choices).toHaveLength(2)
    await a.choose({ id: 'r13', label: '11/28 10:00 세미나' })
    expect(s.calls[1]).toEqual({
      conversation_id: 'c1',
      utterance: '11/28 10:00 세미나',
      form: null,
      choice: 'r13',
      raw_output: null,
    })
    expect(a.phase.value).toBe('preview')
  })

  it('error + closed:false 면 대화를 잇는다 — 다음 턴은 같은 대화 번호와 next_prefix', async () => {
    const s = scripted(
      out({
        kind: 'error',
        message: '시각을 알아듣지 못했습니다. 다시 말씀해 주세요.',
        next_prefix: '상태: event.add | 시각 ?\n질문: 몇 시부터 몇 시까지인가요?\n관리자: ',
      }),
      out({ kind: 'preview', preview: PREVIEW }),
    )
    const runner = new DevRuleRunner()
    const gen = vi.spyOn(runner, 'generate')
    const a = useAssistant({ api: s.api, runner, manifest: STUB_MANIFEST })
    a.open()
    await a.send('803 금요일 특강')
    expect(a.phase.value).toBe('error')
    expect(a.error.value).toBe('시각을 알아듣지 못했습니다. 다시 말씀해 주세요.')
    expect(a.sent.value).toBe('803 금요일 특강') // 머리 줄의 처음 문장은 그대로
    await a.send('3시부터 6시')
    expect(s.calls[1].conversation_id).toBe('c1')
    expect(gen.mock.calls[1][0].user).toBe(
      '상태: event.add | 시각 ?\n질문: 몇 시부터 몇 시까지인가요?\n관리자: 3시부터 6시',
    )
  })

  it('error + closed:true 면 새 대화로 — 다음 턴은 conversation_id null, 첫 접두어', async () => {
    const s = scripted(
      out({ kind: 'error', message: '이해하지 못했습니다.', closed: true }),
      out({ kind: 'preview', preview: PREVIEW }),
    )
    const a = make(s.api)
    a.open()
    await a.send('점심 뭐 먹지')
    expect(a.phase.value).toBe('error')
    await a.send('803 금요일 15시부터 18시까지 알고리즘 특강')
    expect(s.calls[1].conversation_id).toBeNull()
    expect(a.sent.value).toBe('803 금요일 15시부터 18시까지 알고리즘 특강')
  })

  it('조회 답(answer 있음)은 창에 남기고, 취소 답(answer null)은 닫는다', async () => {
    const table = {
      title: '빈 강의실',
      columns: ['강의실', '시각'],
      rows: [['801', '15:00–18:00']],
    }
    const s = scripted(
      out({ kind: 'answer', message: '빈 강의실', closed: true, answer: table }),
      out({ kind: 'answer', message: '요청을 취소했습니다.', closed: true }),
    )
    const a = make(s.api)
    a.open()
    await a.send('금요일 3시부터 6시 빈 강의실')
    expect(a.phase.value).toBe('answer')
    expect(a.turn.value?.answer).toEqual(table)
    a.close()
    a.open()
    await a.send('취소')
    expect(a.phase.value).toBe('closed')
    expect(s.calls[1].conversation_id).toBeNull()
  })

  it('빈 문장은 보내지 않고, 보내는 동안 다시 보내지 않는다', async () => {
    const s = scripted(out({ kind: 'answer', closed: true }))
    const a = make(s.api)
    a.open()
    await a.send('   ')
    expect(s.api.turn).not.toHaveBeenCalled()
    const first = a.send('취소')
    void a.send('취소')
    await first
    expect(s.api.turn).toHaveBeenCalledOnce()
  })

  it('만료(410)면 확인을 닫고 안내, 모델 판(409 schema_version)은 새로고침 안내', async () => {
    const s = scripted(
      out({ kind: 'preview', preview: PREVIEW }),
      out({ kind: 'preview', preview: { ...PREVIEW, preview_id: 'p2' } }),
    )
    const a = make(s.api)
    a.open()
    await a.send('803 금요일 15시부터 18시까지 알고리즘 특강')
    s.api.apply.mockRejectedValueOnce(new ApiError(410, '만료', [], { detail: 'expired' }))
    await a.apply()
    expect(a.phase.value).toBe('error')
    expect(a.error.value).toBe('확인 화면이 만료되었습니다. 다시 말씀해 주세요.')
    expect(a.preview.value).toBeNull()
    expect(a.reload.value).toBe(false)

    await a.send('803 금요일 15시부터 18시까지 알고리즘 특강')
    s.api.apply.mockRejectedValueOnce(new ApiError(409, 'x', [], { detail: 'schema_version' }))
    await a.apply()
    expect(a.error.value).toBe('AI 모델이 새 판으로 바뀌었습니다. 새로고침해 주세요.')
    expect(a.reload.value).toBe(true)
  })

  it('막음이 있으면 적용하지 않는다 — 막힌 미리보기는 rooms 가 비어 올 수 있다', async () => {
    const s = scripted(
      out({
        kind: 'preview',
        preview: { ...PREVIEW, summary: [], blockers: ['지난 날짜에는 추가할 수 없습니다'] },
      }),
    )
    const a = make(s.api)
    a.open()
    await a.send('803 금요일 15시부터 18시까지 알고리즘 특강')
    expect(a.phase.value).toBe('preview')
    await a.apply()
    expect(s.api.apply).not.toHaveBeenCalled()
    expect(a.phase.value).toBe('preview')
  })
})
