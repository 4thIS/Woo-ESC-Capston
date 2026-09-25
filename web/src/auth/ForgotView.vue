<script setup lang="ts">
import { ref } from 'vue'
import AuthShell from './AuthShell.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import { authApi } from '@/api/auth'
import { ApiError } from '@/api/client'
import { useCooldown } from '@/lib/useCooldown'

const email = ref('')
const sent = ref(false)
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
  try {
    await authApi.forgot(email.value.trim()) // 없는 메일·대기 계정도 202 — 결과는 하나뿐
    sent.value = true
    resend.start(60)
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 422) emailError.value = '메일 주소 형식이 올바르지 않습니다'
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
  <AuthShell title="비밀번호 재설정" surface="student" back="/login">
    <form v-if="!sent" class="auth-form" novalidate @submit.prevent="send">
      <Input
        v-model="email"
        label="학교 웹메일"
        type="email"
        autocomplete="email"
        :error="emailError"
        required
      />
      <p v-if="error" class="auth-form__error" role="alert">{{ error }}</p>
      <Button type="submit" :loading="submitting" :disabled="locked">재설정 메일 받기</Button>
      <p class="auth-form__note">링크는 5분 안에 열어주세요</p>
    </form>
    <div v-else class="auth-form">
      <p><strong>보냈어요</strong></p>
      <!-- "가입된 메일이면" 을 꼭 적는다 — 없으면 오타 낸 사람이 영원히 기다린다 (auth.md) -->
      <p class="auth-form__note">
        가입된 메일이면 재설정 링크가 갑니다. 안 오면 60초 뒤 다시 보낼 수 있어요<span
          v-if="resend.active.value"
          class="num"
        >
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
    </div>
  </AuthShell>
</template>
