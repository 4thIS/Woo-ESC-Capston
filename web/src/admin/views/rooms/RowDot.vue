<script setup lang="ts">
import Button from '@/components/ui/Button.vue'
import OutboxDot, { type DotState } from '@/components/domain/OutboxDot.vue'

defineProps<{ state?: DotState; busy?: boolean }>()
const emit = defineEmits<{ resync: [] }>()
</script>

<template>
  <span v-if="state" class="rowdot">
    <OutboxDot :state="state" />
    <!-- 실패·관리자 취소는 노드에 가지 않았다 — 방 단위 재전송 (POST /rooms/{id}/sync) -->
    <Button
      v-if="state === 'failed' || state === 'cancelled'"
      variant="ghost"
      size="sm"
      :loading="busy"
      @click="emit('resync')"
      >재전송</Button
    >
  </span>
</template>

<style scoped>
.rowdot {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
}
</style>
