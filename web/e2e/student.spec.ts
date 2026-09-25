import {
  expect,
  test,
  type APIRequestContext,
  type APIResponse,
  type BrowserContext,
  type Page,
} from '@playwright/test'
import {
  STU,
  SIZES,
  WEB_URL,
  apiLogin,
  createStudent,
  hmOf,
  kstDate,
  kstMinutesNow,
  login,
  seedStudent,
  shot,
} from './helpers'
import cfg from './env.json' with { type: 'json' }

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
let B: { email: string }
const shownRows = () => page.locator('ul.rows > li')
const DAYS = ['월', '화', '수', '목', '금', '토', '일']
const room = (n: number) => seed.roomIds[n]
const card = (text: string) => page.getByRole('article').filter({ hasText: text })

/** 학생으로 신청 (API — 화면 밖 준비). 응답을 그대로 돌려 호출한 쪽이 상태를 본다 */
async function requestAs(
  email: string,
  roomId: number,
  date: string,
  from: string,
  to: string,
  subject: string,
) {
  const [s_h, s_m] = from.split(':').map(Number)
  const [e_h, e_m] = to.split(':').map(Number)
  return api.post(`/api/student/rooms/${roomId}/reservations`, {
    headers: { authorization: `Bearer ${await apiLogin(api, email)}` },
    data: { date, s_h, s_m, e_h, e_m, subject },
  })
}
async function created(r: APIResponse) {
  expect(r.status()).toBe(201)
  return (await r.json()) as { id: number }
}
/** 관리자 승인·거절 (F2 신청 대기 화면이 부르는 것과 같은 API) */
async function adminPost(path: string, data?: unknown) {
  const r = await api.post(path, {
    headers: { authorization: `Bearer ${await apiLogin(api, cfg.ADMINS[0])}` },
    data,
  })
  expect(r.status(), path).toBe(200)
}

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
  const star102 = row102.getByRole('button', { name: '102호 즐겨찾기' })
  await expect(star102).toHaveAttribute('aria-pressed', 'false')
  await star102.click()
  await expect(star102).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('heading', { name: '즐겨찾기', exact: true })).toBeVisible()
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
    page.getByRole('listitem', { name: `${day} 10:00–13:00 수업중 캡스톤디자인 외 1건` }),
  ).toBeVisible()
  const off = page.getByRole('listitem', { name: `${day} 14:00–15:00 휴강 운영체제` })
  await expect(off).toHaveClass(/wg__blk--off/)
  // 취소선이 실제로 그려지는지 — 계산된 스타일이 아니라 픽셀로. 클래스를 빼면 그림이 달라져야 한다
  const label = off.locator('.wg__label')
  const struck = await label.screenshot()
  await label.evaluate((el: { classList: { remove(c: string): void } }) =>
    el.classList.remove('wg__label--off'),
  )
  const plain = await label.screenshot()
  await label.evaluate((el: { classList: { add(c: string): void } }) =>
    el.classList.add('wg__label--off'),
  )
  expect(struck.equals(plain)).toBe(false)
  // 가로로 밀려도(주말 오늘) 시각 열은 격자 왼쪽에 남는다
  const grid = (await page.locator('.wg').boundingBox())!
  const time = (await page.locator('.wg__time').first().boundingBox())!
  expect(time.x).toBeGreaterThanOrEqual(grid.x)
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

