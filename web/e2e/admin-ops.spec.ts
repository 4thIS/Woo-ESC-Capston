import {
  expect,
  test,
  type APIRequestContext,
  type BrowserContext,
  type Page,
} from '@playwright/test'
import cfg from './env.json' with { type: 'json' }
import {
  OPS,
  SIZES,
  WEB_URL,
  apiLogin,
  ensureModems,
  login,
  nextAdmin,
  seedOps,
  shot,
  sql,
} from './helpers'

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

const roomPanel = () => page.getByRole('region', { name: '마스터관2 강의실' })

test('강의실 — 한 곳 추가(유닛 2), 학생 예약은 누르는 즉시 저장, 수정 폼의 호수 잠김 · 2→1 확인', async () => {
  const panel = roomPanel()
  await panel.getByRole('button', { name: '+ 강의실' }).first().click()
  const d = page.getByRole('dialog', { name: '강의실 추가' })
  await d.getByLabel('호수').fill('401')
  await d.getByLabel('유닛').selectOption('2')
  await d.getByRole('button', { name: '저장' }).click()
  await expect(d).toHaveCount(0)
  const row = panel.getByRole('row').filter({ hasText: '401' })
  await expect(row).toContainText('4층')
  await expect(row).toContainText('단말 없음')
  await expect(panel).toContainText('1곳 · 학생 웹에 보이는 곳 0')
  await row.getByRole('checkbox').check()
  await expect(row.getByText('받음', { exact: true })).toBeVisible()
  await expect(panel).toContainText('학생 웹에 보이는 곳 1')
  await row.getByRole('button', { name: '수정' }).click()
  const e = page.getByRole('dialog', { name: '강의실 수정' })
  await expect(e.getByLabel('호수')).toHaveAttribute('readonly', '')
  await e.getByLabel('유닛').selectOption('1')
  await e.getByRole('button', { name: '저장' }).click()
  const c = page.getByRole('dialog', { name: '유닛 줄이기' })
  await expect(c).toContainText('401호의 2번 단말이 목록에서 사라집니다. 벽에서 떼어 주세요.')
  await c.getByRole('button', { name: '줄이기' }).click()
  await expect(e).toHaveCount(0)
  await expect(row.getByRole('cell').nth(2)).toHaveText('1')
  // Toast 가 오른쪽 패널 헤더(+ 강의실)를 덮는다 — 사라진 뒤에 찍는다
  await expect(page.locator('.toast')).toHaveCount(0, { timeout: 10_000 })
  await shot(page, 'admin-master-room-1440')
})

test('삭제 — 강의실이 있으면 건물 삭제 잠김(툴팁), 강의실 삭제는 딸린 개수를 적는다', async () => {
  const b = buildingRow('마스터관2')
  await expect(b.getByRole('button', { name: '삭제' })).toBeDisabled()
  await expect(b.locator('[title="강의실을 먼저 지우세요 (1곳)"]')).toHaveCount(1)
  const panel = roomPanel()
  await panel
    .getByRole('row')
    .filter({ hasText: '401' })
    .getByRole('button', { name: '삭제' })
    .click()
  const c = page.getByRole('dialog', { name: '강의실 삭제' })
  await expect(c).toContainText('마스터관2 401호를 지웁니다.')
  await expect(c).toContainText('딸린 시간표·예약·시험기간이 없습니다.')
  await c.getByRole('button', { name: '삭제' }).click()
  await expect(c).toHaveCount(0)
  await expect(panel.getByText('이 건물에 강의실이 없습니다')).toBeVisible()
  await expect(b.getByRole('button', { name: '삭제' })).toBeEnabled()
})

