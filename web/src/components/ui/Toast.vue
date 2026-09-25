<script setup lang="ts">
import Button from './Button.vue'
import type { ToastAction } from './toast'

withDefaults(
  defineProps<{ tone?: 'neutral' | 'danger'; message: string; action?: ToastAction }>(),
  {
    tone: 'neutral',
  },
)
const emit = defineEmits<{ dismiss: [] }>()
</script>

<template>
  <div class="toast" :class="`toast--${tone}`" :role="tone === 'danger' ? 'alert' : 'status'">
    <p class="toast__msg">{{ message }}</p>
    <Button
      v-if="action"
      variant="ghost"
      size="sm"
      @click="
        () => {
          action!.onClick()
          emit('dismiss')
        }
      "
      >{{ action.label }}</Button
    >
    <button type="button" class="toast__close" aria-label="닫기" @click="emit('dismiss')">×</button>
  </div>
</template>

<style scoped>
.toast {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 360px;
  max-width: calc(100vw - var(--space-6));
  padding: var(--space-3) var(--space-3) var(--space-3) var(--space-4);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-md);
  background: var(--surface);
  color: var(--text-1);
}
/* 성공에는 색을 쓰지 않는다 — danger 만 왼쪽 3px 띠 */
.toast--danger {
  box-shadow: inset 3px 0 0 var(--danger);
}
.toast__msg {
  flex: 1;
  margin: 0;
}
.toast__close {
  border: 0;
  background: none;
  color: var(--text-2);
  font: inherit;
  font-size: var(--font-size-lg);
  cursor: pointer;
}
</style>
