<script setup lang="ts">
// 저장(localStorage)은 화면이 한다 — 이 컴포넌트는 모양과 이름만 (student-room.md)
defineProps<{ on: boolean }>()
const emit = defineEmits<{ toggle: [] }>()
</script>

<template>
  <button
    type="button"
    class="star"
    :class="{ 'star--on': on }"
    :aria-label="on ? '즐겨찾기 해제' : '즐겨찾기 추가'"
    :aria-pressed="on"
    @click="emit('toggle')"
  >
    {{ on ? '★' : '☆' }}
  </button>
</template>

<style scoped>
.star {
  flex: 0 0 auto;
  width: 48px;
  height: 48px;
  padding: 0;
  border: 0;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-disabled);
  font: inherit;
  font-size: var(--font-size-xl);
  line-height: 1;
  cursor: pointer;
}
.star--on {
  color: var(--brand);
}
.star:hover {
  background: var(--sunken);
}
</style>
