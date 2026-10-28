<script setup lang="ts">
import Badge from '@/components/ui/Badge.vue'
import type { SlotSource } from '@/api/types'
import { SOURCE_LABEL } from './rules'

defineProps<{ source: SlotSource }>()
const STYLE = {
  1: { tone: 'neutral', variant: 'outline' },
  2: { tone: 'neutral', variant: 'solid' },
  3: { tone: 'danger', variant: 'outline' },
} as const
</script>

<template>
  <Badge
    :tone="STYLE[source].tone"
    :variant="STYLE[source].variant"
    :title="
      source === 1 ? 'CSV 로 들어온 행 — 다음 CSV 가 덮는다' : '웹에서 고친 행 — CSV 가 덮지 않는다'
    "
  >
    <!-- 이게 없으면 CSV 임포트 뒤 "왜 이 행만 안 바뀌지"를 설명할 수 없다 (admin-rooms.md §1) -->
    {{ SOURCE_LABEL[source] }}
  </Badge>
</template>
