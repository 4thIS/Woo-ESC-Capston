<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Select from '@/components/ui/Select.vue'
import Table from '@/components/ui/Table.vue'
import { showToast } from '@/components/ui/toast'
import SlotForm from '@/components/domain/SlotForm.vue'
import SlotGroupForm from '@/components/domain/SlotGroupForm.vue'
import SourceBadge from '@/components/domain/SourceBadge.vue'
import TypeBadge from '@/components/domain/TypeBadge.vue'
import type { DotState } from '@/components/domain/OutboxDot.vue'
import { groupDot, groupSlots, type SlotGroup } from '@/components/domain/slotGroups'
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
  csv: []
}>()

// 호수 필터는 트리가 한다 — 블록에는 요일·유형만 (admin-rooms.md)
const ALL = { value: 0, label: '전체' }
const day = ref(0)
const type = ref(0)
const order = (roomId: number) => props.rooms.findIndex((r) => r.id === roomId)
// 연속 교시는 한 줄 (admin-rooms.md 「연속 교시 묶음」) — 저장은 교시마다 그대로, 목록에서만 묶는다
type Row = SlotGroup & { first: SlotWithRoom }
const rows = computed<Row[]>(() =>
  groupSlots(
    props.slots.filter(
      (s) => (!day.value || s.day === day.value) && (!type.value || s.type === type.value),
    ),
  )
    .sort((a, b) => order(a.room_id) - order(b.room_id) || a.day - b.day || a.start - b.start)
    .map((g) => ({ ...g, first: g.slots[0] })),
)
const COLUMNS = [
  { key: 'room', label: '호수', width: '72px' },
  { key: 'day', label: '요일', width: '56px' },
  { key: 'time', label: '시간', width: '168px' },
  { key: 'subject', label: '과목명' },
  { key: 'professor', label: '교수', width: '96px' },
  { key: 'type', label: '유형', width: '80px' },
  { key: 'source', label: '출처', width: '64px' },
  { key: 'actions', label: '작업', width: '104px', align: 'right' as const },
]
const asG = (row: Record<string, unknown>) => row as unknown as Row
const span = (s: SlotWithRoom) => `${hm(s.s_h, s.s_m)}–${hm(s.e_h, s.e_m)}`
const mm = (m: number) => hm(Math.floor(m / 60), m % 60)
/** 시간 칸 아래 한 줄 — '3교시 · 50분 + 쉬는 10분' */
function periodsNote(g: SlotGroup): string {
  if (g.slots.length === 1) return ''
  const n = `${g.slots.length}교시`
  return g.uniform ? `${n} · ${g.periodMin}분 + 쉬는 ${g.gapMin}분` : n
}
const roomLabel = (r: RoomOut) => `${props.label(r.id)}호`

// 추가·수정은 같은 폼 — 페이지2 셀 편집도 이 폼이다 (검증이 경로마다 갈라지지 않게)
const formOpen = ref(false)
const editing = ref<SlotWithRoom | null>(null)
function openForm(s: SlotWithRoom | null) {
  editing.value = s
  formOpen.value = true
  emit('changed') // 겹침 검사(existing)가 최신 슬롯을 보게 — 다른 관리자가 넣은 같은 키를 모르고 덮지 않도록
}
// 줄의 수정 — 한 교시짜리는 지금 폼, 여러 교시면 묶음 폼(시작 · 교시 수 · 한 교시)
const editingGroup = ref<SlotGroup | null>(null)
function editRow(g: SlotGroup) {
  if (g.slots.length === 1) return openForm(g.slots[0])
  editingGroup.value = g
  emit('changed')
}
// 저장한 행이 요일·유형 필터에 가려지면 필터를 푼다 — 행과 점이 보여야 결과를 안다
const reveal = ref<string | null>(null)
watch(
  () => props.slots,
  (slots) => {
    const k = reveal.value
    if (!k || !slots.some((s) => slotKey(s) === k)) return
    reveal.value = null
    if (!rows.value.some((r) => r.slots.some((s) => slotKey(s) === k))) day.value = type.value = 0
  },
)
function onSaved(r: SavedRow) {
  reveal.value = r.key
  emit('saved', r)
  emit('changed')
}

