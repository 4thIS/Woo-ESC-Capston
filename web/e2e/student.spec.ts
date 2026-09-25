import { expect, test, type BrowserContext, type Page } from '@playwright/test'
import { SIZES, WEB_URL, shot } from './helpers'

// 한 파일 = 한 컨텍스트 · 학생 UI 로그인 한 번 — 서버의 IP 당 분당 로그인 30회 상한 (F1 plan Task 13 메모).
// 로그인 뒤 이동은 링크 클릭으로 (page.goto 는 새로고침 = 메모리 세션 소실)
test.describe.configure({ mode: 'serial' })
let ctx: BrowserContext
let page: Page

test.beforeAll(async ({ browser }) => {
  ctx = await browser.newContext({ baseURL: WEB_URL, locale: 'ko-KR', viewport: SIZES.student })
  page = await ctx.newPage()
})
test.afterAll(async () => {
  await ctx.close()
})

test('로그인 벽 — 빈 폼 대신 무엇을 볼 수 있는지, 로그인은 돌아올 주소를 안다', async () => {
  await page.goto('/')
  await expect(
    page.getByRole('heading', {
      level: 1,
      name: '학교의 빈 강의실을 확인하고 예약을 신청할 수 있어요.',
    }),
  ).toBeVisible()
  const login = page.getByRole('link', { name: '로그인' })
  await expect(login).toHaveAttribute('href', '/login?next=/')
  expect((await login.boundingBox())!.height).toBeGreaterThanOrEqual(48)
  await expect(page.getByRole('link', { name: '가입 신청' })).toHaveAttribute('href', '/signup')
  await shot(page, 'student-gate-390')
})

test('없는 주소 — 벽 없이 404 + 건물 목록으로', async () => {
  await page.goto('/no/such/page')
  await expect(page.getByRole('heading', { name: '찾을 수 없는 주소예요' })).toBeVisible()
  await expect(page.getByRole('link', { name: '건물 목록으로' })).toHaveAttribute('href', '/')
  expect((await page.locator('header.sh').boundingBox())!.height).toBe(58)
  await shot(page, 'student-notfound-390')
})
