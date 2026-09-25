<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError } from '@/api/client'
import { studentApi } from '@/api/student'
import type { StudentResvIn } from '@/api/types'
import ReserveSheet from '@/components/student/ReserveSheet.vue'
import {
  CAP_TEXT,
  DAILY_TEXT,
  FULL_TEXT,
  MAX_ACTIVE,
  STALE_TEXT,
  TAKEN_TEXT,
  activeCount,
} from '@/components/student/rules'
import EmptyState from '@/components/ui/EmptyState.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import { showToast } from '@/components/ui/toast'
import { useResource } from '@/lib/useResource'
import StudentHeader from '../StudentHeader.vue'
import { useRoomWeek } from '../building'
import NotFoundView from './NotFoundView.vue'

const router = useRouter()
// 신청 화면은 폴링하지 않는다 — 고른 구간이 60초마다 흔들리지 않게. 제출 오류 때만 재조회 (설계 판정)
const { bld, roomNo, room, now, notFound, title, week, weekError, reload } = useRoomWeek({
  poll: false,
})
const { data: mine, reload: reloadMine } = useResource(() => studentApi.mine())
const count = computed(() => activeCount(mine.value ?? [], now.value))
const submitting = ref(false)
/** 하루 10회(429) — 이 화면에 있는 동안 잠근다 */
const locked = ref(false)

async function submit(body: StudentResvIn) {
  if (submitting.value || !room.value) return // 이중 제출 — 버튼 loading 과 같은 선
  submitting.value = true
  try {
    await studentApi.requestResv(room.value.room_id, body)
    showToast({ message: '예약을 신청했어요. 관리자 승인 뒤 확정돼요.' })
    await router.push('/me')
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    await explain(e)
  } finally {
    submitting.value = false
  }
}

/** 서버 원문 대신 이유를 말하고, 고를 거리를 새로 불러온다 (student-room.md §화면이 거는 제약) */
async function explain(e: ApiError) {
  // 401·403 은 client 가 로그인으로 보낸다 — 입력은 되살리지 않는다(F1·auth.md)
  if (e.status === 401 || e.status === 403) return
  if (e.status === 429) {
    locked.value = true
    showToast({ tone: 'danger', message: DAILY_TEXT })
  } else if (e.status === 409) {
    // 겹침(누가 먼저)과 가득(24건)이 둘 다 409 — 원문 대신 재조회한 full 로 가른다
    await reload()
    showToast({ tone: 'danger', message: week.value?.full ? FULL_TEXT : TAKEN_TEXT })
  } else if (e.status === 400) {
    // 창 밖·지난 시각·진행 중 3건이 400 — 3건인지는 내 예약으로 안다
    await Promise.all([reload(), reloadMine()])
    showToast({ tone: 'danger', message: count.value >= MAX_ACTIVE ? CAP_TEXT : STALE_TEXT })
  } else if (e.status === 404) {
    await reload() // 그새 예약을 받지 않게 된 방 — 주간도 404 → 404 화면
  } else {
    showToast({ tone: 'danger', message: e.message })
  }
}
const retry = () => void reload()
</script>

<template>
  <NotFoundView v-if="notFound" :back="`/${bld}`" back-label="강의실 목록으로" />
  <div v-else class="reserve">
    <StudentHeader
      :title="`${title} 예약`"
      :back="`/${bld}/${roomNo}`"
      back-label="닫기"
      back-text="✕"
    />
    <Skeleton v-if="!week && !weekError" :rows="4" />
    <EmptyState
      v-else-if="!week"
      message="비어 있는 시간을 불러오지 못했어요"
      :actions="[{ label: '다시 시도', variant: 'primary', onClick: retry }]"
    />
    <ReserveSheet
      v-else
      :days="week.free"
      :now="now"
      :my-future-count="count"
      :full="week.full"
      :locked="locked"
      :submitting="submitting"
      @submit="submit"
    />
  </div>
</template>

<style scoped>
.reserve {
  min-height: 100vh;
  background: var(--surface);
}
</style>
