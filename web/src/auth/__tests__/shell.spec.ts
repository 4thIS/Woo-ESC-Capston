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

  it('관리자 로그인은 지금처럼 카드 하나 — 소개 패널 없음', () => {
    expect(mountShell('admin').find('aside.auth__intro').exists()).toBe(false)
  })
})
