<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Input from '@/components/ui/Input.vue'
import Modal from '@/components/ui/Modal.vue'
import Select from '@/components/ui/Select.vue'
import Table from '@/components/ui/Table.vue'
import { showToast } from '@/components/ui/toast'
import { detailText } from '@/components/domain/rules'
import { ApiError, MESSAGES } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { BuildingOut, BuildingPatch, ModemOut, RoomOut } from '@/api/types'
import { session } from '@/lib/session'
import ConfirmModal from '../../ConfirmModal.vue'
import {
  BLD_MAX,
  OTHER_SCHOOL_BLD,
  bldProblem,
  modemChangeText,
  modemOptions,
  normalizeBld,
  usedBlds,
} from '../../masterView'

const props = defineProps<{
  buildings?: BuildingOut[]
  rooms: RoomOut[]
  modems: ModemOut[]
  loading: boolean
  selectedId: number | null
}>()
const emit = defineEmits<{ select: [id: number]; changed: []; reload: [] }>()

// 첫 불러오기 실패 — 목록이 없는 것이지 건물이 0개인 것이 아니다. 빈 학교(설치 안내)로 보이면 안 된다
const failed = computed(() => props.buildings === undefined && !props.loading)

const list = computed(() => props.buildings ?? [])
const full = computed(() => list.value.length >= BLD_MAX)
const roomCount = (id: number) => props.rooms.filter((r) => r.building_id === id).length
const rows = computed(() => list.value.map((b) => ({ ...b, rooms: roomCount(b.id) })))
const COLUMNS = [
  { key: 'bld', label: '글자', width: '52px' },
  { key: 'name', label: '이름' },
  { key: 'modem_id', label: '모뎀', width: '104px' },
  { key: 'rooms', label: '방', width: '48px', align: 'right' as const },
  { key: 'actions', label: '작업', width: '92px' },
]
const asB = (row: Record<string, unknown>) => row as unknown as BuildingOut & { rooms: number }

// ---- 추가·수정 폼 ----
const editing = ref<BuildingOut | null>(null)
const formOpen = ref(false)
const form = reactive({ name: '', bld: '', modem: '' })
const errors = reactive<{ name?: string; bld?: string; form?: string }>({})
const saving = ref(false)
const initial = ref('')
const dirty = computed(() => JSON.stringify(form) !== initial.value)
// bld 는 무선 주소 — 강의실이 생기면 잠긴다 (노드 NVS 가 (bld, room, unit) 을 들고 있다)
const bldLocked = computed(() => !!editing.value && roomCount(editing.value.id) > 0)
const others = computed(() => list.value.filter((b) => b.id !== editing.value?.id))
const bldHint = computed(() =>
  bldLocked.value
    ? '강의실이 있는 건물은 글자를 바꿀 수 없습니다. 바꾸려면 강의실을 모두 지우고 다시 만들어야 합니다.'
    : `대문자 한 글자 · 쓰는 중: ${usedBlds(others.value) || '없음'}`,
)

function clearErrors() {
  delete errors.name
  delete errors.bld
  delete errors.form
}
function openForm(b: BuildingOut | null) {
  editing.value = b
  Object.assign(form, { name: b?.name ?? '', bld: b?.bld ?? '', modem: b?.modem_id ?? '' })
  clearErrors()
  initial.value = JSON.stringify(form)
  formOpen.value = true
}
function validate(): boolean {
  clearErrors()
  if (!form.name.trim()) errors.name = '이름을 넣으세요'
  const p = bldLocked.value ? null : bldProblem(form.bld, list.value, editing.value?.id ?? null)
  if (p) errors.bld = p
  return !errors.name && !errors.bld
}

// 모뎀을 바꾸면 서버가 대기 전송을 새 모뎀으로 옮기고 양쪽 모뎀에 config 를 다시 내린다 —
// 이름만 고치러 온 관리자가 드롭다운을 잘못 건드릴 수 있어, 바뀐 경우에만 대기 건수로 묻는다
const modemAsk = ref<string[] | null>(null)
async function submit() {
  if (saving.value || !validate()) return
  const b = editing.value
  if (b && (b.modem_id ?? '') !== form.modem) {
    saving.value = true
    let queued: number | null = null
    try {
      queued = (await roomsApi.buildingOutbox(b.id, 'queued')).length
    } catch (e) {
      if (!(e instanceof ApiError)) throw e // 건수를 못 세도 묻기는 한다
    } finally {
      saving.value = false
    }
    modemAsk.value = [modemChangeText(queued, b.modem_id, form.modem || null)]
    return
  }
  await save()
}

