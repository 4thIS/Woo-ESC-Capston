<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Modal from '@/components/ui/Modal.vue'
import Select from '@/components/ui/Select.vue'
import Table from '@/components/ui/Table.vue'
import { showToast } from '@/components/ui/toast'
import SignalBars from '@/components/domain/SignalBars.vue'
import { loraApi } from '@/api/lora'
import { ApiError } from '@/api/client'
import type { NodeOut, PendingOut } from '@/api/types'
import { formatKst, relativeKo } from '@/lib/time'
import { provisionChoices, volts } from '../../nodesView'

const props = defineProps<{ pending?: PendingOut[]; nodes: NodeOut[]; loading: boolean }>()
const emit = defineEmits<{ changed: [] }>()
// 첫 조회가 실패하면(로딩도 아니고 데이터도 없음) "없음"이 아니라 "불러오지 못했다"
const failed = computed(() => !props.loading && props.pending === undefined)

const COLUMNS: {
  key: string
  label: string
  width?: string
  align?: 'left' | 'right' | 'center'
}[] = [
  { key: 'mac', label: 'MAC', width: '128px' },
  { key: 'modem_id', label: '모뎀Pi', width: '128px' },
  { key: 'fw', label: 'FW', width: '56px', align: 'right' },
  { key: 'batt', label: '배터리', width: '88px', align: 'right' },
  { key: 'rssi', label: '신호', width: '112px' },
  { key: 'first', label: '처음 발견', width: '104px' },
  { key: 'last', label: '마지막 발견' },
  { key: 'actions', label: '작업', width: '112px' },
]
const asP = (row: Record<string, unknown>) => row as unknown as PendingOut

// 배정 Modal — 선택지는 기대 노드(rooms × units)에서만: 없는 (bld, room, unit) 을 고를 수 없다
const target = ref<PendingOut | null>(null)
const bld = ref('')
const room = ref<number | ''>('')
const unit = ref<number | ''>('')
const choices = computed(() => provisionChoices(props.nodes, bld.value, room.value))
watch(bld, () => (room.value = ''))
// 노드가 1대뿐인 방은 번호를 고를 필요가 없다
watch(room, () => {
  const u = choices.value.units
  unit.value = u.length === 1 ? u[0].value : ''
})
const occupied = computed(
  () => choices.value.units.find((u) => u.value === unit.value)?.mac ?? null,
)
const ready = computed(() => !!bld.value && room.value !== '' && unit.value !== '')
const busy = ref(false)

function open(p: PendingOut) {
  bld.value = ''
  room.value = ''
  unit.value = ''
  target.value = p
}

async function submit() {
  const p = target.value
  if (!p || busy.value || !ready.value) return
  const body = { bld: bld.value, room: room.value as number, unit: unit.value as number }
  const name = choices.value.buildings.find((b) => b.value === body.bld)?.label ?? body.bld
  busy.value = true
  try {
    await loraApi.provision(p.mac, body)
    target.value = null
    // 서버는 pending 행을 바로 지우지 않는다 — 장치가 SET_ROOM 을 받고 응답하면 ESP노드 표로 옮겨 간다
    showToast({
      message: `${name} ${body.room}호에 배정했습니다. 장치가 다음에 깨어나면 적용됩니다.`,
    })
    emit('changed')
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 404) {
      target.value = null
      showToast({ message: '장치 또는 강의실이 사라졌습니다. 목록을 새로 불러옵니다.' })
      emit('changed')
    } else if (e.status !== 401 && e.status !== 403)
      showToast({ tone: 'danger', message: e.message })
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="block" aria-labelledby="nodes-pending">
    <h2 id="nodes-pending" class="block__title">등록 대기</h2>
    <Table
      :columns="COLUMNS"
      :rows="(pending ?? []) as unknown as Record<string, unknown>[]"
      row-key="mac"
      :loading="loading && !pending"
    >
      <template #empty>
        <EmptyState
          :message="
            failed ? '등록 대기 장치를 불러오지 못했습니다' : '등록을 기다리는 장치가 없습니다.'
          "
        />
      </template>
      <template #cell-batt="{ row }"
        ><span class="num">{{ volts(asP(row).batt_mv) }}</span></template
      >
      <template #cell-rssi="{ row }"><SignalBars :rssi="asP(row).rssi" /></template>
      <template #cell-first="{ row }">
        <span :title="formatKst(asP(row).first_seen_at)">{{
          relativeKo(asP(row).first_seen_at)
        }}</span>
      </template>
      <template #cell-last="{ row }">
        <span :title="formatKst(asP(row).last_seen_at)">{{
          relativeKo(asP(row).last_seen_at)
        }}</span>
      </template>
      <template #cell-actions="{ row }">
        <Button size="sm" @click="open(asP(row))">강의실 배정</Button>
      </template>
    </Table>

    <Modal
      :open="!!target"
      title="강의실 배정"
      size="sm"
      :close-on-backdrop="!bld"
      @close="target = null"
    >
      <p class="block__text num">장치 {{ target?.mac }}</p>
      <p v-if="!choices.buildings.length" class="block__text">
        먼저 건물 · 강의실을 등록해 주세요.
      </p>
      <div v-else class="assign">
        <Select v-model="bld" :options="choices.buildings" label="건물" placeholder="건물 선택" />
        <Select
          v-model="room"
          :options="choices.rooms"
          label="호수"
          placeholder="호수 선택"
          :disabled="!bld"
        />
        <Select
          v-model="unit"
          :options="choices.units"
          label="노드"
          placeholder="노드 선택"
          :disabled="room === ''"
        />
        <p v-if="occupied" class="assign__hint">
          이 자리에는 이미 노드 {{ occupied }} 가 있습니다.
        </p>
      </div>
      <template #footer>
        <Button variant="secondary" @click="target = null">취소</Button>
        <Button :loading="busy" :disabled="!ready" @click="submit">배정</Button>
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
.assign {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.assign__hint {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
</style>
