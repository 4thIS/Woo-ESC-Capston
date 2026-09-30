<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/components/ui/Badge.vue'
import type { SlotType } from '@/api/types'
import { BUSY_TYPES, TYPE_LABEL } from './rules'

const props = defineProps<{ type: SlotType }>()
const busy = computed(() => BUSY_TYPES.includes(props.type))
</script>

<template>
  <Badge :tone="busy ? 'busy' : 'neutral'" :variant="busy ? 'tint' : 'outline'">
    <!-- 1·2·5·6 은 같은 busy — 구분은 라벨 (e-Paper RED 이분법과 1:1). 매핑을 화면마다 다시 쓰지 않는다 -->
    {{ TYPE_LABEL[type] }}
  </Badge>
</template>
