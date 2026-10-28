<script setup lang="ts">
import ResvStatusBadge from '@/components/student/ResvStatusBadge.vue'

// 다음 예약 카드 + 신청 → 승인 → 체크인. 현재 단계만 brand.tint + brand 테두리 (landing.md 기능 카드 3)
const STEPS = ['신청', '승인', '체크인']
const CURRENT = 1
</script>

<template>
  <div class="rp" role="img" aria-label="예약 신청 예시">
    <div class="rp__card">
      <p class="rp__head">
        <span class="rp__label">다음 예약</span><ResvStatusBadge status="approved" />
      </p>
      <p class="rp__when num">10/16 목 14:00–15:00</p>
      <p class="rp__where">공학관 401호 · 스터디</p>
    </div>
    <p class="rp__steps">
      <template v-for="(s, i) in STEPS" :key="s">
        <span v-if="i" class="rp__arrow">→</span>
        <span class="rp__step" :class="{ 'rp__step--on': i === CURRENT }">{{ s }}</span>
      </template>
    </p>
  </div>
</template>

<style scoped>
.rp {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.rp__card {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-3);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-md);
  background: var(--surface);
}
.rp__card p {
  margin: 0;
}
.rp__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.rp__label {
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.rp__when {
  font-weight: var(--font-weight-bold);
}
.rp__where {
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.rp__steps {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  margin: 0;
}
.rp__arrow {
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.rp__step {
  padding: 2px var(--space-2);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-full);
  background: var(--surface);
  font-size: var(--font-size-xs);
  color: var(--text-2);
}
.rp__step--on {
  border-color: var(--brand);
  background: var(--brand-tint);
  color: var(--brand);
  font-weight: var(--font-weight-bold);
}
</style>
