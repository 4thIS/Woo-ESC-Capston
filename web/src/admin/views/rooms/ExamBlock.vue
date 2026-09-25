<script setup lang="ts">
import { computed, ref } from 'vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Table from '@/components/ui/Table.vue'
import { showToast } from '@/components/ui/toast'
import ExamForm from '@/components/domain/ExamForm.vue'
import type { DotState } from '@/components/domain/OutboxDot.vue'
import { conflictMessage, examKey, type SavedRow } from '@/components/domain/rules'
import { ApiError } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { ExamWithRoom, RoomOut } from '@/api/types'
import ConfirmModal from '../../ConfirmModal.vue'
import { groupExams, roomsLabel, type ExamGroup } from '../../roomsView'
import RowDot from './RowDot.vue'

const props = withDefaults(
  defineProps<{
    rooms: RoomOut[]
    label: (roomId: number) => string
    exams: ExamWithRoom[]
    states: Map<string, DotState>
    loading: boolean
    /** 재전송 응답을 기다리는 강의실 id — 그 방 행들의 재전송 버튼을 잠근다 */
    resyncing?: Set<number>
  }>(),
  { resyncing: () => new Set<number>() },
)
const emit = defineEmits<{
  saved: [row: SavedRow]
  changed: []
  resync: [roomId: number, key: string]
}>()

const order = (roomId: number) => props.rooms.findIndex((r) => r.id === roomId)
const groups = computed(() => groupExams(props.exams, order))
const COLUMNS = [
  { key: 'rooms', label: '호수' },
  { key: 'date_start', label: '시작일', width: '120px' },
  { key: 'date_end', label: '종료일', width: '120px' },
  { key: 'count', label: '강의실', width: '80px', align: 'right' as const },
]
const asG = (row: Record<string, unknown>) => row as unknown as ExamGroup
const roomLabel = (r: RoomOut) => `${props.label(r.id)}호`

// 추가 — 강의실을 고르는 것은 트리. 폼에는 날짜만, 대상은 고른 방 전부 (admin-rooms.md 시험기간)
const formOpen = ref(false)
const editing = ref<ExamWithRoom | null>(null)
const formRooms = computed(() =>
  editing.value ? props.rooms.filter((r) => r.id === editing.value!.room_id) : props.rooms,
)
function openForm(x: ExamWithRoom | null) {
  editing.value = x
  formOpen.value = true
}

const removing = ref<ExamWithRoom | null>(null)
const busy = ref(false)
async function remove() {
  const x = removing.value
  if (!x || busy.value) return
  busy.value = true
  try {
    await roomsApi.deleteExam(x.room_id, x.id)
    showToast({ message: '지웠습니다.' })
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 409) showToast({ tone: 'danger', message: conflictMessage(e) })
    else if (e.status === 404)
      showToast({ tone: 'danger', message: '이미 바뀐 시험기간입니다. 목록을 새로 불러옵니다.' })
    else if (e.status !== 401 && e.status !== 403) showToast({ tone: 'danger', message: e.message })
  } finally {
    busy.value = false
    removing.value = null
    emit('changed')
  }
}
</script>

<template>
  <section class="blk" aria-labelledby="blk-exams">
    <header class="blk__head">
      <h2 id="blk-exams" class="blk__title">시험기간</h2>
      <!-- 버튼이 대상 수를 말한다 — 트리에서 4층을 누르면 그 층 전체가 대상 -->
      <Button class="blk__add" :disabled="!rooms.length" @click="openForm(null)"
        >+ 선택한 {{ rooms.length }}곳에 기간 추가</Button
      >
    </header>
    <Table
      expandable
      :columns="COLUMNS"
      :rows="groups as unknown as Record<string, unknown>[]"
      :loading="loading"
    >
      <template #empty>
        <EmptyState v-if="!rooms.length" message="위에서 강의실을 고르세요" />
        <EmptyState
          v-else
          message="등록된 항목이 없습니다"
          :actions="[{ label: '기간 추가', variant: 'primary', onClick: () => openForm(null) }]"
        />
      </template>
      <template #cell-rooms="{ row }"
        ><span class="num">{{
          roomsLabel(asG(row).items.map((x) => label(x.room_id)))
        }}</span></template
      >
      <template #cell-date_start="{ row }"
        ><span class="num">{{ asG(row).date_start }}</span></template
      >
      <template #cell-date_end="{ row }"
        ><span class="num">{{ asG(row).date_end }}</span></template
      >
      <template #cell-count="{ row }"
        ><span class="num">{{ asG(row).items.length }}곳</span></template
      >
      <template #expanded="{ row }">
        <ul class="blk__items">
          <li v-for="x in asG(row).items" :key="x.id" class="blk__item">
            <span class="num">{{ label(x.room_id) }}호</span>
            <RowDot
              :state="states.get(examKey(x.id))"
              :busy="resyncing.has(x.room_id)"
              @resync="emit('resync', x.room_id, examKey(x.id))"
            />
            <Button variant="ghost" size="sm" @click="openForm(x)">수정</Button>
            <Button variant="ghost" size="sm" @click="removing = x">삭제</Button>
          </li>
        </ul>
      </template>
    </Table>
    <ExamForm
      :open="formOpen"
      :rooms="formRooms"
      :value="editing"
      :room-label="roomLabel"
      @close="formOpen = false"
      @saved="(r) => emit('saved', r)"
      @done="emit('changed')"
    />
    <ConfirmModal
      :open="!!removing"
      title="시험기간 삭제"
      :lines="
        removing
          ? [`${label(removing.room_id)}호 시험기간 ${removing.date_start} ~ ${removing.date_end}`]
          : []
      "
      :loading="busy"
      @confirm="remove"
      @close="removing = null"
    />
  </section>
</template>

<style scoped>
.blk {
  overflow: hidden;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.blk__head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
}
.blk__title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.blk__add {
  margin-left: auto;
}
.blk__items {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-5);
  margin: 0;
  padding: 0;
  list-style: none;
}
.blk__item {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}
</style>
