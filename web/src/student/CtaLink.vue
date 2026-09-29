<script setup lang="ts">
import { RouterLink, type RouteLocationRaw } from 'vue-router'

// 화면의 1차 동작 — brand 채움 링크 (이동이라 button 이 아니라 a). 모바일 48px, 넓은 폭 헤더 40px
withDefaults(defineProps<{ to: RouteLocationRaw; compact?: boolean }>(), { compact: false })
</script>

<template>
  <RouterLink :to="to" class="cta" :class="{ 'cta--compact': compact }"><slot /></RouterLink>
</template>

<style scoped>
.cta {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: var(--control-height-md);
  padding: 0 var(--space-4);
  border-radius: var(--radius-md);
  background: var(--brand);
  color: var(--on-brand);
  font-weight: var(--font-weight-bold);
  text-decoration: none;
  white-space: nowrap;
}
.cta--compact {
  min-height: 40px;
}
.cta:hover {
  filter: brightness(0.9);
}
.cta {
  transition:
    background-color var(--dur-fast) ease,
    transform var(--dur-fast) var(--ease-soft);
}
.cta:active {
  transform: scale(0.98);
}
</style>