// 지우기 — 교시 하나 또는 묶음 전체(한 트랜잭션). 없는 키는 서버가 조용히 넘긴다(멱등)
const removing = ref<SlotWithRoom[] | null>(null)
const busy = ref(false)
function removeRow(g: SlotGroup) {
  editingGroup.value = null
  removing.value = g.slots
}
const removeLines = computed(() => {
  const list = removing.value
  if (!list?.length) return []
  const f = list[0]
  const l = list[list.length - 1]
  const head = `${props.label(f.room_id)}호 ${DAYS[f.day - 1]} ${f.subject}`
  return list.length === 1
    ? [`${head} ${hm(f.s_h, f.s_m)}`]
    : [`${head} — ${list.length}교시 ${hm(f.s_h, f.s_m)}–${hm(l.e_h, l.e_m)}`]
})
async function remove() {
  const list = removing.value
  if (!list?.length || busy.value) return
  busy.value = true
  try {
    const roomId = list[0].room_id
    if (list.length === 1) await roomsApi.deleteSlot(roomId, list[0])
    else
      await roomsApi.replaceSlots(roomId, {
        remove: list.map(({ day, s_h, s_m }) => ({ day, s_h, s_m })),
        put: [],
      })
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
        >+ 시간표 추가</Button
      >
    </header>
    <Table
      :columns="COLUMNS"
      :rows="rows as unknown as Record<string, unknown>[]"
      row-key="key"
      :loading="loading"
      expandable
      tall
    >
      <template #empty>
        <EmptyState v-if="!rooms.length" message="위에서 강의실을 고르세요" />
        <EmptyState v-else-if="day || type" message="조건에 맞는 슬롯이 없습니다" />
        <EmptyState
          v-else
          message="이 건물에 등록된 시간표가 없습니다"
          :actions="[
            { label: 'CSV 가져오기', onClick: () => emit('csv') },
            { label: '시간표 추가', variant: 'primary', onClick: () => openForm(null) },
          ]"
        />
      </template>
      <template #cell-room="{ row }">
        <!-- 호수를 누르면 그 강의실의 한 주 (페이지2) -->
        <RouterLink class="blk__room num" :to="`/rooms/${asG(row).room_id}/week`">{{
          label(asG(row).room_id)
        }}</RouterLink>
      </template>
      <template #cell-day="{ row }">{{ DAYS[asG(row).day - 1] }}</template>
      <template #cell-time="{ row }">
        <span class="blk__time">
          <b class="num">{{ mm(asG(row).start) }} – {{ mm(asG(row).end) }}</b>
          <small v-if="periodsNote(asG(row))">{{ periodsNote(asG(row)) }}</small>
        </span>
      </template>
      <template #cell-subject="{ row }">{{ asG(row).first.subject }}</template>
      <template #cell-professor="{ row }">{{ asG(row).first.professor || '—' }}</template>
      <template #cell-type="{ row }"><TypeBadge :type="asG(row).first.type" /></template>
      <template #cell-source="{ row }"><SourceBadge :source="asG(row).first.source" /></template>
      <template #cell-actions="{ row }">
        <div class="blk__actions">
          <RowDot
            :state="groupDot(asG(row), states)"
            :busy="resyncing.has(asG(row).room_id)"
            @resync="emit('resync', asG(row).room_id, asG(row).key)"
          />
          <Button variant="ghost" size="sm" @click="editRow(asG(row))">수정</Button>
          <Button variant="ghost" size="sm" @click="removeRow(asG(row))">삭제</Button>
        </div>
      </template>
      <!-- 펼치면 교시별 — 한 교시만 휴강 · 보강할 때 -->
      <template #expanded="{ row }">
        <ul class="blk__periods">
          <li v-for="(s, i) in asG(row).slots" :key="slotKey(s)" class="blk__period">
            <span class="num">{{ i + 1 }}교시 {{ span(s) }}</span>
            <span class="blk__actions">
              <RowDot
                :state="states.get(slotKey(s))"
                :busy="resyncing.has(s.room_id)"
                @resync="emit('resync', s.room_id, slotKey(s))"
              />
              <Button variant="ghost" size="sm" @click="openForm(s)">수정</Button>
              <Button variant="ghost" size="sm" @click="removing = [s]">삭제</Button>
            </span>
          </li>
        </ul>
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
    <SlotGroupForm
      :open="!!editingGroup"
      :group="editingGroup"
      :room-label="editingGroup ? `${label(editingGroup.room_id)}호` : ''"
      :existing="slots"
      @close="editingGroup = null"
      @saved="onSaved"
      @stale="emit('changed')"
      @remove="editingGroup && removeRow(editingGroup)"
    />
    <ConfirmModal
      :open="!!removing"
      :title="(removing?.length ?? 0) > 1 ? '수업 삭제' : '슬롯 삭제'"
      :lines="removeLines"
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
.blk__time {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  /* 두 줄 칸 — 행 테두리에 글자가 붙지 않게 (Table td 는 위아래 여백이 0) */
  padding-block: var(--space-2);
}
.blk__time small {
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.blk__periods {
  display: grid;
  gap: var(--space-1);
  margin: 0;
  padding: 0 0 0 var(--space-6);
  list-style: none;
}
.blk__period {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 32px;
  color: var(--text-2);
}
</style>
