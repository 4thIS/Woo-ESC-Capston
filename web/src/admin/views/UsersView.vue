<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Input from '@/components/ui/Input.vue'
import Modal from '@/components/ui/Modal.vue'
import Select from '@/components/ui/Select.vue'
import Table from '@/components/ui/Table.vue'
import Textarea from '@/components/ui/Textarea.vue'
import { showToast } from '@/components/ui/toast'
import { usersApi } from '@/api/users'
import { ApiError } from '@/api/client'
import type { UserOut, UserStatus } from '@/api/types'
import { useResource } from '@/lib/useResource'
import { formatKst, relativeKo } from '@/lib/time'
import { refreshPending } from '../pending'
import { FILTERS, STATUS_BADGE, matchUser, sortUsers } from '../usersView'

const status = ref<UserStatus | ''>('pending_approval')
const q = ref('')
const { data, error, loading, reload } = useResource(
  () => usersApi.list(status.value || undefined),
  {
    deps: status,
  },
)
const rows = computed(() => sortUsers((data.value ?? []).filter((x) => matchUser(x, q.value))))
const pendingHere = computed(
  () => (data.value ?? []).filter((x) => x.status === 'pending_approval').length,
)

const COLUMNS = [
  { key: 'name', label: '이름', width: '96px' },
  { key: 'student_no', label: '학번', width: '104px' },
  { key: 'email', label: '웹메일' },
  { key: 'role', label: '역할', width: '72px' },
  { key: 'status', label: '상태', width: '88px' },
  { key: 'created_at', label: '신청', width: '96px' },
  { key: 'approved_at', label: '승인', width: '96px' },
  { key: 'actions', label: '작업', width: '136px' },
]

const emptyMessage = computed(() => {
  if (q.value.trim()) return '검색 결과가 없습니다'
  if (status.value === 'pending_approval') return '승인을 기다리는 신청이 없습니다' // 평소 상태 — 버튼 없음
  if (status.value === '')
    return '아직 가입한 회원이 없습니다. 학생 웹 주소에서 가입 신청을 받습니다.'
  return '해당하는 회원이 없습니다'
})

// 목록 오류 — 401·403 은 client 가 로그인으로 보낸다
watch(error, (e) => {
  if (e && e.status !== 401 && e.status !== 403)
    showToast({ tone: 'danger', message: e.message, action: { label: '재시도', onClick: reload } })
})

type Kind = 'approve' | 'reject' | 'disable' | 'enable'
const OK: Record<Kind, string> = {
  // 메일은 응답을 기다리지 않는다 — 발송을 보장하는 문구로 쓰지 않는다
  approve: '승인했습니다. 학생에게 메일이 갑니다.',
  reject: '거절했습니다. 학생에게 메일이 갑니다.',
  disable: '정지했습니다.',
  enable: '해제했습니다.',
}
const CHANGED: Record<Kind, string> = {
  approve: '이미 처리된 신청입니다',
  reject: '이미 처리된 신청입니다',
  disable: '상태가 이미 바뀌었습니다. 목록을 새로 불러옵니다.',
  enable: '상태가 이미 바뀌었습니다. 목록을 새로 불러옵니다.',
}
const busy = ref<string | null>(null) // 처리 중인 행 — 연타 방지

// retry: Toast 재시도 — 기본은 같은 회원·같은 호출을 다시 (submit* 이 Modal 경로를 넘긴다)
async function act(
  user: UserOut,
  kind: Kind,
  call: () => Promise<unknown>,
  retry: () => unknown = () => act(user, kind, call),
): Promise<boolean> {
  if (busy.value) return false
  busy.value = user.email
  try {
    await call()
    showToast({ message: OK[kind] })
    return true
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 409 || e.status === 404) showToast({ message: CHANGED[kind] })
    else if (e.status !== 401 && e.status !== 403)
      showToast({
        tone: 'danger',
        message: e.message,
        action: { label: '재시도', onClick: () => void retry() },
      })
    return e.status === 409 || e.status === 404 // 모달은 닫는다 — 대상이 이미 바뀌었다
  } finally {
    // 새 목록이 올 때까지 잠가 둔다 — 옛 행을 또 누르면 409 만 는다
    try {
      await Promise.all([reload(), refreshPending()])
    } finally {
      busy.value = null
    }
  }
}

// 거절 — 사유가 학생에게 메일로 그대로 간다 (Modal 필수)
const rejecting = ref<UserOut | null>(null)
const reason = ref('')
function openReject(user: UserOut) {
  reason.value = ''
  rejecting.value = user
}
async function submitReject() {
  const user = rejecting.value
  const r = reason.value.trim()
  if (!user || !r) return
  const call = () => usersApi.reject(user.email, r)
  // 재시도는 실패한 그 회원만 — 그 사람 Modal 이 아직 열려 있으면 거기서(고친 사유로, 성공 시 닫힘),
  // 아니면 그때의 사유로 조용히. 다른 회원의 열린 Modal 을 건드리지 않는다
  const retry = () =>
    rejecting.value?.email === user.email ? submitReject() : act(user, 'reject', call)
  if (await act(user, 'reject', call, retry)) rejecting.value = null
}

