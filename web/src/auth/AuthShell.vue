<script setup lang="ts">
import { RouterLink } from 'vue-router'

defineProps<{ title: string; surface: 'student' | 'admin'; back?: string }>()
</script>

<template>
  <!-- 로그인 전에는 사이드바를 그리지 않는다 — 빈 바탕에 폼 하나 (auth.md) -->
  <div class="auth" :class="`auth--${surface}`">
    <slot name="banner" />
    <div class="auth__body">
      <!-- 학생 PC(≥640) 는 좌우 분할 — 왼쪽 소개, 오른쪽 폼. 폰에서는 숨긴다 -->
      <aside v-if="surface === 'student'" class="auth__intro">
        <p class="auth__intro-brand">우송 ESC</p>
        <p class="auth__intro-lead">학교의 빈 강의실을 확인하고 예약하세요.</p>
        <ul class="auth__intro-list">
          <li>지금 빈 강의실</li>
          <li>이번 주 시간표</li>
          <li>예약 신청·승인</li>
        </ul>
      </aside>
      <div class="auth__pane">
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
    </div>
  </div>
</template>

<style scoped>
/* flow-root — 카드의 윗여백이 바탕 밖으로 새어(margin collapse) 100vh 위에 얹혀 스크롤이 생기지 않게 */
.auth {
  display: flow-root;
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
.auth__intro {
  display: none;
}
@media (min-width: 640px) {
  /* 좌우 분할 — 왼쪽 brand 패널, 오른쪽 폼을 세로 가운데 */
  .auth--student .auth__body {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    min-height: 100vh;
  }
  .auth--student .auth__intro {
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: var(--space-5);
    padding: var(--space-7);
    background: var(--brand);
    color: var(--on-brand);
  }
  .auth--student .auth__pane {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--space-6) var(--space-4);
  }
  /* 왼쪽 패널이 이름을 이미 말한다 — 폼 위의 작은 이름은 뺀다 */
  .auth--student .auth__card .auth__brand {
    display: none;
  }
}
.auth__intro-brand {
  margin: 0;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-bold);
}
.auth__intro-lead {
  margin: 0;
  max-width: 20em;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  line-height: var(--leading-tight);
}
.auth__intro-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding-left: 1.2em;
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
/* 버튼 모양 링크(.cta, 로그인 벽)는 제 스타일 그대로 */
.auth__card > :slotted(a:not(.cta)) {
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
/* 학생은 폰 — 바닥·안내 문단의 링크도 터치 타깃 48px (tokens.md) */
.auth--student .auth__footer :deep(a),
.auth--student :slotted(.auth-form__note) a {
  display: inline-flex;
  align-items: center;
  min-height: var(--control-height-md);
}
</style>
