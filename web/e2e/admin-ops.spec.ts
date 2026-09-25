import {
  expect,
  test,
  type APIRequestContext,
  type BrowserContext,
  type Page,
} from '@playwright/test'
import cfg from './env.json' with { type: 'json' }
import { SIZES, WEB_URL, ensureModems, login, nextAdmin, shot } from './helpers'

// 한 파일 = 컨텍스트 둘(우리 학교·다른 학교), 로그인 각 한 번 — 서버의 IP 당 분당 로그인 30회 상한.
// 화면 이동은 사이드 메뉴 클릭으로 (page.goto 는 새로고침 = 메모리 세션 소실)
test.describe.configure({ mode: 'serial' })
let ctx: BrowserContext
let other: BrowserContext
let api: APIRequestContext
let page: Page
let otherPage: Page

test.beforeAll(async ({ browser }) => {
  ctx = await browser.newContext({ baseURL: WEB_URL, locale: 'ko-KR', viewport: SIZES.admin })
  api = ctx.request
  await ensureModems(api, ['e2e-m4', 'e2e-m5'])
  page = await ctx.newPage()
  await page.goto('/admin/master')
  await login(page, nextAdmin)
  await expect(page).toHaveURL(/\/admin\/master$/)
  other = await browser.newContext({ baseURL: WEB_URL, locale: 'ko-KR', viewport: SIZES.admin })
  otherPage = await other.newPage()
  await otherPage.goto('/admin/master')
  await login(otherPage, () => cfg.OTHER_ADMIN)
  await expect(otherPage).toHaveURL(/\/admin\/master$/)
})
test.afterAll(async () => {
  await ctx.close()
  await other.close()
})

const buildingPanel = (p: Page) => p.getByRole('region', { name: '건물', exact: true })
const buildingRow = (name: string) => buildingPanel(page).getByRole('row').filter({ hasText: name })

// ---- 건물 · 강의실 ----
test('다른 학교 — 건물 0개면 설치 순서 안내, 소문자 z 를 치면 Z 로 만든다', async () => {
  const p = otherPage
  await expect(p.getByText('건물을 먼저 만드세요')).toBeVisible()
  await expect(p.getByText('학교는 CLI 에서만 만든다')).toBeVisible()
  await expect(p.getByText('타학교 · net_id 76')).toBeVisible()
  await shot(p, 'admin-master-empty-1440')
  await p.getByRole('button', { name: '+ 건물' }).first().click()
  const d = p.getByRole('dialog', { name: '건물 추가' })
  await d.getByLabel('이름').fill('타학교관')
  await d.getByLabel('글자').fill('z')
  await expect(d.getByLabel('글자')).toHaveValue('Z')
  await d.getByRole('button', { name: '저장' }).click()
  await expect(d).toHaveCount(0)
  await expect(buildingPanel(p).getByRole('button', { name: '타학교관' })).toBeVisible()
})

test('우리 학교 — 다른 학교가 쓰는 Z 는 글자 칸 오류, 나머지 입력은 그대로 두고 고쳐서 만든다', async () => {
  await page.getByRole('button', { name: '+ 건물' }).first().click()
  const d = page.getByRole('dialog', { name: '건물 추가' })
  await d.getByLabel('이름').fill('마스터관')
  await d.getByLabel('글자').fill('z')
  await d.getByLabel('모뎀').selectOption('e2e-m4')
  await d.getByRole('button', { name: '저장' }).click()
  await expect(d.getByText('다른 학교가 이미 쓰는 글자입니다. 다른 글자를 고르세요.')).toBeVisible()
  await expect(d.getByLabel('이름')).toHaveValue('마스터관')
  await d.getByLabel('글자').fill('m')
  await d.getByRole('button', { name: '저장' }).click()
  await expect(d).toHaveCount(0)
  await expect(buildingPanel(page).getByRole('button', { name: '마스터관' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await expect(buildingRow('마스터관')).toContainText('e2e-m4')
})

test('모뎀을 바꾸면 대기 건수와 함께 확인 — 이름만 바꾸면 묻지 않는다', async () => {
  await buildingRow('마스터관').getByRole('button', { name: '수정' }).click()
  const d = page.getByRole('dialog', { name: '건물 수정' })
  await d.getByLabel('모뎀').selectOption('e2e-m5')
  await d.getByRole('button', { name: '저장' }).click()
  const c = page.getByRole('dialog', { name: '모뎀 변경' })
  await expect(c).toContainText(
    '대기 중 0건이 e2e-m5 로 옮겨집니다. 옛 모뎀(e2e-m4)과 새 모뎀 양쪽이 설정을 다시 받습니다.',
  )
  await c.getByRole('button', { name: '바꾸기' }).click()
  await expect(c).toHaveCount(0)
  await expect(d).toHaveCount(0)
  await expect(buildingRow('마스터관')).toContainText('e2e-m5')
  await buildingRow('마스터관').getByRole('button', { name: '수정' }).click()
  await d.getByLabel('이름').fill('마스터관2')
  await d.getByRole('button', { name: '저장' }).click()
  await expect(d).toHaveCount(0)
  await expect(c).toHaveCount(0)
  await expect(buildingPanel(page).getByRole('button', { name: '마스터관2' })).toBeVisible()
  await shot(page, 'admin-master-building-1440')
})
