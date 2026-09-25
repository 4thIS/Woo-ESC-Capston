<script lang="ts">
import type { NodeWarning } from '@/api/types'

/** 우선순위 unseen > low_batt > resync > clock_stale (admin-nodes.md, 서버 WARNING_ORDER 와 같다) */
export const WARNING_ORDER: NodeWarning[] = ['unseen', 'low_batt', 'resync', 'clock_stale']
export const WARNING_LABEL: Record<NodeWarning, string> = {
  unseen: '응답 없음',
  low_batt: '배터리',
  resync: '재동기 중',
  clock_stale: '시계',
}
</script>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/components/ui/Badge.vue'

// 판정은 서버가 한다 — 받은 배열을 배지 하나로 줄이기만 한다
const props = withDefaults(defineProps<{ warnings?: NodeWarning[] }>(), { warnings: () => [] })
const present = computed(() => WARNING_ORDER.filter((w) => props.warnings.includes(w)))
const worst = computed(() => present.value[0])
const rest = computed(
  () =>
    present.value
      .slice(1)
      .map((w) => WARNING_LABEL[w])
      .join(' · ') || undefined,
)
const danger = computed(() => worst.value === 'unseen' || worst.value === 'low_batt')
</script>

<template>
  <Badge v-if="!worst" variant="solid">동기화됨</Badge>
  <Badge v-else variant="outline" :tone="danger ? 'danger' : 'neutral'" :title="rest">{{
    WARNING_LABEL[worst]
  }}</Badge>
</template>
