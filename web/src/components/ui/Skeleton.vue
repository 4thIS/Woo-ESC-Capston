<script setup lang="ts">
withDefaults(defineProps<{ variant?: 'text' | 'block'; rows?: number; width?: string }>(), {
  variant: 'text',
  rows: 1,
  width: '100%',
})
</script>

<template>
  <div class="sk" :class="`sk--${variant}`" aria-hidden="true">
    <template v-if="variant === 'text'">
      <span
        v-for="i in rows"
        :key="i"
        class="sk__line"
        :style="{ width: rows > 1 && i === rows ? '60%' : width }"
      />
    </template>
    <span v-else class="sk__block" :style="{ width }" />
  </div>
</template>

<style scoped>
.sk--text {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.sk__line,
.sk__block {
  display: block;
  border-radius: var(--radius-sm);
  background: var(--skeleton-a);
  animation: pulse 1.4s ease-in-out infinite;
}
.sk__line {
  height: var(--font-size-md);
}
.sk__block {
  height: 100%;
  min-height: var(--control-height-md);
}
@keyframes pulse {
  50% {
    background: var(--skeleton-b);
  }
}
@media (prefers-reduced-motion: reduce) {
  .sk__line,
  .sk__block {
    animation: none;
  }
}
</style>
