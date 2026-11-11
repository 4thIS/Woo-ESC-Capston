<script setup lang="ts">
import { RouterLink } from 'vue-router'
import LogoRiver from '@/components/domain/LogoRiver.vue'
import logo from '@/assets/logo/esc-logo.svg'

// home — 로그인 화면만: 폼 위 이름이 `‹ ESC`, ‹ 는 메인 페이지 / 로 (auth.md 「탭」)
// titleHidden — 로그인 화면만: 탭·제출 버튼이 이미 '로그인'이라 제목은 스크린리더용으로만 (auth.md, #95)
defineProps<{
  title: string
  surface: 'student' | 'admin'
  back?: string
  home?: boolean
  titleHidden?: boolean
}>()
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
    <!-- 폰 로그인 위 띠 — 다른 화면은 폼이 첫 화면에서 밀려 두지 않는다 (auth.md) -->
    <div v-if="surface === 'student' && home" class="auth__band">
      <div class="auth__band-river"><LogoRiver :k="0.3" :height="150" /></div>
      <div class="auth__band-cover"></div>
      <a href="/" class="auth__band-home" aria-label="메인 페이지"
        >‹ <img :src="logo" alt="ESC" width="44" height="16"
      /></a>
      <p class="auth__band-lead">학교의 빈 강의실을 <br />확인하고 예약하세요.</p>
    </div>
    <div class="auth__body">
      <!-- 학생 PC(≥640) 는 좌우 분할 — 왼쪽 소개, 오른쪽 폼. 폰에서는 숨긴다 -->
      <aside v-if="surface === 'student'" class="auth__intro">
        <!-- 로그인 전에는 학교를 모른다(웹메일 도메인으로 정해진다) — 학교 이름 없이 서비스 이름만 -->
        <!-- 메인 페이지 / 로 — 관리자 앱에서도 페이지를 새로 연다(라우터 이동 아님) -->
        <div class="auth__intro-river"><LogoRiver :k="0.72" :height="470" /></div>
        <div class="auth__intro-cover"></div>
        <!-- 로고 높이 20 (logo.md) — 링크 칸은 터치 하한 48 -->
        <p class="auth__intro-brand">
          <a href="/"><img :src="logo" alt="ESC" width="55" height="20" /></a>
        </p>
        <div class="auth__intro-text">
          <p class="auth__intro-lead">학교의 빈 강의실을 <br />확인하고 예약하세요.</p>
          <p class="auth__intro-can">지금 빈 강의실 · 이번 주 시간표 · 예약 신청·승인</p>
        </div>
      </aside>
      <div class="auth__pane">
        <main class="auth__card">
          <p class="auth__brand">
            <a v-if="home" href="/" class="auth__home" aria-label="메인 페이지">‹</a
            ><img :src="logo" alt="ESC" :width="home ? 44 : 55" :height="home ? 16 : 20" />
          </p>
          <slot name="tabs" />
          <h1 class="auth__title" :class="{ 'auth__title--sr': titleHidden }">
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
.auth__band {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  height: 300px;
  padding: var(--space-3) var(--space-4) var(--space-4);
  overflow: hidden;
  border-bottom: var(--border-thin) solid var(--line-2);
  background: var(--surface);
  color: var(--text-1);
}
/* ‹ ESC 와 한 문장 사이의 띠 — 로고가 글자 뒤로 지나가지 않는다 */
.auth__band-river {
  position: absolute;
  top: 64px;
  right: 0;
  left: 0;
  height: 150px;
}
.auth__band-cover {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    180deg,
    var(--surface) 64px,
    transparent 76px,
    transparent 200px,
    var(--surface) 222px
  );
  pointer-events: none;
}
.auth__band-home {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  align-self: flex-start;
  min-height: var(--control-height-md);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  color: inherit;
  text-decoration: none;
}
.auth__band-lead {
  position: relative;
  margin: 0;
  font-size: var(--font-size-display-band);
  font-weight: var(--font-weight-heavy);
  line-height: var(--leading-display);
}
/* 띠가 ‹ ESC 를 이미 말한다 — 폼 위 이름이 두 번 나오지 않게 */
.auth__band ~ .auth__body .auth__brand {
  display: none;
}
@media (min-width: 640px) {
  .auth__band {
    display: none;
  }
  /* 좌우 분할 — 왼쪽 소개 패널(brand 는 1차 액션 전용), 오른쪽 폼을 세로 가운데 */
  .auth--student .auth__body {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    min-height: 100vh;
  }
  .auth--student .auth__intro {
    position: relative;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    gap: var(--space-5);
    min-width: 0;
    padding: var(--panel-inset-y) var(--space-7);
    overflow: hidden;
    border-right: var(--border-thin) solid var(--line-2);
    background: var(--surface);
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
/* ESC 아래부터 흐른다. 아래쪽 글자는 글자 칸 자체의 바탕색이 덮는다(.auth__intro-text) */
.auth__intro-river {
  position: absolute;
  top: 88px;
  right: 0;
  left: 0;
  height: 470px;
}
.auth__intro-cover {
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, var(--surface) 88px, transparent 108px);
  pointer-events: none;
}
.auth__intro-brand {
  position: relative;
  display: flex;
  margin: 0;
}
.auth__intro-brand a {
  display: inline-flex;
  align-items: center;
  min-height: var(--control-height-md);
  /* 칸만 48 로 키우고 자리는 로고 높이만큼 — 아래 로고 강·글자 위치가 그대로 */
  margin: calc((20px - var(--control-height-md)) / 2) 0;
}
/* 칸 폭이 좁아 제목이 여러 줄이 되어도 글자 높이만큼 덮는다 — 칸 양옆·바닥까지, 위로는 옅어진다 */
.auth__intro-text {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin: 0 calc(-1 * var(--space-7)) calc(-1 * var(--panel-inset-y));
  padding: 0 var(--space-7) var(--panel-inset-y);
  background: var(--surface);
}
.auth__intro-text::before {
  position: absolute;
  right: 0;
  bottom: 100%;
  left: 0;
  height: 100px;
  background: linear-gradient(0deg, var(--surface), transparent);
  content: '';
}
.auth__intro-lead {
  margin: 0;
  font-size: var(--font-size-display-auth);
  font-weight: var(--font-weight-heavy);
  line-height: var(--leading-display);
  letter-spacing: var(--tracking-display-auth);
}
.auth__intro-can {
  margin: 0;
  font-size: var(--font-size-md);
  color: var(--text-2);
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
/* 시각적으로만 숨김 — 읽기 순서·제목 이동은 그대로 */
.auth__title--sr {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
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
  /* 링크는 터치 타깃 48px 안에서 세로 가운데 — 가운뎃점도 같은 선에 (안 하면 48px 칸 맨 위에 붙는다) */
  align-items: center;
  /* 비어도 자리는 그대로(로그인 관리자 탭) — 탭을 바꿀 때 세로 가운데 놓인 폼이 움직이지 않게 */
  min-height: var(--control-height-md);
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
