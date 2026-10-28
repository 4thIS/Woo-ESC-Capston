<script setup lang="ts">
import { ref } from 'vue'

const props = withDefaults(
  defineProps<{
    tone?: 'neutral' | 'danger'
    message: string
    dismissible?: boolean
    storageKey?: string
  }>(),
  { tone: 'neutral', dismissible: true },
)
const emit = defineEmits<{ dismiss: [] }>()
const key = props.storageKey ? `banner:${props.storageKey}` : null

function wasDismissed(): boolean {
  if (!key) return false
  try {
    return localStorage.getItem(key) === '1'
  } catch {
    return false // 사생활 보호 모드 등 — 기억 못 해도 배너는 보인다
  }
}
const hidden = ref(wasDismissed())

function dismiss() {
  hidden.value = true
  if (key) {
    try {
      localStorage.setItem(key, '1')
    } catch {
      /* 기억 못 해도 지금은 닫는다 */
    }
  }
  emit('dismiss')
}
</script>

<template>
  <div
    v-if="!hidden"
    class="banner"
    :class="`banner--${tone}`"
    :role="tone === 'danger' ? 'alert' : 'status'"
  >
    <p class="banner__msg">{{ message }} <slot /></p>
    <button
      v-if="dismissible"
      type="button"
      class="banner__close"
      aria-label="닫기"
      @click="dismiss"
    >
      ×
    </button>
  </div>
</template>

<style scoped>
.banner {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--sunken);
  border-bottom: var(--border-thin) solid var(--line-2);
  color: var(--text-1);
}
.banner--danger .banner__msg {
  color: var(--danger);
}
.banner__msg {
  flex: 1;
  margin: 0;
}
.banner__close {
  border: 0;
  background: none;
  color: var(--text-2);
  font: inherit;
  font-size: var(--font-size-lg);
  cursor: pointer;
}
</style>
