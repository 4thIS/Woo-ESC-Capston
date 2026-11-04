<script setup lang="ts">
import { useRouter } from 'vue-router'
import EmptyState from '@/components/ui/EmptyState.vue'

// 없는 주소 — 메뉴는 그대로 두고(셸 안 라우트) 기본 화면으로 가는 길을 준다
const router = useRouter()
</script>

<template>
  <EmptyState
    message="찾을 수 없는 주소입니다. 주소를 확인하거나 전송 현황으로 돌아가세요."
    :actions="[
      { label: '전송 현황으로', variant: 'primary', onClick: () => void router.push('/dashboard') },
    ]"
  />
</template>
