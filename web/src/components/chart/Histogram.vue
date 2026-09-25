<script lang="ts">
/** 계열색은 고정 순서 (tokens.md §chart 규칙 1). 범례(Legend)도 이 값을 쓴다 */
export const SERIES_COLORS = [
  'var(--chart-series-1)',
  'var(--chart-series-2)',
  'var(--chart-series-3)',
] as const
type S = { label: string }
/** 4계열 이상은 타입에서 막는다 (tokens.md §chart 규칙 2).
 * 슬롯 순서는 고정 — 색(hist__bar--N)은 배열 인덱스로 정해진다. 계열을 건너뛰거나 필터링해서
 * 빼지 말 것: 값이 없는 계열도 0 을 채워 자리를 지켜야 다른 계열이 색을 이어받지 않는다. */
export type HistogramSeries = [S] | [S, S] | [S, S, S]
export interface HistogramBucket {
  label: string
  values: number[]
}

/** 눈금 간격 — 최댓값을 세 칸에 담는 1·2·5 계열 수. 건수라 1 보다 작지 않다 */
export function niceStep(max: number): number {
  if (max <= 0) return 1
  const raw = max / 3
  const pow = 10 ** Math.floor(Math.log10(raw))
  const step = ([1, 2, 5, 10].find((m) => m * pow >= raw) ?? 10) * pow
  return Math.max(1, step)
}
</script>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  buckets: HistogramBucket[]
  series: HistogramSeries
  marker?: { at: number; label: string }
}>()

// px 고정 — 막대 폭 15px 를 지키려고 확대·축소하지 않는다 (components.md)
const BAR = 15
const GAP = 2
const SLOT = 72
const L = 32
const T = 24
const PLOT = 160
const B = 24
const R = 8
const BASE = T + PLOT

const width = computed(() => L + props.buckets.length * SLOT + R)
const height = T + PLOT + B
const peak = computed(() => Math.max(0, ...props.buckets.flatMap((b) => b.values)))
const step = computed(() => niceStep(peak.value))
const top = computed(() => step.value * 3)
const y = (v: number) => BASE - (Math.min(v, top.value) / top.value) * PLOT
const n = computed(() => props.series.length)
const barX = (i: number, j: number) =>
  L + i * SLOT + (SLOT - (n.value * BAR + (n.value - 1) * GAP)) / 2 + j * (BAR + GAP)
const val = (b: HistogramBucket, j: number) => b.values[j] ?? 0

/** 계열마다 가장 큰 막대(같으면 첫 것)의 bucket 번호 — 값 라벨은 거기에만. 전부 0 이면 -1 */
const peakIdx = computed(() =>
  Array.from({ length: n.value }, (_, j) => {
    let best = -1
    let bv = 0
    props.buckets.forEach((b, i) => {
      if (val(b, j) > bv) {
        bv = val(b, j)
        best = i
      }
    })
    return best
  }),
)

/** 위 두 모서리만 radius.sm(4px), 바닥은 축에 붙는다 */
function barPath(x: number, v: number): string {
  const yt = y(v)
  const r = Math.min(4, BASE - yt, BAR / 2)
  return (
    `M${x},${BASE}V${yt + r}Q${x},${yt} ${x + r},${yt}` +
    `H${x + BAR - r}Q${x + BAR},${yt} ${x + BAR},${yt + r}V${BASE}Z`
  )
}
const tick = (v: number) => String(Math.round(v * 10) / 10)
</script>

<template>
  <svg class="hist" :width="width" :height="height" :viewBox="`0 0 ${width} ${height}`">
    <!-- 격자선은 두 줄만 (admin-dashboard.md) -->
    <g class="hist__grid">
      <line
        v-for="k in [1, 2]"
        :key="k"
        :x1="L"
        :x2="width - R"
        :y1="y(step * k)"
        :y2="y(step * k)"
      />
    </g>
    <g class="hist__ticks">
      <text v-for="k in [1, 2]" :key="k" :x="L - 6" :y="y(step * k) + 4" text-anchor="end">
        {{ tick(step * k) }}
      </text>
    </g>
    <g v-for="(b, i) in buckets" :key="b.label">
      <template v-for="(s, j) in series" :key="s.label">
        <path
          v-if="val(b, j) > 0"
          :class="['hist__bar', `hist__bar--${j + 1}`]"
          :d="barPath(barX(i, j), val(b, j))"
        />
        <text
          v-if="peakIdx[j] === i"
          class="hist__value"
          :x="barX(i, j) + BAR / 2"
          :y="y(val(b, j)) - 4"
          text-anchor="middle"
        >
          {{ val(b, j) }}
        </text>
      </template>
      <text class="hist__label" :x="L + i * SLOT + SLOT / 2" :y="BASE + 16" text-anchor="middle">
        {{ b.label }}
      </text>
    </g>
    <line class="hist__axis" :x1="L" :x2="width - R" :y1="BASE" :y2="BASE" />
    <g v-if="marker" class="hist__marker">
      <line :x1="L + marker.at * SLOT" :x2="L + marker.at * SLOT" :y1="T - 8" :y2="BASE" />
      <text :x="L + marker.at * SLOT + 4" :y="T - 12">{{ marker.label }}</text>
    </g>
  </svg>
</template>

<style scoped>
.hist {
  display: block;
  font-size: var(--font-size-xs);
  font-variant-numeric: tabular-nums;
}
.hist__grid line {
  stroke: var(--chart-grid);
}
.hist__axis {
  stroke: var(--chart-axis);
}
.hist__ticks text,
.hist__label {
  fill: var(--chart-text);
}
.hist__bar--1 {
  fill: var(--chart-series-1);
}
.hist__bar--2 {
  fill: var(--chart-series-2);
}
.hist__bar--3 {
  fill: var(--chart-series-3);
}
/* 글자는 계열색을 입지 않는다 (규칙 5) */
.hist__value {
  fill: var(--text-2);
  font-weight: var(--font-weight-bold);
}
.hist__marker line {
  stroke: var(--line-3);
  stroke-dasharray: 3 3;
}
.hist__marker text {
  fill: var(--text-3);
}
</style>
