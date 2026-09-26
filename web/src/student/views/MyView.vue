<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '@/api/client'
import { studentApi } from '@/api/student'
import type { ResvMineOut } from '@/api/types'
import MyResvCard from '@/components/student/MyResvCard.vue'
import { CHANGED_TEXT, CHECKIN_CLOSED_TEXT, sortMine } from '@/components/student/rules'
import Banner from '@/components/ui/Banner.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Modal from '@/components/ui/Modal.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import { showToast } from '@/components/ui/toast'
import { usePolling } from '@/lib/usePolling'
import { useResource } from '@/lib/useResource'
import RefreshedNote from '../RefreshedNote.vue'
import StudentHeader from '../StudentHeader.vue'
import { BUILDING } from '../building'
import { POLL_MS, useNow } from '../composables'
import { lastBld } from '../favorites'

type Kind = 'checkin' | 'cancel'
const router = useRouter()
// 신청한 뒤 학생이 돌아오는 자리 — 승인·거절 알림이 없어(S10 비목표) 60초마다 다시 본다
// 건물 안(/E/me)이면 레이아웃이 부르는 것을 같이 쓴다 — 두 번 부르지 않고, 취소·체크인 뒤 재조회가
// 사이드바의 다음 예약 카드에도 바로 닿는다. 열 때 한 번 새로 부른다(방금 신청한 예약)
const shared = inject(BUILDING, null)?.mine
const { data, error, refreshedAt, reload } = shared ?? useResource(() => studentApi.mine())
if (shared) void reload()
else usePolling(reload, POLL_MS)
const now = useNow()
const list = computed(() => sortMine(data.value ?? [], now.value))
// 건물 안(/E/me)이면 목록 옆 칸 — 넓은 폭은 목록이 보이니 ‹ 를 감춘다
const inBld = useRoute().params.bld as string | undefined
const last = inBld ?? lastBld()
const back = last ? `/${last}` : '/'
const busy = ref<{ id: number; kind: Kind } | null>(null)
const confirming = ref<ResvMineOut | null>(null)
const withdraw = computed(() => confirming.value?.status === 'requested')

/** 쓰기 한 건 — busy 는 await 전에 동기로 세운다(카드의 busy prop 은 한 렌더 늦다). 409·404(그새 관리자가 처리·이미 취소)는 문장 + 재조회 */
async function run(
  r: ResvMineOut,
  kind: Kind,
  call: () => Promise<unknown>,
  ok: string,
  conflict: string,
) {
  if (busy.value) return
  busy.value = { id: r.id, kind }
  // 재조회가 끝날 때까지 잠근다 — 옛 카드의 체크인이 잠깐 다시 눌려 엉뚱한 409 문장이 나지 않게
  try {
    try {
      await call()
      showToast({ message: ok })
    } catch (e) {
      if (!(e instanceof ApiError)) throw e
      // 401·403 은 client 가 로그인으로 보낸다 — 부를 것이 없다
      if (e.status === 401 || e.status === 403) return
      // 서버 원문은 내지 않는다 — 그새 바뀐 상태(409·404, 400 은 방어)는 이 화면의 문장.
      // 곧 재조회하니 그 문장은 알림일 뿐 — 8초 뒤 닫혀 헤더를 덮어 두지 않는다 (최종 리뷰 I3)
      const known = [400, 404, 409].includes(e.status)
      showToast({
        tone: 'danger',
        message: known ? conflict : e.message,
        duration: known ? 8000 : undefined,
      })
    }
    await reload()
  } finally {
    busy.value = null
  }
}

const checkin = (r: ResvMineOut) =>
  run(r, 'checkin', () => studentApi.checkin(r.id), '체크인했어요', CHECKIN_CLOSED_TEXT)
// 다른 카드가 쓰는 중이면 열지 않는다 — 열어 둔 확인이 run 의 busy 에 막혀 조용히 사라지지 않게
const askCancel = (r: ResvMineOut) => {
  if (!busy.value) confirming.value = r
}
const closeModal = () => {
  confirming.value = null
}
// 신청 취소 중 관리자가 승인했으면 서버가 승인 예약의 취소로 처리한다 — 결과가 같아 문장은 하나
async function confirmCancel() {
  const r = confirming.value
  if (!r) return
  confirming.value = null
  await run(r, 'cancel', () => studentApi.cancel(r.id), '취소했어요', CHANGED_TEXT)
}
const retry = () => void reload()
const goBack = () => void router.push(back)
</script>

<template>
  <div class="me">
    <StudentHeader title="내 예약" :back="back" :hide-back-wide="!!inBld" />
    <Banner v-if="error && data" tone="danger" :message="error.message" :dismissible="false">
      <Button variant="secondary" @click="retry">다시 시도</Button>
    </Banner>
    <main class="me__body">
      <Skeleton v-if="!data && !error" :rows="4" />
      <EmptyState
        v-else-if="!data"
        message="내 예약을 불러오지 못했어요"
        :actions="[{ label: '다시 시도', variant: 'primary', onClick: retry }]"
      />
      <EmptyState
        v-else-if="!list.length"
        message="아직 신청한 예약이 없어요"
        :actions="[{ label: '강의실 보러 가기', variant: 'primary', onClick: goBack }]"
      />
      <div v-else class="me__list">
        <MyResvCard
          v-for="r in list"
          :key="r.id"
          :resv="r"
          :now="now"
          :busy="busy?.id === r.id ? busy.kind : null"
          @checkin="checkin(r)"
          @cancel="askCancel(r)"
        />
      </div>
      <RefreshedNote v-if="data" :at="refreshedAt" :epaper="false" />
    </main>
    <!-- 둘 다 확인을 거친다 — 신청 취소는 행이 지워진다는 것을 적는다 (student-room.md §취소와 철회) -->
    <Modal
      :open="confirming !== null"
      :title="withdraw ? '신청 취소' : '예약 취소'"
      size="sm"
      @close="closeModal"
    >
      <p class="me__confirm">
        {{
          withdraw ? '신청을 거두면 기록이 남지 않습니다.' : '취소하면 문 앞 화면에서도 지워져요.'
        }}
      </p>
      <template #footer>
        <Button variant="secondary" @click="closeModal">닫기</Button>
        <Button variant="danger" @click="confirmCancel">{{
          withdraw ? '신청 취소' : '예약 취소'
        }}</Button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.me__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-width: 640px;
  margin: 0 auto;
  padding: var(--space-4);
}
.me__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.me__confirm {
  margin: 0;
}
</style>
