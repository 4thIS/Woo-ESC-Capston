<script setup lang="ts">
import { computed, ref } from 'vue'
import Button from '@/components/ui/Button.vue'
import { GUIDE_STEPS, swipeStep } from '../guide'

// 이용 안내 (student-room.md 「학생 앱 메뉴 · 이용 안내」) — 다섯 장을 버튼 · 점 · 단계 목록 · 스와이프로 넘긴다.
// 칸 폭으로 접힌다(container query) — 창을 줄여도 깨지지 않게
const cur = ref(0)
const step = computed(() => GUIDE_STEPS[cur.value])
const last = GUIDE_STEPS.length - 1
const go = (i: number) => {
  cur.value = Math.min(last, Math.max(0, i))
}
const next = () => go(cur.value === last ? 0 : cur.value + 1)

let start: { x: number; y: number } | null = null
function down(e: PointerEvent) {
  start = { x: e.clientX, y: e.clientY }
}
function up(e: PointerEvent) {
  if (!start) return
  const d = swipeStep(e.clientX - start.x, e.clientY - start.y)
  start = null
  if (d) go(cur.value + d)
}
</script>

<template>
  <main class="gd">
    <header class="gd__head">
      <h1 class="gd__h1">이용 안내</h1>
      <p class="gd__lead">
        빈 강의실을 찾는 데서 문 앞 화면에 내 예약이 뜨기까지. 한 장씩 넘겨 보세요.
      </p>
    </header>
    <div class="gd__body">
      <ol class="gd__steps" aria-label="이용 안내 단계">
        <li v-for="(s, i) in GUIDE_STEPS" :key="s.short">
          <button type="button" :aria-current="i === cur ? 'step' : undefined" @click="go(i)">
            <span class="gd__num num">{{ i + 1 }}</span
            >{{ s.short }}
          </button>
        </li>
      </ol>

      <!-- 사진을 옆으로 밀면 넘긴다 — 세로 스크롤은 그대로(touch-action: pan-y) -->
      <figure class="gd__figure" @pointerdown="down" @pointerup="up" @pointercancel="start = null">
        <div class="gd__frame" :class="`gd__frame--${step.frame}`">
          <img
            class="gd__img"
            :src="step.img"
            :alt="step.alt"
            :width="step.frame === 'door' ? 800 : 390"
            :height="step.frame === 'door' ? 480 : 844"
            draggable="false"
          />
        </div>
        <div class="gd__dots">
          <button
            v-for="(s, i) in GUIDE_STEPS"
            :key="s.short"
            type="button"
            :aria-label="`${i + 1}단계 ${s.short}`"
            :aria-current="i === cur ? 'step' : undefined"
            @click="go(i)"
          >
            <span />
          </button>
        </div>
        <figcaption class="gd__swipe">옆으로 밀면 다음 장</figcaption>
      </figure>

      <section class="gd__text" aria-live="polite">
        <p class="gd__count num">{{ cur + 1 }} / {{ GUIDE_STEPS.length }} · {{ step.chapter }}</p>
        <h2 class="gd__title">{{ step.title }}</h2>
        <p class="gd__desc">{{ step.desc }}</p>
        <ul class="gd__tips">
          <li v-for="t in step.tips" :key="t">
            <svg aria-hidden="true" viewBox="0 0 14 14"><path d="M2.5 7.5l3 3 6-7" /></svg>{{ t }}
          </li>
        </ul>
        <div class="gd__nav">
          <Button variant="secondary" :disabled="cur === 0" @click="go(cur - 1)">이전</Button>
          <Button class="gd__next" @click="next">{{ cur === last ? '처음으로' : '다음' }}</Button>
        </div>
      </section>
    </div>
  </main>
</template>

