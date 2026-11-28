import { describe, expect, it, vi } from 'vitest'
import { computed, ref } from 'vue'
import { mount } from '@vue/test-utils'
import type { PreviewOut, TurnOut } from '@/api/types'

// 명령창이 보는 상태 — 확인(preview) 단계에 있는 대화 하나
const turn = ref<TurnOut | null>(null)
const phase = ref('preview')
vi.mock('@/admin/assistant/store', () => ({
  canType: computed(() => true),
  assistantStore: () => ({
    phase,
    text: ref(''),
    sent: ref('801 매주월요일 9시~12시 자료구조 김교수 추가'),
    turn,
    preview: computed(() => turn.value?.preview ?? null),
    error: ref(''),
    stale: ref(false),
    reload: ref(false),
    close: vi.fn(),
    send: vi.fn(),
    choose: vi.fn(),
    apply: vi.fn(),
  }),
}))

const AssistantBar = (await import('@/admin/assistant/AssistantBar.vue')).default

// 서버(#181)가 정규 시간표(class.*)만 바꿀 때 — week_start: null (types.ts PreviewWeek)
const weekly: PreviewOut = {
  preview_id: 'p1',
  expires_at: new Date('2026-11-27T17:04:41Z'),
  summary: ['+ 매주 월 09:00–12:00 수업 "자료구조" (공학관 801)'],
  blockers: [],
  warnings: [],
  notices: [],
  rooms: [
    {
      room_id: 1,
      building_id: 1,
      label: '공학관 801',
      added: 1,
      removed: 0,
      changed: 0,
      weeks: [
        {
          week_start: null,
          before: { slots: [], reservations: [], exams: [] },
          after: {
            slots: [
              {
                s_h: 9,
                s_m: 0,
                e_h: 12,
                e_m: 0,
                type: 1,
                subject: '자료구조',
                professor: '김교수',
                day: 1,
                source: 2,
                id: 8,
                room_id: 1,
              },
            ],
            reservations: [],
            exams: [],
          },
          changes: [{ entity: 'slot', key: 'd1-0900', op: 'add', fields: [] }],
        },
      ],
    },
  ],
} as unknown as PreviewOut

describe('AssistantBar — 정규 시간표 확인 화면', () => {
  it('week_start 가 null 이어도 그린다 — 날짜 대신 "매주"', async () => {
    phase.value = 'preview'
    turn.value = {
      conversation_id: 'c1',
      kind: 'preview',
      message: '',
      choices: [],
      next_prefix: null,
      closed: false,
      preview: weekly,
      answer: null,
    }
    const w = mount(AssistantBar, { attachTo: document.body })
    await w.vm.$nextTick()
    const text = document.body.textContent ?? ''
    expect(text).toContain('변경 확인 · 공학관 801')
    expect(text).toContain('매주 (정규 시간표)')
    expect(text).toContain('월요일')
    expect(text).not.toContain('NaN')
    w.unmount()
  })
})

describe('AssistantBar — 되묻기 선택 버튼', () => {
  it('버튼이 있어도 직접 답할 입력칸을 함께 보인다', async () => {
    phase.value = 'ask'
    turn.value = {
      conversation_id: 'c1',
      kind: 'ask',
      message: "'999' 강의실을 찾지 못했습니다. 현재 있는 강의실은 아래와 같습니다.",
      choices: [
        { id: 'room:1', label: '공학관 801' },
        { id: 'room:2', label: '공학관 803' },
      ],
      next_prefix: null,
      closed: false,
      preview: null,
      answer: null,
    }
    const w = mount(AssistantBar, { attachTo: document.body })
    await w.vm.$nextTick()
    const labels = w.findAll('button').map((b) => b.text())
    expect(labels).toContain('공학관 801')
    expect(labels).toContain('공학관 803')
    expect(w.find('#ai-answer').exists()).toBe(true)
    expect(labels.filter((x) => x === '요청 취소')).toHaveLength(1)
    w.unmount()
  })
})