async function save() {
  const b = editing.value
  saving.value = true
  try {
    if (b) {
      // 부분 수정 — 바뀐 필드만 보낸다
      const patch: BuildingPatch = {}
      if (form.name.trim() !== b.name) patch.name = form.name.trim()
      if (!bldLocked.value && form.bld !== b.bld) patch.bld = form.bld
      if (form.modem !== (b.modem_id ?? '')) patch.modem_id = form.modem || null
      if (Object.keys(patch).length) await roomsApi.patchBuilding(b.id, patch)
    } else {
      const created = await roomsApi.createBuilding({
        school_id: session.value!.school_id, // 내 학교가 아니면 서버가 404
        name: form.name.trim(),
        bld: form.bld,
        modem_id: form.modem || null,
      })
      emit('select', created.id)
    }
    modemAsk.value = null
    formOpen.value = false
    showToast({ message: '저장했습니다.' })
    emit('changed')
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    modemAsk.value = null
    // 다른 학교가 쓰는 글자는 화면이 미리 알 수 없다 — Toast 가 아니라 글자 칸에 붙인다
    if (e.status === 409 && /다른 학교/.test(detailText(e))) errors.bld = OTHER_SCHOOL_BLD
    else if (e.status === 409) {
      // 같은 학교 글자 경합(다른 탭·관리자가 먼저 만듦) — 건물 문장으로 글자 칸에, 목록을 새로
      errors.bld = '이미 쓰는 글자입니다. 목록을 새로 불러옵니다.'
      emit('changed')
    } else if (e.status === 404) {
      showToast({
        tone: 'danger',
        message: '건물이나 모뎀을 찾을 수 없습니다. 목록을 새로 불러옵니다.',
      })
      formOpen.value = false
      emit('changed')
    } else if (e.status === 422) errors.form = MESSAGES[422]
    else if (e.status !== 401 && e.status !== 403) errors.form = e.message
  } finally {
    saving.value = false
  }
}

// ---- 삭제 — 강의실 0곳일 때만 (방이 있으면 서버 409, 버튼을 잠가 둔다) ----
const removing = ref<BuildingOut | null>(null)
const removingBusy = ref(false)
async function remove() {
  const b = removing.value
  if (!b || removingBusy.value) return
  removingBusy.value = true
  try {
    await roomsApi.deleteBuilding(b.id)
    showToast({ message: `${b.name}(${b.bld}) 건물을 지웠습니다.` })
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 409)
      showToast({
        tone: 'danger',
        message: '강의실이 남아 있어 지울 수 없습니다. 목록을 새로 불러옵니다.',
      })
    else if (e.status !== 404 && e.status !== 401 && e.status !== 403)
      showToast({ tone: 'danger', message: e.message })
  } finally {
    removingBusy.value = false
    removing.value = null
    emit('changed')
  }
}
</script>

