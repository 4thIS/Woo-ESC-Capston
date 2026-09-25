import { describe, expect, it } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import type { FreeDay } from '@/api/types'
import ReserveSheet from '../ReserveSheet.vue'
import { CAP_TEXT, DAILY_TEXT, FULL_TEXT } from '../rules'

const NOW = new Date('2026-10-23T01:42:00Z') // KST 금 10:42
const all = [{ from: '09:00', to: '21:00' }]
// 오늘의 10:40 구간은 서버가 준 뒤 시간이 흘러 지난 것 — 화면이 지운다
const DAYS: FreeDay[] = [
  {
    date: '2026-10-23',
    spans: [
      { from: '10:40', to: '11:30' },
      { from: '16:00', to: '21:00' },
    ],
  },
  { date: '2026-10-24', spans: [] },
  { date: '2026-10-25', spans: all },
  { date: '2026-10-26', spans: all },
  { date: '2026-10-27', spans: all },
  { date: '2026-10-28', spans: all },
  { date: '2026-10-29', spans: all },
  { date: '2026-10-30', spans: all },
]
const base = { days: DAYS, now: NOW, myFutureCount: 0 }
type W = VueWrapper
const opts = (w: W, i: number) =>
  w
    .findAll('select')
    [i].findAll('option')
    .map((o) => o.text())
const value = (w: W, i: number) => (w.findAll('select')[i].element as HTMLSelectElement).value
const submitBtn = (w: W) => w.get<HTMLButtonElement>('button[type="submit"]')

