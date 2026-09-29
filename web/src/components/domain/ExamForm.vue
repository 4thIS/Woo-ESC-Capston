<script setup lang="ts">
import { computed, reactive, ref, useId, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Modal from '@/components/ui/Modal.vue'
import { showToast } from '@/components/ui/toast'
import { ApiError } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { ExamIn, ExamWithRoom, RoomOut } from '@/api/types'
import { conflictMessage, examKey, type SavedRow } from './rules'

// 저장 버튼은 Modal 바닥(폼 밖)에 있다 — form 속성으로 이어 Enter 가 폼을 제출하게 (submit 한 길만)
const formId = useId()

const props = withDefaults(
  defineProps<{
    open: boolean
    /** 대상 — 추가는 트리에서 고른 방 전부, 수정은 그 방 하나 (폼 안에 강의실 목록을 두지 않는다) */
    rooms: RoomOut[]
    value?: ExamWithRoom | null
    roomLabel?: (r: RoomOut) => string
  }>(),
  { value: null, roomLabel: (r: RoomOut) => `${r.room}호` },
)
const emit = defineEmits<{ close: []; saved: [row: SavedRow]; done: [] }>()

const form = reactive({ start: '', end: '' })
const error = ref('')
const running = ref(false)
const done = ref(0)
const total = ref(0)
const initial = ref('')
const dirty = computed(() => JSON.stringify(form) !== initial.value)
const label = computed(() => (props.value ? '저장' : `선택한 ${props.rooms.length}곳에 기간 추가`))
const progress = computed(() => `${done.value}/${total.value || props.rooms.length} 적용 중`)
const targetText = computed(() => {
  const names = props.rooms.map((r) => props.roomLabel(r))
  return names.length <= 5
    ? names.join(', ')
    : `${names.slice(0, 5).join(', ')} 외 ${names.length - 5}곳`
})

watch(
  () => props.open,
  (open) => {
    if (!open) return
    form.start = props.value?.date_start ?? ''
    form.end = props.value?.date_end ?? ''
    error.value = ''
    initial.value = JSON.stringify(form)
  },
  { immediate: true },
)

function close() {
  if (!running.value) emit('close')
}

async function submit() {
  if (running.value || !props.rooms.length) return
  if (!form.start || !form.end) {
    error.value = '시작일과 종료일을 고르세요'
    return
  }
  if (form.end < form.start) {
    error.value = '종료일은 시작일과 같거나 뒤여야 합니다'
    return
  }
  error.value = ''
  if (await run([...props.rooms], { date_start: form.start, date_end: form.end }, props.value?.id))
    emit('close')
}

/** 방마다 POST — 벌크 엔드포인트가 없다. 일부 실패해도 되돌리지 않는다: 되돌리는 DELETE 도 실패할 수 있어
 * 상태가 더 불분명해진다. 성공분은 두고 실패한 방만 재시도로 남긴다 (admin-rooms.md 시험기간) */
async function run(list: RoomOut[], body: ExamIn, id?: number): Promise<boolean> {
  running.value = true
  total.value = list.length
  done.value = 0
  const failed: RoomOut[] = []
  let reason = '' // 409(id 소진 등)는 재시도해도 같다 — 첫 사유를 Toast 에 붙인다 (admin-rooms.md §3)
  try {
    for (const r of list) {
      try {
        const res = await roomsApi.saveExam(r.id, id ? { ...body, id } : body)
        emit('saved', { roomId: r.id, key: examKey(res.id ?? id!), outboxIds: res.outbox_ids })
      } catch (e) {
        if (!(e instanceof ApiError)) throw e
        if (e.status === 401 || e.status === 403) return false // 로그인 화면으로 간다
        if (e.status === 409 && !reason) reason = conflictMessage(e)
        failed.push(r)
      }
      done.value++
    }
  } finally {
    running.value = false
    emit('done')
  }
  if (!failed.length)
    showToast({
      message: list.length > 1 ? `${list.length}곳에 시험기간을 넣었습니다.` : '저장했습니다.',
    })
  else
    showToast({
      tone: 'danger',
      message: `${list.length}개 중 ${list.length - failed.length}개 적용 · ${failed.map((r) => props.roomLabel(r)).join(', ')} 실패${reason ? ` · ${reason}` : ''}`,
      action: { label: '재시도', onClick: () => void run(failed, body, id) },
    })
  return true
}
</script>

<template>
  <Modal
    :open="open"
    :title="value ? '시험기간 수정' : '시험기간 추가'"
    :close-on-backdrop="!dirty && !running"
    @close="close"
  >
    <form :id="formId" class="form" novalidate @submit.prevent="submit">
      <p class="form__target">
        대상 <span class="num">{{ rooms.length }}</span
        >곳 · {{ targetText || '없음' }}
      </p>
      <div class="form__grid">
        <Input v-model="form.start" label="시작일" type="date" class="num" required />
        <Input
          v-model="form.end"
          label="종료일"
          type="date"
          class="num"
          required
          :error="error || undefined"
        />
      </div>
    </form>
    <template #footer>
      <Button variant="secondary" :disabled="running" @click="close">취소</Button>
      <!-- 진행 라벨 폭은 Button 이 가장 긴 자리로 미리 잡는다 (Task 3) -->
      <Button
        class="form__submit"
        :loading="running"
        :loading-label="progress"
        :disabled="!rooms.length"
        type="submit"
        :form="formId"
        >{{ label }}</Button
      >
    </template>
  </Modal>
</template>

<style scoped>
.form__target {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.form__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3) var(--space-4);
}
</style>
