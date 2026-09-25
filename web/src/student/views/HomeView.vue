<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import EmptyState from '@/components/ui/EmptyState.vue'
import { clearSession, session } from '@/lib/session'

const router = useRouter()
const message = computed(() => `${session.value?.name ?? ''}님, 강의실 화면은 준비 중입니다`)
function logout() {
  clearSession()
  void router.replace('/login')
}
</script>

<template>
  <main>
    <EmptyState
      :message="message"
      :actions="[{ label: '로그아웃', variant: 'secondary', onClick: logout }]"
    />
  </main>
</template>
