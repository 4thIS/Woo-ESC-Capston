import {
  expect,
  test,
  type APIRequestContext,
  type BrowserContext,
  type Page,
} from '@playwright/test'
import cfg from './env.json' with { type: 'json' }
import {
  SEED,
  SIZES,
  WEB_URL,
  apiLogin,
  fillLogin,
  nextAdmin,
  seedMonitoring,
  shot,
} from './helpers'

// e2e 는 node 타입 — page.evaluate 콜백은 브라우저에서 돈다
declare const navigator: { clipboard: { readText(): Promise<string> } }

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
  await fillLogin(page, nextAdmin())
  // 전체 실행에서는 앞 파일들이 IP 당 분당 로그인 30회를 채운 채 넘어온다 — 429 면 창이 지난 뒤 한 번 더
  const limited = page.getByText('잠시 후 다시 시도해 주세요')
  await expect(
    page.getByRole('heading', { name: 'ESP노드', exact: true }).or(limited),
  ).toBeVisible()
  if (await limited.isVisible()) {
    test.setTimeout(120_000)
    await page.waitForTimeout(61_000)
    await fillLogin(page, nextAdmin())
  }
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
  expect(modems.map((m) => `${m.modem_id}:${m.connected}`)).toEqual(['e2e-m1:true', 'e2e-m2:false'])
  expect(await get('/api/admin/analytics/latency')).toMatchObject({
    n: 8,
    p50: 25,
    p95: 50,
    max: 95,
    within_30s: 0.625,
    within_90s: 0.875,
  })
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
