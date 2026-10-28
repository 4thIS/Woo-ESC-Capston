<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import AuthShell from './AuthShell.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import { authApi } from '@/api/auth'
import { ApiError } from '@/api/client'
import { useCooldown } from '@/lib/useCooldown'
import { readFragmentToken } from './fragment'

// 입력 시간 연장이 없다 (비밀번호 하나라 5분이면 충분 — S4a). 만료되면 /forgot 으로 되돌린다
const token = readFragmentToken()
const state = ref<'form' | 'invalid' | 'done'>(token ? 'form' : 'invalid')
const password = ref('')
const pwError = ref('')
const error = ref('')
const submitting = ref(false)
const { active: locked, start: lock } = useCooldown()

async function submit() {
  if (submitting.value || locked.value || !token) return
  pwError.value = password.value.length < 8 ? '8자 이상 입력해 주세요' : ''
  if (pwError.value) return
  error.value = ''
  submitting.value = true
  try {
    await authApi.reset(token, password.value)
    state.value = 'done'
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 400) state.value = 'invalid'
    else if (e.status === 422) pwError.value = '8자 이상 입력해 주세요'
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
  <AuthShell title="새 비밀번호" surface="student">
    <form v-if="state === 'form'" class="auth-form" novalidate @submit.prevent="submit">
      <Input
        v-model="password"
        label="새 비밀번호"
        type="password"
        autocomplete="new-password"
        hint="8자 이상"
        :error="pwError"
        required
      />
      <p v-if="error" class="auth-form__error" role="alert">{{ error }}</p>
      <Button type="submit" :loading="submitting" :disabled="locked">비밀번호 바꾸기</Button>
    </form>
    <template v-else-if="state === 'invalid'">
      <p class="auth-form__error" role="alert">링크가 만료되었거나 잘못되었습니다</p>
      <RouterLink to="/forgot">비밀번호를 잊었어요</RouterLink>
    </template>
    <template v-else>
      <p><strong>비밀번호를 바꿨어요</strong></p>
      <p class="auth-form__note">다른 기기에서 로그인해 있던 곳은 모두 로그아웃됩니다.</p>
      <RouterLink to="/login">로그인하러 가기</RouterLink>
      <!-- 관리자 웹 주소를 링크로 걸지 않는다 — 학생 웹이 관리자 주소를 실을 이유가 없다 (auth.md) -->
      <p class="auth-form__note">관리자 계정이면 관리자 웹 주소에서 로그인하세요.</p>
    </template>
  </AuthShell>
</template>
