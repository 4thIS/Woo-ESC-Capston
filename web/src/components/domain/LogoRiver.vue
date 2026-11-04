<script setup lang="ts">
import { computed } from 'vue'
import { LOGOS, layoutLogos } from './logoRiver'

// 대학 로고가 오른쪽에서 왼쪽으로 흐르기만 하는 판 — 메인(폰·태블릿·터치)과 인증 화면.
// 잡고 던지는 판은 메인 PC 전용 LogoRiverPhysics. 움직임 줄이기는 base.css 전역 규칙이 끈다
const props = defineProps<{ k: number; height: number }>()

// 긴 로고의 반폭보다 커서, 두 벌이 이어지는 곳이 화면에 보이지 않는다
const MARGIN = 200
const BASE_W = 2000
const BASE_SPEED = 40
const MIN_SPEED_K = 0.7

const margin = computed(() => MARGIN * props.k)
const W = computed(() => Math.max(BASE_W * props.k, (window.screen?.width ?? 0) + margin.value))
const logos = computed(() => layoutLogos(LOGOS, { W: W.value, H: props.height, k: props.k }))
const trackStyle = computed(() => ({
  width: `${W.value * 2}px`,
  animationDuration: `${W.value / (BASE_SPEED * Math.max(props.k, MIN_SPEED_K))}s`,
}))
const copies = computed(() =>
  [0, 1].flatMap((n) =>
    logos.value.map((l) => ({
      key: `${n}-${l.slug}`,
      src: l.url,
      style: {
        left: `${l.x - l.w / 2 + n * W.value - margin.value}px`,
        top: `${l.y - l.h / 2}px`,
        width: `${l.w}px`,
        height: `${l.h}px`,
        animationDuration: `${l.d}s`,
        animationDelay: `${l.dl}s`,
      },
    })),
  ),
)
</script>

<template>
  <div class="river" aria-hidden="true">
    <div class="river__track" :style="trackStyle">
      <img
        v-for="c in copies"
        :key="c.key"
        class="river__logo"
        :src="c.src"
        :style="c.style"
        alt=""
        draggable="false"
      />
    </div>
  </div>
</template>

<style scoped>
.river {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}
.river__track {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  animation: river-drift 50s linear infinite;
}
.river__logo {
  position: absolute;
  object-fit: contain;
  animation: river-bob 5s ease-in-out infinite alternate;
}
@keyframes river-drift {
  to {
    transform: translateX(-50%);
  }
}
@keyframes river-bob {
  from {
    transform: translateY(-7px) scale(0.985);
  }
  to {
    transform: translateY(7px) scale(1.015);
  }
}
</style>
