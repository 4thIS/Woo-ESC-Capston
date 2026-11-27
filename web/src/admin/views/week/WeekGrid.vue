<script setup lang="ts">
import { computed } from 'vue'
import { DAYS, TYPE_LABEL } from '@/components/domain/rules'
import type { DiffOp, ExamOut } from '@/api/types'
import { fieldsText, type BlockMark } from '../../assistant/diffMarks'
import { addDays, hm, md } from '@/lib/time'
import {
  ROW_PX,
  blockBox,
  examDates,
  gridRange,
  layoutDay,
  timeRows,
  type Block,
  type Placed,
} from '../../weekView'

// 주간 격자 하나 — 주간 시간표(편집)와 AI 비서 확인 화면(기존│수정, 읽기 전용)이 같이 쓴다 (admin-schedule.md)
const props = withDefaults(
  defineProps<{
    blocks: Block[]
    exams: ExamOut[]
    monday: string
    night: boolean
    weekend: boolean
    /** 세로 범위를 잡을 블록 — 기존│수정 두 격자를 같은 행에 맞출 때 둘을 합쳐 넘긴다 */
    rangeBlocks?: Block[]
    editable?: boolean
    clickable?: (p: Placed) => boolean
    blockTitle?: (p: Placed) => string | undefined
    failed?: (p: Placed) => boolean
    /** AI 비서 확인 화면의 변경 표시 — 테두리 2px + 머리 태그 (admin-assistant.md 「변경 표시」) */
    marks?: (p: Placed) => BlockMark | undefined
    /** 요일만 — 정규 시간표(특정 주가 아님) 확인 화면에서 날짜를 숨긴다 */
    weekly?: boolean
  }>(),
  {
    rangeBlocks: undefined,
    editable: false,
    clickable: () => false,
    blockTitle: () => undefined,
    failed: () => false,
    marks: () => undefined,
  },
)
const TAG: Record<DiffOp, string> = { add: '+ 추가', remove: '− 삭제', change: '~ 수정' }
/** 변경 블록은 바뀐 칸을 title 로 — 그 밖은 화면이 준 title */
function titleOf(p: Placed) {
  const m = props.marks(p)
  return m?.op === 'change' && m.fields.length
    ? `바뀐 칸: ${fieldsText(m.fields)}`
    : props.blockTitle(p)
}
const emit = defineEmits<{ cell: [at: { day: number; t: number }]; block: [p: Placed] }>()
defineSlots<{ dot?(props: { p: Placed }): unknown; overlay?(): unknown }>()

const clock = (t: number) => hm(Math.floor(t / 60), t % 60)
const range = computed(() => gridRange(props.rangeBlocks ?? props.blocks, props.night))
const rows = computed(() => timeRows(range.value))
const examOn = computed(() => examDates(props.exams, props.monday))
const days = computed(() =>
  Array.from({ length: props.weekend ? 7 : 5 }, (_, i) => {
    const date = addDays(props.monday, i)
    const { placed, overlaps } = layoutDay(props.blocks.filter((b) => b.day === i + 1))
    return {
      day: i + 1,
      date,
      exam: examOn.value.has(date),
      blocks: placed.flatMap((p) => {
        const box = blockBox(p, range.value)
        return box ? [{ p, box }] : []
      }),
      marks: overlaps.flatMap((o) => {
        const box = blockBox(o, range.value)
        return box ? [{ o, box }] : []
      }),
    }
  }),
)
function blockClass(p: Placed) {
  const requested = p.resv?.status === 'requested'
  const cancelled = p.slot?.type === 3
  return {
    'wk__block--busy': !requested && !cancelled,
    'wk__block--cancelled': cancelled,
    'wk__block--requested': requested,
    'wk__block--failed': props.failed(p),
    'wk__block--static': !props.clickable(p),
    [`wk__block--diff-${props.marks(p)?.op}`]: !!props.marks(p),
  }
}
// 라벨이 상태를 말한다 — 넷(수업·시험·특강·대여)을 색으로 나누지 않는다
// 연속 교시 블록은 '수업중 · 3교시' (admin-schedule.md)
const periodsOf = (p: Placed) => p.group?.slots.length ?? 1
function blockLabel(p: Placed) {
  if (p.slot) return TYPE_LABEL[p.slot.type] + (periodsOf(p) > 1 ? ` · ${periodsOf(p)}교시` : '')
  return `${p.resv!.status === 'requested' ? '신청' : '예약'} · ${TYPE_LABEL[p.resv!.type]}`
}
/** 스크린리더 이름 — '월 10:00–12:00 수업중 캡스톤디자인' */
const blockName = (p: Placed) =>
  `${DAYS[p.day - 1]} ${clock(p.s)}–${clock(p.e)} ${blockLabel(p)} ${p.slot?.subject ?? p.resv?.subject ?? ''}`.trim()
