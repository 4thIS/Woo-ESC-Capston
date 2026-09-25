<script setup lang="ts">
import Button, { type ButtonVariant } from './Button.vue'

withDefaults(
  defineProps<{
    message: string
    actions?: { label: string; variant?: ButtonVariant; onClick: () => void }[]
  }>(),
  { actions: () => [] },
)
</script>

<template>
  <div class="empty">
    <p class="empty__msg">{{ message }}</p>
    <div v-if="actions.length" class="empty__actions">
      <!-- 최대 2개 (components.md) -->
      <Button
        v-for="a in actions.slice(0, 2)"
        :key="a.label"
        :variant="a.variant ?? 'secondary'"
        @click="a.onClick"
        >{{ a.label }}</Button
      >
    </div>
  </div>
</template>

<style scoped>
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-6) var(--space-4);
  text-align: center;
}
.empty__msg {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.empty__actions {
  display: flex;
  gap: var(--space-2);
}
</style>
