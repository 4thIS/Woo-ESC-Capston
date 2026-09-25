<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Select from '@/components/ui/Select.vue'
import Table from '@/components/ui/Table.vue'
import { showToast } from '@/components/ui/toast'
import NodeStateBadge from '@/components/domain/NodeStateBadge.vue'
import SignalBars from '@/components/domain/SignalBars.vue'
import { adminApi } from '@/api/admin'
import { loraApi } from '@/api/lora'
import { ApiError } from '@/api/client'
import type { NodeOut } from '@/api/types'
import { useResource } from '@/lib/useResource'
import { usePolling } from '@/lib/usePolling'
import { formatKst, relativeKo } from '@/lib/time'
import LastRefreshed from '../LastRefreshed.vue'
import ModemPanel from './nodes/ModemPanel.vue'
import { buildingOptions, roomLabel, sortNodes, unitsByRoom, versions, volts } from '../nodesView'

const router = useRouter()
const modemPanel = ref<InstanceType<typeof ModemPanel> | null>(null)

// 블록 셋 = 엔드포인트 셋 (admin-nodes.md). 한 번에 읽어 한 시각(refreshedAt)으로 보인다
const { data, error, loading, refreshedAt, reload } = useResource(async () => {
  const [modems, nodes, pending] = await Promise.all([
    loraApi.modems(),
    adminApi.nodes(),
    loraApi.pending(),
  ])
  return { modems, nodes, pending }
})
// 노드를 켜 놓고 이 화면을 보는 일이 잦다 — 30초 (숨김이면 정지, 떠나면 해제)
usePolling(reload, 30_000)

// 끊긴 동안 Toast 는 한 번 — 30초마다 쌓이지 않게. 이전 표는 그대로 둔다(빈 표 = "전부 죽었다"로 오독)
watch(error, (e, prev) => {
  if (e && !prev && e.status !== 401 && e.status !== 403)
    showToast({
      tone: 'danger',
      message: e.message,
      action: { label: '재시도', onClick: () => void reload() },
    })
})

const nodes = computed(() => data.value?.nodes ?? [])
const units = computed(() => unitsByRoom(nodes.value))
const buildingId = ref<number | ''>('')
const buildingOpts = computed(() => buildingOptions(nodes.value))
// 고른 건물이 목록에서 사라지면(삭제) 전체로
watch(buildingOpts, (opts) => {
  if (!opts.some((o) => o.value === buildingId.value)) buildingId.value = ''
})
const onlyWarn = ref(false)
const rows = computed(() =>
  sortNodes(
    nodes.value.filter(
      (n) =>
        (buildingId.value === '' || n.building_id === buildingId.value) &&
        (!onlyWarn.value || n.warnings.length > 0),
    ),
  ).map((n) => ({ ...n, key: `${n.room_id}-${n.unit}` })),
)

// master 화면(F2)이 있을 때만 링크 — 라우트가 없으면 버튼을 두지 않는다
const hasMaster = router.resolve('/master').matched.length > 0
const empty = computed(() => {
  if (!data.value)
    return {
      message: '노드 목록을 불러오지 못했습니다',
      actions: [{ label: '다시 불러오기', onClick: () => void reload() }],
    }
  if (nodes.value.length === 0)
    return {
      message: '이 건물에 강의실이 없습니다',
      actions: hasMaster
        ? [{ label: '건물 · 강의실', onClick: () => void router.push('/master') }]
        : [],
    }
  return { message: '문제 있는 노드가 없습니다', actions: [] }
})

const COLUMNS: {
  key: string
  label: string
  width?: string
  align?: 'left' | 'right' | 'center'
}[] = [
  { key: 'room', label: '호수' },
  { key: 'mac', label: 'MAC', width: '120px' },
  { key: 'fw', label: 'FW', width: '56px', align: 'right' },
  { key: 'batt', label: '배터리', width: '96px', align: 'right' },
  { key: 'rssi', label: '신호', width: '112px' },
  { key: 'ver', label: '버전 S/R/E/I', width: '112px' },
  { key: 'state', label: '상태', width: '104px' },
  { key: 'seen', label: '마지막 수신', width: '104px' },
  { key: 'actions', label: '작업', width: '88px' },
]
const asNode = (row: Record<string, unknown>) => row as unknown as NodeOut