const who = (p: Placed) =>
  p.slot ? p.slot.professor : (p.resv!.requester?.name ?? p.resv!.professor)
</script>

<template>
  <div class="wk__scroll">
    <div class="wk__grid" :style="{ '--cols': days.length }">
      <div class="wk__corner" />
      <div v-for="d in days" :key="d.date" class="wk__head">
        <span
          >{{ DAYS[d.day - 1] }} <span v-if="!weekly" class="num">{{ md(d.date) }}</span></span
        >
        <!-- 시험기간은 요일 헤더 아래 얇은 띠 — 셀은 건드리지 않는다 -->
        <span v-if="d.exam" class="wk__exam">시험기간</span>
      </div>
      <div class="wk__times">
        <div v-for="t in rows" :key="t" class="wk__time num">{{ clock(t) }}</div>
      </div>
      <div
        v-for="d in days"
        :key="`c${d.date}`"
        class="wk__col"
        :style="{ height: `${rows.length * ROW_PX}px` }"
      >
        <button
          v-for="t in rows"
          :key="t"
          type="button"
          class="wk__cell"
          :disabled="!editable"
          :aria-label="`${DAYS[d.day - 1]} ${clock(t)} 시간표 추가`"
          @click="emit('cell', { day: d.day, t })"
        />
        <!-- 자리 하나에 블록과 점이 형제로 선다 — 재전송 버튼을 role=button 블록 안에 넣으면
             스크린리더가 한 덩어리로 읽고, 재전송의 Enter 가 블록까지 올라가 편집을 연다 -->
        <div
          v-for="{ p, box } in d.blocks"
          :key="p.key"
          class="wk__place"
          :style="{
            top: `${box.top}px`,
            height: `${box.height}px`,
            left: `calc(${(p.lane / p.lanes) * 100}% + 4px)`,
            width: `calc(${100 / p.lanes}% - 8px)`,
          }"
        >
          <div
            class="wk__block"
            :class="blockClass(p)"
            :role="clickable(p) ? 'button' : undefined"
            :tabindex="clickable(p) ? 0 : undefined"
            :aria-label="clickable(p) ? blockName(p) : undefined"
            :title="titleOf(p)"
            @click="emit('block', p)"
            @keydown.enter.self.prevent="emit('block', p)"
            @keydown.space.self.prevent="emit('block', p)"
          >
            <!-- 색만으로 읽히지 않게 기호 + 글자 -->
            <span v-if="marks(p)" class="wk__tag" :class="`wk__tag--${marks(p)!.op}`">{{
              TAG[marks(p)!.op]
            }}</span>
            <span class="wk__label">{{ blockLabel(p) }}</span>
            <!-- 높이가 모자라면 교수부터 지운다 -->
            <span v-if="box.height >= 40" class="wk__subject">{{
              p.slot?.subject ?? p.resv?.subject
            }}</span>
            <span v-if="box.height >= 80 && who(p)" class="wk__who">{{ who(p) }}</span>
            <span v-if="box.cutEnd" class="wk__cut num">~{{ clock(p.e) }}</span>
          </div>
          <span class="wk__dot"><slot name="dot" :p="p" /></span>
        </div>
        <div
          v-for="({ o, box }, i) in d.marks"
          :key="`m${i}`"
          class="wk__overlap"
          :style="{
            top: `${box.top}px`,
            height: `${box.height}px`,
            left: `calc(${(o.lane / o.lanes) * 100}% - 1.5px)`,
          }"
        >
          <!-- 막대 아래 바깥, 먼저 끝난 블록 쪽에 두 줄로 — 블록 글자는 위쪽에 있어 덮지 않고, 반 폭(1440·7열 ≈78px)에 들어간다.
               ponytail: 바로 이어지는 다음 블록의 윗줄은 가릴 수 있다 — 겹침 자체가 고쳐야 할 상태라 둔다 -->
          <span class="wk__overlap-label num" :class="`wk__overlap-label--${o.side}`"
            ><span>겹침</span> <span>{{ clock(o.s) }}–{{ clock(o.e) }}</span></span
          >
        </div>
      </div>
      <slot name="overlay" />
    </div>
  </div>
</template>

