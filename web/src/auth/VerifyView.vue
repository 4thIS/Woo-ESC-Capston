<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import AuthShell from './AuthShell.vue'
import StepList from './StepList.vue'
import Banner from '@/components/ui/Banner.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import { authApi } from '@/api/auth'
import { ApiError } from '@/api/client'
import { useCooldown } from '@/lib/useCooldown'
import { readFragmentToken } from './fragment'

const STEPS = ['메일로 링크를 보냅니다', '링크를 열어 이름·학번·비밀번호', '관리자 승인 뒤 로그인']
const STUDENT_NO = /^[0-9A-Za-z-]+$/ // 서버 VerifyIn 과 같은 규칙 (S4a §3.4)
const router = useRouter()
const token = readFragmentToken()
type State = 'opening' | 'form' | 'invalid' | 'done'
const state = ref<State>(token ? 'opening' : 'invalid')
const email = ref('')
const name = ref('')
const studentNo = ref('')
const password = ref('')
const errs = ref<{ name?: string; studentNo?: string; password?: string }>({})
const error = ref('')
const submitting = ref(false)
const { active: locked, start: lock } = useCooldown()

async function open() {
  if (!token) return
  error.value = ''
  state.value = 'opening'
  try {
    // 토큰을 쓰지 않고 확인 + 입력 시간 30분 연장 — 다 채운 뒤에 만료를 알면 처음부터 다시다
    email.value = (await authApi.verifyOpen(token)).email
    state.value = 'form'
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 400) state.value = 'invalid'
    else error.value = e.message // 네트워크·503 — 다시 열기 버튼
  }
}
onMounted(open)

function validate(): boolean {
  const e: typeof errs.value = {}
  if (!name.value.trim()) e.name = '이름을 입력해 주세요'
  if (!STUDENT_NO.test(studentNo.value.trim()))
    e.studentNo = '학번은 영문·숫자·하이픈만 쓸 수 있어요'
  if (password.value.length < 8) e.password = '8자 이상 입력해 주세요'
  errs.value = e
  return Object.keys(e).length === 0
}

async function submit() {
  if (submitting.value || locked.value || !token || !validate()) return
  error.value = ''
  submitting.value = true
  try {
    await authApi.verify({
      token,
      name: name.value.trim(),
      student_no: studentNo.value.trim(),
      password: password.value,
    })
    state.value = 'done'
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    // 409 는 토큰을 쓰지 않는다 — 학번만 고쳐 다시 낸다 (auth.md)
    if (e.status === 409) errs.value = { studentNo: '이미 등록된 학번입니다' }
    else if (e.status === 400) state.value = 'invalid'
    else if (e.status === 422)
      errs.value = {
        name: e.fields.includes('name') ? '이름을 확인해 주세요' : undefined,
        studentNo: e.fields.includes('student_no')
          ? '학번은 영문·숫자·하이픈만 쓸 수 있어요'
          : undefined,
        password: e.fields.includes('password') ? '8자 이상 입력해 주세요' : undefined,
      }
    else if (e.status === 429) {
      error.value = '잠시 후 다시 시도해 주세요'
      lock(10)
    } else error.value = e.message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthShell :title="state === 'done' ? '가입 신청 완료' : '가입 완료'" surface="student">
    <template #banner>
      <Banner
        v-if="error && state === 'opening'"
        tone="danger"
        :message="error"
        :dismissible="false"
      />
    </template>

    <template v-if="state === 'opening'">
      <Skeleton :rows="3" />
      <Button v-if="error" variant="secondary" @click="open">다시 열기</Button>
    </template>

    <template v-else-if="state === 'invalid'">
      <p class="auth-form__error" role="alert">링크가 만료되었거나 잘못되었습니다</p>
      <Button @click="router.push('/signup')">가입 신청 다시 하기</Button>
    </template>

    <template v-else-if="state === 'form'">
      <p class="verify__email">{{ email }}</p>
      <StepList :steps="STEPS" :current="1" />
      <form class="auth-form" novalidate @submit.prevent="submit">
        <Input v-model="name" label="이름" autocomplete="name" :error="errs.name" required />
        <Input
          v-model="studentNo"
          label="학번"
          inputmode="text"
          autocomplete="off"
          :error="errs.studentNo"
          required
        />
        <Input
          v-model="password"
          label="비밀번호"
          type="password"
          autocomplete="new-password"
          hint="8자 이상"
          :error="errs.password"
          required
        />
        <p v-if="error" class="auth-form__error" role="alert">{{ error }}</p>
        <Button type="submit" :loading="submitting" :disabled="locked">가입 신청</Button>
      </form>
    </template>

    <template v-else>
      <StepList :steps="STEPS" :current="2" />
      <p><strong>승인을 기다리는 중입니다</strong></p>
      <p class="auth-form__note">
        관리자가 승인해야 로그인할 수 있어요. 승인되면 메일로 알려 드려요.
      </p>
      <RouterLink to="/login">로그인 화면으로</RouterLink>
    </template>
  </AuthShell>
</template>

<style scoped>
.verify__email {
  margin: 0;
  font-weight: var(--font-weight-bold);
  word-break: break-all;
}
</style>
