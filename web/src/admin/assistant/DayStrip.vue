<script setup lang="ts">
import { computed } from 'vue'
import { DAY_END, DAY_START, layoutDay, type Block } from '../weekView'
import type { BlockMark } from './diffMarks'

// 하루 막대 — 바뀌는 날 하나의 기존 · 수정 두 줄 (admin-assistant.md 「왼쪽 열」)
const props = defineProps<{
  title: string
  before: Block[]
  after: Block[]
  marks: (b: Block) => BlockMark | undefined
}>()

const range = computed(() => {
  const all = [...props.before, ...props.after]
  const from = Math.min(DAY_START, ...all.map((b) => Math.floor(b.s / 60) * 60))
  const to = Math.max(DAY_END, ...all.map((b) => Math.ceil(b.e / 60) * 60))
  return { from, to }
})
const pct = (t: number) => ((t - range.value.from) / (range.value.to - range.value.from)) * 100
const LANE = 18
function row(blocks: Block[], side: 'before' | 'after') {
  const { placed, overlaps } = layoutDay(blocks)
  const lanes = Math.max(1, ...placed.map((p) => p.lanes))
  return {
    height: lanes * LANE + 6,
    blocks: placed.map((p) => {
      const m = props.marks(p)
      const shown = m && (m.op === 'change' || (m.op === 'add') === (side === 'after'))
      return {
        key: p.key,
        busy: p.busy,
        op: shown ? m.op : undefined,
        style: {
          left: `${pct(p.s)}%`,
          width: `${pct(p.e) - pct(p.s)}%`,
          top: `${3 + (p.lane * (lanes * LANE)) / p.lanes}px`,
          height: `${(lanes * LANE) / p.lanes - 2}px`,
        },
      }
    }),
    bars: overlaps.map((o) => ({ left: `calc(${pct(o.s)}% - 1.5px)` })),
  }
}
const rows = computed(() => [
  { label: '기존', ...row(props.before, 'before') },
  { label: '수정', ...row(props.after, 'after') },
])
const ticks = computed(() => {
  const out: { t: number; left: string }[] = []
  for (let t = range.value.from; t <= range.value.to; t += 180) out.push({ t, left: `${pct(t)}%` })
  return out
})
</script>

<template>
  <div class="strip">
    <b class="strip__title">{{ title }}</b>
    <div v-for="r in rows" :key="r.label" class="strip__row">
      <span class="strip__label">{{ r.label }}</span>
      <div class="strip__track" :style="{ height: `${r.height}px` }">
        <span
          v-for="b in r.blocks"
          :key="b.key"
          class="strip__block"
          :class="[
            b.busy ? 'strip__block--busy' : 'strip__block--free',
            b.op && `strip__block--${b.op}`,
          ]"
          :style="b.style"
        />
        <span v-for="(x, i) in r.bars" :key="i" class="strip__overlap" :style="x" />
      </div>
    </div>
    <div class="strip__row" aria-hidden="true">
      <span class="strip__label" />
      <div class="strip__ticks num">
        <span v-for="k in ticks" :key="k.t" :style="{ left: k.left }">{{
          String(k.t / 60).padStart(2, '0')
        }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.strip {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3);
  border-radius: var(--radius-lg);
  background: var(--sunken);
}
.strip__title {
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.strip__row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.strip__label {
  flex: none;
  width: 32px;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  color: var(--text-2);
}
.strip__track {
  position: relative;
  flex: 1;
  border: var(--border-thin) solid var(--line-1);
  border-radius: var(--radius-sm);
  background: var(--surface);
}
.strip__block {
  position: absolute;
  box-sizing: border-box;
  border-radius: var(--radius-sm);
}
.strip__block--busy {
  border: var(--border-thin) solid var(--room-busy-line);
  background: var(--room-busy-fill);
}
.strip__block--free {
  border: var(--border-thin) dashed var(--room-free-line);
  background: var(--surface);
}
.strip__block--add {
  border: var(--border-thick) solid var(--diff-add-line);
}
.strip__block--remove {
  border: var(--border-thick) dashed var(--diff-remove-line);
}
.strip__block--change {
  border: var(--border-thick) solid var(--diff-change-line);
}
.strip__overlap {
  position: absolute;
  top: 3px;
  bottom: 3px;
  width: 3px;
  background: var(--danger);
}
.strip__ticks {
  position: relative;
  flex: 1;
  height: 12px;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.strip__ticks span {
  position: absolute;
  transform: translateX(-50%);
}
.strip__ticks span:first-child {
  transform: none;
}
</style>
