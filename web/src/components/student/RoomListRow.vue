<script setup lang="ts">
import { RouterLink } from 'vue-router'
import Badge from '@/components/ui/Badge.vue'
import FavoriteStar from './FavoriteStar.vue'

// 링크 안에 버튼을 넣지 않는다 — 어느 쪽이 눌렸는지·스크린리더가 헷갈린다 (student-room.md 화면 1)
defineProps<{
  to: string
  room: number
  state: 'busy' | 'free' | 'other'
  label: string
  until: string
  fav: boolean
}>()
const emit = defineEmits<{ toggleFav: [] }>()
</script>

<template>
  <li class="row">
    <RouterLink :to="to" class="row__link" :aria-label="`${room}호 ${label} ${until}`">
      <span class="row__room num">{{ room }}호</span>
      <span class="row__state">
        <Badge v-if="state === 'busy'" tone="busy" size="sm">{{ label }}</Badge>
        <span v-else :class="state === 'free' ? 'row__free' : 'row__other'">{{ label }}</span>
      </span>
      <span class="row__until num">{{ until }}</span>
      <span class="row__chev" aria-hidden="true">›</span>
    </RouterLink>
    <FavoriteStar :on="fav" :name="`${room}호`" @toggle="emit('toggleFav')" />
  </li>
</template>

<style scoped>
.row {
  display: flex;
  align-items: center;
  min-height: 56px;
  padding-right: var(--space-1);
  border-bottom: var(--border-thin) solid var(--line-1);
}
.row:last-child {
  border-bottom: 0;
}
.row__link {
  flex: 1;
  min-width: 0;
  min-height: 56px;
  display: grid;
  grid-template-columns: auto 1fr auto;
  column-gap: var(--space-3);
  align-items: center;
  padding: var(--space-2) 0 var(--space-2) var(--space-4);
  color: var(--text-1);
  text-decoration: none;
}
.row__room {
  grid-column: 1;
  grid-row: 1 / 3;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.row__state {
  grid-column: 2;
  grid-row: 1;
  display: flex;
  align-items: center;
  font-size: var(--font-size-sm);
}
.row__free {
  color: var(--room-free-text);
  font-weight: var(--font-weight-bold);
}
.row__other {
  color: var(--text-2);
}
.row__until {
  grid-column: 2;
  grid-row: 2;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.row__chev {
  grid-column: 3;
  grid-row: 1 / 3;
  font-size: var(--font-size-lg);
  color: var(--text-3);
}
.row__link {
  transition:
    background-color var(--dur-fast) ease,
    transform var(--dur-fast) var(--ease-soft);
}
.row__link:hover {
  background: var(--nav-hover);
}
.row__link:active {
  transform: scale(0.99);
}
.row__chev {
  transition: transform var(--dur-base) var(--ease-spring);
}
.row__link:hover .row__chev {
  transform: translateX(3px);
}
</style>
