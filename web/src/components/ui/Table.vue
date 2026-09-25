<script setup lang="ts">
import { reactive } from 'vue'
import Skeleton from './Skeleton.vue'
import EmptyState from './EmptyState.vue'

type Col = {
  key: string
  label: string
  align?: 'left' | 'right' | 'center'
  width?: string
  sticky?: boolean
}
const props = withDefaults(
  defineProps<{
    columns: Col[]
    rows: Record<string, unknown>[]
    rowKey?: string
    selected?: string[]
    loading?: boolean
    empty?: string
    expandable?: boolean
  }>(),
  { rowKey: 'id', selected: () => [], loading: false, empty: '항목이 없습니다', expandable: false },
)
const open = reactive(new Set<string>())
const keyOf = (row: Record<string, unknown>) => String(row[props.rowKey])
const toggle = (k: string) => (open.has(k) ? open.delete(k) : open.add(k))
const cellClass = (c: Col) => [
  `tbl__cell--${c.align ?? 'left'}`,
  { num: c.align === 'right', 'tbl__cell--sticky': c.sticky },
]
const span = () => props.columns.length + (props.expandable ? 1 : 0)
</script>

<template>
  <div class="tbl-wrap">
    <table class="tbl">
      <thead>
        <tr>
          <th v-if="expandable" class="tbl__toggle-col" aria-label="펼치기" />
          <th
            v-for="c in columns"
            :key="c.key"
            scope="col"
            :class="cellClass(c)"
            :style="c.width ? { width: c.width } : undefined"
          >
            {{ c.label }}
          </th>
        </tr>
      </thead>
      <tbody>
        <template v-if="loading">
          <tr v-for="i in 5" :key="`sk${i}`" class="tbl__row">
            <td :colspan="span()"><Skeleton /></td>
          </tr>
        </template>
        <tr v-else-if="rows.length === 0">
          <td :colspan="span()" class="tbl__empty">
            <slot name="empty"><EmptyState :message="empty" /></slot>
          </td>
        </tr>
        <template v-else>
          <template v-for="row in rows" :key="keyOf(row)">
            <tr class="tbl__row" :class="{ 'tbl__row--selected': selected.includes(keyOf(row)) }">
              <td v-if="expandable" class="tbl__toggle-col">
                <button
                  type="button"
                  class="tbl__toggle"
                  :aria-expanded="open.has(keyOf(row)) ? 'true' : 'false'"
                  aria-label="펼치기"
                  @click="toggle(keyOf(row))"
                >
                  {{ open.has(keyOf(row)) ? '▾' : '▸' }}
                </button>
              </td>
              <td v-for="c in columns" :key="c.key" :class="cellClass(c)">
                <slot :name="`cell-${c.key}`" :row="row">{{ row[c.key] ?? '—' }}</slot>
              </td>
            </tr>
            <tr v-if="expandable && open.has(keyOf(row))" class="tbl__expanded">
              <td :colspan="span()"><slot name="expanded" :row="row" /></td>
            </tr>
          </template>
        </template>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.tbl-wrap {
  overflow-x: auto;
}
.tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
  color: var(--text-1);
}
/* 선을 덜 긋는다 — 헤더 아래 line.2 2px, 행 사이 line.1 1px, 세로선 없음 */
th {
  height: 32px;
  padding: 0 var(--space-3);
  background: var(--sunken);
  border-bottom: var(--border-thick) solid var(--line-2);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  letter-spacing: 0.06em;
  color: var(--text-2);
  white-space: nowrap;
}
td {
  height: 32px;
  padding: 0 var(--space-3);
  border-bottom: var(--border-thin) solid var(--line-1);
}
.tbl__cell--left {
  text-align: left;
}
.tbl__cell--right {
  text-align: right;
}
.tbl__cell--center {
  text-align: center;
}
.tbl__cell--sticky {
  position: sticky;
  left: 0;
  background: inherit;
}
.tbl__row {
  background: var(--surface);
}
.tbl__row:hover {
  background: var(--sunken);
}
.tbl__row--selected,
.tbl__row--selected:hover {
  background: var(--brand-tint);
}
.tbl__expanded > td {
  padding: var(--space-2) var(--space-3) var(--space-2) var(--space-6);
  background: var(--sunken);
}
.tbl__toggle-col {
  width: 32px;
  padding: 0;
  text-align: center;
}
.tbl__toggle {
  border: 0;
  background: none;
  color: var(--text-2);
  font: inherit;
  cursor: pointer;
}
.tbl__empty {
  height: auto;
}
</style>
