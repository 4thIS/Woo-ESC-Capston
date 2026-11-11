import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import LandingView from '@/student/views/landing/LandingView.vue'

async function mountLanding() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: ['/', '/login', '/signup', '/policies/:doc'].map((path) => ({ path, component: {} })),
  })
  await router.push('/')
  await router.isReady()
  return mount(LandingView, { global: { plugins: [router] } })
}

function stubMedia(matching: string[]) {
  vi.stubGlobal('matchMedia', (q: string) => ({
    matches: matching.includes(q),
    addEventListener: () => {},
    removeEventListener: () => {},
  }))
}
const PC = '(min-width: 1024px) and (hover: hover) and (pointer: fine)'
const WIDE = '(min-width: 1024px)'

describe('메인 페이지 (landing.md)', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('히어로 — 제목은 h1 하나, 로그인(brand 채움은 이 하나)·가입 신청, 보조 문구와 미리보기 없음', async () => {
    const w = await mountLanding()
    expect(w.findAll('h1').map((h) => h.text())).toEqual(['빈 강의실, 폰으로 바로 확인하세요.'])
    const hero = w.get('.hero')
    expect(hero.text()).toContain('강의실 시간표 · 예약')
    expect(hero.text()).not.toContain('관리자 승인 뒤 이용')
    expect(hero.findAll('[role="img"]')).toHaveLength(0)
    expect(hero.get('a.cta--primary').attributes('href')).toBe('/login')
    expect(hero.get('a.cta--secondary').attributes('href')).toBe('/signup')
    expect(w.findAll('a.cta--primary')).toHaveLength(1)
  })

  it('matchMedia 없으면 흐르기만 하는 판(폰 배율), 넓은 터치 화면은 배율 1, 마우스 PC 는 잡는 판', async () => {
    const phone = await mountLanding()
    expect(phone.get('.hero .river').classes()).not.toContain('river--physics')
    expect(phone.get('.hero .river__track').attributes('style')).toContain('width: 2240px')
    phone.unmount()

    stubMedia([WIDE])
    const touch = await mountLanding()
    expect(touch.get('.hero .river').classes()).not.toContain('river--physics')
    expect(touch.get('.hero .river__track').attributes('style')).toContain('width: 4000px')
    touch.unmount()

    stubMedia([WIDE, PC])
    const pc = await mountLanding()
    expect(pc.get('.hero .river').classes()).toContain('river--physics')
    pc.unmount()
  })

  it('움직임 줄이기면 PC 에서도 잡는 판을 쓰지 않는다', async () => {
    stubMedia([WIDE, PC, '(prefers-reduced-motion: reduce)'])
    const w = await mountLanding()
    expect(w.get('.hero .river').classes()).not.toContain('river--physics')
    w.unmount()
  })

  it('헤더 왼쪽은 ESC 로고(높이 20), 바닥글 문장 안의 ESC 는 글자 그대로 (logo.md)', async () => {
    const w = await mountLanding()
    const img = w.get('header img')
    expect(img.attributes('alt')).toBe('ESC')
    expect(img.attributes('height')).toBe('20')
    expect(w.get('header').text()).not.toContain('ESC')
    expect(w.get('footer').text()).toContain('ESC — 전자종이')
  })

  it('바닥글에 로고 고지 한 줄', async () => {
    const w = await mountLanding()
    expect(w.get('footer').text()).toContain(
      '표시된 로고는 각 대학의 상표이며, 제휴나 도입을 뜻하지 않습니다.',
    )
  })

  it('시간표 미리보기 블록 라벨은 두 글자 — 넓은 화면 요일 칸에서 잘리지 않게 (#101)', async () => {
    const w = await mountLanding()
    const labels = w.findAll('.wp__label').map((l) => l.text())
    expect(labels).toContain('예약')
    expect(labels.every((l) => l.length === 2)).toBe(true)
    expect(w.get('.wp__block--mine').text()).toBe('예약')
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
    // 카드 1은 3행(★ 하나, 사용중 둘 — 수업중·시험중)
    const [card] = previews
    expect(card.findAll('.lr')).toHaveLength(3)
    expect(card.text()).toContain('수업중')
    expect(card.text()).toContain('시험중')
    expect(card.findAll('.lr__star--on')).toHaveLength(1)
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

  it('바닥글에 이용약관 · 개인정보 처리방침 — 언제든 열 수 있게', async () => {
    const w = await mountLanding()
    const links = w.get('footer').findAll('a')
    expect(links.map((a) => [a.text(), a.attributes('href')]).slice(0, 2)).toEqual([
      ['이용약관', '/policies/terms'],
      ['개인정보 처리방침', '/policies/privacy'],
    ])
  })

  it('관리자 로그인은 바닥글 링크 하나 — 관리자 앱이라 페이지를 새로 연다(<a href>)', async () => {
    const w = await mountLanding()
    const a = w.get('footer a.foot__admin')
    expect(a.text()).toBe('관리자 로그인')
    expect(a.attributes('href')).toBe('/admin/login')
  })
})
