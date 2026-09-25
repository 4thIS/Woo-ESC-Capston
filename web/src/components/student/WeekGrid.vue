<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { BUSY_TYPES, DAYS, TYPE_LABEL } from '@/components/domain/rules'
import { ROW_MIN, gridRows, type GridBlock, type GridRange } from './grid'
import { minToHm } from './rules'

// 관리자 페이지2와 형태가 같고 규칙이 하나 다르다 — 겹친 블록을 서버가 합쳐 준다 (student-room.md 화면 3)
const props = withDefaults(
  defineProps<{
    days: number[]
    blocks: GridBlock[]
    rowHeight: 24 | 32
    range: GridRange
    todayIndex?: number
    nowTop?: number | null
  }>(),
  { todayIndex: -1, nowTop: null },
)

const root = ref<HTMLElement | null>(null)
// 좁은 폭에서 주말 열(토·일)이 오늘이면 주중 5열 뒤에 숨는다 — 올릴 때 한 번 끝까지 민다
onMounted(() => {
  if (props.todayIndex >= 5 && root.value) root.value.scrollLeft = root.value.scrollWidth
})
const wide = computed(() => props.rowHeight === 32)
const height = computed(() => `${gridRows(props.range) * props.rowHeight}px`)
/** 정시마다 시각 라벨 — 30분 행 두 개에 하나 */
const hours = computed(() => {
  const out: { label: string; top: number }[] = []
  for (let m = Math.ceil(props.range.start / 60) * 60; m < props.range.end; m += 60)
    out.push({ label: minToHm(m), top: ((m - props.range.start) / ROW_MIN) * props.rowHeight })
  return out
})
const byDay = computed(() => props.days.map((d) => props.blocks.filter((b) => b.day === d)))
/** 사용중 넷은 한 색(room.busy), 휴강은 점선 + 취소선, 나머지는 테두리만 */
const kind = (b: GridBlock) =>
  BUSY_TYPES.includes(b.type) ? 'busy' : b.type === 3 ? 'off' : 'plain'
const name = (d: number, b: GridBlock) =>
  `${DAYS[d - 1]} ${b.extra} ${b.label}${b.requested ? ' 대기중' : ''}`
</script>

<template>
  <div
    ref="root"
    class="wg"
    :class="{ 'wg--wide': wide }"
    :style="{ '--wg-row': `${rowHeight}px` }"
  >
    <div
      class="wg__grid"
      :style="{
        gridTemplateColumns: `var(--wg-time) repeat(${days.length}, minmax(var(--wg-col), 1fr))`,
      }"
    >
      <span class="wg__corner" aria-hidden="true" />
      <span
        v-for="(d, i) in days"
        :key="`h${d}`"
        class="wg__day"
        :class="{ 'wg__day--today': i === todayIndex }"
        >{{ DAYS[d - 1] }}</span
      >
      <div class="wg__times" :style="{ height }" aria-hidden="true">
        <span
          v-for="h in hours"
          :key="h.label"
          class="wg__time num"
          :style="{ top: `${h.top}px` }"
          >{{ h.label }}</span
        >
      </div>
      <div
        v-for="(d, i) in days"
        :key="`c${d}`"
        class="wg__col"
        :class="{ 'wg__col--today': i === todayIndex }"
        :style="{ height }"
        role="list"
        :aria-label="`${DAYS[d - 1]}요일`"
      >
        <div
          v-for="b in byDay[i]"
          :key="`${b.day}-${b.top}`"
          role="listitem"
          class="wg__blk"
          :class="[
            `wg__blk--${kind(b)}`,
            { 'wg__blk--mine': b.mine, 'wg__blk--requested': b.requested },
          ]"
          :style="{ top: `${b.top}px`, height: `${b.height}px` }"
          :aria-label="name(d, b)"
        >
          <span v-if="wide" class="wg__type">{{ TYPE_LABEL[b.type] }}</span>
          <span class="wg__label" :class="{ 'wg__label--off': kind(b) === 'off' }"
            ><span class="wg__text">{{ b.label }}</span></span
          >
          <span v-if="wide" class="wg__extra num">{{ b.extra }}</span>
        </div>
        <div
          v-if="i === todayIndex && nowTop !== null"
          class="wg__now"
          :style="{ top: `${nowTop}px` }"
          aria-hidden="true"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 눈금만 폭에 따라 줄인다 — 390: 30분 24px · 시각 34px · 하루 64px / 넓은 폭: 32 · 40 · 120 이상 */
