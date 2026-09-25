import {
  expect,
  test,
  type APIRequestContext,
  type BrowserContext,
  type Page,
} from '@playwright/test'
import { STU, SIZES, WEB_URL, createStudent, login, seedStudent, shot } from './helpers'

// e2e 는 node 타입 — page.evaluate 콜백은 브라우저에서 돈다
declare const localStorage: { getItem(k: string): string | null }

// 한 파일 = 한 컨텍스트 · 학생 UI 로그인 한 번 — 서버의 IP 당 분당 로그인 30회 상한 (F1 plan Task 13 메모).
// 로그인 뒤 이동은 링크 클릭으로 (page.goto 는 새로고침 = 메모리 세션 소실)
test.describe.configure({ mode: 'serial' })
let ctx: BrowserContext
let page: Page
let api: APIRequestContext
let A: { email: string }
let seed: Awaited<ReturnType<typeof seedStudent>>
const shownRows = () => page.locator('ul.rows > li')
const DAYS = ['월', '화', '수', '목', '금', '토', '일']

test.beforeAll(async ({ browser }) => {
  ctx = await browser.newContext({ baseURL: WEB_URL, locale: 'ko-KR', viewport: SIZES.student })
  api = ctx.request
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

test('딥링크 — 소문자는 대문자로, 벽 → 로그인 → 원래 주소, 없는 건물은 404 → 건물 목록', async () => {
  test.setTimeout(60_000)
  seed = await seedStudent(api)
  A = await createStudent(api, { approve: true, name: '이학생' })
  await page.goto('/q')
  await expect(page).toHaveURL(/\/Q$/)
  await expect(page.getByRole('heading', { name: /^Q동의 빈 강의실/ })).toBeVisible()
  await page.getByRole('link', { name: '로그인' }).click()
  await login(page, () => A.email, page.locator('header.sh'))
  await expect(page).toHaveURL(/\/Q$/)
  await expect(page.getByRole('heading', { name: '찾을 수 없는 주소예요' })).toBeVisible()
  await page.getByRole('link', { name: '건물 목록으로' }).click()
  await expect(page.getByRole('heading', { name: '건물을 고르세요' })).toBeVisible()
  const h = page.getByRole('link', { name: new RegExp(`^${STU.building} `) })
  await expect(h).toHaveAttribute('aria-label', /4개 강의실 · 지금 3곳 비어 있어요/)
  await expect(
    page.getByRole('link', { name: new RegExp(`^${STU.other.building} `) }),
  ).toBeVisible()
  await shot(page, 'student-home-390')
  await h.click()
  await expect(page).toHaveURL(new RegExp(`/${STU.bld}$`))
})

test('강의실 목록 — 빈 곳 개수가 먼저, 빈 강의실만 기본, 즐겨찾기는 고르면 생긴다', async () => {
  await expect(page.getByRole('heading', { name: '3곳이 지금 비어 있어요' })).toBeVisible()
  await expect(shownRows()).toHaveCount(3)
  await expect(page.getByRole('link', { name: /^101호/ })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: /^즐겨찾기/ })).toHaveCount(0)
  await page.getByLabel('빈 강의실만').uncheck()
  await expect(shownRows()).toHaveCount(4)
  await expect(page.getByRole('link', { name: /^101호 특강 / })).toBeVisible()
  const row102 = shownRows().filter({ hasText: '102호' })
  expect((await row102.boundingBox())!.height).toBeGreaterThanOrEqual(56)
  await row102.getByRole('button', { name: '즐겨찾기 추가' }).click()
  await expect(row102.getByRole('button', { name: '즐겨찾기 해제' })).toBeVisible()
  await expect(page.getByRole('heading', { name: /^즐겨찾기/ })).toBeVisible()
  await expect(page.getByRole('link', { name: '102호 비어있음', exact: true })).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('esc.fav'))).toBe('["H-102"]')
  await expect(page.locator('.rn')).toContainText(/문 앞 e-Paper 와 같은 내용 · \d\d:\d\d 갱신/)
  await shot(page, 'student-list-390')
})

test('강의실 — 오늘 목록은 빈 구간도 행, 지금 행을 세운다, ‹ 는 목록으로 가는 링크', async () => {
  await page.getByRole('link', { name: /^101호 / }).click()
  await expect(page).toHaveURL(new RegExp(`/${STU.bld}/101$`))
  await expect(page.getByRole('heading', { level: 1, name: `${STU.building} 101호` })).toBeVisible()
  const nowRow = page.locator('.today__row--now')
  await expect(nowRow).toContainText('세미나')
  await expect(nowRow).toContainText(/지금 \d\d:\d\d/)
  await expect(page.locator('.today__row').filter({ hasText: '비어있음' }).first()).toBeVisible()
  await expect(page.getByRole('link', { name: '강의실 목록' })).toHaveAttribute(
    'href',
    `/${STU.bld}`,
  )
  const cta = page.getByRole('link', { name: '이 강의실 예약하기' })
  expect((await cta.boundingBox())!.height).toBeGreaterThanOrEqual(48)
  await shot(page, 'student-room-390')
})

test('이번 주 — 겹친 사용 블록은 한 덩어리 "외 1건", 휴강은 점선으로 따로', async () => {
  await page.getByRole('link', { name: '이번 주 전체 보기' }).click()
  await expect(page).toHaveURL(new RegExp(`/${STU.bld}/101/week$`))
  const day = DAYS[seed.tomorrowDay - 1]
  await expect(
    page.getByRole('listitem', { name: `${day} 10:00–13:00 캡스톤디자인 외 1건` }),
  ).toBeVisible()
  await expect(page.getByRole('listitem', { name: `${day} 14:00–15:00 운영체제` })).toHaveClass(
    /wg__blk--off/,
  )
  await shot(page, 'student-week-390')
})

test('넓은 폭 — /week 는 강의실로, 목록 340px 상주, 격자는 같은 모양, 예약은 헤더 오른쪽', async () => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await expect(page).toHaveURL(new RegExp(`/${STU.bld}/101$`))
  const list = page.getByRole('region', { name: '강의실 목록' })
  await expect(list).toBeVisible()
  expect((await list.boundingBox())!.width).toBe(340)
  await expect(page.locator('.sh').getByRole('link', { name: '이 강의실 예약하기' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '다음 비는 시간' })).toBeVisible()
  await expect(page.getByRole('listitem', { name: /캡스톤디자인 외 1건/ })).toBeVisible()
  await shot(page, 'student-wide-1280')
  await page.setViewportSize(SIZES.student)
  await expect(list).toBeHidden()
})
