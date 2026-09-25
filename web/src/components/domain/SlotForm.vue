<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Modal from '@/components/ui/Modal.vue'
import Select from '@/components/ui/Select.vue'
import { showToast } from '@/components/ui/toast'
import { ApiError, MESSAGES } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { RoomOut, SlotIn, SlotSource, SlotWithRoom } from '@/api/types'
import { hm } from '@/lib/time'
import {
  DAY_OPTIONS,
  PROF_MAX,
  SUBJ_MAX,
  TYPE_OPTIONS,
  conflictMessage,
  slotKey,
  type SavedRow,
} from './rules'
import { parseHm, slotErrors, type SlotDraft } from './slotForm'

const props = withDefaults(
  defineProps<{
    open: boolean
    mode?: 'create' | 'edit'
    rooms: RoomOut[]
    roomLabel?: (r: RoomOut) => string
    /** edit — 고칠 슬롯 */
    value?: SlotWithRoom | null
    /** create — 기본 강의실, 격자에서 누른 요일·시각 */
    preset?: { room_id: number; day?: number; s_h?: number; s_m?: number } | null
    /** 겹침 검사 대상 (같은 방·같은 요일만 본다) */
    existing?: SlotWithRoom[]
    removable?: boolean
  }>(),
  {
    mode: 'create',
    roomLabel: (r: RoomOut) => `${r.room}호`,
    value: null,
    preset: null,
    existing: () => [],
    removable: false,
  },
)
const emit = defineEmits<{ close: []; saved: [row: SavedRow]; stale: []; remove: [] }>()

const draft = reactive<SlotDraft>({
  roomId: 0,
  day: 1,
  start: '09:00',
  end: '10:00',
  type: 1,
  subject: '',
  professor: '',
})
const errors = ref<{ start?: string; end?: string }>({})
const formError = ref('')
const saving = ref(false)
const initial = ref('')
const dirty = computed(() => JSON.stringify(draft) !== initial.value)
const roomOptions = computed(() =>
  props.rooms.map((r) => ({ value: r.id, label: props.roomLabel(r) })),
)

watch(
  () => props.open,
  (open) => {
    if (!open) return
    const v = props.value
    const p = props.preset
    const sh = p?.s_h ?? 9
    const sm = p?.s_m ?? 0
    Object.assign(
      draft,
      v
        ? {
            roomId: v.room_id,
            day: v.day,
            start: hm(v.s_h, v.s_m),
            end: hm(v.e_h, v.e_m),
            type: v.type,
            subject: v.subject,
            professor: v.professor,
          }
        : {
            roomId: p?.room_id ?? props.rooms[0]?.id ?? 0,
            day: p?.day ?? 1,
            start: hm(sh, sm),
            end: hm(Math.min(sh + 1, 23), sm), // 종료 기본값은 +1시간 (admin-schedule.md)
            type: 1,
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
  errors.value = slotErrors(draft, props.existing, props.value)
  if (errors.value.start || errors.value.end) return
  const [s_h, s_m] = parseHm(draft.start)!
  const [e_h, e_m] = parseHm(draft.end)!
  const slot: SlotIn = {
    day: draft.day,
    s_h,
    s_m,
    e_h,
    e_m,
    type: draft.type,
    subject: draft.subject,
    professor: draft.professor,
    // 웹에서 고친 행은 수동(2) — 포털(1)은 올라가고 긴급(3)은 그대로 (3 에 2 를 보내면 409)
    source: Math.max(2, props.value?.source ?? 2) as SlotSource,
  }
  const key = slotKey({ room_id: draft.roomId, ...slot })
  const old = props.value
  saving.value = true
  formError.value = ''
  try {
    const r = await roomsApi.putSlot(draft.roomId, slot)
    const saved: SavedRow = { roomId: draft.roomId, key, outboxIds: r.outbox_ids }
    // 키(요일·시작)나 방이 바뀌면 PUT 은 새 행을 만든다 — 옛 행을 지운다. 새 행을 먼저 넣어
    // 지우기가 실패해도 데이터가 사라지지 않게 한다 (최악이 중복 한 줄 — 보이고 지울 수 있다)
    if (old && slotKey(old) !== key) {
      try {
        await roomsApi.deleteSlot(old.room_id, old)
      } catch (e) {
        if (!(e instanceof ApiError)) throw e
        if (e.status === 401 || e.status === 403) return
        emit('saved', saved)
        emit('stale')
        showToast({
          tone: 'danger',
          message: '새 슬롯은 저장했지만 옛 슬롯을 지우지 못했습니다. 표에서 지워 주세요.',
        })
        emit('close')
        return
      }
    }
    emit('saved', saved)
    showToast({ message: '저장했습니다.' })
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
    :title="mode === 'edit' ? '슬롯 수정' : '슬롯 추가'"
    :close-on-backdrop="!dirty"
    @close="emit('close')"
  >
    <form class="form" novalidate @submit.prevent="save">
      <p v-if="formError" class="form__error" role="alert">{{ formError }}</p>
      <div class="form__grid">
        <Select v-model="draft.roomId" label="강의실" :options="roomOptions" />
        <Select v-model="draft.day" label="요일" :options="DAY_OPTIONS" />
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
        <Input v-model="draft.subject" label="과목명" :max-bytes="SUBJ_MAX" />
        <Input v-model="draft.professor" label="교수" :max-bytes="PROF_MAX" />
        <Select v-model="draft.type" label="유형" :options="TYPE_OPTIONS" />
      </div>
      <p v-if="value?.source === 1" class="form__hint">
        저장하면 이 슬롯은 수동 편집으로 바뀌어 CSV 임포트에 덮이지 않습니다.
      </p>
    </form>
    <template #footer>
      <Button
        v-if="removable && mode === 'edit'"
        variant="ghost"
        class="form__remove"
        @click="emit('remove')"
        >삭제</Button
      >
      <Button variant="secondary" @click="emit('close')">취소</Button>
      <Button :loading="saving" @click="save">저장</Button>
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
.form__remove {
  margin-right: auto;
}
</style>
