<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AuthShell from './AuthShell.vue'
import Banner from '@/components/ui/Banner.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import { authApi } from '@/api/auth'
import { ApiError } from '@/api/client'
import { authNotice, setSession } from '@/lib/session'
import { useCooldown } from '@/lib/useCooldown'
import { safeNext } from './next'

const props = defineProps<{ app: 'admin' | 'student' }>()
const route = useRoute()
const router = useRouter()

const email = ref('')
const password = ref('')
const error = ref('')
const emailError = ref('')
const pending = ref(false)
const submitting = ref(false)
const notice = ref(authNotice.value) // 401·403 으로 쫓겨 온 이유 — 한 번 보이고 지운다
authNotice.value = null
const { active: locked, start: lock } = useCooldown()

// 비밀번호가 맞았을 때만 보이는 문구라 계정 존재를 새지 않는다 (auth.md 「역할 확인」)
const ROLE_MISMATCH = {
  admin: '관리자 계정이 아닙니다. 학생은 학생 웹에서 로그인하세요.',
  student: '관리자 계정입니다. 관리자 웹에서 로그인하세요.',
} as const

async function submit() {
  if (submitting.value || locked.value) return
  error.value = ''
  emailError.value = ''
  pending.value = false
  notice.value = null
  submitting.value = true
  try {
    const out = await authApi.login(email.value.trim(), password.value)
    if (out.role !== props.app) {
      error.value = ROLE_MISMATCH[props.app] // 토큰은 저장하지 않고 버린다
      return
    }
    setSession(out)
    await router.replace(safeNext(route.query.next, '/'))
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 401) error.value = '이메일 또는 비밀번호가 틀립니다'
    else if (e.status === 403) pending.value = true
    else if (e.status === 422) emailError.value = '메일 주소 형식이 올바르지 않습니다'
    else if (e.status === 429) {
      error.value = '잠시 후 다시 시도해 주세요'
      lock(10) // 서버가 남은 시간을 주지 않는다 (spec §4.1)
    } else error.value = e.message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthShell :title="app === 'admin' ? '관리자 로그인' : '로그인'" :surface="app">
    <template #banner>
      <Banner v-if="notice === 'expired'" message="다시 로그인해 주세요." :dismissible="false" />
      <Banner
        v-else-if="notice === 'idle'"
        message="10분 동안 활동이 없어 자동으로 로그아웃했습니다."
        :dismissible="false"
      />
      <Banner
        v-else-if="notice === 'forbidden'"
        tone="danger"
        message="이 화면을 쓸 권한이 없습니다."
        :dismissible="false"
      />
      <!-- 403 승인 대기는 적색이 아니다 — 학생이 뭘 잘못한 게 아니다 -->
      <Banner
        v-if="pending"
        message="아직 승인되지 않았어요. 관리자 승인 뒤 로그인할 수 있어요."
        :dismissible="false"
      />
    </template>
    <form class="auth-form" novalidate @submit.prevent="submit">
      <Input
        v-model="email"
        :label="app === 'admin' ? '이메일' : '학교 웹메일'"
        type="email"
        autocomplete="username"
        :error="emailError"
        required
      />
      <Input
        v-model="password"
        label="비밀번호"
        type="password"
        autocomplete="current-password"
        required
      />
      <p v-if="error" class="auth-form__error" role="alert">{{ error }}</p>
      <Button type="submit" :loading="submitting" :disabled="locked">로그인</Button>
    </form>
    <template #footer>
      <template v-if="app === 'student'">
        <RouterLink to="/signup">가입 신청</RouterLink>
        <span aria-hidden="true">·</span>
        <RouterLink to="/forgot">비밀번호를 잊었어요</RouterLink>
      </template>
      <!-- 관리자 재설정도 학생 앱 /forgot·/reset (#46 auth.md). ponytail: 같은 오리진 전제 — 배포에서 도메인을 나누면(#44 뒤) STUDENT_WEB_URL 로 -->
      <a v-else href="/forgot">비밀번호를 잊었어요</a>
    </template>
  </AuthShell>
</template>
