<script setup lang="ts">
import { computed, reactive, ref, useId, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Modal from '@/components/ui/Modal.vue'
import Select from '@/components/ui/Select.vue'
import { showToast } from '@/components/ui/toast'
import { ApiError, MESSAGES } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { ResvIn, ResvWithRoom, RoomOut } from '@/api/types'
import { dayOfDate, hm, kstDateStr } from '@/lib/time'
import {
  DAYS,
  LATER_HINT,
  PROF_MAX,
  SUBJ_MAX,
  TYPE_OPTIONS,
  conflictMessage,
  resvKey,
  resvWindow,
  type SavedRow,
} from './rules'
import { resvErrors, type ResvDraft } from './resvForm'
import { parseHm } from './slotForm'

// 저장 버튼은 Modal 바닥(폼 밖)에 있다 — form 속성으로 이어 Enter 가 폼을 제출하게 (submit 한 길만)
const formId = useId()

const props = withDefaults(
  defineProps<{
    open: boolean
    mode?: 'create' | 'edit'
    rooms: RoomOut[]
    roomLabel?: (r: RoomOut) => string
    value?: ResvWithRoom | null
    preset?: { room_id: number } | null
    existing?: ResvWithRoom[]
  }>(),
  {
    mode: 'create',
    roomLabel: (r: RoomOut) => `${r.room}호`,
    value: null,
    preset: null,
    existing: () => [],
  },
)
const emit = defineEmits<{ close: []; saved: [row: SavedRow]; stale: [] }>()

const draft = reactive<ResvDraft>({
  roomId: 0,
  date: '',
  start: '10:00',
  end: '11:00',
  type: 5,
  subject: '',
  professor: '',
})
const errors = ref<{ date?: string; start?: string; end?: string }>({})
const formError = ref('')
const saving = ref(false)
const initial = ref('')
const today = ref(kstDateStr(new Date()))
const dirty = computed(() => JSON.stringify(draft) !== initial.value)
const roomOptions = computed(() =>
  props.rooms.map((r) => ({ value: r.id, label: props.roomLabel(r) })),
)
// 요일은 서버 필드가 아니다 — 날짜에서 계산해 읽기 전용으로 보인다
const weekday = computed(() => (draft.date ? DAYS[dayOfDate(draft.date) - 1] : ''))
const later = computed(() => !!draft.date && resvWindow(draft.date, today.value) === 'later')

watch(
  () => props.open,
  (open) => {
    if (!open) return
    today.value = kstDateStr(new Date())
    const v = props.value
    Object.assign(
      draft,
      v
        ? {
            roomId: v.room_id,
            date: v.date,
            start: hm(v.s_h, v.s_m),
            end: hm(v.e_h, v.e_m),
            type: v.type,
            subject: v.subject,
            professor: v.professor,
          }
        : {
            roomId: props.preset?.room_id ?? props.rooms[0]?.id ?? 0,
            date: '',
            start: '10:00',
            end: '11:00',
            type: 5,
            subject: '',
            professor: '',
          },
    )
    errors.value = {}
    formError.value = ''
    initial.value = JSON.stringify(draft)
  },
  { immediate: true },
)

async function save() {
  if (saving.value) return
  errors.value = resvErrors(draft, props.existing, props.value?.id ?? null, today.value)
  if (errors.value.date || errors.value.start || errors.value.end) return
  const [s_h, s_m] = parseHm(draft.start)!
  const [e_h, e_m] = parseHm(draft.end)!
  const body: ResvIn = {
    date: draft.date,
    s_h,
    s_m,
    e_h,
    e_m,
    type: draft.type,
    subject: draft.subject,
    professor: draft.professor,
  }
  // 채번하지 않는다 — 추가는 id 없이, 수정만 그 id 로 (S4b §2.5)
  if (props.value) body.id = props.value.id
  saving.value = true
  formError.value = ''
  try {
    const r = await roomsApi.saveResv(draft.roomId, body)
    const id = r.id ?? props.value!.id
    emit('saved', { roomId: draft.roomId, key: resvKey(id), outboxIds: r.outbox_ids })
    // 창 밖(7일)은 실패가 아니다 — outbox_ids 는 비거나(새 행) 옛 날짜 DEL 만 담긴다(창 밖으로 옮긴 수정)
    showToast({ message: later.value ? `저장했습니다. ${LATER_HINT}.` : '저장했습니다.' })
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
    :title="mode === 'edit' ? '예약 수정' : '예약 추가'"
    :close-on-backdrop="!dirty"
    @close="emit('close')"
  >
    <form :id="formId" class="form" novalidate @submit.prevent="save">
      <p v-if="formError" class="form__error" role="alert">{{ formError }}</p>
      <div class="form__grid">
        <Select
          v-model="draft.roomId"
          label="강의실"
          :options="roomOptions"
          :disabled="mode === 'edit'"
        />
        <Select v-model="draft.type" label="유형" :options="TYPE_OPTIONS" />
        <Input
          v-model="draft.date"
          label="날짜"
          type="date"
          class="num"
          required
          :error="errors.date"
          :hint="later ? LATER_HINT : undefined"
        />
        <Input :model-value="weekday" label="요일" readonly tabindex="-1" />
        <Input
          v-model="draft.start"
          label="시작"
          type="time"
          class="num"
          required
          :error="errors.start"
        />
        <Input
          v-model="draft.end"
          label="종료"
          type="time"
          class="num"
          required
          :error="errors.end"
        />
        <Input v-model="draft.subject" label="사용 목적" :max-bytes="SUBJ_MAX" />
        <Input v-model="draft.professor" label="주관 부서" :max-bytes="PROF_MAX" />
      </div>
      <p v-if="mode === 'edit'" class="form__hint">다른 강의실로 옮기려면 지우고 다시 만드세요.</p>
    </form>
    <template #footer>
      <Button variant="secondary" @click="emit('close')">취소</Button>
      <Button type="submit" :form="formId" :loading="saving">저장</Button>
    </template>
  </Modal>
</template>

<style scoped>
.form__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3) var(--space-4);
}
.form__error {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-sm);
  color: var(--danger);
}
.form__hint {
  margin: var(--space-3) 0 0;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
</style>
