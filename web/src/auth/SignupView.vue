<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import AuthShell from './AuthShell.vue'
import StepList from './StepList.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import { authApi } from '@/api/auth'
import { ApiError } from '@/api/client'
import { useCooldown } from '@/lib/useCooldown'

const STEPS = ['메일로 링크를 보냅니다', '링크를 열어 이름·학번·비밀번호', '관리자 승인 뒤 로그인']
const email = ref('')
const sentTo = ref('')
const emailError = ref('')
const error = ref('')
const submitting = ref(false)
const resend = useCooldown()
const { active: locked, start: lock } = useCooldown()

async function send() {
  if (submitting.value || locked.value) return
  emailError.value = ''
  error.value = ''
  submitting.value = true
  const to = email.value.trim()
  try {
    await authApi.signup(to) // 이미 가입이어도 202 — 결과를 가려 말하지 않는다
    sentTo.value = to
    resend.start(60)
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 422) emailError.value = '메일 주소 형식이 올바르지 않습니다'
    else if (e.status === 400) emailError.value = '학교 웹메일로만 가입할 수 있어요'
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
  <AuthShell title="가입 신청" surface="student" back="/login">
    <template v-if="!sentTo">
      <form class="auth-form" novalidate @submit.prevent="send">
        <Input
          v-model="email"
          label="학교 웹메일"
          type="email"
          autocomplete="email"
          placeholder="20231234@mjc.ac.kr"
          :error="emailError"
          required
        />
        <StepList :steps="STEPS" :current="0" />
        <p v-if="error" class="auth-form__error" role="alert">{{ error }}</p>
        <Button type="submit" :loading="submitting" :disabled="locked">인증 메일 받기</Button>
        <p class="auth-form__note">링크는 5분 안에 열어주세요</p>
      </form>
    </template>
    <template v-else>
      <div class="auth-form">
        <p>
          <strong>{{ sentTo }} 로 보냈어요</strong>
        </p>
        <StepList :steps="STEPS" :current="1" />
        <p class="auth-form__note">
          메일이 안 오면 60초 뒤 다시 보낼 수 있어요<span v-if="resend.active.value" class="num">
            ({{ resend.remaining.value }}초)</span
          >
        </p>
        <p v-if="error" class="auth-form__error" role="alert">{{ error }}</p>
        <Button
          variant="secondary"
          :loading="submitting"
          :disabled="resend.active.value || locked"
          @click="send"
          >다시 보내기</Button
        >
        <p class="auth-form__note">
          이미 가입한 메일이면 메일이 오지 않습니다. 로그인해 보세요.
          <RouterLink to="/login">로그인</RouterLink>
        </p>
      </div>
    </template>
  </AuthShell>
</template>
