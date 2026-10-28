<script setup lang="ts">
import { RouterLink, type RouteLocationRaw } from 'vue-router'

// 이동이라 button 이 아니라 a — 모양은 Button 의 variant 와 같다(primary = 화면의 1차 동작 brand 채움).
// 모바일 48px, 넓은 폭 헤더 40px
withDefaults(
  defineProps<{
    to: RouteLocationRaw
    compact?: boolean
    variant?: 'primary' | 'secondary' | 'ghost'
  }>(),
  { compact: false, variant: 'primary' },
)
</script>

<template>
  <RouterLink :to="to" class="cta" :class="[`cta--${variant}`, { 'cta--compact': compact }]"
    ><slot
  /></RouterLink>
</template>

<style scoped>
.cta {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: var(--control-height-md);
  padding: 0 var(--space-4);
  border: var(--border-thin) solid transparent;
  border-radius: var(--radius-md);
  font-weight: var(--font-weight-bold);
  text-decoration: none;
  white-space: nowrap;
}
.cta--compact {
  min-height: 40px;
}
.cta--primary {
  background: var(--brand);
  color: var(--on-brand);
}
.cta--primary:hover {
  filter: brightness(0.9);
}
.cta--secondary {
  border-color: var(--line-3);
  background: var(--surface);
  color: var(--text-1);
}
.cta--ghost {
  background: transparent;
  color: var(--text-1);
}
.cta--secondary:hover,
.cta--ghost:hover {
  background: var(--sunken);
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