test('범위로 추가 — 이미 있는 호수는 점선·취소선, 눌러서 빼고, 라벨이 실제 개수를 말한다', async () => {
  const panel = roomPanel()
  await panel.getByRole('button', { name: '범위로 추가' }).first().click()
  const d = page.getByRole('dialog', { name: '마스터관2 범위로 추가' })
  await d.getByLabel('시작 호수').fill('101')
  await d.getByLabel('끝 호수').fill('105')
  await d.getByRole('button', { name: '5곳 만들기' }).click()
  await expect(d).toHaveCount(0)
  await expect(
    page.getByText('5곳을 만들었습니다. 마스터관2 모뎀Pi 에 설정이 다시 내려갔습니다.'),
  ).toBeVisible()
  await panel.getByRole('button', { name: '범위로 추가' }).first().click()
  await d.getByLabel('시작 호수').fill('101')
  await d.getByLabel('끝 호수').fill('112')
  await expect(d).toContainText('만들어질 방 12곳 중 7곳 · 이미 있는 5곳은 건너뛴다')
  await expect(d.getByRole('button', { name: '103', exact: true })).toBeDisabled()
  await d.getByRole('button', { name: '106', exact: true }).click()
  await expect(d.getByRole('button', { name: '6곳 만들기' })).toBeVisible()
  await shot(page, 'admin-master-range-1440')
  await d.getByRole('button', { name: '6곳 만들기' }).click()
  await expect(d).toHaveCount(0)
  await expect(panel).toContainText('11곳 · 학생 웹에 보이는 곳 11')
  await expect(panel.getByRole('row').filter({ hasText: '106' })).toHaveCount(0)
  await shot(page, 'admin-master-1440')
  // /api/admin/nodes 는 학교 전체를 본다 — 방을 지우지 않으면 뒤에 도는 monitor.spec.ts 의 노드 수가 어긋난다
  const headers = { authorization: `Bearer ${await apiLogin(api, nextAdmin())}` }
  const buildings = (await (await api.get('/api/buildings', { headers })).json()) as {
    id: number
    name: string
  }[]
  const bid = buildings.find((b) => b.name === '마스터관2')!.id
  const created = (await (await api.get('/api/rooms', { headers })).json()) as {
    id: number
    building_id: number
  }[]
  for (const r of created.filter((r) => r.building_id === bid))
    await api.delete(`/api/rooms/${r.id}`, { headers })
})

// ---- 강의실 설정 ----
// eslint-disable-next-line @typescript-eslint/no-unused-vars -- 방 id 는 Task 15–18 테스트가 쓴다
let ops: Awaited<ReturnType<typeof seedOps>>
const slotsBlock = () => page.getByRole('region', { name: '시간표' })
/** 테스트 전용 — 모뎀이 연결되지 않은 E2E 에서 무선 결과(ACK·실패·취소)를 흉내 낸다 */
const setOutbox = (room: number, state: string, lastError: string | null = null) =>
  sql(
    `UPDATE outbox SET state = '${state}', last_error = ${lastError ? `'${lastError}'` : 'NULL'}, ` +
      `finished_at = strftime('%Y-%m-%d %H:%M:%S', 'now') ` +
      `WHERE bld = '${OPS.bld}' AND room = ${room} AND state IN ('queued', 'dispatched')`,
  )

test('강의실 설정 — 트리: 건물 전체, 검색해도 선택 유지, 버튼 라벨이 선택을 말한다', async () => {
  ops = await seedOps(api)
  await page.getByRole('link', { name: '강의실 설정' }).click()
  await expect(page).toHaveURL(/\/admin\/rooms$/)
  const trigger = page.locator('.tree__trigger')
  await trigger.click()
  const tree = page.getByRole('group', { name: '강의실 선택' })
  await tree.getByRole('button', { name: '전체 해제' }).click()
  await expect(trigger).toContainText('강의실 선택')
  await expect(slotsBlock().getByText('위에서 강의실을 고르세요')).toBeVisible()
  await tree.getByRole('checkbox', { name: OPS.building }).check()
  await expect(trigger).toContainText(`${OPS.building} 101 외 3곳`)
  await tree.getByLabel('호수 검색').fill('201')
  await expect(tree.getByRole('checkbox', { name: '101호' })).toHaveCount(0)
  await tree.getByRole('checkbox', { name: '201호' }).uncheck()
  await tree.getByLabel('호수 검색').fill('')
  await expect(trigger).toContainText(`${OPS.building} 101 · 102 · 202`)
  await page.keyboard.press('Escape')
  await expect(tree).toHaveCount(0)
  await expect(slotsBlock().getByText('이 건물에 등록된 시간표가 없습니다')).toBeVisible()
})

