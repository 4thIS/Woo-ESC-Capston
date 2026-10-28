<script setup lang="ts">
// 이번 주 격자(화면 2)의 축소 — 월~금 × 5칸. 사용중은 room.busy, 내 예약은 brand 1px 테두리 (student-room.md 와 같은 규칙)
const DAYS = ['월', '화', '수', '목', '금']
const BLOCKS = [
  { day: 1, from: 1, span: 2, label: '수업' },
  { day: 2, from: 3, span: 1, label: '시험' },
  { day: 3, from: 1, span: 1, label: '수업' },
  { day: 3, from: 4, span: 1, label: '내 예약', mine: true },
  { day: 4, from: 2, span: 2, label: '특강' },
  { day: 5, from: 1, span: 1, label: '수업' },
]
</script>

<template>
  <div class="wp" role="img" aria-label="주간 시간표 예시">
    <span v-for="(d, i) in DAYS" :key="d" class="wp__day" :style="{ gridColumn: i + 1 }">{{
      d
    }}</span>
    <span
      v-for="b in BLOCKS"
      :key="`${b.day}-${b.from}`"
      class="wp__block"
      :class="{ 'wp__block--mine': b.mine }"
      :style="{ gridColumn: b.day, gridRow: `${b.from + 1} / span ${b.span}` }"
      ><span class="wp__label">{{ b.label }}</span></span
    >
  </div>
</template>

<style scoped>
/* 카드 한 칸이 좁아져도(넓은 화면 ≈268px) 5열을 지킨다 — 요일 칸이 30px 아래면 라벨을 지우고 색만 (landing.md) */
.wp {
  container-type: inline-size;
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  grid-template-rows: auto repeat(5, 22px);
  gap: 3px;
  padding: var(--space-2);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-md);
  background: var(--surface);
}
.wp__day {
  grid-row: 1;
  text-align: center;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.wp__block {
  display: flex;
  align-items: flex-start;
  min-width: 0;
  padding: 2px 4px;
  border: var(--border-thin) solid var(--room-busy-line);
  border-radius: var(--radius-sm);
  background: var(--room-busy-fill);
  color: var(--room-busy-label);
  overflow: hidden;
}
.wp__block--mine {
  border-color: var(--brand);
}
.wp__label {
  font-size: 10px;
  font-weight: var(--font-weight-bold);
  white-space: nowrap;
}
@container (max-width: 170px) {
  .wp__label {
    display: none;
  }
}
</style>
