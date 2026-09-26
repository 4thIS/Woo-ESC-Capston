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
declare const document: { documentElement: { scrollHeight: number } }
declare const window: { innerHeight: number }

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
  await shot(page, 'student-login-390')
  // 넓은 화면(≥640)에서는 카드에 윗여백 — 그래도 스크롤이 생기지 않는다
  await page.setViewportSize({ width: 1280, height: 800 })
  await noScroll(page)
})

test('역할이 다른 앱에 로그인하면 토큰을 버리고 안내한다', async ({ page, request }) => {
  const s = await createStudent(request, { approve: true })
  await page.goto('/admin/login')
  await fillLogin(page, s.email)
  await expect(
    page.getByText('관리자 계정이 아닙니다. 학생은 학생 웹에서 로그인하세요.'),
  ).toBeVisible()
  await expect(page).toHaveURL(/\/admin\/login/)

  await page.goto('/login')
  await fillLogin(page, nextAdmin())
  await expect(page.getByText('관리자 계정입니다. 관리자 웹에서 로그인하세요.')).toBeVisible()
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
