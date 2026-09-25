import {
  expect,
  test,
  type APIRequestContext,
  type BrowserContext,
  type Page,
} from '@playwright/test'
import cfg from './env.json' with { type: 'json' }
import { SEED, SIZES, WEB_URL, apiLogin, login, nextAdmin, seedMonitoring, shot } from './helpers'

// e2e 는 node 타입 — page.evaluate 콜백은 브라우저에서 돈다
declare const navigator: { clipboard: { readText(): Promise<string> } }
declare const document: { documentElement: { scrollHeight: number } }

// 한 파일 = 한 브라우저 컨텍스트·로그인 한 번 — 서버의 IP 당 분당 로그인 30회 상한 (F1 plan Task 13 메모)
test.describe.configure({ mode: 'serial' })
let ctx: BrowserContext
let api: APIRequestContext
let page: Page

test.beforeAll(async ({ browser }) => {
  ctx = await browser.newContext({
    baseURL: WEB_URL,
    locale: 'ko-KR',
    viewport: SIZES.admin,
    permissions: ['clipboard-read', 'clipboard-write'],
  })
  api = ctx.request
  await seedMonitoring(api)
  page = await ctx.newPage()
  await page.goto('/admin/nodes')
  await login(page, nextAdmin)
  await expect(page).toHaveURL(/\/admin\/nodes$/)
})
test.afterAll(async () => {
  await ctx.close()
})

test('시드 — 노드 4행·경고, 대기 장치 1, 모뎀 2, 지연 표본 8 (두 번 불러도 한 벌)', async () => {
  await seedMonitoring(api)
  const headers = { authorization: `Bearer ${await apiLogin(api, cfg.ADMINS[0])}` }
  const get = async (p: string) => {
    const r = await api.get(p, { headers })
    expect(r.status(), p).toBe(200)
    return r.json()
  }
  const nodes = (await get('/api/admin/nodes')) as {
    room: number
    unit: number
    warnings: string[]
  }[]
  expect(nodes.map((n) => `${n.room}-${n.unit}:${n.warnings.join(',')}`)).toEqual([
    '401-1:',
    '402-1:unseen,low_batt',
    '402-2:unseen',
    '403-1:low_batt,resync',
  ])
  const pending = (await get('/api/lora/pending')) as { mac: string }[]
  expect(pending.map((p) => p.mac)).toEqual([SEED.mac])
  const modems = (await get('/api/lora/modems')) as { modem_id: string; connected: boolean }[]
  // 전체 실행에서는 admin-ops 가 먼저 e2e-m4·m5 를 등록한다 — 시드 모뎀만 본다
  const seeded: string[] = [SEED.modem, SEED.offlineModem]
  expect(
    modems.filter((m) => seeded.includes(m.modem_id)).map((m) => `${m.modem_id}:${m.connected}`),
  ).toEqual(['e2e-m1:true', 'e2e-m2:false'])
  expect(await get('/api/admin/analytics/latency')).toMatchObject({
    n: 8,
    p50: 25,
    p95: 50,
    max: 95,
    within_30s: 0.625,
    within_90s: 0.875,
  })
})

// ---- 전송 현황 (노드 화면 조작보다 먼저 — 재전송·배정이 outbox 를 더 만든다) ----
test('전송 현황 — KPI·분포·최근 전송이 1440×900 한 화면에', async () => {
  await page.getByRole('link', { name: '전송 현황' }).click()
  await expect(page).toHaveURL(/\/admin\/dashboard$/)
  const tiles = page.locator('.stat')
  await expect(tiles.nth(0)).toContainText('25초')
  await expect(tiles.nth(0)).toContainText('p95 50초 · 최대 95초')
  await expect(tiles.nth(1)).toContainText('62.5%')
  await expect(tiles.nth(1)).toContainText('목표 95% · 미달')
  await expect(tiles.nth(2)).toContainText('87.5%')
  await expect(tiles.nth(2)).toContainText('목표 전부 · 미달')
  await expect(tiles.nth(3)).toContainText('1건')
  const hist = page.locator('svg.hist')
  await expect(hist.locator('path')).toHaveCount(7)
  await expect(hist.locator('.hist__value')).toHaveText(['1', '2'])
  await expect(hist.locator('.hist__marker text')).toHaveText('SLA 30초')
  const recent = page.getByRole('region', { name: '최근 전송' }).locator('tbody tr')
  await expect(recent.locator('td:nth-child(3)')).toHaveText([
    '대기',
    '실패',
    '95초',
    '50초',
    '35초',
    '12초',
    '28초',
  ])
  await expect(recent.nth(0)).toContainText('E 402 · 예약')
  await expect(recent.locator('.dash__slow')).toHaveCount(3)
  await expect(recent.nth(1).locator('.dash__failed')).toHaveText('실패')
  expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThanOrEqual(900)
  await shot(page, 'admin-dashboard-1440')
})

