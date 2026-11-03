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

describe('약관 내용 — 운영자가 정한 값 (PR #102)', () => {
  const text = (id: string) => JSON.stringify(POLICIES.find((p) => p.id === id))

  it('운영 주체·시행일·거절 신청 보관 기간은 채워졌다 — 대괄호는 아직 안 정한 둘뿐', () => {
    const all = JSON.stringify(POLICIES)
    expect(new Set(all.match(/\[[^\]"]+\]/g))).toEqual(
      new Set(['[이름 · 직위 · 메일]', '[메일 발송 서비스]']),
    )
    expect(POLICIES.map((p) => p.effective)).toEqual(['2026-10-28', '2026-10-28'])
    expect(all).toContain('ESC 캡스톤디자인 팀이 운영하는')
    expect(all).toContain('ESC 캡스톤디자인 팀은 「개인정보')
    expect(text('privacy')).toContain('거절한 날부터 7일 뒤 자동 삭제')
  })

  it('처리방침 — 접속 기록(IP)은 항목·보유 기간에, Cloudflare 는 처리 위탁·국외 이전에', () => {
    const sec = (id: string) => JSON.stringify(POLICIES[1].sections.find((s) => s.id === id))
    expect(sec('p2')).toContain('접속 IP')
    expect(sec('p3')).toContain('접속 기록')
    expect(sec('p6')).toContain('Cloudflare, Inc.')
    expect(sec('p6')).toContain('국외 이전')
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