<style scoped>
.gd {
  container-type: inline-size;
  max-width: 1280px;
  margin: 0 auto;
  padding: var(--space-4);
  box-sizing: border-box;
}
.gd__head {
  margin-bottom: var(--space-4);
}
.gd__h1 {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
}
.gd__lead {
  margin: var(--space-1) 0 0;
  color: var(--text-2);
}
/* 좁으면 위에서 아래로 — 단계 칩 줄 · 사진 · 설명 */
.gd__body {
  display: grid;
  grid-template-areas: 'steps' 'figure' 'text';
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-4);
}
.gd__steps {
  grid-area: steps;
  display: flex;
  gap: var(--space-2);
  margin: 0;
  padding: 0 0 var(--space-1);
  overflow-x: auto;
  list-style: none;
}
.gd__steps button {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 44px;
  padding: 0 var(--space-3);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-full);
  background: var(--surface);
  color: var(--text-2);
  font: inherit;
  font-size: var(--font-size-sm);
  white-space: nowrap;
  cursor: pointer;
}
.gd__steps button:hover {
  background: var(--nav-hover);
}
.gd__steps button[aria-current='step'] {
  border-color: var(--brand);
  background: var(--brand-tint);
  color: var(--brand);
  font-weight: var(--font-weight-bold);
}
.gd__num {
  display: inline-grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: var(--radius-full);
  background: var(--sunken);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
}
[aria-current='step'] > .gd__num {
  background: var(--brand);
  color: var(--on-brand);
}
.gd__figure {
  grid-area: figure;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
  margin: 0;
  padding: var(--space-5) var(--space-4) var(--space-3);
  border-radius: var(--radius-lg);
  background: var(--sunken);
  touch-action: pan-y;
  user-select: none;
}
/* 기기처럼 — 폰 화면은 6px 테두리 · 둥근 모서리, 문 앞 e-Paper 는 10px 테두리 */
.gd__frame {
  width: 100%;
  overflow: hidden;
  border: 6px solid var(--text-1);
  border-radius: 18px;
  background: var(--surface);
  box-sizing: border-box;
}
.gd__frame--phone {
  max-width: 260px;
}
.gd__frame--door {
  max-width: 560px;
  border-width: 10px;
  border-radius: 10px;
}
.gd__img {
  display: block;
  width: 100%;
  height: auto;
}
.gd__dots {
  display: flex;
}
.gd__dots button {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
}
.gd__dots span {
  display: block;
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  background: var(--line-3);
  transition: width var(--dur-fast) var(--ease-soft);
}
.gd__dots [aria-current='step'] span {
  width: 22px;
  background: var(--brand);
}
.gd__swipe {
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.gd__text {
  grid-area: text;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  min-width: 0;
}
.gd__count {
  margin: 0;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
  color: var(--brand);
}
.gd__title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  line-height: var(--leading-tight);
}
.gd__desc {
  margin: 0;
  color: var(--text-1);
  line-height: var(--leading-relaxed);
}
.gd__tips {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-lg);
  background: var(--brand-tint);
  list-style: none;
}
.gd__tips li {
  display: flex;
  gap: var(--space-2);
  line-height: var(--leading-normal);
}
.gd__tips svg {
  flex: none;
  width: 14px;
  height: 14px;
  margin-top: 4px;
  fill: none;
  stroke: var(--brand);
  stroke-width: 2;
}
.gd__nav {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-1);
}
.gd__nav > :first-child {
  flex: 1;
}
.gd__next {
  flex: 2;
}
/* 중간 폭 — 단계 칩 줄 아래 사진 · 설명 나란히 */
@container (min-width: 600px) {
  .gd__body {
    grid-template-areas: 'steps steps' 'figure text';
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    align-items: start;
  }
  .gd__swipe {
    display: none;
  }
}
/* 넓은 폭 — 왼쪽 단계 목록 · 가운데 사진 · 오른쪽 설명 */
@container (min-width: 960px) {
  .gd__body {
    grid-template-areas: 'steps figure text';
    grid-template-columns: 220px minmax(0, 1fr) minmax(0, 1fr);
    gap: var(--space-6);
  }
  .gd__steps {
    flex-direction: column;
    gap: var(--space-1);
    overflow: visible;
  }
  .gd__steps button {
    width: 100%;
    border-color: transparent;
    border-radius: var(--radius-md);
    background: transparent;
  }
  .gd__title {
    font-size: var(--font-size-display-auth);
  }
}
</style>
