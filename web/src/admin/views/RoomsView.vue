<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { showToast } from '@/components/ui/toast'
import RoomTree from '@/components/domain/RoomTree.vue'
import { examKey, resvKey, slotKey, type SavedRow } from '@/components/domain/rules'
import { ApiError } from '@/api/client'
import { adminApi } from '@/api/admin'
import { loraApi } from '@/api/lora'
import { roomsApi } from '@/api/rooms'
import type { RoomOut } from '@/api/types'
import { useResource } from '@/lib/useResource'
import { useOutboxTracker } from '../outboxTrack'
import { defaultPick, roomLabeler } from '../roomsView'
import { picked } from '../selection'
import CsvImport from './rooms/CsvImport.vue'
import ExamBlock from './rooms/ExamBlock.vue'
import PendingBlock from './rooms/PendingBlock.vue'
import ResvBlock from './rooms/ResvBlock.vue'
import SlotBlock from './rooms/SlotBlock.vue'

const router = useRouter()
const master = useResource(async () => {
  const [buildings, rooms] = await Promise.all([roomsApi.buildings(), roomsApi.rooms()])
  return { buildings, rooms }
})
const buildings = computed(() => master.data.value?.buildings ?? [])
const allRooms = computed(() => master.data.value?.rooms ?? [])
const hasNoRooms = computed(() => !!master.data.value && !allRooms.value.length)

// 트리 선택은 모듈 상태 — 다른 화면을 다녀와도 남는다. 지워진 방은 빼고, 비었으면 첫 건물의 첫 층
watch(master.data, (d) => {
  if (!d) return
  const alive = picked.value.filter((id) => d.rooms.some((r) => r.id === id))
  picked.value = alive.length ? alive : defaultPick(d.buildings, d.rooms)
})
const selection = computed({
  get: () => picked.value,
  set: (ids: number[]) => (picked.value = ids),
})
const order = (r: RoomOut) => buildings.value.findIndex((b) => b.id === r.building_id)
const pickedRooms = computed(() =>
  allRooms.value
    .filter((r) => picked.value.includes(r.id))
    .sort((a, b) => order(a) - order(b) || a.room - b.room),
)
const label = computed(() => roomLabeler(buildings.value, pickedRooms.value))

// 건물 단위 조회 3개 (S4b §2.6) — 같은 건물 안에서 고른 방을 바꿔도 다시 부르지 않고 걸러서 보인다
const bids = computed(() =>
  [...new Set(pickedRooms.value.map((r) => r.building_id))].sort((a, b) => a - b),
)
const bidsKey = computed(() => bids.value.join(','))
const scope = useResource(
  async () => {
    const key = bidsKey.value
    const per = await Promise.all(
      bids.value.map((b) =>
        Promise.all([
          roomsApi.buildingSlots(b),
          roomsApi.buildingResv(b),
          roomsApi.buildingExams(b),
        ]),
      ),
    )
    return {
      key,
      slots: per.flatMap((p) => p[0]),
      resv: per.flatMap((p) => p[1]),
      exams: per.flatMap((p) => p[2]),
    }
  },
  { deps: bidsKey },
)
// 신청 대기는 학교 전체 — 처리해야 할 일이라 트리 밖 신청도 숨기지 않는다 (설계 판정)
const pending = useResource(() => adminApi.pendingResv())
const inPick = <T extends { room_id: number }>(xs: T[] | undefined) =>
  (xs ?? []).filter((x) => picked.value.includes(x.room_id))
// 지금 고른 건물들의 데이터만 쓴다 — 다른 건물 조합의 옛 응답·첫 진입의 빈 결과를 '비어 있음'으로 그리지 않는다
const fresh = computed(() =>
  scope.data.value?.key === bidsKey.value ? scope.data.value : undefined,
)
const slots = computed(() => inPick(fresh.value?.slots))
const resv = computed(() => inPick(fresh.value?.resv))
const exams = computed(() => inPick(fresh.value?.exams))
const scopeFailed = computed(() => !fresh.value && !!scope.error.value && !scope.loading.value)
const scopeLoading = computed(() => !fresh.value && !scopeFailed.value)
function reloadAll() {
  void scope.reload()
  void pending.reload()
}

// 오류 — Toast + 재시도. 표는 이전 내용을 지우지 않는다 (useResource 가 data 를 지킨다)
for (const r of [master, scope, pending])
  watch(r.error, (e) => {
    if (e && e.status !== 401 && e.status !== 403)
      showToast({
        tone: 'danger',
        message: e.message,
        action: { label: '재시도', onClick: () => void r.reload() },
      })
  })

