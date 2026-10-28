import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { POLICIES } from '@/student/policies'
import { routes } from '@/student/router'
import PolicyView from '@/student/views/PolicyView.vue'

async function at(path: string) {
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(path)
  await router.isReady()
  return router
}

describe('약관 데이터 — 문서를 하나 넣으면 칩·목록·주소·목차가 같이 생긴다', () => {
  it('이용약관·개인정보 처리방침, 문서·조항 id 는 겹치지 않는다', () => {
    expect(POLICIES.map((p) => [p.id, p.title])).toEqual([
      ['terms', '이용약관'],
      ['privacy', '개인정보 처리방침'],
    ])
    for (const p of POLICIES) {
      expect(p.sections.length).toBeGreaterThan(0)
      expect(new Set(p.sections.map((s) => s.id)).size).toBe(p.sections.length)
    }
  })
})

describe('약관 페이지 /policies/:doc', () => {
  it('로그인 없이 열린다, 없는 문서·/policies 는 이용약관으로', async () => {
    expect((await at('/policies/privacy')).currentRoute.value.matched[0].meta.gate).toBeFalsy()
    expect((await at('/policies')).currentRoute.value.path).toBe('/policies/terms')
    expect((await at('/policies/nope')).currentRoute.value.path).toBe('/policies/terms')
  })

  it('문서 목록은 주소를 가진 링크(지금 문서 aria-current), 목차는 조항 앵커', async () => {
    const router = await at('/policies/privacy')
    const w = mount(PolicyView, { global: { plugins: [router] } })
    const docs = w.get('nav[aria-label="문서"]').findAll('a')
    expect(docs.map((a) => [a.text(), a.attributes('href')])).toEqual([
      ['이용약관', '/policies/terms'],
      ['개인정보 처리방침', '/policies/privacy'],
    ])
    expect(w.get('a[aria-current="page"]').text()).toBe('개인정보 처리방침')
    const doc = POLICIES[1]
    expect(w.get('h2').text()).toBe('개인정보 처리방침')
    expect(w.text()).toContain('시행일')
    const toc = w.findAll('.pol__toc a')
    expect(toc).toHaveLength(doc.sections.length * 2) // 폰(접는 목차)·넓은 폭(왼쪽 목차) 두 벌
    for (const s of doc.sections) {
      expect(w.find(`section#${s.id}`).exists()).toBe(true)
      expect(w.find(`a[href="#${s.id}"]`).exists()).toBe(true)
    }
    expect(w.find('table').exists()).toBe(true) // 처리 항목·보유 기간 표
  })
})
