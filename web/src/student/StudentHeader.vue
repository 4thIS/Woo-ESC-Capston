<script setup lang="ts">
import { RouterLink } from 'vue-router'

// 58px 상단 — ‹ 는 진짜 링크(뒤로가기와 결과가 같아야 한다, student-room.md 화면 2)
withDefaults(
  defineProps<{
    title: string
    back?: string
    backLabel?: string
    backText?: string
    hideBackWide?: boolean
    showMe?: boolean
    meTo?: string
  }>(),
  { backLabel: '뒤로', backText: '‹', hideBackWide: false, showMe: false, meTo: '/me' },
)
</script>

<template>
  <header class="sh" :class="{ 'sh--nobackwide': hideBackWide }">
    <RouterLink v-if="back" :to="back" class="sh__back" :aria-label="backLabel">{{
      backText
    }}</RouterLink>
    <h1 class="sh__title">{{ title }}</h1>
    <div v-if="$slots.default || showMe" class="sh__right">
      <slot />
      <RouterLink v-if="showMe" :to="meTo" class="sh__me">내 예약</RouterLink>
    </div>
  </header>
</template>

<style scoped>
.sh {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  height: 58px;
  padding: 0 var(--space-2) 0 var(--space-4);
  border-bottom: var(--border-thin) solid var(--line-2);
  background: var(--surface);
}
.sh__back {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  margin-left: calc(-1 * var(--space-3));
  font-size: var(--font-size-xl);
  color: var(--text-1);
  text-decoration: none;
}
.sh__title {
  flex: 1;
  min-width: 0;
  margin: 0;
  overflow: hidden;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  white-space: nowrap;
  text-overflow: ellipsis;
}
.sh__right {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.sh__me {
  display: inline-flex;
  align-items: center;
  min-height: 48px;
  padding: 0 var(--space-2);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
  color: var(--text-1);
  white-space: nowrap;
}
@media (min-width: 640px) {
  .sh--nobackwide .sh__back {
    display: none;
  }
}
</style>
