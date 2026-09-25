<script setup lang="ts">
import { computed, useId } from 'vue'
import { clipBytes, utf8Bytes } from '@/lib/bytes'

defineOptions({ inheritAttrs: false })
const props = withDefaults(
  defineProps<{
    modelValue?: string | number
    label?: string
    hint?: string
    error?: string
    required?: boolean
    disabled?: boolean
    size?: 'sm' | 'md'
    maxBytes?: number
    multiline?: boolean
  }>(),
  { size: 'md' },
)
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const id = useId()
const msgId = `${id}-msg`
const bytes = computed(() => utf8Bytes(String(props.modelValue ?? '')))
const hasMsg = computed(() => Boolean(props.error || props.hint || props.maxBytes))

function commit(target: EventTarget | null) {
  const el = target as HTMLInputElement | HTMLTextAreaElement
  let v = el.value
  if (props.maxBytes && utf8Bytes(v) > props.maxBytes) {
    v = clipBytes(v, props.maxBytes)
    el.value = v
  }
  emit('update:modelValue', v)
}
function onInput(e: Event) {
  if ((e as InputEvent).isComposing) return // 한글 조합 중에는 자르지 않는다
  commit(e.target)
}
</script>

<template>
  <div class="field" :class="[`field--${size}`, { 'field--error': error }]">
    <label v-if="label" :for="id" class="field__label"
      >{{ label }}<span v-if="required" class="field__req" aria-hidden="true">*</span></label
    >
    <component
      :is="multiline ? 'textarea' : 'input'"
      :id="id"
      class="field__control"
      :class="{ 'field__control--multi': multiline }"
      :value="modelValue ?? ''"
      :required="required"
      :disabled="disabled"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="hasMsg ? msgId : undefined"
      v-bind="$attrs"
      @input="onInput"
      @compositionend="(e: Event) => commit(e.target)"
    />
    <p v-if="error" :id="msgId" class="field__msg field__msg--error" role="alert">{{ error }}</p>
    <p v-else-if="hint || maxBytes" :id="msgId" class="field__msg">
      <span>{{ hint }}</span>
      <span v-if="maxBytes" class="num">{{ bytes }} / {{ maxBytes }} B</span>
    </p>
  </div>
</template>

<style scoped>
.field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.field__label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-regular);
  color: var(--text-2);
}
.field__req {
  margin-left: 2px;
  color: var(--danger);
}
.field__control {
  height: var(--control-height-md);
  padding: 0 var(--space-3);
  border: var(--border-thin) solid var(--line-3);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-1);
  font: inherit;
}
.field--sm .field__control {
  height: var(--control-height-sm);
}
.field__control--multi {
  height: auto;
  padding: var(--space-2) var(--space-3);
  resize: vertical;
}
.field__control:disabled {
  color: var(--text-disabled);
  opacity: 0.6;
  cursor: not-allowed;
}
.field__control[readonly] {
  background: var(--sunken);
}
.field--error .field__control {
  border: var(--border-thick) solid var(--danger);
}
/* 에러와 포커스가 겹치면 outline 만 */
.field--error .field__control:focus-visible {
  border-color: var(--line-3);
}
.field__msg {
  display: flex;
  justify-content: space-between;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.field__msg--error {
  color: var(--danger);
}
</style>