test('기간 30일 — from 이 to 보다 29일 앞 (KST 날짜)', async () => {
  const req = page.waitForRequest(
    (r) => r.url().includes('/api/admin/analytics/latency') && r.url().includes('type=all'),
  )
  await page.getByLabel('기간').selectOption({ label: '최근 30일' })
  const q = new URL((await req).url()).searchParams
  expect((Date.parse(q.get('to')!) - Date.parse(q.get('from')!)) / 86_400_000).toBe(29)
  await expect(page.locator('.stat').nth(0)).toContainText('25초')
  await page.getByLabel('기간').selectOption({ label: '최근 7일' })
  await page.getByRole('link', { name: '노드 상태' }).click()
  await expect(page).toHaveURL(/\/admin\/nodes$/)
})

// ---- 노드 상태 ----
const esp = () => page.getByRole('region', { name: 'ESP노드', exact: true })

test('노드 상태 — 보고 없음 먼저, 경고 배지 하나, 배터리 V·신호, 마지막 갱신', async () => {
  const rows = esp().locator('tbody tr')
  await expect(rows).toHaveCount(4)
  await expect(rows.nth(0)).toContainText('공학관 402-2')
  await expect(rows.nth(0)).toContainText('응답 없음')
  await expect(rows.nth(1)).toContainText('공학관 402-1')
  await expect(rows.nth(1).getByText('응답 없음')).toHaveAttribute('title', '배터리')
  await expect(rows.nth(1)).toContainText('3.42 V')
  await expect(rows.nth(1)).toContainText('−95 dBm')
  await expect(rows.nth(2)).toContainText('공학관 403')
  await expect(rows.nth(2).getByText('배터리', { exact: true })).toHaveAttribute(
    'title',
    '재동기 중',
  )
  await expect(rows.nth(3)).toContainText('공학관 401')
  await expect(rows.nth(3)).toContainText('동기화됨')
  await expect(rows.nth(3)).toContainText('41/12/3/2')
  await expect(page.getByText(/마지막 갱신 \d\d:\d\d/)).toBeVisible()
  await expect(page.getByRole('link', { name: '노드 상태' })).toHaveAttribute(
    'aria-current',
    'page',
  )
  await shot(page, 'admin-nodes-1440')
})

test('문제 있는 것만 · 건물 필터', async () => {
  await esp().getByLabel('문제 있는 것만').check()
  await expect(esp().locator('tbody tr')).toHaveCount(3)
  await esp().getByLabel('문제 있는 것만').uncheck()
  await page.getByLabel('건물').selectOption({ label: SEED.building })
  await expect(esp().locator('tbody tr')).toHaveCount(4)
  await page.getByLabel('건물').selectOption({ label: '전체' })
})

test('네트워크가 끊겨도 표를 지우지 않는다', async () => {
  // 경로 함수로 — '**/api/**' 는 Vite 모듈(/src/api/client.ts)까지 잡는다
  const isApi = (u: URL) => u.pathname.startsWith('/api/')
  await page.route(isApi, (r) => r.abort())
  await page.getByRole('button', { name: '새로고침' }).click()
  await expect(page.getByText('서버에 연결할 수 없습니다. 네트워크를 확인해 주세요.')).toBeVisible()
  await expect(esp().locator('tbody tr')).toHaveCount(4)
  await page.unroute(isApi)
  await page.getByRole('alert').getByRole('button', { name: '닫기' }).click()
})

test('시각 브로드캐스트 — 연결된 모뎀Pi 가 없으면 그렇게 말한다', async () => {
  await page.getByRole('button', { name: '시각 브로드캐스트' }).click()
  await expect(page.getByText('연결된 모뎀Pi가 없어 보내지 못했습니다.')).toBeVisible()
})

test('재전송 — 방 단위 동기화 요청', async () => {
  const row = esp().locator('tbody tr', { hasText: '공학관 401' })
  await row.getByRole('button', { name: '재전송' }).click()
  await expect(page.getByText('공학관 401호 재전송을 요청했습니다.')).toBeVisible()
})

// ---- 모뎀Pi ----
const modemCard = (id: string) =>
  page
    .getByRole('region', { name: '모뎀Pi', exact: true })
    .getByRole('listitem')
    .filter({ hasText: id })

