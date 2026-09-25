<script setup lang="ts">
import { RouterLink } from 'vue-router'

defineProps<{ title: string; surface: 'student' | 'admin'; back?: string }>()
</script>

<template>
  <!-- 로그인 전에는 사이드바를 그리지 않는다 — 빈 바탕에 폼 하나 (auth.md) -->
  <div class="auth" :class="`auth--${surface}`">
    <slot name="banner" />
    <main class="auth__card">
      <p class="auth__brand">우송 ESC</p>
      <h1 class="auth__title">
        <RouterLink v-if="back" :to="back" class="auth__back" aria-label="뒤로">‹</RouterLink
        >{{ title }}
      </h1>
      <slot />
      <div v-if="$slots.footer" class="auth__footer"><slot name="footer" /></div>
    </main>
  </div>
</template>

<style scoped>
.auth {
  min-height: 100vh;
}
.auth__card {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  width: 100%;
  max-width: 400px;
  margin: 0 auto;
  padding: var(--space-6) var(--space-4);
}
/* 폰에서는 카드가 화면 전체 — 카드 아래로 회색 바탕이 반쯤 드러나지 않게 */
.auth--student,
.auth--student .auth__card {
  background: var(--surface);
}
@media (min-width: 640px) {
  .auth--student {
    background: none;
  }
  .auth--student .auth__card {
    margin-top: var(--space-7);
    border: var(--border-thin) solid var(--line-2);
    border-radius: var(--radius-lg);
  }
}
.auth--admin .auth__card {
  max-width: 360px;
  margin-top: 15vh;
}
.auth__brand {
  margin: 0;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
  color: var(--text-2);
}
.auth__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  line-height: var(--leading-tight);
}
.auth__back {
  display: inline-grid;
  place-items: center;
  min-width: var(--control-height-md);
  min-height: var(--control-height-md);
  margin-left: calc(-1 * var(--space-3));
  color: var(--text-1);
  text-decoration: none;
}
.auth__footer {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  justify-content: center;
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
.auth__footer :deep(a) {
  color: var(--text-2);
}
/* 결과 화면의 맨 문단·링크 — 브라우저 기본 여백·파랑 대신, 링크는 터치 타깃 48px */
.auth__card :deep(p) {
  margin: 0;
}
.auth__card > :slotted(a) {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  min-height: var(--control-height-md);
  color: var(--brand);
}
:slotted(.auth-form) {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
:slotted(.auth-form) button[type='submit'] {
  width: 100%;
}
:slotted(.auth-form__error) {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--danger);
}
:slotted(.auth-form__note) {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
:slotted(.auth-form__note) a {
  color: var(--brand);
}
</style>
