<script setup lang="ts">
import { computed, ref } from 'vue'
import Button from '@/components/ui/Button.vue'
import Modal from '@/components/ui/Modal.vue'
import Table from '@/components/ui/Table.vue'
import Textarea from '@/components/ui/Textarea.vue'
import { showToast } from '@/components/ui/toast'
import { DAYS, LATER_HINT, conflictMessage, resvWindow } from '@/components/domain/rules'
import { ApiError } from '@/api/client'
import { adminApi } from '@/api/admin'
import type { ResvAdminOut } from '@/api/types'
import { dayOfDate, formatHm, formatKst, hm, kstDateStr, md, relativeKo } from '@/lib/time'

const props = defineProps<{ pending?: ResvAdminOut[] }>()
const emit = defineEmits<{ changed: [] }>()

// 오래된 신청 먼저 — 먼저 온 것을 먼저 본다 (서버는 날짜순)
const rows = computed(() =>
  [...(props.pending ?? [])].sort(
    (a, b) => (a.requested_at?.getTime() ?? 0) - (b.requested_at?.getTime() ?? 0),
  ),
)
const COLUMNS = [
  { key: 'who', label: '신청자', width: '96px' },
  { key: 'room', label: '호수', width: '120px' },
  { key: 'date', label: '날짜', width: '96px' },
  { key: 'time', label: '시간', width: '112px' },
  { key: 'subject', label: '용도' },
  { key: 'requested_at', label: '신청 시각', width: '96px' },
  { key: 'actions', label: '작업', width: '136px', align: 'right' as const },
]
const asP = (row: Record<string, unknown>) => row as unknown as ResvAdminOut
/** 시작 시각이 지난 신청은 서버가 승인을 409 로 막는다 — 누르기 전에 잠근다 (거절은 된다). KST 문자열 비교 */
const started = (r: ResvAdminOut, now = new Date()) =>
  `${r.date} ${hm(r.s_h, r.s_m)}` <= `${kstDateStr(now)} ${formatHm(now)}`
const STARTED_HINT = '시작 시각이 지나 승인할 수 없습니다'

const busy = ref<number | null>(null)
/** 승인·거절 공통. 409·404 면 true(대상이 이미 바뀌었다 — 모달을 닫는다) */
async function act(r: ResvAdminOut, call: () => Promise<unknown>, ok: string): Promise<boolean> {
  if (busy.value !== null) return false
  busy.value = r.id
  try {
    await call()
    showToast({ message: ok })
    return true
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    // 두 관리자가 동시에 · 그사이 직접 예약이 겹침 · 이미 시작 · 용량 24 — 이유를 말하고 새로 부른다
    if (e.status === 409) showToast({ tone: 'danger', message: conflictMessage(e) })
    else if (e.status === 404) showToast({ tone: 'danger', message: '이미 처리된 신청입니다.' })
    else if (e.status !== 401 && e.status !== 403) showToast({ tone: 'danger', message: e.message })
    return e.status === 409 || e.status === 404
  } finally {
    busy.value = null
    emit('changed')
  }
}
function approve(r: ResvAdminOut) {
  const later = resvWindow(r.date, kstDateStr(new Date())) === 'later'
  void act(
    r,
    () => adminApi.approveResv(r.id),
    later ? `승인했습니다. ${LATER_HINT}.` : '승인했습니다. 문 앞 화면에 나갑니다.',
  )
}

// 거절 — 사유가 필수이고 학생에게 그대로 보인다
const rejecting = ref<ResvAdminOut | null>(null)
const reason = ref('')
function openReject(r: ResvAdminOut) {
  reason.value = ''
  rejecting.value = r
}
async function submitReject() {
  const r = rejecting.value
  const text = reason.value.trim()
  if (!r || !text) return
  if (
    await act(r, () => adminApi.rejectResv(r.id, text), '거절했습니다. 사유가 학생에게 보입니다.')
  )
    rejecting.value = null
}
</script>

<template>
  <!-- 0건이면 블록을 감춘다 — 평소 비어 있는 블록이 자리를 차지하면 다른 표를 밀어낸다 -->
  <section v-if="rows.length" class="blk" aria-labelledby="blk-pending">
    <header class="blk__head">
      <h2 id="blk-pending" class="blk__title">신청 대기</h2>
      <span class="blk__count num">{{ rows.length }}건</span>
    </header>
    <Table :columns="COLUMNS" :rows="rows as unknown as Record<string, unknown>[]">
      <template #cell-who="{ row }">
        <!-- 이름만 — 학번·메일은 툴팁 (목록을 넓히지 않으면서 본인 확인) -->
        <span
          :title="`${asP(row).requester?.student_no ?? '학번 없음'} · ${asP(row).requester?.email ?? ''}`"
          >{{ asP(row).requester?.name ?? '—' }}</span
        >
      </template>
      <template #cell-room="{ row }">{{ asP(row).building }} {{ asP(row).room }}</template>
      <template #cell-date="{ row }"
        ><span class="num"
          >{{ md(asP(row).date) }} ({{ DAYS[dayOfDate(asP(row).date) - 1] }})</span
        ></template
      >
      <template #cell-time="{ row }"
        ><span class="num"
          >{{ hm(asP(row).s_h, asP(row).s_m) }}–{{ hm(asP(row).e_h, asP(row).e_m) }}</span
        ></template
      >
      <template #cell-requested_at="{ row }">
        <span v-if="asP(row).requested_at" :title="formatKst(asP(row).requested_at!)">{{
          relativeKo(asP(row).requested_at!)
        }}</span>
        <span v-else>—</span>
      </template>
      <template #cell-actions="{ row }">
        <div class="blk__actions">
          <Button
            size="sm"
            :loading="busy === asP(row).id"
            :disabled="(busy !== null && busy !== asP(row).id) || started(asP(row))"
            :title="started(asP(row)) ? STARTED_HINT : undefined"
            @click="approve(asP(row))"
            >승인</Button
          >
          <Button variant="ghost" size="sm" :disabled="busy !== null" @click="openReject(asP(row))"
            >거절</Button
          >
        </div>
      </template>
    </Table>
    <Modal
      :open="!!rejecting"
      title="예약 신청 거절"
      size="sm"
      :close-on-backdrop="!reason"
      @close="rejecting = null"
    >
      <p class="blk__modal-text">
        {{ rejecting?.requester?.name }} 의 {{ rejecting?.building }} {{ rejecting?.room }}호
        {{ rejecting?.date }} 신청을 거절합니다. 사유는 학생에게 그대로 보입니다.
      </p>
      <Textarea
        v-model="reason"
        label="거절 사유"
        placeholder="같은 시간에 학과 행사가 있습니다"
        maxlength="200"
        rows="3"
        required
      />
      <template #footer>
        <Button variant="secondary" @click="rejecting = null">취소</Button>
        <Button
          variant="danger"
          :loading="busy === rejecting?.id"
          :disabled="!reason.trim()"
          @click="submitReject"
          >거절</Button
        >
      </template>
    </Modal>
  </section>
</template>

<style scoped>
.blk {
  overflow: hidden;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.blk__head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
}
.blk__title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.blk__count {
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.blk__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-1);
}
.blk__modal-text {
  margin: 0 0 var(--space-4);
}
</style>
