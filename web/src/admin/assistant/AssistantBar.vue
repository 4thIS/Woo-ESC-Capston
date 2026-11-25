<script setup lang="ts">
import { computed, nextTick, onScopeDispose, ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import { DAYS } from '@/components/domain/rules'
import { addDays, formatHm, md } from '@/lib/time'
import WeekGrid from '../views/week/WeekGrid.vue'
import { needsNight, needsWeekend, weekBlocks, type Block } from '../weekView'
import DayStrip from './DayStrip.vue'
import { markOf } from './diffMarks'
import { assistantStore } from './store'

// AI 비서 — 지금 화면 위에 내려오는 명령창 (docs/design/screens/admin-assistant.md)
const a = assistantStore()
const { phase, text, sent, turn, preview, error, stale } = a

const input = ref<HTMLInputElement | null>(null)
const answer = ref('')
const view = ref<'before' | 'after'>('after')

const expanded = computed(() => phase.value === 'preview' || phase.value === 'applying')
const editing = computed(() => phase.value === 'input' || phase.value === 'error')
const busy = computed(() => phase.value === 'sending')

// 열리면 입력칸에 — 닫히면 연 버튼(사이드 메뉴)으로 포커스가 돌아간다
let opener: HTMLElement | null = null
watch(phase, async (p, prev) => {
  if (prev === 'closed' && p !== 'closed') opener = document.activeElement as HTMLElement | null
  if (p === 'closed') {
    opener?.focus?.()
    view.value = 'after'
    answer.value = ''
  }
  if (p === 'input' || p === 'error') {
    await nextTick()
    input.value?.focus()
  }
  if (p === 'preview' && prev !== 'applying') {
    view.value = 'after'
    // 바뀐 블록이 보이게 — 09시부터 그리는 격자에서 오후 변경은 아래에 가려 있다
    await nextTick()
    const box = grid.value?.querySelector<HTMLElement>('.wk__scroll')
    const first = box?.querySelector<HTMLElement>('[class*="wk__block--diff-"]')
    if (box && first) {
      const top = first.getBoundingClientRect().top - box.getBoundingClientRect().top
      box.scrollTop = Math.max(0, box.scrollTop + top - 60)
    }
  }
})
const grid = ref<HTMLElement | null>(null)
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && phase.value !== 'closed') a.close()
}
window.addEventListener('keydown', onKey)
onScopeDispose(() => window.removeEventListener('keydown', onKey))

/** Enter = 보내기, 한글 조합 중 Enter 는 보내지 않는다 */
function enter(e: KeyboardEvent, go: () => void) {
  if (e.isComposing || e.keyCode === 229) return
  e.preventDefault()
  go()
}
const sendText = () => void a.send()
function sendAnswer() {
  const v = answer.value
  answer.value = ''
  void a.send(v)
}

// ---- 확인 — 강의실 하나 · 주 하나(1단계) ----
const room = computed(() => preview.value?.rooms[0] ?? null)
const week = computed(() => room.value?.weeks[0] ?? null)
const monday = computed(() => week.value?.week_start ?? '')
const changes = computed(() => week.value?.changes ?? [])
const before = computed(() =>
  week.value
    ? weekBlocks(week.value.before.slots, week.value.before.reservations, monday.value)
    : [],
)
const after = computed(() =>
  week.value ? weekBlocks(week.value.after.slots, week.value.after.reservations, monday.value) : [],
)
const both = computed(() => [...before.value, ...after.value])
const markFor = (b: Block) => markOf(b, changes.value)
const gridMarks = (b: Block) => {
  const m = markFor(b)
  if (!m) return undefined
  // 추가는 수정 쪽에만, 삭제는 기존 쪽에만, 수정은 양쪽 (admin-assistant.md 「변경 표시」)
  if (m.op === 'add' && view.value === 'before') return undefined
  if (m.op === 'remove' && view.value === 'after') return undefined
  return m
}
/** 하루 막대 — 바뀌는 날마다(최대 셋) */
const changedDays = computed(() =>
  [...new Set(both.value.filter((b) => markFor(b)).map((b) => b.day))].sort((x, y) => x - y),
)
const strips = computed(() =>
  changedDays.value.slice(0, 3).map((day) => ({
    day,
    title: `${md(addDays(monday.value, day - 1))}(${DAYS[day - 1]})`,
    before: before.value.filter((b) => b.day === day),
    after: after.value.filter((b) => b.day === day),
  })),
)
const changeCount = computed(() =>
  room.value ? room.value.added + room.value.removed + room.value.changed : 0,
)
const until = computed(() => (preview.value ? formatHm(preview.value.expires_at) : ''))
const blocked = computed(() => !!preview.value?.blockers.length)
const VIEWS = [
  { value: 'before', label: '기존' },
  { value: 'after', label: '수정' },
]
</script>

