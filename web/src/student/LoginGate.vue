<script setup lang="ts">
import { RouterLink } from 'vue-router'
import AuthShell from '@/auth/AuthShell.vue'
import CtaLink from './CtaLink.vue'

// 빈 로그인 폼 대신 — 무엇을 볼 수 있는지 한 문장과 어느 건물인지(주소의 글자)부터 (student-room.md §로그인 벽).
// 로그인·가입 화면과 같은 틀(AuthShell) — PC 에서는 왼쪽 소개 패널 + 오른쪽 이 안내
defineProps<{ bld?: string; next: string }>()
</script>

<template>
  <AuthShell
    surface="student"
    :title="`${bld ? `${bld}동` : '학교'}의 빈 강의실을 확인하고 예약을 신청할 수 있어요.`"
  >
    <p class="gate__text">학교 웹메일로 로그인하세요.</p>
    <CtaLink :to="{ path: '/login', query: { next } }">로그인</CtaLink>
    <p class="gate__text">
      처음이신가요? <RouterLink to="/signup" class="gate__link">가입 신청</RouterLink>
    </p>
  </AuthShell>
</template>

<style scoped>
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
