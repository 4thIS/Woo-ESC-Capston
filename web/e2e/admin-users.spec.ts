import { expect, test, type Page } from '@playwright/test'
import { SIZES, apiLogin, cli, createStudent, fillLogin, nextAdmin, shot } from './helpers'

test.use({ viewport: SIZES.admin })

async function openUsers(page: Page, admin = nextAdmin()) {
  await page.goto('/admin/users')
  await fillLogin(page, admin)
  await expect(page).toHaveURL(/\/admin\/users$/)
  return admin
}
const row = (page: Page, email: string) => page.getByRole('row').filter({ hasText: email })

test('승인 — 확인 없이 바로, 대기 목록에서 빠진다', async ({ page, request }) => {
  const a = await createStudent(request, { name: '김민준' })
  const b = await createStudent(request, { name: '박서연' })
  await openUsers(page)
  await expect(row(page, a.email)).toContainText('대기중')
  await expect(row(page, b.email)).toBeVisible()
  await shot(page, 'admin-users-1440')
  await row(page, a.email).getByRole('button', { name: '승인' }).click()
  await expect(page.getByText('승인했습니다. 학생에게 메일이 갑니다.')).toBeVisible()
  await expect(row(page, a.email)).toHaveCount(0)
})

test('거절 — 사유 필수, 거절 필터에 거절됨', async ({ page, request }) => {
  const s = await createStudent(request)
  await openUsers(page)
  await row(page, s.email).getByRole('button', { name: '거절' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('button', { name: '거절' })).toBeDisabled()
  await dialog.getByLabel('거절 사유').fill('학번이 잘못되었습니다')
  await shot(page, 'admin-users-reject-1440')
  await dialog.getByRole('button', { name: '거절' }).click()
  await expect(page.getByText('거절했습니다. 학생에게 메일이 갑니다.')).toBeVisible()
  await page.getByRole('combobox').selectOption({ label: '거절' })
  await expect(row(page, s.email)).toContainText('거절됨')
})

test('정지 → 해제', async ({ page, request }) => {
  const s = await createStudent(request, { approve: true })
  await openUsers(page)
  await page.getByRole('combobox').selectOption({ label: '활성' })
  await row(page, s.email).getByRole('button', { name: '정지' }).click()
  await expect(page.getByRole('dialog')).toContainText('로그인이 즉시 끊깁니다')
  await page.getByRole('dialog').getByRole('button', { name: '정지' }).click()
  await expect(page.getByText('정지했습니다.')).toBeVisible()
  await page.getByRole('combobox').selectOption({ label: '정지' })
  await expect(row(page, s.email)).toContainText('정지됨')
  await row(page, s.email).getByRole('button', { name: '해제' }).click()
  await expect(page.getByText('해제했습니다.')).toBeVisible()
  await expect(row(page, s.email)).toHaveCount(0)
})

test('다른 곳에서 먼저 승인 → 409 안내 + 새로고침 (Review Focus 4)', async ({ page, request }) => {
  const s = await createStudent(request)
  await openUsers(page)
  await expect(row(page, s.email)).toBeVisible()
  const t = await apiLogin(request, nextAdmin())
  await request.post(`/api/admin/users/${encodeURIComponent(s.email)}/approve`, {
    headers: { authorization: `Bearer ${t}` },
  })
  await row(page, s.email).getByRole('button', { name: '승인' }).click()
  await expect(page.getByText('이미 처리된 신청입니다')).toBeVisible()
  await expect(row(page, s.email)).toHaveCount(0)
})

test('세션이 무효가 되면 로그인으로, 다시 로그인하면 같은 화면', async ({ page }) => {
  const admin = await openUsers(page)
  // 관리자 token_version 을 올린다 — 비밀번호 재설정·정지와 같은 효과 (S4a)
  cli(['set-user', '--email', admin, '--status', 'active'])
  await page.getByRole('combobox').selectOption({ label: '전체' })
  await expect(page).toHaveURL(/\/admin\/login\?next=/)
  await expect(page.getByText('다시 로그인해 주세요.')).toBeVisible()
  await shot(page, 'admin-relogin-1440')
  await fillLogin(page, admin)
  await expect(page).toHaveURL(/\/admin\/users$/)
})
