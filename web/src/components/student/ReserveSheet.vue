<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { FreeDay, FreeRange, StudentResvIn } from '@/api/types'
import { SUBJ_MAX } from '@/components/domain/rules'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'
import { kstDateStr, kstMinutes } from '@/lib/time'
import {
  CAP_TEXT,
  DAILY_TEXT,
  DOOR_HINT,
  FULL_TEXT,
  MAX_ACTIVE,
  chipDay,
  dateLabel,
  defaultEnd,
  durationText,
  endOptions,
  hmToMin,
  minToHm,
  spanKey,
  startOptions,
} from './rules'

// 예약 신청 화면 전체 — 제약을 "고를 수 없게" 건다. 빈 구간은 서버 free 만 (student-room.md §예약)
const props = withDefaults(
  defineProps<{
    days: FreeDay[]
    now: Date
    myFutureCount: number
    full?: boolean
    locked?: boolean
    submitting?: boolean
    maxBytes?: number
  }>(),
  { full: false, locked: false, submitting: false, maxBytes: SUBJ_MAX },
)
const emit = defineEmits<{ submit: [body: StudentResvIn] }>()

const date = ref<string | null>(null)
const spanId = ref<string | null>(null)
const start = ref<number | null>(null)
const end = ref<number | null>(null)
const subject = ref('')

// 처음엔 빈 구간이 있는 첫 날. 재조회로 days 가 바뀌어도 고른 날은 그대로 둔다
watch(
  () => props.days,
  (days) => {
    if (!days.some((d) => d.date === date.value))
      date.value = (days.find((d) => d.spans.length) ?? days[0])?.date ?? null
  },
  { immediate: true },
)

const day = computed(() => props.days.find((d) => d.date === date.value) ?? null)
/** 오늘이면 지금 이후만 — 서버가 준 뒤 흐른 시간만큼 지운다. 자정이 지나 어제가 된 날은 전부 지운다 */
const after = computed(() => {
  const today = kstDateStr(props.now)
  if (!day.value || day.value.date > today) return null
  return day.value.date === today ? kstMinutes(props.now) : Infinity
})
/** 고를 수 있는 시작이 하나라도 남은 구간만 (student-room.md: 오늘 칩에서 지난 구간을 지운다) */
const shown = computed(
  () => day.value?.spans.filter((s) => startOptions(s, after.value).length) ?? [],
)
/** 재조회로 사라졌거나 시간이 흘러 지난 구간이면 null — 선택이 풀리고 버튼이 잠긴다 */
const span = computed(() => shown.value.find((s) => spanKey(s) === spanId.value) ?? null)
const starts = computed(() => (span.value ? startOptions(span.value, after.value) : []))
const ends = computed(() =>
  span.value && start.value !== null ? endOptions(start.value, span.value) : [],
)

function pickDay(d: string) {
  date.value = d
  spanId.value = null
  start.value = null
  end.value = null
}
function pickSpan(s: FreeRange) {
  spanId.value = spanKey(s)
  const first = startOptions(s, after.value)[0] ?? null
  start.value = first
  end.value = first === null ? null : defaultEnd(first, s)
}
function pickStart(v: string | number) {
  start.value = Number(v)
  if (span.value && !endOptions(start.value, span.value).includes(end.value ?? -1))
    end.value = defaultEnd(start.value, span.value)
}
function pickEnd(v: string | number) {
  end.value = Number(v)
}
// 시간이 흘러 고른 시작이 지나면 다음 후보로 (없으면 비운다)
watch(starts, (list) => {
  if (start.value === null || list.includes(start.value)) return
  if (list.length) pickStart(list[0])
  else {
    start.value = null
    end.value = null
  }
})

const blocker = computed(() => {
  if (props.full) return FULL_TEXT
  if (props.myFutureCount >= MAX_ACTIVE) return CAP_TEXT
  return props.locked ? DAILY_TEXT : null
})
const valid = computed(
  () =>
    start.value !== null &&
    starts.value.includes(start.value) &&
    end.value !== null &&
    ends.value.includes(end.value) &&
    subject.value.trim() !== '',
)
const summary = computed(() =>
  day.value && valid.value
    ? `${dateLabel(day.value.date)} ${minToHm(start.value!)}–${minToHm(end.value!)}`
    : '시간을 고르세요',
)
const startOpts = computed(() => starts.value.map((m) => ({ value: m, label: minToHm(m) })))
const endOpts = computed(() => ends.value.map((m) => ({ value: m, label: minToHm(m) })))

function submit() {
  if (!valid.value || blocker.value || props.submitting || !day.value) return
  const s = start.value!
  const e = end.value!
  emit('submit', {
    date: day.value.date,
    s_h: Math.floor(s / 60),
    s_m: s % 60,
    e_h: Math.floor(e / 60),
    e_m: e % 60,
    subject: subject.value.trim(),
  })
}
</script>

