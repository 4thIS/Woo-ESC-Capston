<script setup lang="ts">
import { RouterLink } from 'vue-router'
import Badge from './Badge.vue'

defineProps<{ items: { to: string; label: string; badge?: number }[] }>()
</script>

<template>
  <nav class="nav">
    <ul class="nav__list">
      <li v-for="i in items" :key="i.to">
        <RouterLink :to="i.to" class="nav__item" active-class="nav__item--active">
          <span>{{ i.label }}</span>
          <Badge v-if="i.badge" variant="solid" class="num">{{ i.badge }}</Badge>
        </RouterLink>
      </li>
    </ul>
    <div v-if="$slots.footer" class="nav__footer"><slot name="footer" /></div>
  </nav>
</template>

<style scoped>
.nav {
  display: flex;
  flex-direction: column;
  width: 220px;
  min-height: 100vh;
  padding: var(--space-3) var(--space-2);
  background: var(--sunken);
  border-right: var(--border-thin) solid var(--line-2);
}
.nav__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.nav__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 32px;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  font-size: var(--font-size-md);
  color: var(--text-2);
  text-decoration: none;
}
.nav__item:hover {
  background: var(--nav-hover);
}
.nav__item--active,
.nav__item--active:hover {
  background: var(--brand-tint);
  color: var(--brand);
  font-weight: var(--font-weight-medium);
}
.nav__footer {
  margin-top: auto;
  padding: var(--space-3);
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
</style>
