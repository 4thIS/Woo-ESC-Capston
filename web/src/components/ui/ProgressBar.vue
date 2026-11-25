<script setup lang="ts">
import { computed } from 'vue'

// components.md ProgressBar — 퍼센트 글자는 화면이 옆에 적는다
const props = defineProps<{ value: number; max: number; label: string }>()
const pct = computed(() =>
  props.max > 0 ? Math.min(100, Math.max(0, (props.value / props.max) * 100)) : 0,
)
</script>

<template>
  <div
    class="progress"
    role="progressbar"
    :aria-valuenow="value"
    aria-valuemin="0"
    :aria-valuemax="max"
    :aria-label="label"
  >
    <div class="progress__fill" :style="{ width: `${pct}%` }" />
  </div>
</template>

<style scoped>
.progress {
  height: 8px;
  overflow: hidden;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-full);
  background: var(--sunken);
}
.progress__fill {
  height: 100%;
  border-radius: var(--radius-full);
  background: var(--brand);
  transition: width 0.2s;
}
@media (prefers-reduced-motion: reduce) {
  .progress__fill {
    transition: none;
  }
}
</style>