// 재전송 — 방 단위 전체 동기화. 한 번에 하나만
const syncing = ref<number | null>(null)
async function resend(n: NodeOut) {
  if (syncing.value !== null) return
  syncing.value = n.room_id
  try {
    await loraApi.syncRoom(n.room_id)
    showToast({ message: `${n.building} ${n.room}호 재전송을 요청했습니다.` })
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 404) {
      showToast({ message: '강의실이 이미 삭제되었습니다. 목록을 새로 불러옵니다.' })
      void reload()
    } else if (e.status !== 401 && e.status !== 403)
      showToast({
        tone: 'danger',
        message: e.message,
        action: { label: '재시도', onClick: () => void resend(n) },
      })
  } finally {
    syncing.value = null
  }
}

// 시각 브로드캐스트 — 서버 전역 10분 1회. 연결된 모뎀이 0대면 실패가 아니라 안내
const broadcasting = ref(false)
async function broadcast() {
  if (broadcasting.value) return
  broadcasting.value = true
  try {
    const { modems } = await loraApi.broadcastTime()
    showToast({
      message: modems
        ? `모뎀Pi ${modems}대에 시각을 보냈습니다.`
        : '연결된 모뎀Pi가 없어 보내지 못했습니다.',
    })
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 429)
      showToast({ message: '시각 브로드캐스트는 10분에 한 번만 보낼 수 있습니다.' })
    else if (e.status !== 401 && e.status !== 403) showToast({ tone: 'danger', message: e.message })
  } finally {
    broadcasting.value = false
  }
}
</script>

<template>
  <main class="nodes">
    <header class="nodes__head">
      <h1 class="nodes__title">ESP노드 · 모뎀Pi</h1>
      <LastRefreshed :at="refreshedAt" />
      <div class="nodes__tools">
        <label class="nodes__filter">
          <span>건물</span>
          <Select v-model="buildingId" :options="buildingOpts" size="sm" />
        </label>
        <Button variant="ghost" size="sm" :loading="loading" @click="reload">새로고침</Button>
        <Button variant="secondary" size="sm" :loading="broadcasting" @click="broadcast"
          >시각 브로드캐스트</Button
        >
        <Button size="sm" @click="modemPanel?.openRegister()">+ 모뎀Pi 등록</Button>
      </div>
    </header>

    <ModemPanel ref="modemPanel" :modems="data?.modems" :loading="loading" @changed="reload" />

    <section class="nodes__block" aria-labelledby="nodes-esp">
      <div class="nodes__block-head">
        <h2 id="nodes-esp" class="nodes__h2">ESP노드</h2>
        <Checkbox v-model="onlyWarn" label="문제 있는 것만" />
      </div>
      <Table
        :columns="COLUMNS"
        :rows="rows as unknown as Record<string, unknown>[]"
        row-key="key"
        :loading="loading && !data"
      >
        <template #empty>
          <EmptyState :message="empty.message" :actions="empty.actions" />
        </template>
        <template #cell-room="{ row }"
          >{{ asNode(row).building }} {{ roomLabel(asNode(row), units) }}</template
        >
        <template #cell-batt="{ row }">
          <Badge v-if="asNode(row).warnings.includes('low_batt')" tone="busy" class="num">{{
            volts(asNode(row).batt_mv)
          }}</Badge>
          <span v-else class="num">{{ volts(asNode(row).batt_mv) }}</span>
        </template>
        <template #cell-rssi="{ row }"><SignalBars :rssi="asNode(row).rssi" /></template>
        <template #cell-ver="{ row }"
          ><span class="num">{{ versions(asNode(row)) }}</span></template
        >
        <template #cell-state="{ row }"
          ><NodeStateBadge :warnings="asNode(row).warnings"
        /></template>
        <template #cell-seen="{ row }">
          <span v-if="asNode(row).last_seen_at" :title="formatKst(asNode(row).last_seen_at!)">{{
            relativeKo(asNode(row).last_seen_at!)
          }}</span>
          <template v-else>—</template>
        </template>
        <template #cell-actions="{ row }">
          <Button
            variant="ghost"
            size="sm"
            :loading="syncing === asNode(row).room_id"
            :disabled="syncing !== null"
            @click="resend(asNode(row))"
            >재전송</Button
          >
        </template>
      </Table>
    </section>
  </main>
</template>

<style scoped>
.nodes {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  padding: var(--space-5);
}
.nodes__head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.nodes__title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
}
.nodes__tools {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-left: auto;
}
.nodes__filter {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.nodes__block-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}
.nodes__h2 {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
</style>
