import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import ModemPanel from '@/admin/views/nodes/ModemPanel.vue'
import { loraApi } from '@/api/lora'
import { ApiError, MESSAGES } from '@/api/client'
import type { ModemOut } from '@/api/types'
import { dismissToast, toasts } from '@/components/ui/toast'

vi.mock('@/api/lora', () => ({ loraApi: { registerModem: vi.fn(), rotateToken: vi.fn() } }))
const lora = vi.mocked(loraApi, true)

const m = (over: Partial<ModemOut> = {}): ModemOut => ({
  modem_id: 'gonghak-01',
  agent_ver: '0.4.1',
  modem_fw: '1.2.0',
  last_seen_at: new Date(),
  connected: true,
  school_id: 1,
  ...over,
})
const mountPanel = (modems?: ModemOut[], loading = false) =>
  mount(ModemPanel, { props: { modems, loading }, global: { stubs: { teleport: true } } })
const button = (w: VueWrapper, text: string) => w.findAll('button').find((b) => b.text() === text)!
async function issueToken(w: VueWrapper) {
  lora.registerModem.mockResolvedValue({ modem_id: 'gonghak-02', token: 'tok-abc' })
  ;(w.vm as unknown as { openRegister(): void }).openRegister()
  await nextTick()
  await w.get('[role="dialog"] input').setValue('gonghak-02')
  await button(w, '등록').trigger('click')
  await flushPromises()
}

beforeEach(() => {
  toasts.value.forEach((t) => dismissToast(t.id))
  lora.registerModem.mockReset()
  lora.rotateToken.mockReset()
})

describe('ModemPanel', () => {
  it('카드 — 연결됨(solid)/끊김(danger), 접속 기록 없음, 토큰은 어디에도 없다', () => {
    const w = mountPanel([
      m(),
      m({ modem_id: 'sahoe-01', connected: false, last_seen_at: null, agent_ver: null }),
    ])
    const cards = w.findAll('li.modem')
    expect(cards[0].text()).toContain('gonghak-01')
    expect(cards[0].text()).toContain('agent 0.4.1 · 방금')
    expect(cards[0].get('.badge').text()).toBe('연결됨')
    expect(cards[1].get('.badge--danger').text()).toBe('끊김')
    expect(cards[1].text()).toContain('agent — · 접속 기록 없음')
    expect(w.find('code.token').exists()).toBe(false)
  })

  it('로딩 중 첫 조회 — Skeleton 2개', () => {
    const w = mountPanel(undefined, true)
    expect(w.findAll('.sk')).toHaveLength(2)
  })

  it('첫 조회 실패(로딩 아님, modems undefined) — "없음"으로 오독되지 않게', () => {
    const w = mountPanel(undefined, false)
    expect(w.text()).toContain('불러오지 못했습니다')
    expect(w.text()).not.toContain('등록된 모뎀Pi가 없습니다')
  })

  it('0대면 빈 상태 + 등록 버튼이 등록 Modal 을 연다', async () => {
    const w = mountPanel([])
    expect(w.text()).toContain('등록된 모뎀Pi가 없습니다')
    await button(w, '모뎀Pi 등록').trigger('click')
    expect(w.get('[role="dialog"]').text()).toContain('모뎀Pi ID')
  })

  it('등록 — 형식이 틀리면 막고, 성공하면 토큰을 한 번 보여 주고 changed', async () => {
    const w = mountPanel([m()])
    ;(w.vm as unknown as { openRegister(): void }).openRegister()
    await nextTick()
    await w.get('[role="dialog"] input').setValue('Gonghak 02')
    expect(w.text()).toContain('영문 소문자·숫자·하이픈만, 32자 이내로 적어 주세요.')
    expect(button(w, '등록').attributes('disabled')).toBeDefined()
    await issueToken(w)
    expect(lora.registerModem).toHaveBeenCalledWith('gonghak-02')
    expect(w.get('code.token').text()).toBe('tok-abc')
    expect(w.text()).toContain('이 창을 닫으면 다시 볼 수 없습니다.')
    expect(w.emitted('changed')).toHaveLength(1)
  })

  it('이미 있는 ID(400) — 입력 오류로, Modal 은 그대로', async () => {
    lora.registerModem.mockRejectedValue(new ApiError(400, MESSAGES[400]))
    const w = mountPanel([m()])
    ;(w.vm as unknown as { openRegister(): void }).openRegister()
    await nextTick()
    await w.get('[role="dialog"] input').setValue('gonghak-01')
    await button(w, '등록').trigger('click')
    await flushPromises()
    expect(w.get('[role="dialog"]').text()).toContain('이미 등록된 모뎀Pi ID입니다.')
    expect(w.find('code.token').exists()).toBe(false)
    await w.get('[role="dialog"] input').setValue('gonghak-09')
    expect(w.get('[role="dialog"]').text()).not.toContain('이미 등록된 모뎀Pi ID입니다.')
  })

  it('토큰 재발급 — 확인 Modal 뒤에만 호출, 새 토큰 표시', async () => {
    lora.rotateToken.mockResolvedValue({ modem_id: 'gonghak-01', token: 'tok-new' })
    const w = mountPanel([m()])
    await button(w, '토큰 재발급').trigger('click')
    expect(lora.rotateToken).not.toHaveBeenCalled()
    expect(w.get('[role="dialog"]').text()).toContain(
      '기존 토큰이 즉시 무효가 되어 이 모뎀Pi가 끊깁니다',
    )
    await button(w, '재발급').trigger('click')
    await flushPromises()
    expect(lora.rotateToken).toHaveBeenCalledWith('gonghak-01')
    expect(w.get('code.token').text()).toBe('tok-new')
    // 재발급은 기존 토큰을 즉시 끊는다 — 부모가 다시 읽지 않으면 연결됨이 30초간 거짓으로 남는다
    expect(w.emitted('changed')).toHaveLength(1)
  })

  it('재발급 404 — 안내 + changed, Modal 닫힘', async () => {
    lora.rotateToken.mockRejectedValue(new ApiError(404, MESSAGES[404]))
    const w = mountPanel([m()])
    await button(w, '토큰 재발급').trigger('click')
    await button(w, '재발급').trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe('이미 삭제된 모뎀Pi입니다. 목록을 새로 불러옵니다.')
    expect(w.emitted('changed')).toHaveLength(1)
    expect(w.find('[role="dialog"]').exists()).toBe(false)
  })

  it('토큰 창은 Esc·배경으로 닫히지 않는다 — 닫기 버튼만 (Review Focus 5)', async () => {
    const w = mountPanel([m()])
    await issueToken(w)
    await w.get('[role="dialog"]').trigger('keydown', { key: 'Escape' })
    expect(w.find('code.token').exists()).toBe(true)
    await w.get('.modal__backdrop').trigger('mousedown')
    expect(w.find('code.token').exists()).toBe(true)
    await button(w, '닫기').trigger('click')
    expect(w.find('code.token').exists()).toBe(false)
  })

  it('복사 — 클립보드에 쓰고 알린다, 실패하면 직접 복사 안내', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    const w = mountPanel([m()])
    await issueToken(w)
    await button(w, '복사').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('tok-abc')
    expect(toasts.value.at(-1)?.message).toBe('복사했습니다.')
    writeText.mockRejectedValueOnce(new Error('denied'))
    await button(w, '복사').trigger('click')
    await flushPromises()
    expect(toasts.value.at(-1)?.message).toBe(
      '복사하지 못했습니다. 토큰을 직접 선택해 복사해 주세요.',
    )
  })
})
