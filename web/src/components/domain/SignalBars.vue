<script lang="ts">
/** 칸 수는 화면이 정한다 (admin-nodes.md) — ≥ −75 3칸 · ≥ −90 2칸 · 그 아래 1칸 */
export function signalLevel(rssi: number): 1 | 2 | 3 {
  return rssi >= -75 ? 3 : rssi >= -90 ? 2 : 1
}
</script>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ rssi: number | null }>()
const level = computed(() => (props.rssi == null ? 0 : signalLevel(props.rssi)))
// 음수 기호는 U+2212 (디자인 표기 −71 dBm)
const text = computed(() =>
  props.rssi == null ? '—' : `${props.rssi < 0 ? '−' : ''}${Math.abs(props.rssi)} dBm`,
)
</script>

<template>
  <span class="sig num">
    <svg
      v-if="rssi != null"
      class="sig__bars"
      width="13"
      height="12"
      viewBox="0 0 13 12"
      role="img"
      :aria-label="`신호 3칸 중 ${level}칸`"
    >
      <rect
        v-for="i in 3"
        :key="i"
        :x="(i - 1) * 5"
        :y="12 - i * 4"
        width="3"
        :height="i * 4"
        :class="i <= level ? 'sig__on' : 'sig__off'"
      />
    </svg>
    {{ text }}
  </span>
</template>

<style scoped>
.sig {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
}
/* 색을 쓰지 않는다 — 채운 칸 수로만 */
.sig__on {
  fill: var(--text-2);
}
.sig__off {
  fill: var(--line-3);
}
</style>
