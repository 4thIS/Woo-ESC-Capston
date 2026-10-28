import { readonly, ref } from 'vue'

export type ToastTone = 'neutral' | 'danger'
export interface ToastAction {
  label: string
  onClick: () => void
}
export interface ToastItem {
  id: number
  tone: ToastTone
  message: string
  action?: ToastAction
}

const MAX = 3
const items = ref<ToastItem[]>([])
export const toasts = readonly(items)
let seq = 0

export function dismissToast(id: number): void {
  items.value = items.value.filter((t) => t.id !== id)
}

/** danger 는 자동으로 사라지지 않는다 — 에러를 놓치면 안 된다 (components.md) */
export function showToast(t: {
  tone?: ToastTone
  message: string
  action?: ToastAction
  duration?: number
}): number {
  const id = ++seq
  const tone = t.tone ?? 'neutral'
  items.value = [...items.value, { id, tone, message: t.message, action: t.action }].slice(-MAX)
  const duration = t.duration ?? (tone === 'danger' ? 0 : 5000)
  if (duration > 0) setTimeout(() => dismissToast(id), duration)
  return id
}