// 저장 뒤 OutboxDot — 행 key 로 30초 (새로고침하면 끊긴다)
const tracker = useOutboxTracker()
const buildingOf = (roomId: number) => allRooms.value.find((r) => r.id === roomId)?.building_id
function onSaved(s: SavedRow) {
  const b = buildingOf(s.roomId)
  if (b !== undefined) tracker.track(s.key, b, s.outboxIds)
}
// 재전송은 방 단위 — 그 방에서 실패·취소로 보이는 행을 모두 새 작업으로 따라간다
const DEAD = ['failed', 'cancelled']
/** 그 방의 행 keys — 시간표·예약·시험기간 */
function roomKeys(roomId: number): string[] {
  const d = fresh.value
  const mine = <T extends { room_id: number }>(xs: T[] | undefined) =>
    (xs ?? []).filter((x) => x.room_id === roomId)
  return [
    ...mine(d?.slots).map(slotKey),
    ...mine(d?.resv).map((r) => resvKey(r.id)),
    ...mine(d?.exams).map((x) => examKey(x.id)),
  ]
}
function resync(roomId: number, key: string) {
  const b = buildingOf(roomId)
  if (b === undefined) return
  const keys = roomKeys(roomId).filter(
    (k) => k !== key && DEAD.includes(tracker.states.get(k) ?? ''),
  )
  void tracker.resync([key, ...keys], roomId, b)
}

// CSV — 파일 선택은 숨은 input, 흐름(미리보기→적용)은 CsvImport 가 진다
const csv = ref<InstanceType<typeof CsvImport>>()
// 선택한 곳 동기화 — '전체 동기화'를 범위로 좁혔다. 건물 전체를 실수로 재전송하지 않게. 확인 없이 보낸다(파괴적이지 않다)
const syncing = ref(false)
async function syncPicked() {
  const list = [...pickedRooms.value]
  if (syncing.value || !list.length) return
  syncing.value = true
  const bad: string[] = []
  try {
    for (const r of list) {
      try {
        const res = await loraApi.syncRoom(r.id)
        // 점이 있던 행(실패·취소 등)은 새 작업을 따라간다 — 옛 실패 점이 남아 거짓말하지 않게
        for (const k of roomKeys(r.id))
          if (tracker.states.has(k)) tracker.track(k, r.building_id, res.outbox_ids)
      } catch (e) {
        if (!(e instanceof ApiError)) throw e
        if (e.status === 401 || e.status === 403) return // 로그인 화면으로 간다
        bad.push(`${label.value(r.id)}호`)
      }
    }
  } finally {
    syncing.value = false
  }
  showToast(
    bad.length
      ? {
          tone: 'danger',
          message: `${list.length}곳 중 ${list.length - bad.length}곳 보냄 · ${bad.join(', ')} 실패`,
        }
      : { message: `${list.length}곳에 다시 보냈습니다.` },
  )
}
</script>

<template>
  <main class="rooms">
    <!-- 상단 바는 스크롤해도 붙어 있다 — 트리에서 고른 것이 아래 표들의 범위다 -->
    <header class="rooms__bar">
      <RoomTree v-model:selected="selection" :buildings="buildings" :rooms="allRooms" />
      <span class="rooms__hint">강의실 선택</span>
      <div class="rooms__tools">
        <Button variant="secondary" :loading="csv?.busy" @click="csv?.pick()">CSV 가져오기</Button>
        <Button
          variant="secondary"
          :loading="syncing"
          :disabled="!pickedRooms.length"
          @click="syncPicked"
          >선택한 곳 동기화</Button
        >
      </div>
    </header>
    <CsvImport ref="csv" @applied="scope.reload" />
    <EmptyState
      v-if="hasNoRooms"
      message="강의실이 없습니다. 건물 · 강의실 화면에서 먼저 만드세요."
      :actions="[
        { label: '건물 · 강의실로', variant: 'primary', onClick: () => router.push('/master') },
      ]"
    />
    <div v-else class="rooms__blocks">
      <EmptyState
        v-if="scopeFailed"
        message="시간표·예약·시험기간을 불러오지 못했습니다"
        :actions="[{ label: '다시 불러오기', onClick: () => void scope.reload() }]"
      />
      <SlotBlock
        v-else
        :rooms="pickedRooms"
        :label="label"
        :slots="slots"
        :states="tracker.states"
        :resyncing="tracker.resyncing"
        :loading="scopeLoading"
        @saved="onSaved"
        @changed="scope.reload"
        @resync="resync"
        @csv="csv?.pick()"
      />
      <!-- 신청 대기는 예약 블록 위에 선다 — 승인해야 approved 가 되어 노드로 나간다 -->
      <PendingBlock :pending="pending.data.value" @changed="reloadAll" />
      <ResvBlock
        v-if="!scopeFailed"
        :rooms="pickedRooms"
        :label="label"
        :resv="resv"
        :states="tracker.states"
        :resyncing="tracker.resyncing"
        :loading="scopeLoading"
        @saved="onSaved"
        @changed="reloadAll"
        @resync="resync"
      />
      <ExamBlock
        v-if="!scopeFailed"
        :rooms="pickedRooms"
        :label="label"
        :exams="exams"
        :states="tracker.states"
        :resyncing="tracker.resyncing"
        :loading="scopeLoading"
        @saved="onSaved"
        @changed="scope.reload"
        @resync="resync"
      />
    </div>
  </main>
</template>

<style scoped>
.rooms {
  padding: 0 var(--space-5) var(--space-5);
}
.rooms__bar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) 0;
  background: var(--bg);
}
.rooms__hint {
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
.rooms__tools {
  display: flex;
  gap: var(--space-2);
  margin-left: auto;
}
/* 탭이 아니라 세로 스택 — 셋이 같은 강의실의 다른 시간 축이라 함께 보여야 한다 */
.rooms__blocks {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}
</style>
