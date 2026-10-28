import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import LandingView from '@/student/views/landing/LandingView.vue'

async function mountLanding() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: ['/', '/login', '/signup'].map((path) => ({ path, component: {} })),
  })
  await router.push('/')
  await router.isReady()
  return mount(LandingView, { global: { plugins: [router] } })
}

describe('메인 페이지 (landing.md)', () => {
  it('히어로 — 제목은 h1 하나, 로그인(brand 채움은 이 하나)·가입 신청', async () => {
    const w = await mountLanding()
    expect(w.findAll('h1').map((h) => h.text())).toEqual(['빈 강의실, 폰으로 바로 확인하세요.'])
    const hero = w.get('.hero')
    expect(hero.text()).toContain('강의실 시간표 · 예약')
    expect(hero.text()).toContain('학교 웹메일로 가입 · 관리자 승인 뒤 이용')
    expect(hero.get('a.cta--primary').attributes('href')).toBe('/login')
    expect(hero.get('a.cta--secondary').attributes('href')).toBe('/signup')
    expect(w.findAll('a.cta--primary')).toHaveLength(1)
  })

  it('학교 이름을 쓰지 않는다 — 서버를 부르지 않는 서비스 소개', async () => {
    const w = await mountLanding()
    expect(w.text()).not.toContain('MJC')
    expect(w.text()).not.toContain('명지')
  })

  it('기능 카드 넷 — 로그인 화면 왼쪽 「할 수 있는 일」과 같은 말', async () => {
    const w = await mountLanding()
    expect(w.findAll('.feature h3').map((h) => h.text())).toEqual([
      '지금 빈 강의실',
      '이번 주 시간표',
      '예약 신청',
      '문 앞 화면과 같은 정보',
    ])
  })

  it('미리보기는 눌리지 않는 한 덩어리 그림 — role=img + 이름, 안에 링크·버튼 없음', async () => {
    const w = await mountLanding()
    const previews = w.findAll('[role="img"]')
    expect(previews.map((p) => p.attributes('aria-label'))).toEqual([
      '강의실 목록 예시',
      '강의실 목록 예시',
      '주간 시간표 예시',
      '예약 신청 예시',
      '문 앞 화면 예시',
    ])
    for (const p of previews) expect(p.findAll('a, button')).toHaveLength(0)
    // 문 앞 화면은 시각 대신 요일 — 박힌 시각은 멈춰 틀린 정보가 된다 (terminal-epaper.md 「헤더」)
    const ep = previews.find((p) => p.attributes('aria-label') === '문 앞 화면 예시')!
    const head = ep.get('.ep__head').text()
    expect(head).toContain('목요일')
    expect(head).not.toMatch(/\d{1,2}:\d{2}/)
    // 히어로 4행(★ 하나, 사용중 둘 — 수업중·시험중), 카드 1은 같은 것의 3행
    const [hero, card] = previews
    expect(hero.findAll('.lr')).toHaveLength(4)
    expect(card.findAll('.lr')).toHaveLength(3)
    expect(hero.text()).toContain('수업중')
    expect(hero.text()).toContain('시험중')
    expect(hero.findAll('.lr__star--on')).toHaveLength(1)
  })

  it('시작하는 방법 3단계 — 번호는 칠하지 않는다, 폰용 가입 신청하기', async () => {
    const w = await mountLanding()
    expect(w.findAll('.steps li h3').map((h) => h.text())).toEqual([
      '학교 웹메일로 가입 신청',
      '이름 · 학번 · 비밀번호 입력',
      '관리자 승인 뒤 로그인',
    ])
    expect(w.get('.steps__cta').attributes('href')).toBe('/signup')
  })

  it('관리자 로그인은 바닥글 링크 하나 — 관리자 앱이라 페이지를 새로 연다(<a href>)', async () => {
    const w = await mountLanding()
    const a = w.get('footer a')
    expect(a.text()).toBe('관리자 로그인')
    expect(a.attributes('href')).toBe('/admin/login')
  })
})
