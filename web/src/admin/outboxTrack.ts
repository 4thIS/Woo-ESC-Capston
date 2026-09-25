import { reactive } from 'vue'
import { ApiError } from '@/api/client'
import { loraApi } from '@/api/lora'
import { roomsApi } from '@/api/rooms'
import type { OutboxOut } from '@/api/types'
import type { DotState } from '@/components/domain/OutboxDot.vue'
import { showToast } from '@/components/ui/toast'
import { usePolling } from '@/lib/usePolling'

/** 저장 뒤 이만큼 따라간다 (spec §4.3). 새로고침하면 끊긴다 — 합의 */
export const TRACK_MS = 30_000
export const TRACK_EVERY_MS = 3_000

/** 관리자 취소는 두 모양 — queued 에서 'cancelled', dispatched 뒤엔 'failed' + last_error 'cancelled'. 같게 그린다 */
export const dotOf = (o: Pick<OutboxOut, 'state' | 'last_error'>): DotState =>
  o.state === 'failed' && o.last_error === 'cancelled' ? 'cancelled' : o.state

const RANK: DotState[] = ['failed', 'cancelled', 'queued', 'dispatched', 'acked']
/** 한 저장이 여러 작업(유닛 둘 등)을 만들면 가장 덜 끝난 것 — 실패가 하나라도 있으면 실패 */
export const worst = (states: DotState[]): DotState =>
  RANK.find((s) => states.includes(s)) ?? 'queued'

/** 화면 하나가 쓰는 추적기 — 행 key 마다 점 상태. 건물 outbox(최신 500)를 3초마다 읽는다 */
export function useOutboxTracker() {
  const states = reactive(new Map<string, DotState>())
  const live = new Map<string, { buildingId: number; ids: number[]; until: number }>()

  /** 빈 ids(7일 창 밖 예약)는 추적하지 않는다 — '예정'은 화면이 pushed_at·날짜로 그린다 */
  function track(key: string, buildingId: number, ids: number[]) {
    live.delete(key)
    states.delete(key)
    if (!ids.length) return
    states.set(key, 'queued')
    live.set(key, { buildingId, ids, until: Date.now() + TRACK_MS })
  }

  async function poll() {
    for (const [k, t] of live) if (Date.now() > t.until) live.delete(k) // 점은 마지막 상태로 남는다
    if (!live.size) return
    const byId = new Map<number, OutboxOut>()
    for (const b of new Set([...live.values()].map((t) => t.buildingId))) {
      try {
        for (const o of await roomsApi.buildingOutbox(b)) byId.set(o.id, o)
      } catch (e) {
        if (!(e instanceof ApiError)) throw e // 끊김 — 다음 틱에 다시
      }
    }
    for (const [k, t] of live) {
      const rows = t.ids.map((i) => byId.get(i)).filter((o): o is OutboxOut => !!o)
      if (!rows.length) continue
      const s = worst(rows.map(dotOf))
      states.set(k, s)
      if (s !== 'queued' && s !== 'dispatched') live.delete(k)
    }
  }
  usePolling(poll, TRACK_EVERY_MS)

  /** 실패·취소 행의 재전송 — 방 단위 (POST /rooms/{id}/sync: 시간표·예약·시험기간 전부) */
  async function resync(key: string, roomId: number, buildingId: number) {
    try {
      const r = await loraApi.syncRoom(roomId)
      track(key, buildingId, r.outbox_ids)
      showToast({ message: '다시 보냈습니다.' })
    } catch (e) {
      if (!(e instanceof ApiError)) throw e
      if (e.status !== 401 && e.status !== 403) showToast({ tone: 'danger', message: e.message })
    }
  }

  return { states, track, resync }
}
