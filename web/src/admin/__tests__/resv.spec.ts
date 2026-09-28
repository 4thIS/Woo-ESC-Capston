import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import PendingBlock from '@/admin/views/rooms/PendingBlock.vue'
import ResvBlock from '@/admin/views/rooms/ResvBlock.vue'
import { adminApi } from '@/api/admin'
import { roomsApi } from '@/api/rooms'
import { ApiError, MESSAGES } from '@/api/client'
import type { ResvAdminOut, ResvWithRoom, RoomOut } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/admin', () => ({
  adminApi: { approveResv: vi.fn(), rejectResv: vi.fn(), cancelResv: vi.fn() },
}))
vi.mock('@/api/rooms', () => ({ roomsApi: { deleteResv: vi.fn(), saveResv: vi.fn() } }))
const admin = vi.mocked(adminApi)
const rooms = vi.mocked(roomsApi)

const requester = { email: 's1@mjc.ac.kr', name: '김민준', student_no: '20231234' }
const P = (
  id: number,
  subject: string,
  requestedAt: string,
  date = '2026-09-27',
): ResvAdminOut => ({
  id,
  date,
  s_h: 10,
  s_m: 0,
  e_h: 12,
  e_m: 0,
  type: 6,
  subject,
  professor: '',
  status: 'requested',
  requested_at: new Date(requestedAt),
  decided_at: null,
  reject_reason: null,
  checked_in_at: null,
  cancelled_at: null,
  room_id: 11,
  building: '공학관',
  room: 401,
  requester,
  pushed_at: null,
})
const V = (o: Partial<ResvWithRoom>): ResvWithRoom => ({
  id: 7,
  room_id: 11,
  date: '2026-09-27',
  s_h: 16,
  s_m: 0,
  e_h: 17,
  e_m: 0,
  type: 5,
  subject: '신입생 OT',
  professor: '학생처',
  status: 'approved',
  requester: null,
  pushed_at: new Date(),
  ...o,
})
const roomList: RoomOut[] = [{ id: 11, building_id: 1, room: 401, units: 1, reservable: true }]

type Root = VueWrapper | DOMWrapper<Element>
const btn = (root: Root, text: string) => root.findAll('button').find((b) => b.text() === text)!
let w: VueWrapper
const dialog = (title: string) =>
  w.findAll('[role=dialog]').find((d) => d.get('h2').text() === title)

beforeEach(() => {
  // KST 2026-09-25(금) 12:00
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-09-25T03:00:00Z'))
  Object.values(admin).forEach((f) => f.mockReset())
  Object.values(rooms).forEach((f) => f.mockReset())
  for (const t of [...toasts.value]) dismissToast(t.id)
})
afterEach(() => vi.useRealTimers())

describe('신청 대기', () => {
  it('0건이면 블록 자체를 감춘다', () => {
    w = mount(PendingBlock, { props: { pending: [] } })
    expect(w.find('section').exists()).toBe(false)
  })

  it('오래된 신청 먼저, 신청자는 이름만 — 학번·메일은 툴팁', () => {
    w = mount(PendingBlock, {
      props: {
        pending: [
          P(2, '나중 신청', '2026-09-24T05:00:00Z'),
          P(1, '먼저 신청', '2026-09-24T01:00:00Z'),
        ],
      },
    })
    const rows = w.findAll('tbody tr')
    expect(rows[0].text()).toContain('먼저 신청')
    expect(rows[0].text()).toContain('공학관 401')
    expect(rows[0].get('[title]').attributes('title')).toBe('20231234 · s1@mjc.ac.kr')
    expect(w.text()).toContain('2건')
  })

  it('승인 — 문장 Toast 와 목록 새로 고침', async () => {
    admin.approveResv.mockResolvedValue(P(1, 'x', '2026-09-24T01:00:00Z'))
    w = mount(PendingBlock, { props: { pending: [P(1, '스터디', '2026-09-24T01:00:00Z')] } })
    await btn(w, '승인').trigger('click')
    await flushPromises()
    expect(admin.approveResv).toHaveBeenCalledWith(1)
    expect(toasts.value.at(-1)?.message).toBe('승인했습니다. 문 앞 화면에 나갑니다.')
    expect(w.emitted('changed')).toHaveLength(1)
  })

  it('409 — 다른 관리자가 먼저 처리: 문장·재조회, 버튼이 잠긴 채 남지 않는다', async () => {
    admin.approveResv.mockRejectedValue(
      new ApiError(409, MESSAGES[409], [], { detail: 'approved 상태에서는 불가' }),
    )
    w = mount(PendingBlock, {
      props: {
        pending: [P(1, '스터디', '2026-09-24T01:00:00Z'), P(2, '회의', '2026-09-24T02:00:00Z')],
      },
    })
    await btn(w.findAll('tbody tr')[0], '승인').trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)).toMatchObject({
      tone: 'danger',
      message: '이미 처리된 신청입니다.',
    })
    expect(w.emitted('changed')).toHaveLength(1)
    expect(w.findAll('button').every((b) => !(b.element as HTMLButtonElement).disabled)).toBe(true)
  })

  it('승인 시 겹침·용량 409 는 그 이유를 말한다', async () => {
    admin.approveResv.mockRejectedValue(
      new ApiError(409, MESSAGES[409], [], {
        detail: '이 강의실은 이번 주 예약이 가득 찼습니다(노드 용량 24)',
      }),
    )
    w = mount(PendingBlock, { props: { pending: [P(1, '스터디', '2026-09-24T01:00:00Z')] } })
    await btn(w, '승인').trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe(
      '이 강의실은 7일 안 예약이 가득 찼습니다(24건). 지난 예약을 정리하세요.',
    )
  })

  it('시작 시각이 지난 신청은 승인을 잠근다(툴팁) — 거절은 된다', async () => {
    // 지금 KST 09-25 12:00 — 오늘 10:00 신청은 지났다, 오늘 13:00 은 아직
    const past = { ...P(1, '지난 것', '2026-09-24T01:00:00Z', '2026-09-25'), s_h: 10 }
    const soon = { ...P(2, '곧', '2026-09-24T02:00:00Z', '2026-09-25'), s_h: 13 }
    w = mount(PendingBlock, { props: { pending: [past, soon] } })
    const row = (t: string) => w.findAll('tbody tr').find((r) => r.text().includes(t))!
    const ok = btn(row('지난 것'), '승인')
    expect(ok.attributes('disabled')).toBeDefined()
    expect(ok.attributes('title')).toBe('시작 시각이 지나 승인할 수 없습니다')
    expect(btn(row('지난 것'), '거절').attributes('disabled')).toBeUndefined()
    expect(btn(row('곧'), '승인').attributes('disabled')).toBeUndefined()
  })

  it('거절 — 사유가 없으면 잠기고, 사유를 보내면 닫힌다', async () => {
    admin.rejectResv.mockResolvedValue(P(1, 'x', '2026-09-24T01:00:00Z'))
    w = mount(PendingBlock, {
      props: { pending: [P(1, '스터디', '2026-09-24T01:00:00Z')] },
      global: { stubs: { teleport: true } },
    })
    await btn(w.find('tbody'), '거절').trigger('click')
    const d = dialog('예약 신청 거절')!
    expect((btn(d, '거절').element as HTMLButtonElement).disabled).toBe(true)
    await d.get('textarea').setValue('시험 기간입니다')
    // teleport 스텁이 다시 그리면 앞서 잡은 요소는 떨어져 나간다 — 다시 찾는다
    await btn(dialog('예약 신청 거절')!, '거절').trigger('click')
    await flushPromises()
    expect(admin.rejectResv).toHaveBeenCalledWith(1, '시험 기간입니다')
    expect(dialog('예약 신청 거절')).toBeUndefined()
    expect(toasts.value.at(-1)?.message).toBe('거절했습니다. 사유가 학생에게 보입니다.')
  })
})