<template>
  <section class="panel" aria-labelledby="master-bld">
    <header class="panel__head">
      <h2 id="master-bld" class="panel__title">건물</h2>
      <!-- 26개가 상한 — 남은 수를 모르면 26번째에서야 안다 -->
      <span class="panel__count num">{{ list.length }} / {{ BLD_MAX }}</span>
      <span class="panel__tools" :title="full ? '건물은 26개까지입니다' : undefined">
        <Button
          variant="secondary"
          size="sm"
          :disabled="full || buildings === undefined"
          @click="openForm(null)"
          >+ 건물</Button
        >
      </span>
    </header>
    <div v-if="failed" class="panel__empty">
      <EmptyState
        message="건물 목록을 불러오지 못했습니다"
        :actions="[{ label: '다시 불러오기', onClick: () => emit('reload') }]"
      />
    </div>
    <div v-else-if="!loading && !list.length" class="panel__empty">
      <EmptyState
        message="건물을 먼저 만드세요"
        :actions="[{ label: '+ 건물', variant: 'primary', onClick: () => openForm(null) }]"
      />
      <!-- 이 시스템의 첫 화면 — 설치 순서가 곧 화면 순서다 -->
      <ol class="panel__steps">
        <li>건물을 만들고 모뎀Pi 를 배정합니다.</li>
        <li>강의실을 범위로 추가합니다.</li>
        <li>노드 상태에서 단말을 배정하고, 강의실 설정에서 시간표를 넣습니다.</li>
      </ol>
    </div>
    <Table
      v-else
      tall
      :columns="COLUMNS"
      :rows="rows as unknown as Record<string, unknown>[]"
      :loading="loading"
      :selected="selectedId === null ? [] : [String(selectedId)]"
    >
      <template #cell-bld="{ row }"
        ><span class="panel__bld">{{ asB(row).bld }}</span></template
      >
      <template #cell-name="{ row }">
        <button
          type="button"
          class="panel__pick"
          :aria-pressed="asB(row).id === selectedId ? 'true' : 'false'"
          @click="emit('select', asB(row).id)"
        >
          {{ asB(row).name }}
        </button>
      </template>
      <template #cell-modem_id="{ row }">
        <span v-if="asB(row).modem_id" class="num">{{ asB(row).modem_id }}</span>
        <!-- 모뎀이 없으면 이 건물 강의실은 갱신을 못 받는다 — 기능이 죽어 있어 적색 -->
        <Badge v-else tone="danger" variant="outline" title="이 건물 강의실은 갱신을 받지 못합니다"
          >미배정</Badge
        >
      </template>
      <template #cell-rooms="{ row }"
        ><span class="num">{{ asB(row).rooms }}</span></template
      >
      <template #cell-actions="{ row }">
        <div class="panel__actions">
          <Button variant="ghost" size="sm" @click="openForm(asB(row))">수정</Button>
          <!-- 비활성 버튼은 마우스 이벤트가 없어 툴팁을 감싼 칸에 단다 -->
          <span
            :title="asB(row).rooms ? `강의실을 먼저 지우세요 (${asB(row).rooms}곳)` : undefined"
          >
            <Button
              variant="ghost"
              size="sm"
              :disabled="asB(row).rooms > 0"
              @click="removing = asB(row)"
              >삭제</Button
            >
          </span>
        </div>
      </template>
    </Table>

    <Modal
      :open="formOpen"
      :title="editing ? '건물 수정' : '건물 추가'"
      :close-on-backdrop="!dirty"
      @close="formOpen = false"
    >
      <form class="form" novalidate @submit.prevent="submit">
        <p v-if="errors.form" class="form__error" role="alert">{{ errors.form }}</p>
        <Input v-model="form.name" label="이름" required :error="errors.name" />
        <Input
          :model-value="form.bld"
          label="글자"
          required
          maxlength="1"
          autocomplete="off"
          :readonly="bldLocked"
          :error="errors.bld"
          :hint="bldHint"
          @update:model-value="(v: string) => (form.bld = normalizeBld(v))"
        />
        <Select
          v-model="form.modem"
          label="모뎀"
          :options="modemOptions(modems, list, editing?.id ?? null)"
        />
      </form>
      <template #footer>
        <Button variant="secondary" @click="formOpen = false">취소</Button>
        <Button :loading="saving" @click="submit">저장</Button>
      </template>
    </Modal>
    <ConfirmModal
      :open="!!modemAsk"
      title="모뎀 변경"
      :lines="modemAsk ?? []"
      confirm-label="바꾸기"
      :danger="false"
      :loading="saving"
      @confirm="save"
      @close="modemAsk = null"
    />
    <ConfirmModal
      :open="!!removing"
      title="건물 삭제"
      :lines="removing ? [`${removing.name}(${removing.bld}) 건물을 지웁니다.`] : []"
      :loading="removingBusy"
      @confirm="remove"
      @close="removing = null"
    />
  </section>
</template>

<style scoped>
.panel {
  overflow: hidden;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.panel__head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
}
.panel__title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.panel__count {
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
.panel__tools {
  margin-left: auto;
}
.panel__empty {
  padding: var(--space-4);
}
.panel__steps {
  margin: 0;
  padding-left: var(--space-5);
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.panel__bld {
  font-weight: var(--font-weight-bold);
}
.panel__pick {
  padding: 0;
  border: 0;
  background: none;
  color: var(--text-1);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.panel__pick[aria-pressed='true'] {
  color: var(--brand);
  font-weight: var(--font-weight-medium);
}
.panel__actions {
  display: flex;
  gap: var(--space-1);
}
/* 선택된 건물 행 — brand.tint(Table) + 왼쪽 3px brand 막대 (admin-master.md) */
.panel :deep(.tbl__row--selected td:first-child) {
  box-shadow: inset 3px 0 0 var(--brand);
}
.form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.form__error {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--danger);
}
</style>