describe('ReserveSheet — 제약은 고를 수 없게 건다 (student-room.md §화면이 거는 제약)', () => {
  it('칩 8개 = 창, 첫 칩은 오늘, 빈 구간이 있는 첫 날이 골라져 있다', () => {
    const w = mount(ReserveSheet, { props: base })
    const chips = w.findAll('button.rs__chip')
    expect(chips).toHaveLength(8)
    expect(chips[0].text()).toContain('오늘')
    expect(chips[0].attributes('aria-checked')).toBe('true')
    expect(chips[1].attributes('aria-label')).toBe('10월 24일 토')
    expect(w.get('legend').text()).toContain('10월 23일 금')
  })

  it('구간을 고르면 시작은 5분 단위(오늘은 지금 이후만), 끝은 +15~+120·구간 끝까지, 기본 +60', async () => {
    const w = mount(ReserveSheet, { props: base })
    expect(w.findAll('label.rs__span .num').map((l) => l.text())).toEqual([
      '10:40 – 11:30',
      '16:00 – 21:00',
    ])
    expect(w.findAll('label.rs__span .rs__dur').map((l) => l.text())).toEqual(['50분', '5시간'])
    await w.findAll('input[type="radio"]')[0].setValue()
    expect(opts(w, 0)).toEqual(['10:45', '10:50', '10:55', '11:00', '11:05', '11:10', '11:15'])
    expect(opts(w, 1)).toEqual(['11:00', '11:05', '11:10', '11:15', '11:20', '11:25', '11:30'])
    expect(value(w, 0)).toBe(String(10 * 60 + 45))
    expect(value(w, 1)).toBe(String(11 * 60 + 30))
  })

  it('시작을 바꾸면 끝이 범위 밖일 때만 다시 잡는다', async () => {
    const w = mount(ReserveSheet, { props: base })
    await w.findAll('input[type="radio"]')[1].setValue()
    expect(value(w, 1)).toBe(String(17 * 60))
    await w.findAll('select')[0].setValue(String(16 * 60 + 30))
    expect(value(w, 1)).toBe(String(17 * 60))
    await w.findAll('select')[0].setValue(String(18 * 60))
    expect(value(w, 1)).toBe(String(19 * 60))
  })

  it('제출 — 서버 모양 그대로 한 번, 목적이 공백이면 못 보낸다', async () => {
    const w = mount(ReserveSheet, { props: base })
    await w.findAll('input[type="radio"]')[1].setValue()
    await w.get('.field__control').setValue('   ')
    expect(submitBtn(w).element.disabled).toBe(true)
    await w.get('.field__control').setValue('캡스톤 스터디')
    expect(submitBtn(w).element.disabled).toBe(false)
    expect(w.get('.rs__summary').text()).toBe('10월 23일 금 16:00–17:00')
    await w.get('form').trigger('submit')
    expect(w.emitted('submit')).toEqual([
      [{ date: '2026-10-23', s_h: 16, s_m: 0, e_h: 17, e_m: 0, subject: '캡스톤 스터디' }],
    ])
  })

  it('막는 이유 — 가득·3건·하루 상한, 버튼은 disabled (다 골라도)', async () => {
    const filled = async (props: Partial<{ myFutureCount: number; locked: boolean }>) => {
      const w = mount(ReserveSheet, { props: { ...base, ...props } })
      await w.findAll('input[type="radio"]')[1].setValue()
      await w.get('.field__control').setValue('스터디')
      return w
    }
    const cap = await filled({ myFutureCount: 3 })
    expect(cap.get('.rs__blocker').text()).toBe(CAP_TEXT)
    expect(submitBtn(cap).element.disabled).toBe(true)
    await cap.get('form').trigger('submit')
    expect(cap.emitted('submit')).toBeUndefined()
    const daily = await filled({ locked: true })
    expect(daily.get('.rs__blocker').text()).toBe(DAILY_TEXT)
    const full = mount(ReserveSheet, {
      props: { ...base, full: true, days: DAYS.map((d) => ({ ...d, spans: [] })) },
    })
    expect(full.get('.rs__blocker').text()).toBe(FULL_TEXT)
    expect(full.get('.rs__empty').text()).toBe(FULL_TEXT)
    expect(mount(ReserveSheet, { props: base }).find('.rs__blocker').exists()).toBe(false)
  })

  it('다른 날 칩 — 그 날의 구간, 빈 날은 문장', async () => {
    const w = mount(ReserveSheet, { props: base })
    await w.findAll('button.rs__chip')[1].trigger('click')
    expect(w.findAll('button.rs__chip')[1].attributes('aria-checked')).toBe('true')
    expect(w.get('.rs__empty').text()).toBe('이 날은 비어 있는 시간이 없어요')
    await w.findAll('button.rs__chip')[2].trigger('click')
    await w.findAll('input[type="radio"]')[0].setValue()
    expect(opts(w, 0)[0]).toBe('09:00')
  })

  it('재조회로 고른 구간이 사라지면 선택이 풀리고, 고른 날·입력은 그대로', async () => {
    const w = mount(ReserveSheet, { props: base })
    await w.findAll('button.rs__chip')[2].trigger('click')
    await w.findAll('input[type="radio"]')[0].setValue()
    await w.get('.field__control').setValue('스터디')
    expect(submitBtn(w).element.disabled).toBe(false)
    const next = DAYS.map((d) =>
      d.date === '2026-10-25' ? { ...d, spans: [{ from: '12:00', to: '21:00' }] } : d,
    )
    await w.setProps({ days: next })
    expect(w.findAll('button.rs__chip')[2].attributes('aria-checked')).toBe('true')
    expect(
      w.findAll('input[type="radio"]').some((r) => (r.element as HTMLInputElement).checked),
    ).toBe(false)
    expect(w.findAll('select')).toHaveLength(0)
    expect(submitBtn(w).element.disabled).toBe(true)
    expect((w.get('.field__control').element as HTMLInputElement).value).toBe('스터디')
  })

  it('submitting 이면 loading — 다시 누를 수 없다', async () => {
    const w = mount(ReserveSheet, { props: base })
    await w.findAll('input[type="radio"]')[1].setValue()
    await w.get('.field__control').setValue('스터디')
    await w.setProps({ submitting: true })
    expect(submitBtn(w).attributes('aria-busy')).toBe('true')
    await w.get('form').trigger('submit')
    expect(w.emitted('submit')).toBeUndefined()
  })
})
