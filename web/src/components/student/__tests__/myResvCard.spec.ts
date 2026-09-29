import { describe, expect, it } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import type { ResvMineOut } from '@/api/types'
import MyResvCard from '../MyResvCard.vue'

const NOW = new Date('2026-10-23T01:42:00Z') // KST 금 10:42
const resv = (over: Partial<ResvMineOut> = {}): ResvMineOut => ({
  id: 7,
  date: '2026-10-23',
  s_h: 10,
  s_m: 50,
  e_h: 12,
  e_m: 0,
  type: 6,
  subject: '캡스톤 스터디',
  professor: '',
  status: 'approved',
  requested_at: null,
  decided_at: null,
  reject_reason: null,
  checked_in_at: null,
  checked_out_at: null,
  cancelled_at: null,
  room_id: 11,
  building: '공학관',
  room: 401,
  ...over,
})
const buttons = (w: VueWrapper) => w.findAll('button').map((b) => b.text())

describe('MyResvCard', () => {
  it('승인 · 창 안(시작 뒤) — 체크인(primary)만, 시작이 지나 취소는 없다, 읽는 이름에 방·시각', async () => {
    const w = mount(MyResvCard, { props: { resv: resv({ s_m: 40 }), now: NOW } })
    expect(w.get('article').attributes('aria-label')).toBe('공학관 401호 10/23 금 10:40–12:00')
    expect(w.get('.badge').text()).toBe('승인됨')
    expect(buttons(w)).toEqual(['체크인'])
    expect(w.findAll('button')[0].classes()).toContain('btn--primary')
    await w.findAll('button')[0].trigger('click')
    expect(w.emitted('checkin')).toHaveLength(1)
  })

  it('승인 · 시작 전 — 체크인은 잠기고 시작 시각부터, 취소는 된다', async () => {
    const w = mount(MyResvCard, { props: { resv: resv(), now: NOW } }) // 10:50 시작, 지금 10:42
    expect(buttons(w)).toEqual(['체크인', '취소'])
    expect((w.findAll('button')[0].element as HTMLButtonElement).disabled).toBe(true)
    expect(w.get('.mc__hint').text()).toBe('10:50부터 체크인할 수 있어요')
    await w.findAll('button')[1].trigger('click')
    expect(w.emitted('cancel')).toHaveLength(1)
  })

  it('체크인하고 사용 중 — 조기 퇴실만, 누르면 알린다', async () => {
    const inUse = resv({ s_m: 0, checked_in_at: new Date('2026-10-23T01:01:00Z') }) // 10:00–12:00, 10:01 체크인
    const w = mount(MyResvCard, { props: { resv: inUse, now: NOW } })
    expect(buttons(w)).toEqual(['조기 퇴실']) // 시작이 지나 취소는 없다
    // 카드 오른쪽 위(머리 줄)에 빨간 버튼 (사용자 결정)
    const btn = w.get('.mc__head button')
    expect(btn.text()).toBe('조기 퇴실')
    expect(btn.classes()).toContain('btn--danger')
    await w.findAll('button')[0].trigger('click')
    expect(w.emitted('checkout')).toHaveLength(1)
  })

  it('일찍 체크인한 시작 전 — 취소 대신 조기 퇴실', () => {
    const early = resv({ s_h: 10, s_m: 50, checked_in_at: new Date('2026-10-23T01:41:00Z') })
    const w = mount(MyResvCard, { props: { resv: early, now: NOW } })
    expect(buttons(w)).toEqual(['조기 퇴실'])
  })

  it('퇴실했으면 퇴실 시각 한 줄만 — 체크인 줄·버튼이 다시 생기지 않는다', () => {
    const out = resv({
      s_m: 0,
      e_h: 10,
      e_m: 23,
      checked_in_at: new Date('2026-10-23T01:01:00Z'),
      checked_out_at: new Date('2026-10-23T01:23:00Z'),
    })
    const w = mount(MyResvCard, { props: { resv: out, now: NOW } })
    expect(w.text()).toContain('✓ 10:23 퇴실')
    expect(w.text()).not.toContain('체크인')
    expect(w.findAll('button')).toHaveLength(0)
  })

  it('퇴실 중 — 버튼이 loading, 다른 쓰기 중이면 disabled', () => {
    const inUse = resv({ s_m: 0, checked_in_at: new Date('2026-10-23T01:01:00Z') })
    const busy = mount(MyResvCard, { props: { resv: inUse, now: NOW, busy: 'checkout' } })
    expect(busy.get('button').attributes('aria-busy')).toBe('true')
  })

  it('창 밖 — 숨기지 않고 disabled + 언제부터', () => {
    const w = mount(MyResvCard, { props: { resv: resv({ s_h: 11, s_m: 0 }), now: NOW } })
    const ci = w.findAll('button')[0]
    expect(ci.text()).toBe('체크인')
    expect((ci.element as HTMLButtonElement).disabled).toBe(true)
    expect(ci.classes()).toContain('btn--secondary')
    expect(w.get('.mc__hint').text()).toBe('11:00부터 체크인할 수 있어요')
  })

  it('체크인했으면 버튼 자리가 시각으로, 시작 뒤엔 취소 대신 조기 퇴실만', () => {
    const w = mount(MyResvCard, {
      props: {
        resv: resv({ s_h: 10, s_m: 30, checked_in_at: new Date('2026-10-23T01:32:00Z') }),
        now: NOW,
      },
    })
    expect(w.get('.mc__done').text()).toBe('✓ 10:32 체크인')
    expect(buttons(w)).toEqual(['조기 퇴실']) // 사용 중(10:30–12:00) — early-checkout spec
  })

  it('대기중 — 신청 취소만, 체크인 없음', () => {
    const w = mount(MyResvCard, { props: { resv: resv({ status: 'requested' }), now: NOW } })
    expect(w.get('.badge').text()).toBe('대기중')
    expect(buttons(w)).toEqual(['신청 취소'])
  })

  it('거절됨 — 사유를 본문에, 만료됨 — 한 줄, 끝난 승인 — 버튼 없음', () => {
    const rej = mount(MyResvCard, {
      props: {
        resv: resv({ status: 'rejected', reject_reason: '학과 행사와 겹칩니다' }),
        now: NOW,
      },
    })
    expect(rej.get('.mc__note').text()).toBe('사유: 학과 행사와 겹칩니다')
    expect(rej.findAll('button')).toHaveLength(0)
    const exp = mount(MyResvCard, { props: { resv: resv({ status: 'expired' }), now: NOW } })
    expect(exp.get('.mc__note').text()).toBe('승인 전에 시간이 지났어요')
    const past = mount(MyResvCard, {
      props: { resv: resv({ s_h: 9, s_m: 0, e_h: 10, e_m: 0 }), now: NOW },
    })
    expect(past.findAll('button')).toHaveLength(0)
    expect(past.find('.mc__hint').exists()).toBe(false)
  })

  it('처리 중(busy) — 두 버튼 다 잠기고 누른 쪽만 loading', () => {
    const w = mount(MyResvCard, { props: { resv: resv(), now: NOW, busy: 'cancel' } })
    const [ci, cancel] = w.findAll('button')
    expect((ci.element as HTMLButtonElement).disabled).toBe(true)
    expect(cancel.attributes('aria-busy')).toBe('true')
  })
})
