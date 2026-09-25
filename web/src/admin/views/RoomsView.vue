<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import EmptyState from '@/components/ui/EmptyState.vue'
import { showToast } from '@/components/ui/toast'
import RoomTree from '@/components/domain/RoomTree.vue'
import type { SavedRow } from '@/components/domain/rules'
import { adminApi } from '@/api/admin'
import { roomsApi } from '@/api/rooms'
import type { RoomOut } from '@/api/types'
import { useResource } from '@/lib/useResource'
import { useOutboxTracker } from '../outboxTrack'
import { defaultPick, roomLabeler } from '../roomsView'
import { picked } from '../selection'
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
const scope = useResource(
  async () => {
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
      slots: per.flatMap((p) => p[0]),
      resv: per.flatMap((p) => p[1]),
      exams: per.flatMap((p) => p[2]),
    }
  },
  { deps: () => bids.value.join(',') },
)
// 신청 대기는 학교 전체 — 처리해야 할 일이라 트리 밖 신청도 숨기지 않는다 (설계 판정)
const pending = useResource(() => adminApi.pendingResv())
const inPick = <T extends { room_id: number }>(xs: T[] | undefined) =>
  (xs ?? []).filter((x) => picked.value.includes(x.room_id))
const slots = computed(() => inPick(scope.data.value?.slots))
const resv = computed(() => inPick(scope.data.value?.resv))
const scopeLoading = computed(() => scope.loading.value && !scope.data.value)
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
function resync(roomId: number, key: string) {
  const b = buildingOf(roomId)
  if (b !== undefined) void tracker.resync(key, roomId, b)
}
</script>

<template>
  <main class="rooms">
    <!-- 상단 바는 스크롤해도 붙어 있다 — 트리에서 고른 것이 아래 표들의 범위다 -->
    <header class="rooms__bar">
      <RoomTree v-model:selected="selection" :buildings="buildings" :rooms="allRooms" />
      <span class="rooms__hint">강의실 선택</span>
    </header>
    <EmptyState
      v-if="hasNoRooms"
      message="강의실이 없습니다. 건물 · 강의실 화면에서 먼저 만드세요."
      :actions="[
        { label: '건물 · 강의실로', variant: 'primary', onClick: () => router.push('/master') },
      ]"
    />
    <div v-else class="rooms__blocks">
      <SlotBlock
        :rooms="pickedRooms"
        :label="label"
        :slots="slots"
        :states="tracker.states"
        :resyncing="tracker.resyncing"
        :loading="scopeLoading"
        @saved="onSaved"
        @changed="scope.reload"
        @resync="resync"
      />
      <!-- 신청 대기는 예약 블록 위에 선다 — 승인해야 approved 가 되어 노드로 나간다 -->
      <PendingBlock :pending="pending.data.value" @changed="reloadAll" />
      <ResvBlock
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
/* 탭이 아니라 세로 스택 — 셋이 같은 강의실의 다른 시간 축이라 함께 보여야 한다 */
.rooms__blocks {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}
</style>
