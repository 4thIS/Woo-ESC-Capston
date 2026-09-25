<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Banner from '@/components/ui/Banner.vue'
import { showToast } from '@/components/ui/toast'
import { adminApi } from '@/api/admin'
import { loraApi } from '@/api/lora'
import { roomsApi } from '@/api/rooms'
import { useResource } from '@/lib/useResource'
import BuildingPanel from './master/BuildingPanel.vue'

// 마스터 데이터는 관리자가 바꿀 때만 바뀐다 — 자동 새로고침 없음 (admin-master.md)
const { data, error, loading, reload } = useResource(async () => {
  const [buildings, rooms, modems, nodes] = await Promise.all([
    roomsApi.buildings(),
    roomsApi.rooms(),
    loraApi.modems(),
    adminApi.nodes(),
  ])
  return { buildings, rooms, modems, nodes }
})
const selectedId = ref<number | null>(null)
watch(data, (d) => {
  if (d && !d.buildings.some((b) => b.id === selectedId.value))
    selectedId.value = d.buildings[0]?.id ?? null
})
// reservable 기본값이 꺼짐 — 켜는 것을 잊으면 학생 웹이 빈 채로 남는다
const noReservable = computed(
  () => !!data.value?.rooms.length && !data.value.rooms.some((r) => r.reservable),
)
watch(error, (e) => {
  if (e && e.status !== 401 && e.status !== 403)
    showToast({ tone: 'danger', message: e.message, action: { label: '재시도', onClick: reload } })
})
</script>

<template>
  <main class="master">
    <header class="master__head">
      <h1 class="master__title">건물 · 강의실</h1>
      <p class="master__sub">여기서 만든 방만 다른 화면에 나온다</p>
    </header>
    <Banner
      v-if="noReservable"
      message="학생 예약을 받는 강의실이 없습니다. 학생 웹 목록이 비어 있습니다."
      :dismissible="false"
    />
    <div class="master__body">
      <BuildingPanel
        :buildings="data?.buildings"
        :rooms="data?.rooms ?? []"
        :modems="data?.modems ?? []"
        :loading="loading && !data"
        :selected-id="selectedId"
        @select="selectedId = $event"
        @changed="reload"
      />
    </div>
  </main>
</template>

<style scoped>
.master {
  padding: var(--space-5);
}
.master__head {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}
.master__title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
}
.master__sub {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
/* 좌우 2단 — 건물 패널 396px 고정, 강의실 표가 남는 폭 */
.master__body {
  display: grid;
  grid-template-columns: 396px minmax(0, 1fr);
  gap: var(--space-5);
  align-items: start;
  margin-top: var(--space-4);
}
</style>
