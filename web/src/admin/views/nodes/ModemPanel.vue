<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Input from '@/components/ui/Input.vue'
import Modal from '@/components/ui/Modal.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import { showToast } from '@/components/ui/toast'
import { loraApi } from '@/api/lora'
import { ApiError } from '@/api/client'
import type { ModemOut, TokenOut } from '@/api/types'
import { formatKst, relativeKo } from '@/lib/time'

defineProps<{ modems?: ModemOut[]; loading: boolean }>()
const emit = defineEmits<{ changed: [] }>()

// 서버 ModemIn 과 같은 규칙 — 소문자·숫자·하이픈, 1~32자
const MODEM_ID = /^[a-z0-9-]{1,32}$/
const FORMAT_MSG = '영문 소문자·숫자·하이픈만, 32자 이내로 적어 주세요.'
const registering = ref(false)
const modemId = ref('')
const serverError = ref('')
const submitting = ref(false)
const validId = computed(() => MODEM_ID.test(modemId.value))
const idError = computed(
  () => serverError.value || (modemId.value && !validId.value ? FORMAT_MSG : ''),
)
watch(modemId, () => (serverError.value = ''))

function openRegister() {
  modemId.value = ''
  serverError.value = ''
  registering.value = true
}
defineExpose({ openRegister })

// 토큰은 이 Modal 에서 한 번만 보인다 — 서버가 다시 알려주지 않는다
const issued = ref<TokenOut | null>(null)

async function submitRegister() {
  if (!validId.value || submitting.value) return
  submitting.value = true
  try {
    issued.value = await loraApi.registerModem(modemId.value)
    registering.value = false
    emit('changed')
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    // 서버: 같은 ID 가 있으면 400(lora_service ValidationError), 형식이 틀리면 422
    if (e.status === 400) serverError.value = '이미 등록된 모뎀Pi ID입니다.'
    else if (e.status === 422) serverError.value = FORMAT_MSG
    else if (e.status !== 401 && e.status !== 403) showToast({ tone: 'danger', message: e.message })
  } finally {
    submitting.value = false
  }
}

// 재발급 — 기존 토큰이 즉시 무효 → 그 모뎀Pi 가 끊긴다. 확인 Modal 안에서만
const rotating = ref<string | null>(null)
const rotatingBusy = ref(false)
async function submitRotate() {
  const id = rotating.value
  if (!id || rotatingBusy.value) return
  rotatingBusy.value = true
  try {
    issued.value = await loraApi.rotateToken(id)
    rotating.value = null
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 404) {
      rotating.value = null
      showToast({ message: '이미 삭제된 모뎀Pi입니다. 목록을 새로 불러옵니다.' })
      emit('changed')
    } else if (e.status !== 401 && e.status !== 403)
      showToast({ tone: 'danger', message: e.message })
  } finally {
    rotatingBusy.value = false
  }
}

async function copy() {
  try {
    await navigator.clipboard.writeText(issued.value!.token)
    showToast({ message: '복사했습니다.' })
  } catch {
    // 권한 거부·비보안 컨텍스트(http) — 토큰은 user-select: all 이라 한 번 클릭으로 선택된다
    showToast({ message: '복사하지 못했습니다. 토큰을 직접 선택해 복사해 주세요.' })
  }
}
</script>

<template>
  <section class="block" aria-labelledby="nodes-modem">
    <h2 id="nodes-modem" class="block__title">모뎀Pi</h2>
    <div v-if="loading && !modems" class="modems">
      <Skeleton v-for="i in 2" :key="i" variant="block" width="260px" />
    </div>
    <EmptyState
      v-else-if="modems && modems.length === 0"
      message="등록된 모뎀Pi가 없습니다"
      :actions="[{ label: '모뎀Pi 등록', variant: 'primary', onClick: openRegister }]"
    />
    <ul v-else-if="modems" class="modems">
      <li v-for="md in modems" :key="md.modem_id" class="modem">
        <p class="modem__id">{{ md.modem_id }}</p>
        <p class="modem__meta num">
          agent {{ md.agent_ver ?? '—' }} ·
          <span v-if="md.last_seen_at" :title="formatKst(md.last_seen_at)">{{
            relativeKo(md.last_seen_at)
          }}</span>
          <template v-else>접속 기록 없음</template>
        </p>
        <div class="modem__foot">
          <Badge v-if="md.connected" variant="solid">연결됨</Badge>
          <Badge v-else variant="outline" tone="danger">끊김</Badge>
          <Button variant="ghost" size="sm" @click="rotating = md.modem_id">토큰 재발급</Button>
        </div>
      </li>
    </ul>

    <Modal
      :open="registering"
      title="모뎀Pi 등록"
      size="sm"
      :close-on-backdrop="!modemId"
      @close="registering = false"
    >
      <form @submit.prevent="submitRegister">
        <Input
          v-model="modemId"
          label="모뎀Pi ID"
          hint="예: gonghak-01 — 모뎀Pi 설정의 modem_id 와 같아야 합니다"
          :error="idError || undefined"
          required
        />
      </form>
      <template #footer>
        <Button variant="secondary" @click="registering = false">취소</Button>
        <Button :loading="submitting" :disabled="!validId" @click="submitRegister">등록</Button>
      </template>
    </Modal>

    <Modal :open="!!rotating" title="토큰 재발급" size="sm" @close="rotating = null">
      <p class="block__text">
        {{ rotating }} 의 기존 토큰이 즉시 무효가 되어 이 모뎀Pi가 끊깁니다. 새 토큰을 모뎀Pi 설정에
        넣어야 다시 연결됩니다.
      </p>
      <template #footer>
        <Button variant="secondary" @click="rotating = null">취소</Button>
        <Button variant="danger" :loading="rotatingBusy" @click="submitRotate">재발급</Button>
      </template>
    </Modal>

    <!-- 배경 클릭·Esc 로 닫히지 않는다 (closeOnBackdrop=false 는 Esc 도 막는다) — 토큰은 다시 볼 수 없다 -->
    <Modal :open="!!issued" title="모뎀Pi 토큰" :close-on-backdrop="false" @close="issued = null">
      <p class="block__text">{{ issued?.modem_id }} 의 토큰입니다. 모뎀Pi 설정에 넣으세요.</p>
      <code class="token">{{ issued?.token }}</code>
      <p class="token__warn">이 창을 닫으면 다시 볼 수 없습니다.</p>
      <template #footer>
        <Button variant="secondary" @click="copy">복사</Button>
        <Button @click="issued = null">닫기</Button>
      </template>
    </Modal>
  </section>
</template>

<style scoped>
.block__title {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.block__text {
  margin: 0 0 var(--space-3);
}
.modems {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  margin: 0;
  padding: 0;
  list-style: none;
}
.modem {
  width: 260px;
  padding: var(--space-4);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-md);
}
.modem p {
  margin: 0;
}
.modem__id {
  font-weight: var(--font-weight-bold);
}
.modem__meta {
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
.modem__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: var(--space-3);
}
.token {
  display: block;
  padding: var(--space-3);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-sm);
  background: var(--sunken);
  font-size: var(--font-size-lg);
  word-break: break-all;
  user-select: all;
}
.token__warn {
  margin: var(--space-3) 0 0;
  color: var(--danger);
  font-weight: var(--font-weight-bold);
}
</style>
