<script setup lang="ts">
import { RouterLink } from 'vue-router'
import AuthShell from '@/auth/AuthShell.vue'
import Banner from '@/components/ui/Banner.vue'
import { authNotice } from '@/lib/session'
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
    <!-- 새로고침한 탭의 세션이 만료돼 버려졌다(restoreSession) — 말없이 벽만 서지 않게. 지우지 않고 두어
         로그인 화면에서도 한 번 더 보인다 -->
    <template #banner>
      <Banner
        v-if="authNotice === 'expired'"
        message="다시 로그인해 주세요."
        :dismissible="false"
      />
    </template>
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
