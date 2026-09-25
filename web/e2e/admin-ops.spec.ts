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
  createStudent,
  ensureModems,
  kstDate,
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

const resvBlock = () => page.getByRole('region', { name: '예약', exact: true })

test('예약 — 7일 안은 대기 점, 7일 밖은 예정 배지 (폼에서도 저장 전에 같은 문구)', async () => {
  const resv = resvBlock()
  await resv.getByRole('button', { name: '+ 예약 추가' }).click()
  const d = page.getByRole('dialog', { name: '예약 추가' })
  await d.getByLabel('강의실').selectOption({ label: '101호' })
  await d.getByLabel('날짜').fill(kstDate(1))
  await d.getByLabel('시작').fill('16:00')
  await d.getByLabel('종료').fill('17:00')
  await d.getByLabel('사용 목적').fill('신입생 OT')
  await d.getByLabel('주관 부서').fill('학생처')
  await d.getByRole('button', { name: '저장' }).click()
  await expect(d).toHaveCount(0)
  const near = resv.getByRole('row').filter({ hasText: '신입생 OT' })
  await expect(near.getByRole('img', { name: '대기' })).toBeVisible()
  await expect(near).toContainText('—')
  await resv.getByRole('button', { name: '+ 예약 추가' }).click()
  await d.getByLabel('날짜').fill(kstDate(10))
  await expect(d.getByText('7일 이내로 들어오면 자동 전송됩니다')).toBeVisible()
  await d.getByLabel('사용 목적').fill('동문회')
  await d.getByRole('button', { name: '저장' }).click()
  await expect(d).toHaveCount(0)
  const far = resv.getByRole('row').filter({ hasText: '동문회' })
  await expect(far.getByText('예정')).toHaveAttribute(
    'title',
    '7일 이내로 들어오면 자동 전송됩니다',
  )
})

test('신청 대기 — 오래된 순, 승인하면 예약 표로, 다른 관리자가 먼저 처리하면 409 문장, 거절은 사유 필수', async () => {
  const no = `P${Date.now().toString(36).toUpperCase()}`
  // 로그인은 IP 당 분당 30회 — 앞 테스트가 이미 캐시한 ADMINS[1] 로 가입 승인과 '다른 관리자'를 함께 한다
  const other = { authorization: `Bearer ${await apiLogin(api, cfg.ADMINS[1])}` }
  const s = await createStudent(api, { name: '김신청', studentNo: no })
  const ok = await api.post(`/api/admin/users/${encodeURIComponent(s.email)}/approve`, {
    headers: other,
  })
  expect(ok.ok()).toBe(true)
  const st = { authorization: `Bearer ${await apiLogin(api, s.email)}` }
  const ask = async (s_h: number, subject: string) => {
    const r = await api.post(`/api/student/rooms/${ops.roomIds[101]}/reservations`, {
      headers: st,
      data: { date: kstDate(2), s_h, s_m: 0, e_h: s_h + 1, e_m: 0, subject },
    })
    expect(r.status(), subject).toBe(201)
    return ((await r.json()) as { id: number }).id
  }
  await ask(9, '캡스톤 스터디')
  const second = await ask(10, '동아리 회의')
  await ask(11, '밴드 연습')
  // 신청 대기는 자동 새로고침이 없다 — 화면을 다시 연다
  await page.getByRole('link', { name: '건물 · 강의실' }).click()
  await page.getByRole('link', { name: '강의실 설정' }).click()
  const pend = page.getByRole('region', { name: '신청 대기' })
  await expect(pend).toContainText('3건')
  await expect(pend.locator('tbody tr').nth(0)).toContainText('캡스톤 스터디')
  await expect(pend.getByText('김신청').first()).toHaveAttribute('title', `${no} · ${s.email}`)
  await shot(page, 'admin-rooms-pending-1440')
  await pend
    .getByRole('row')
    .filter({ hasText: '캡스톤 스터디' })
    .getByRole('button', { name: '승인' })
    .click()
  await expect(page.getByText('승인했습니다. 문 앞 화면에 나갑니다.')).toBeVisible()
  const approved = resvBlock().getByRole('row').filter({ hasText: '캡스톤 스터디' })
  await expect(approved).toContainText('김신청')
  await expect(approved).toContainText(no)
  // 다른 관리자가 먼저 승인
  const r = await api.post(`/api/admin/reservations/${second}/approve`, { headers: other })
  expect(r.status()).toBe(200)
  await pend
    .getByRole('row')
    .filter({ hasText: '동아리 회의' })
    .getByRole('button', { name: '승인' })
    .click()
  await expect(page.getByText('이미 처리된 신청입니다.')).toBeVisible()
  await expect(pend.getByRole('row').filter({ hasText: '동아리 회의' })).toHaveCount(0)
  // 거절 — 사유 필수, 0건이 되면 블록이 사라진다
  await pend
    .getByRole('row')
    .filter({ hasText: '밴드 연습' })
    .getByRole('button', { name: '거절' })
    .click()
  const d = page.getByRole('dialog', { name: '예약 신청 거절' })
  await expect(d.getByRole('button', { name: '거절' })).toBeDisabled()
  await d.getByLabel('거절 사유').fill('시험 기간입니다')
  await d.getByRole('button', { name: '거절' }).click()
  await expect(page.getByText('거절했습니다. 사유가 학생에게 보입니다.')).toBeVisible()
  await expect(pend).toHaveCount(0)
})

