<script setup lang="ts">
import { computed } from 'vue'
import type { ResvStatus } from '@/api/types'
import Badge from '@/components/ui/Badge.vue'

const props = defineProps<{ status: ResvStatus }>()
// approved 만 room.busy 틴트 — 적색은 "그 방이 실제로 쓰인다"는 뜻 (student-room.md §상태 다섯)
const LABEL: Record<ResvStatus, string> = {
  requested: '대기중',
  approved: '승인됨',
  rejected: '거절됨',
  cancelled: '취소됨',
  expired: '만료됨',
}
const busy = computed(() => props.status === 'approved')
</script>

<template>
  <Badge :tone="busy ? 'busy' : 'neutral'" :variant="busy ? 'tint' : 'outline'" size="sm">{{
    LABEL[status]
  }}</Badge>
</template>
