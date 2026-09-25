import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import UsersView from '@/admin/views/UsersView.vue'
import { matchUser, sortUsers } from '@/admin/usersView'
import { usersApi } from '@/api/users'
import { ApiError, MESSAGES } from '@/api/client'
import type { UserOut } from '@/api/types'
import { toasts, dismissToast } from '@/components/ui/toast'

vi.mock('@/api/users', () => ({
  usersApi: { list: vi.fn(), approve: vi.fn(), reject: vi.fn(), disable: vi.fn(), enable: vi.fn() },
}))
vi.mock('@/admin/pending', () => ({ refreshPending: vi.fn() }))
const api = vi.mocked(usersApi)

const u = (over: Partial<UserOut>): UserOut => ({
  email: 's@wsu.ac.kr',
  school_id: 1,
  role: 'student',
  status: 'pending_approval',
  name: '김민준',
  student_no: '20231234',
  created_at: new Date('2026-09-25T00:00:00Z'),
  approved_at: null,
  ...over,
})
const stubs = { teleport: true }
async function mountView() {
  const w = mount(UsersView, { global: { stubs } })
  await flushPromises()
  return w
}
const buttonByText = (w: ReturnType<typeof mount>, text: string) =>
  w.findAll('button').find((b) => b.text() === text)!

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset())
  for (const t of [...toasts.value]) dismissToast(t.id)
})

describe('정렬·검색', () => {
  it('대기 건은 오래된 순으로 먼저, 나머지는 최신순', () => {
    const d = (s: string) => new Date(`2026-09-${s}T00:00:00Z`)
    const out = sortUsers([
      u({ email: 'a', status: 'active', created_at: d('01') }),
      u({ email: 'p2', created_at: d('20') }),
      u({ email: 'b', status: 'active', created_at: d('10') }),
      u({ email: 'p1', created_at: d('05') }),
    ])
    expect(out.map((x) => x.email)).toEqual(['p1', 'p2', 'b', 'a'])
  })
  it('이름·학번·메일 부분 일치, 대소문자 무시', () => {
    const x = u({ name: '이정민', student_no: 'AB-12', email: 'Lee@wsu.ac.kr' })
    expect(matchUser(x, '정민')).toBe(true)
    expect(matchUser(x, 'ab-1')).toBe(true)
    expect(matchUser(x, 'lee@')).toBe(true)
    expect(matchUser(x, '김')).toBe(false)
    expect(matchUser(u({ student_no: null }), '')).toBe(true)
  })
})

