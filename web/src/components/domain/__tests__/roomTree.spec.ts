import { afterEach, describe, expect, it } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import RoomTree from '@/components/domain/RoomTree.vue'
import { buildTree, checkOf, selectionLabel, toggleGroup } from '@/components/domain/roomTree'
import type { BuildingOut, RoomOut } from '@/api/types'

const B = (id: number, name: string, bld: string): BuildingOut => ({
  id,
  school_id: 1,
  name,
  bld,
  modem_id: null,
})
const R = (id: number, building_id: number, room: number): RoomOut => ({
  id,
  building_id,
  room,
  units: 1,
  reservable: false,
})
const buildings = [B(1, '공학관', 'E'), B(2, '사회관', 'S')]
const rooms = [R(13, 1, 501), R(11, 1, 401), R(12, 1, 402), R(14, 1, 5), R(21, 2, 101)]

describe('roomTree', () => {
  it('건물 → 층(호수 ÷ 100, 100 미만 기타) → 호수 오름차순', () => {
    const t = buildTree(buildings, rooms)
    expect(t[0].floors.map((f) => [f.label, f.rooms.map((r) => r.room)])).toEqual([
      ['기타', [5]],
      ['4층', [401, 402]],
      ['5층', [501]],
    ])
    expect(t[0].ids).toEqual([14, 11, 12, 13])
    expect(t[1].floors[0].label).toBe('1층')
  })

  it('검색은 호수 숫자만 — 맞는 방이 없는 건물은 빠진다', () => {
    const t = buildTree(buildings, rooms, '40')
    expect(t).toHaveLength(1)
    expect(t[0].ids).toEqual([11, 12])
  })

  it('부모 체크 — 일부면 some, 누르면 전부, 전부면 전부 해제 (다른 선택은 그대로)', () => {
    expect(checkOf([11, 12], [11])).toBe('some')
    expect(checkOf([11, 12], [])).toBe('none')
    expect(checkOf([11, 12], [12, 11])).toBe('all')
    expect(toggleGroup([11, 12], [21, 11])).toEqual([21, 11, 12])
    expect(toggleGroup([11, 12], [21, 11, 12])).toEqual([21])
  })

  it('버튼 라벨 — 셋까지 나열, 넷 이상·여러 건물은 "외 N곳", single 은 호', () => {
    expect(selectionLabel(buildings, rooms, [], 'multi')).toBe('강의실 선택')
    expect(selectionLabel(buildings, rooms, [12, 11, 13], 'multi')).toBe('공학관 401 · 402 · 501')
    expect(selectionLabel(buildings, rooms, [14, 11, 12, 13], 'multi')).toBe('공학관 5 외 3곳')
    expect(selectionLabel(buildings, rooms, [21, 11], 'multi')).toBe('공학관 401 외 1곳')
    expect(selectionLabel(buildings, rooms, [21], 'single')).toBe('사회관 101호')
  })
})

describe('RoomTree', () => {
  let w: VueWrapper
  afterEach(() => w?.unmount())
  async function open(props: Record<string, unknown> = {}) {
    w = mount(RoomTree, {
      props: { buildings, rooms, selected: [11], ...props },
      attachTo: document.body,
    })
    await w.get('.tree__trigger').trigger('click')
  }
  const last = () => w.emitted('update:selected')?.at(-1)?.[0]
  const roomRows = () => w.findAll('.tree__row--r').map((r) => r.text())

  it('닫혀 있어도 버튼이 선택을 말한다 — 열면 고른 방의 건물·층이 펼쳐져 있다', async () => {
    await open()
    expect(w.get('.tree__trigger').text()).toContain('공학관 401')
    expect(w.get('.tree__trigger').attributes('aria-expanded')).toBe('true')
    expect(roomRows()).toEqual(['401호', '402호'])
  })

  it('건물을 누르면 그 건물 전체 — 일부만 골라졌으면 indeterminate', async () => {
    await open()
    const b = w.get('.tree__row--b input[type=checkbox]')
    expect((b.element as HTMLInputElement).indeterminate).toBe(true)
    await b.setValue(true)
    expect(last()).toEqual([11, 14, 12, 13])
  })

  it('검색해도 선택은 그대로 — 트리만 줄고, 호수를 누르면 즉시 반영 (확인 버튼 없음)', async () => {
    await open()
    await w.get('input[type=search]').setValue('50')
    expect(roomRows()).toEqual(['501호'])
    expect(w.emitted('update:selected')).toBeUndefined()
    await w.get('.tree__row--r input[type=checkbox]').setValue(true)
    expect(last()).toEqual([11, 13])
    expect(w.find('.tree__panel').exists()).toBe(true)
  })

  it('전체 해제', async () => {
    await open()
    await w.get('.tree__clear').trigger('click')
    expect(last()).toEqual([])
  })

  it('single — 체크박스 없이 호수를 누르면 그 방 하나, 드롭다운이 닫힌다', async () => {
    await open({ mode: 'single' })
    expect(w.find('.tree__panel input[type=checkbox]').exists()).toBe(false)
    await w
      .findAll('.tree__row--r')
      .find((r) => r.text() === '402호')!
      .trigger('click')
    expect(last()).toEqual([12])
    expect(w.find('.tree__panel').exists()).toBe(false)
  })

  it('Esc·바깥 누르기로 닫힌다', async () => {
    await open()
    await w.get('input[type=search]').trigger('keydown', { key: 'Escape' })
    expect(w.find('.tree__panel').exists()).toBe(false)
    await w.get('.tree__trigger').trigger('click')
    document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    await w.vm.$nextTick()
    expect(w.find('.tree__panel').exists()).toBe(false)
  })

  it('방이 많아도(300곳) 검색으로 하나를 찾는다', async () => {
    const many = Array.from({ length: 300 }, (_, i) => R(1000 + i, 1, 100 + i * 4))
    await open({ rooms: many, selected: [] })
    await w.get('input[type=search]').setValue('1196')
    expect(roomRows()).toEqual(['1196호'])
  })
})
