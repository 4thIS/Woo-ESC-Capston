<script setup lang="ts">
import { computed, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { studentApi } from '@/api/student'
import EmptyState from '@/components/ui/EmptyState.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import { useResource } from '@/lib/useResource'
import StudentHeader from '../StudentHeader.vue'
import { lastBld } from '../favorites'
import { buildingsOf } from '../roomView'

const router = useRouter()
const { data, error, reload } = useResource(() => studentApi.rooms())
const buildings = computed(() => buildingsOf(data.value ?? []))
// 첫 응답 한 번 — 최근 건물 → 건물이 하나뿐이면 그 건물 → 아니면 목록 (student-room.md 미결 3)
watch(
  data,
  (rooms) => {
    if (!rooms) return
    const list = buildingsOf(rooms)
    const target =
      list.find((b) => b.bld === lastBld()) ?? (list.length === 1 ? list[0] : undefined)
    if (target) void router.replace(`/${target.bld}`)
  },
  { once: true },
)
const retry = () => void reload()
</script>

<template>
  <div class="home">
    <StudentHeader title="MJC ESC" show-me />
    <main class="home__body">
      <h2 class="home__h">건물을 고르세요</h2>
      <Skeleton v-if="!data && !error" :rows="5" />
      <EmptyState
        v-else-if="!data"
        message="건물 목록을 불러오지 못했어요"
        :actions="[{ label: '다시 시도', variant: 'primary', onClick: retry }]"
      />
      <EmptyState v-else-if="!buildings.length" message="예약할 수 있는 강의실이 없습니다" />
      <ul v-else class="home__list">
        <li v-for="b in buildings" :key="b.id">
          <RouterLink
            :to="`/${b.bld}`"
            class="home__row"
            :aria-label="`${b.name} ${b.rooms}개 강의실 · 지금 ${b.free}곳 비어 있어요`"
          >
            <span class="home__name">{{ b.name }}</span>
            <span class="home__meta num"
              >{{ b.rooms }}개 강의실 · 지금 {{ b.free }}곳 비어 있어요</span
            >
            <span class="home__chev" aria-hidden="true">›</span>
          </RouterLink>
        </li>
      </ul>
    </main>
  </div>
</template>

<style scoped>
.home__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-width: 640px;
  margin: 0 auto;
  padding: var(--space-4);
}
.home__h {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
}
.home__list {
  margin: 0;
  padding: 0;
  list-style: none;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.home__list li + li {
  border-top: var(--border-thin) solid var(--line-1);
}
.home__row {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  min-height: 56px;
  padding: var(--space-2) var(--space-4);
  color: var(--text-1);
  text-decoration: none;
}
.home__name {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.home__meta {
  grid-row: 2;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.home__chev {
  grid-column: 2;
  grid-row: 1 / 3;
  font-size: var(--font-size-lg);
  color: var(--text-3);
}
</style>
