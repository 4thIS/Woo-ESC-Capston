<script setup lang="ts">
import { computed } from 'vue'
import type { ResvMineOut } from '@/api/types'
import Button from '@/components/ui/Button.vue'
import ResvStatusBadge from './ResvStatusBadge.vue'
import { cancelKind, checkinState, resvWhen } from './rules'

// 체크인 창(시작 −10 ~ +15분)과 취소/철회 구분을 이 카드가 진다 (student-room.md §내 예약)
const props = withDefaults(
  defineProps<{ resv: ResvMineOut; now: Date; busy?: 'checkin' | 'cancel' | null }>(),
  { busy: null },
)
const emit = defineEmits<{ checkin: []; cancel: [] }>()
const ci = computed(() => checkinState(props.resv, props.now))
const cancel = computed(() => cancelKind(props.resv, props.now))
</script>

<template>
  <article class="mc" :aria-label="`${resv.building} ${resv.room}호 ${resvWhen(resv)}`">
    <p class="mc__head">
      <ResvStatusBadge :status="resv.status" />
      <span class="mc__room num">{{ resv.building }} {{ resv.room }}호</span>
    </p>
    <p class="mc__when num">{{ resvWhen(resv) }}</p>
    <p class="mc__subject">{{ resv.subject }}</p>
    <p v-if="resv.status === 'rejected' && resv.reject_reason" class="mc__note">
      사유: {{ resv.reject_reason }}
    </p>
    <p v-if="resv.status === 'expired'" class="mc__note">승인 전에 시간이 지났어요</p>
    <div v-if="ci || cancel" class="mc__actions">
      <p v-if="ci?.kind === 'done'" class="mc__done num">✓ {{ ci.at }} 체크인</p>
      <Button
        v-else-if="ci"
        :variant="ci.kind === 'open' ? 'primary' : 'secondary'"
        :disabled="ci.kind !== 'open' || busy !== null"
        :loading="busy === 'checkin'"
        @click="emit('checkin')"
        >체크인</Button
      >
      <Button
        v-if="cancel"
        variant="secondary"
        :disabled="busy !== null"
        :loading="busy === 'cancel'"
        @click="emit('cancel')"
        >{{ cancel === 'withdraw' ? '신청 취소' : '취소' }}</Button
      >
    </div>
    <!-- 창 밖이면 숨기지 않고 언제부터인지 — 버튼이 사라지면 기능이 있는지 모른다 -->
    <p v-if="ci?.kind === 'before'" class="mc__hint num">{{ ci.from }}부터 체크인할 수 있어요</p>
    <p v-else-if="ci?.kind === 'after'" class="mc__hint">체크인 시간이 지났어요</p>
  </article>
</template>

<style scoped>
.mc {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-4);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.mc p {
  margin: 0;
}
.mc__head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.mc__room {
  font-weight: var(--font-weight-bold);
}
.mc__subject,
.mc__note {
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.mc__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-2);
}
.mc__done {
  display: inline-flex;
  align-items: center;
  min-height: var(--control-height-md);
  font-weight: var(--font-weight-bold);
}
.mc__hint {
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
</style>
