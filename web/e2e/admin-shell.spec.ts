import { expect, test } from '@playwright/test'
import { SIZES, createStudent, fillLogin, nextAdmin, shot } from './helpers'

// e2e 는 node 타입(tsconfig.node.json) — page.evaluate 콜백은 브라우저에서 도는데 DOM lib 이 없다
declare const document: { documentElement: { scrollWidth: number } }

test('로그인 → 전송 현황, 사이드바 순서·활성 + 회원 대기 건수', async ({ page, request }) => {
  await createStudent(request) // 승인 대기 1건 이상
  await page.setViewportSize(SIZES.admin)
  await page.goto('/admin/')
  await fillLogin(page, nextAdmin())
  await expect(page).toHaveURL(/\/admin\/dashboard$/)
  await expect(page.locator('nav a')).toHaveText([/^노드 상태$/, /^전송 현황$/, /^회원\s*\d+$/])
  await expect(page.getByRole('link', { name: '전송 현황' })).toHaveAttribute(
    'aria-current',
    'page',
  )
  const nav = await page.locator('nav').boundingBox()
  expect(Math.round(nav!.width)).toBe(220)
  await shot(page, 'admin-shell-1440')
})

test('1024px 미만 — 가로 스크롤 + 한 번만 뜨는 Banner', async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 800 })
  await page.goto('/admin/login')
  await fillLogin(page, nextAdmin())
  const banner = page.getByText('관리자 화면은 1024px 이상에서 쓰도록 만들어졌습니다')
  await expect(banner).toBeVisible()
  const scrollW = await page.evaluate(() => document.documentElement.scrollWidth)
  expect(scrollW).toBeGreaterThanOrEqual(1024)
  await shot(page, 'admin-narrow-900')
  await page.getByRole('button', { name: '닫기' }).click()
  await expect(banner).toHaveCount(0)
  // 새로고침하면 메모리 세션이라 다시 로그인 — Banner 는 localStorage 로 기억
  await page.reload()
  await fillLogin(page, nextAdmin())
  await expect(page).toHaveURL(/\/admin\/dashboard$/)
  await expect(banner).toHaveCount(0)
})
