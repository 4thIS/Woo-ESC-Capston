<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import { showToast } from '@/components/ui/toast'
import OutboxDot from '@/components/domain/OutboxDot.vue'
import ResvForm from '@/components/domain/ResvForm.vue'
import RoomTree from '@/components/domain/RoomTree.vue'
import SlotForm from '@/components/domain/SlotForm.vue'
import SlotGroupForm from '@/components/domain/SlotGroupForm.vue'
import { groupDot, type SlotGroup } from '@/components/domain/slotGroups'
import { DAYS, conflictMessage, resvKey, slotKey, type SavedRow } from '@/components/domain/rules'
import { ApiError } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { ResvWithRoom, SlotWithRoom } from '@/api/types'
import { addDays, hm, kstDateStr, md, mondayOf } from '@/lib/time'
import { useResource } from '@/lib/useResource'
import ConfirmModal from '../ConfirmModal.vue'
import { useOutboxTracker } from '../outboxTrack'
import { resvDot } from '../roomsView'
import { nightPref, picked, weekMonday, weekRoom, weekendPref } from '../selection'
import { needsNight, needsWeekend, weekBlocks, type Placed } from '../weekView'
import RowDot from './rooms/RowDot.vue'
import WeekGrid from './week/WeekGrid.vue'
import { appliedTick } from '../assistant/store'

const props = defineProps<{ roomId?: string }>()
const router = useRouter()
const today = kstDateStr(new Date())

const master = useResource(async () => {
  const [buildings, rooms] = await Promise.all([roomsApi.buildings(), roomsApi.rooms()])
  return { buildings, rooms }
})
const id = computed(() => (props.roomId ? Number(props.roomId) : null))
const room = computed(() => master.data.value?.rooms.find((r) => r.id === id.value) ?? null)
const noRooms = computed(() => !!master.data.value && !master.data.value.rooms.length)

// /week — 마지막으로 본 강의실 → 페이지1 트리의 첫 방 → 첫 강의실
watch(
  () => [master.data.value, id.value] as const,
  ([d, rid]) => {
    if (!d || rid !== null) return
    const has = (x: number | null | undefined): x is number =>
      x != null && d.rooms.some((r) => r.id === x)
    const first = [...d.rooms].sort((a, b) => a.building_id - b.building_id || a.room - b.room)[0]
    const target = [weekRoom.value, picked.value[0], first?.id].find(has)
    if (target !== undefined) void router.replace(`/rooms/${target}/week`)
  },
  { immediate: true },
)
// 실제로 있는 강의실만 기억한다 — 주소창의 아무 숫자나 메뉴 링크가 되지 않게
watch(
  room,
  (r) => {
    if (r) weekRoom.value = r.id
  },
  { immediate: true },
)

// 강의실 하나만 본다 — 건물 단위 API 가 필요 없다. 세 번 불러 겹쳐 그린다
const res = useResource(
  async () => {
    const rid = id.value
    if (rid === null) return null
    const [slots, resv, exams] = await Promise.all([
      roomsApi.slots(rid),
      roomsApi.reservations(rid),
      roomsApi.exams(rid),
    ])
    return { rid, slots: slots.map((s) => ({ ...s, room_id: rid })), resv, exams }
  },
  { deps: id },
)
// AI 비서가 적용하면 다시 불러온다 — 덮개가 걷힐 때 새 블록이 보이게
watch(appliedTick, () => void res.reload())
// 지금 보는 방의 응답만 쓴다 — 방을 바꾼 직후 옛 방의 블록을 새 방 제목 아래 그리지 않는다
// (주는 화면이 거르므로 방만 맞으면 된다)
const fresh = computed(() =>
  res.data.value && res.data.value.rid === id.value ? res.data.value : undefined,
)
// 다른 학교·지워진 방은 404 — 권한 오류가 아니라 '없음'으로 다룬다 (서버가 존재를 숨긴다)
const notFound = computed(
  () =>
    (!!master.data.value && id.value !== null && !room.value) ||
    (!fresh.value && !res.loading.value && res.error.value?.status === 404),
)
// 첫 불러오기 실패는 빈 시간표가 아니다 — 격자 가운데 오류 안내 + 다시 불러오기
const failedRes = computed(() => {
  if (!master.data.value && master.error.value && !master.loading.value) return master
  if (id.value !== null && !fresh.value && res.error.value && !res.loading.value) return res
  return null
})
const loadingRes = computed(() => id.value !== null && !fresh.value && !failedRes.value)
for (const r of [master, res])
  // 다시 불러오기도 실패하면 Toast 를 쌓지 않는다 — 처음 실패할 때 한 번 (MasterView 와 같다)
  watch(r.error, (e, prev) => {
    if (e && !prev && ![401, 403, 404].includes(e.status))
      showToast({
        tone: 'danger',
        message: e.message,
        action: { label: '재시도', onClick: () => void r.reload() },
      })
  })

