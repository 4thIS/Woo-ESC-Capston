<script setup lang="ts">
import { computed, reactive, ref, useId, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Modal from '@/components/ui/Modal.vue'
import Select from '@/components/ui/Select.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import PeriodFields from './PeriodFields.vue'
import { showToast } from '@/components/ui/toast'
import { ApiError, MESSAGES } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { SlotIn, SlotSource, SlotType, SlotWithRoom } from '@/api/types'
import { parseHm, slotErrors } from './slotForm'
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
  /** 주간 시간표 블록 — 맨 위 토글 '묶음 전체 | 한 교시만' (admin-schedule.md). 목록은 없이 지금 그대로 */
  scopes?: boolean
}>()
/** remove — 지울 교시들(묶음 전체 또는 고른 한 교시). 확인은 부모가 */
const emit = defineEmits<{
  close: []
  saved: [row: SavedRow]
  stale: []
  remove: [slots: SlotWithRoom[]]
}>()

type Scope = 'all' | 'one'
const SCOPES = [
  { value: 'all', label: '묶음 전체' },
  { value: 'one', label: '한 교시만' },
]
const scope = ref<Scope>('all')
// 한 교시만 — 고른 교시 하나를 지금 슬롯 수정처럼(시작 · 종료 · 과목 · 교수 · 유형)
const pick = ref(0)
const one = reactive({ start: '', end: '', type: 1 as SlotType, subject: '', professor: '' })
const oneErrors = ref<{ start?: string; end?: string }>({})
const picked = computed(() => props.group?.slots[pick.value] ?? null)
const pickItems = computed(
  () => props.group?.slots.map((_, i) => ({ value: String(i), label: `${i + 1}교시` })) ?? [],
)
function choose(i: number) {
  const s = props.group?.slots[i]
  if (!s) return
  pick.value = i
  Object.assign(one, {
    start: hm(s.s_h, s.s_m),
    end: hm(s.e_h, s.e_m),
    type: s.type,
    subject: s.subject,
    professor: s.professor,
  })
  oneErrors.value = {}
}

const draft = reactive({ type: 1 as SlotType, subject: '', professor: '' })
const time = ref<PeriodDraft>({ start: '09:00', count: 1, pattern: '50-10' })
const formError = ref('')
const saving = ref(false)
const initial = ref('')
const snapshot = () => JSON.stringify([draft, time.value, one])
const dirty = computed(() => snapshot() !== initial.value)

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
    scope.value = 'all'
    choose(0)
    formError.value = ''
    initial.value = snapshot()
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
const subtitle = computed(() => {
  const g = props.group
  if (!g) return ''
  const head = `${props.roomLabel} · ${DAYS[g.day - 1]}요일`
  return props.scopes ? `${head} · ${g.slots[0].subject} · ${g.slots.length}교시` : head
})
const span = (p: { s_h: number; s_m: number; e_h: number; e_m: number }) =>
  `${hm(p.s_h, p.s_m)}–${hm(p.e_h, p.e_m)}`
const before = computed(() => props.group?.slots.map(span).join(' · ') ?? '')
const after = computed(() => periods.value?.map(span).join(' · ') ?? '')

// 저장 — 지울 교시 · 넣을 교시를 한 요청 한 트랜잭션으로(POST /slots/replace). 같은 키는 덮어쓴다
async function save() {
  const g = props.group
  if (!g || saving.value) return
  if (scope.value === 'one') return saveOne(g)
  if (startError.value || !periods.value) return
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
  await send(g, g.slots, put, `${put.length}교시를 저장했습니다.`)
}

function saveOne(g: SlotGroup) {
  const s = picked.value
  if (!s) return
  oneErrors.value = slotErrors({ roomId: g.room_id, day: g.day, ...one }, props.existing, s)
  if (oneErrors.value.start || oneErrors.value.end) return
  const [s_h, s_m] = parseHm(one.start)!
  const [e_h, e_m] = parseHm(one.end)!
  const put: SlotIn = {
    day: g.day,
    s_h,
    s_m,
    e_h,
    e_m,
    type: one.type,
    subject: one.subject,
    professor: one.professor,
    // 웹에서 고친 교시는 수동(2) — 포털(1)은 올라가고 긴급(3)은 그대로
    source: Math.max(2, s.source) as SlotSource,
  }
  return send(g, [s], [put], '저장했습니다.')
}

