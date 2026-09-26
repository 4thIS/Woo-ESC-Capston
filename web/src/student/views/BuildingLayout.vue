<script setup lang="ts">
import { computed, provide, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { studentApi } from '@/api/student'
import type { RoomStateOut } from '@/api/types'
import RoomListRow from '@/components/student/RoomListRow.vue'
import { FREE_LAYOUT, layoutLabel, rowState, untilText } from '@/components/student/rules'
import Banner from '@/components/ui/Banner.vue'
import Button from '@/components/ui/Button.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Select from '@/components/ui/Select.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import { formatHm } from '@/lib/time'
import { usePolling } from '@/lib/usePolling'
import { useResource } from '@/lib/useResource'
import RefreshedNote from '../RefreshedNote.vue'
import StudentHeader from '../StudentHeader.vue'
import { BUILDING } from '../building'
import { POLL_MS } from '../composables'
import { favKey, favorites, rememberBld, toggleFavorite } from '../favorites'
import { buildingsOf } from '../roomView'
import NotFoundView from './NotFoundView.vue'

const route = useRoute()
const router = useRouter()
// 학교 전체 방 — 개수·목록·건물 Select·자식 화면의 room_id 가 모두 여기서 나온다
const { data, error, refreshedAt, reload } = useResource(() => studentApi.rooms())
usePolling(reload, POLL_MS)
const loaded = computed(() => data.value !== undefined)
provide(BUILDING, { rooms: data, loaded, error, reload })

const bld = computed(() => String(route.params.bld))
const all = computed(() => data.value ?? [])
const buildings = computed(() => buildingsOf(all.value))
const building = computed(() => buildings.value.find((b) => b.bld === bld.value) ?? null)
// 글자가 바뀔 때만 — 폴링마다 building 객체가 새로 생겨도 다시 적지 않는다
watch(
  () => building.value?.bld,
  (b) => {
    if (b) rememberBld(b)
  },
  { immediate: true },
)
const rooms = computed(() => all.value.filter((r) => r.bld === bld.value))
const freeCount = computed(() => rooms.value.filter((r) => r.layout === FREE_LAYOUT).length)
// '빈 강의실만' 기본 켜짐 — 18개보다 5개가 목적에 맞는다
const freeOnly = ref(true)
// 건물을 바꾸면 기본으로 — 앞 건물에서 끈 필터가 따라오지 않게
watch(bld, () => {
  freeOnly.value = true
})
const shown = computed(() =>
  freeOnly.value ? rooms.value.filter((r) => r.layout === FREE_LAYOUT) : rooms.value,
)
const favSet = computed(() => new Set(favorites.value))
const favRooms = computed(() => all.value.filter((r) => favSet.value.has(favKey(r.bld, r.room))))
const chipName = (r: RoomStateOut) => `${r.bld === bld.value ? '' : `${r.building} `}${r.room}호`
const options = computed(() => buildings.value.map((b) => ({ value: b.bld, label: b.name })))
/** 좁은 폭에서 자식(강의실·주간·예약)이 있으면 목록을 감춘다 — 넓은 폭은 둘 다 (CSS) */
const hasChild = computed(() => route.matched.length > 1)

const retry = () => void reload()
const showAll = () => {
  freeOnly.value = false
}
const pickBuilding = (v: string | number) => void router.push(`/${v}`)
</script>

<template>
  <NotFoundView v-if="loaded && !building" back="/" back-label="건물 목록으로" />
  <div v-else class="split" :class="{ 'split--child': hasChild }">
    <section class="split__list" aria-label="강의실 목록">
      <StudentHeader title="MJC ESC" show-me>
        <Select
          v-if="options.length > 1"
          class="split__bld"
          label="건물"
          :model-value="bld"
          :options="options"
          @update:model-value="pickBuilding"
        />
      </StudentHeader>
      <!-- 오래된 값이라도 지우지 않는다 — 갱신 줄이 오래됐다고 말한다 -->
      <Banner v-if="error && loaded" tone="danger" :message="error.message" :dismissible="false">
        <Button variant="secondary" @click="retry">다시 시도</Button>
      </Banner>
      <div class="list">
        <template v-if="!loaded">
          <EmptyState
            v-if="error"
            message="강의실 목록을 불러오지 못했어요"
            :actions="[{ label: '다시 시도', variant: 'primary', onClick: retry }]"
          />
          <Skeleton v-else :rows="5" />
        </template>
        <template v-else-if="building">
          <h2 class="list__count">
            <template v-if="freeCount"
              ><span class="num">{{ freeCount }}곳</span>이 지금 비어 있어요</template
            >
            <template v-else>지금 비어 있는 강의실이 없어요</template>
          </h2>
          <p class="list__sub num">
            {{ building.name }} {{ rooms.length }}개 강의실<template v-if="refreshedAt">
              · {{ formatHm(refreshedAt) }} 기준</template
            >
          </p>

          <section v-if="favRooms.length" class="fav" aria-labelledby="fav-h">
            <!-- 안내는 제목 밖 — 제목의 접근 이름은 '즐겨찾기' 만 -->
            <div class="fav__head">
              <h3 id="fav-h" class="list__h">즐겨찾기</h3>
              <span class="list__hint">★ 을 눌러 모아둡니다</span>
            </div>
            <ul class="fav__chips">
              <li v-for="r in favRooms" :key="favKey(r.bld, r.room)">
                <RouterLink
                  :to="`/${r.bld}/${r.room}`"
                  class="fav__chip"
                  :aria-label="`${chipName(r)} ${layoutLabel(r.layout)}`"
                >
                  <span class="fav__star" aria-hidden="true">★</span>
                  <span class="num">{{ chipName(r) }}</span>
                  <span class="fav__state">{{ layoutLabel(r.layout) }}</span>
                </RouterLink>
              </li>
            </ul>
          </section>

          <div class="list__bar">
            <h3 class="list__h">{{ building.name }} 전체</h3>
            <Checkbox v-model="freeOnly" label="빈 강의실만" />
          </div>
          <EmptyState
            v-if="!shown.length"
            message="지금은 모든 강의실이 사용 중입니다"
            :actions="[{ label: '전체 보기', onClick: showAll }]"
          />
          <ul v-else class="rows">
            <RoomListRow
              v-for="r in shown"
              :key="r.room_id"
              :to="`/${r.bld}/${r.room}`"
              :room="r.room"
              :state="rowState(r.layout)"
              :label="layoutLabel(r.layout)"
              :until="untilText(r.layout, r.until)"
              :fav="favSet.has(favKey(r.bld, r.room))"
              @toggle-fav="toggleFavorite(favKey(r.bld, r.room))"
            />
          </ul>
          <RefreshedNote :at="refreshedAt" />
        </template>
      </div>
    </section>
    <section class="split__main">
      <RouterView v-if="hasChild" v-slot="{ Component, route: r }">
        <div :key="r.matched[r.matched.length - 1]?.path" class="page">
          <component :is="Component" />
        </div>
      </RouterView>
      <EmptyState v-else message="왼쪽 목록에서 강의실을 고르세요" />
    </section>
  </div>
</template>

<style scoped>
.split {
  min-height: 100vh;
}
.split__list,
.split__main {
  min-width: 0;
}
/* 좁은 폭 — 목록과 자식 중 하나만 (뒤로가기로 오간다) */
@media (max-width: 639px) {
  .split--child .split__list {
    display: none;
  }
  .split:not(.split--child) .split__main {
    display: none;
  }
}
/* 넓은 폭 — 목록 340px 상주, 화면을 키우지 않고 더 보여준다 (student-room.md 「넓은 폭」) */
@media (min-width: 640px) {
  .split {
    display: grid;
    grid-template-columns: 340px minmax(0, 1fr);
  }
  .split__list {
    position: sticky;
    top: 0;
    height: 100vh;
    overflow-y: auto;
    border-right: var(--border-thin) solid var(--line-2);
  }
}
.split__bld {
  width: 132px;
}
.split__bld :deep(.sel__label) {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
}
.list__count {
  margin: 0;
  font-size: 24px; /* student-room.md 화면 1 "24px bold" — 치수 토큰에 24 가 없다(xl 20) */
  font-weight: var(--font-weight-bold);
  line-height: var(--leading-tight);
}
.list__sub {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
.list__h {
  margin: 0;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-bold);
}
.list__hint {
  margin-left: var(--space-2);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-regular);
  color: var(--text-3);
}
.list__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}
.fav {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.fav__head {
  display: flex;
  align-items: baseline;
}
.fav__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}
.fav__chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  min-height: 48px;
  padding: 0 var(--space-3);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-full);
  background: var(--surface);
  color: var(--text-1);
  font-weight: var(--font-weight-bold);
  text-decoration: none;
}
.fav__star {
  color: var(--brand);
}
.fav__state {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-regular);
  color: var(--text-2);
}
.rows {
  margin: 0;
  padding: 0;
  list-style: none;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
</style>