<template>
  <Transition name="ai-fade">
    <div v-if="phase !== 'closed'" class="ai__backdrop" aria-hidden="true" @click="a.close()" />
  </Transition>
  <Transition name="ai-drop">
    <section
      v-if="phase !== 'closed'"
      class="ai"
      :class="{
        'ai--expanded': expanded,
        'ai--tall': phase === 'ask' || phase === 'error',
      }"
      role="dialog"
      aria-modal="true"
      aria-label="AI 비서"
    >
      <!-- 머리 줄 — 모든 상태 공통 -->
      <div class="ai__head">
        <svg v-if="phase !== 'applied'" class="ai__icon" viewBox="0 0 24 24" aria-hidden="true">
          <path
            d="M12 3l1.8 4.7 4.7 1.8-4.7 1.8L12 16l-1.8-4.7-4.7-1.8 4.7-1.8ZM18.5 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8Z"
          />
        </svg>
        <svg v-else class="ai__icon ai__icon--ok" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M5 12.5l4.5 4.5L19 7.5" />
        </svg>
        <template v-if="editing">
          <label for="ai-input" class="sr-only">AI 비서에게 말하기</label>
          <input
            id="ai-input"
            ref="input"
            v-model="text"
            class="ai__input"
            type="text"
            maxlength="300"
            autocomplete="off"
            placeholder="한 문장으로 말하세요 — 예: 803 금요일 15~18시 특강"
            @keydown.enter="enter($event, sendText)"
          />
          <Button size="sm" :disabled="!text.trim()" @click="sendText">보내기</Button>
        </template>
        <template v-else-if="phase === 'applied'">
          <span class="ai__done" aria-live="polite"
            >적용했습니다. 문 앞 화면으로 보내는 중입니다.</span
          >
        </template>
        <template v-else>
          <span class="ai__sent">{{ sent }}</span>
          <span v-if="busy" class="ai__status">변경 내용을 정리하는 중…</span>
          <span v-else-if="expanded" class="ai__status num">{{ until }} 까지</span>
        </template>
        <Button variant="ghost" size="sm" aria-label="닫기" class="ai__close" @click="a.close()">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </Button>
        <span
          v-if="busy"
          class="ai__progress"
          role="progressbar"
          aria-label="변경 내용을 정리하는 중"
          ><span
        /></span>
      </div>

      <!-- 오류 · 되묻기 — 한 줄 아래 칸 -->
      <p v-if="phase === 'error'" class="ai__panel ai__error" role="alert">{{ error }}</p>
      <div v-if="phase === 'ask'" class="ai__panel" aria-live="polite">
        <p class="ai__q"><b>AI</b> {{ turn?.message }}</p>
        <div class="ai__answer">
          <label for="ai-answer" class="sr-only">답</label>
          <input
            id="ai-answer"
            v-model="answer"
            class="ai__answer-input"
            type="text"
            maxlength="300"
            autocomplete="off"
            @keydown.enter="enter($event, sendAnswer)"
          />
          <Button :disabled="!answer.trim()" @click="sendAnswer">답하기</Button>
          <Button variant="ghost" @click="a.close()">요청 취소</Button>
        </div>
      </div>

      <!-- 확인 — 펼친 창 -->
      <template v-if="expanded && preview && room">
        <div class="ai__body">
          <div class="ai__left">
            <h2 class="ai__title">변경 확인 · {{ room.label }}</h2>
            <p v-if="stale" class="ai__stale">
              확인하는 동안 다른 변경이 있었습니다. 바뀐 내용으로 다시 확인해 주세요.
            </p>
            <ul class="ai__list">
              <li v-for="s in preview.summary" :key="s">{{ s }}</li>
            </ul>
            <div v-if="preview.blockers.length" class="ai__blockers" role="alert">
              <p>적용할 수 없습니다:</p>
              <ul class="ai__list">
                <li v-for="b in preview.blockers" :key="b">{{ b }}</li>
              </ul>
            </div>
            <ul v-if="preview.warnings.length" class="ai__list">
              <li v-for="w in preview.warnings" :key="w">⚠&#xFE0E; {{ w }}</li>
            </ul>
            <ul v-if="preview.notices.length" class="ai__list ai__notice">
              <li v-for="n in preview.notices" :key="n">{{ n }}</li>
            </ul>
            <DayStrip
              v-for="s in strips"
              :key="s.day"
              :title="s.title"
              :before="s.before"
              :after="s.after"
              :marks="markFor"
            />
            <p v-if="changedDays.length > 3" class="ai__notice">
              외 {{ changedDays.length - 3 }}일 — 오른쪽 격자에서 봅니다
            </p>
            <p class="ai__notice">
              적용하면 문 앞 화면으로 보냅니다. {{ until }} 까지 적용하지 않으면 이 확인은
              사라집니다.
            </p>
          </div>
          <div class="ai__right">
            <div class="ai__week">
              <b class="num">{{ md(monday) }}~{{ md(addDays(monday, 6)) }} 주</b>
              <SegmentedControl
                :items="VIEWS"
                :value="view"
                label="보기"
                @update:value="(v) => (view = v as 'before' | 'after')"
              />
            </div>
            <div ref="grid" class="ai__grid">
              <WeekGrid
                :blocks="view === 'before' ? before : after"
                :range-blocks="both"
                :exams="(view === 'before' ? week?.before : week?.after)?.exams ?? []"
                :monday="monday"
                :night="needsNight(both)"
                :weekend="needsWeekend(both)"
                :marks="gridMarks"
              />
            </div>
          </div>
        </div>
        <div class="ai__foot">
          <span class="ai__count"
            >변경 {{ changeCount }}건 · 겹침 {{ preview.warnings.length }}건</span
          >
          <Button variant="secondary" @click="a.close()">취소</Button>
          <Button :disabled="blocked" :loading="phase === 'applying'" @click="a.apply()"
            >적용</Button
          >
        </div>
      </template>
    </section>
  </Transition>
