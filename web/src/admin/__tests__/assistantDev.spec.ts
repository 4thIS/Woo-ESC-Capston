import { describe, expect, it } from 'vitest'
import { DevRuleRunner, parseSentence } from '@/admin/assistant/dev/devRule'

const GEN = { temperature: 0, max_tokens: 256 }

describe('parseSentence — 개발용 규칙 해석기', () => {
  it('강의실 · 요일 · 시각 · 유형 · 이름을 문장 그대로 옮긴다', () => {
    expect(parseSentence('803호 이번주 금요일 15시부터 18시까지 알고리즘 특강 잡아줘')).toEqual({
      v: 1,
      intent: 'event.add',
      target: {},
      set: {
        rooms: ['803'],
        when: '이번주 금요일',
        time: '15시부터 18시까지',
        type: '특강',
        subject: '알고리즘 특강',
      },
    })
  })
  it('이름이 없으면 subject 를 빼고, 대관은 대여, 반은 시각에 남긴다', () => {
    const f = parseSentence('803 화요일 10시 반부터 12시 대관') as { set: Record<string, unknown> }
    expect(f.set).toEqual({
      rooms: ['803'],
      when: '화요일',
      time: '10시 반부터 12시',
      type: '대여',
    })
  })
  it('취소 · 알 수 없는 말', () => {
    expect(parseSentence('취소')).toMatchObject({ intent: 'cancel' })
    expect(parseSentence('점심 뭐 먹지')).toMatchObject({ intent: 'unknown' })
  })
})

describe('DevRuleRunner', () => {
  it('첫 턴은 문장 해석, 되물음 뒤("질문:" 있음)는 그 답을 fill 의 subject 로', async () => {
    const r = new DevRuleRunner()
    const first = JSON.parse(
      await r.generate({
        system: '',
        user: '관리자: 803 금요일 3시부터 6시 특강',
        schema: {},
        generation: GEN,
      }),
    )
    expect(first.intent).toBe('event.add')
    const fill = JSON.parse(
      await r.generate({
        system: '',
        user: '상태: …\n질문: 특강 이름은 무엇인가요?\n관리자: 알고리즘 특강',
        schema: {},
        generation: GEN,
      }),
    )
    expect(fill).toEqual({ v: 1, intent: 'fill', target: {}, set: { subject: '알고리즘 특강' } })
  })

  it('되물음의 답에 강의실 · 요일 · 시각이 있으면 그 칸으로 채운다(이름 대신)', async () => {
    const r = new DevRuleRunner()
    const fill = async (answer: string) =>
      JSON.parse(
        await r.generate({
          system: '',
          user: `상태: …\n질문: …\n관리자: ${answer}`,
          schema: {},
          generation: GEN,
        }),
      ).set
    expect(await fill('3시부터 6시')).toEqual({ time: '3시부터 6시' })
    expect(await fill('803호')).toEqual({ rooms: ['803'] })
    expect(await fill('다음주 금요일')).toEqual({ when: '다음주 금요일' })
    expect(await fill('알고리즘')).toEqual({ subject: '알고리즘' })
  })
})
