<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import ToastHost from '@/components/ui/ToastHost.vue'
import { session } from '@/lib/session'
import LoginGate from './LoginGate.vue'
import LandingView from './views/landing/LandingView.vue'

const route = useRoute()
// 조회도 로그인이 필요하다(S10 §3). 리다이렉트 없이 그 주소에서 벽을 그린다 — 주소가 곧 상태
const gated = computed(() => route.meta.gate === true && !session.value)
const gateBld = computed(() =>
  typeof route.params.bld === 'string' ? route.params.bld : undefined,
)
</script>

<template>
  <!-- `/` 는 벽 대신 메인 페이지 — 딥링크(/E/401)는 볼 곳을 알고 온 사람이라 벽 그대로 (landing.md) -->
  <LandingView v-if="gated && route.path === '/'" />
  <LoginGate v-else-if="gated" :bld="gateBld" :next="route.fullPath" />
  <!-- 화면 전환 — 관리자와 같은 움직임. 같은 화면의 주소 글자만 바뀌면 다시 그리지 않는다 -->
  <RouterView v-else v-slot="{ Component, route: r }">
    <div :key="r.matched[0]?.path" class="page">
      <component :is="Component" />
    </div>
  </RouterView>
  <ToastHost />
</template>
