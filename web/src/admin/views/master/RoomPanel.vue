<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Input from '@/components/ui/Input.vue'
import Modal from '@/components/ui/Modal.vue'
import Select from '@/components/ui/Select.vue'
import Table from '@/components/ui/Table.vue'
import { showToast } from '@/components/ui/toast'
import { conflictMessage, detailText, floorLabel } from '@/components/domain/rules'
import { ApiError, MESSAGES } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { BuildingOut, NodeOut, RoomOut, RoomPatch } from '@/api/types'
import ConfirmModal from '../../ConfirmModal.vue'
import {
  UNIT_OPTIONS,
  countFor,
  roomDeleteLines,
  roomNodeText,
  type RoomCounts,
} from '../../masterView'

const props = defineProps<{
  building: BuildingOut
  rooms: RoomOut[]
  nodes: NodeOut[]
  loading: boolean
}>()
const emit = defineEmits<{ changed: []; range: [] }>()

const mine = computed(() =>
  props.rooms.filter((r) => r.building_id === props.building.id).sort((a, b) => a.room - b.room),
)
const COLUMNS = [
  { key: 'room', label: '호수', width: '72px' },
  { key: 'floor', label: '층', width: '52px' },
  { key: 'units', label: '유닛', width: '64px', align: 'right' as const },
  { key: 'reservable', label: '학생 예약', width: '128px' },
  { key: 'node', label: '노드' },
  { key: 'actions', label: '작업', width: '92px' },
]
const asR = (row: Record<string, unknown>) => row as unknown as RoomOut

// ---- reservable — 이 화면의 요점. 끄면 학생 웹에서 그 방이 사라진다(문 앞 e-Paper 는 그대로) ----
// 즉시 저장. 응답·새 목록이 오기 전까지 누른 값을 보이고, 실패하면 되돌린다
const flipped = reactive(new Map<number, boolean>())
const flipping = reactive(new Set<number>())
watch(
  () => props.rooms,
  () => flipped.clear(),
)
const reservableOf = (r: RoomOut) => flipped.get(r.id) ?? r.reservable
const visible = computed(() => mine.value.filter(reservableOf).length)
async function flip(r: RoomOut, on: boolean) {
  if (flipping.has(r.id)) return
  flipping.add(r.id)
  flipped.set(r.id, on)
  try {
    // 부분 PATCH — 전체 바디를 보내면 다른 탭에서 바뀐 units 를 덮는다
    await roomsApi.patchRoom(r.id, { reservable: on })
    emit('changed')
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    flipped.delete(r.id)
    if (e.status !== 401 && e.status !== 403)
      showToast({ tone: 'danger', message: `${r.room}호 학생 예약 설정을 바꾸지 못했습니다.` })
    if (e.status === 404) emit('changed')
  } finally {
    flipping.delete(r.id)
  }
}

// ---- 추가·수정 폼 — 층 입력 칸은 없다(파생값), 호수는 새로 만들 때만 ----
const editing = ref<RoomOut | null>(null)
const formOpen = ref(false)
const form = reactive({ room: '', units: 1, reservable: false })
const errors = reactive<{ room?: string; form?: string }>({})
const saving = ref(false)
const initial = ref('')
const dirty = computed(() => JSON.stringify(form) !== initial.value)
function openForm(r: RoomOut | null) {
  editing.value = r
  Object.assign(form, {
    room: r ? String(r.room) : '',
    units: r?.units ?? 1,
    reservable: r?.reservable ?? false,
  })
  delete errors.room
  delete errors.form
  initial.value = JSON.stringify(form)
  formOpen.value = true
}

