<script setup lang="ts">
import { computed, provide, watch } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import { studentApi } from '@/api/student'
import ToastHost from '@/components/ui/ToastHost.vue'
import { session } from '@/lib/session'
import { usePolling } from '@/lib/usePolling'
import { useResource } from '@/lib/useResource'
import LoginGate from './LoginGate.vue'
import StudentNav from './StudentNav.vue'
import { MINE } from './building'
import { POLL_MS } from './composables'
import LandingView from './views/landing/LandingView.vue'

const route = useRoute()
// 조회도 로그인이 필요하다(S10 §3). 리다이렉트 없이 그 주소에서 벽을 그린다 — 주소가 곧 상태
const gated = computed(() => route.meta.gate === true && !session.value)
const gateBld = computed(() =>
  typeof route.params.bld === 'string' ? route.params.bld : undefined,
)
// 메뉴는 로그인한 학생 화면에만 — 인증 · 약관 · 404 에는 없다 (student-room.md 「학생 앱 메뉴」)
const nav = computed(() => route.meta.gate === true && !!session.value)
const tabs = computed(() => nav.value && route.meta.detail !== true)

// 내 예약 한 벌 — 메뉴 배지 · 다음 예약 카드 · 내 예약 화면이 같이 쓴다. 로그인 동안만 부른다
const mine = useResource(() => studentApi.mine(), { immediate: false })
watch(
  () => session.value?.token,
  (t) => {
    if (t) void mine.reload()
    else mine.data.value = undefined
  },
  { immediate: true },
)
usePolling(async () => {
  if (session.value) await mine.reload()
}, POLL_MS)
provide(MINE, mine)
</script>

<template>
  <!-- `/` 는 벽 대신 메인 페이지 — 딥링크(/E/401)는 볼 곳을 알고 온 사람이라 벽 그대로 (landing.md) -->
  <LandingView v-if="gated && route.path === '/'" />
  <LoginGate v-else-if="gated" :bld="gateBld" :next="route.fullPath" />
  <template v-else>
    <StudentNav v-if="nav" :tabs="tabs" />
    <!-- 화면 전환 — 관리자와 같은 움직임. 같은 화면의 주소 글자만 바뀌면 다시 그리지 않는다 -->
    <RouterView v-slot="{ Component, route: r }">
      <div :key="r.matched[0]?.path" class="page" :class="{ 'page--tabs': tabs, 'page--nav': nav }">
        <component :is="Component" />
      </div>
    </RouterView>
  </template>
  <ToastHost />
</template>

<style scoped>
/* 위 막대 높이 — 메뉴가 있는 화면에서만(넓은 폭). StudentHeader · 목록 칸이 이 아래에 붙는다.
   약관 · 404 같은 공개 화면은 막대가 없어 0 — 헤더가 64px 아래에 뜨지 않는다 */
@media (min-width: 640px) {
  .page--nav {
    --student-nav-h: 64px;
  }
}
/* 아래 탭(64px + 기기 아래 여백)이 마지막 줄을 가리지 않게 — 폰에서만 */
@media (max-width: 639px) {
  .page--tabs {
    padding-bottom: calc(64px + env(safe-area-inset-bottom));
  }
}
</style>