test('시험기간 — 고른 3곳에 한 번에(진행 라벨), 같은 기간은 한 행으로 접고 펼쳐서 지운다', async () => {
  const ex = page.getByRole('region', { name: '시험기간' })
  await ex.getByRole('button', { name: '+ 선택한 3곳에 기간 추가' }).click()
  const d = page.getByRole('dialog', { name: '시험기간 추가' })
  await expect(d).toContainText('대상 3곳 · 101호, 102호, 202호')
  await d.getByLabel('시작일').fill(kstDate(20))
  await d.getByLabel('종료일').fill(kstDate(24))
  await d.getByRole('button', { name: '선택한 3곳에 기간 추가' }).click()
  await expect(d).toHaveCount(0)
  await expect(page.getByText('3곳에 시험기간을 넣었습니다.')).toBeVisible()
  const g = ex.locator('tbody tr').first()
  await expect(g).toContainText('101, 102, 202')
  await expect(g).toContainText('3곳')
  await g.getByRole('button', { name: '펼치기' }).click()
  const items = ex.locator('.blk__item')
  await expect(items).toHaveCount(3)
  await items.filter({ hasText: '202호' }).getByRole('button', { name: '삭제' }).click()
  const c = page.getByRole('dialog', { name: '시험기간 삭제' })
  await c.getByRole('button', { name: '삭제' }).click()
  await expect(items).toHaveCount(2)
  // 상단 바 오른쪽 버튼이 보이게 Toast 가 걷힌 뒤 찍는다
  await expect(page.locator('.toast')).toHaveCount(0, { timeout: 10_000 })
  await shot(page, 'admin-rooms-1440')
})

test('CSV — 먼저 미리보기, 웹에서 고친 행은 건너뛴다고 말하고, 적용하면 포털 출처 / 행 오류는 아무것도 적용 안 됨', async () => {
  const csv = (rows: string[]) => ({
    name: 'slots.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(
      ['school,building,room,day,start,end,type,subject,professor', ...rows].join('\n'),
    ),
  })
  await page
    .locator('input[type=file]')
    .setInputFiles(
      csv([
        '우송대,K,101,월,13:00,15:00,수업,포털수업,박교수',
        '우송대,K,202,수,09:00,10:00,수업,포털과목,이교수',
      ]),
    )
  const d = page.getByRole('dialog', { name: 'CSV 가져오기 — slots.csv' })
  await expect(d).toContainText('강의실 1곳 · 추가 1 · 수정 0 · 삭제 0')
  await expect(d.getByRole('row').filter({ hasText: '수동 슬롯 있음' })).toContainText('2')
  await shot(page, 'admin-rooms-csv-1440')
  await d.getByRole('button', { name: '적용' }).click()
  await expect(page.getByText(/시간표를 가져왔습니다/)).toBeVisible()
  const slots = page.getByRole('region', { name: '시간표' })
  await expect(slots.getByRole('row').filter({ hasText: '포털과목' })).toContainText('포털')
  await expect(slots.getByRole('row').filter({ hasText: '캡스톤디자인' })).toContainText('수동')
  await expect(slots.getByRole('row').filter({ hasText: '포털수업' })).toHaveCount(0)
  await page
    .locator('input[type=file]')
    .setInputFiles(csv(['우송대,K,999,월,09:00,10:00,수업,없는방,김교수']))
  const e = page.getByRole('dialog', { name: 'CSV 오류 — 아무것도 적용되지 않았습니다' })
  await expect(e.getByRole('row').filter({ hasText: '999' })).toContainText('2')
  await e.getByRole('button', { name: '닫기' }).click()
  await expect(e).toHaveCount(0)
})

test('선택한 곳 동기화 — 고른 방 수만큼 보내고 결과를 말한다', async () => {
  // 앞 테스트의 Toast 더미가 상단 바 오른쪽 버튼을 가린다 — 걷힐 때까지
  await expect(page.locator('.toast')).toHaveCount(0, { timeout: 10_000 })
  await page.getByRole('button', { name: '선택한 곳 동기화' }).click()
  await expect(page.getByText('3곳에 다시 보냈습니다.')).toBeVisible()
})
