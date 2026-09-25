<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Legend from '@/components/ui/Legend.vue'
import Select from '@/components/ui/Select.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import StatTile from '@/components/ui/StatTile.vue'
import Table from '@/components/ui/Table.vue'
import { showToast } from '@/components/ui/toast'
import Histogram, { SERIES_COLORS, type HistogramSeries } from '@/components/chart/Histogram.vue'
import OutboxDot from '@/components/domain/OutboxDot.vue'
import { adminApi } from '@/api/admin'
import { loraApi } from '@/api/lora'
import { useResource } from '@/lib/useResource'
import { usePolling } from '@/lib/usePolling'
import { kstDateStr } from '@/lib/time'
import LastRefreshed from '../LastRefreshed.vue'
import {
  PERIODS,
  RECENT_LIMIT,
  histogram,
  kpis,
  recentRows,
  type RecentRow,
} from '../dashboardView'

const SERIES: HistogramSeries = [{ label: 'SLOT_SET' }, { label: 'RESV_SET' }]
const LEGEND = [
  { label: 'SLOT_SET', color: SERIES_COLORS[0] },
  { label: 'RESV_SET', color: SERIES_COLORS[1] },
]

const days = ref(7)
// 한 번에 읽어 한 시각으로 — KPI(all)·분포(계열별 2)·실패·최근 전송
const { data, error, loading, refreshedAt, reload } = useResource(
  async () => {
    const d = days.value
    const now = new Date()
    const range = { from: kstDateStr(now, -(d - 1)), to: kstDateStr(now) }
    const [all, slot, resv, failed, recent] = await Promise.all([
      adminApi.latency({ ...range, type: 'all' }),
      adminApi.latency({ ...range, type: 'SLOT_SET' }),
      adminApi.latency({ ...range, type: 'RESV_SET' }),
      adminApi.failed(d),
      loraApi.recentOutbox(RECENT_LIMIT),
    ])
    return { days: d, all, slot, resv, failed: failed.length, recent }
  },
  { deps: days },
)
// 전시 중 켜 두는 화면 — 60초 (숨김이면 정지, 떠나면 해제)
usePolling(reload, 60_000)

watch(error, (e, prev) => {
  if (e && !prev && e.status !== 401 && e.status !== 403)
    showToast({
      tone: 'danger',
      message: e.message,
      action: { label: '재시도', onClick: () => void reload() },
    })
})

const tiles = computed(() =>
  data.value ? kpis(data.value.all, data.value.failed, data.value.days) : [],
)
const hist = computed(() => (data.value ? histogram(data.value.slot, data.value.resv) : null))
const recent = computed(() => (data.value ? recentRows(data.value.recent) : []))
const r = (row: Record<string, unknown>) => row as unknown as RecentRow
const COLUMNS = [
  { key: 'time', label: '시각', width: '88px' },
  { key: 'room', label: '강의실' },
  { key: 'delay', label: '지연', width: '72px', align: 'right' as const },
  { key: 'state', label: '상태', width: '48px', align: 'center' as const },
]
</script>

<template>
  <main class="dash">
    <header class="dash__head">
      <h1 class="dash__title">반영 지연</h1>
      <LastRefreshed :at="refreshedAt" />
      <label class="dash__filter">
        <span>기간</span>
        <Select v-model="days" :options="PERIODS" size="sm" />
      </label>
    </header>

    <div class="dash__kpis">
      <template v-if="data">
        <StatTile v-for="k in tiles" :key="k.label" v-bind="k" />
      </template>
      <template v-else>
        <Skeleton v-for="i in 4" :key="i" variant="block" />
      </template>
    </div>

    <div class="dash__body">
      <section class="card" aria-labelledby="dash-hist">
        <div class="card__head">
          <h2 id="dash-hist" class="card__title">반영 지연 분포</h2>
          <Legend :series="LEGEND" />
        </div>
        <Skeleton v-if="!hist" variant="block" />
        <EmptyState v-else-if="data?.all.n === 0" message="아직 전송된 작업이 없습니다" />
        <div v-else class="dash__chart">
          <Histogram
            :buckets="hist.buckets"
            :series="SERIES"
            :marker="hist.marker"
            role="img"
            aria-label="반영 지연 분포 — 구간(초)별 건수"
          />
        </div>
      </section>

      <section class="card" aria-labelledby="dash-recent">
        <div class="card__head">
          <h2 id="dash-recent" class="card__title">최근 전송</h2>
        </div>
        <Table
          :columns="COLUMNS"
          :rows="recent as unknown as Record<string, unknown>[]"
          :loading="!data && loading"
          empty="아직 전송된 작업이 없습니다"
        >
          <template #cell-time="{ row }"
            ><span class="num" :title="r(row).when">{{ r(row).time }}</span></template
          >
          <template #cell-room="{ row }">{{ r(row).room }} · {{ r(row).kind }}</template>
          <template #cell-delay="{ row }">
            <span :class="{ dash__slow: r(row).slow, dash__failed: r(row).failed }">{{
              r(row).delay
            }}</span>
          </template>
          <template #cell-state="{ row }"><OutboxDot :state="r(row).state" /></template>
        </Table>
      </section>
    </div>
  </main>
</template>

<style scoped>
.dash {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  padding: var(--space-5);
}
.dash__head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.dash__title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
}
.dash__filter {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  margin-left: auto;
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.dash__kpis {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
}
/* 차트가 주인공, 목록은 곁 — 1.7 : 1 */
.dash__body {
  display: grid;
  grid-template-columns: 1.7fr 1fr;
  gap: var(--space-5);
  align-items: start;
}
.card {
  min-width: 0;
  padding: var(--space-4);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-md);
}
.card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}
.card__title {
  margin: 0;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-bold);
}
/* 1024px 폭에서는 차트(616px)가 칸보다 넓다 — 가로 스크롤 */
.dash__chart {
  overflow-x: auto;
}
.dash__slow {
  font-weight: var(--font-weight-bold);
}
.dash__failed {
  color: var(--danger);
}
</style>
