import { computed, onScopeDispose, ref } from 'vue'
import { clearSession, session } from '@/lib/session'

export const IDLE_MS = 10 * 60_000
export const WARN_MS = 60_000
const KEY = 'esc.admin.idle'
const EVENTS = ['pointerdown', 'pointermove', 'keydown', 'wheel', 'touchstart'] as const

/**
 * 관리자 자동 로그아웃 — 마지막 활동에서 10분. 마지막 1분은 경고라 그때부터는 아무 데나 눌러도
 * 연장되지 않고 '시간 연장'만 연장한다(경고를 읽지도 않고 지나치지 않게).
 * 마지막 활동 시각은 토큰과 함께 sessionStorage 에 — 새로고침으로 타이머가 초기화되지 않는다.
 * 폴링 요청은 활동이 아니다(DOM 이벤트만).
 */
const tag = () => session.value?.token.slice(-16) ?? ''
/** 이 토큰의 마지막 활동 시각 — 다른 토큰(새 로그인)의 기록이면 없음 */
function savedAt(): number | null {
  try {
    const saved = JSON.parse(sessionStorage.getItem(KEY) ?? 'null') as {
      t: string
      at: number
    } | null
    return saved?.t === tag() ? saved.at : null
  } catch {
    return null // 저장소가 막힌 창 — 새로고침하면 새로 센다
  }
}

/** 진입점이 마운트 전에 — 마감이 지난 탭을 새로고침하면 화면을 그리기 전에(요청 401 없이) 로그아웃 */
export function expireIfIdle(): void {
  const at = savedAt()
  if (session.value && at !== null && Date.now() - at >= IDLE_MS) clearSession('idle')
}

export function useIdleLogout() {
  const last = savedAt() ?? Date.now()
  const now = ref(Date.now())
  const deadline = ref(last + IDLE_MS)
  const remaining = computed(() => Math.max(0, deadline.value - now.value))
  const warning = computed(() => remaining.value <= WARN_MS)

  function save() {
    try {
      sessionStorage.setItem(KEY, JSON.stringify({ t: tag(), at: deadline.value - IDLE_MS }))
    } catch {
      // 위와 같다
    }
  }
  function expire() {
    stop()
    try {
      sessionStorage.removeItem(KEY)
    } catch {
      // 위와 같다
    }
    clearSession('idle')
  }
  /** 시간은 틱 수가 아니라 벽시계로 — 숨긴 탭은 타이머가 분 단위로 늦어진다 */
  function tick() {
    now.value = Date.now()
    if (now.value >= deadline.value) expire()
  }
  function extend() {
    now.value = Date.now()
    // 돌아와서 한 첫 움직임이 이미 지난 마감을 되살리지 않게 — 먼저 잰다
    if (now.value >= deadline.value) return expire()
    deadline.value = now.value + IDLE_MS
    save()
  }
  function onActivity() {
    // pointermove 는 초당 수십 번 — 1초 안의 연장은 건너뛴다
    if (!warning.value && Date.now() - (deadline.value - IDLE_MS) > 1000) extend()
  }

  save()
  const timer = window.setInterval(tick, 1000)
  for (const e of EVENTS) window.addEventListener(e, onActivity, { passive: true, capture: true })
  document.addEventListener('visibilitychange', tick)
  function stop() {
    window.clearInterval(timer)
    for (const e of EVENTS) window.removeEventListener(e, onActivity, { capture: true })
    document.removeEventListener('visibilitychange', tick)
  }
  onScopeDispose(stop)
  tick()

  return { remaining, warning, extend }
}

/** 09:41 */
export const mmss = (ms: number) => {
  const s = Math.ceil(ms / 1000)
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}
