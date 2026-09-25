<script setup lang="ts">
import Toast from './Toast.vue'
import { dismissToast, toasts } from './toast'
</script>

<template>
  <div class="toast-host" aria-live="polite">
    <Toast
      v-for="t in toasts"
      :key="t.id"
      :tone="t.tone"
      :message="t.message"
      :action="t.action"
      @dismiss="dismissToast(t.id)"
    />
  </div>
</template>

<style scoped>
.toast-host {
  position: fixed;
  top: var(--space-4);
  right: var(--space-4);
  z-index: 200;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
</style>