<template>
  <form class="rs" @submit.prevent="submit">
    <section class="rs__sec">
      <h2 class="rs__h">날짜 <span class="rs__sub">· 오늘부터 7일까지</span></h2>
      <div class="rs__chips" role="radiogroup" aria-label="날짜">
        <!-- 네이티브 라디오(구간과 같은 모양) — 한 탭 멈춤, 화살표로 옮긴다. 입력은 칩 전체를 덮어 48px 을 그대로 받는다 -->
        <label
          v-for="(d, i) in days"
          :key="d.date"
          class="rs__chip"
          :class="{ 'rs__chip--on': d.date === date }"
        >
          <input
            type="radio"
            name="date"
            class="rs__chip-in"
            :value="d.date"
            :checked="d.date === date"
            :aria-label="i === 0 ? `오늘 ${dateLabel(d.date)}` : dateLabel(d.date)"
            @change="pickDay(d.date)"
          />
          <span>{{ i === 0 ? '오늘' : chipDay(d.date) }}</span>
          <span class="rs__chip-num num">{{ Number(d.date.slice(8, 10)) }}</span>
        </label>
      </div>
    </section>

    <fieldset v-if="day" class="rs__sec rs__spans">
      <legend class="rs__h">
        비어 있는 시간 <span class="rs__sub">· {{ dateLabel(day.date) }}</span>
      </legend>
      <p v-if="!shown.length" class="rs__empty">
        {{ full ? FULL_TEXT : '이 날은 비어 있는 시간이 없어요' }}
      </p>
      <label
        v-for="s in shown"
        :key="spanKey(s)"
        class="rs__span"
        :class="{ 'rs__span--on': spanKey(s) === spanId }"
      >
        <input
          type="radio"
          name="span"
          :value="spanKey(s)"
          :checked="spanKey(s) === spanId"
          @change="pickSpan(s)"
        />
        <span class="num">{{ s.from }} – {{ s.to }}</span>
        <span class="rs__dur">{{ durationText(hmToMin(s.to) - hmToMin(s.from)) }}</span>
      </label>
    </fieldset>

    <div v-if="span" class="rs__sec rs__time">
      <Select
        label="시작"
        :model-value="start ?? undefined"
        :options="startOpts"
        @update:model-value="pickStart"
      />
      <Select
        label="끝"
        :model-value="end ?? undefined"
        :options="endOpts"
        @update:model-value="pickEnd"
      />
    </div>

    <div class="rs__sec">
      <Input
        v-model="subject"
        label="무엇에 쓰나요"
        required
        :max-bytes="maxBytes"
        :hint="DOOR_HINT"
      />
      <p class="rs__note">예약하면 관리자 승인 뒤 확정돼요</p>
    </div>

    <footer class="rs__bar">
      <p v-if="blocker" class="rs__blocker" role="status">{{ blocker }}</p>
      <div class="rs__bar-row">
        <p class="rs__summary num">{{ summary }}</p>
        <Button type="submit" :disabled="!valid || !!blocker" :loading="submitting"
          >예약하기</Button
        >
      </div>
    </footer>
  </form>
</template>

<style scoped>
.rs {
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 58px);
  min-height: calc(100dvh - 58px);
}
.rs__sec {
  min-width: 0;
  margin: 0;
  padding: var(--space-4) var(--space-4) 0;
  border: 0;
}
.rs__h {
  margin: 0 0 var(--space-2);
  padding: 0;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-bold);
}
.rs__sub {
  font-weight: var(--font-weight-regular);
  color: var(--text-3);
}
.rs__chips {
  display: flex;
  gap: var(--space-2);
  overflow-x: auto;
}
.rs__chip {
  position: relative;
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-width: 52px;
  height: 52px;
  border: var(--border-thin) solid var(--line-3);
  border-radius: var(--radius-md);
  background: var(--surface);
  color: var(--text-1);
  font: inherit;
  font-size: var(--font-size-sm);
  line-height: var(--leading-tight);
  cursor: pointer;
}
.rs__chip-in {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  margin: 0;
  opacity: 0;
  cursor: pointer;
}
/* 입력이 투명하니 초점 링은 칩에 — 가로 스크롤 상자가 바깥 링을 자르니 안쪽으로 */
.rs__chip:has(.rs__chip-in:focus-visible) {
  outline: var(--border-thick) solid var(--focus);
  outline-offset: -2px;
}
.rs__chip--on {
  border-color: var(--brand);
  background: var(--brand-tint);
  color: var(--brand);
  font-weight: var(--font-weight-bold);
}
.rs__chip-num {
  font-size: var(--font-size-xs);
}
/* legend 는 fieldset 테두리 자리에 그려져 padding 이 legend 아래로 간다 — 위 간격은 margin 으로 */
.rs__spans {
  margin-top: var(--space-4);
  padding-top: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.rs__span {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: 52px;
  padding: 0 var(--space-3);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-md);
  background: var(--surface);
  cursor: pointer;
}
.rs__span input {
  accent-color: var(--brand);
}
.rs__span--on {
  border-color: var(--brand);
  background: var(--brand-tint);
}
.rs__dur {
  margin-left: auto;
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
.rs__empty {
  margin: 0;
  color: var(--text-3);
}
.rs__time {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
}
.rs__note {
  margin: var(--space-2) 0 0;
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.rs__bar {
  position: sticky;
  bottom: 0;
  margin-top: auto;
  padding: var(--space-3) var(--space-4);
  border-top: var(--border-thin) solid var(--line-2);
  background: var(--surface);
}
.rs__blocker {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
  color: var(--text-1);
}
.rs__bar-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.rs__summary {
  flex: 1;
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
</style>
