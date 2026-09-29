<script setup lang="ts">
defineProps<{ series: { label: string; color: string }[] }>()
</script>

<template>
  <!-- 계열 1개면 제목이 이름을 진다 — 범례 없음 -->
  <ul v-if="series.length >= 2" class="legend">
    <li v-for="s in series" :key="s.label" class="legend__item">
      <span class="legend__mark" :style="{ background: s.color }" aria-hidden="true" />{{ s.label }}
    </li>
  </ul>
</template>

<style scoped>
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin: 0;
  padding: 0;
  list-style: none;
}
.legend__item {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--font-size-xs);
  color: var(--text-2); /* 글자는 계열색을 입지 않는다 */
}
.legend__mark {
  width: 9px;
  height: 9px;
  border-radius: var(--radius-sm);
}
</style>
