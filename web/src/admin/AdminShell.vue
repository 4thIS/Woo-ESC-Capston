<script setup lang="ts">
import { computed, onMounted, onScopeDispose, ref } from 'vue'
import { RouterView, useRouter } from 'vue-router'
import SidebarNav from '@/components/ui/SidebarNav.vue'
import Banner from '@/components/ui/Banner.vue'
import Button from '@/components/ui/Button.vue'
import Modal from '@/components/ui/Modal.vue'
import { clearSession, session } from '@/lib/session'
import { ApiError } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { SchoolOut } from '@/api/types'
import { usePolling } from '@/lib/usePolling'
import { mmss, useIdleLogout } from './idle'
import { pendingCount, refreshPending } from './pending'
import { weekRoom } from './selection'

const router = useRouter()
const me = computed(() => session.value?.name ?? '')
// #46 admin-master.md 순서: 건물 · 강의실 · 강의실 설정 · 주간 시간표 · 노드 상태 · 전송 현황 · 회원
const nav = computed(() => [
  { to: '/master', label: '건물 · 강의실', group: '운영', icon: 'building' as const },
  { to: '/rooms', label: '강의실 설정', group: '운영', icon: 'settings' as const },
  // 메뉴 항목에 :roomId 를 둘 수 없다 — 마지막으로 본 강의실, 없으면 /week 가 골라 준다
  {
    to: weekRoom.value === null ? '/week' : `/rooms/${weekRoom.value}/week`,
    label: '주간 시간표',
    group: '운영',
    icon: 'calendar' as const,
  },
  { to: '/nodes', label: '노드 상태', group: '모니터링', icon: 'node' as const },
  { to: '/dashboard', label: '전송 현황', group: '모니터링', icon: 'send' as const },
  { to: '/users', label: '회원', group: '사람', icon: 'users' as const, badge: pendingCount.value },
])
const initial = computed(() => me.value.slice(0, 1) || '관')

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

// 10분 무활동 자동 로그아웃 — 남은 시간과 연장은 늘 사이드바에, 마지막 1분은 모달로 묻는다
const idle = useIdleLogout()
const left = computed(() => mmss(idle.remaining.value))
</script>

<template>
  <div class="shell">
    <SidebarNav :items="nav">
      <template #header>
        <div class="shell__brand">
          <span class="shell__logo" aria-hidden="true">MJC</span>
          <p class="shell__brand-text"><b>MJC ESC</b><span>강의실 게시 관리자</span></p>
        </div>
      </template>
      <template #footer>
        <div class="shell__card">
          <p v-if="school" class="shell__school num">
            <b>{{ school.name }}</b> · net_id {{ school.net_id }}
          </p>
          <p class="shell__cli">학교는 CLI 에서만 만든다</p>
        </div>
        <div class="shell__me">
          <span class="shell__avatar" aria-hidden="true">{{ initial }}</span>
          <p class="shell__user">
            <b>{{ me }}</b
            ><span>관리자</span>
          </p>
          <button
            type="button"
            class="shell__logout"
            aria-label="로그아웃"
            title="로그아웃"
            @click="logout"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M15 4h4v16h-4M10 16l4-4-4-4M14 12H4" />
            </svg>
          </button>
        </div>
        <div class="shell__idle" :class="{ 'shell__idle--warn': idle.warning.value }">
          <span
            >자동 로그아웃 <b class="num" :aria-label="`${left} 남음`">{{ left }}</b></span
          >
          <Button variant="ghost" size="sm" @click="idle.extend">시간 연장</Button>
        </div>
      </template>
    </SidebarNav>
    <div class="shell__main">
      <Banner
        v-if="narrow"
        message="관리자 화면은 1024px 이상에서 쓰도록 만들어졌습니다"
        storage-key="admin-narrow"
      />
      <!-- 화면 전환 — 새 화면이 살짝 떠오르듯. 같은 화면의 :id 만 바뀌면(주간 시간표 강의실 이동) 다시 그리지 않는다 -->
      <RouterView v-slot="{ Component, route: r }">
        <div :key="r.matched[r.matched.length - 1]?.path" class="page">
          <component :is="Component" />
        </div>
      </RouterView>
    </div>
    <!-- 배경·Esc 로 닫지 않는다 — 닫는 것이 연장인지 아닌지 모호해진다 -->
    <Modal
      :open="idle.warning.value"
      title="곧 자동 로그아웃됩니다"
      size="sm"
      :close-on-backdrop="false"
      @close="idle.extend"
    >
      <p class="shell__warn num">
        10분 동안 활동이 없어 <b>{{ left }}</b> 뒤 로그아웃됩니다. 계속 쓰려면 시간을 연장하세요.
      </p>
      <template #footer>
        <Button variant="secondary" @click="logout">로그아웃</Button>
        <Button @click="idle.extend">시간 연장</Button>
      </template>
    </Modal>
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
.shell__brand {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.shell__logo {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-lg);
  background: var(--brand);
  color: var(--on-brand);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  letter-spacing: 0.02em;
}
.shell__brand-text,
.shell__user {
  display: flex;
  flex-direction: column;
  margin: 0;
  min-width: 0;
}
.shell__brand-text b,
.shell__user b {
  font-size: var(--font-size-md);
  color: var(--text-1);
}
.shell__brand-text span,
.shell__user span {
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.shell__card {
  margin: 0 var(--space-2) var(--space-3);
  padding: var(--space-3);
  border: var(--border-thin) solid var(--line-1);
  border-radius: var(--radius-lg);
  background: var(--sunken);
}
.shell__school {
  margin: 0 0 2px;
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.shell__school b {
  color: var(--text-1);
}
.shell__cli {
  margin: 0;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.shell__me {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-2) 0;
  border-top: var(--border-thin) solid var(--line-1);
}
.shell__avatar {
  display: grid;
  place-items: center;
  flex: none;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-full);
  background: var(--brand-tint);
  color: var(--brand);
  font-weight: var(--font-weight-bold);
}
.shell__logout {
  display: grid;
  place-items: center;
  margin-left: auto;
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: var(--radius-md);
  background: none;
  color: var(--text-3);
  cursor: pointer;
  transition:
    background-color 180ms ease,
    color 180ms ease;
}
.shell__logout:hover {
  background: var(--nav-hover);
  color: var(--text-1);
}
.shell__logout:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 1px;
}
.shell__idle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  margin-top: var(--space-2);
  padding: 0 var(--space-2);
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.shell__idle b {
  color: var(--text-2);
}
.shell__idle--warn b {
  color: var(--danger);
}
.shell__warn {
  margin: 0;
}
.shell__logout svg {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}
</style>
