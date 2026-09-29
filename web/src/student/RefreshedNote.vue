<script setup lang="ts">
import { formatHm, formatKst } from '@/lib/time'
import { useStale } from '@/lib/useStale'

// 오래된 값이라도 지우지 않는다 — 대신 이 줄이 오래됐다고 말한다 (student-room.md §상태)
const props = withDefaults(defineProps<{ at: Date | null; epaper?: boolean }>(), {
  epaper: true,
})
const { stale } = useStale(() => props.at)
</script>

<template>
  <p class="rn num" :class="{ 'rn--stale': stale }" role="status">
    <template v-if="epaper"><span aria-hidden="true">● </span>문 앞 e-Paper 와 같은 내용</template>
    <template v-if="at"
      >{{ epaper ? ' · ' : ''
      }}<span :title="formatKst(at)">{{ formatHm(at) }} 갱신</span></template
    >
    <template v-if="stale"> · 갱신이 멈췄어요</template>
  </p>
</template>

<style scoped>
.rn {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.rn--stale {
  color: var(--danger);
  font-weight: var(--font-weight-bold);
}
</style>
