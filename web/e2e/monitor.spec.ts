import { expect, test, type APIRequestContext, type BrowserContext } from '@playwright/test'
import cfg from './env.json' with { type: 'json' }
import { SEED, SIZES, WEB_URL, apiLogin, seedMonitoring } from './helpers'

// 한 파일 = 한 브라우저 컨텍스트·로그인 한 번 — 서버의 IP 당 분당 로그인 30회 상한 (F1 plan Task 13 메모)
test.describe.configure({ mode: 'serial' })
let ctx: BrowserContext
let api: APIRequestContext

test.beforeAll(async ({ browser }) => {
  ctx = await browser.newContext({
    baseURL: WEB_URL,
    locale: 'ko-KR',
    viewport: SIZES.admin,
    permissions: ['clipboard-read', 'clipboard-write'],
  })
  api = ctx.request
  await seedMonitoring(api)
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
