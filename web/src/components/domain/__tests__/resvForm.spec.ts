import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ResvForm from '@/components/domain/ResvForm.vue'
import { resvErrors, type ResvDraft } from '@/components/domain/resvForm'
import { roomsApi } from '@/api/rooms'
import { ApiError, MESSAGES } from '@/api/client'
import type { ResvWithRoom, RoomOut } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/rooms', () => ({ roomsApi: { saveResv: vi.fn() } }))
const api = vi.mocked(roomsApi)

const rooms: RoomOut[] = [{ id: 11, building_id: 1, room: 401, units: 1, reservable: true }]
const resv = (o: Partial<ResvWithRoom> = {}): ResvWithRoom => ({
  id: 7,
  room_id: 11,
  date: '2026-09-26',
  s_h: 10,
  s_m: 0,
  e_h: 12,
  e_m: 0,
  type: 5,
  subject: '신입생 OT',
  professor: '학생처',
  status: 'approved',
  requester: null,
  pushed_at: null,
  ...o,
})
const draft = (o: Partial<ResvDraft> = {}): ResvDraft => ({
  roomId: 11,
  date: '2026-09-26',
  start: '11:00',
  end: '12:00',
  type: 5,
  subject: '',
  professor: '',
  ...o,
})

// 저장 버튼은 form 속성으로 폼에 붙는다 — 문서 안에 있어야 이어진다(버튼 클릭 = 폼 submit)
let w: VueWrapper
async function mountForm(props: Record<string, unknown> = {}) {
  w = mount(ResvForm, {
    props: { open: true, rooms, preset: { room_id: 11 }, ...props },
    global: { stubs: { teleport: true } },
    attachTo: document.body,
  })
  await flushPromises()
}
const field = (label: string) =>
  w
    .findAll('.field, .sel')
    .find(
      (f) => f.find('label').exists() && f.get('label').text().replace('*', '').trim() === label,
    )!
const control = (label: string) => field(label).get('input, select')
const save = () =>
  w
    .findAll('button')
    .find((b) => b.text() === '저장')!
    .trigger('click')

beforeEach(() => {
  // KST 2026-09-25(금) 12:00
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-09-25T03:00:00Z'))
  api.saveResv.mockReset().mockResolvedValue({ outbox_ids: [5], id: 12 })
  for (const t of [...toasts.value]) dismissToast(t.id)
})
afterEach(() => {
  w?.unmount()
  vi.useRealTimers()
})

describe('resvErrors', () => {
  it('오늘 이전 날짜·종료 ≤ 시작은 막는다', () => {
    expect(resvErrors(draft({ date: '2026-09-24' }), [], null, '2026-09-25').date).toBe(
      '오늘 이전 날짜에는 만들 수 없습니다',
    )
    expect(resvErrors(draft({ end: '11:00' }), [], null, '2026-09-25').end).toBe(
      '종료는 시작보다 늦어야 합니다 (자정을 넘기지 않습니다)',
    )
  })
  it('같은 방·같은 날 승인·신청 예약과 겹치면 막는다 — 거절·취소·자기 자신은 아니다', () => {
    expect(resvErrors(draft(), [resv()], null, '2026-09-25').end).toBe(
      '겹칩니다: 10:00–12:00 신입생 OT',
    )
    expect(resvErrors(draft(), [resv({ status: 'requested' })], null, '2026-09-25').end).toBe(
      '겹칩니다: 10:00–12:00 신청 · 신입생 OT',
    )
    expect(resvErrors(draft(), [resv({ status: 'rejected' })], null, '2026-09-25')).toEqual({})
    expect(resvErrors(draft(), [resv()], 7, '2026-09-25')).toEqual({})
  })
})

describe('ResvForm', () => {
  it('추가 — id 없이 보내고(서버 채번), 응답 id 로 행 키, 요일은 날짜에서 읽기 전용', async () => {
    await mountForm()
    await control('날짜').setValue('2026-09-26')
    expect((control('요일').element as HTMLInputElement).value).toBe('토')
    expect(control('요일').attributes('readonly')).toBeDefined()
    await control('시작').setValue('16:00')
    await control('종료').setValue('17:00')
    await control('사용 목적').setValue('신입생 OT')
    await save()
    await flushPromises()
    const body = api.saveResv.mock.calls[0][1]
    expect(api.saveResv.mock.calls[0][0]).toBe(11)
    expect(body).not.toHaveProperty('id')
    expect(body).toMatchObject({
      date: '2026-09-26',
      s_h: 16,
      e_h: 17,
      subject: '신입생 OT',
      type: 5,
    })
    expect(w.emitted('saved')![0]).toEqual([{ roomId: 11, key: 'r12', outboxIds: [5] }])
    expect(toasts.value.at(-1)?.message).toBe('저장했습니다.')
  })

  it('7일 밖이면 저장 전에 hint 로 알리고 막지 않는다 — 빈 outbox_ids 는 실패가 아니다', async () => {
    api.saveResv.mockResolvedValue({ outbox_ids: [], id: 13 })
    await mountForm()
    await control('날짜').setValue('2026-10-05')
    expect(field('날짜').text()).toContain('7일 이내로 들어오면 자동 전송됩니다')
    await save()
    await flushPromises()
    expect(api.saveResv).toHaveBeenCalledTimes(1)
    expect(toasts.value.at(-1)).toMatchObject({
      tone: 'neutral',
      message: '저장했습니다. 7일 이내로 들어오면 자동 전송됩니다.',
    })
  })

  it('지난 날짜는 막는다', async () => {
    await mountForm()
    await control('날짜').setValue('2026-09-24')
    await save()
    await flushPromises()
    expect(api.saveResv).not.toHaveBeenCalled()
    expect(field('날짜').text()).toContain('오늘 이전 날짜에는 만들 수 없습니다')
  })

  it('수정 — 그 id 로, 강의실은 잠근다 (다른 방은 409)', async () => {
    await mountForm({ mode: 'edit', value: resv() })
    expect((control('강의실').element as HTMLSelectElement).disabled).toBe(true)
    expect(w.text()).toContain('다른 강의실로 옮기려면 지우고 다시 만드세요')
    await control('사용 목적').setValue('신입생 OT 2부')
    await save()
    await flushPromises()
    expect(api.saveResv.mock.calls[0][1]).toMatchObject({ id: 7, subject: '신입생 OT 2부' })
  })

  it('409 가득 참 — 사람 문장, 목록 새로 고침, 폼은 열어 둔다', async () => {
    api.saveResv.mockRejectedValue(
      new ApiError(409, MESSAGES[409], [], {
        detail: '이 강의실은 이번 주 예약이 가득 찼습니다(노드 용량 24)',
      }),
    )
    await mountForm()
    await control('날짜').setValue('2026-09-26')
    await save()
    await flushPromises()
    expect(toasts.value.at(-1)).toMatchObject({
      tone: 'danger',
      message: '이 강의실은 7일 안 예약이 가득 찼습니다(24건). 지난 예약을 정리하세요.',
    })
    expect(w.emitted('stale')).toHaveLength(1)
    expect(w.emitted('close')).toBeUndefined()
  })
})
