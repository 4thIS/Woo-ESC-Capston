import { afterEach, describe, expect, it } from 'vitest'
import { enableAutoUnmount } from '@vue/test-utils'
import { GUIDE_STEPS, swipeStep } from '@/student/guide'
import GuideView from '@/student/views/GuideView.vue'
import { mountAt } from './support'

enableAutoUnmount(afterEach)
const mountGuide = async () => (await mountAt(GuideView, '/guide', '/guide')).w
type W = Awaited<ReturnType<typeof mountGuide>>
const stepButtons = (w: W) => w.findAll('.gd__steps button')
const btn = (w: W, text: string) => w.findAll('button').find((b) => b.text() === text)!

describe('이용 안내 — /guide (student-room.md 「학생 앱 메뉴 · 이용 안내」)', () => {
  it('다섯 장 — 사진 · 제목 · 설명 · 팁 둘, 단계 목록, 첫 장은 이전 잠금', async () => {
    const w = await mountGuide()
    expect(GUIDE_STEPS).toHaveLength(5)
    expect(stepButtons(w).map((b) => b.text())).toEqual([
      '1강의실 고르기',
      '2시간표 보기',
      '3예약 신청',
      '4승인 · 체크인',
      '5문 앞 화면',
    ])
    expect(w.get('.gd__title').text()).toBe('지금 비어 있는 곳부터')
    expect(w.get('.gd__count').text()).toBe('1 / 5 · 강의실 탭')
    expect(w.findAll('.gd__tips li')).toHaveLength(2)
    expect(w.get('.gd__img').attributes('alt')).toContain('강의실 목록')
    expect(stepButtons(w)[0].attributes('aria-current')).toBe('step')
    expect(btn(w, '이전').attributes('disabled')).toBeDefined()
    expect(w.get('.gd__text').attributes('aria-live')).toBe('polite')
  })

  it('다음 · 단계 목록 · 점으로 넘기고, 마지막 장의 처음으로는 1장으로', async () => {
    const w = await mountGuide()
    await btn(w, '다음').trigger('click')
    expect(w.get('.gd__title').text()).toBe('들어가 보면, 오늘 하루가 한눈에')
    expect(stepButtons(w)[1].attributes('aria-current')).toBe('step')
    await stepButtons(w)[4].trigger('click')
    expect(w.find('.gd__frame--door').exists()).toBe(true)
    expect(btn(w, '처음으로')).toBeTruthy()
    await btn(w, '처음으로').trigger('click')
    expect(w.get('.gd__count').text()).toBe('1 / 5 · 강의실 탭')
    await w.findAll('.gd__dots button')[2].trigger('click')
    expect(w.get('.gd__count').text()).toBe('3 / 5 · 예약 화면')
    await btn(w, '이전').trigger('click')
    expect(w.get('.gd__count').text()).toBe('2 / 5 · 강의실 화면')
  })

  it('사진을 옆으로 밀면 넘긴다 — 50px 넘게, 세로보다 가로가 클 때만', async () => {
    expect(swipeStep(-80, 10)).toBe(1)
    expect(swipeStep(80, 10)).toBe(-1)
    expect(swipeStep(-40, 0)).toBe(0)
    expect(swipeStep(-60, 90)).toBe(0)
    const w = await mountGuide()
    const fig = w.get('.gd__figure')
    await fig.trigger('pointerdown', { clientX: 300, clientY: 100 })
    await fig.trigger('pointerup', { clientX: 200, clientY: 110 })
    expect(w.get('.gd__count').text()).toBe('2 / 5 · 강의실 화면')
    // 첫 장에서 오른쪽으로 밀어도 그대로
    await stepButtons(w)[0].trigger('click')
    await fig.trigger('pointerdown', { clientX: 100, clientY: 100 })
    await fig.trigger('pointerup', { clientX: 250, clientY: 100 })
    expect(w.get('.gd__count').text()).toBe('1 / 5 · 강의실 탭')
  })
})