const shrinkAsk = ref<string[] | null>(null)
function submit() {
  if (saving.value) return
  delete errors.room
  delete errors.form
  const r = editing.value
  if (!r) {
    const n = Number(form.room)
    if (!/^\d+$/.test(form.room) || n < 1 || n > 9999) {
      errors.room = '호수는 1~9999 정수입니다'
      return
    }
    if (mine.value.some((x) => x.room === n)) {
      errors.room = '이미 있는 호수입니다'
      return
    }
  } else if (form.units < r.units) {
    // 2 → 1: unit 2 가 기대 노드에서 빠지는데 단말은 벽에 붙어 있다. 늘리는 쪽은 묻지 않는다
    // (새 자리가 노드 화면에 '응답 없음'으로 뜨는 것이 곧 "여기에 단말을 달아라")
    shrinkAsk.value = [`${r.room}호의 2번 단말이 목록에서 사라집니다. 벽에서 떼어 주세요.`]
    return
  }
  void save()
}

async function save() {
  const r = editing.value
  saving.value = true
  try {
    if (r) {
      const patch: RoomPatch = {}
      if (form.units !== r.units) patch.units = form.units
      if (form.reservable !== r.reservable) patch.reservable = form.reservable
      if (Object.keys(patch).length) await roomsApi.patchRoom(r.id, patch)
      showToast({ message: '저장했습니다.' })
    } else {
      await roomsApi.createRoom({
        building_id: props.building.id,
        room: Number(form.room),
        units: form.units,
        reservable: form.reservable,
      })
      showToast({ message: `${form.room}호를 만들었습니다.` })
    }
    shrinkAsk.value = null
    formOpen.value = false
    emit('changed')
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    shrinkAsk.value = null
    if (e.status === 409) {
      // 다른 탭에서 같은 호수를 먼저 만들었다 — 호수 칸에 붙이고 목록을 새로 받는다
      errors.room = /constraint violation/.test(detailText(e))
        ? '이미 있는 호수입니다. 목록을 새로 불러옵니다.'
        : conflictMessage(e)
      emit('changed')
    } else if (e.status === 404) {
      showToast({
        tone: 'danger',
        message: '강의실이나 건물을 찾을 수 없습니다. 목록을 새로 불러옵니다.',
      })
      formOpen.value = false
      emit('changed')
    } else if (e.status === 422) errors.form = MESSAGES[422]
    else if (e.status !== 401 && e.status !== 403) errors.form = e.message
  } finally {
    saving.value = false
  }
}

// ---- 삭제 — 시간표·예약·시험기간이 CASCADE 로 함께 사라진다. 개수를 적는다(이름 입력은 요구하지 않는다) ----
const removing = ref<RoomOut | null>(null)
const removeLines = ref<string[]>([])
const counting = ref(false)
const removingBusy = ref(false)
async function askRemove(r: RoomOut) {
  removing.value = r
  removeLines.value = [`${props.building.name} ${r.room}호를 지웁니다.`, '딸린 항목 수를 세는 중…']
  counting.value = true
  let counts: RoomCounts | null = null
  try {
    const [slots, resv, exams] = await Promise.all([
      roomsApi.buildingSlots(props.building.id),
      roomsApi.buildingResv(props.building.id),
      roomsApi.buildingExams(props.building.id),
    ])
    counts = countFor(r.id, slots, resv, exams)
  } catch (e) {
    if (!(e instanceof ApiError)) throw e // 못 세도 지울 수는 있다 — 문장이 그렇게 말한다
  } finally {
    counting.value = false
  }
  if (removing.value?.id === r.id)
    removeLines.value = roomDeleteLines(props.building.name, r, counts, props.nodes)
}
async function remove() {
  const r = removing.value
  if (!r || removingBusy.value || counting.value) return
  removingBusy.value = true
  try {
    await roomsApi.deleteRoom(r.id)
    showToast({ message: `${r.room}호를 지웠습니다.` })
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status !== 404 && e.status !== 401 && e.status !== 403)
      showToast({ tone: 'danger', message: e.message })
  } finally {
    removingBusy.value = false
    removing.value = null
    emit('changed')
  }
}
</script>

