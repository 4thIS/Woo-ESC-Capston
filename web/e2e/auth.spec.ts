import { expect, test } from '@playwright/test'
import {
  PASSWORD,
  SIZES,
  apiLogin,
  createStudent,
  fillLogin,
  mailCount,
  mailToken,
  nextAdmin,
  shot,
  uniqEmail,
} from './helpers'

test.use({ viewport: SIZES.student })

test('가입 신청 → 링크 → 승인 대기 403 → 승인 → 로그인', async ({ page, request }) => {
  const email = uniqEmail('new')
  await page.goto('/signup')
  await expect(page.getByRole('heading', { name: '가입 신청' })).toBeVisible() // 지연 로딩 라우트
  await shot(page, 'signup-390')
  await page.getByLabel('학교 웹메일').fill(email)
  const before = mailCount(email)
  await page.getByRole('button', { name: '인증 메일 받기' }).click()
  await expect(page.getByText(`${email} 로 보냈어요`)).toBeVisible()
  await expect(page.getByRole('button', { name: '다시 보내기' })).toBeDisabled()
  await shot(page, 'signup-sent-390')

  const token = await mailToken(email, { after: before })
  await page.goto(`/verify#token=${token}`)
  await expect(page.getByText(email)).toBeVisible()
  expect(new URL(page.url()).hash).toBe('') // 토큰은 주소에서 지워졌다
  await page.getByLabel('이름').fill('김민준')
  await page.getByLabel('학번').fill(`E${Date.now().toString(36)}`)
  await page.getByLabel('비밀번호').fill(PASSWORD)
  await shot(page, 'verify-390')
  await page.getByRole('button', { name: '가입 신청' }).click()
  await expect(page.getByText('승인을 기다리는 중입니다')).toBeVisible()
  await shot(page, 'verify-done-390')

  await page.goto('/login')
  await fillLogin(page, email)
  await expect(
    page.getByText('아직 승인되지 않았어요. 관리자 승인 뒤 로그인할 수 있어요.'),
  ).toBeVisible()
  await shot(page, 'login-pending-390')

  const t = await apiLogin(request, nextAdmin())
  await request.post(`/api/admin/users/${encodeURIComponent(email)}/approve`, {
    headers: { authorization: `Bearer ${t}` },
  })
  await fillLogin(page, email)
  await expect(page.getByText('강의실 화면은 준비 중입니다')).toBeVisible()
})

test('학번 중복 409 → 학번만 고쳐 다시 제출', async ({ page, request }) => {
  const taken = await createStudent(request)
  const email = uniqEmail('dup')
  const before = mailCount(email)
  await request.post('/api/auth/signup', { data: { email } })
  await page.goto(`/verify#token=${await mailToken(email, { after: before })}`)
  await page.getByLabel('이름').fill('이정민')
  await page.getByLabel('학번').fill(taken.studentNo)
  await page.getByLabel('비밀번호').fill(PASSWORD)
  await page.getByRole('button', { name: '가입 신청' }).click()
  await expect(page.getByText('이미 등록된 학번입니다')).toBeVisible()
  await expect(page.getByLabel('이름')).toHaveValue('이정민')
  await page.getByLabel('학번').fill(`${taken.studentNo}X`)
  await page.getByRole('button', { name: '가입 신청' }).click()
  await expect(page.getByText('승인을 기다리는 중입니다')).toBeVisible()
})

test('링크를 연 뒤 새로고침하면 만료 안내 (Review Focus 2)', async ({ page }) => {
  const email = uniqEmail('reload')
  await page.goto('/signup')
  await page.getByLabel('학교 웹메일').fill(email)
  const before = mailCount(email)
  await page.getByRole('button', { name: '인증 메일 받기' }).click()
  await page.goto(`/verify#token=${await mailToken(email, { after: before })}`)
  await expect(page.getByText(email)).toBeVisible()
  await page.reload()
  await expect(page.getByText('링크가 만료되었거나 잘못되었습니다')).toBeVisible()
})

test('학교 웹메일이 아니면 입력 칸 에러', async ({ page }) => {
  await page.goto('/signup')
  await page.getByLabel('학교 웹메일').fill('someone@gmail.com')
  await page.getByRole('button', { name: '인증 메일 받기' }).click()
  await expect(page.getByText('학교 웹메일로만 가입할 수 있어요')).toBeVisible()
  await expect(page.getByText('메일로 링크를 보냅니다')).toBeVisible()
})

test('비밀번호 재설정 → 새 비밀번호로 로그인, 옛 비밀번호는 거절', async ({ page, request }) => {
  const s = await createStudent(request, { approve: true })
  await page.goto('/forgot')
  await page.getByLabel('학교 웹메일').fill(s.email)
  const before = mailCount(s.email)
  await page.getByRole('button', { name: '재설정 메일 받기' }).click()
  await expect(page.getByText('가입된 메일이면 재설정 링크가 갑니다.')).toBeVisible()
  await shot(page, 'forgot-sent-390')

  await page.goto(`/reset#token=${await mailToken(s.email, { after: before })}`)
  await page.getByLabel('새 비밀번호').fill('newpassword9')
  await page.getByRole('button', { name: '비밀번호 바꾸기' }).click()
  await expect(
    page.getByText('다른 기기에서 로그인해 있던 곳은 모두 로그아웃됩니다.'),
  ).toBeVisible()
  await shot(page, 'reset-done-390')

  await page.goto('/login')
  await fillLogin(page, s.email, PASSWORD)
  await expect(page.getByText('이메일 또는 비밀번호가 틀립니다')).toBeVisible()
  await fillLogin(page, s.email, 'newpassword9')
  await expect(page.getByText('강의실 화면은 준비 중입니다')).toBeVisible()
})
