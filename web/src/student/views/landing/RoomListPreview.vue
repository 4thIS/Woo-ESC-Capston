<script setup lang="ts">
import TypeBadge from '@/components/domain/TypeBadge.vue'

// 강의실 목록(화면 1)의 축소 — 고정 예시라 서버를 부르지 않는다. 눌리지 않는 한 덩어리 그림 (landing.md 「미리보기」)
defineProps<{ rows: 3 | 4 }>()
const ROWS = [
  { room: 401, type: 1 as const, until: '10:50 까지', fav: false },
  { room: 402, type: null, until: '13:00 까지', fav: true },
  { room: 403, type: 2 as const, until: '12:00 까지', fav: false },
  { room: 404, type: null, until: '오늘 계속 비어 있어요', fav: false },
]
</script>

<template>
  <ul class="lp" role="img" aria-label="강의실 목록 예시">
    <li v-for="r in ROWS.slice(0, rows)" :key="r.room" class="lr">
      <span class="lr__room num">{{ r.room }}호</span>
      <span class="lr__state">
        <TypeBadge v-if="r.type" :type="r.type" />
        <span v-else class="lr__free">비어있음</span>
        <span class="lr__until num">{{ r.until }}</span>
      </span>
      <span class="lr__star" :class="{ 'lr__star--on': r.fav }">{{ r.fav ? '★' : '☆' }}</span>
    </li>
  </ul>
</template>

<style scoped>
.lp {
  margin: 0;
  padding: 0;
  list-style: none;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.lr {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  column-gap: var(--space-3);
  min-height: 52px;
  padding: var(--space-2) var(--space-4);
  border-bottom: var(--border-thin) solid var(--line-1);
}
.lr:last-child {
  border-bottom: 0;
}
.lr__room {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.lr__state {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  min-width: 0;
}
.lr__free {
  font-size: var(--font-size-sm);
  color: var(--room-free-text);
}
.lr__until {
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.lr__star {
  font-size: var(--font-size-lg);
  color: var(--text-disabled); /* ★ brand / ☆ text.disabled (student-room.md 즐겨찾기) */
}
.lr__star--on {
  color: var(--brand);
}
</style>
