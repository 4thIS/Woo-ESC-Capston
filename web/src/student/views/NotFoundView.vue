<script setup lang="ts">
import { RouterLink } from 'vue-router'
import StudentHeader from '../StudentHeader.vue'

// 주소를 잘못 친 경우가 흔하다 — 돌아갈 링크를 준다. 없는 방·예약을 안 받는 방·다른 학교 방이 모두 여기
withDefaults(defineProps<{ back?: string; backLabel?: string }>(), {
  back: '/',
  backLabel: '건물 목록으로',
})
</script>

<template>
  <div class="nf">
    <StudentHeader title="우송 ESC" />
    <main class="nf__body">
      <h2 class="nf__title">찾을 수 없는 주소예요</h2>
      <p class="nf__text">주소를 잘못 입력했거나, 예약을 받지 않는 강의실이에요.</p>
      <RouterLink :to="back" class="nf__link">{{ backLabel }}</RouterLink>
    </main>
  </div>
</template>

<style scoped>
.nf__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-6) var(--space-4);
}
.nf__title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
}
.nf__text {
  margin: 0;
  color: var(--text-2);
}
.nf__link {
  display: inline-flex;
  align-items: center;
  min-height: 48px;
  color: var(--brand);
  font-weight: var(--font-weight-bold);
}
</style>
