<script setup lang="ts">
// 문 앞 전자종이 축소판 — 흰 바탕 · 검정 글자 · 적색 사용중 띠 하나 (terminal-epaper.md 의 3색 그대로).
// 헤더는 시각이 아니라 요일 — 화면에 박힌 시각은 몇 시간씩 멈춰 틀린 정보가 된다 (terminal-epaper.md 「헤더」)
</script>

<template>
  <div class="ep" role="img" aria-label="문 앞 화면 예시">
    <p class="ep__head"><b>공학관 401호</b><span>목요일</span></p>
    <p class="ep__band">사용중</p>
    <p class="ep__now">자료구조 · 김교수</p>
    <p class="ep__time num">09:00 – 10:50</p>
    <p class="ep__next num">다음 13:00 운영체제</p>
  </div>
</template>

<style scoped>
.ep {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-2) var(--space-3);
  border: var(--border-thin) solid var(--line-3);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-1);
}
.ep p {
  margin: 0;
}
.ep__head {
  display: flex;
  justify-content: space-between;
  font-size: var(--font-size-sm);
}
.ep .ep__band {
  margin: var(--space-1) calc(-1 * var(--space-3));
  padding: 2px var(--space-3);
  background: var(--room-busy-label);
  color: var(--on-brand);
  font-weight: var(--font-weight-bold);
}
.ep__now {
  font-weight: var(--font-weight-bold);
}
.ep__time,
.ep .ep__next {
  font-size: var(--font-size-sm);
}
.ep .ep__next {
  margin-top: var(--space-1);
  padding-top: var(--space-1);
  border-top: var(--border-thin) solid var(--text-1);
}
</style>
