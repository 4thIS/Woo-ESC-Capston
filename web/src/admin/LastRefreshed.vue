<script setup lang="ts">
import { formatHm, formatKst } from '@/lib/time'
import { useStale } from '@/lib/useStale'

const props = defineProps<{ at: Date | null }>()
const { stale } = useStale(() => props.at)
</script>

<template>
  <!-- 색만으로 말하지 않는다 — 멈췄으면 문장을 붙인다 -->
  <p
    v-if="at"
    class="refreshed num"
    :class="{ 'refreshed--stale': stale }"
    :title="formatKst(at)"
    role="status"
  >
    마지막 갱신 {{ formatHm(at) }}<template v-if="stale"> · 갱신이 멈췄습니다</template>
  </p>
</template>

<style scoped>
.refreshed {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.refreshed--stale {
  color: var(--danger);
  font-weight: var(--font-weight-bold);
}
</style>
