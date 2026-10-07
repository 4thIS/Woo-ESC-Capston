<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Table from '@/components/ui/Table.vue'
import TypeBadge from '@/components/domain/TypeBadge.vue'
import { DAYS } from '@/components/domain/rules'
import type { ResvWithRoom } from '@/api/types'
import { useNow } from '@/lib/useNow'
import { dayOfDate, hm } from '@/lib/time'
import { LOG_DAYS, logResult, logType, splitResv } from '../../roomsView'

// 예약 로그 — 끝난 승인(사용 완료·조기 퇴실·미체크인)과 취소·거절·만료. 읽기 전용, 최근 것부터
const props = defineProps<{
  label: (roomId: number) => string
  resv: ResvWithRoom[]
  loading: boolean
}>()

const all = ref(false)
// 지금 시각은 주기적으로 + 다시 불러올 때 새로 — 켜 둔 화면에서도 사용중·체크인 대기가 넘어가고 끝난 예약이 로그로 간다
const now = useNow(30_000)
watch(
  () => props.resv,
  () => (now.value = new Date()),
)
const rows = computed(() =>
  splitResv(props.resv, now.value, all.value).log.map((r) => ({ ...r, key: `log-${r.id}` })),
)
const COLUMNS = [
  { key: 'room', label: '호수', width: '72px' },
  { key: 'date', label: '날짜', width: '104px' },
  { key: 'day', label: '요일', width: '56px' },
  { key: 'start', label: '시작', width: '64px' },
  { key: 'end', label: '종료', width: '64px' },
  { key: 'subject', label: '사용 목적' },
  { key: 'who', label: '신청자', width: '96px' },
  { key: 'no', label: '학번', width: '88px' },
  { key: 'type', label: '유형', width: '80px' },
  { key: 'result', label: '결과', width: '180px' },
]
const asV = (row: Record<string, unknown>) => row as unknown as ResvWithRoom
</script>

<template>
  <section class="blk" aria-labelledby="blk-log">
    <header class="blk__head">
      <h2 id="blk-log" class="blk__title">예약 로그</h2>
      <span class="blk__range">{{ all ? '전체' : `최근 ${LOG_DAYS}일` }}</span>
      <Button class="blk__all" variant="ghost" size="sm" @click="all = !all">{{
        all ? `최근 ${LOG_DAYS}일만` : '전체 보기'
      }}</Button>
    </header>
    <Table
      :columns="COLUMNS"
      :rows="rows as unknown as Record<string, unknown>[]"
      row-key="key"
      :loading="loading"
    >
      <template #empty>
        <EmptyState message="끝난 예약이 없습니다" />
      </template>
      <template #cell-room="{ row }"
        ><span class="num">{{ label(asV(row).room_id) }}</span></template
      >
      <template #cell-date="{ row }"
        ><span class="num">{{ asV(row).date }}</span></template
      >
      <template #cell-day="{ row }">{{ DAYS[dayOfDate(asV(row).date) - 1] }}</template>
      <template #cell-start="{ row }"
        ><span class="num">{{ hm(asV(row).s_h, asV(row).s_m) }}</span></template
      >
      <template #cell-end="{ row }"
        ><span class="num">{{ hm(asV(row).e_h, asV(row).e_m) }}</span></template
      >
      <template #cell-who="{ row }">{{ asV(row).requester?.name ?? '—' }}</template>
      <template #cell-no="{ row }"
        ><span class="num">{{ asV(row).requester?.student_no ?? '—' }}</span></template
      >
      <template #cell-type="{ row }">
        <Badge v-if="logType(asV(row))" variant="outline">{{ logType(asV(row)) }}</Badge>
        <TypeBadge v-else :type="asV(row).type" />
      </template>
      <template #cell-result="{ row }"
        ><span class="blk__result num" :title="logResult(asV(row))">{{
          logResult(asV(row))
        }}</span></template
      >
    </Table>
  </section>
</template>

<style scoped>
.blk {
  overflow: hidden;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.blk__head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
}
.blk__title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.blk__range {
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
.blk__all {
  margin-left: auto;
}
.blk__result {
  /* 거절 사유는 200자까지 — 한 줄로 자르고 전체는 title (admin-rooms.md) */
  display: block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
</style>
