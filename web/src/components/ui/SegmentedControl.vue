<script setup lang="ts">
import { useId } from 'vue'

// 붙은 버튼 줄 (components.md SegmentedControl) — 라디오 줄. 지금 쓰는 곳은 로그인 학생|관리자 탭 하나로,
// 고르면 같은 화면에서 바뀐다(주소를 바꾸지 않는다, 2026-10-28 결정). ponytail: href 링크 줄은 쓰는 곳이 생기면
defineProps<{ items: { value: string; label: string }[]; value: string; label: string }>()
const emit = defineEmits<{ 'update:value': [value: string] }>()
const name = useId()
</script>

<template>
  <!-- 네이티브 라디오(날짜 칩과 같은 방식) — 한 번의 Tab 멈춤, 화살표로 옮긴다. 입력은 칸 전체를 덮는다 -->
  <div class="seg" role="radiogroup" :aria-label="label">
    <label
      v-for="i in items"
      :key="i.value"
      class="seg__item"
      :class="{ 'seg__item--on': i.value === value }"
    >
      <input
        type="radio"
        class="seg__in"
        :name="name"
        :value="i.value"
        :checked="i.value === value"
        @change="emit('update:value', i.value)"
      />{{ i.label }}
    </label>
  </div>
</template>

<style scoped>
/* 선택은 1차 액션이 아니다 — brand 없이 면(surface vs sunken)과 굵기로 고른 칸을 세운다 */
.seg {
  display: grid;
  grid-auto-columns: minmax(0, 1fr);
  grid-auto-flow: column;
  gap: var(--space-1);
  height: var(--control-height-md);
  padding: var(--space-1);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-md);
  background: var(--sunken);
}
.seg__item {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  border: var(--border-thin) solid transparent;
  border-radius: var(--radius-sm);
  color: var(--text-2);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition:
    background-color var(--dur-fast) ease,
    color var(--dur-fast) ease;
}
.seg__in {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  margin: 0;
  opacity: 0;
  cursor: pointer;
}
/* 입력이 투명하니 초점 링은 칸에 (Button 과 같은 2px · offset 2px) */
.seg__item:has(.seg__in:focus-visible) {
  outline: var(--border-thick) solid var(--focus);
  outline-offset: 2px;
}
.seg__item:hover {
  color: var(--text-1);
}
.seg__item--on {
  border-color: var(--line-2);
  background: var(--surface);
  color: var(--text-1);
  font-weight: var(--font-weight-bold);
}
</style>
