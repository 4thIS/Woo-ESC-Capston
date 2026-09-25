<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import Badge from '@/components/ui/Badge.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import type { BuildingOut, RoomOut } from '@/api/types'
import { buildTree, checkOf, selectionLabel, toggleGroup } from './roomTree'

const props = withDefaults(
  defineProps<{
    mode?: 'multi' | 'single'
    buildings: BuildingOut[]
    rooms: RoomOut[]
    selected?: number[]
  }>(),
  { mode: 'multi', selected: () => [] },
)
const emit = defineEmits<{ 'update:selected': [ids: number[]] }>()

const open = ref(false)
const query = ref('')
const expanded = ref(new Set<string>())
const root = ref<HTMLElement>()
const tree = computed(() => buildTree(props.buildings, props.rooms, query.value))
const label = computed(() =>
  selectionLabel(props.buildings, props.rooms, props.selected, props.mode),
)
const multi = computed(() => props.mode === 'multi')
// 검색 중이면 전부 펼친다 — 맞는 호수가 접힌 층 안에 숨지 않게
const isOpen = (key: string) => !!query.value.trim() || expanded.value.has(key)
function toggleExpand(key: string) {
  const s = new Set(expanded.value)
  if (s.has(key)) s.delete(key)
  else s.add(key)
  expanded.value = s
}
// 선택은 닫을 때가 아니라 누르는 즉시 반영 — 확인 버튼을 두지 않는다
const set = (ids: number[]) => emit('update:selected', ids)
function pick(id: number) {
  if (!multi.value) {
    set([id])
    open.value = false
    return
  }
  set(
    props.selected.includes(id) ? props.selected.filter((i) => i !== id) : [...props.selected, id],
  )
}

// 열 때 — 고른 방이 있는 건물·층을 펼친다 (아무것도 안 골랐으면 첫 건물)
watch(open, (o) => {
  if (!o) return
  const s = new Set(expanded.value)
  for (const b of buildTree(props.buildings, props.rooms))
    for (const f of b.floors)
      if (f.rooms.some((r) => props.selected.includes(r.id))) {
        s.add(b.key)
        s.add(f.key)
      }
  if (!s.size && props.buildings.length) s.add(`b${props.buildings[0].id}`)
  expanded.value = s
})

// 바깥 클릭·Esc 로 닫힌다
function onDocDown(e: MouseEvent) {
  if (open.value && root.value && !root.value.contains(e.target as Node)) open.value = false
}
document.addEventListener('mousedown', onDocDown)
onScopeDispose(() => document.removeEventListener('mousedown', onDocDown))
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && open.value) {
    e.stopPropagation()
    open.value = false
  }
}
</script>