<template>
  <section class="panel" aria-labelledby="master-room">
    <header class="panel__head">
      <h2 id="master-room" class="panel__title">{{ building.name }} 강의실</h2>
      <span class="panel__count num">{{ mine.length }}곳 · 학생 웹에 보이는 곳 {{ visible }}</span>
      <span class="panel__note">층 = 호수 ÷ 100</span>
      <div class="panel__tools">
        <!-- 방 30개를 하나씩 넣는 것은 실사용이 안 된다 — 범위가 정상 경로 -->
        <Button variant="secondary" size="sm" @click="emit('range')">범위로 추가</Button>
        <Button size="sm" @click="openForm(null)">+ 강의실</Button>
      </div>
    </header>
    <Table
      tall
      :columns="COLUMNS"
      :rows="mine as unknown as Record<string, unknown>[]"
      :loading="loading"
    >
      <template #empty>
        <EmptyState
          message="이 건물에 강의실이 없습니다"
          :actions="[{ label: '범위로 추가', variant: 'primary', onClick: () => emit('range') }]"
        />
      </template>
      <template #cell-room="{ row }"
        ><span class="num">{{ asR(row).room }}</span></template
      >
      <template #cell-floor="{ row }">{{ floorLabel(asR(row).room) }}</template>
      <template #cell-units="{ row }"
        ><span class="num">{{ asR(row).units }}</span></template
      >
      <template #cell-reservable="{ row }">
        <Checkbox
          :model-value="reservableOf(asR(row))"
          :disabled="flipping.has(asR(row).id)"
          :label="reservableOf(asR(row)) ? '받음' : '안 받음'"
          @update:model-value="(v) => flip(asR(row), v === true)"
        />
      </template>
      <template #cell-node="{ row }">{{ roomNodeText(asR(row), nodes) }}</template>
      <template #cell-actions="{ row }">
        <div class="panel__actions">
          <Button variant="ghost" size="sm" @click="openForm(asR(row))">수정</Button>
          <Button variant="ghost" size="sm" @click="askRemove(asR(row))">삭제</Button>
        </div>
      </template>
    </Table>

    <Modal
      :open="formOpen"
      :title="editing ? '강의실 수정' : '강의실 추가'"
      :close-on-backdrop="!dirty"
      @close="formOpen = false"
    >
      <form class="form" novalidate @submit.prevent="submit">
        <p v-if="errors.form" class="form__error" role="alert">{{ errors.form }}</p>
        <!-- 호수는 bld 와 함께 무선 주소 — 수정 폼에서 잠근다 -->
        <Input
          v-model="form.room"
          label="호수"
          inputmode="numeric"
          class="num"
          required
          :readonly="!!editing"
          :error="errors.room"
          :hint="
            editing
              ? '호수를 바꾸려면 강의실을 지우고 다시 만든 뒤, 문 앞 단말을 다시 등록하세요.'
              : undefined
          "
        />
        <Select v-model="form.units" label="유닛" :options="UNIT_OPTIONS" />
        <Checkbox v-model="form.reservable" label="학생 예약을 받는다" />
      </form>
      <template #footer>
        <Button variant="secondary" @click="formOpen = false">취소</Button>
        <Button :loading="saving" @click="submit">저장</Button>
      </template>
    </Modal>
    <ConfirmModal
      :open="!!shrinkAsk"
      title="유닛 줄이기"
      :lines="shrinkAsk ?? []"
      confirm-label="줄이기"
      :loading="saving"
      @confirm="save"
      @close="shrinkAsk = null"
    />
    <ConfirmModal
      :open="!!removing"
      title="강의실 삭제"
      :lines="removeLines"
      :loading="counting || removingBusy"
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
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
}
.panel__title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.panel__count {
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.panel__note {
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.panel__tools {
  display: flex;
  gap: var(--space-2);
  margin-left: auto;
}
.panel__actions {
  display: flex;
  gap: var(--space-1);
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
