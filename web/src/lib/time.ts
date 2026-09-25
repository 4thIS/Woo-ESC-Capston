// 서버 *_at 은 Z 없는 naive UTC (S4a §3.4). 해석은 api/client 가 이 함수로 한 번만, 표시는 KST 로만.
const TZ = 'Asia/Seoul'
const HAS_ZONE = /(Z|[+-]\d\d:?\d\d)$/

export function parseUtc(v: string): Date {
  return new Date(HAS_ZONE.test(v) ? v : `${v}Z`)
}

const parts = new Intl.DateTimeFormat('en-CA', {
  timeZone: TZ,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

function kst(d: Date) {
  const p = Object.fromEntries(parts.formatToParts(d).map((x) => [x.type, x.value]))
  return { y: p.year, mo: p.month, d: p.day, h: p.hour, mi: p.minute }
}

export function formatKst(d: Date): string {
  const k = kst(d)
  return `${k.y}-${k.mo}-${k.d} ${k.h}:${k.mi}`
}

export function formatHm(d: Date): string {
  const k = kst(d)
  return `${k.h}:${k.mi}`
}

const KST_MS = 9 * 3600_000
const kstDay = (d: Date) => Math.floor((d.getTime() + KST_MS) / 86_400_000)

/** KST 달력 날짜 'YYYY-MM-DD' (+offsetDays). 분석 API 의 from·to 가 KST 날짜다 (S10 §4.3) */
export function kstDateStr(d: Date, offsetDays = 0): string {
  return new Date((kstDay(d) + offsetDays) * 86_400_000).toISOString().slice(0, 10)
}

export function relativeKo(d: Date, now: Date = new Date()): string {
  const sec = (now.getTime() - d.getTime()) / 1000
  if (sec < 60) return '방금'
  const days = kstDay(now) - kstDay(d)
  if (days === 0)
    return sec < 3600 ? `${Math.floor(sec / 60)}분 전` : `${Math.floor(sec / 3600)}시간 전`
  if (days === 1) return '어제'
  if (days < 7) return `${days}일 전`
  const k = kst(d)
  return `${Number(k.mo)}월 ${Number(k.d)}일`
}
