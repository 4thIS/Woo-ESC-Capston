<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { SlotType } from '@/api/types'
import { BUSY_TYPES, TYPE_LABEL } from '@/components/domain/rules'
import FavoriteStar from '@/components/student/FavoriteStar.vue'
import WeekGrid from '@/components/student/WeekGrid.vue'
import { dateLabel, durationText, hmToMin } from '@/components/student/rules'
import Badge from '@/components/ui/Badge.vue'
import Banner from '@/components/ui/Banner.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import { dayOfDate, formatHm, kstDateStr, kstMinutes, mondayOf } from '@/lib/time'
import CtaLink from '../CtaLink.vue'
import RefreshedNote from '../RefreshedNote.vue'
import StudentHeader from '../StudentHeader.vue'
import { useRoomWeek, useWeekGrid } from '../building'
import { useWide } from '../composables'
import { favKey, favorites, toggleFavorite } from '../favorites'
import { nextFree, todayRows } from '../roomView'
import NotFoundView from './NotFoundView.vue'

const ROW_PX = 32 // 넓은 폭 격자 — 좁은 폭은 /week 별도 화면 (student-room.md 「넓은 폭」)
const wide = useWide()
const { bld, roomNo, now, notFound, title, week, weekError, refreshedAt, reload } = useRoomWeek({
  poll: true,
})
const { days, blocks, range, todayIndex, nowY } = useWeekGrid(week, now, ROW_PX)
const today = computed(() => kstDateStr(now.value))
// '지금' 카드 대신 오늘 목록에서 지금 행을 세운다 — 빈 구간도 행 (student-room.md 화면 2)
// 서버 주간이 이번 주일 때만(자정 직후 한 번의 폴링 사이 어긋남) — 격자의 '오늘'과 같은 판정
const rows = computed(() =>
  week.value && week.value.week_start === mondayOf(today.value)
    ? todayRows(
        week.value.busy.find((d) => d.day === dayOfDate(today.value))?.spans ?? [],
        kstMinutes(now.value),
      )
    : [],
)
const fav = computed(() => favorites.value.includes(favKey(bld.value, roomNo.value)))
const next = computed(() => nextFree(week.value?.free ?? []))
const reserveTo = computed(() => `/${bld.value}/${roomNo.value}/reserve`)
const isBusy = (t: SlotType | null) => t !== null && BUSY_TYPES.includes(t)
const toggle = () => toggleFavorite(favKey(bld.value, roomNo.value))
const retry = () => void reload()
</script>

