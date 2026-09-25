<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Table from '@/components/ui/Table.vue'
import { showToast } from '@/components/ui/toast'
import ResvForm from '@/components/domain/ResvForm.vue'
import TypeBadge from '@/components/domain/TypeBadge.vue'
import type { DotState } from '@/components/domain/OutboxDot.vue'
import { DAYS, conflictMessage, resvKey, type SavedRow } from '@/components/domain/rules'
import { ApiError } from '@/api/client'
import { adminApi } from '@/api/admin'
import { roomsApi } from '@/api/rooms'
import type { ResvWithRoom, RoomOut } from '@/api/types'
import { dayOfDate, hm, kstDateStr } from '@/lib/time'
import ConfirmModal from '../../ConfirmModal.vue'
import { resvDot } from '../../roomsView'
import RowDot from './RowDot.vue'

const props = withDefaults(
  defineProps<{
    rooms: RoomOut[]
    label: (roomId: number) => string
    resv: ResvWithRoom[]
    states: Map<string, DotState>
    loading: boolean
    /** 재전송 응답을 기다리는 행 key — 그 행의 재전송 버튼을 잠근다 */
    resyncing?: Set<string>
  }>(),
  { resyncing: () => new Set<string>() },
)
const emit = defineEmits<{
  saved: [row: SavedRow]
  changed: []
  resync: [roomId: number, key: string]
}>()

const today = kstDateStr(new Date())
// 예약 블록은 approved 만 — 신청은 위의 신청 대기, 거절·취소·만료는 그리지 않는다 (admin-rooms.md)
const rows = computed(() =>
  props.resv
    .filter((r) => r.status === 'approved')
    .sort(
      (a, b) =>
        a.date.localeCompare(b.date) || a.s_h - b.s_h || a.s_m - b.s_m || a.room_id - b.room_id,
    )
    .map((r) => ({ ...r, key: resvKey(r.id) })),
)
const COLUMNS = [
  { key: 'room', label: '호수', width: '72px' },
  { key: 'date', label: '날짜', width: '104px' },
  { key: 'day', label: '요일', width: '56px' },
  { key: 'start', label: '시작', width: '64px' },
  { key: 'end', label: '종료', width: '64px' },
  { key: 'subject', label: '사용 목적' },
  { key: 'who', label: '신청자', width: '96px' },
  { key: 'no', label: '학번', width: '88px' },
  { key: 'type', label: '유형', width: '80px' },
  { key: 'actions', label: '작업', width: '104px', align: 'right' as const },
]
const asV = (row: Record<string, unknown>) => row as unknown as ResvWithRoom & { key: string }
const roomLabel = (r: RoomOut) => `${props.label(r.id)}호`

const formOpen = ref(false)
const editing = ref<ResvWithRoom | null>(null)
// 수정은 관리자가 넣은 approved 만 — 학생 신청은 승인·거절·취소로 다룬다 (서버도 409)
function openForm(r: ResvWithRoom | null) {
  if (r && (r.requester || r.status !== 'approved')) return
  editing.value = r
  formOpen.value = true
}
function onSaved(r: SavedRow) {
  emit('saved', r)
  emit('changed')
}

// 학생 예약은 지우지 않고 취소한다 — 학생 화면에 '취소됨'으로 남는다. 관리자 예약은 삭제 (설계 판정)
const removing = ref<ResvWithRoom | null>(null)
const busy = ref(false)
const removeLines = computed(() => {
  const r = removing.value
  if (!r) return []
  const what = `${props.label(r.room_id)}호 ${r.date} ${hm(r.s_h, r.s_m)}–${hm(r.e_h, r.e_m)} ${r.subject}`
  return r.requester ? [what, `${r.requester.name} 학생 화면에 취소됨으로 보입니다.`] : [what]
})
async function remove() {
  const r = removing.value
  if (!r || busy.value) return
  busy.value = true
  try {
    if (r.requester) await adminApi.cancelResv(r.id)
    else await roomsApi.deleteResv(r.room_id, r.id)
    showToast({ message: r.requester ? '예약을 취소했습니다.' : '지웠습니다.' })
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 409) showToast({ tone: 'danger', message: conflictMessage(e) })
    else if (e.status === 404)
      showToast({ tone: 'danger', message: '이미 바뀐 예약입니다. 목록을 새로 불러옵니다.' })
    else if (e.status !== 401 && e.status !== 403) showToast({ tone: 'danger', message: e.message })
  } finally {
    busy.value = false
    removing.value = null
    emit('changed')
  }
}
</script>

<template>
  <section class="blk" aria-labelledby="blk-resv">
    <header class="blk__head">
      <h2 id="blk-resv" class="blk__title">예약</h2>
      <Button class="blk__add" :disabled="!rooms.length" @click="openForm(null)"
        >+ 예약 추가</Button
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
        <EmptyState
          v-else
          message="등록된 항목이 없습니다"
          :actions="[{ label: '예약 추가', variant: 'primary', onClick: () => openForm(null) }]"
        />
      </template>
      <template #cell-room="{ row }">
        <RouterLink class="blk__room num" :to="`/rooms/${asV(row).room_id}/week`">{{
          label(asV(row).room_id)
        }}</RouterLink>
      </template>
      <template #cell-date="{ row }"
        ><span class="num">{{ asV(row).date }}</span></template
      >
      <!-- 요일은 날짜에서 계산한 읽기 전용 값 -->
      <template #cell-day="{ row }">{{ DAYS[dayOfDate(asV(row).date) - 1] }}</template>
      <template #cell-start="{ row }"
        ><span class="num">{{ hm(asV(row).s_h, asV(row).s_m) }}</span></template
      >
      <template #cell-end="{ row }"
        ><span class="num">{{ hm(asV(row).e_h, asV(row).e_m) }}</span></template
      >
      <!-- 신청자는 requested_by 에서 서버가 풀어 준 이름 — professor 를 쓰지 않는다 -->
      <template #cell-who="{ row }">{{ asV(row).requester?.name ?? '—' }}</template>
      <template #cell-no="{ row }"
        ><span class="num">{{ asV(row).requester?.student_no ?? '—' }}</span></template
      >
      <template #cell-type="{ row }"><TypeBadge :type="asV(row).type" /></template>
      <template #cell-actions="{ row }">
        <div class="blk__actions">
          <RowDot
            :state="resvDot(asV(row), states.get(asV(row).key), today)"
            :busy="resyncing.has(asV(row).key)"
            @resync="emit('resync', asV(row).room_id, asV(row).key)"
          />
          <Button v-if="asV(row).requester" variant="ghost" size="sm" @click="removing = asV(row)"
            >취소</Button
          >
          <template v-else>
            <Button variant="ghost" size="sm" @click="openForm(asV(row))">수정</Button>
            <Button variant="ghost" size="sm" @click="removing = asV(row)">삭제</Button>
          </template>
        </div>
      </template>
    </Table>
    <ResvForm
      :open="formOpen"
      :mode="editing ? 'edit' : 'create'"
      :rooms="rooms"
      :room-label="roomLabel"
      :value="editing"
      :preset="rooms[0] ? { room_id: rooms[0].id } : null"
      :existing="resv"
      @close="formOpen = false"
      @saved="onSaved"
      @stale="emit('changed')"
    />
    <ConfirmModal
      :open="!!removing"
      :title="removing?.requester ? '예약 취소' : '예약 삭제'"
      :lines="removeLines"
      :confirm-label="removing?.requester ? '예약 취소' : '삭제'"
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
