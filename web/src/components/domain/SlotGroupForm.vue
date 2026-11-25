<script setup lang="ts">
import { computed, reactive, ref, useId, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Modal from '@/components/ui/Modal.vue'
import Select from '@/components/ui/Select.vue'
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
  spansOverlap,
  type SavedRow,
} from './rules'
import { parseHm } from './slotForm'
import { periodsFrom, type SlotGroup } from './slotGroups'

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

/** 한 교시 = 수업 + 쉬는시간. 학교마다 다를 수 있어 묶음의 지금 값도 고를 수 있게 둔다 */
const PATTERNS: [number, number][] = [
  [50, 10],
  [75, 15],
]
const patternLabel = ([len, gap]: [number, number]) =>
  gap ? `${len}분 + 쉬는 ${gap}분` : `${len}분 (쉬는시간 없음)`
const COUNT_OPTIONS = Array.from({ length: 8 }, (_, i) => ({ value: i + 1, label: `${i + 1}` }))

const draft = reactive({
  start: '09:00',
  count: 1,
  pattern: '50-10',
  type: 1 as SlotType,
  subject: '',
  professor: '',
})
const formError = ref('')
const saving = ref(false)
const initial = ref('')
const dirty = computed(() => JSON.stringify(draft) !== initial.value)

const patternOptions = computed(() => {
  const g = props.group
  const all = [...PATTERNS]
  if (g && !all.some(([l, x]) => l === g.periodMin && x === g.gapMin))
    all.unshift([g.periodMin, g.gapMin])
  return all.map((p) => ({ value: `${p[0]}-${p[1]}`, label: patternLabel(p) }))
})

watch(
  () => props.open,
  (open) => {
    const g = props.group
    if (!open || !g) return
    const first = g.slots[0]
    Object.assign(draft, {
      start: hm(first.s_h, first.s_m),
      count: g.slots.length,
      pattern: `${g.periodMin}-${g.gapMin}`,
      type: first.type,
      subject: first.subject,
      professor: first.professor,
    })
    formError.value = ''
    initial.value = JSON.stringify(draft)
  },
  { immediate: true },
)

const periods = computed(() => {
  const s = parseHm(draft.start)
  const [len, gap] = draft.pattern.split('-').map(Number)
  return s ? periodsFrom(s[0] * 60 + s[1], draft.count, len, gap) : null
})
const startError = computed(() => {
  const g = props.group
  if (!parseHm(draft.start)) return '시작 시각을 넣으세요'
  if (!periods.value) return '자정을 넘깁니다 — 시작을 당기거나 교시를 줄이세요'
  if (!g) return ''
  const mine = new Set(g.slots.map(slotKey))
  const hit = props.existing.find(
    (x) =>
      x.room_id === g.room_id &&
      x.day === g.day &&
      !mine.has(slotKey(x)) &&
      periods.value!.some((p) => spansOverlap(x, p)),
  )
  return hit ? `겹칩니다: ${hm(hit.s_h, hit.s_m)}–${hm(hit.e_h, hit.e_m)} ${hit.subject}` : ''
})
const span = (p: { s_h: number; s_m: number; e_h: number; e_m: number }) =>
  `${hm(p.s_h, p.s_m)}–${hm(p.e_h, p.e_m)}`
const endLabel = computed(() => {
  const last = periods.value?.[periods.value.length - 1]
  return last ? hm(last.e_h, last.e_m) : '—'
})
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
      <fieldset class="gf__time">
        <legend class="gf__legend">시간</legend>
        <div class="gf__grid gf__grid--3">
          <Input
            v-model="draft.start"
            label="시작"
            type="time"
            class="num"
            required
            :error="startError"
          />
          <Select v-model="draft.count" label="교시 수" :options="COUNT_OPTIONS" />
          <Select v-model="draft.pattern" label="한 교시" :options="patternOptions" />
        </div>
        <p class="gf__end">
          끝 <b class="num">{{ endLabel }}</b> — 시작 · 교시 수에서 자동으로 정해집니다
        </p>
        <div class="gf__preview">
          <p class="gf__caption">저장되는 교시 (문 앞 화면은 쉬는시간을 이 사이로 보여 줍니다)</p>
          <ul class="gf__chips">
            <li v-for="(p, i) in periods ?? []" :key="i" class="gf__chip num">
              {{ i + 1 }}교시 {{ span(p) }}
            </li>
          </ul>
          <p v-if="after !== before" class="gf__before num">지금 {{ before }}</p>
        </div>
      </fieldset>
      <p v-if="!group.uniform" class="gf__hint">
        교시 길이 · 쉬는시간이 고르지 않은 묶음입니다. 저장하면 고른 '한 교시'로 고르게 다시
        만듭니다.
      </p>
    </form>
    <template #footer>
      <Button variant="ghost" class="gf__remove" @click="emit('remove')">묶음 삭제</Button>
      <Button variant="secondary" @click="emit('close')">취소</Button>
      <Button type="submit" :form="formId" :loading="saving" :disabled="!!startError"
        >{{ periods?.length ?? draft.count }}교시 저장</Button
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
.gf__grid--3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.gf__time {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin: 0;
  padding: var(--space-3) var(--space-4) var(--space-4);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
}
.gf__legend {
  padding: 0 var(--space-1);
  font-weight: var(--font-weight-bold);
}
.gf__end {
  margin: 0;
  color: var(--text-2);
}
.gf__end b {
  color: var(--text-1);
}
.gf__preview {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding-top: var(--space-3);
  border-top: var(--border-thin) solid var(--line-1);
}
.gf__caption,
.gf__before,
.gf__hint {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.gf__before {
  text-decoration: line-through;
}
.gf__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}
.gf__chip {
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-full);
  background: var(--brand-tint);
  color: var(--brand);
  font-size: var(--font-size-xs);
}
.gf__remove {
  margin-right: auto;
}
</style>
