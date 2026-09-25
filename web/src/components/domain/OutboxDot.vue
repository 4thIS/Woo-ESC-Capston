<script lang="ts">
import type { OutboxState } from '@/api/types'

/** scheduled 는 서버 상태가 아니다 — 7일 창 밖이라 outbox_ids 가 빈 배열일 때 화면이 만든다 (components.md) */
export type DotState = OutboxState | 'scheduled'
export const DOT_LABEL: Record<DotState, string> = {
  queued: '대기',
  dispatched: '전송 중',
  acked: '반영됨',
  failed: '실패',
  // 관리자가 의도한 일이라 경고색은 아니지만, 웹 DB 는 새 값인데 문 앞은 옛 값이다 (admin-rooms.md)
  cancelled: '취소됨 — 노드에 반영 안 됨',
  scheduled: '7일 이내로 들어오면 자동 전송됩니다',
}
</script>

<script setup lang="ts">
import Badge from '@/components/ui/Badge.vue'

defineProps<{ state: DotState }>()
</script>

<template>
  <Badge v-if="state === 'scheduled'" variant="outline" :title="DOT_LABEL.scheduled">예정</Badge>
  <span
    v-else
    class="dot"
    :class="`dot--${state}`"
    role="img"
    :aria-label="DOT_LABEL[state]"
    :title="DOT_LABEL[state]"
  />
</template>

<style scoped>
/* 색이 아니라 채움 정도로 단계를 읽는다 (tokens.md §outbox). gray.400 = --text-disabled, gray.600 = --text-2 */
.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border: 1.5px solid transparent;
  border-radius: var(--radius-full);
  vertical-align: middle;
}
.dot--queued {
  border-color: var(--text-disabled);
}
.dot--dispatched {
  border-color: var(--text-2);
  background: linear-gradient(90deg, var(--text-2) 50%, transparent 50%);
}
.dot--acked {
  background: var(--text-2);
}
.dot--failed {
  background: var(--danger);
}
.dot--cancelled {
  border-color: var(--text-disabled);
  background: linear-gradient(
    135deg,
    transparent 42%,
    var(--text-disabled) 42% 58%,
    transparent 58%
  );
}
</style>