describe('예약 블록', () => {
  async function mountBlock(resv: ResvWithRoom[], states = new Map()) {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/:p(.*)*', component: { render: () => null } }],
    })
    w = mount(ResvBlock, {
      props: { rooms: roomList, label: () => '401', resv, states, loading: false },
      global: { plugins: [router], stubs: { teleport: true } },
    })
    await flushPromises()
  }

  it('approved 만 — 신청자·학번은 학생 신청만, 관리자가 넣은 것은 —', async () => {
    await mountBlock([
      V({ id: 1 }),
      V({ id: 2, subject: '스터디', requester, professor: '' }),
      V({ id: 3, subject: '대기중', status: 'requested', requester }),
      V({ id: 4, subject: '거절됨', status: 'rejected', requester }),
    ])
    const rows = w.findAll('tbody tr')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('신입생 OT')
    expect(rows[0].findAll('td')[6].text()).toBe('—')
    expect(rows[1].findAll('td')[6].text()).toBe('김민준')
    expect(rows[1].findAll('td')[7].text()).toBe('20231234')
  })

  it('창 밖·노드에 안 간 예약은 예정 배지 (툴팁) — 추적 중이면 그 점', async () => {
    await mountBlock(
      [V({ id: 1, date: '2026-10-05', pushed_at: null }), V({ id: 2, subject: '방금 저장' })],
      new Map([['r2', 'queued']]),
    )
    // 날짜순 — 9/27(방금 저장) 이 10/5 보다 먼저
    const rows = w.findAll('tbody tr')
    expect(rows[0].get('.dot').attributes('title')).toBe('대기')
    // 유형 칸의 TypeBadge 도 .badge — 작업 칸의 것을 본다
    const badge = rows[1].get('.rowdot .badge')
    expect(badge.text()).toBe('예정')
    expect(badge.attributes('title')).toBe('7일 이내로 들어오면 자동 전송됩니다')
  })

  it('학생 예약은 지우지 않고 취소 — 관리자 예약은 삭제', async () => {
    admin.cancelResv.mockResolvedValue(P(2, 'x', '2026-09-24T01:00:00Z'))
    rooms.deleteResv.mockResolvedValue({ outbox_ids: [], id: null })
    await mountBlock([V({ id: 1 }), V({ id: 2, subject: '스터디', requester })])
    const rows = w.findAll('tbody tr')
    expect(rows[1].findAll('button').map((b) => b.text())).toEqual(['취소'])
    await btn(rows[1], '취소').trigger('click')
    const c = dialog('예약 취소')!
    expect(c.text()).toContain('김민준 학생 화면에 취소됨으로 보입니다.')
    await btn(c, '예약 취소').trigger('click')
    await flushPromises()
    expect(admin.cancelResv).toHaveBeenCalledWith(2)
    await btn(w.findAll('tbody tr')[0], '삭제').trigger('click')
    await btn(dialog('예약 삭제')!, '삭제').trigger('click')
    await flushPromises()
    expect(rooms.deleteResv).toHaveBeenCalledWith(11, 1)
  })
})
