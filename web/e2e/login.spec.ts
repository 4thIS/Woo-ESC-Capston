import { expect, test, type Page } from '@playwright/test'
import {
  SIZES,
  createStudent,
  expectStudentLanding,
  fillLogin,
  nextAdmin,
  shot,
  uniqEmail,
} from './helpers'

// e2e 는 node 타입(tsconfig.node.json) — page.evaluate 콜백은 브라우저에서 도는데 DOM lib 이 없다
declare const document: { documentElement: { scrollHeight: number; scrollWidth: number } }
declare const window: { innerHeight: number; innerWidth: number }

// 카드의 윗여백이 바탕(.auth, min-height 100vh) 밖으로 새면 폼 하나짜리 화면이 스크롤된다.
// 창 크기를 바꾼 직후 한 프레임은 이전 높이가 남는다 — 제자리를 잡을 때까지 다시 잰다
const noScroll = (page: Page) =>
  expect
    .poll(() => page.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight))
    .toBe(true)

test('관리자 — 가드가 로그인으로 보내고, 로그인하면 돌아온다', async ({ page }) => {
  await page.setViewportSize(SIZES.admin)
  await page.goto('/admin/')
  await expect(page).toHaveURL(/\/admin\/login\?next=/)
  await expect(page.getByRole('link', { name: '가입 신청' })).toHaveCount(0)
  await shot(page, 'admin-login-1440')
  await noScroll(page)
  await fillLogin(page, nextAdmin())
  await expect(page).toHaveURL(/\/admin\/dashboard$/)
})

test('학생 로그인 화면 390', async ({ page }) => {
  await page.setViewportSize(SIZES.student)
  await page.goto('/login')
  await expect(page.getByRole('heading', { name: '로그인' })).toBeVisible()
  // 터치 타깃 48px (tokens.md)
  const box = await page.getByRole('button', { name: '로그인' }).boundingBox()
  expect(box!.height).toBeGreaterThanOrEqual(48)
  for (const name of ['가입 신청', '비밀번호를 잊었어요']) {
    const link = await page.getByRole('link', { name }).boundingBox()
    expect(link!.height, name).toBeGreaterThanOrEqual(48)
  }
  // 두 링크 사이 가운뎃점은 링크 글자와 같은 선 — 48px 칸 맨 위에 뜨지 않는다
  const mid = async (l: ReturnType<typeof page.locator>) => {
    const b = (await l.boundingBox())!
    return b.y + b.height / 2
  }
  const footer = page.locator('.auth__footer')
  expect(
    Math.abs((await mid(footer.locator('span'))) - (await mid(footer.locator('a').first()))),
  ).toBeLessThan(2)
  await shot(page, 'student-login-390')
  // 넓은 화면(≥640)에서는 카드에 윗여백 — 그래도 스크롤이 생기지 않는다
  await page.setViewportSize({ width: 1280, height: 800 })
  await noScroll(page)
})

test('역할이 다른 앱에 로그인하면 토큰을 버리고 안내한다', async ({ page, request }) => {
  const s = await createStudent(request, { approve: true })
  await page.goto('/admin/login')
  await fillLogin(page, s.email)
  // 문구가 바로 위의 탭을 가리킨다 (auth.md 「역할 확인」)
  await expect(page.getByText("학생 계정입니다. 위의 '학생'을 골라 로그인하세요.")).toBeVisible()
  await expect(page).toHaveURL(/\/admin\/login/)

  await page.goto('/login')
  await fillLogin(page, nextAdmin())
  await expect(
    page.getByText("관리자 계정입니다. 위의 '관리자'를 골라 로그인하세요."),
  ).toBeVisible()
})

test('학생|관리자 탭 — 두 앱을 오가도 탭·폼이 1px 도 움직이지 않고, 폰에서도 관리자 로그인이 가로로 넘치지 않는다', async ({
  page,
}) => {
  const place = () =>
    Promise.all(
      [page.getByRole('navigation', { name: '로그인 역할' }), page.locator('form')].map((l) =>
        l.boundingBox(),
      ),
    )
  for (const size of [SIZES.student, { width: 1280, height: 800 }]) {
    await page.setViewportSize(size)
    await page.goto('/login')
    const tabs = page.getByRole('navigation', { name: '로그인 역할' })
    await expect(tabs.getByRole('link', { name: '학생' })).toHaveAttribute('aria-current', 'page')
    const before = await place()
    // 관리자 탭은 라우터 이동이 아니라 관리자 앱을 새로 연다 — 토큰이 그 앱 메모리에 남아야 한다
    await tabs.getByRole('link', { name: '관리자' }).click()
    await expect(page).toHaveURL(/\/admin\/login$/)
    await expect(tabs.getByRole('link', { name: '관리자' })).toHaveAttribute('aria-current', 'page')
    expect(await place()).toEqual(before)
    await expect(page.getByRole('link', { name: '가입 신청' })).toHaveCount(0)
    await expect(page.getByRole('link', { name: '비밀번호를 잊었어요' })).toHaveCount(0)
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true)
    await shot(page, `admin-login-tab-${size.width}`)
    // 메인 페이지 / 로 — 폰은 폼 위 ‹, 넓은 폭은 왼쪽 ESC (그때 ‹ ESC 는 숨는다). 관리자 앱에서도 /
    const home = size.width < 640 ? '메인 페이지' : 'ESC'
    await expect(page.getByRole('link', { name: home })).toHaveAttribute('href', '/')
  }
})

test('429 뒤 10초 잠금이 풀린다 (Review Focus 5)', async ({ page }) => {
  test.setTimeout(45_000)
  const email = uniqEmail('nobody')
  await page.goto('/login')
  for (let i = 0; i < 5; i++) {
    // IP 상한에 걸려 기다렸다 다시 냈으면 이메일 창도 새로 시작했다 — 그 제출이 첫 번째
    if (await fillLogin(page, email, 'wrongpass1')) i = 0
    await expect(page.getByText('이메일 또는 비밀번호가 틀립니다')).toBeVisible()
  }
  await fillLogin(page, email, 'wrongpass1', { retry429: false })
  await expect(page.getByText('잠시 후 다시 시도해 주세요')).toBeVisible()
  const btn = page.getByRole('button', { name: '로그인' })
  await expect(btn).toBeDisabled()
  await expect(btn).toBeEnabled({ timeout: 12_000 })
})

test('next 가 외부 주소면 기본 화면으로 (Review Focus 1)', async ({ page, request }) => {
  const s = await createStudent(request, { approve: true })
  await page.goto('/login?next=//evil.example')
  await fillLogin(page, s.email)
  await expectStudentLanding(page)
})
