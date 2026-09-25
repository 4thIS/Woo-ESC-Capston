<script setup lang="ts">
import { useId } from 'vue'

type Opt = { value: string | number; label: string; disabled?: boolean }
const props = withDefaults(
  defineProps<{
    modelValue?: string | number
    options: Opt[]
    label?: string
    placeholder?: string
    disabled?: boolean
    size?: 'sm' | 'md'
  }>(),
  { size: 'md' },
)
const emit = defineEmits<{ 'update:modelValue': [value: string | number] }>()
const id = useId()

function onChange(e: Event) {
  const i = (e.target as HTMLSelectElement).selectedIndex - (props.placeholder ? 1 : 0)
  const opt = props.options[i]
  if (opt) emit('update:modelValue', opt.value)
}
</script>

<template>
  <div class="sel" :class="`sel--${size}`">
    <label v-if="label" :for="id" class="sel__label">{{ label }}</label>
    <select
      :id="id"
      class="sel__control"
      :disabled="disabled"
      :value="modelValue ?? ''"
      @change="onChange"
    >
      <option v-if="placeholder" value="" disabled>{{ placeholder }}</option>
      <option v-for="o in options" :key="o.value" :value="o.value" :disabled="o.disabled">
        {{ o.label }}
      </option>
    </select>
  </div>
</template>

<style scoped>
.sel {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.sel__label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-regular);
  color: var(--text-2);
}
.sel__control {
  height: var(--control-height-md);
  padding: 0 calc(var(--space-3) * 2 + 8px) 0 var(--space-3);
  border: var(--border-thin) solid var(--line-3);
  border-radius: var(--radius-sm);
  color: var(--text-1);
  font: inherit;
  appearance: none;
  /* 화살표만 배경으로 갈아 끼운다 (components.md) — 두 삼각 그라데이션으로 V 자 */
  background:
    linear-gradient(45deg, transparent 50%, var(--text-2) 50%) no-repeat
      calc(100% - var(--space-3) - 4px) 50% / 4px 4px,
    linear-gradient(135deg, var(--text-2) 50%, transparent 50%) no-repeat
      calc(100% - var(--space-3)) 50% / 4px 4px,
    var(--surface);
}
.sel--sm .sel__control {
  height: var(--control-height-sm);
}
.sel__control:disabled {
  color: var(--text-disabled);
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