describe('UsersView', () => {
  it('기본 필터는 승인 대기, 대기 행에 승인·거절', async () => {
    api.list.mockResolvedValue([u({})])
    const w = await mountView()
    expect(api.list).toHaveBeenCalledWith('pending_approval')
    expect(w.text()).toContain('대기중')
    expect(buttonByText(w, '승인')).toBeTruthy()
    expect(buttonByText(w, '거절')).toBeTruthy()
  })

  it('승인은 확인 없이 바로, 성공 Toast 는 발송을 보장하지 않는 문구', async () => {
    api.list.mockResolvedValue([u({})])
    api.approve.mockResolvedValue(u({ status: 'active' }))
    const w = await mountView()
    await buttonByText(w, '승인').trigger('click')
    await flushPromises()
    expect(api.approve).toHaveBeenCalledWith('s@wsu.ac.kr')
    expect(w.find('[role="dialog"]').exists()).toBe(false)
    expect(toasts.value.at(-1)?.message).toBe('승인했습니다. 학생에게 메일이 갑니다.')
    expect(api.list).toHaveBeenCalledTimes(2) // 새로고침
  })

  it('409 → 이미 처리된 신청 + 새로고침, 버튼이 잠긴 채 남지 않는다 (Review Focus 4)', async () => {
    api.list.mockResolvedValue([u({})])
    api.approve.mockRejectedValue(new ApiError(409, MESSAGES[409]))
    const w = await mountView()
    await buttonByText(w, '승인').trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe('이미 처리된 신청입니다')
    expect(api.list).toHaveBeenCalledTimes(2)
    expect((buttonByText(w, '승인').element as HTMLButtonElement).disabled).toBe(false)
  })

  it('네트워크 오류 → danger Toast + 재시도', async () => {
    api.list.mockResolvedValue([u({})])
    api.approve.mockRejectedValueOnce(new ApiError(0, MESSAGES[0]))
    api.approve.mockResolvedValueOnce(u({ status: 'active' }))
    const w = await mountView()
    await buttonByText(w, '승인').trigger('click')
    await flushPromises()
    const t = toasts.value.at(-1)!
    expect(t.tone).toBe('danger')
    t.action!.onClick()
    await flushPromises()
    expect(api.approve).toHaveBeenCalledTimes(2)
  })

  it('거절 — 사유 없이는 못 보낸다, 사유는 그대로 간다', async () => {
    api.list.mockResolvedValue([u({})])
    api.reject.mockResolvedValue(u({ status: 'rejected' }))
    const w = await mountView()
    await buttonByText(w, '거절').trigger('click')
    // teleport 스텁은 갱신마다 슬롯을 다시 그린다 — dialog 를 매번 다시 찾는다 (실제 Teleport 는 유지)
    const dialog = () => w.get('[role="dialog"]')
    const submit = () =>
      dialog()
        .findAll('button')
        .find((b) => b.text() === '거절')!
    expect((submit().element as HTMLButtonElement).disabled).toBe(true)
    await dialog().get('textarea').setValue('  학번이 잘못되었습니다  ')
    expect((submit().element as HTMLButtonElement).disabled).toBe(false)
    await submit().trigger('click')
    await flushPromises()
    expect(api.reject).toHaveBeenCalledWith('s@wsu.ac.kr', '학번이 잘못되었습니다')
    expect(w.find('[role="dialog"]').exists()).toBe(false)
  })

  it('정지는 확인 Modal, 관리자 행은 CLI 에서만 변경', async () => {
    api.list.mockResolvedValue([
      u({ email: 'a@wsu.ac.kr', status: 'active' }),
      u({ email: 'admin@wsu.ac.kr', role: 'admin', status: 'active', student_no: null }),
    ])
    api.disable.mockResolvedValue(u({ status: 'disabled' }))
    const w = await mountView()
    expect(w.text()).toContain('CLI 에서만 변경')
    expect(w.findAll('button').filter((b) => b.text() === '정지')).toHaveLength(1)
    await buttonByText(w, '정지').trigger('click')
    expect(w.get('[role="dialog"]').text()).toContain('로그인이 즉시 끊깁니다')
    const confirm = w
      .get('[role="dialog"]')
      .findAll('button')
      .find((b) => b.text() === '정지')!
    await confirm.trigger('click')
    await flushPromises()
    expect(api.disable).toHaveBeenCalledWith('a@wsu.ac.kr')
  })

  it('정지된 회원은 해제(확인 없음), 정지됨 배지는 적색', async () => {
    api.list.mockResolvedValue([u({ status: 'disabled' })])
    api.enable.mockResolvedValue(u({ status: 'active' }))
    const w = await mountView()
    expect(w.get('.badge--danger').text()).toBe('정지됨')
    await buttonByText(w, '해제').trigger('click')
    await flushPromises()
    expect(api.enable).toHaveBeenCalledWith('s@wsu.ac.kr')
  })

  it('필터를 바꾸면 그 상태로 다시 부른다, 전체는 status 없이', async () => {
    api.list.mockResolvedValue([])
    const w = await mountView()
    await w.get('select').setValue('')
    await flushPromises()
    expect(api.list).toHaveBeenLastCalledWith(undefined)
    expect(w.text()).toContain('아직 가입한 회원이 없습니다')
  })

  it('대기 0건은 평소 상태 — 버튼 없는 빈 문구', async () => {
    api.list.mockResolvedValue([])
    const w = await mountView()
    expect(w.text()).toContain('승인을 기다리는 신청이 없습니다')
    expect(w.find('.empty button').exists()).toBe(false)
  })

  async function openRejectWith(reason: string) {
    api.list.mockResolvedValue([u({})])
    const w = await mountView()
    await buttonByText(w, '거절').trigger('click')
    if (reason) await w.get('[role="dialog"] textarea').setValue(reason)
    return w
  }
  const dialogButton = (w: ReturnType<typeof mount>, text: string) =>
    w
      .get('[role="dialog"]')
      .findAll('button')
      .find((b) => b.text() === text)!

  it('거절 — 409·404 가 아닌 오류면 Modal 이 남는다', async () => {
    api.reject.mockRejectedValue(new ApiError(0, MESSAGES[0]))
    const w = await openRejectWith('사유')
    await dialogButton(w, '거절').trigger('click')
    await flushPromises()
    expect(w.find('[role="dialog"]').exists()).toBe(true)
    expect(toasts.value.at(-1)?.tone).toBe('danger')
  })

  it.each([409, 404])('거절 — %i 이면 Modal 을 닫는다', async (status) => {
    api.reject.mockRejectedValue(new ApiError(status, MESSAGES[status] ?? 'x'))
    const w = await openRejectWith('사유')
    await dialogButton(w, '거절').trigger('click')
    await flushPromises()
    expect(w.find('[role="dialog"]').exists()).toBe(false)
  })

  it('거절 — 사유를 쓴 뒤에는 배경·Esc 로 닫히지 않는다', async () => {
    const w = await openRejectWith('사유')
    await w.get('.modal__backdrop').trigger('mousedown')
    await w.get('[role="dialog"]').trigger('keydown', { key: 'Escape' })
    expect(w.find('[role="dialog"]').exists()).toBe(true)
    expect((w.get('[role="dialog"] textarea').element as HTMLTextAreaElement).value).toBe('사유')
  })

  it('거절 실패 Toast 의 재시도는 성공하면 Modal 을 닫는다', async () => {
    api.reject.mockRejectedValueOnce(new ApiError(0, MESSAGES[0]))
    api.reject.mockResolvedValueOnce(u({ status: 'rejected' }))
    const w = await openRejectWith('사유')
    await dialogButton(w, '거절').trigger('click')
    await flushPromises()
    toasts.value.at(-1)!.action!.onClick()
    await flushPromises()
    expect(api.reject).toHaveBeenCalledTimes(2)
    expect(w.find('[role="dialog"]').exists()).toBe(false)
  })

  it('정지 — 성공하면 Modal 을 닫는다', async () => {
    api.list.mockResolvedValue([u({ status: 'active' })])
    api.disable.mockResolvedValue(u({ status: 'disabled' }))
    const w = await mountView()
    await buttonByText(w, '정지').trigger('click')
    await dialogButton(w, '정지').trigger('click')
    await flushPromises()
    expect(w.find('[role="dialog"]').exists()).toBe(false)
  })

  it('승인 뒤 새 목록이 올 때까지 행 버튼이 잠겨 있다', async () => {
    let land!: (v: UserOut[]) => void
    api.list.mockResolvedValueOnce([u({})])
    api.list.mockReturnValueOnce(new Promise<UserOut[]>((r) => (land = r)))
    api.approve.mockResolvedValue(u({ status: 'active' }))
    const w = await mountView()
    await buttonByText(w, '승인').trigger('click')
    await flushPromises()
    expect((buttonByText(w, '승인').element as HTMLButtonElement).disabled).toBe(true)
    expect((buttonByText(w, '거절').element as HTMLButtonElement).disabled).toBe(true)
    land([u({ email: 'o@wsu.ac.kr' })])
    await flushPromises()
    expect((buttonByText(w, '승인').element as HTMLButtonElement).disabled).toBe(false)
  })

  it('필터를 바꿔 새 목록을 부르는 동안 옛 행의 버튼은 잠긴다', async () => {
    api.list.mockResolvedValueOnce([u({})])
    api.list.mockReturnValueOnce(new Promise<UserOut[]>(() => {}))
    const w = await mountView()
    await w.get('select').setValue('')
    await flushPromises()
    expect((buttonByText(w, '승인').element as HTMLButtonElement).disabled).toBe(true)
  })
})
