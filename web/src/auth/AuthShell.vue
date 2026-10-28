<script setup lang="ts">
import { RouterLink } from 'vue-router'

// home — 로그인 화면만: 폼 위 이름이 `‹ ESC`, ‹ 는 메인 페이지 / 로 (auth.md 「탭」)
defineProps<{ title: string; surface: 'student' | 'admin'; back?: string; home?: boolean }>()
</script>

<template>
  <!-- 로그인 전에는 사이드바를 그리지 않는다 (auth.md). data-surface — 관리자 앱에서 열린 관리자 로그인도
       학생 로그인과 탭으로 오가는 한 화면이라 student 치수 (#87 「관리자 로그인」) -->
  <div
    class="auth"
    :class="`auth--${surface}`"
    :data-surface="surface === 'student' ? 'student' : undefined"
  >
    <slot name="banner" />
    <div class="auth__body">
      <!-- 학생 PC(≥640) 는 좌우 분할 — 왼쪽 소개, 오른쪽 폼. 폰에서는 숨긴다 -->
      <aside v-if="surface === 'student'" class="auth__intro">
        <!-- 로그인 전에는 학교를 모른다(웹메일 도메인으로 정해진다) — 학교 이름 없이 서비스 이름만 -->
        <!-- 메인 페이지 / 로 — 관리자 앱에서도 페이지를 새로 연다(라우터 이동 아님) -->
        <p class="auth__intro-brand"><a href="/">ESC</a></p>
        <p class="auth__intro-lead">학교의 빈 강의실을 확인하고 예약하세요.</p>
        <ul class="auth__intro-list">
          <li>지금 빈 강의실</li>
          <li>이번 주 시간표</li>
          <li>예약 신청·승인</li>
        </ul>
      </aside>
      <div class="auth__pane">
        <main class="auth__card">
          <p class="auth__brand">
            <a v-if="home" href="/" class="auth__home" aria-label="메인 페이지">‹</a>ESC
          </p>
          <slot name="tabs" />
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
  /* html 의 글자 크기는 그 앱의 치수로 이미 계산돼 상속된다 — 관리자 앱에서도 student 값으로 다시 잡는다 */
  font-size: var(--font-size-md);
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
  /* 좌우 분할 — 왼쪽 소개 패널(가라앉은 면 — brand 는 1차 액션 전용), 오른쪽 폼을 세로 가운데 */
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
    border-right: var(--border-thin) solid var(--line-2);
    background: var(--sunken);
    color: var(--text-1);
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
.auth__intro-brand a {
  color: inherit;
  text-decoration: none;
}
.auth__intro-brand a:hover {
  text-decoration: underline;
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
  display: flex;
  align-items: center;
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
/* ‹ — 터치 타깃 48px, 글자는 이름 줄과 같은 선 (.auth__back 과 같은 몫) */
.auth__home {
  display: inline-grid;
  place-items: center;
  min-width: var(--control-height-md);
  min-height: var(--control-height-md);
  margin: calc(-1 * var(--space-3)) 0 calc(-1 * var(--space-3)) calc(-1 * var(--space-3));
  font-size: var(--font-size-xl);
  color: var(--text-1);
  text-decoration: none;
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