<template>
  <NotFoundView v-if="notFound" :back="`/${bld}`" back-label="강의실 목록으로" />
  <div v-else class="room">
    <StudentHeader :title="title" :back="`/${bld}`" back-label="강의실 목록" hide-back-wide>
      <FavoriteStar :on="fav" @toggle="toggle" />
      <CtaLink v-if="wide" :to="reserveTo" compact>이 강의실 예약하기</CtaLink>
    </StudentHeader>
    <Banner
      v-if="weekError && week"
      tone="danger"
      :message="weekError.message"
      :dismissible="false"
    >
      <Button variant="secondary" @click="retry">다시 시도</Button>
    </Banner>
    <main class="room__body">
      <section class="room__card" aria-labelledby="today-h">
        <h2 id="today-h" class="room__h">
          오늘 <span class="room__date num">{{ dateLabel(today) }}</span>
        </h2>
        <Skeleton v-if="!week && !weekError" :rows="3" />
        <EmptyState
          v-else-if="!week"
          message="시간표를 불러오지 못했어요"
          :actions="[{ label: '다시 시도', variant: 'primary', onClick: retry }]"
        />
        <ol v-else class="today">
          <li
            v-for="r in rows"
            :key="r.from"
            class="today__row"
            :class="{ 'today__row--now': r.now }"
          >
            <span class="today__time num"
              >{{ r.from }}<span class="today__to">–{{ r.to }}</span></span
            >
            <span
              class="today__label"
              :class="{ 'today__label--off': r.type === 3, 'today__label--mine': r.mine }"
              ><span class="today__text">{{ r.label }}</span
              ><span v-if="r.type === null" class="today__until num"> —{{ r.to }}</span></span
            >
            <Badge v-if="isBusy(r.type)" tone="busy" size="sm">{{
              TYPE_LABEL[r.type as SlotType]
            }}</Badge>
            <Badge v-else-if="r.type === 3" tone="neutral" variant="outline" size="sm">휴강</Badge>
            <!-- '지금'은 brand — 적색은 '사용중' 전용 -->
            <Badge v-if="r.now" tone="brand" variant="solid" size="sm" class="num"
              >지금 {{ formatHm(now) }}</Badge
            >
          </li>
        </ol>
      </section>

      <section v-if="wide" class="room__card" aria-labelledby="next-h">
        <h2 id="next-h" class="room__h">다음 비는 시간</h2>
        <p v-if="next" class="room__next-v num">
          {{ next.from }} – {{ next.to }} ·
          {{ durationText(hmToMin(next.to) - hmToMin(next.from)) }}
        </p>
        <p v-else class="room__muted">오늘은 더 비는 시간이 없어요</p>
      </section>

      <section v-if="wide && week" class="room__card" aria-labelledby="week-h">
        <h2 id="week-h" class="room__h">이번 주</h2>
        <WeekGrid
          :days="days"
          :blocks="blocks"
          :row-height="ROW_PX"
          :range="range"
          :today-index="todayIndex"
          :now-top="nowY"
        />
      </section>

      <RouterLink v-if="!wide" :to="`/${bld}/${roomNo}/week`" class="room__week"
        >이번 주 전체 보기 <span aria-hidden="true">›</span></RouterLink
      >
      <RefreshedNote :at="refreshedAt" />
    </main>
    <!-- 1차 동작은 엄지가 닿는 하단 (student-room.md §예약 · 진입) -->
    <footer v-if="!wide" class="room__cta">
      <CtaLink :to="reserveTo">이 강의실 예약하기</CtaLink>
      <p class="room__muted">비어 있는 시간만 · 7일 이내</p>
    </footer>
  </div>
</template>

<style scoped>
.room {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}
.room__body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-4);
}
.room__card {
  padding: var(--space-4);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.room__h {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-bold);
}
.room__date {
  margin-left: var(--space-2);
  font-weight: var(--font-weight-regular);
  color: var(--text-3);
}
.today {
  margin: 0;
  padding: 0;
  list-style: none;
}
.today__row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 48px;
  padding: 0 var(--space-2);
  border-bottom: var(--border-thin) solid var(--line-1);
}
.today__row:last-child {
  border-bottom: 0;
}
.today__row--now {
  background: var(--brand-tint);
}
.today__row--now .today__time {
  color: var(--brand);
  font-weight: var(--font-weight-bold);
}
.today__time {
  flex: 0 0 auto;
  color: var(--text-2);
}
/* 좁은 폭은 시작 시각만, 넓은 폭은 시각 구간 (student-room.md 「넓은 폭」) */
.today__to {
  display: none;
}
.today__label {
  flex: 1;
  min-width: 0;
}
.today__label--off {
  color: var(--room-free-text);
}
/* 취소선은 선으로 그린다 — WeekGrid 휴강과 같은 방식(글자 장식은 굵기·상자에 따라 안 그려진다) */
.today__label--off .today__text {
  background: linear-gradient(currentColor, currentColor) 0 55% / 100% 1px no-repeat;
  -webkit-box-decoration-break: clone;
  box-decoration-break: clone;
}
.today__label--mine {
  color: var(--brand);
  font-weight: var(--font-weight-bold);
}
.today__until {
  color: var(--text-3);
}
.room__next-v {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.room__muted {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.room__week {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 48px;
  padding: 0 var(--space-4);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-md);
  background: var(--surface);
  color: var(--text-1);
  font-weight: var(--font-weight-bold);
  text-decoration: none;
}
.room__cta {
  position: sticky;
  bottom: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3) var(--space-4);
  border-top: var(--border-thin) solid var(--line-2);
  background: var(--surface);
  text-align: center;
}
@media (min-width: 640px) {
  .today__to {
    display: inline;
  }
  /* 넓은 폭은 시각 구간이 끝을 이미 말한다 — '—HH:MM' 을 두 번 쓰지 않는다 */
  .today__until {
    display: none;
  }
}
</style>