<template>
  <div ref="root" class="tree" :class="`tree--${mode}`" @keydown="onKey">
    <button
      type="button"
      class="tree__trigger"
      :aria-expanded="open ? 'true' : 'false'"
      aria-haspopup="true"
      @click="open = !open"
    >
      <span class="tree__label">{{ label }}</span>
      <Badge v-if="multi && selected.length" variant="solid" class="num">{{
        selected.length
      }}</Badge>
      <span aria-hidden="true">▾</span>
    </button>
    <div v-if="open" class="tree__panel" role="group" aria-label="강의실 선택">
      <div class="tree__head">
        <span>강의실 선택</span>
        <span v-if="multi" class="num">{{ selected.length }}개 선택</span>
      </div>
      <input
        v-model="query"
        class="tree__search"
        type="search"
        inputmode="numeric"
        placeholder="호수 검색"
        aria-label="호수 검색"
      />
      <ul class="tree__list">
        <li v-for="b in tree" :key="b.key">
          <div class="tree__row tree__row--b">
            <button
              type="button"
              class="tree__caret"
              :aria-expanded="isOpen(b.key) ? 'true' : 'false'"
              :aria-label="`${b.building.name} 펼치기`"
              @click="toggleExpand(b.key)"
            >
              {{ isOpen(b.key) ? '▾' : '▸' }}
            </button>
            <Checkbox
              v-if="multi"
              :model-value="checkOf(b.ids, selected) === 'all'"
              :indeterminate="checkOf(b.ids, selected) === 'some'"
              :disabled="!b.ids.length"
              :label="b.building.name"
              @update:model-value="set(toggleGroup(b.ids, selected))"
            />
            <button v-else type="button" class="tree__name" @click="toggleExpand(b.key)">
              {{ b.building.name }}
            </button>
            <span class="tree__count num">{{ b.ids.length }}</span>
          </div>
          <ul v-if="isOpen(b.key)">
            <li v-for="f in b.floors" :key="f.key">
              <div class="tree__row tree__row--f">
                <button
                  type="button"
                  class="tree__caret"
                  :aria-expanded="isOpen(f.key) ? 'true' : 'false'"
                  :aria-label="`${f.label} 펼치기`"
                  @click="toggleExpand(f.key)"
                >
                  {{ isOpen(f.key) ? '▾' : '▸' }}
                </button>
                <Checkbox
                  v-if="multi"
                  :model-value="
                    checkOf(
                      f.rooms.map((r) => r.id),
                      selected,
                    ) === 'all'
                  "
                  :indeterminate="
                    checkOf(
                      f.rooms.map((r) => r.id),
                      selected,
                    ) === 'some'
                  "
                  :label="f.label"
                  @update:model-value="
                    set(
                      toggleGroup(
                        f.rooms.map((r) => r.id),
                        selected,
                      ),
                    )
                  "
                />
                <button v-else type="button" class="tree__name" @click="toggleExpand(f.key)">
                  {{ f.label }}
                </button>
                <span class="tree__count num">{{ f.rooms.length }}</span>
              </div>
              <ul v-if="isOpen(f.key)">
                <li v-for="r in f.rooms" :key="r.id">
                  <div
                    v-if="multi"
                    class="tree__row tree__row--r"
                    :class="{ 'tree__row--on': selected.includes(r.id) }"
                  >
                    <Checkbox
                      :model-value="selected.includes(r.id)"
                      :label="`${r.room}호`"
                      @update:model-value="pick(r.id)"
                    />
                  </div>
                  <button
                    v-else
                    type="button"
                    class="tree__row tree__row--r tree__room num"
                    :class="{ 'tree__row--on': selected.includes(r.id) }"
                    :aria-current="selected.includes(r.id) ? 'true' : undefined"
                    @click="pick(r.id)"
                  >
                    {{ r.room }}호
                  </button>
                </li>
              </ul>
            </li>
          </ul>
        </li>
        <li v-if="!tree.length" class="tree__empty">
          {{ query.trim() ? '맞는 호수가 없습니다' : '강의실이 없습니다' }}
        </li>
      </ul>
      <div class="tree__foot">
        <button v-if="multi" type="button" class="tree__clear" @click="set([])">전체 해제</button>
        <!-- 층은 서버에 없는 값 — 규칙을 관리자에게도 알린다 -->
        <span>층 = 호수 ÷ 100</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tree {
  position: relative;
}
.tree__trigger {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  max-width: 420px;
  height: var(--control-height-md);
  padding: 0 var(--space-3);
  border: var(--border-thin) solid var(--line-3);
  border-radius: var(--radius-md);
  background: var(--surface);
  color: var(--text-1);
  font: inherit;
  font-weight: var(--font-weight-medium);
  cursor: pointer;
}
.tree__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tree__panel {
  position: absolute;
  z-index: 20;
  top: calc(100% + var(--space-1));
  left: 0;
  width: 320px;
  padding: var(--space-2);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.tree__head {
  display: flex;
  justify-content: space-between;
  padding: var(--space-1) var(--space-2);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
}
.tree__search {
  width: 100%;
  height: var(--control-height-sm);
  margin: var(--space-1) 0 var(--space-2);
  padding: 0 var(--space-2);
  border: var(--border-thin) solid var(--line-3);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-1);
  font: inherit;
}
.tree__list,
.tree__list ul {
  margin: 0;
  padding: 0;
  list-style: none;
}
.tree__list {
  max-height: 420px;
  overflow-y: auto;
}
.tree__row {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  height: 32px;
  padding-right: var(--space-2);
}
/* 들여쓰기 — 건물 8 / 층 26 / 호수 62(multi)·48(single) (components.md) */
.tree__row--b {
  padding-left: 8px;
}
.tree__row--f {
  padding-left: 26px;
}
.tree__row--r {
  padding-left: 62px;
}
.tree--single .tree__row--r {
  padding-left: 48px;
}
.tree__row--on {
  background: var(--brand-tint);
  color: var(--brand);
}
.tree__caret,
.tree__name,
.tree__room,
.tree__clear {
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  cursor: pointer;
}
.tree__caret {
  width: 18px;
  padding: 0;
  color: var(--text-2);
}
.tree__room {
  width: 100%;
  text-align: left;
}
.tree__count {
  margin-left: auto;
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.tree__empty {
  padding: var(--space-3) var(--space-2);
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.tree__foot {
  display: flex;
  justify-content: space-between;
  margin-top: var(--space-2);
  padding: var(--space-2) var(--space-2) 0;
  border-top: var(--border-thin) solid var(--line-1);
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.tree__clear {
  padding: 0;
  color: var(--text-1);
}
</style>
