import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import AuthShell from '@/auth/AuthShell.vue'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/', component: {} }],
})
const mountShell = (surface: 'student' | 'admin') =>
  mount(AuthShell, {
    props: { title: '로그인', surface },
    slots: { default: '<form class="auth-form"></form>' },
    global: { plugins: [router] },
  })

describe('AuthShell — 학생 PC 는 좌우 분할(소개 패널 + 폼)', () => {
  it('학생은 소개 패널을 그린다 — 한 줄 소개와 기능 셋, 제목(h1)은 폼 쪽 하나', () => {
    const w = mountShell('student')
    const intro = w.get('aside.auth__intro')
    expect(intro.text()).toContain('학교의 빈 강의실을 확인하고 예약하세요.')
    expect(intro.findAll('li').map((li) => li.text())).toEqual([
      '지금 빈 강의실',
      '이번 주 시간표',
      '예약 신청·승인',
    ])
    expect(w.findAll('h1')).toHaveLength(1)
    expect(w.get('h1').text()).toBe('로그인')
  })

  it('로그인 전에는 학교를 모른다 — 학교 이름 없이 서비스 이름(ESC)만', () => {
    const w = mountShell('student')
    expect(w.get('.auth__intro-brand').text()).toBe('ESC')
    expect(w.get('.auth__brand').text()).toBe('ESC')
    expect(w.text()).not.toContain('MJC')
  })

  it('넓은 폭 왼쪽의 ESC 는 메인 페이지 / 로 가는 링크 — 관리자 앱에서도 페이지를 새로 연다 (auth.md, #87)', () => {
    const a = mountShell('student').get('.auth__intro-brand a')
    expect(a.attributes('href')).toBe('/')
    expect(a.text()).toBe('ESC')
  })

  it('home 이면 폼 위 이름이 ‹ ESC — ‹ 는 / 로. 아니면 ‹ 없이 ESC (로그인 화면만)', () => {
    const home = mount(AuthShell, {
      props: { title: '로그인', surface: 'student', home: true },
      global: { plugins: [router] },
    })
    expect(home.get('a.auth__home').attributes('href')).toBe('/')
    expect(home.get('.auth__brand').text()).toContain('ESC')
    expect(mountShell('student').find('a.auth__home').exists()).toBe(false)
  })

  it('titleHidden 이면 h1 은 남기고 화면에서만 숨긴다 — 다른 화면은 그대로 보인다', () => {
    const hidden = mount(AuthShell, {
      props: { title: '로그인', surface: 'student', titleHidden: true },
      global: { plugins: [router] },
    })
    expect(hidden.get('h1').text()).toBe('로그인')
    expect(hidden.get('h1').classes()).toContain('auth__title--sr')
    expect(mountShell('student').get('h1').classes()).not.toContain('auth__title--sr')
  })

  it('tabs 슬롯은 제목 위 — 탭 줄 다음에 h1', () => {
    const w = mount(AuthShell, {
      props: { title: '로그인', surface: 'student' },
      slots: { tabs: '<nav class="t"></nav>' },
      global: { plugins: [router] },
    })
    const html = w.get('.auth__card').html()
    expect(html.indexOf('class="t"')).toBeLessThan(html.indexOf('<h1'))
  })

  it('학생 치수(data-surface) — 관리자 앱(admin 치수)에서 열려도 같은 크기', () => {
    expect(mountShell('student').get('.auth').attributes('data-surface')).toBe('student')
  })
})
