<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: 'solid' | 'tint' | 'outline'
    tone?: 'neutral' | 'busy' | 'danger' | 'brand'
    size?: 'xs' | 'sm'
  }>(),
  { variant: 'tint', tone: 'neutral', size: 'xs' },
)
</script>

<template>
  <span class="badge" :class="[`badge--${variant}`, `badge--${tone}`, `badge--${size}`]">
    <slot />
  </span>
</template>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--space-2);
  border: var(--border-thin) solid transparent;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  line-height: var(--leading-tight);
  white-space: nowrap;
}
.badge--sm {
  font-size: var(--font-size-sm);
}
/* components.md 표의 네 조합만 — 표에 없는 조합은 mh 확인 뒤 */
.badge--busy.badge--tint {
  background: var(--room-busy-fill);
  border-color: var(--room-busy-line);
  color: var(--room-busy-label);
}
.badge--neutral.badge--outline {
  border-color: var(--line-3);
  color: var(--text-2);
}
.badge--neutral.badge--solid {
  background: var(--sunken);
  color: var(--text-1);
}
.badge--danger.badge--outline {
  border-color: var(--danger);
  color: var(--danger);
}
/* 학생 강의실 화면의 '지금' 배지 — brand 채움 + 흰 글자 (student-room.md 화면 2). 적색은 쓰지 않는다 */
.badge--brand.badge--solid {
  background: var(--brand);
  color: var(--on-brand);
}
</style>
