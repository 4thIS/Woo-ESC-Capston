import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { useAssistant } from '@/admin/assistant/useAssistant'
import { DevRuleRunner } from '@/admin/assistant/dev/devRule'
import { createFakeAssistantApi } from '@/admin/assistant/dev/fakeServer'
import { STUB_MANIFEST } from '@/admin/assistant/adapters/stub'
import type { ResvWithRoom } from '@/api/types'

const fakeDeps = () => ({
  today: '2026-11-25',
  rooms: async () => [{ id: 3, building_id: 7, room: 803, units: 1, reservable: true }],
  buildings: async () => [{ id: 7, school_id: 1, name: '공학관', bld: 'E', modem_id: null }],
  slots: async () => [],
  reservations: async () => [] as ResvWithRoom[],
  exams: async () => [],
  saveResv: vi.fn(async () => ({ id: 17, outbox_ids: [512] })),
})

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('useAssistant — 명령창 흐름 (admin-assistant.md 「흐름」)', () => {
  it('열기 → 보내기 → 되묻기 → 답 → 확인 → 적용 → 3초 뒤 닫힘', async () => {
    const d = fakeDeps()
    const onApplied = vi.fn()
    const a = useAssistant({
      api: createFakeAssistantApi(d),
      runner: new DevRuleRunner(),
      manifest: STUB_MANIFEST,
      onApplied,
    })
    expect(a.phase.value).toBe('closed')
    a.open()
    expect(a.phase.value).toBe('input')
    await a.send('803 금요일 15시부터 18시 특강')
    expect(a.phase.value).toBe('ask')
    expect(a.turn.value?.message).toBe('특강 이름은 무엇인가요?')
    expect(a.sent.value).toBe('803 금요일 15시부터 18시 특강')
    await a.send('알고리즘 특강')
    expect(a.phase.value).toBe('preview')
    expect(a.preview.value?.summary[0]).toContain('알고리즘 특강')
    await a.apply()
    expect(a.phase.value).toBe('applied')
    expect(onApplied).toHaveBeenCalledOnce()
    expect(d.saveResv).toHaveBeenCalledOnce()
    vi.advanceTimersByTime(3000)
    expect(a.phase.value).toBe('closed')
    expect(a.sent.value).toBe('')
  })

  it('빈 문장은 보내지 않고, 보내는 동안 다시 보내지 않는다', async () => {
    const turn = vi.fn(async () => ({
      conversation_id: 'c',
      kind: 'answer' as const,
      message: '',
      choices: [],
      next_prefix: null,
      closed: true,
      preview: null,
      answer: null,
    }))
    const a = useAssistant({
      api: { turn, apply: vi.fn() },
      runner: new DevRuleRunner(),
      manifest: STUB_MANIFEST,
    })
    a.open()
    await a.send('   ')
    expect(turn).not.toHaveBeenCalled()
    const first = a.send('취소')
    void a.send('취소')
    await first
    expect(turn).toHaveBeenCalledOnce()
    expect(a.phase.value).toBe('closed') // 취소 답(closed)은 창을 닫는다
  })

  it('서버가 error 면 그 글을 보이고 입력을 다시 받는다, 만료(410)면 확인을 닫고 안내', async () => {
    const api = createFakeAssistantApi(fakeDeps())
    const a = useAssistant({ api, runner: new DevRuleRunner(), manifest: STUB_MANIFEST })
    a.open()
    await a.send('점심 뭐 먹지')
    expect(a.phase.value).toBe('error')
    expect(a.error.value).toContain('이해하지 못했습니다')
    await a.send('803 금요일 15시부터 18시까지 알고리즘 특강')
    expect(a.phase.value).toBe('preview')
    api.apply = async () => {
      throw new ApiError(410, '만료', [], { detail: 'expired' })
    }
    await a.apply()
    expect(a.phase.value).toBe('error')
    expect(a.error.value).toBe('확인 화면이 만료되었습니다. 다시 말씀해 주세요.')
    expect(a.preview.value).toBeNull()
  })

  it('막음이 있으면 적용하지 않는다, 닫으면 처음부터', async () => {
    const d = { ...fakeDeps(), today: '2026-11-30' } // 이번 주 금요일(11/27)이 지난 날짜가 되는 주
    const a = useAssistant({
      api: createFakeAssistantApi(d),
      runner: new DevRuleRunner(),
      manifest: STUB_MANIFEST,
    })
    a.open()
    await a.send('803 다음주 금요일 15시부터 18시까지 알고리즘 특강')
    expect(a.phase.value).toBe('preview')
    expect(a.preview.value?.blockers).toEqual([])
    a.close()
    a.open()
    await a.send('803 금요일 15시부터 18시까지 알고리즘 특강')
    expect(a.preview.value?.blockers.length).toBe(0)
    a.preview.value!.blockers.push('지난 날짜')
    await a.apply()
    expect(d.saveResv).not.toHaveBeenCalled()
    expect(a.phase.value).toBe('preview')
  })
})
