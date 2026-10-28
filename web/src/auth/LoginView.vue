<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AuthShell from './AuthShell.vue'
import Banner from '@/components/ui/Banner.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import { authApi } from '@/api/auth'
import { ApiError } from '@/api/client'
import type { Role } from '@/api/types'
import { authNotice, handOffSession, setSession } from '@/lib/session'
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

// 비밀번호가 맞았을 때만 보이는 문구라 계정 존재를 새지 않는다. 고칠 곳(탭)이 바로 위라 탭을 가리킨다 (auth.md 「역할 확인」)
const ROLE_MISMATCH = {
  admin: "학생 계정입니다. 위의 '학생'을 골라 로그인하세요.",
  student: "관리자 계정입니다. 위의 '관리자'를 골라 로그인하세요.",
} as const
// 학생|관리자 탭은 같은 화면에서 바뀐다 — 누를 때마다 주소·페이지를 바꾸지 않는다(2026-10-28 wj 결정, auth.md 갱신 요청).
// 처음엔 이 앱의 역할. 다른 역할로 로그인하면 그 앱의 세션 칸에 넣고 그 앱으로 넘어간다
const TABS = [
  { value: 'student', label: '학생' },
  { value: 'admin', label: '관리자' },
]
const role = ref<Role>(props.app)
function pickRole(r: string) {
  role.value = r as Role
  error.value = '' // 앞 탭의 '…계정입니다' 가 남으면 고른 탭과 어긋난다
}

async function submit() {
  if (submitting.value || locked.value) return
  error.value = ''
  emailError.value = ''
  pending.value = false
  notice.value = null
  submitting.value = true
  try {
    const out = await authApi.login(email.value.trim(), password.value)
    if (out.role !== role.value) {
      error.value = ROLE_MISMATCH[role.value] // 토큰은 저장하지 않고 버린다
      return
    }
    if (out.role !== props.app) {
      // 다른 앱(같은 주소의 /admin 또는 /)이 할 일 — ?next= 는 이 앱 주소라 옮기지 않는다
      handOffSession(out)
      window.location.assign(out.role === 'admin' ? '/admin/' : '/')
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
  <!-- 관리자 로그인도 같은 틀·같은 제목·student 치수 — 탭만 바뀐 한 화면처럼 (auth.md 「관리자 로그인」) -->
  <AuthShell title="로그인" surface="student" home>
    <template #tabs>
      <SegmentedControl :items="TABS" :value="role" label="로그인 역할" @update:value="pickRole" />
    </template>
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
        :label="role === 'admin' ? '이메일' : '학교 웹메일'"
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
    <!-- 관리자 탭은 하단 링크가 없다 — 가입은 CLI 뿐이고 비밀번호 찾기도 두지 않는다(2026-10-28 wj 결정, auth.md 갱신 요청).
         줄 자체는 남긴다(빈 48px) — 넓은 폭은 폼을 세로 가운데에 둬서 줄이 사라지면 탭을 바꿀 때 폼이 움직인다.
         관리자 앱에는 /signup·/forgot 이 없어 학생 앱 주소로 페이지를 연다 -->
    <template #footer>
      <template v-if="role === 'student'">
        <a v-if="app === 'admin'" href="/signup">가입 신청</a>
        <RouterLink v-else to="/signup">가입 신청</RouterLink>
        <span aria-hidden="true">·</span>
        <a v-if="app === 'admin'" href="/forgot">비밀번호를 잊었어요</a>
        <RouterLink v-else to="/forgot">비밀번호를 잊었어요</RouterLink>
      </template>
    </template>
  </AuthShell>
</template>