</template>

<style scoped>
/* 본문 영역만 덮는다 — 사이드 메뉴(220px, components.md SidebarNav)는 덮지 않아 AI 비서 버튼으로 닫을 수 있다 */
.ai__backdrop {
  position: fixed;
  inset: 0 0 0 220px;
  z-index: 40;
  background: var(--modal-backdrop);
}
.ai {
  position: fixed;
  top: var(--space-4);
  left: calc(220px + var(--space-5));
  right: var(--space-5);
  z-index: 41;
  display: flex;
  flex-direction: column;
  /* 한 줄(56px + 테두리) ↔ 펼침을 높이로 움직인다 — auto 는 움직이지 않아 한 줄은 고정 높이 */
  height: calc(56px + 2 * var(--border-thin));
  max-height: calc(100vh - var(--space-4) - var(--space-5));
  overflow: hidden;
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
  transition: height var(--dur-slow) var(--ease-soft);
}
/* 확인 — 아래로 펼쳐져 본문을 거의 다 덮는다 (그림자 없음 — 층은 덮개가 진다, tokens.md) */
.ai--expanded {
  height: calc(100vh - var(--space-4) - var(--space-5));
}
/* 되묻기 · 오류 — 아래 칸 높이만큼 */
.ai--tall {
  height: auto;
}
.ai__head {
  position: relative;
  display: flex;
  flex: none;
  align-items: center;
  gap: var(--space-3);
  height: 56px;
  padding: 0 var(--space-3) 0 var(--space-4);
}
.ai__icon {
  flex: none;
  width: 20px;
  height: 20px;
  fill: none;
  stroke: var(--brand);
  stroke-width: 1.7;
  stroke-linejoin: round;
}
.ai__icon--ok {
  stroke: var(--diff-add-text);
  stroke-width: 2;
  stroke-linecap: round;
}
.ai__input {
  flex: 1;
  min-width: 0;
  height: 36px;
  border: 0;
  outline: none;
  background: transparent;
  font: inherit;
  font-size: var(--font-size-lg);
  color: var(--text-1);
}
.ai__sent,
.ai__done {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-size: var(--font-size-lg);
  white-space: nowrap;
  text-overflow: ellipsis;
}
.ai__sent {
  color: var(--text-2);
}
.ai__status {
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
.ai__close {
  margin-left: auto;
}
.ai__close svg {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
}
.ai__progress {
  position: absolute;
  inset: auto 0 0 0;
  height: 2px;
  overflow: hidden;
  background: var(--brand-tint);
}
.ai__progress span {
  display: block;
  width: 30%;
  height: 100%;
  background: var(--brand);
  animation: ai-load 1.1s ease-in-out infinite;
}
@keyframes ai-load {
  from {
    transform: translateX(-100%);
  }
  to {
    transform: translateX(340%);
  }
}
.ai__panel {
  margin: 0;
  padding: var(--space-3) var(--space-4);
  border-top: var(--border-thin) solid var(--line-1);
  background: var(--sunken);
  font-size: var(--font-size-md);
}
.ai__error {
  color: var(--danger);
}
.ai__q {
  margin: 0 0 var(--space-2);
}
.ai__q b {
  margin-right: var(--space-2);
  color: var(--brand);
  font-weight: var(--font-weight-medium);
}
.ai__answer {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}
.ai__answer-input {
  width: 360px;
  height: var(--control-height-md);
  padding: 0 var(--space-3);
  border: var(--border-thin) solid var(--line-3);
  border-radius: var(--radius-md);
  background: var(--surface);
  font: inherit;
  font-size: var(--font-size-md);
}
.ai__body {
  display: grid;
  flex: 1;
  grid-template-columns: 340px minmax(0, 1fr);
  gap: var(--space-5);
  min-height: 0;
  padding: var(--space-2) var(--space-5) var(--space-4);
  border-top: var(--border-thin) solid var(--line-1);
  animation: esc-fade-in var(--dur-base) var(--ease-soft) calc(var(--dur-slow) * 0.6) both;
}
.ai__left {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  min-height: 0;
  padding-top: var(--space-2);
  overflow: auto;
}
.ai__title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.ai__list {
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: var(--font-size-md);
  line-height: var(--leading-normal);
}
.ai__blockers {
  color: var(--danger);
  font-size: var(--font-size-md);
}
.ai__blockers p {
  margin: 0;
}
.ai__notice,
.ai__stale {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
.ai__stale {
  color: var(--text-1);
}
.ai__right {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-height: 0;
}
.ai__week {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--font-size-md);
}
/* 격자 자신의 스크롤 상자가 스크롤한다 — 요일 머리줄(sticky)이 그 상자 기준이라 */
.ai__grid {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}
.ai__grid :deep(.wk__scroll) {
  flex: 1;
  min-height: 0;
  max-height: none;
}
.ai__foot {
  display: flex;
  flex: none;
  align-items: center;
  gap: var(--space-2);
  height: 64px;
  padding: 0 var(--space-5);
  border-top: var(--border-thin) solid var(--line-1);
}
.ai__count {
  margin-right: auto;
  font-size: var(--font-size-md);
  color: var(--text-2);
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
/* 위에서 내려오고 위로 올라간다 */
.ai-drop-enter-active,
.ai-drop-leave-active {
  transition:
    transform var(--dur-base) var(--ease-soft),
    opacity var(--dur-base) ease;
}
.ai-drop-enter-from,
.ai-drop-leave-to {
  transform: translateY(-24px);
  opacity: 0;
}
.ai-fade-enter-active,
.ai-fade-leave-active {
  transition: opacity var(--dur-base) ease;
}
.ai-fade-enter-from,
.ai-fade-leave-to {
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .ai,
  .ai__body,
  .ai-drop-enter-active,
  .ai-drop-leave-active,
  .ai-fade-enter-active,
  .ai-fade-leave-active {
    transition: none;
    animation: none;
  }
}
</style>
