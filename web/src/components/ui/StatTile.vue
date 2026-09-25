<script setup lang="ts">
withDefaults(
  defineProps<{
    label: string
    value: string | number
    unit?: string
    sub?: string
    tone?: 'neutral' | 'danger'
  }>(),
  { tone: 'neutral' },
)
</script>

<template>
  <div class="stat">
    <p class="stat__label">{{ label }}</p>
    <p class="stat__value num" :class="{ 'stat__value--danger': tone === 'danger' }">
      {{ value }}<span v-if="unit" class="stat__unit">{{ unit }}</span>
    </p>
    <p v-if="sub" class="stat__sub">{{ sub }}</p>
  </div>
</template>

<style scoped>
.stat {
  padding: var(--space-4);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-md);
}
.stat p {
  margin: 0;
}
.stat__label {
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
.stat__value {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  line-height: var(--leading-tight);
}
.stat__value--danger {
  color: var(--danger);
}
.stat__unit {
  margin-left: 2px;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--text-2);
}
.stat__sub {
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
</style>
