<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { ResvMineOut } from '@/api/types'
import { checkinState, resvWhen } from './rules'

// 사이드바 맨 위 — 누르면 내 예약. 체크인·취소 버튼은 두지 않는다(쓰기는 내 예약 한 곳에서)
const props = defineProps<{ resv: ResvMineOut; now: Date; to: string }>()
const ci = computed(() => checkinState(props.resv, props.now))
const hint = computed(() => {
  if (props.resv.status === 'requested') return '관리자 승인을 기다리는 중'
  const c = ci.value
  if (c?.kind === 'open') return '지금 체크인할 수 있어요'
  if (c?.kind === 'before') return `${c.from}부터 체크인`
  if (c?.kind === 'done') return `✓ ${c.at} 체크인`
  return ''
})
</script>

<template>
  <RouterLink
    :to="to"
    class="nr"
    :class="{ 'nr--wait': resv.status === 'requested' }"
    :aria-label="`다음 예약 ${resv.building} ${resv.room}호 ${resvWhen(resv)} ${hint}`"
  >
    <span class="nr__label"
      >다음 예약 · {{ resv.status === 'approved' ? '승인됨' : '대기중' }}</span
    >
    <b class="nr__when num">{{ resvWhen(resv) }}</b>
    <span class="nr__where num">{{ resv.building }} {{ resv.room }}호 · {{ resv.subject }}</span>
    <span v-if="hint" class="nr__hint num">{{ hint }} ›</span>
  </RouterLink>
</template>

<style scoped>
.nr {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-4);
  border-radius: var(--radius-lg);
  background: var(--brand);
  color: var(--on-brand);
  text-decoration: none;
  transition: transform var(--dur-fast) var(--ease-soft);
}
.nr:active {
  transform: scale(0.98);
}
/* 대기중은 확정이 아니다 — 채움 대신 연한 바탕 */
.nr--wait {
  background: var(--brand-tint);
  color: var(--text-1);
}
.nr__label,
.nr__hint {
  font-size: var(--font-size-xs);
  opacity: 0.85;
}
.nr__when {
  font-size: var(--font-size-lg);
}
.nr__where {
  font-size: var(--font-size-sm);
}
.nr__hint {
  margin-top: var(--space-1);
}
</style>
