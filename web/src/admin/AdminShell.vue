<script setup lang="ts">
import { computed, onMounted, onScopeDispose, ref } from 'vue'
import { RouterView, useRouter } from 'vue-router'
import SidebarNav from '@/components/ui/SidebarNav.vue'
import Banner from '@/components/ui/Banner.vue'
import Button from '@/components/ui/Button.vue'
import { clearSession, session } from '@/lib/session'
import { ApiError } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { SchoolOut } from '@/api/types'
import { usePolling } from '@/lib/usePolling'
import { pendingCount, refreshPending } from './pending'

const router = useRouter()
const me = computed(() => session.value?.name ?? '')
// #46 admin-master.md 순서: 건물 · 강의실 · 강의실 설정 · 주간 시간표 · 노드 상태 · 전송 현황 · 회원
const nav = computed(() => [
  { to: '/master', label: '건물 · 강의실' },
  { to: '/rooms', label: '강의실 설정' },
  { to: '/nodes', label: '노드 상태' },
  { to: '/dashboard', label: '전송 현황' },
  { to: '/users', label: '회원', badge: pendingCount.value },
])

onMounted(refreshPending)
// 학교는 CLI 에서만 만든다 — 지금 학교를 읽기 전용으로 (admin-master.md). 버튼을 두고 405 를 받게 하지 않는다
const school = ref<SchoolOut | null>(null)
onMounted(async () => {
  try {
    school.value = (await roomsApi.schools())[0] ?? null
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
  }
})
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
        <p v-if="school" class="shell__school num">
          {{ school.name }} · net_id {{ school.net_id }}
        </p>
        <p class="shell__cli">학교는 CLI 에서만 만든다</p>
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
.shell__school {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.shell__cli {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
</style>