// 보고 있는 주 — 강의실을 바꿔도 유지(같은 주의 다른 강의실을 견주는 것이 가장 잦다). 주 이동은 서버를 부르지 않는다
const monday = computed(() => weekMonday.value ?? mondayOf(today))
const sunday = computed(() => addDays(monday.value, 6))
function shiftWeek(n: number) {
  weekMonday.value = addDays(monday.value, 7 * n)
}
const slots = computed<SlotWithRoom[]>(() => fresh.value?.slots ?? [])
const resv = computed<ResvWithRoom[]>(() => fresh.value?.resv ?? [])
const blocks = computed(() => weekBlocks(slots.value, resv.value, monday.value))
// 야간·주말 — 필요한 블록이 있으면 켠 채 시작, 사용자가 누르면 그 선택을 유지
const night = computed({
  get: () => nightPref.value ?? needsNight(blocks.value),
  set: (v: boolean) => (nightPref.value = v),
})
const weekend = computed({
  get: () => weekendPref.value ?? needsWeekend(blocks.value),
  set: (v: boolean) => (weekendPref.value = v),
})
// 빈 격자 자체가 정보 — 격자는 두고 가운데 안내
const empty = computed(
  () => !!fresh.value && !slots.value.length && !blocks.value.some((b) => b.resv),
)
/** 편집은 지금 방의 데이터가 있을 때만 — 겹침 검사가 빈 목록을 보고 통과하지 않게 */
const editable = computed(() => !!room.value && !!fresh.value)

// 저장 뒤 OutboxDot — 블록 우상단 점, 실패면 블록에 danger 2px 테두리 (취소는 테두리 없음)
const tracker = useOutboxTracker()
function saved(s: SavedRow) {
  if (room.value) tracker.track(s.key, room.value.building_id, s.outboxIds)
  void res.reload()
}
// 재전송은 방 단위 — 한 번의 sync 가 방 전체를 다시 보내므로 실패·취소로 보이는 다른 블록도 새 작업을 따라간다
const DEAD = ['failed', 'cancelled']
function resync(key: string) {
  const r = room.value
  if (!r) return
  const others = [...slots.value.map(slotKey), ...resv.value.map((v) => resvKey(v.id))].filter(
    (k) => k !== key && DEAD.includes(tracker.states.get(k) ?? ''),
  )
  void tracker.resync([key, ...others], r.id, r.building_id)
}
const dotOf = (p: Placed) =>
  p.resv
    ? resvDot(p.resv, tracker.states.get(p.key), today)
    : p.group
      ? groupDot(p.group, tracker.states)
      : tracker.states.get(p.key)

