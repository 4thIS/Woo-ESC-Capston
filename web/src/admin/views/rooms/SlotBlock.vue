<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Select from '@/components/ui/Select.vue'
import Table from '@/components/ui/Table.vue'
import { showToast } from '@/components/ui/toast'
import SlotForm from '@/components/domain/SlotForm.vue'
import SourceBadge from '@/components/domain/SourceBadge.vue'
import TypeBadge from '@/components/domain/TypeBadge.vue'
import type { DotState } from '@/components/domain/OutboxDot.vue'
import { DAYS, DAY_OPTIONS, TYPE_OPTIONS, slotKey, type SavedRow } from '@/components/domain/rules'
import { ApiError } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { RoomOut, SlotWithRoom } from '@/api/types'
import { hm } from '@/lib/time'
import ConfirmModal from '../../ConfirmModal.vue'
import RowDot from './RowDot.vue'

const props = withDefaults(
  defineProps<{
    rooms: RoomOut[]
    label: (roomId: number) => string
    slots: SlotWithRoom[]
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

// 호수 필터는 트리가 한다 — 블록에는 요일·유형만 (admin-rooms.md)
const ALL = { value: 0, label: '전체' }
const day = ref(0)
const type = ref(0)
const order = (roomId: number) => props.rooms.findIndex((r) => r.id === roomId)
const rows = computed(() =>
  props.slots
    .filter((s) => (!day.value || s.day === day.value) && (!type.value || s.type === type.value))
    .sort(
      (a, b) =>
        order(a.room_id) - order(b.room_id) || a.day - b.day || a.s_h - b.s_h || a.s_m - b.s_m,
    )
    .map((s) => ({ ...s, key: slotKey(s) })),
)
const COLUMNS = [
  { key: 'room', label: '호수', width: '72px' },
  { key: 'day', label: '요일', width: '56px' },
  { key: 'start', label: '시작', width: '64px' },
  { key: 'end', label: '종료', width: '64px' },
  { key: 'subject', label: '과목명' },
  { key: 'professor', label: '교수', width: '96px' },
  { key: 'type', label: '유형', width: '80px' },
  { key: 'source', label: '출처', width: '64px' },
  { key: 'actions', label: '작업', width: '104px', align: 'right' as const },
]
const asS = (row: Record<string, unknown>) => row as unknown as SlotWithRoom & { key: string }
const roomLabel = (r: RoomOut) => `${props.label(r.id)}호`

// 추가·수정은 같은 폼 — 페이지2 셀 편집도 이 폼이다 (검증이 경로마다 갈라지지 않게)
const formOpen = ref(false)
const editing = ref<SlotWithRoom | null>(null)
function openForm(s: SlotWithRoom | null) {
  editing.value = s
  formOpen.value = true
  emit('changed') // 겹침 검사(existing)가 최신 슬롯을 보게 — 다른 관리자가 넣은 같은 키를 모르고 덮지 않도록
}
// 저장한 행이 요일·유형 필터에 가려지면 필터를 푼다 — 행과 점이 보여야 결과를 안다
const reveal = ref<string | null>(null)
watch(
  () => props.slots,
  (slots) => {
    const k = reveal.value
    if (!k || !slots.some((s) => slotKey(s) === k)) return
    reveal.value = null
    if (!rows.value.some((r) => r.key === k)) day.value = type.value = 0
  },
)
function onSaved(r: SavedRow) {
  reveal.value = r.key
  emit('saved', r)
  emit('changed')
}

const removing = ref<SlotWithRoom | null>(null)
const busy = ref(false)
async function remove() {
  const s = removing.value
  if (!s || busy.value) return
  busy.value = true
  try {
    await roomsApi.deleteSlot(s.room_id, s) // 없는 키는 서버가 조용히 넘긴다(멱등)
    showToast({ message: '지웠습니다.' })
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status !== 401 && e.status !== 403) showToast({ tone: 'danger', message: e.message })
  } finally {
    busy.value = false
    removing.value = null
    emit('changed')
  }
}
</script>

<template>
  <section class="blk" aria-labelledby="blk-slots">
    <header class="blk__head">
      <h2 id="blk-slots" class="blk__title">시간표</h2>
      <Select
        v-model="day"
        label="요일"
        size="sm"
        :options="[ALL, ...DAY_OPTIONS]"
        class="blk__filter"
      />
      <Select
        v-model="type"
        label="유형"
        size="sm"
        :options="[ALL, ...TYPE_OPTIONS]"
        class="blk__filter"
      />
      <Button class="blk__add" :disabled="!rooms.length" @click="openForm(null)"
        >+ 슬롯 추가</Button
      >
    </header>
    <Table
      :columns="COLUMNS"
      :rows="rows as unknown as Record<string, unknown>[]"
      row-key="key"
      :loading="loading"
    >
      <template #empty>
        <EmptyState v-if="!rooms.length" message="위에서 강의실을 고르세요" />
        <EmptyState v-else-if="day || type" message="조건에 맞는 슬롯이 없습니다" />
        <EmptyState
          v-else
          message="이 건물에 등록된 시간표가 없습니다"
          :actions="[{ label: '슬롯 추가', variant: 'primary', onClick: () => openForm(null) }]"
        />
      </template>
      <template #cell-room="{ row }">
        <!-- 호수를 누르면 그 강의실의 한 주 (페이지2) -->
        <RouterLink class="blk__room num" :to="`/rooms/${asS(row).room_id}/week`">{{
          label(asS(row).room_id)
        }}</RouterLink>
      </template>
      <template #cell-day="{ row }">{{ DAYS[asS(row).day - 1] }}</template>
      <template #cell-start="{ row }"
        ><span class="num">{{ hm(asS(row).s_h, asS(row).s_m) }}</span></template
      >
      <template #cell-end="{ row }"
        ><span class="num">{{ hm(asS(row).e_h, asS(row).e_m) }}</span></template
      >
      <template #cell-professor="{ row }">{{ asS(row).professor || '—' }}</template>
      <template #cell-type="{ row }"><TypeBadge :type="asS(row).type" /></template>
      <template #cell-source="{ row }"><SourceBadge :source="asS(row).source" /></template>
      <template #cell-actions="{ row }">
        <div class="blk__actions">
          <RowDot
            :state="states.get(asS(row).key)"
            :busy="resyncing.has(asS(row).room_id)"
            @resync="emit('resync', asS(row).room_id, asS(row).key)"
          />
          <Button variant="ghost" size="sm" @click="openForm(asS(row))">수정</Button>
          <Button variant="ghost" size="sm" @click="removing = asS(row)">삭제</Button>
        </div>
      </template>
    </Table>
    <SlotForm
      :open="formOpen"
      :mode="editing ? 'edit' : 'create'"
      :rooms="rooms"
      :room-label="roomLabel"
      :value="editing"
      :preset="rooms[0] ? { room_id: rooms[0].id } : null"
      :existing="slots"
      @close="formOpen = false"
      @saved="onSaved"
      @stale="emit('changed')"
    />
    <ConfirmModal
      :open="!!removing"
      title="슬롯 삭제"
      :lines="
        removing
          ? [
              `${label(removing.room_id)}호 ${DAYS[removing.day - 1]} ${hm(removing.s_h, removing.s_m)} ${removing.subject}`,
            ]
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
  align-items: flex-end;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
}
.blk__title {
  align-self: center;
  margin: 0 var(--space-2) 0 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.blk__filter {
  width: 120px;
}
.blk__add {
  margin-left: auto;
}
.blk__room {
  color: var(--text-1);
  font-weight: var(--font-weight-medium);
}
.blk__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-1);
}
</style>
