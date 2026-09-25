<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import ToastHost from '@/components/ui/ToastHost.vue'
import { session } from '@/lib/session'
import LoginGate from './LoginGate.vue'

const route = useRoute()
// 조회도 로그인이 필요하다(S10 §3). 리다이렉트 없이 그 주소에서 벽을 그린다 — 주소가 곧 상태
const gated = computed(() => route.meta.gate === true && !session.value)
const gateBld = computed(() =>
  typeof route.params.bld === 'string' ? route.params.bld : undefined,
)
</script>

<template>
  <LoginGate v-if="gated" :bld="gateBld" :next="route.fullPath" />
  <RouterView v-else />
  <ToastHost />
</template>
