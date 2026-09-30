<script setup lang="ts">
import { watch } from 'vue'
import { useRouter } from 'vue-router'
import WeekGrid from '@/components/student/WeekGrid.vue'
import Banner from '@/components/ui/Banner.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import RefreshedNote from '../RefreshedNote.vue'
import StudentHeader from '../StudentHeader.vue'
import { useRoomWeek, useWeekGrid } from '../building'
import { useWide } from '../composables'
import NotFoundView from './NotFoundView.vue'

const ROW_PX = 24 // bp.mobile — 30분 24px, 18행 432px (student-room.md 화면 3)
const router = useRouter()
const wide = useWide()
const { bld, roomNo, now, notFound, title, week, weekError, refreshedAt, reload } = useRoomWeek({
  poll: true,
})
const { days, blocks, range, todayIndex, nowY } = useWeekGrid(week, now, ROW_PX)
// 넓은 폭에서는 이미 강의실 화면 안에 있다 (student-room.md 「넓은 폭」)
watch(
  wide,
  (w) => {
    if (w) void router.replace(`/${bld.value}/${roomNo.value}`)
  },
  { immediate: true },
)
const retry = () => void reload()
</script>

<template>
  <NotFoundView v-if="notFound" :back="`/${bld}`" back-label="강의실 목록으로" />
  <div v-else class="week">
    <StudentHeader
      :title="`${title} · 이번 주`"
      :back="`/${bld}/${roomNo}`"
      back-label="강의실로"
    />
    <Banner
      v-if="weekError && week"
      tone="danger"
      :message="weekError.message"
      :dismissible="false"
    >
      <Button variant="secondary" @click="retry">다시 시도</Button>
    </Banner>
    <main class="week__body">
      <Skeleton v-if="!week && !weekError" :rows="6" />
      <EmptyState
        v-else-if="!week"
        message="이번 주 시간표를 불러오지 못했어요"
        :actions="[{ label: '다시 시도', variant: 'primary', onClick: retry }]"
      />
      <template v-else>
        <div class="week__card">
          <WeekGrid
            :days="days"
            :blocks="blocks"
            :row-height="ROW_PX"
            :range="range"
            :today-index="todayIndex"
            :now-top="nowY"
          />
        </div>
        <p class="week__hint">빈 칸이 비어 있는 시간이에요</p>
      </template>
      <RefreshedNote :at="refreshedAt" />
    </main>
  </div>
</template>

<style scoped>
.week__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  /* 좌우를 줄여 390 에서 시각 34 + 주중 5열 × 64 = 354px 가 가로 스크롤 없이 들어간다 */
  padding: var(--space-4) var(--space-2);
}
.week__card {
  padding: var(--space-2) var(--space-1);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.week__hint {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
</style>
