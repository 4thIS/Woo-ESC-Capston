<script setup lang="ts">
import { computed, provide, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { studentApi } from '@/api/student'
import type { RoomStateOut } from '@/api/types'
import NextResvCard from '@/components/student/NextResvCard.vue'
import RoomListRow from '@/components/student/RoomListRow.vue'
import { FREE_LAYOUT, layoutLabel, nextResv, rowState, untilText } from '@/components/student/rules'
import Banner from '@/components/ui/Banner.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Select from '@/components/ui/Select.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import { clearSession, session } from '@/lib/session'
import { usePolling } from '@/lib/usePolling'
import { useResource } from '@/lib/useResource'
import RefreshedNote from '../RefreshedNote.vue'
import { BUILDING } from '../building'
import { POLL_MS, useNow } from '../composables'
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
// 보기 — '빈 곳' 기본(18개보다 5개가 목적에 맞는다). 즐겨찾기는 건물을 가리지 않는다
type Filter = 'free' | 'all' | 'fav'
const FILTERS: { value: Filter; label: string }[] = [
  { value: 'free', label: '빈 곳' },
  { value: 'all', label: '전체' },
  { value: 'fav', label: '★ 즐겨찾기' },
]
const filter = ref<Filter>('free')
// 건물을 바꾸면 기본으로 — 앞 건물에서 고른 보기가 따라오지 않게
watch(bld, () => {
  filter.value = 'free'
})
const favSet = computed(() => new Set(favorites.value))
const shown = computed(() =>
  filter.value === 'fav'
    ? all.value.filter((r) => favSet.value.has(favKey(r.bld, r.room)))
    : filter.value === 'free'
      ? rooms.value.filter((r) => r.layout === FREE_LAYOUT)
      : rooms.value,
)
const otherBld = (r: RoomStateOut) => (r.bld === bld.value ? undefined : r.building)

// 사이드바 맨 위 — 나와 다음 예약. 불러오지 못하면 카드만 없다(목록이 본업)
const me = computed(() => session.value?.name ?? '')
const mine = useResource(() => studentApi.mine())
usePolling(mine.reload, POLL_MS)
const now = useNow()
const next = computed(() => nextResv(mine.data.value ?? [], now.value))
const meTo = computed(() => `/${bld.value}/me`)
function logout() {
  clearSession()
  void router.replace('/login')
}
const options = computed(() => buildings.value.map((b) => ({ value: b.bld, label: b.name })))
/** 좁은 폭에서 자식(강의실·주간·예약)이 있으면 목록을 감춘다 — 넓은 폭은 둘 다 (CSS) */
const hasChild = computed(() => route.matched.length > 1)

const retry = () => void reload()
const showAll = () => {
  filter.value = 'all'
}
const pickBuilding = (v: string | number) => void router.push(`/${v}`)
</script>

<template>
  <NotFoundView v-if="loaded && !building" back="/" back-label="건물 목록으로" />
  <div v-else class="split" :class="{ 'split--child': hasChild }">
    <section class="split__list" aria-label="강의실 목록">
      <div class="me">
        <span class="me__avatar" aria-hidden="true">{{ me.slice(0, 1) || '나' }}</span>
        <p class="me__who">
          <b>{{ me }}</b
          ><span>MJC ESC</span>
        </p>
        <RouterLink :to="meTo" class="me__link">내 예약</RouterLink>
      </div>
      <!-- 오래된 값이라도 지우지 않는다 — 갱신 줄이 오래됐다고 말한다 -->
      <Banner v-if="error && loaded" tone="danger" :message="error.message" :dismissible="false">
        <Button variant="secondary" @click="retry">다시 시도</Button>
      </Banner>
      <div class="list">
        <NextResvCard v-if="next" :resv="next" :now="now" :to="meTo" />
        <template v-if="!loaded">
          <EmptyState
            v-if="error"
            message="강의실 목록을 불러오지 못했어요"
            :actions="[{ label: '다시 시도', variant: 'primary', onClick: retry }]"
          />
          <Skeleton v-else :rows="5" />
        </template>
        <template v-else-if="building">
          <div class="list__head">
            <h2 class="list__count">
              <template v-if="freeCount"
                ><span class="num">{{ freeCount }}곳</span>이 지금 비어 있어요</template
              >
              <template v-else>지금 비어 있는 강의실이 없어요</template>
            </h2>
            <Select
              v-if="options.length > 1"
              class="list__bld"
              label="건물"
              :model-value="bld"
              :options="options"
              @update:model-value="pickBuilding"
            />
          </div>
          <div class="chips" role="group" aria-label="보기">
            <button
              v-for="f in FILTERS"
              :key="f.value"
              type="button"
              class="chips__chip"
              :aria-pressed="filter === f.value"
              @click="filter = f.value"
            >
              {{ f.label }}
            </button>
          </div>
          <EmptyState
            v-if="!shown.length && filter === 'fav'"
            message="★ 을 눌러 자주 가는 강의실을 모아두세요"
          />
          <EmptyState
            v-else-if="!shown.length"
            message="지금은 모든 강의실이 사용 중입니다"
            :actions="[{ label: '전체 보기', onClick: showAll }]"
          />
          <ul v-else class="rows">
            <RoomListRow
              v-for="r in shown"
              :key="r.room_id"
              :to="`/${r.bld}/${r.room}`"
              :room="r.room"
              :building="otherBld(r)"
              :state="rowState(r.layout)"
              :label="layoutLabel(r.layout)"
              :until="untilText(r.layout, r.until)"
              :fav="favSet.has(favKey(r.bld, r.room))"
              @toggle-fav="toggleFavorite(favKey(r.bld, r.room))"
            />
          </ul>
        </template>
      </div>
      <footer class="foot">
        <RefreshedNote :at="refreshedAt" />
        <Button variant="ghost" size="sm" @click="logout">로그아웃</Button>
      </footer>
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
.split__list {
  display: flex;
  flex-direction: column;
  min-height: 100vh; /* 갱신 줄·로그아웃이 화면 바닥에 */
  box-sizing: border-box;
  background: var(--surface);
}
.me {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-4) 0;
}
.me__avatar {
  display: grid;
  place-items: center;
  flex: none;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-full);
  background: var(--sunken);
  color: var(--text-2);
  font-weight: var(--font-weight-bold);
}
.me__who {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  margin: 0;
}
.me__who b {
  font-size: var(--font-size-md);
}
.me__who span {
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.me__link {
  display: inline-flex;
  align-items: center;
  min-height: 48px; /* 터치 목표 하한 (tokens.md) */
  padding: 0 var(--space-2);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
  color: var(--text-1);
}
.list {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
}
.list__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}
.list__count {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  line-height: var(--leading-tight);
}
.list__bld {
  flex: none;
  width: 112px;
}
.list__bld :deep(.sel__label) {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.chips__chip {
  min-height: 48px; /* 터치 목표 하한 (tokens.md) */
  padding: 0 var(--space-3);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-full);
  background: var(--surface);
  color: var(--text-2);
  font: inherit;
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition:
    background-color var(--dur-fast) ease,
    border-color var(--dur-fast) ease,
    color var(--dur-fast) ease,
    transform var(--dur-fast) var(--ease-soft);
}
.chips__chip:hover {
  background: var(--nav-hover);
}
.chips__chip:active {
  transform: scale(0.97);
}
.chips__chip[aria-pressed='true'] {
  border-color: var(--brand);
  background: var(--brand-tint);
  color: var(--brand);
  font-weight: var(--font-weight-bold);
}
.rows {
  margin: 0;
  padding: 0;
  list-style: none;
  overflow: hidden;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-2) var(--space-2) var(--space-4);
  border-top: var(--border-thin) solid var(--line-1);
}
</style>
