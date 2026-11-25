<script setup lang="ts">
import { computed, reactive, ref, useId, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Modal from '@/components/ui/Modal.vue'
import Select from '@/components/ui/Select.vue'
import PeriodFields from './PeriodFields.vue'
import { showToast } from '@/components/ui/toast'
import { ApiError, MESSAGES } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { SlotIn, SlotSource, SlotType, SlotWithRoom } from '@/api/types'
import { hm } from '@/lib/time'
import {
  DAYS,
  PROF_MAX,
  SUBJ_MAX,
  TYPE_OPTIONS,
  conflictMessage,
  halfwidth,
  slotKey,
  type SavedRow,
} from './rules'
import {
  PERIOD_PATTERNS,
  firstOverlap,
  patternKey,
  patternLabel,
  periodsOf,
  type PeriodDraft,
  type SlotGroup,
} from './slotGroups'

// 교시 묶음 수정 (admin-rooms.md 「연속 교시 묶음」) — 시작 · 교시 수 · 한 교시만 고르면 교시들을 다시 만든다.
// 저장은 교시마다(문 앞 쉬는시간이 그 틈으로 그려진다), 한 요청 한 트랜잭션(POST /slots/replace)
const formId = useId()
const props = defineProps<{
  open: boolean
  group: SlotGroup | null
  /** 'E 803호' 처럼 — 제목 아래 */
  roomLabel: string
  /** 겹침 검사 대상 — 이 묶음의 교시는 뺀다 */
  existing: SlotWithRoom[]
}>()
const emit = defineEmits<{ close: []; saved: [row: SavedRow]; stale: []; remove: [] }>()

const draft = reactive({ type: 1 as SlotType, subject: '', professor: '' })
const time = ref<PeriodDraft>({ start: '09:00', count: 1, pattern: '50-10' })
const formError = ref('')
const saving = ref(false)
const initial = ref('')
const dirty = computed(() => JSON.stringify([draft, time.value]) !== initial.value)

const patternOptions = computed(() => {
  const g = props.group
  // 학교마다 다를 수 있어 묶음의 지금 값도 고를 수 있게 둔다
  const all = [...PERIOD_PATTERNS]
  if (g && !all.some(([l, x]) => l === g.periodMin && x === g.gapMin))
    all.unshift([g.periodMin, g.gapMin])
  return all.map((p) => ({ value: patternKey(p), label: patternLabel(p) }))
})

watch(
  () => props.open,
  (open) => {
    const g = props.group
    if (!open || !g) return
    const first = g.slots[0]
    Object.assign(draft, { type: first.type, subject: first.subject, professor: first.professor })
    time.value = {
      start: hm(first.s_h, first.s_m),
      count: g.slots.length,
      pattern: patternKey([g.periodMin, g.gapMin]),
    }
    formError.value = ''
    initial.value = JSON.stringify([draft, time.value])
  },
  { immediate: true },
)

const periods = computed(() => periodsOf(time.value))
const startError = computed(() => {
  const g = props.group
  if (!/^\d{2}:\d{2}$/.test(time.value.start)) return '시작 시각을 넣으세요'
  if (!periods.value) return '자정을 넘깁니다 — 시작을 당기거나 교시를 줄이세요'
  return g
    ? firstOverlap(props.existing, g.room_id, g.day, periods.value, new Set(g.slots.map(slotKey)))
    : ''
})
const span = (p: { s_h: number; s_m: number; e_h: number; e_m: number }) =>
  `${hm(p.s_h, p.s_m)}–${hm(p.e_h, p.e_m)}`
const before = computed(() => props.group?.slots.map(span).join(' · ') ?? '')
const after = computed(() => periods.value?.map(span).join(' · ') ?? '')

async function save() {
  const g = props.group
  if (saving.value || !g || startError.value || !periods.value) return
  // 웹에서 고친 교시는 수동(2) — 포털(1)은 올라가고 긴급(3)은 그대로 (3 에 2 를 보내면 409)
  const source = Math.max(2, ...g.slots.map((x) => x.source)) as SlotSource
  const put: SlotIn[] = periods.value.map((p) => ({
    day: g.day,
    ...p,
    type: draft.type,
    subject: draft.subject,
    professor: draft.professor,
    source,
  }))
  const remove = g.slots.map(({ day, s_h, s_m }) => ({ day, s_h, s_m }))
  saving.value = true
  formError.value = ''
  try {
    const r = await roomsApi.replaceSlots(g.room_id, { remove, put })
    emit('saved', {
      roomId: g.room_id,
      key: slotKey({ room_id: g.room_id, ...put[0] }),
      outboxIds: r.outbox_ids,
    })
    showToast({ message: `${put.length}교시를 저장했습니다.` })
    emit('close')
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 422) formError.value = MESSAGES[422]
    else if (e.status === 409) {
      showToast({ tone: 'danger', message: conflictMessage(e) })
      emit('stale')
    } else if (e.status === 404) {
      showToast({ tone: 'danger', message: '강의실을 찾을 수 없습니다. 목록을 새로 불러옵니다.' })
      emit('stale')
      emit('close')
    } else if (e.status !== 401 && e.status !== 403) formError.value = e.message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Modal
    :open="open"
    :title="`수업 수정 — ${group?.slots.length ?? 0}교시 묶음`"
    :close-on-backdrop="!dirty"
    @close="emit('close')"
  >
    <form v-if="group" :id="formId" class="gf" novalidate @submit.prevent="save">
      <p class="gf__sub">{{ roomLabel }} · {{ DAYS[group.day - 1] }}요일</p>
      <p v-if="formError" class="gf__error" role="alert">{{ formError }}</p>
      <div class="gf__grid">
        <!-- 전각 영숫자는 칸에서 반각으로 — 서버도 같은 규칙으로 저장한다 (이슈 140) -->
        <Input
          :model-value="draft.subject"
          label="과목명"
          :max-bytes="SUBJ_MAX"
          @update:model-value="(v: string) => (draft.subject = halfwidth(v))"
        />
        <Input
          :model-value="draft.professor"
          label="교수"
          :max-bytes="PROF_MAX"
          @update:model-value="(v: string) => (draft.professor = halfwidth(v))"
        />
        <Select v-model="draft.type" label="유형" :options="TYPE_OPTIONS" />
      </div>
      <PeriodFields
        v-model="time"
        :pattern-options="patternOptions"
        :error="startError"
        caption="저장되는 교시 (문 앞 화면은 쉬는시간을 이 사이로 보여 줍니다)"
      >
        <p v-if="after !== before" class="gf__before num">지금 {{ before }}</p>
      </PeriodFields>
      <p v-if="!group.uniform" class="gf__hint">
        교시 길이 · 쉬는시간이 고르지 않은 묶음입니다. 저장하면 고른 '한 교시'로 고르게 다시
        만듭니다.
      </p>
    </form>
    <template #footer>
      <Button variant="ghost" class="gf__remove" @click="emit('remove')">묶음 삭제</Button>
      <Button variant="secondary" @click="emit('close')">취소</Button>
      <Button type="submit" :form="formId" :loading="saving" :disabled="!!startError"
        >{{ periods?.length ?? time.count }}교시 저장</Button
      >
    </template>
  </Modal>
</template>

<style scoped>
.gf {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.gf__sub {
  margin: calc(-1 * var(--space-2)) 0 0;
  color: var(--text-3);
}
.gf__error {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--danger);
}
.gf__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3) var(--space-4);
}
.gf__before,
.gf__hint {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.gf__before {
  text-decoration: line-through;
}
.gf__remove {
  margin-right: auto;
}
</style>
