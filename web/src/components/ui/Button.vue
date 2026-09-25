<script lang="ts">
export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost'
</script>

<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: ButtonVariant
    size?: 'sm' | 'md'
    disabled?: boolean
    loading?: boolean
    loadingLabel?: string
    type?: 'button' | 'submit'
  }>(),
  { variant: 'primary', size: 'md', disabled: false, loading: false, type: 'button' },
)
</script>

<template>
  <button
    :type="type"
    class="btn"
    :class="[`btn--${variant}`, `btn--${size}`]"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
  >
    <span v-if="loading" class="btn__spin" aria-hidden="true" />
    <template v-if="loading && loadingLabel">{{ loadingLabel }}</template>
    <slot v-else />
  </button>
</template>

<style scoped>
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  height: var(--control-height-md);
  padding: 0 var(--space-4);
  border: var(--border-thin) solid transparent;
  border-radius: var(--radius-md);
  font: inherit;
  font-weight: var(--font-weight-medium);
  white-space: nowrap;
  cursor: pointer;
}
.btn--sm {
  height: var(--control-height-sm);
}
.btn--primary {
  background: var(--brand);
  color: var(--on-brand);
}
.btn--danger {
  background: var(--danger);
  color: var(--on-brand);
}
.btn--secondary {
  background: var(--surface);
  border-color: var(--line-3);
  color: var(--text-1);
}
.btn--ghost {
  background: transparent;
  color: var(--text-1);
}
.btn--primary:hover:enabled,
.btn--danger:hover:enabled {
  filter: brightness(0.9);
}
.btn--secondary:hover:enabled,
.btn--ghost:hover:enabled {
  background: var(--sunken);
}
/* disabled: 글자 text.disabled + opacity .6, hue 는 그대로. loading 은 잠그기만 하고 색은 유지 */
.btn:disabled:not([aria-busy]) {
  color: var(--text-disabled);
  opacity: 0.6;
  cursor: not-allowed;
}
.btn[aria-busy] {
  cursor: progress;
}
.btn__spin {
  width: 1em;
  height: 1em;
  border: var(--border-thick) solid currentColor;
  border-right-color: transparent;
  border-radius: var(--radius-full);
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .btn__spin {
    animation: none;
  }
}
</style>