// ---- 편집 — 페이지1과 같은 폼. 드래그로 만들지 않는다 (값은 숫자로) ----
const slotOpen = ref(false)
const slotEditing = ref<SlotWithRoom | null>(null)
const slotPreset = ref<{ room_id: number; day?: number; s_h?: number; s_m?: number } | null>(null)
function openSlot(s: SlotWithRoom | null, at?: { day: number; t: number }) {
  if (!editable.value || !room.value) return
  slotEditing.value = s
  slotPreset.value = at
    ? { room_id: room.value.id, day: at.day, s_h: Math.floor(at.t / 60), s_m: at.t % 60 }
    : { room_id: room.value.id }
  slotOpen.value = true
  void res.reload() // 겹침 검사(existing)가 최신 슬롯을 보게 — 다른 관리자가 넣은 같은 키를 모르고 덮지 않도록
}
const resvOpen = ref(false)
const resvEditing = ref<ResvWithRoom | null>(null)
/** 수정은 관리자가 넣은 approved 만 — 신청은 신청 대기에서, 학생 예약은 강의실 설정에서 취소 (ResvBlock 과 같다) */
const resvEditable = (v: ResvWithRoom) => v.status === 'approved' && !v.requester
const clickable = (p: Placed) => !!p.slot || (!!p.resv && resvEditable(p.resv))
function blockTitle(p: Placed) {
  if (p.resv?.status === 'requested') return '신청 대기 — 강의실 설정에서 승인·거절'
  if (p.resv?.requester) return '학생 예약 — 강의실 설정에서 취소'
  return undefined
}
// 여러 교시 블록은 묶음 폼 — 맨 위 토글 '묶음 전체 | 한 교시만'. 한 교시짜리는 지금 슬롯 수정
const groupEditing = ref<SlotGroup | null>(null)
function openBlock(p: Placed) {
  if (!editable.value) return
  if (p.group && p.group.slots.length > 1) {
    groupEditing.value = p.group
    void res.reload()
  } else if (p.slot) openSlot(p.slot)
  else if (p.resv && resvEditable(p.resv)) {
    resvEditing.value = p.resv
    resvOpen.value = true
    void res.reload()
  }
}
// 지우기 — 교시 하나 또는 여러 교시(한 트랜잭션). 확인 모달 한 곳
const removing = ref<SlotWithRoom[] | null>(null)
const removingBusy = ref(false)
function askRemove(list: SlotWithRoom[]) {
  removing.value = list
  slotOpen.value = false
  groupEditing.value = null
}
const removeLines = computed(() => {
  const list = removing.value
  const r = room.value
  if (!list?.length || !r) return []
  const f = list[0]
  const l = list[list.length - 1]
  const head = `${r.room}호 ${DAYS[f.day - 1]}`
  return list.length === 1
    ? [`${head} ${hm(f.s_h, f.s_m)} ${f.subject}`]
    : [`${head} ${f.subject} — ${list.length}교시 ${hm(f.s_h, f.s_m)}–${hm(l.e_h, l.e_m)}`]
})
async function remove() {
  const list = removing.value
  if (!list?.length || removingBusy.value) return
  removingBusy.value = true
  try {
    const rid = list[0].room_id
    if (list.length === 1) await roomsApi.deleteSlot(rid, list[0])
    else
      await roomsApi.replaceSlots(rid, {
        remove: list.map(({ day, s_h, s_m }) => ({ day, s_h, s_m })),
        put: [],
      })
    showToast({ message: '지웠습니다.' })
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status !== 401 && e.status !== 403)
      showToast({ tone: 'danger', message: e.status === 409 ? conflictMessage(e) : e.message })
  } finally {
    removingBusy.value = false
    removing.value = null
    void res.reload()
  }
}
function pickRoom(ids: number[]) {
  if (ids[0] !== undefined) void router.push(`/rooms/${ids[0]}/week`)
}
function toRooms() {
  if (id.value !== null) picked.value = [id.value]
  void router.push('/rooms')
}
</script>

