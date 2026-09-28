<script setup lang="ts">
import { nextTick, onMounted, onScopeDispose, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import Badge from './Badge.vue'

export type NavIcon = 'building' | 'settings' | 'calendar' | 'node' | 'send' | 'users'
const props = defineProps<{
  items: { to: string; label: string; badge?: number; group?: string; icon?: NavIcon }[]
}>()

// 24×24 선 아이콘 — stroke 는 currentColor 라 글자색(선택·hover)을 그대로 따른다
const ICONS: Record<NavIcon, string> = {
  building: 'M4 21V5l8-3 8 3v16M9 21v-4h6v4M8 8h1M8 12h1M15 8h1M15 12h1',
  settings: 'M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M16 4v4M10 10v4M18 16v4',
  calendar:
    'M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2ZM3 10h18M8 3v4M16 3v4',
  node: 'M12 19h.01M8.5 15.5a5 5 0 0 1 7 0M5.5 12.5a9 9 0 0 1 13 0M2.5 9.5a13 13 0 0 1 19 0',
  send: 'M3 12h4l3-8 4 16 3-8h4',
  users:
    'M9 11.5A3.5 3.5 0 1 0 9 4.5a3.5 3.5 0 0 0 0 7ZM2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6 6 0 0 1 3.5 6',
}
const showGroup = (i: number) => {
  const g = props.items[i].group
  return !!g && g !== props.items[i - 1]?.group
}

// 선택 표시(pill)는 목록 위에 하나만 두고 선택된 항목 자리로 미끄러뜨린다 — 항목마다 배경을 켜고 끄면 '툭' 바뀐다
const list = ref<HTMLElement | null>(null)
const pill = ref({ y: 0, h: 0, on: false, ready: false })
const route = useRoute()
function place() {
  const a = list.value?.querySelector<HTMLElement>('.nav__item--active')
  if (!a) return void (pill.value = { ...pill.value, on: false })
  pill.value = { y: a.offsetTop, h: a.offsetHeight, on: true, ready: pill.value.ready }
  // 첫 자리는 움직이지 않고 놓는다 — 화면을 열 때 위에서 날아오지 않게
  if (!pill.value.ready) requestAnimationFrame(() => (pill.value.ready = true))
}
watch(
  () => [route.path, props.items.length],
  () => nextTick(place),
)
onMounted(() => nextTick(place))
window.addEventListener('resize', place)
onScopeDispose(() => window.removeEventListener('resize', place))
</script>

<template>
  <nav class="nav">
    <div v-if="$slots.header" class="nav__header"><slot name="header" /></div>
    <ul ref="list" class="nav__list">
      <li
        class="nav__pill"
        :class="{ 'nav__pill--on': pill.on, 'nav__pill--ready': pill.ready }"
        :style="{ transform: `translateY(${pill.y}px)`, height: `${pill.h}px` }"
        aria-hidden="true"
      ></li>
      <template v-for="(i, n) in items" :key="i.to">
        <!-- 묶음 제목은 제목으로 — 스크린리더가 제목 이동으로 묶음을 건넌다 -->
        <li v-if="showGroup(n)" class="nav__group" role="none">
          <h2 class="nav__group-h">{{ i.group }}</h2>
        </li>
        <li>
          <RouterLink
            :to="i.to"
            class="nav__item"
            active-class="nav__item--active"
            :aria-label="i.badge ? `${i.label}, 대기 ${i.badge}건` : undefined"
          >
            <svg v-if="i.icon" class="nav__icon" viewBox="0 0 24 24" aria-hidden="true">
              <path :d="ICONS[i.icon]" />
            </svg>
            <span class="nav__label">{{ i.label }}</span>
            <Transition name="nav-pop">
              <Badge v-if="i.badge" :key="i.badge" variant="solid" class="nav__count num">{{
                i.badge
              }}</Badge>
            </Transition>
          </RouterLink>
        </li>
      </template>
    </ul>
    <div v-if="$slots.footer" class="nav__footer"><slot name="footer" /></div>
  </nav>
</template>

<style scoped>
/* 움직임 — 애플식 감속(빠르게 출발해 길게 멈춤)과 살짝 튀는 스프링. 모두 transform·opacity 만 */
.nav {
  display: flex;
  flex-direction: column;
  width: 220px;
  min-height: 100vh;
  padding: var(--space-3) var(--space-2);
  background: var(--sunken);
  border-right: var(--border-thin) solid var(--line-2);
}
.nav__header {
  padding: var(--space-1) var(--space-2) var(--space-3);
  margin-bottom: var(--space-1);
  border-bottom: var(--border-thin) solid var(--line-1);
}
.nav__list {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.nav__group {
  margin: var(--space-3) var(--space-3) var(--space-1);
}
.nav__group-h {
  margin: 0;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  letter-spacing: 0.06em;
  color: var(--text-3);
}
.nav__pill {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  border-radius: var(--radius-md);
  background: var(--brand-tint);
  opacity: 0;
  pointer-events: none;
}
.nav__pill--on {
  opacity: 1;
}
.nav__pill--ready {
  transition:
    transform var(--dur-slow) var(--ease-soft),
    height var(--dur-slow) var(--ease-soft),
    opacity var(--dur-fast) ease;
}
.nav__item {
  position: relative; /* pill 위에 글자가 오도록 */
  display: flex;
  align-items: center;
  gap: var(--space-3);
  height: var(--control-height-md);
  padding: 0 var(--space-3);
  border-radius: var(--radius-md);
  font-size: var(--font-size-md);
  color: var(--text-2);
  text-decoration: none;
  transition:
    background-color var(--dur-fast) ease,
    color var(--dur-fast) ease,
    transform var(--dur-fast) var(--ease-soft);
}
.nav__item:hover:not(.nav__item--active) {
  background: var(--nav-hover);
}
.nav__item:active {
  transform: scale(0.98);
}
.nav__item--active {
  color: var(--brand);
  font-weight: var(--font-weight-medium);
}
.nav__icon {
  width: 16px;
  height: 16px;
  flex: none;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
  transition: transform var(--dur-base) var(--ease-spring);
}
.nav__item:hover .nav__icon {
  transform: translateX(1px) scale(1.06);
}
.nav__label {
  flex: 1;
  min-width: 0;
}
/* 숫자가 생기거나 바뀌면 말랑하게 톡 */
.nav-pop-enter-active {
  transition:
    transform var(--dur-base) var(--ease-spring),
    opacity var(--dur-fast) ease;
}
.nav-pop-leave-active {
  position: absolute;
  right: var(--space-3);
  transition:
    transform var(--dur-fast) ease,
    opacity var(--dur-fast) ease;
}
.nav-pop-enter-from,
.nav-pop-leave-to {
  transform: scale(0.5);
  opacity: 0;
}
.nav__footer {
  margin-top: auto;
  padding-top: var(--space-3);
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
@media (prefers-reduced-motion: reduce) {
  .nav__pill--ready,
  .nav__item,
  .nav__icon,
  .nav-pop-enter-active,
  .nav-pop-leave-active {
    transition: none;
  }
  .nav__item:active,
  .nav__item:hover .nav__icon {
    transform: none;
  }
}
</style>
