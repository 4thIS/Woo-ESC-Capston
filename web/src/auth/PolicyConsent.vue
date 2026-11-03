<script setup lang="ts">
// 가입 화면 버튼 아래 한 줄 — 누르면 동의한 것으로 본다(이용약관 제4조). 체크박스는 두지 않는다.
// 새 탭으로 연다 — 같은 탭이면 입력값이 사라지고 /verify 는 메일 링크 토큰을 이미 주소에서 지워 돌아와도 못 쓴다
defineProps<{ lead: string }>()
</script>

<template>
  <p class="consent">
    {{ lead }}
    <a href="/policies/terms" target="_blank" rel="noopener">이용약관</a>과
    <a href="/policies/privacy" target="_blank" rel="noopener">개인정보 처리방침</a>에 동의하는
    것으로 봅니다.
  </p>
</template>

<style scoped>
.consent {
  margin: 0;
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-2);
}
.consent a {
  color: var(--text-1);
  font-weight: var(--font-weight-medium);
  text-decoration: underline;
  text-underline-offset: 2px;
}
</style>
