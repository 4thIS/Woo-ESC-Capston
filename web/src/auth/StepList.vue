<script setup lang="ts">
defineProps<{ steps: string[]; current: number }>()
const MARK = ['①', '②', '③', '④', '⑤']
</script>

<template>
  <!-- 번호는 장식이 아니라 실제 순서 — 지금 단계만 brand (auth.md) -->
  <ol class="steps">
    <li
      v-for="(s, i) in steps"
      :key="s"
      class="steps__item"
      :class="{ 'steps__item--current': i === current }"
      :aria-current="i === current ? 'step' : undefined"
    >
      <span aria-hidden="true">{{ MARK[i] }}</span> {{ s }}
    </li>
  </ol>
</template>

<style scoped>
.steps {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.steps__item--current {
  color: var(--brand);
  font-weight: var(--font-weight-bold);
}
</style>