.wg {
  --wg-time: 34px;
  --wg-col: 64px;
  overflow-x: auto;
}
.wg--wide {
  --wg-time: 40px;
  /* 1280 에서 목록 340 을 빼고 주말까지 7열: 40 + 7 × 116 = 852 ≤ 874 (spec 200px 이상은 mh 판정 대기) */
  --wg-col: 116px;
}
.wg__grid {
  display: grid;
}
.wg__corner {
  position: sticky;
  left: 0;
  z-index: 1;
  background: var(--surface);
  border-bottom: var(--border-thin) solid var(--line-2);
}
.wg__day {
  padding: var(--space-1) 0;
  border-bottom: var(--border-thin) solid var(--line-2);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
  text-align: center;
  color: var(--text-2);
}
/* 오늘 — brand 머리 + brand.tint 바탕. 적색은 쓰지 않는다('사용중' 전용) */
.wg__day--today {
  color: var(--brand);
  background: var(--brand-tint);
}
/* 가로로 밀려도(390 주말) 시각 열은 남는다 — 블록(z-index 없음) 위에 */
.wg__times {
  position: sticky;
  left: 0;
  z-index: 1;
  background: var(--surface);
}
.wg__time {
  position: absolute;
  /* 390 의 시각 열 34px 에 'HH:MM'(12px ≈ 33px)이 잘리지 않게 — 오른쪽에 붙이고 자간을 조금 좁힌다 */
  right: 0;
  letter-spacing: -0.02em;
  font-size: var(--font-size-xs);
  line-height: 1;
  color: var(--text-3);
}
.wg__col {
  position: relative;
  border-left: var(--border-thin) solid var(--line-1);
  background-image: repeating-linear-gradient(
    to bottom,
    transparent 0,
    transparent calc(var(--wg-row) - 1px),
    var(--line-1) calc(var(--wg-row) - 1px),
    var(--line-1) var(--wg-row)
  );
}
.wg__col--today {
  background-color: var(--brand-tint);
}
.wg__blk {
  position: absolute;
  left: 2px;
  right: 2px;
  display: flex;
  flex-direction: column;
  padding: 2px var(--space-1);
  overflow: hidden;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-sm);
  background: var(--surface);
  font-size: var(--font-size-xs);
  line-height: var(--leading-tight);
}
.wg__blk--busy {
  background: var(--room-busy-fill);
  border-color: var(--room-busy-line);
  color: var(--room-busy-label);
}
.wg__blk--off {
  border-style: dashed;
  border-color: var(--room-free-line);
  color: var(--room-free-text);
}
/* 취소선은 글자 장식이 아니라 선으로 그린다 — line-clamp 상자 안 굵은 글자에서 text-decoration 이
   그려지지 않는 브라우저가 있다. 인라인 배경이라 줄마다(clone) 55% 높이에 1px */
.wg__label--off .wg__text {
  background: linear-gradient(currentColor, currentColor) 0 55% / 100% 1px no-repeat;
  -webkit-box-decoration-break: clone;
  box-decoration-break: clone;
}
/* 내가 잡은 것 — brand 1px, 신청(대기)은 점선 */
.wg__blk--mine {
  outline: var(--border-thin) solid var(--brand);
  outline-offset: -1px;
}
.wg__blk--requested {
  outline-style: dashed;
}
.wg__label {
  font-weight: var(--font-weight-bold);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}
.wg__type,
.wg__extra {
  font-size: var(--font-size-xs);
}
.wg__now {
  position: absolute;
  left: 0;
  right: 0;
  height: var(--border-thick);
  background: var(--brand);
}
</style>
