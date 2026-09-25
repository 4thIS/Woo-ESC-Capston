<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import Input from '@/components/ui/Input.vue'
import Modal from '@/components/ui/Modal.vue'
import Select from '@/components/ui/Select.vue'
import { showToast } from '@/components/ui/toast'
import { ApiError } from '@/api/client'
import { roomsApi } from '@/api/rooms'
import type { BuildingOut, RoomOut } from '@/api/types'
import { UNIT_OPTIONS, rangeProblem, rangeRooms } from '../../masterView'

const props = defineProps<{ open: boolean; building: BuildingOut; rooms: RoomOut[] }>()
const emit = defineEmits<{ close: []; changed: [] }>()

const form = reactive({ start: '', end: '', units: 1, reservable: true })
const excluded = ref<number[]>([])
const failed = ref<number[]>([])
const running = ref(false)
const done = ref(0)
const total = ref(0)
watch(
  () => props.open,
  (open) => {
    if (!open) return
    Object.assign(form, { start: '', end: '', units: 1, reservable: true })
    excluded.value = []
    failed.value = []
    done.value = 0
    total.value = 0
  },
  { immediate: true },
)

const existing = computed(() =>
  props.rooms.filter((r) => r.building_id === props.building.id).map((r) => r.room),
)
const filled = computed(() => !!form.start.trim() && !!form.end.trim())
const problem = computed(() =>
  filled.value ? rangeProblem(form.start.trim(), form.end.trim()) : null,
)
const chips = computed(() =>
  filled.value && !problem.value
    ? rangeRooms(Number(form.start), Number(form.end), existing.value)
    : [],
)
// 실패한 것이 있으면 그것만 다시 — 아니면 이미 있는 것·뺀 것을 제외한 칩
const targets = computed(() =>
  failed.value.length
    ? failed.value
    : chips.value.filter((c) => !c.exists && !excluded.value.includes(c.room)).map((c) => c.room),
)
const skipped = computed(() => chips.value.filter((c) => c.exists).length)
const locked = computed(() => running.value || failed.value.length > 0)
// 버튼 라벨이 실제로 만들 개수를 말한다 — '추가'가 아니다
const label = computed(() =>
  failed.value.length
    ? `실패한 ${failed.value.length}곳 재시도`
    : `${targets.value.length}곳 만들기`,
)
const progress = computed(() => `${done.value} / ${total.value || targets.value.length} 만드는 중`)

function toggle(room: number) {
  excluded.value = excluded.value.includes(room)
    ? excluded.value.filter((r) => r !== room)
    : [...excluded.value, room]
}
function close() {
  if (!running.value) emit('close')
}

// 벌크 엔드포인트가 없다 — 한 곳씩 POST. 일부 실패해도 되돌리지 않는다: 되돌리는 DELETE 도 실패할 수 있다
async function run() {
  if (running.value || !targets.value.length) return
  const list = [...targets.value]
  running.value = true
  total.value = list.length
  done.value = 0
  const bad: number[] = []
  try {
    for (const room of list) {
      try {
        await roomsApi.createRoom({
          building_id: props.building.id,
          room,
          units: form.units,
          reservable: form.reservable,
        })
      } catch (e) {
        if (!(e instanceof ApiError)) throw e
        if (e.status === 401 || e.status === 403) return
        if (e.status !== 409) bad.push(room) // 409 = 그사이 누가 만들었다 — 있는 것으로 친다
      }
      done.value++
    }
  } finally {
    running.value = false
    emit('changed')
  }
  failed.value = bad
  const made = list.length - bad.length
  if (!bad.length) {
    // 방 하나마다 모뎀에 config 가 한 번씩 나간다 — 노드 화면의 변화를 예상하게
    const tail = props.building.modem_id
      ? `${props.building.name} 모뎀Pi 에 설정이 다시 내려갔습니다.`
      : '모뎀Pi 가 배정되지 않아 문 앞 화면은 갱신되지 않습니다.'
    showToast({ message: `${made}곳을 만들었습니다. ${tail}` })
    emit('close')
  } else
    showToast({
      tone: 'danger',
      message: `${list.length}곳 중 ${made}곳 만듦 · ${bad.map((r) => `${r}호`).join(', ')} 실패`,
    })
}
</script>

<template>
  <Modal
    :open="open"
    :title="`${building.name} 범위로 추가`"
    size="lg"
    :close-on-backdrop="!filled && !running"
    @close="close"
  >
    <div class="range">
      <div class="range__fields">
        <Input
          v-model="form.start"
          label="시작 호수"
          inputmode="numeric"
          class="num"
          :disabled="locked"
        />
        <Input
          v-model="form.end"
          label="끝 호수"
          inputmode="numeric"
          class="num"
          :disabled="locked"
          :error="problem ?? undefined"
        />
        <Select v-model="form.units" label="유닛" :options="UNIT_OPTIONS" :disabled="locked" />
        <Checkbox v-model="form.reservable" label="학생 예약을 받는다" :disabled="locked" />
      </div>
      <template v-if="chips.length">
        <p class="range__sum num">
          만들어질 방 {{ chips.length }}곳 중 {{ targets.length }}곳<template v-if="skipped">
            · 이미 있는 {{ skipped }}곳은 건너뛴다</template
          >
        </p>
        <!-- 범위 문법을 늘리지 않는다 — 보고 눌러서 뺀다. 이미 있는 호수는 조용히 지우지 않고 점선+취소선 -->
        <ul class="range__chips" aria-label="만들 호수">
          <li v-for="c in chips" :key="c.room">
            <button
              type="button"
              class="chip num"
              :class="{ 'chip--exists': c.exists, 'chip--failed': failed.includes(c.room) }"
              :disabled="c.exists || locked"
              :aria-pressed="!c.exists && !excluded.includes(c.room) ? 'true' : 'false'"
              :title="c.exists ? '이미 있음' : undefined"
              @click="toggle(c.room)"
            >
              {{ c.room }}
            </button>
          </li>
        </ul>
      </template>
    </div>
    <template #footer>
      <Button variant="secondary" :disabled="running" @click="close">취소</Button>
      <Button
        class="range__submit"
        :loading="running"
        :loading-label="progress"
        :disabled="!targets.length"
        @click="run"
        >{{ label }}</Button
      >
    </template>
  </Modal>
</template>

<style scoped>
.range__fields {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-3);
  align-items: end;
}
.range__sum {
  margin: var(--space-4) 0 var(--space-2);
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.range__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  max-height: 240px;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  list-style: none;
}
.chip {
  min-width: 52px;
  height: var(--control-height-sm);
  padding: 0 var(--space-2);
  border: var(--border-thin) solid var(--line-3);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-2);
  font: inherit;
  cursor: pointer;
}
.chip[aria-pressed='true'] {
  border-color: var(--brand);
  background: var(--brand-tint);
  color: var(--brand);
}
.chip--exists {
  border-style: dashed;
  color: var(--text-3);
  text-decoration: line-through;
  cursor: not-allowed;
}
.chip--failed {
  border: var(--border-thick) solid var(--danger);
  color: var(--danger);
}
</style>
