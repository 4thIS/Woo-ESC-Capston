import { afterEach, describe, expect, it } from 'vitest'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { clearSession, session, setSession } from '@/lib/session'
import AccountView from '@/student/views/AccountView.vue'
import { mountAt } from './support'

enableAutoUnmount(afterEach)
afterEach(() => clearSession())

describe('내 정보 — /account (student-room.md 「학생 앱 메뉴 · 이용 안내」)', () => {
  it('이름 · 학교, 약관 둘, 로그아웃은 토큰을 버리고 로그인으로', async () => {
    setSession({
      token: 't',
      role: 'student',
      school_id: 1,
      school_name: '명지전문대학',
      name: '김민준',
    })
    const { w, router } = await mountAt(AccountView, '/account', '/account')
    expect(w.get('.ac__name').text()).toBe('김민준')
    expect(w.get('.ac__school').text()).toBe('명지전문대학')
    expect(w.findAll('.ac__links a').map((a) => [a.text(), a.attributes('href')])).toEqual([
      ['이용약관', '/policies/terms'],
      ['개인정보 처리방침', '/policies/privacy'],
    ])
    await w.get('.ac__logout').trigger('click')
    await flushPromises()
    expect(session.value).toBeNull()
    expect(router.currentRoute.value.path).toBe('/login')
  })
})
