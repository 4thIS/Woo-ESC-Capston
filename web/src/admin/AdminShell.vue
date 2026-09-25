<script setup lang="ts">
import { computed, onMounted, onScopeDispose, ref } from 'vue'
import { RouterView, useRouter } from 'vue-router'
import SidebarNav from '@/components/ui/SidebarNav.vue'
import Banner from '@/components/ui/Banner.vue'
import Button from '@/components/ui/Button.vue'
import { clearSession, session } from '@/lib/session'
import { usePolling } from '@/lib/usePolling'
import { pendingCount, refreshPending } from './pending'

const router = useRouter()
const me = computed(() => session.value?.name ?? '')
// F2·F3 가 위쪽에 항목을 더한다 — 순서는 #46 admin-master.md 확정본
const nav = computed(() => [{ to: '/users', label: '회원', badge: pendingCount.value }])

onMounted(refreshPending)
usePolling(refreshPending, 60_000)

// 데스크톱 전용 — 막지 않고 가로 스크롤 + 1회 안내 (tokens.md 브레이크포인트)
const mq = window.matchMedia('(max-width: 1023px)')
const narrow = ref(mq.matches)
const onChange = (e: MediaQueryListEvent) => (narrow.value = e.matches)
mq.addEventListener('change', onChange)
onScopeDispose(() => mq.removeEventListener('change', onChange))

function logout() {
  clearSession()
  void router.replace('/login')
}
</script>

<template>
  <div class="shell">
    <SidebarNav :items="nav">
      <template #footer>
        <p class="shell__user">{{ me }}</p>
        <Button variant="ghost" size="sm" class="shell__logout" @click="logout">로그아웃</Button>
      </template>
    </SidebarNav>
    <div class="shell__main">
      <Banner
        v-if="narrow"
        message="관리자 화면은 1024px 이상에서 쓰도록 만들어졌습니다"
        storage-key="admin-narrow"
      />
      <RouterView />
    </div>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  min-width: 1024px;
  min-height: 100vh;
}
.shell__main {
  flex: 1;
  min-width: 0;
}
.shell__user {
  margin: 0 0 var(--space-1);
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
</style>