<style scoped>
/* WeekView.vue 에서 그대로 옮겼다 — .wk__scroll 부터 .wk__overlap-label--right 까지 */
/* 격자 컨테이너 line.2 1px + radius.lg, 세로 스크롤 — 요일 헤더와 시각 열은 붙어 있다 */
.wk__scroll {
  max-height: calc(100vh - 150px);
  overflow: auto;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.wk__grid {
  position: relative;
  display: grid;
  grid-template-columns: 56px repeat(var(--cols), minmax(0, 1fr));
}
.wk__corner,
.wk__head {
  position: sticky;
  top: 0;
  z-index: 3;
  border-bottom: var(--border-thin) solid var(--line-2);
  background: var(--surface);
}
.wk__corner {
  left: 0;
  z-index: 4;
}
.wk__head {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 44px;
  padding: var(--space-1) var(--space-2);
  border-left: var(--border-thin) solid var(--line-1);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
}
.wk__exam {
  align-self: flex-start;
  margin-top: 2px;
  padding: 0 var(--space-1);
  border-radius: var(--radius-sm);
  background: var(--room-busy-fill);
  color: var(--room-busy-label);
  font-size: var(--font-size-xs);
}
.wk__times {
  position: sticky;
  left: 0;
  z-index: 2;
  background: var(--surface);
}
.wk__time {
  height: 44px;
  padding: 2px var(--space-2);
  border-bottom: var(--border-thin) solid var(--line-1);
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
/* 열 구분선은 line.1 (설계 판정 — gray.50 의 2층 토큰이 없다) */
.wk__col {
  position: relative;
  border-left: var(--border-thin) solid var(--line-1);
}
.wk__cell {
  display: block;
  width: 100%;
  height: 44px;
  border: 0;
  border-bottom: var(--border-thin) solid var(--line-1);
  background: transparent;
  cursor: pointer;
}
.wk__cell:hover:enabled {
  background: var(--sunken);
}
.wk__place {
  position: absolute;
}
.wk__block {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow: hidden;
  padding: var(--space-1) var(--space-2);
  border: var(--border-thin) solid transparent;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  cursor: pointer;
}
.wk__block--busy {
  border-color: var(--room-busy-line);
  background: var(--room-busy-fill);
}
.wk__block--busy .wk__label {
  color: var(--room-busy-label);
}
.wk__block--cancelled {
  border: var(--border-thin) dashed var(--room-free-line);
  background: var(--surface);
  color: var(--room-free-text);
}
.wk__block--cancelled .wk__subject {
  text-decoration: line-through;
}
/* 신청(승인 대기) — 아무것도 점유하지 않았다: 바탕 없이 2px 점선 + text.3 */
.wk__block--requested {
  border: var(--border-thick) dashed var(--line-3);
  background: var(--surface);
  color: var(--text-3);
  cursor: default;
}
.wk__block--static {
  cursor: default;
}
.wk__block--failed {
  border: var(--border-thick) solid var(--danger);
}
/* AI 비서 변경 표시 — 바탕은 상태 색 그대로, 테두리 2px + 머리 태그만 (tokens.md diff.*) */
.wk__block--diff-add {
  border: var(--border-thick) solid var(--diff-add-line);
}
.wk__block--diff-remove {
  border: var(--border-thick) dashed var(--diff-remove-line);
}
.wk__block--diff-remove .wk__subject {
  text-decoration: line-through;
}
.wk__block--diff-change {
  border: var(--border-thick) solid var(--diff-change-line);
}
.wk__tag {
  align-self: flex-start;
  padding: 0 var(--space-1);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
}
.wk__tag--add {
  background: var(--diff-add-fill);
  color: var(--diff-add-text);
}
.wk__tag--remove {
  background: var(--diff-remove-fill);
  color: var(--diff-remove-text);
}
.wk__tag--change {
  background: var(--diff-change-fill);
  color: var(--diff-change-text);
}
.wk__label {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
}
.wk__subject {
  overflow: hidden;
  font-weight: var(--font-weight-medium);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wk__who {
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.wk__cut {
  margin-top: auto;
  font-size: var(--font-size-xs);
}
.wk__dot {
  position: absolute;
  top: var(--space-1);
  right: var(--space-1);
}
/* 겹침 — 두 블록 사이 겹친 구간에만 danger 3px 막대 하나 + 라벨 하나 */
.wk__overlap {
  position: absolute;
  z-index: 1;
  width: 3px;
  background: var(--danger);
  pointer-events: none;
}
.wk__overlap-label {
  position: absolute;
  top: 100%;
  display: flex;
  flex-direction: column;
  padding: 0 var(--space-1);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--danger);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  white-space: nowrap;
}
.wk__overlap-label--left {
  right: 0;
  align-items: flex-end;
}
.wk__overlap-label--right {
  left: 0;
  align-items: flex-start;
}
</style>
