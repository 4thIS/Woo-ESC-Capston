<script setup lang="ts">
import { computed, ref, watchEffect } from 'vue'

const props = defineProps<{
  modelValue?: boolean | unknown[]
  value?: unknown
  label?: string
  indeterminate?: boolean
  disabled?: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean | unknown[]] }>()
const el = ref<HTMLInputElement>()
const checked = computed(() =>
  Array.isArray(props.modelValue) ? props.modelValue.includes(props.value) : !!props.modelValue,
)
watchEffect(
  () => {
    if (el.value) el.value.indeterminate = !!props.indeterminate
  },
  { flush: 'post' },
)

function onChange(e: Event) {
  const on = (e.target as HTMLInputElement).checked
  if (Array.isArray(props.modelValue)) {
    const rest = props.modelValue.filter((v) => v !== props.value)
    emit('update:modelValue', on ? [...rest, props.value] : rest)
  } else emit('update:modelValue', on)
}
</script>

<template>
  <label class="cb" :class="{ 'cb--disabled': disabled }">
    <span class="cb__wrap">
      <input
        ref="el"
        type="checkbox"
        class="cb__input"
        :checked="checked"
        :disabled="disabled"
        @change="onChange"
      />
      <span class="cb__box" aria-hidden="true" />
    </span>
    <span v-if="label || $slots.default"
      ><slot>{{ label }}</slot></span
    >
  </label>
</template>

<style scoped>
.cb {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--control-height-sm); /* 28px */
  cursor: pointer;
}
/* 학생 웹은 터치 타깃 48px (components.md Checkbox) */
:global([data-surface='student']) .cb {
  min-height: var(--control-height-md);
}
.cb--disabled {
  color: var(--text-disabled);
  opacity: 0.6;
  cursor: not-allowed;
}
.cb__wrap {
  position: relative;
  width: 16px;
  height: 16px;
}
.cb__input {
  position: absolute;
  inset: 0;
  margin: 0;
  opacity: 0;
  cursor: inherit;
}
.cb__box {
  position: absolute;
  inset: 0;
  border: var(--border-thin) solid var(--line-3);
  border-radius: var(--radius-sm);
  background: var(--surface);
  pointer-events: none;
}
.cb__input:checked + .cb__box,
.cb__input:indeterminate + .cb__box {
  border-color: var(--brand);
  background: var(--brand);
}
.cb__input:checked + .cb__box::after {
  content: '';
  position: absolute;
  left: 4px;
  top: 1px;
  width: 5px;
  height: 9px;
  border: solid var(--on-brand);
  border-width: 0 var(--border-thick) var(--border-thick) 0;
  transform: rotate(45deg);
}
.cb__input:indeterminate + .cb__box::after {
  content: '';
  position: absolute;
  left: 3px;
  right: 3px;
  top: 6px;
  height: var(--border-thick);
  background: var(--on-brand);
}
.cb__input:focus-visible + .cb__box {
  outline: var(--border-thick) solid var(--focus);
  outline-offset: 2px;
}
.cb__box {
  transition:
    background-color var(--dur-fast) ease,
    border-color var(--dur-fast) ease,
    transform var(--dur-fast) var(--ease-soft);
}
.cb:hover .cb__input:not(:checked):enabled + .cb__box {
  border-color: var(--text-3);
}
.cb:active .cb__input:enabled + .cb__box {
  transform: scale(0.9);
}
/* 체크 표시가 톡 */
.cb__input:checked + .cb__box::after {
  animation: cb-check var(--dur-base) var(--ease-spring);
}
@keyframes cb-check {
  from {
    opacity: 0;
    transform: rotate(45deg) scale(0.3);
  }
}
</style>