// 정지 — token_version 이 올라 그 사람의 세션이 즉시 끊긴다
const disabling = ref<UserOut | null>(null)
async function submitDisable() {
  const user = disabling.value
  if (!user) return
  const call = () => usersApi.disable(user.email)
  const retry = () =>
    disabling.value?.email === user.email ? submitDisable() : act(user, 'disable', call)
  if (await act(user, 'disable', call, retry)) disabling.value = null
}

// 필터를 바꿔 옛 행이 남아 있는 동안에도 잠근다
const locked = computed(() => !!busy.value || loading.value)
const asUser = (row: Record<string, unknown>) => row as unknown as UserOut
</script>

<template>
  <main class="users">
    <header class="users__head">
      <h1 class="users__title">회원</h1>
      <Badge v-if="status === 'pending_approval'" variant="solid" size="sm" class="num"
        >승인 대기 {{ pendingHere }}</Badge
      >
      <Select v-model="status" :options="FILTERS" size="sm" class="users__filter" />
      <!-- Input 은 attrs 를 <input> 에 내린다 — 오른쪽 정렬은 감싼 div 로 -->
      <div class="users__search">
        <Input v-model="q" size="sm" placeholder="이름·학번·메일 검색" aria-label="회원 검색" />
      </div>
    </header>

    <Table
      :columns="COLUMNS"
      :rows="rows as unknown as Record<string, unknown>[]"
      row-key="email"
      :loading="loading && !data"
    >
      <template #empty>
        <EmptyState :message="emptyMessage" />
      </template>
      <template #cell-student_no="{ row }">{{ asUser(row).student_no ?? '—' }}</template>
      <template #cell-role="{ row }">
        <Badge variant="outline">{{ asUser(row).role === 'admin' ? '관리자' : '학생' }}</Badge>
      </template>
      <template #cell-status="{ row }">
        <Badge
          :tone="STATUS_BADGE[asUser(row).status].tone"
          :variant="STATUS_BADGE[asUser(row).status].variant"
          >{{ STATUS_BADGE[asUser(row).status].label }}</Badge
        >
      </template>
      <template #cell-created_at="{ row }">
        <span v-if="asUser(row).role === 'admin'">—</span>
        <span v-else :title="formatKst(asUser(row).created_at)">{{
          relativeKo(asUser(row).created_at)
        }}</span>
      </template>
      <template #cell-approved_at="{ row }">
        <span v-if="asUser(row).approved_at" :title="formatKst(asUser(row).approved_at!)">{{
          relativeKo(asUser(row).approved_at!)
        }}</span>
        <span v-else>—</span>
      </template>
      <template #cell-actions="{ row }">
        <span v-if="asUser(row).role === 'admin'" class="users__cli">CLI 에서만 변경</span>
        <div v-else class="users__actions">
          <template v-if="asUser(row).status === 'pending_approval'">
            <Button
              size="sm"
              :loading="busy === asUser(row).email"
              :disabled="locked && busy !== asUser(row).email"
              @click="act(asUser(row), 'approve', () => usersApi.approve(asUser(row).email))"
              >승인</Button
            >
            <Button variant="ghost" size="sm" :disabled="locked" @click="openReject(asUser(row))"
              >거절</Button
            >
          </template>
          <Button
            v-else-if="asUser(row).status === 'active'"
            variant="ghost"
            size="sm"
            :disabled="locked"
            @click="disabling = asUser(row)"
            >정지</Button
          >
          <Button
            v-else-if="asUser(row).status === 'disabled'"
            variant="ghost"
            size="sm"
            :loading="busy === asUser(row).email"
            :disabled="locked && busy !== asUser(row).email"
            @click="act(asUser(row), 'enable', () => usersApi.enable(asUser(row).email))"
            >해제</Button
          >
        </div>
      </template>
    </Table>

    <Modal
      :open="!!rejecting"
      title="가입 신청 거절"
      size="sm"
      :close-on-backdrop="!reason"
      @close="rejecting = null"
    >
      <p class="users__modal-text">
        {{ rejecting?.name }} ({{ rejecting?.email }}) 의 신청을 거절합니다. 사유는 학생에게 메일로
        그대로 갑니다.
      </p>
      <Textarea
        v-model="reason"
        label="거절 사유"
        placeholder="학번이 잘못되었습니다"
        maxlength="200"
        rows="3"
        required
      />
      <template #footer>
        <Button variant="secondary" @click="rejecting = null">취소</Button>
        <Button
          variant="danger"
          :loading="busy === rejecting?.email"
          :disabled="!reason.trim()"
          @click="submitReject"
          >거절</Button
        >
      </template>
    </Modal>

    <Modal :open="!!disabling" title="회원 정지" size="sm" @close="disabling = null">
      <p class="users__modal-text">
        {{ disabling?.name }} ({{ disabling?.email }}) 을 정지합니다. 이 사람의 로그인이 즉시
        끊깁니다.
      </p>
      <template #footer>
        <Button variant="secondary" @click="disabling = null">취소</Button>
        <Button variant="danger" :loading="busy === disabling?.email" @click="submitDisable"
          >정지</Button
        >
      </template>
    </Modal>
  </main>
</template>

<style scoped>
.users {
  padding: var(--space-5);
}
.users__head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}
.users__title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
}
.users__search {
  width: 220px;
  margin-left: auto;
}
.users__actions {
  display: flex;
  gap: var(--space-1);
}
.users__cli {
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.users__modal-text {
  margin: 0 0 var(--space-4);
}
</style>
