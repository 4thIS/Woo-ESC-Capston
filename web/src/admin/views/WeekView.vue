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
import {
  DAYS,
  TYPE_LABEL,
  conflictMessage,
  resvKey,
  slotKey,
  type SavedRow,
} from '@/components/domain/rules'
import { ApiError } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { ResvWithRoom, SlotWithRoom } from '@/api/types'
import { addDays, hm, kstDateStr, md, mondayOf } from '@/lib/time'
import { useResource } from '@/lib/useResource'
import ConfirmModal from '../ConfirmModal.vue'
import { useOutboxTracker } from '../outboxTrack'
import { resvDot } from '../roomsView'
import { nightPref, picked, weekMonday, weekRoom, weekendPref } from '../selection'
import {
  ROW_PX,
  blockBox,
  examDates,
  gridRange,
  layoutDay,
  needsNight,
  needsWeekend,
  timeRows,
  weekBlocks,
  type Placed,
} from '../weekView'
import RowDot from './rooms/RowDot.vue'

const props = defineProps<{ roomId?: string }>()
const router = useRouter()
const today = kstDateStr(new Date())
const clock = (t: number) => hm(Math.floor(t / 60), t % 60)

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
  watch(r.error, (e) => {
    if (e && ![401, 403, 404].includes(e.status))
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
const range = computed(() => gridRange(blocks.value, night.value))
const rows = computed(() => timeRows(range.value))
const examOn = computed(() => examDates(fresh.value?.exams ?? [], monday.value))
const days = computed(() =>
  Array.from({ length: weekend.value ? 7 : 5 }, (_, i) => {
    const date = addDays(monday.value, i)
    const { placed, overlaps } = layoutDay(blocks.value.filter((b) => b.day === i + 1))
    return {
      day: i + 1,
      date,
      exam: examOn.value.has(date),
      blocks: placed.flatMap((p) => {
        const box = blockBox(p, range.value)
        return box ? [{ p, box }] : []
      }),
      marks: overlaps.flatMap((o) => {
        const box = blockBox(o, range.value)
        return box ? [{ o, box }] : []
      }),
    }
  }),
)
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
  p.resv ? resvDot(p.resv, tracker.states.get(p.key), today) : tracker.states.get(p.key)
function blockClass(p: Placed) {
  const requested = p.resv?.status === 'requested'
  const cancelled = p.slot?.type === 3
  return {
    'wk__block--busy': !requested && !cancelled,
    'wk__block--cancelled': cancelled,
    'wk__block--requested': requested,
    'wk__block--failed': dotOf(p) === 'failed',
    'wk__block--static': !clickable(p),
  }
}
// 라벨이 상태를 말한다 — 넷(수업·시험·특강·대여)을 색으로 나누지 않는다
function blockLabel(p: Placed) {
  if (p.slot) return TYPE_LABEL[p.slot.type]
  return `${p.resv!.status === 'requested' ? '신청' : '예약'} · ${TYPE_LABEL[p.resv!.type]}`
}
/** 스크린리더 이름 — '월 10:00–12:00 수업중 캡스톤디자인' */
const blockName = (p: Placed) =>
  `${DAYS[p.day - 1]} ${clock(p.s)}–${clock(p.e)} ${blockLabel(p)} ${p.slot?.subject ?? p.resv?.subject ?? ''}`.trim()
const who = (p: Placed) =>
  p.slot ? p.slot.professor : (p.resv!.requester?.name ?? p.resv!.professor)

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
function openBlock(p: Placed) {
  if (!editable.value) return
  if (p.slot) openSlot(p.slot)
  else if (p.resv && resvEditable(p.resv)) {
    resvEditing.value = p.resv
    resvOpen.value = true
    void res.reload()
  }
}
const removing = ref<SlotWithRoom | null>(null)
const removingBusy = ref(false)
function askRemove() {
  removing.value = slotEditing.value
  slotOpen.value = false
}
async function remove() {
  const s = removing.value
  if (!s || removingBusy.value) return
  removingBusy.value = true
  try {
    await roomsApi.deleteSlot(s.room_id, s)
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
      <Button class="wk__add" :disabled="!editable" @click="openSlot(null)">+ 슬롯 추가</Button>
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
    <div v-else class="wk__scroll">
      <div class="wk__grid" :style="{ '--cols': days.length }">
        <div class="wk__corner" />
        <div v-for="d in days" :key="d.date" class="wk__head">
          <span
            >{{ DAYS[d.day - 1] }} <span class="num">{{ md(d.date) }}</span></span
          >
          <!-- 시험기간은 요일 헤더 아래 얇은 띠 — 셀은 건드리지 않는다 -->
          <span v-if="d.exam" class="wk__exam">시험기간</span>
        </div>
        <div class="wk__times">
          <div v-for="t in rows" :key="t" class="wk__time num">{{ clock(t) }}</div>
        </div>
        <div
          v-for="d in days"
          :key="`c${d.date}`"
          class="wk__col"
          :style="{ height: `${rows.length * ROW_PX}px` }"
        >
          <button
            v-for="t in rows"
            :key="t"
            type="button"
            class="wk__cell"
            :disabled="!editable"
            :aria-label="`${DAYS[d.day - 1]} ${clock(t)} 슬롯 추가`"
            @click="openSlot(null, { day: d.day, t })"
          />
          <!-- 자리 하나에 블록과 점이 형제로 선다 — 재전송 버튼을 role=button 블록 안에 넣으면
               스크린리더가 한 덩어리로 읽고, 재전송의 Enter 가 블록까지 올라가 편집을 연다 -->
          <div
            v-for="{ p, box } in d.blocks"
            :key="p.key"
            class="wk__place"
            :style="{
              top: `${box.top}px`,
              height: `${box.height}px`,
              left: `calc(${(p.lane / p.lanes) * 100}% + 4px)`,
              width: `calc(${100 / p.lanes}% - 8px)`,
            }"
          >
            <div
              class="wk__block"
              :class="blockClass(p)"
              :role="clickable(p) ? 'button' : undefined"
              :tabindex="clickable(p) ? 0 : undefined"
              :aria-label="clickable(p) ? blockName(p) : undefined"
              :title="blockTitle(p)"
              @click="openBlock(p)"
              @keydown.enter.self.prevent="openBlock(p)"
              @keydown.space.self.prevent="openBlock(p)"
            >
              <span class="wk__label">{{ blockLabel(p) }}</span>
              <!-- 높이가 모자라면 교수부터 지운다 -->
              <span v-if="box.height >= 40" class="wk__subject">{{
                p.slot?.subject ?? p.resv?.subject
              }}</span>
              <span v-if="box.height >= 80 && who(p)" class="wk__who">{{ who(p) }}</span>
              <span v-if="box.cutEnd" class="wk__cut num">~{{ clock(p.e) }}</span>
            </div>
            <span class="wk__dot"
              ><RowDot
                :state="dotOf(p)"
                :busy="!!room && tracker.resyncing.has(room.id)"
                @resync="resync(p.key)"
            /></span>
          </div>
          <div
            v-for="({ o, box }, i) in d.marks"
            :key="`m${i}`"
            class="wk__overlap"
            :style="{
              top: `${box.top}px`,
              height: `${box.height}px`,
              left: `calc(${(o.lane / o.lanes) * 100}% - 1.5px)`,
            }"
          >
            <!-- 막대 왼쪽에 두 줄로 — 오른쪽 블록의 라벨을 가리지 않고, 반 폭(1440·7열 ≈78px)에 들어간다 -->
            <span class="wk__overlap-label num"
              ><span>겹침</span> <span>{{ clock(o.s) }}–{{ clock(o.e) }}</span></span
            >
          </div>
        </div>
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
              { label: '슬롯 추가', variant: 'primary', onClick: () => openSlot(null) },
              { label: '페이지1에서 CSV 가져오기', onClick: toRooms },
            ]"
          />
        </div>
      </div>
    </div>
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
      :lines="
        removing && room
          ? [
              `${room.room}호 ${DAYS[removing.day - 1]} ${hm(removing.s_h, removing.s_m)} ${removing.subject}`,
            ]
          : []
      "
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
/* 격자 컨테이너 line.2 1px + radius.lg, 세로 스크롤 — 요일 헤더와 시각 열은 붙어 있다 */
.wk__scroll {
  max-height: calc(100vh - 150px);
  overflow: auto;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.wk__grid {
  position: relative;
  display: grid;
  grid-template-columns: 56px repeat(var(--cols), minmax(0, 1fr));
}
.wk__corner,
.wk__head {
  position: sticky;
  top: 0;
  z-index: 3;
  border-bottom: var(--border-thin) solid var(--line-2);
  background: var(--surface);
}
.wk__corner {
  left: 0;
  z-index: 4;
}
.wk__head {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 44px;
  padding: var(--space-1) var(--space-2);
  border-left: var(--border-thin) solid var(--line-1);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
}
.wk__exam {
  align-self: flex-start;
  margin-top: 2px;
  padding: 0 var(--space-1);
  border-radius: var(--radius-sm);
  background: var(--room-busy-fill);
  color: var(--room-busy-label);
  font-size: var(--font-size-xs);
}
.wk__times {
  position: sticky;
  left: 0;
  z-index: 2;
  background: var(--surface);
}
.wk__time {
  height: 44px;
  padding: 2px var(--space-2);
  border-bottom: var(--border-thin) solid var(--line-1);
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
/* 열 구분선은 line.1 (설계 판정 — gray.50 의 2층 토큰이 없다) */
.wk__col {
  position: relative;
  border-left: var(--border-thin) solid var(--line-1);
}
.wk__cell {
  display: block;
  width: 100%;
  height: 44px;
  border: 0;
  border-bottom: var(--border-thin) solid var(--line-1);
  background: transparent;
  cursor: pointer;
}
.wk__cell:hover:enabled {
  background: var(--sunken);
}
.wk__place {
  position: absolute;
}
.wk__block {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow: hidden;
  padding: var(--space-1) var(--space-2);
  border: var(--border-thin) solid transparent;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  cursor: pointer;
}
.wk__block--busy {
  border-color: var(--room-busy-line);
  background: var(--room-busy-fill);
}
.wk__block--busy .wk__label {
  color: var(--room-busy-label);
}
.wk__block--cancelled {
  border: var(--border-thin) dashed var(--room-free-line);
  background: var(--surface);
  color: var(--room-free-text);
}
.wk__block--cancelled .wk__subject {
  text-decoration: line-through;
}
/* 신청(승인 대기) — 아무것도 점유하지 않았다: 바탕 없이 2px 점선 + text.3 */
.wk__block--requested {
  border: var(--border-thick) dashed var(--line-3);
  background: var(--surface);
  color: var(--text-3);
  cursor: default;
}
.wk__block--static {
  cursor: default;
}
.wk__block--failed {
  border: var(--border-thick) solid var(--danger);
}
.wk__label {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
}
.wk__subject {
  overflow: hidden;
  font-weight: var(--font-weight-medium);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wk__who {
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.wk__cut {
  margin-top: auto;
  font-size: var(--font-size-xs);
}
.wk__dot {
  position: absolute;
  top: var(--space-1);
  right: var(--space-1);
}
/* 겹침 — 두 블록 사이 겹친 구간에만 danger 3px 막대 하나 + 라벨 하나 */
.wk__overlap {
  position: absolute;
  z-index: 1;
  width: 3px;
  background: var(--danger);
  pointer-events: none;
}
.wk__overlap-label {
  position: absolute;
  top: var(--space-1);
  right: 6px;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  padding: 0 var(--space-1);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--danger);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  white-space: nowrap;
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