test('내 예약 — 승인됨·대기중·거절됨, 신청 취소는 기록이 남지 않는다, 창 안이면 체크인', async () => {
  const r1 = await created(
    await requestAs(A.email, room(103), kstDate(2), '10:00', '11:00', '팀 회의'),
  )
  const r3 = await created(
    await requestAs(A.email, room(104), kstDate(3), '14:00', '15:00', '동아리'),
  )
  await adminPost(`/api/admin/reservations/${r3.id}/reject`, { reason: '학과 행사와 겹칩니다' })
  // 체크인 창 안에서 곧 시작하는 오늘 예약 — 자정 가까이는 만들 수 없다(Global Constraints 시간대)
  const start = Math.ceil((kstMinutesNow() + 2) / 5) * 5
  const canCheckin = start + 15 <= 23 * 60 + 55
  if (canCheckin) {
    const r2 = await created(
      await requestAs(A.email, room(104), kstDate(0), hmOf(start), hmOf(start + 15), '스터디'),
    )
    await adminPost(`/api/admin/reservations/${r2.id}/approve`)
  }
  await page.getByRole('link', { name: '강의실 목록' }).click()
  await page.getByRole('link', { name: '내 예약' }).click()
  await expect(page).toHaveURL(/\/me$/)
  await expect(card('팀 회의').getByText('대기중')).toBeVisible()
  await expect(card('팀 회의')).toContainText(`${STU.building} 103호`)
  await expect(card('동아리').getByText('거절됨')).toBeVisible()
  await expect(card('동아리')).toContainText('사유: 학과 행사와 겹칩니다')
  await expect(card('동아리').getByRole('button')).toHaveCount(0)
  for (const b of await page.locator('article button').all())
    expect((await b.boundingBox())!.height).toBeGreaterThanOrEqual(48)
  await shot(page, 'student-me-390')
  await card('팀 회의').getByRole('button', { name: '신청 취소' }).click()
  const dlg = page.getByRole('dialog', { name: '신청 취소' })
  await expect(dlg).toContainText('신청을 거두면 기록이 남지 않습니다')
  await dlg.getByRole('button', { name: '신청 취소' }).click()
  await expect(card('팀 회의')).toHaveCount(0)
  // 철회는 행을 지운다 — 서버에도 남지 않는다
  const mine = await api.get('/api/student/me/reservations', {
    headers: { authorization: `Bearer ${await apiLogin(api, A.email)}` },
    params: { status: 'cancelled' },
  })
  expect(((await mine.json()) as { id: number }[]).map((r) => r.id)).not.toContain(r1.id)
  test.skip(!canCheckin, '자정 가까이는 체크인 창 안의 오늘 예약을 만들 수 없다')
  await card('스터디').getByRole('button', { name: '체크인' }).click()
  await expect(card('스터디')).toContainText(/✓ \d\d:\d\d 체크인/)
  await shot(page, 'student-me-checkin-390')
})

test('승인된 예약 취소 — 확인 뒤 취소됨으로 남는다 (신청 취소와 다르다)', async () => {
  const r4 = await created(
    await requestAs(A.email, room(103), kstDate(4), '10:00', '11:00', '발표 연습'),
  )
  await adminPost(`/api/admin/reservations/${r4.id}/approve`)
  // /me 는 60초마다 — 기다리지 않고 한 번 나갔다 온다
  await page.getByRole('link', { name: '뒤로' }).click()
  await expect(page).toHaveURL(new RegExp(`/${STU.bld}$`))
  await page.getByRole('link', { name: '내 예약' }).click()
  await expect(card('발표 연습').getByText('승인됨')).toBeVisible()
  await expect(card('발표 연습').getByRole('button', { name: '체크인' })).toBeDisabled()
  await expect(card('발표 연습')).toContainText('09:50부터 체크인할 수 있어요')
  await card('발표 연습').getByRole('button', { name: '취소', exact: true }).click()
  const dlg = page.getByRole('dialog', { name: '예약 취소' })
  await expect(dlg).toContainText('취소하면 문 앞 화면에서도 지워져요')
  await dlg.getByRole('button', { name: '예약 취소' }).click()
  await expect(card('발표 연습').getByText('취소됨')).toBeVisible()
  await expect(card('발표 연습').getByRole('button')).toHaveCount(0)
  await shot(page, 'student-me-cancelled-390')
})

