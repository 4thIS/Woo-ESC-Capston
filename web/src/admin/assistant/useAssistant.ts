import { computed, ref } from 'vue'
import { ApiError } from '@/api/client'
import { classify } from '@/api/assistant'
import type { ApplyOut, ModelManifestOn, TurnIn, TurnOut } from '@/api/types'
import { parseForm, userMessage } from './prompt'
import type { ModelRunner } from './runner'

/** admin-assistant.md 「흐름」 — 닫힘 · 명령창(입력) · 보내는 중 · 되묻기 · 확인 · 적용 중 · 적용 후 · 오류 */
export type Phase =
  'closed' | 'input' | 'sending' | 'ask' | 'preview' | 'applying' | 'applied' | 'error'

export interface AssistantDeps {
  api: { turn(t: TurnIn): Promise<TurnOut>; apply(previewId: string): Promise<ApplyOut> }
  runner: ModelRunner
  manifest: ModelManifestOn
  /** 적용이 끝났다 — 뒤 화면을 다시 불러온다 */
  onApplied?: () => void
  /** 적용 후 닫히기까지 (ms) */
  closeDelay?: number
}

const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e))

export function useAssistant(deps: AssistantDeps) {
  const phase = ref<Phase>('closed')
  const text = ref('')
  /** 처음 보낸 문장 — 머리 줄에 남는다 */
  const sent = ref('')
  const turn = ref<TurnOut | null>(null)
  const error = ref('')
  /** 409 stale 로 미리보기가 바뀌었다 */
  const stale = ref(false)
  let conversation: string | null = null
  let prefix: string | null = null
  let timer: ReturnType<typeof setTimeout> | null = null

  const preview = computed(() => turn.value?.preview ?? null)
  const isOpen = computed(() => phase.value !== 'closed')

  function reset() {
    text.value = ''
    sent.value = ''
    turn.value = null
    error.value = ''
    stale.value = false
    conversation = null
    prefix = null
    if (timer) clearTimeout(timer)
    timer = null
  }
  function show() {
    if (phase.value !== 'closed') return
    reset()
    phase.value = 'input'
  }
  function close() {
    reset()
    phase.value = 'closed'
  }
  const toggle = () => (isOpen.value ? close() : show())

  function handle(t: TurnOut) {
    conversation = t.closed ? null : t.conversation_id
    prefix = t.closed ? null : t.next_prefix
    turn.value = t
    text.value = ''
    if (t.kind === 'ask') phase.value = 'ask'
    else if (t.kind === 'preview') phase.value = 'preview'
    else if (t.kind === 'error') {
      error.value = t.message
      phase.value = 'error'
    } else close() // 취소 등 — 대화가 끝났다
  }

  async function send(utterance: string = text.value) {
    const u = utterance.trim()
    if (!u || !['input', 'ask', 'error'].includes(phase.value)) return
    if (prefix === null) sent.value = u
    phase.value = 'sending'
    error.value = ''
    const m = deps.manifest
    const req = {
      system: m.system_prompt,
      user: userMessage(prefix ?? m.first_prefix, u),
      schema: m.json_schema,
      generation: m.generation,
    }
    try {
      // 양식으로 못 읽으면 한 번 더 — 그래도 못 읽으면 원문을 서버로(학습 기록, 서버가 error 로 답한다)
      let raw = await deps.runner.generate(req)
      let form = parseForm(raw)
      if (!form) {
        raw = await deps.runner.generate(req)
        form = parseForm(raw)
      }
      handle(
        await deps.api.turn({
          conversation_id: conversation,
          utterance: u,
          form,
          choice: null,
          raw_output: form ? null : raw.slice(0, 2000),
        }),
      )
    } catch (e) {
      error.value =
        e instanceof ApiError && e.status === 429 ? '잠시 뒤 다시 보내 주세요.' : errorText(e)
      phase.value = 'error'
    }
  }

  async function apply() {
    const p = preview.value
    if (phase.value !== 'preview' || !p || p.blockers.length) return
    phase.value = 'applying'
    try {
      await deps.api.apply(p.preview_id)
      phase.value = 'applied'
      deps.onApplied?.()
      timer = setTimeout(close, deps.closeDelay ?? 3000)
    } catch (e) {
      const f = e instanceof ApiError ? classify(e) : null
      if (f?.kind === 'stale' && turn.value) {
        turn.value = { ...turn.value, preview: f.preview }
        stale.value = true
        phase.value = 'preview'
        return
      }
      turn.value = null
      conversation = null
      prefix = null
      error.value =
        f?.kind === 'expired'
          ? '확인 화면이 만료되었습니다. 다시 말씀해 주세요.'
          : f?.kind === 'schema_version'
            ? 'AI 모델이 새 판으로 바뀌었습니다. 새로고침해 주세요.'
            : f?.kind === 'rate'
              ? '잠시 뒤 다시 보내 주세요.'
              : errorText(e)
      phase.value = 'error'
    }
  }

  return {
    phase,
    text,
    sent,
    turn,
    preview,
    error,
    stale,
    isOpen,
    open: show,
    close,
    toggle,
    send,
    apply,
  }
}