async function send(g: SlotGroup, old: SlotWithRoom[], put: SlotIn[], done: string) {
  const remove = old.map(({ day, s_h, s_m }) => ({ day, s_h, s_m }))
  saving.value = true
  formError.value = ''
  try {
    const r = await roomsApi.replaceSlots(g.room_id, { remove, put })
    emit('saved', {
      roomId: g.room_id,
      key: slotKey({ room_id: g.room_id, ...put[0] }),
      outboxIds: r.outbox_ids,
    })
    showToast({ message: done })
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
    :title="scopes ? '시간표 수정' : `수업 수정 — ${group?.slots.length ?? 0}교시 묶음`"
    :close-on-backdrop="!dirty"
    @close="emit('close')"
  >
    <form v-if="group" :id="formId" class="gf" novalidate @submit.prevent="save">
      <p class="gf__sub">{{ subtitle }}</p>
      <p v-if="formError" class="gf__error" role="alert">{{ formError }}</p>
      <SegmentedControl
        v-if="scopes"
        :items="SCOPES"
        :value="scope"
        label="수정 범위"
        @update:value="(v: string) => (scope = v === 'one' ? 'one' : 'all')"
      />
      <template v-if="scope === 'one'">
        <SegmentedControl
          :items="pickItems"
          :value="String(pick)"
          label="고칠 교시"
          @update:value="(v: string) => choose(Number(v))"
        />
        <div class="gf__grid">
          <Input
            v-model="one.start"
            label="시작"
            type="time"
            class="num"
            required
            :error="oneErrors.start"
          />
          <Input
            v-model="one.end"
            label="종료"
            type="time"
            class="num"
            required
            :error="oneErrors.end"
          />
          <Input
            :model-value="one.subject"
            label="과목명"
            :max-bytes="SUBJ_MAX"
            @update:model-value="(v: string) => (one.subject = halfwidth(v))"
          />
          <Input
            :model-value="one.professor"
            label="교수"
            :max-bytes="PROF_MAX"
            @update:model-value="(v: string) => (one.professor = halfwidth(v))"
          />
          <Select v-model="one.type" label="유형" :options="TYPE_OPTIONS" />
        </div>
        <p v-if="picked?.source === 1" class="gf__hint">
          저장하면 이 교시는 수동 편집으로 바뀌어 CSV 임포트에 덮이지 않습니다.
        </p>
      </template>
      <div v-else class="gf__grid">
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
        v-if="scope === 'all'"
        v-model="time"
        :pattern-options="patternOptions"
        :error="startError"
        caption="저장되는 교시 (문 앞 화면은 쉬는시간을 이 사이로 보여 줍니다)"
      >
        <p v-if="after !== before" class="gf__before num">지금 {{ before }}</p>
      </PeriodFields>
      <p v-if="scope === 'all' && !group.uniform" class="gf__hint">
        교시 길이 · 쉬는시간이 고르지 않은 묶음입니다. 저장하면 고른 '한 교시'로 고르게 다시
        만듭니다.
      </p>
    </form>
    <template #footer>
      <Button
        v-if="scope === 'one'"
        variant="ghost"
        class="gf__remove"
        @click="picked && emit('remove', [picked])"
        >삭제</Button
      >
      <Button
        v-else
        variant="ghost"
        class="gf__remove"
        @click="group && emit('remove', group.slots)"
        >묶음 삭제</Button
      >
      <Button variant="secondary" @click="emit('close')">취소</Button>
      <Button v-if="scope === 'one'" type="submit" :form="formId" :loading="saving">저장</Button>
      <Button v-else type="submit" :form="formId" :loading="saving" :disabled="!!startError"
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
