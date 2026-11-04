<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import { LOGOS, layoutLogos, riverCoverEdge } from '@/components/domain/logoRiver'
import {
  advance,
  bodyTransform,
  createWorld,
  ensureWidth,
  grab,
  hitTest,
  moveGrab,
  pointerVelocity,
  release,
  WRAP_MARGIN,
} from './riverPhysics'

// 메인 페이지 PC 전용 — 로고를 잡고 던지는 판. 포인터는 히어로(surface)에서 받는다.
// 프레임마다 Vue 를 거치지 않고 transform 만 쓴다
const props = defineProps<{ surface: HTMLElement | null }>()

const H = 720
const BASE_W = 2000
// 덮개가 반쯤 옅어진 곳부터 잡힌다 — 안 보이는 로고가 잡히면 안 된다
const GRAB_FROM_COVER = 140
const SAMPLE_KEEP_MS = 150
const NOT_LOGO = 'a, button, h1, h2, p, input, label'

const W = Math.max(BASE_W, (window.screen?.width ?? 0) + 2 * WRAP_MARGIN)
const logos = layoutLogos(LOGOS, { W, H, k: 1 })
const world = createWorld(logos, W, H)

const root = ref<HTMLElement>()
const imgs: HTMLImageElement[] = []
const paused = ref(false)

let onScreen = true
let raf = 0
let last = 0
let samples: { t: number; x: number; y: number }[] = []

function paint() {
  world.bodies.forEach((b, i) => {
    if (imgs[i]) imgs[i].style.transform = bodyTransform(b, world.t)
  })
}

function frame(now: number) {
  raf = 0
  if (last) {
    if (props.surface) ensureWidth(world, props.surface.clientWidth)
    advance(world, (now - last) / 1000)
    paint()
  }
  last = now
  sync()
}

/** 돌아야 할 때만 다음 프레임을 건다 */
function sync() {
  const run = !paused.value && onScreen && !document.hidden
  if (run && !raf) {
    raf = requestAnimationFrame(frame)
  } else if (!run) {
    if (raf) cancelAnimationFrame(raf)
    raf = 0
    last = 0
  }
}

function at(e: MouseEvent) {
  const rect = props.surface!.getBoundingClientRect()
  return { x: e.clientX - rect.left, y: e.clientY - rect.top }
}

function logoUnder(e: PointerEvent) {
  if (paused.value || e.pointerType !== 'mouse') return -1
  if ((e.target as Element | null)?.closest?.(NOT_LOGO)) return -1
  const p = at(e)
  return hitTest(world, p.x, p.y, riverCoverEdge(props.surface!.clientWidth) + GRAB_FROM_COVER)
}

function setCursor(value: string) {
  const el = props.surface
  if (el) el.style.cursor = value
}

function onDown(e: PointerEvent) {
  if (e.button !== 0) return
  const i = logoUnder(e)
  if (i < 0) return
  e.preventDefault() // 글자 선택이 시작되지 않게
  props.surface!.setPointerCapture(e.pointerId)
  const p = at(e)
  grab(world, i, p.x, p.y)
  samples = [{ t: e.timeStamp, ...p }]
  setCursor('grabbing')
}

function onMove(e: PointerEvent) {
  if (world.held < 0) {
    setCursor(logoUnder(e) >= 0 ? 'grab' : '')
    return
  }
  const p = at(e)
  moveGrab(world, p.x, p.y, props.surface!.clientWidth)
  samples.push({ t: e.timeStamp, ...p })
  samples = samples.filter((s) => e.timeStamp - s.t <= SAMPLE_KEEP_MS)
}

function onUp(e: PointerEvent) {
  if (world.held < 0) return
  const v = pointerVelocity(samples, e.timeStamp)
  release(world, v.vx, v.vy)
  if (props.surface?.hasPointerCapture(e.pointerId)) {
    props.surface.releasePointerCapture(e.pointerId)
  }
  setCursor(logoUnder(e) >= 0 ? 'grab' : '')
}

/** 창 전환 · 취소 — 손에 붙어 남지 않게 속도 0으로 놓는다 */
function drop() {
  if (world.held < 0) return
  release(world, 0, 0)
  setCursor('')
}

const SURFACE_EVENTS = [
  ['pointerdown', onDown],
  ['pointermove', onMove],
  ['pointerup', onUp],
  ['pointercancel', drop],
  ['lostpointercapture', drop],
] as const

function attach(el: HTMLElement) {
  for (const [type, fn] of SURFACE_EVENTS) el.addEventListener(type, fn as EventListener)
}
function detach(el: HTMLElement) {
  for (const [type, fn] of SURFACE_EVENTS) el.removeEventListener(type, fn as EventListener)
  el.style.cursor = ''
}

watch(
  () => props.surface,
  (el, old) => {
    if (old) detach(old)
    if (el) attach(el)
  },
  { immediate: true },
)

function togglePause() {
  paused.value = !paused.value
  if (paused.value) {
    drop()
    setCursor('')
  }
  sync()
}

let observer: IntersectionObserver | undefined

onMounted(() => {
  paint()
  window.addEventListener('blur', drop)
  document.addEventListener('visibilitychange', sync)
  if (typeof IntersectionObserver === 'function' && root.value) {
    observer = new IntersectionObserver((entries) => {
      onScreen = entries[entries.length - 1].isIntersecting
      sync()
    })
    observer.observe(root.value)
  }
  sync()
})

onBeforeUnmount(() => {
  if (raf) cancelAnimationFrame(raf)
  raf = 0
  // sync 가 다시 걸지 않게
  paused.value = true
  window.removeEventListener('blur', drop)
  document.removeEventListener('visibilitychange', sync)
  observer?.disconnect()
  if (props.surface) detach(props.surface)
  world.held = -1
})
</script>

<template>
  <div ref="root" class="river river--physics">
    <div class="river__field" aria-hidden="true">
      <img
        v-for="(l, i) in logos"
        :key="l.slug"
        :ref="(el) => (imgs[i] = el as HTMLImageElement)"
        class="river__logo"
        :src="l.url"
        :style="{ width: `${l.w}px`, height: `${l.h}px` }"
        alt=""
        draggable="false"
      />
    </div>
    <Button
      class="river__pause"
      variant="secondary"
      :aria-label="paused ? '로고 흐름 재생' : '로고 흐름 멈춤'"
      @click="togglePause"
    >
      {{ paused ? '재생' : '멈춤' }}
    </Button>
  </div>
</template>

<style scoped>
.river {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}
.river__field {
  position: absolute;
  inset: 0;
}
.river__logo {
  position: absolute;
  top: 0;
  left: 0;
  object-fit: contain;
  user-select: none;
  will-change: transform;
}
.river__pause {
  position: absolute;
  right: var(--space-4);
  bottom: var(--space-4);
  pointer-events: auto;
}
</style>
