<script setup lang="ts">
import { computed } from 'vue'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'
import { hm } from '@/lib/time'
import { COUNT_OPTIONS, periodsOf, type PeriodDraft } from './slotGroups'

// 시간 상자 (admin-rooms.md 「연속 교시 묶음」) — 시작 · 교시 수 · 한 교시를 고르면 끝과 교시 칩이 따라온다.
// 묶음 수정 창과 시간표 추가 창(여러 교시 한 번에)이 같이 쓴다
const props = defineProps<{
  modelValue: PeriodDraft
  patternOptions: { value: string; label: string }[]
  /** 시작 칸 아래 — 겹침 · 자정 넘김 */
  error?: string
  /** 칩 위 한 줄 — '저장되는 교시 …' / '추가되는 교시 …' */
  caption: string
}>()
const emit = defineEmits<{ 'update:modelValue': [v: PeriodDraft] }>()
const set = (patch: Partial<PeriodDraft>) =>
  emit('update:modelValue', { ...props.modelValue, ...patch })

const periods = computed(() => periodsOf(props.modelValue))
const endLabel = computed(() => {
  const p = periods.value
  const last = p ? p[p.length - 1] : null
  return last ? hm(last.e_h, last.e_m) : '—'
})
</script>

<template>
  <fieldset class="pf">
    <legend class="pf__legend">시간</legend>
    <div class="pf__grid">
      <Input
        :model-value="modelValue.start"
        label="시작"
        type="time"
        class="num"
        required
        :error="error"
        @update:model-value="(v: string) => set({ start: v })"
      />
      <Select
        :model-value="modelValue.count"
        label="교시 수"
        :options="COUNT_OPTIONS"
        @update:model-value="(v: string | number) => set({ count: Number(v) })"
      />
      <Select
        :model-value="modelValue.pattern"
        label="한 교시"
        :options="patternOptions"
        @update:model-value="(v: string | number) => set({ pattern: String(v) })"
      />
    </div>
    <p class="pf__end">
      끝 <b class="num">{{ endLabel }}</b> — 시작 · 교시 수에서 자동으로 정해집니다
    </p>
    <div class="pf__preview">
      <p class="pf__caption">{{ caption }}</p>
      <ul class="pf__chips">
        <li v-for="(p, i) in periods ?? []" :key="i" class="pf__chip num">
          {{ i + 1 }}교시 {{ hm(p.s_h, p.s_m) }}–{{ hm(p.e_h, p.e_m) }}
        </li>
      </ul>
      <slot />
    </div>
  </fieldset>
</template>

<style scoped>
.pf {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin: 0;
  padding: var(--space-3) var(--space-4) var(--space-4);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
}
.pf__legend {
  padding: 0 var(--space-1);
  font-weight: var(--font-weight-bold);
}
.pf__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-3) var(--space-4);
}
.pf__end {
  margin: 0;
  color: var(--text-2);
}
.pf__end b {
  color: var(--text-1);
}
.pf__preview {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding-top: var(--space-3);
  border-top: var(--border-thin) solid var(--line-1);
}
.pf__caption {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.pf__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}
.pf__chip {
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-full);
  background: var(--brand-tint);
  color: var(--brand);
  font-size: var(--font-size-xs);
}
</style>
