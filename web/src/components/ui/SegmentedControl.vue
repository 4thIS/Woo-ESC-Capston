<script setup lang="ts">
// 붙은 버튼 줄 (components.md SegmentedControl). 지금 쓰는 곳은 로그인 학생|관리자 탭 하나라 링크 줄만 —
// ponytail: href 없는 라디오 줄(update:value)은 쓰는 곳이 생기면
defineProps<{
  items: { value: string; label: string; href: string }[]
  value: string
  label: string
}>()
</script>

<template>
  <nav class="seg" :aria-label="label">
    <a
      v-for="i in items"
      :key="i.value"
      :href="i.href"
      class="seg__item"
      :class="{ 'seg__item--on': i.value === value }"
      :aria-current="i.value === value ? 'page' : undefined"
      >{{ i.label }}</a
    >
  </nav>
</template>

<style scoped>
/* 선택은 1차 액션이 아니다 — brand 없이 면(surface vs sunken)과 굵기로 고른 칸을 세운다 */
.seg {
  display: grid;
  grid-auto-columns: minmax(0, 1fr);
  grid-auto-flow: column;
  gap: var(--space-1);
  height: var(--control-height-md);
  padding: var(--space-1);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-md);
  background: var(--sunken);
}
.seg__item {
  display: flex;
  align-items: center;
  justify-content: center;
  border: var(--border-thin) solid transparent;
  border-radius: var(--radius-sm);
  color: var(--text-2);
  font-weight: var(--font-weight-medium);
  text-decoration: none;
  transition:
    background-color var(--dur-fast) ease,
    color var(--dur-fast) ease;
}
.seg__item:hover {
  color: var(--text-1);
}
.seg__item--on {
  border-color: var(--line-2);
  background: var(--surface);
  color: var(--text-1);
  font-weight: var(--font-weight-bold);
}
</style>
