import { describe, expect, it, vi } from 'vitest'
import { DevRuleRunner, parseSentence } from '@/admin/assistant/dev/devRule'
import { createFakeAssistantApi, resolveTime } from '@/admin/assistant/dev/fakeServer'
import type { ResvWithRoom, RoomOut, SlotOut } from '@/api/types'

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
})

describe('resolveTime', () => {
  it('오후 기본(1~8시는 +12), 반 · 분', () => {
    expect(resolveTime('15시부터 18시까지')).toEqual({ s: 900, e: 1080 })
    expect(resolveTime('3시부터 6시')).toEqual({ s: 900, e: 1080 })
    expect(resolveTime('10시 반부터 12시')).toEqual({ s: 630, e: 720 })
    expect(resolveTime('9시 30분부터 11시')).toEqual({ s: 570, e: 660 })
    expect(resolveTime('오후')).toBeNull()
  })
})

describe('가짜 서버 — 개발 서버에서만', () => {
  const room: RoomOut = { id: 3, building_id: 7, room: 803, units: 1, reservable: true }
  const slot: SlotOut = {
    id: 5,
    day: 5,
    s_h: 15,
    s_m: 0,
    e_h: 17,
    e_m: 0,
    type: 1,
    subject: '자료구조',
    professor: '김교수',
    source: 2,
  }
  const deps = () => ({
    today: '2026-11-25',
    rooms: vi.fn(async () => [room]),
    buildings: vi.fn(async () => [
      { id: 7, school_id: 1, name: '공학관', bld: 'E', modem_id: null },
    ]),
    slots: vi.fn(async () => [slot]),
    reservations: vi.fn(async () => [] as ResvWithRoom[]),
    exams: vi.fn(async () => []),
    saveResv: vi.fn(async () => ({ id: 17, outbox_ids: [512] })),
  })

  it('이름이 없으면 되묻고, fill 로 채우면 미리보기 — 겹침 경고, 적용은 예약 저장', async () => {
    const d = deps()
    const api = createFakeAssistantApi(d)
    const ask = await api.turn({
      conversation_id: null,
      utterance: '803 금요일 15시부터 18시 특강',
      form: {
        v: 1,
        intent: 'event.add',
        target: {},
        set: { rooms: ['803'], when: '금요일', time: '15시부터 18시', type: '특강' },
      },
      choice: null,
    })
    expect(ask.kind).toBe('ask')
    expect(ask.message).toBe('특강 이름은 무엇인가요?')
    expect(ask.next_prefix).toContain('질문: 특강 이름은 무엇인가요?')
    const t = await api.turn({
      conversation_id: ask.conversation_id,
      utterance: '알고리즘 특강',
      form: { v: 1, intent: 'fill', target: {}, set: { subject: '알고리즘 특강' } },
      choice: null,
    })
    expect(t.kind).toBe('preview')
    const p = t.preview!
    expect(p.summary).toEqual(['+ 11/27(금) 15:00–18:00 특강 "알고리즘 특강" (공학관 803)'])
    expect(p.warnings).toEqual(['기존 수업 "자료구조"(15:00–17:00)와 겹칩니다'])
    const w = p.rooms[0].weeks[0]
    expect(w.week_start).toBe('2026-11-23')
    expect(w.before.reservations).toHaveLength(0)
    expect(w.after.reservations[0]).toMatchObject({ date: '2026-11-27', s_h: 15, e_h: 18, type: 5 })
    expect(w.changes).toEqual([
      { entity: 'resv', key: `r${w.after.reservations[0].id}`, op: 'add', fields: [] },
    ])
    expect(await api.apply(p.preview_id)).toEqual({ change_id: 17, outbox_ids: [512] })
    expect(d.saveResv).toHaveBeenCalledWith(3, {
      date: '2026-11-27',
      s_h: 15,
      s_m: 0,
      e_h: 18,
      e_m: 0,
      type: 5,
      subject: '알고리즘 특강',
      professor: '',
    })
  })

  it('연속 교시는 묶음 하나로 경고한다 — 교시마다 한 줄이 아니라 (격자와 같은 묶음)', async () => {
    const d = deps()
    d.slots = vi.fn(async () => [
      { ...slot, e_h: 16 },
      { ...slot, id: 6, s_h: 16, e_h: 17 },
    ])
    const t = await createFakeAssistantApi(d).turn({
      conversation_id: null,
      utterance: '803 금요일 15시부터 18시까지 알고리즘 특강',
      form: {
        v: 1,
        intent: 'event.add',
        target: {},
        set: {
          rooms: ['803'],
          when: '금요일',
          time: '15시부터 18시까지',
          type: '특강',
          subject: '알고리즘 특강',
        },
      },
      choice: null,
    })
    expect(t.preview!.warnings).toEqual(['기존 수업 "자료구조"(15:00–17:00)와 겹칩니다'])
  })

  it('강의실을 모르면 error, 취소는 닫힘', async () => {
    const api = createFakeAssistantApi(deps())
    const e = await api.turn({
      conversation_id: null,
      utterance: '999 금 3시부터 4시 특강 a',
      form: {
        v: 1,
        intent: 'event.add',
        target: {},
        set: { rooms: ['999'], when: '금', time: '3시부터 4시', type: '특강', subject: 'a' },
      },
      choice: null,
    })
    expect(e).toMatchObject({ kind: 'error', message: '999호를 찾지 못했습니다.' })
    const c = await api.turn({
      conversation_id: null,
      utterance: '취소',
      form: { v: 1, intent: 'cancel', target: {}, set: {} },
      choice: null,
    })
    expect(c).toMatchObject({ kind: 'answer', closed: true })
  })
})
