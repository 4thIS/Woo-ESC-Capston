<script setup lang="ts">
import { computed, ref, shallowRef } from 'vue'
import Button from '@/components/ui/Button.vue'
import Modal from '@/components/ui/Modal.vue'
import Table from '@/components/ui/Table.vue'
import { showToast } from '@/components/ui/toast'
import { ApiError } from '@/api/client'
import { IMPORT_MAX_BYTES, roomsApi } from '@/api/rooms'
import type { ImportErrors, ImportRowError, ImportSummary } from '@/api/types'

const emit = defineEmits<{ applied: [] }>()
const input = ref<HTMLInputElement>()
const name = ref('')
let bytes: ArrayBuffer | null = null
const preview = shallowRef<ImportSummary | null>(null)
const rowErrors = shallowRef<ImportRowError[] | null>(null)
const busy = ref(false)
const TOO_BIG = '1 MB 를 넘는 파일은 가져올 수 없습니다.'
// 보내는 중에는 새 파일을 받지 않는다 — 미리본 파일과 적용할 파일이 갈리지 않게
defineExpose({ pick: () => busy.value || input.value?.click(), busy })

async function onFile() {
  const el = input.value!
  const f = el.files?.[0]
  el.value = '' // 같은 파일을 고쳐 다시 올려도 change 가 나게
  if (!f || busy.value) return
  if (f.size > IMPORT_MAX_BYTES) {
    showToast({ tone: 'danger', message: TOO_BIG })
    return
  }
  name.value = f.name
  // 바이트 그대로 보낸다 — UTF-8 이 아니면 서버가 400 으로 알려 준다(화면에서 디코딩하면 깨진 채 들어간다)
  bytes = await f.arrayBuffer()
  await send(true)
}

/** 먼저 dry_run 으로 요약만 — 관리자가 보고 적용한다. 서버는 전체 검증 뒤 적용이라 부분 적용이 없다 */
async function send(dryRun: boolean) {
  if (!bytes || busy.value) return
  busy.value = true
  try {
    const r = await roomsApi.importSlots(bytes, dryRun)
    if (dryRun) {
      preview.value = r
      return
    }
    preview.value = null
    const skipped = r.skipped.length ? ` 웹에서 고친 ${r.skipped.length}행은 건너뛰었습니다.` : ''
    showToast({ message: `시간표를 가져왔습니다 — 강의실 ${r.rooms}곳에 보냅니다.${skipped}` })
    emit('applied')
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    preview.value = null
    const errs = (e.detail as Partial<ImportErrors> | null)?.errors
    if (e.status === 400 && errs) rowErrors.value = errs
    else if (e.status === 400)
      showToast({ tone: 'danger', message: 'CSV 를 UTF-8 로 저장해 주세요 (엑셀: CSV UTF-8).' })
    else if (e.status === 413) showToast({ tone: 'danger', message: TOO_BIG })
    else if (e.status === 500 && !dryRun) {
      // DB 는 반영됐고 FILE 큐잉만 실패 — 동기화로 다시 보낼 수 있다
      showToast({
        tone: 'danger',
        message: '시간표는 저장됐지만 전송 준비에 실패했습니다. 선택한 곳 동기화로 다시 보내세요.',
      })
      emit('applied')
    } else if (e.status !== 401 && e.status !== 403)
      showToast({ tone: 'danger', message: e.message })
  } finally {
    busy.value = false
  }
}

const changes = computed(() =>
  preview.value ? preview.value.added + preview.value.updated + preview.value.deleted : 0,
)
const SKIP_COLS = [
  { key: 'row', label: '행', width: '64px', align: 'right' as const },
  { key: 'reason', label: '사유' },
]
const ERR_COLS = [
  { key: 'row', label: '행', width: '64px', align: 'right' as const },
  { key: 'error', label: '사유' },
]
/** 행 0 은 파일 전체(헤더·노드 상한) 오류 — 칸에 — */
const rowsOf = (xs: { row: number }[]) =>
  xs.map((x, i) => ({ ...x, id: i, row: x.row || '—' })) as unknown as Record<string, unknown>[]
</script>

<template>
  <input
    ref="input"
    type="file"
    accept=".csv,text/csv"
    class="csv__file"
    aria-label="CSV 파일"
    @change="onFile"
  />
  <Modal
    :open="!!preview"
    :title="`CSV 가져오기 — ${name}`"
    size="lg"
    @close="busy || (preview = null)"
  >
    <template v-if="preview">
      <p class="csv__sum num">
        강의실 {{ preview.rooms }}곳 · 추가 {{ preview.added }} · 수정 {{ preview.updated }} · 삭제
        {{ preview.deleted }}
      </p>
      <p v-if="preview.deleted" class="csv__note">삭제는 파일에 없는 포털(CSV) 행입니다.</p>
      <p v-if="!changes" class="csv__note">바뀌는 것이 없습니다.</p>
      <template v-if="preview.skipped.length">
        <!-- source 보호 — 기능이지 버그가 아니다 (admin-rooms.md §1) -->
        <p class="csv__note">
          웹에서 고친 행(출처 수동·긴급)은 CSV 가 덮지 않습니다 — 아래
          {{ preview.skipped.length }}행은 건너뜁니다.
        </p>
        <Table :columns="SKIP_COLS" :rows="rowsOf(preview.skipped)" />
      </template>
    </template>
    <template #footer>
      <Button variant="secondary" :disabled="busy" @click="preview = null">취소</Button>
      <Button :loading="busy" :disabled="!changes" @click="send(false)">적용</Button>
    </template>
  </Modal>
  <Modal
    :open="!!rowErrors"
    title="CSV 오류 — 아무것도 적용되지 않았습니다"
    size="lg"
    @close="rowErrors = null"
  >
    <p class="csv__note">
      전체를 검사한 뒤에 적용하므로 일부만 들어가지 않았습니다. 고쳐서 다시 올리세요.
    </p>
    <Table :columns="ERR_COLS" :rows="rowsOf(rowErrors ?? [])" />
    <template #footer>
      <Button variant="secondary" @click="rowErrors = null">닫기</Button>
    </template>
  </Modal>
</template>

<style scoped>
.csv__file {
  display: none;
}
.csv__sum {
  margin: 0 0 var(--space-3);
  font-weight: var(--font-weight-bold);
}
.csv__note {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
</style>
