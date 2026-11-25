<script setup lang="ts">
import { computed, inject } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { activeCount } from '@/components/student/rules'
import logo from '@/assets/logo/esc-logo.svg'
import { schoolTitle } from '@/lib/session'
import { MINE } from './building'
import { useNow } from './composables'
import { lastBld } from './favorites'

// 메뉴 넷 (student-room.md 「학생 앱 메뉴 · 이용 안내」) — 폰은 아래 탭, 넓은 폭은 위 막대. 같은 넷을 같은 순서로
withDefaults(
  defineProps<{
    /** 아래 탭 — 상세 화면(강의실 · 이번 주 · 예약)은 하단 고정 바가 있어 끈다 */ tabs?: boolean
  }>(),
  {
    tabs: true,
  },
)
const route = useRoute()
const mine = inject(MINE, null)
const now = useNow()
const count = computed(() => activeCount(mine?.data.value ?? [], now.value))

const bld = computed(() => (typeof route.params.bld === 'string' ? route.params.bld : lastBld()))
type Key = 'rooms' | 'me' | 'guide' | 'account'
const current = computed<Key>(() => {
  const p = route.path
  if (p === '/guide') return 'guide'
  if (p === '/account') return 'account'
  if (p === '/me' || p.endsWith('/me')) return 'me'
  return 'rooms'
})
const items = computed(() => [
  { key: 'rooms' as const, name: '강의실', to: bld.value ? `/${bld.value}` : '/' },
  { key: 'me' as const, name: '내 예약', to: bld.value ? `/${bld.value}/me` : '/me' },
  { key: 'guide' as const, name: '이용 안내', to: '/guide' },
  { key: 'account' as const, name: '내 정보', to: '/account' },
])
</script>

<template>
  <!-- 넓은 폭 위 막대 — 오른쪽 끝 자리(#esc-nav-bld)에 건물 안 화면이 건물 선택을 보낸다 -->
  <header class="nav__top">
    <span class="nav__brand"
      ><img :src="logo" alt="ESC" width="55" height="20" />{{
        schoolTitle === 'ESC' ? '' : schoolTitle
      }}</span
    >
    <nav aria-label="학생 메뉴" class="nav__toplinks">
      <RouterLink
        v-for="i in items"
        :key="i.key"
        :to="i.to"
        class="nav__toplink"
        :aria-current="i.key === current ? 'page' : undefined"
        ><span class="nav__name">{{ i.name }}</span
        ><span v-if="i.key === 'me' && count" class="nav__badge num">{{ count }}</span></RouterLink
      >
    </nav>
    <div id="esc-nav-bld" class="nav__bld" />
  </header>
  <nav v-if="tabs" aria-label="학생 메뉴" class="nav__tabs">
    <RouterLink
      v-for="i in items"
      :key="i.key"
      :to="i.to"
      class="nav__tab"
      :aria-current="i.key === current ? 'page' : undefined"
    >
      <span class="nav__icon" aria-hidden="true">
        <svg v-if="i.key === 'rooms'" viewBox="0 0 22 22">
          <path d="M3.5 19V8l7.5-4.5L18.5 8v11" />
          <path d="M8.5 19v-5h5v5" />
        </svg>
        <svg v-else-if="i.key === 'me'" viewBox="0 0 22 22">
          <rect x="3.5" y="4.5" width="15" height="14" rx="2" />
          <path d="M3.5 9h15M7.5 2.5v4M14.5 2.5v4" />
        </svg>
        <svg v-else-if="i.key === 'guide'" viewBox="0 0 22 22">
          <circle cx="11" cy="11" r="8" />
          <path d="M8.6 8.6a2.5 2.5 0 1 1 3.4 2.3c-.7.3-1 .8-1 1.5v.6" />
          <path d="M11 15.6v.4" />
        </svg>
        <svg v-else viewBox="0 0 22 22">
          <circle cx="11" cy="8" r="3.5" />
          <path d="M4 19c1-3.5 3.8-5 7-5s6 1.5 7 5" />
        </svg>
        <span v-if="i.key === 'me' && count" class="nav__badge nav__badge--dot num">{{
          count
        }}</span>
      </span>
      <span class="nav__name">{{ i.name }}</span>
    </RouterLink>
  </nav>
</template>

<style scoped>
/* 높이 64px — StudentApp(아래 여백) · BuildingLayout(왼쪽 칸 sticky top)이 같은 값을 쓴다 */
.nav__top {
  position: sticky;
  top: 0;
  z-index: 5;
  display: none;
  align-items: center;
  gap: var(--space-5);
  height: 64px;
  padding: 0 var(--space-5);
  border-bottom: var(--border-thin) solid var(--line-2);
  background: var(--surface);
}
.nav__brand {
  display: flex;
  /* 학교명은 로고 바닥선에 붙인다 */
  align-items: flex-end;
  line-height: 1;
  font-size: var(--font-size-xs);
  gap: var(--space-2);
  color: var(--text-2);
  white-space: nowrap;
}
.nav__brand img {
  flex: none;
}
.nav__toplinks {
  display: flex;
  align-self: stretch;
  gap: var(--space-1);
}
.nav__toplink {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 0 var(--space-3);
  border-bottom: 3px solid transparent;
  color: var(--text-2);
  font-weight: var(--font-weight-medium);
  text-decoration: none;
  white-space: nowrap;
}
.nav__toplink:hover {
  background: var(--nav-hover);
}
.nav__toplink[aria-current='page'] {
  border-bottom-color: var(--brand);
  color: var(--brand);
  font-weight: var(--font-weight-bold);
}
.nav__bld {
  margin-left: auto;
}
.nav__badge {
  display: inline-grid;
  place-items: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  box-sizing: border-box;
  border-radius: var(--radius-full);
  background: var(--brand);
  color: var(--on-brand);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
}
/* 폰 아래 탭 — 64px + 기기 아래 여백 */
.nav__tabs {
  position: fixed;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 5;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  height: calc(64px + env(safe-area-inset-bottom));
  padding-bottom: env(safe-area-inset-bottom);
  box-sizing: border-box;
  border-top: var(--border-thin) solid var(--line-2);
  background: var(--surface);
}
.nav__tab {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  color: var(--text-2);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  text-decoration: none;
}
.nav__tab[aria-current='page'] {
  color: var(--brand);
  font-weight: var(--font-weight-bold);
}
.nav__icon {
  position: relative;
  display: flex;
}
.nav__icon svg {
  width: 22px;
  height: 22px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
}
.nav__badge--dot {
  position: absolute;
  top: -6px;
  right: -12px;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
}
@media (min-width: 640px) {
  .nav__top {
    display: flex;
  }
  .nav__tabs {
    display: none;
  }
}
</style>