<template>
  <main class="wk">
    <header class="wk__bar">
      <!-- 버튼 라벨이 곧 현재 강의실 — 화면 제목을 겸한다 (h1 을 따로 두지 않는다) -->
      <RoomTree
        mode="single"
        :buildings="master.data.value?.buildings ?? []"
        :rooms="master.data.value?.rooms ?? []"
        :selected="id === null ? [] : [id]"
        @update:selected="pickRoom"
      />
      <div class="wk__nav">
        <Button variant="ghost" size="sm" aria-label="이전 주" @click="shiftWeek(-1)">◀</Button>
        <button type="button" class="wk__range num" title="이번 주로" @click="weekMonday = null">
          {{ md(monday) }}~{{ md(sunday) }}
        </button>
        <Button variant="ghost" size="sm" aria-label="다음 주" @click="shiftWeek(1)">▶</Button>
      </div>
      <Checkbox v-model="night" label="야간" />
      <Checkbox v-model="weekend" label="주말" />
      <Button class="wk__add" :disabled="!editable" @click="openSlot(null)">+ 시간표 추가</Button>
    </header>
    <div class="wk__legend">
      <Badge tone="busy">사용중</Badge>
      <span>수업·시험·특강·대여는 라벨로 구분</span>
      <Badge variant="outline">휴강</Badge>
      <span class="wk__legend-item"><OutboxDot state="acked" /> 완료</span>
      <span class="wk__legend-item"><OutboxDot state="queued" /> 대기</span>
    </div>
    <EmptyState
      v-if="notFound"
      message="강의실을 찾을 수 없습니다. 위에서 다른 강의실을 고르세요."
    />
    <EmptyState
      v-else-if="noRooms"
      message="강의실이 없습니다. 건물 · 강의실 화면에서 먼저 만드세요."
      :actions="[
        { label: '건물 · 강의실로', variant: 'primary', onClick: () => router.push('/master') },
      ]"
    />
    <WeekGrid
      v-else
      :blocks="blocks"
      :exams="fresh?.exams ?? []"
      :monday="monday"
      :night="night"
      :weekend="weekend"
      :editable="editable"
      :clickable="clickable"
      :block-title="blockTitle"
      :failed="(p: Placed) => dotOf(p) === 'failed'"
      @cell="(at) => openSlot(null, at)"
      @block="openBlock"
    >
      <template #dot="{ p }">
        <RowDot
          :state="dotOf(p)"
          :busy="!!room && tracker.resyncing.has(room.id)"
          @resync="resync(p.key)"
        />
      </template>
      <template #overlay>
        <div v-if="failedRes" class="wk__overlay">
          <EmptyState
            message="시간표·예약·시험기간을 불러오지 못했습니다"
            :actions="[{ label: '다시 불러오기', onClick: () => void failedRes?.reload() }]"
          />
        </div>
        <div v-else-if="loadingRes" class="wk__overlay">
          <Skeleton variant="block" width="60%" />
        </div>
        <div v-else-if="empty" class="wk__overlay">
          <EmptyState
            message="이 강의실에 등록된 시간표가 없습니다"
            :actions="[
              { label: '시간표 추가', variant: 'primary', onClick: () => openSlot(null) },
              { label: '페이지1에서 CSV 가져오기', onClick: toRooms },
            ]"
          />
        </div>
      </template>
    </WeekGrid>
    <SlotForm
      :open="slotOpen"
      :mode="slotEditing ? 'edit' : 'create'"
      :rooms="room ? [room] : []"
      :value="slotEditing"
      :preset="slotPreset"
      :existing="slots"
      removable
      @close="slotOpen = false"
      @saved="saved"
      @stale="res.reload"
      @remove="slotEditing && askRemove([slotEditing])"
    />
    <SlotGroupForm
      :open="!!groupEditing"
      :group="groupEditing"
      :room-label="room ? `${room.room}호` : ''"
      :existing="slots"
      scopes
      @close="groupEditing = null"
      @saved="saved"
      @stale="res.reload"
      @remove="askRemove"
    />
    <ResvForm
      :open="resvOpen"
      mode="edit"
      :rooms="room ? [room] : []"
      :value="resvEditing"
      :existing="resv"
      @close="resvOpen = false"
      @saved="saved"
      @stale="res.reload"
    />
    <ConfirmModal
      :open="!!removing"
      title="슬롯 삭제"
      :lines="removeLines"
      :loading="removingBusy"
      @confirm="remove"
      @close="removing = null"
    />
  </main>
</template>

<style scoped>
.wk {
  padding: 0 var(--space-5) var(--space-5);
}
.wk__bar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-4) 0 var(--space-2);
  background: var(--bg);
}
.wk__nav {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}
.wk__range {
  padding: var(--space-1) var(--space-2);
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-1);
  font: inherit;
  font-weight: var(--font-weight-bold);
  cursor: pointer;
}
.wk__range:hover {
  background: var(--sunken);
}
.wk__add {
  margin-left: auto;
}
.wk__legend {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding-bottom: var(--space-3);
  font-size: var(--font-size-xs);
  color: var(--text-2);
}
.wk__legend-item {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
}
.wk__overlay {
  position: absolute;
  inset: 44px 0 0 56px;
  display: grid;
  place-items: center;
  pointer-events: none;
}
.wk__overlay > * {
  pointer-events: auto;
  border-radius: var(--radius-lg);
  background: var(--surface);
}
</style>