test('시간표 — 추가, 겹침은 저장 전에 막음, 시작을 바꾸면 옛 행이 남지 않음, 점 대기 → 반영됨', async () => {
  const slots = slotsBlock()
  await slots.getByRole('button', { name: '+ 슬롯 추가' }).click()
  const d = page.getByRole('dialog', { name: '슬롯 추가' })
  await d.getByLabel('강의실').selectOption({ label: '101호' })
  await d.getByLabel('요일').selectOption({ label: '월' })
  await d.getByLabel('시작').fill('09:00')
  await d.getByLabel('종료').fill('11:00')
  await d.getByLabel('과목명').fill('캡스톤디자인')
  await d.getByLabel('교수').fill('김교수')
  await d.getByRole('button', { name: '저장' }).click()
  await expect(d).toHaveCount(0)
  const row = slots.getByRole('row').filter({ hasText: '캡스톤디자인' })
  await expect(row).toContainText('수동')
  await expect(row.getByRole('img', { name: '대기' })).toBeVisible()
  // 겹침 — 서버는 같은 키만 막는다. 폼이 먼저 막는다
  await slots.getByRole('button', { name: '+ 슬롯 추가' }).click()
  await d.getByLabel('강의실').selectOption({ label: '101호' })
  await d.getByLabel('요일').selectOption({ label: '월' })
  await d.getByLabel('시작').fill('10:00')
  await d.getByLabel('종료').fill('12:00')
  await d.getByRole('button', { name: '저장' }).click()
  await expect(d.getByText('겹칩니다: 09:00–11:00 캡스톤디자인')).toBeVisible()
  await d.getByRole('button', { name: '취소' }).click()
  // 시작을 바꾸면 새 행을 넣고 옛 행을 지운다 — 한 줄만 남는다
  await row.getByRole('button', { name: '수정' }).click()
  const e = page.getByRole('dialog', { name: '슬롯 수정' })
  await e.getByLabel('시작').fill('13:00')
  await e.getByLabel('종료').fill('15:00')
  await e.getByRole('button', { name: '저장' }).click()
  await expect(e).toHaveCount(0)
  await expect(row).toHaveCount(1)
  await expect(row).toContainText('13:00')
  setOutbox(101, 'acked')
  await expect(row.getByRole('img', { name: '반영됨' })).toBeVisible({ timeout: 10_000 })
})

test('전송 실패 — 점이 실패 + 재전송(방 단위), 관리자 취소는 취소됨', async () => {
  const slots = slotsBlock()
  await slots.getByRole('button', { name: '+ 슬롯 추가' }).click()
  const d = page.getByRole('dialog', { name: '슬롯 추가' })
  await d.getByLabel('강의실').selectOption({ label: '102호' })
  await d.getByLabel('요일').selectOption({ label: '화' })
  await d.getByLabel('과목명').fill('임베디드')
  await d.getByRole('button', { name: '저장' }).click()
  const row = slots.getByRole('row').filter({ hasText: '임베디드' })
  await expect(row.getByRole('img', { name: '대기' })).toBeVisible()
  setOutbox(102, 'failed', 'max_retries')
  await expect(row.getByRole('img', { name: '실패' })).toBeVisible({ timeout: 10_000 })
  await row.getByRole('button', { name: '재전송' }).click()
  await expect(page.getByText('다시 보냈습니다.')).toBeVisible()
  await expect(row.getByRole('img', { name: '대기' })).toBeVisible()
  setOutbox(102, 'failed', 'cancelled')
  await expect(row.getByRole('img', { name: '취소됨 — 노드에 반영 안 됨' })).toBeVisible({
    timeout: 10_000,
  })
  await expect(row.getByRole('button', { name: '재전송' })).toBeVisible()
  await shot(page, 'admin-rooms-slots-1440')
})