test('모뎀Pi — 연결 상태 카드, 등록하면 토큰을 한 번만 보여 준다', async () => {
  await expect(modemCard(SEED.modem)).toContainText('연결됨')
  await expect(modemCard(SEED.offlineModem)).toContainText('끊김')
  await expect(modemCard(SEED.offlineModem)).toContainText('접속 기록 없음')
  await page.getByRole('button', { name: '+ 모뎀Pi 등록' }).click()
  await page.getByRole('dialog').getByLabel('모뎀Pi ID').fill('e2e-ui-1')
  await page.getByRole('dialog').getByRole('button', { name: '등록' }).click()
  const code = page.getByRole('dialog').locator('code')
  await expect(code).toBeVisible()
  const token = (await code.textContent())!.trim()
  expect(token.length).toBeGreaterThan(20)
  await expect(page.getByRole('dialog')).toContainText('이 창을 닫으면 다시 볼 수 없습니다.')
  await page.getByRole('dialog').getByRole('button', { name: '복사' }).click()
  await expect(page.getByText('복사했습니다.')).toBeVisible()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(token)
  await shot(page, 'admin-nodes-token-1440')
  await page.keyboard.press('Escape')
  await expect(code).toBeVisible()
  await page.getByRole('dialog').getByRole('button', { name: '닫기' }).click()
  await expect(modemCard('e2e-ui-1')).toContainText('끊김')
})

test('토큰 재발급 — 확인 뒤에만, 새 토큰 표시', async () => {
  await modemCard(SEED.offlineModem).getByRole('button', { name: '토큰 재발급' }).click()
  await expect(page.getByRole('dialog')).toContainText('끊깁니다')
  await page.getByRole('dialog').getByRole('button', { name: '재발급', exact: true }).click()
  await expect(page.getByRole('dialog').locator('code')).toBeVisible()
  await page.getByRole('dialog').getByRole('button', { name: '닫기' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
})
// ---- 등록 대기 ----
test('등록 대기 → 강의실 배정', async () => {
  const row = page
    .getByRole('region', { name: '등록 대기', exact: true })
    .locator('tbody tr', { hasText: SEED.mac })
  await expect(row).toContainText(SEED.modem)
  await expect(row).toContainText('4.10 V')
  await expect(row).toContainText('−68 dBm')
  await row.getByRole('button', { name: '강의실 배정' }).click()
  const d = page.getByRole('dialog')
  await d.getByLabel('건물').selectOption({ label: SEED.building })
  await d.getByLabel('호수').selectOption({ label: '402호' })
  await expect(d.getByLabel('노드').locator('option')).toHaveText([
    '노드 선택',
    '1번 노드 — 사용 중',
    '2번 노드',
  ])
  await d.getByLabel('노드').selectOption({ label: '2번 노드' })
  await shot(page, 'admin-nodes-provision-1440')
  await d.getByRole('button', { name: '배정', exact: true }).click()
  await expect(
    page.getByText(`${SEED.building} 402호에 배정했습니다. 장치가 다음에 깨어나면 적용됩니다.`),
  ).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

// ---- 다른 학교 — 학교 스코프 · 빈 상태 ----
test('다른 학교 관리자 — 우리 학교 장비·전송이 보이지 않고 빈 상태', async ({ browser }) => {
  const other = await browser.newContext({
    baseURL: WEB_URL,
    locale: 'ko-KR',
    viewport: SIZES.admin,
  })
  const p = await other.newPage()
  await p.goto('/admin/')
  await login(p, () => cfg.OTHER_ADMIN)
  await expect(p).toHaveURL(/\/admin\/dashboard$/)
  await expect(p.getByText('아직 전송된 작업이 없습니다').first()).toBeVisible()
  await expect(p.locator('.stat__value')).toHaveText(['—', '—', '—', '0건'])
  await expect(p.locator('svg.hist')).toHaveCount(0)
  await shot(p, 'admin-dashboard-empty-1440')
  await p.getByRole('link', { name: '노드 상태' }).click()
  await expect(p.getByText('등록된 모뎀Pi가 없습니다')).toBeVisible()
  await expect(p.getByText('이 건물에 강의실이 없습니다')).toBeVisible()
  await expect(p.getByText('등록을 기다리는 장치가 없습니다.')).toBeVisible()
  await expect(p.getByText(SEED.modem)).toHaveCount(0)
  await shot(p, 'admin-nodes-empty-1440')
  await other.close()
})
