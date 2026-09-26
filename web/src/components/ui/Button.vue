<script lang="ts">
export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost'
</script>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
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
// 진행 라벨("3/12 적용 중")은 숫자가 바뀌어도 폭이 흔들리면 안 된다 (components.md) — 숫자를 가장 긴
// 자릿수의 0 으로 채운 문자열을 숨겨 두어 폭을 미리 잡는다. .num(tabular-nums)이라 숫자 폭은 0 과 같다
const sizer = computed(() => {
  const label = props.loadingLabel
  if (!label) return ''
  const width = Math.max(...(label.match(/\d+/g) ?? ['']).map((s) => s.length))
  return label.replace(/\d+/g, '0'.repeat(width))
})
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
    <span class="btn__label">
      <span :class="{ btn__ghost: loading && loadingLabel }"><slot /></span>
      <span v-if="loadingLabel" class="btn__ghost num" aria-hidden="true">{{ sizer }}</span>
      <span v-if="loading && loadingLabel" class="btn__progress num">{{ loadingLabel }}</span>
    </span>
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
/* 기본 라벨·폭 잡이·진행 라벨을 한 칸에 겹친다 — 폭은 셋 중 가장 넓은 것 */
.btn__label {
  display: inline-grid;
}
.btn__label > * {
  grid-area: 1 / 1;
  text-align: center;
}
.btn__ghost {
  visibility: hidden;
}
.btn {
  transition:
    background-color var(--dur-fast) ease,
    border-color var(--dur-fast) ease,
    color var(--dur-fast) ease,
    transform var(--dur-fast) var(--ease-soft);
}
.btn:active:enabled {
  transform: scale(0.97);
}
</style>
