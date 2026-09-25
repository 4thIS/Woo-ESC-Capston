<script setup lang="ts">
import { RouterLink } from 'vue-router'
import CtaLink from './CtaLink.vue'

// 빈 로그인 폼 대신 — 무엇을 볼 수 있는지 한 문장과 어느 건물인지(주소의 글자)부터 (student-room.md §로그인 벽)
defineProps<{ bld?: string; next: string }>()
</script>

<template>
  <main class="gate">
    <p class="gate__brand">우송 ESC</p>
    <h1 class="gate__title">
      {{ bld ? `${bld}동` : '학교' }}의 빈 강의실을 확인하고 예약을 신청할 수 있어요.
    </h1>
    <p class="gate__text">학교 웹메일로 로그인하세요.</p>
    <CtaLink :to="{ path: '/login', query: { next } }">로그인</CtaLink>
    <p class="gate__text">
      처음이신가요? <RouterLink to="/signup" class="gate__link">가입 신청</RouterLink>
    </p>
  </main>
</template>

<style scoped>
.gate {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  max-width: 400px;
  min-height: 100vh;
  margin: 0 auto;
  padding: var(--space-7) var(--space-4);
  background: var(--surface);
}
.gate__brand {
  margin: 0;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
  color: var(--text-2);
}
.gate__title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  line-height: var(--leading-tight);
}
.gate__text {
  margin: 0;
  color: var(--text-2);
}
.gate__link {
  display: inline-flex;
  align-items: center;
  min-height: 48px;
  color: var(--brand);
  font-weight: var(--font-weight-bold);
}
</style>
