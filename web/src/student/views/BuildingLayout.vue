<script setup lang="ts">
import { computed, onMounted, provide, ref, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import { studentApi } from '@/api/student'
import type { RoomStateOut } from '@/api/types'
import NextResvCard from '@/components/student/NextResvCard.vue'
import RoomListRow from '@/components/student/RoomListRow.vue'
import {
  FREE_LAYOUT,
  dateLabel,
  layoutLabel,
  nextResv,
  rowState,
  untilText,
} from '@/components/student/rules'
import Banner from '@/components/ui/Banner.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Select from '@/components/ui/Select.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import { session } from '@/lib/session'
import { formatHm, kstDateStr, kstMinutes } from '@/lib/time'
import { usePolling } from '@/lib/usePolling'
import { useResource } from '@/lib/useResource'
import RefreshedNote from '../RefreshedNote.vue'
import { BUILDING, useMine } from '../building'
import { POLL_MS, schoolTitle, useNow, useWide } from '../composables'
import { favKey, favorites, rememberBld, toggleFavorite } from '../favorites'
import { buildingsOf, byFloor, defaultRoom, roomStats, topic } from '../roomView'
import NotFoundView from './NotFoundView.vue'

const route = useRoute()
const router = useRouter()
// 학교 전체 방 — 개수·목록·건물 Select·자식 화면의 room_id 가 모두 여기서 나온다
const { data, error, refreshedAt, reload } = useResource(() => studentApi.rooms())
usePolling(reload, POLL_MS)
const loaded = computed(() => data.value !== undefined)

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

// 다음 예약 카드 — 내 예약은 앱이 한 번 불러 메뉴 배지와 같이 쓴다. 불러오지 못하면 카드만 없다(목록이 본업)
const mine = useMine()
provide(BUILDING, { rooms: data, loaded, error, reload, mine })
const now = useNow()
const next = computed(() => nextResv(mine.data.value ?? [], now.value))
const meTo = computed(() => `/${bld.value}/me`)

// 폰 머리말 · 인사 줄 · 숫자 칸 (student-room.md 「학생 앱 메뉴 · 이용 안내」). 넓은 폭은 위 막대가 맡는다
const wide = useWide()
const school = schoolTitle
const dateText = computed(() => `${dateLabel(kstDateStr(now.value))}요일`)
const greet = computed(() => {
  const place = `지금 ${topic(building.value?.name ?? '')}`
  const name = session.value?.name
  return name ? `${name}님, ${place}` : place
})
const stats = computed(() => roomStats(rooms.value, kstMinutes(now.value)))
// 층 묶음 — 즐겨찾기 보기는 건물을 가리지 않아 묶지 않는다
const groups = computed(() =>
  filter.value === 'fav' ? [{ floor: null, rooms: shown.value }] : byFloor(shown.value),
)
// 넓은 폭의 건물 선택은 위 막대 오른쪽 끝(StudentNav #esc-nav-bld)으로 — 그 자리가 없으면(단독) 보내지 않는다
const navSlot = ref(false)
onMounted(() => {
  navSlot.value = !!document.getElementById('esc-nav-bld')
})
const options = computed(() => buildings.value.map((b) => ({ value: b.bld, label: b.name })))
/** 좁은 폭에서 자식(강의실·주간·예약)이 있으면 목록을 감춘다 — 넓은 폭은 둘 다 (CSS) */
const hasChild = computed(() => route.matched.length > 1)

// 넓은 폭 /{bld} — 오른쪽 칸을 비우지 않는다: 즐겨찾기 → 빈 곳 → 첫 강의실 (replace — 뒤로가기로 다시 튕기지 않게)
watch(
  [wide, hasChild, () => building.value?.bld],
  ([w, child, b]) => {
    if (!w || child || !b || route.params.room !== undefined) return
    const r = defaultRoom(rooms.value, favorites.value)
    if (r) void router.replace(`/${r.bld}/${r.room}`)
  },
  { immediate: true },
)

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
      <header v-if="!wide" class="top">
        <span class="top__brand"
          ><b>ESC</b><template v-if="school !== 'ESC'">{{ school }}</template></span
        >
        <Select
          v-if="options.length > 1"
          class="top__bld"
          label="건물"
          :model-value="bld"
          :options="options"
          @update:model-value="pickBuilding"
        />
      </header>
      <Teleport v-else-if="navSlot && options.length > 1" to="#esc-nav-bld">
        <Select
          class="top__bld"
          label="건물"
          :model-value="bld"
          :options="options"
          @update:model-value="pickBuilding"
        />
      </Teleport>
      <!-- 오래된 값이라도 지우지 않는다 — 갱신 줄이 오래됐다고 말한다 -->
      <Banner v-if="error && loaded" tone="danger" :message="error.message" :dismissible="false">
        <Button variant="secondary" @click="retry">다시 시도</Button>
      </Banner>
      <div class="list">
        <template v-if="!wide && building">
          <div class="hello">
            <p class="hello__text">
              <span class="hello__date">{{ dateText }}</span
              ><b>{{ greet }}</b>
            </p>
            <span class="hello__clock num">{{ formatHm(now) }}</span>
          </div>
          <dl class="stats">
            <div class="stats__item stats__item--free">
              <dt>지금 빈 곳</dt>
              <dd class="num">{{ stats.free }}</dd>
            </div>
            <div class="stats__item stats__item--busy">
              <dt>사용중</dt>
              <dd class="num">{{ stats.busy }}</dd>
            </div>
            <div class="stats__item">
              <dt>곧 비는 곳</dt>
              <dd class="num">{{ stats.soon }}</dd>
            </div>
          </dl>
        </template>
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
            <!-- 폰은 숫자 칸이 개수를 말한다 — 제목은 '강의실' -->
            <h2 class="list__count">
              <template v-if="!wide">강의실</template>
              <template v-else-if="freeCount"
                ><span class="num">{{ freeCount }}곳</span>이 지금 비어 있어요</template
              >
              <template v-else>지금 비어 있는 강의실이 없어요</template>
            </h2>
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
          <template v-for="g in groups" v-else :key="g.floor ?? 'fav'">
            <h3 v-if="g.floor !== null" class="floor">{{ g.floor }}층</h3>
            <ul class="rows">
              <RoomListRow
                v-for="r in g.rooms"
                :key="r.room_id"
                :to="`/${r.bld}/${r.room}`"
                :room="r.room"
                :building="otherBld(r)"
                :current="r.bld === bld && String(r.room) === route.params.room"
                :state="rowState(r.layout)"
                :label="layoutLabel(r.layout)"
                :until="untilText(r.layout, r.until)"
                :fav="favSet.has(favKey(r.bld, r.room))"
                @toggle-fav="toggleFavorite(favKey(r.bld, r.room))"
              />
            </ul>
          </template>
        </template>
      </div>
      <footer class="foot">
        <RefreshedNote :at="refreshedAt" />
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
/* 넓은 폭은 위 막대(StudentNav, 64px) 아래부터 */
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
    min-height: calc(100vh - 64px);
  }
  .split__list {
    position: sticky;
    top: 64px;
    height: calc(100vh - 64px);
    overflow-y: auto;
    border-right: var(--border-thin) solid var(--line-2);
  }
}
.split__list {
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  background: var(--surface);
}
/* 폰 머리말 — ESC · 학교 · 건물 선택 */
.top {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: 58px;
  padding: var(--space-2) var(--space-4);
  border-bottom: var(--border-thin) solid var(--line-1);
}
.top__brand {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  overflow: hidden;
  color: var(--text-2);
  white-space: nowrap;
  text-overflow: ellipsis;
}
.top__brand b {
  font-size: var(--font-size-lg);
  letter-spacing: 0.04em;
  color: var(--brand);
}
.top__bld {
  flex: none;
  width: 120px;
}
.top__bld :deep(.sel__label) {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
/* 인사 줄 + 지금 시각 */
.hello {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-3);
}
.hello__text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
}
.hello__date {
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
.hello__text b {
  font-size: var(--font-size-xl);
  line-height: var(--leading-tight);
}
.hello__clock {
  flex: none;
  font-size: var(--font-size-display-auth);
  font-weight: var(--font-weight-bold);
  line-height: 1;
}
/* 숫자 칸 셋 — 누르는 칸이 아니다 */
.stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-2);
  margin: 0;
}
.stats__item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-3);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.stats__item dt {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  color: var(--text-2);
}
.stats__item dd {
  margin: 0;
  font-size: var(--font-size-display-auth);
  font-weight: var(--font-weight-bold);
  line-height: var(--leading-tight);
}
.stats__item--free {
  border-color: var(--brand-tint);
  background: var(--brand-tint);
}
.stats__item--free dt,
.stats__item--free dd {
  color: var(--brand);
}
.stats__item--busy {
  border-color: var(--room-busy-fill);
  background: var(--room-busy-fill);
}
.stats__item--busy dt,
.stats__item--busy dd {
  color: var(--room-busy-label);
}
.floor {
  margin: var(--space-1) 0 calc(-1 * var(--space-1));
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  color: var(--text-3);
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
