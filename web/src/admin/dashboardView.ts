import { FAILED_LIMIT } from '@/api/admin'
import type { LatencyBin, LatencyOut, OutboxOut, OutboxState } from '@/api/types'
import type { HistogramBucket } from '@/components/chart/Histogram.vue'
import { formatHm, formatKst } from '@/lib/time'

/** 기간 — 기본은 시안의 최근 7일. 서버 상한 90일 (S10 §4.3) */
export const PERIODS = [
  { value: 7, label: '최근 7일' },
  { value: 30, label: '최근 30일' },
  { value: 90, label: '최근 90일' },
]
export const RECENT_LIMIT = 7

const nf = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 1 })
/** 소수 한 자리까지, 천 단위 쉼표 — 25 → "25", 18.44 → "18.4", 1234 → "1,234" */
export const fmt1 = (v: number) => nf.format(v)

/** 서버 bin 경계 그대로 — 화면이 버킷을 만들지 않는다 (admin-dashboard.md) */
export const binLabel = (b: LatencyBin) => (b.lt == null ? `${b.ge}+` : `${b.ge}–${b.lt}`)

export interface Kpi {
  label: string
  value: string
  unit?: string
  sub?: string
  tone: 'neutral' | 'danger'
}

/** KPI 4 — 추세 화살표 없이 목표와 판정을 문장으로. 전송 0건이면 — (0건과 0%는 다른 말이다) */
export function kpis(l: LatencyOut, failed: number, days: number): Kpi[] {
  const has = l.n > 0
  const pct = (r: number) => fmt1(r * 100)
  return [
    has
      ? {
          label: 'p50 반영 지연',
          value: fmt1(l.p50 ?? 0),
          unit: '초',
          sub: `p95 ${fmt1(l.p95 ?? 0)}초 · 최대 ${fmt1(l.max ?? 0)}초`,
          tone: 'neutral',
        }
      : { label: 'p50 반영 지연', value: '—', sub: '전송 기록 없음', tone: 'neutral' },
    has
      ? {
          label: '30초 이내 비율',
          value: pct(l.within_30s),
          unit: '%',
          sub: `목표 95% · ${l.within_30s >= 0.95 ? '충족' : '미달'}`,
          tone: 'neutral',
        }
      : { label: '30초 이내 비율', value: '—', sub: '목표 95%', tone: 'neutral' },
    // 웨이크 수신률 대신 (서버 지표 없음 — spec §9)
    has
      ? {
          label: '90초 이내 비율',
          value: pct(l.within_90s),
          unit: '%',
          sub: `목표 전부 · ${l.within_90s >= 1 ? '충족' : '미달'}`,
          tone: 'neutral',
        }
      : { label: '90초 이내 비율', value: '—', sub: '목표 전부', tone: 'neutral' },
    {
      label: '전송 실패',
      value: failed >= FAILED_LIMIT ? `${fmt1(FAILED_LIMIT)}+` : fmt1(failed),
      unit: '건',
      sub: `최근 ${days}일 · 모든 작업`,
      tone: failed > 0 ? 'danger' : 'neutral',
    },
  ]
}

/** 두 계열(SLOT_SET·RESV_SET)을 bucket 별로 묶고, SLA 30초 선은 ge=30 bin 의 왼쪽 경계 */
export function histogram(slot: LatencyOut, resv: LatencyOut) {
  const buckets: HistogramBucket[] = slot.bins.map((b, i) => ({
    label: binLabel(b),
    values: [b.count, resv.bins[i]?.count ?? 0],
  }))
  const at = slot.bins.findIndex((b) => b.ge === 30)
  return { buckets, marker: at >= 0 ? { at, label: 'SLA 30초' } : undefined }
}

const TYPE_LABEL: Record<string, string> = {
  SLOT_SET: '시간표',
  SLOT_DEL: '시간표 삭제',
  DAY_CLEAR: '하루 비움',
  RESV_SET: '예약',
  RESV_DEL: '예약 삭제',
  EXAM_SET: '시험기간',
  EXAM_DEL: '시험기간 삭제',
  FILE: '전체 동기화',
  CMD: '명령',
  SET_ROOM: '강의실 배정',
}

export interface RecentRow {
  id: number
  time: string
  when: string
  room: string
  kind: string
  delay: string
  slow: boolean
  failed: boolean
  state: OutboxState
}

/** 최근 전송 — 서버는 id 오름차순, 화면은 최신이 위. 지연은 acked 만(서버 analytics 와 같은 식: finished − created, 음수 0) */
export function recentRows(list: OutboxOut[]): RecentRow[] {
  return [...list].reverse().map((o) => {
    const secs =
      o.state === 'acked' && o.finished_at
        ? Math.max(0, (o.finished_at.getTime() - o.created_at.getTime()) / 1000)
        : null
    return {
      id: o.id,
      time: formatHm(o.created_at),
      when: formatKst(o.created_at),
      room: `${o.bld} ${o.room}`,
      kind: TYPE_LABEL[o.type] ?? o.type,
      delay:
        secs != null
          ? `${fmt1(secs)}초`
          : o.state === 'failed'
            ? '실패'
            : o.state === 'cancelled'
              ? '취소'
              : '대기',
      // 느린 것은 실패가 아니다 — bold 로만 (적색 아님)
      slow: secs != null && secs > 30,
      failed: o.state === 'failed',
      state: o.state,
    }
  })
}
