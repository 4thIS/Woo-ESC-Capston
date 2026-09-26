<script setup lang="ts">
import { nextTick, ref, useId, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    open: boolean
    title: string
    size?: 'sm' | 'md' | 'lg'
    closeOnBackdrop?: boolean
    /** 다른 모달 위 — 열려 있는 편집 모달에 가리면 안 되는 확인(자동 로그아웃 경고) */
    top?: boolean
  }>(),
  { size: 'md', closeOnBackdrop: true, top: false },
)
const emit = defineEmits<{ close: [] }>()
const titleId = useId()
const panel = ref<HTMLElement>()
let opener: HTMLElement | null = null

const FOCUSABLE =
  'input:not([disabled]),select:not([disabled]),textarea:not([disabled]),button:not([disabled]),a[href],[tabindex]:not([tabindex="-1"])'
const focusables = () => [...(panel.value?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])]

watch(
  () => props.open,
  async (open) => {
    if (open) {
      opener = document.activeElement as HTMLElement | null
      await nextTick()
      // data-autofocus → 첫 입력 → 없으면 첫 포커스 대상 (components.md).
      // data-autofocus 는 안전한 쪽을 고를 때 — 첫 버튼이 되돌릴 수 없는 동작이면 Enter 한 번에 실행된다
      const first =
        panel.value?.querySelector<HTMLElement>('[data-autofocus]') ??
        panel.value?.querySelector<HTMLElement>(
          'input:not([disabled]),select:not([disabled]),textarea:not([disabled])',
        ) ??
        focusables()[0]
      ;(first ?? panel.value)?.focus()
    } else {
      await nextTick()
      opener?.focus()
      opener = null
    }
  },
  { immediate: true },
)

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.stopPropagation()
    if (props.closeOnBackdrop) emit('close') // false = 폼이 더럽다 — Esc 로도 버리지 않는다
  } else if (e.key === 'Tab') {
    const f = focusables()
    if (!f.length) return
    const i = f.indexOf(document.activeElement as HTMLElement)
    const next = e.shiftKey ? (i <= 0 ? f.length - 1 : i - 1) : i === f.length - 1 ? 0 : i + 1
    e.preventDefault()
    f[next].focus()
  }
}
function onBackdrop() {
  if (props.closeOnBackdrop) emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="modal" :class="{ 'modal--top': top }">
      <div class="modal__backdrop" @mousedown.self="onBackdrop" />
      <div
        ref="panel"
        class="modal__panel"
        :class="`modal__panel--${size}`"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        tabindex="-1"
        @keydown="onKeydown"
      >
        <h2 :id="titleId" class="modal__title">{{ title }}</h2>
        <div class="modal__body"><slot /></div>
        <div v-if="$slots.footer" class="modal__footer"><slot name="footer" /></div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: grid;
  place-items: center;
  padding: var(--space-4);
}
.modal--top {
  z-index: 150; /* 모달(100) 위, 알림(200) 아래 */
}
.modal__backdrop {
  position: absolute;
  inset: 0;
  background: var(--modal-backdrop); /* 블러 없음 */
}
.modal__panel {
  position: relative;
  width: 100%;
  max-height: calc(100vh - var(--space-6));
  overflow: auto;
  padding: var(--space-5);
  border-radius: var(--radius-lg);
  background: var(--surface); /* 그림자 없음 — 배경 딤이 층을 진다 */
}
.modal__panel--sm {
  max-width: 400px;
}
.modal__panel--md {
  max-width: 560px;
}
.modal__panel--lg {
  max-width: 800px;
}
.modal__title {
  margin: 0 0 var(--space-4);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  line-height: var(--leading-tight);
}
.modal__footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  margin-top: var(--space-5);
}
.modal__backdrop {
  animation: esc-fade-in var(--dur-base) ease;
}
.modal__panel {
  animation: esc-rise-in var(--dur-slow) var(--ease-soft);
}
</style>