test('예약 — 날짜 칩 8개, 서버가 준 빈 구간만, 신청하면 내 예약에 대기중', async () => {
  await page.getByRole('link', { name: '뒤로' }).click()
  await shownRows().filter({ hasText: '102호' }).getByRole('link').click() // ★ 칩(102호)과 겹치지 않게 목록 행으로
  await page.getByRole('link', { name: '이 강의실 예약하기' }).click()
  await expect(page).toHaveURL(new RegExp(`/${STU.bld}/102/reserve$`))
  await expect(page.getByRole('link', { name: '닫기' })).toHaveAttribute('href', `/${STU.bld}/102`)
  const chips = page.getByRole('radiogroup', { name: '날짜' }).getByRole('radio')
  await expect(chips).toHaveCount(8)
  await expect(chips.first()).toHaveAccessibleName(/^오늘 /)
  expect((await chips.nth(1).boundingBox())!.height).toBeGreaterThanOrEqual(48)
  // 네이티브 라디오 — 화살표로 다음 날로 옮기면 그 날이 골라진다
  await chips.first().focus()
  await page.keyboard.press('ArrowRight')
  await expect(chips.nth(1)).toBeChecked()
  await expect(chips.nth(1)).toBeFocused()
  await page.getByRole('radio', { name: /^09:00 – 21:00/ }).check()
  await page.getByLabel('시작', { exact: true }).selectOption({ label: '10:00' })
  await page.getByLabel('끝', { exact: true }).selectOption({ label: '11:00' })
  await page.getByLabel(/무엇에 쓰나요/).fill('캡스톤 스터디')
  await expect(page.getByText('19 / 20 B')).toBeVisible()
  await expect(page.getByText('문 앞 화면에는 "학생 예약"으로만 표시돼요')).toBeVisible()
  await shot(page, 'student-reserve-390')
  await page.getByRole('button', { name: '예약하기' }).click()
  await expect(page).toHaveURL(/\/me$/)
  await expect(card('캡스톤 스터디').getByText('대기중')).toBeVisible()
})

test('경합 — 고르는 사이 남이 먼저 신청하면 409 문장 + 빈 구간 새로 고침, 남의 이름은 없다', async () => {
  B = await createStudent(api, { approve: true, name: '박학생' })
  await page.getByRole('link', { name: '뒤로' }).click()
  await shownRows().filter({ hasText: '102호' }).getByRole('link').click() // ★ 칩(102호)과 겹치지 않게 목록 행으로
  await page.getByRole('link', { name: '이 강의실 예약하기' }).click()
  await page.getByRole('radiogroup', { name: '날짜' }).getByRole('radio').nth(1).click()
  await page.getByRole('radio', { name: /^11:00 – 21:00/ }).check()
  await page.getByLabel('시작', { exact: true }).selectOption({ label: '11:00' })
  await page.getByLabel('끝', { exact: true }).selectOption({ label: '12:00' })
  await page.getByLabel(/무엇에 쓰나요/).fill('세미나 준비')
  await created(await requestAs(B.email, room(102), kstDate(1), '11:00', '12:00', '먼저 온 사람'))
  await page.getByRole('button', { name: '예약하기' }).click()
  await expect(
    page.getByText('방금 다른 사람이 먼저 신청했어요. 비어 있는 시간을 새로 불러왔어요.'),
  ).toBeVisible()
  await expect(page).toHaveURL(/\/reserve$/)
  await expect(page.getByRole('radio', { name: /^12:00 – 21:00/ })).toBeVisible()
  await expect(page.getByRole('radio', { name: /^11:00 – 21:00/ })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '예약하기' })).toBeDisabled()
  await expect(page.getByText('먼저 온 사람')).toHaveCount(0)
  await expect(page.getByText('박학생')).toHaveCount(0)
  await shot(page, 'student-reserve-taken-390')
})

test('건수 상한 — 진행 중 신청 3건이면 버튼을 잠그고 이유를 말한다', async () => {
  // 서버가 3건째 뒤를 400 으로 막을 때까지 채운다 — 체크인 예약을 건너뛴 날에도 같은 결과
  for (let i = 5; i <= 7; i++) {
    const r = await requestAs(A.email, room(103), kstDate(i), '10:00', '11:00', `연습 ${i}`)
    if (r.status() === 400) break
    expect(r.status()).toBe(201)
  }
  // 앞 테스트의 409 Toast 는 재조회 뒤의 알림이라 8초 뒤 스스로 닫힌다 — 헤더의 ✕ 닫기가 드러날 때까지
  await expect(page.getByRole('alert')).toHaveCount(0, { timeout: 10_000 })
  // 신청 화면은 폴링하지 않는다 — 한 번 닫았다 연다
  await page.getByRole('link', { name: '닫기' }).click()
  await page.getByRole('link', { name: '이 강의실 예약하기' }).click()
  await expect(page.getByText('신청은 3건까지 할 수 있어요')).toBeVisible()
  await expect(page.getByRole('button', { name: '예약하기' })).toBeDisabled()
  await shot(page, 'student-reserve-cap-390')
})
