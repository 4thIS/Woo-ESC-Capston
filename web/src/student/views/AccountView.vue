<script setup lang="ts">
import { RouterLink, useRouter } from 'vue-router'
import Button from '@/components/ui/Button.vue'
import { clearSession, schoolTitle, session } from '@/lib/session'
import StudentHeader from '../StudentHeader.vue'

// 내 정보 (student-room.md 「학생 앱 메뉴 · 이용 안내」) — 로그인 응답에 있는 이름 · 학교만. 로그아웃은 여기 한 곳
const router = useRouter()
function logout() {
  clearSession()
  void router.replace('/login')
}
</script>

<template>
  <div class="ac">
    <StudentHeader title="내 정보" />
    <main class="ac__body">
      <section class="ac__card" aria-label="내 계정">
        <span class="ac__avatar" aria-hidden="true">{{ session?.name.slice(0, 1) || '나' }}</span>
        <p class="ac__who">
          <b class="ac__name">{{ session?.name }}</b>
          <span class="ac__school">{{ schoolTitle }}</span>
        </p>
      </section>
      <nav class="ac__links" aria-label="약관">
        <RouterLink to="/policies/terms">이용약관</RouterLink>
        <RouterLink to="/policies/privacy">개인정보 처리방침</RouterLink>
      </nav>
      <Button variant="secondary" class="ac__logout" @click="logout">로그아웃</Button>
    </main>
  </div>
</template>

<style scoped>
.ac__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  max-width: 640px;
  margin: 0 auto;
  padding: var(--space-4);
}
.ac__card {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.ac__avatar {
  display: grid;
  place-items: center;
  flex: none;
  width: 48px;
  height: 48px;
  border-radius: var(--radius-full);
  background: var(--brand-tint);
  color: var(--brand);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.ac__who {
  display: flex;
  flex-direction: column;
  margin: 0;
}
.ac__name {
  font-size: var(--font-size-lg);
}
.ac__school {
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
.ac__links {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.ac__links a {
  display: flex;
  align-items: center;
  min-height: 52px;
  padding: 0 var(--space-4);
  color: var(--text-1);
  text-decoration: none;
}
.ac__links a + a {
  border-top: var(--border-thin) solid var(--line-1);
}
.ac__links a:hover {
  background: var(--nav-hover);
}
</style>
