import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test, type APIRequestContext, type Page } from '@playwright/test'
import cfg from './env.json' with { type: 'json' }

const web = fileURLToPath(new URL('..', import.meta.url))
// start-server.mjs 와 같은 규칙 — E2E_SERVER_DIR(web/ 기준 상대 또는 절대), 기본 ../server
const serverDir = path.resolve(web, process.env.E2E_SERVER_DIR ?? '../server')
const logPath = path.join(web, 'e2e/.tmp/server.log')
const shell = process.platform === 'win32'
/** Vite dev 서버 주소 — E2E_WEB_PORT(기본 5173), playwright.config.ts 와 같은 규칙 */
export const WEB_URL = `http://127.0.0.1:${process.env.E2E_WEB_PORT ?? '5173'}`
const serverEnv = () => ({
  ...process.env,
  SERVER_DB: path.join(web, 'e2e/.tmp/e2e.db'),
  JWT_SECRET: cfg.JWT_SECRET,
  STUDENT_WEB_URL: WEB_URL,
  MAIL_BACKEND: cfg.MAIL_BACKEND,
  DEBUG: cfg.DEBUG,
  PYTHONIOENCODING: cfg.PYTHONIOENCODING,
})

export const SIZES = {
  admin: { width: 1440, height: 900 },
  student: { width: 390, height: 844 },
} as const
export const PASSWORD = cfg.ADMIN_PASSWORD

let rr = 0
/** 로그인 상한(이메일당 분당 5회)을 피하려고 관리자 계정을 돌려 쓴다.
 * IP 당 분당 30회 상한(모두 127.0.0.1)은 돌려 써도 피하지 못한다 — 한 번의 E2E 실행이 1분 안에 30번 넘게 로그인하면 429 */
export const nextAdmin = () => cfg.ADMINS[rr++ % cfg.ADMINS.length]

export const uniqEmail = (prefix: string) =>
  `${prefix}${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}@${cfg.SCHOOL_DOMAIN}`

export async function shot(page: Page, name: string) {
  await page.screenshot({ path: path.join(web, 'e2e/.shots', `${name}.png`), fullPage: true })
}

/** 콘솔 메일 백엔드가 stdout 에 찍은 `to` 앞 메일 중 링크 토큰이 있는 것들 (오래된 것부터).
 * 로그를 `[mail] ` 줄에서 잘라 블록 하나 = 메일 하나로 본다 — 다른 사람 메일로 넘어가지 않는다 */
function tokensFor(to: string): string[] {
  const log = existsSync(logPath) ? readFileSync(logPath, 'utf8') : ''
  return log
    .split(/^(?=\[mail\] )/m)
    .filter((b) => b.startsWith(`[mail] to=${to} `))
    .map((b) => /#token=([A-Za-z0-9_-]+)/.exec(b)?.[1])
    .filter((t): t is string => !!t)
}

/** 메일을 부르기 전에 세어 두고 `mailToken(to, { after })` 로 넘긴다 */
export const mailCount = (to: string) => tokensFor(to).length

/** `to` 앞 토큰 메일이 `after` 통보다 많아지면 마지막 것의 토큰 (메일은 응답 뒤 BackgroundTasks 로 나간다) */
export async function mailToken(to: string, { after = 0 } = {}): Promise<string> {
  let tokens: string[] = []
  await expect
    .poll(() => (tokens = tokensFor(to)).length, { timeout: 5_000 })
    .toBeGreaterThan(after)
  return tokens.at(-1)!
}

/** 이메일별 관리자 토큰 캐시 — IP 당 분당 30회 로그인 상한을 아끼려고 (비밀번호가 기본값일 때만) */
const tokens = new Map<string, string>()

export function cli(args: string[], input?: string) {
  const r = spawnSync('uv', ['run', 'python', '-m', 'app.cli', ...args], {
    cwd: serverDir,
    env: serverEnv(),
    input,
    encoding: 'utf8',
    shell,
  })
  expect(r.status, r.stderr).toBe(0)
  // set-user 는 token_version 을 올린다 — 그 사람의 캐시된 토큰은 이제 401
  const i = args.indexOf('--email')
  if (args[0] === 'set-user' && i >= 0) tokens.delete(args[i + 1])
}

/** **테스트 전용.** 무선 트래픽(STATUS·pending 발견·ACK)으로만 생기는 행을 E2E DB 에 직접 넣는다 —
 * 관리자 REST 로는 만들 수 없다. 스크립트는 stdin 으로 넘긴다(Windows shell 인용 문제 회피). 시각은 SQLite 'now'(UTC) 기준 */
export function sql(script: string) {
  const py = [
    'import os, sqlite3',
    'c = sqlite3.connect(os.environ["SERVER_DB"], timeout=10)',
    `c.executescript(${JSON.stringify(script)})`,
    'c.close()',
  ].join('\n')
  const r = spawnSync('uv', ['run', 'python', '-'], {
    cwd: serverDir,
    env: serverEnv(),
    input: py,
    encoding: 'utf8',
    shell,
  })
  expect(r.status, r.stderr).toBe(0)
}

/** 로그인 상한(IP 당 분당 30회)은 슬라이딩 60초 — 그만큼 기다리면 이메일·IP 창이 모두 비어 있다 */
const LIMIT_WAIT_MS = 61_000
async function waitOutLimit(page?: Page) {
  test.setTimeout(test.info().timeout + LIMIT_WAIT_MS + 5_000)
  if (page) await page.waitForTimeout(LIMIT_WAIT_MS)
  else await new Promise((r) => setTimeout(r, LIMIT_WAIT_MS))
}

export async function apiLogin(request: APIRequestContext, email: string, pw = PASSWORD) {
  const hit = pw === PASSWORD ? tokens.get(email) : undefined
  if (hit) return hit
  const post = () => request.post('/api/auth/login', { data: { email, password: pw } })
  let r = await post()
  // 전체 실행은 IP 당 분당 30회 상한에 걸려 있다 — 429 면 창이 지난 뒤 한 번 더
  if (r.status() === 429) {
    await waitOutLimit()
    r = await post()
  }
  expect(r.status()).toBe(200)
  const token = (await r.json()).token as string
  if (pw === PASSWORD) tokens.set(email, token)
  return token
}

/** 가입 신청 → 메일 토큰 → verify/open → verify (+ 승인). 화면을 거치지 않는 준비용 */
export async function createStudent(
  request: APIRequestContext,
  opts: { email?: string; name?: string; studentNo?: string; approve?: boolean } = {},
) {
  const email = opts.email ?? uniqEmail('s')
  const studentNo = opts.studentNo ?? `S${Date.now().toString(36)}`
  const after = mailCount(email)
  expect((await request.post('/api/auth/signup', { data: { email } })).status()).toBe(202)
  const token = await mailToken(email, { after })
  expect((await request.post('/api/auth/verify/open', { data: { token } })).ok()).toBe(true)
  const v = await request.post('/api/auth/verify', {
    data: { token, name: opts.name ?? '김민준', student_no: studentNo, password: PASSWORD },
  })
  expect(v.ok()).toBe(true)
  if (opts.approve) {
    const t = await apiLogin(request, nextAdmin())
    const a = await request.post(`/api/admin/users/${encodeURIComponent(email)}/approve`, {
      headers: { authorization: `Bearer ${t}` },
    })
    expect(a.ok()).toBe(true)
  }
  return { email, studentNo, password: PASSWORD }
}

/** 로그인 폼 제출. 응답이 429(IP 당 분당 30회 상한 — 전체 실행이 그 언저리에 있다)면 창이 지난 뒤 한 번 더 내고
 * true 를 돌려준다(그 사이 이메일 상한 창도 비었다). 429 자체를 보려는 테스트는 `retry429: false` */
export async function fillLogin(
  page: Page,
  email: string,
  pw = PASSWORD,
  { retry429 = true } = {},
): Promise<boolean> {
  await page.getByLabel(/웹메일|이메일/).fill(email)
  await page.getByLabel('비밀번호').fill(pw)
  const res = page.waitForResponse((r) => r.url().includes('/api/auth/login'))
  await page.getByRole('button', { name: '로그인' }).click()
  if (!retry429 || (await res).status() !== 429) return false
  await waitOutLimit(page)
  await fillLogin(page, email, pw, { retry429: false })
  return true
}

/** 전체 실행에서는 앞 파일들이 IP 당 분당 로그인 30회를 채운 채 넘어온다 — 429 면 창이 지난 뒤 한 번 더.
 * email 은 함수로 받는다 — nextAdmin 처럼 매 시도마다 계정을 돌려 쓸 수 있게 */
export async function login(page: Page, email: () => string) {
  await fillLogin(page, email())
  await expect(page.locator('nav')).toBeVisible()
}

// ---- F3 모니터링 시드 ----

export const SEED = {
  modem: 'e2e-m1',
  offlineModem: 'e2e-m2',
  building: '공학관',
  bld: 'E',
  mac: 'A1B2C3D4E5F6',
} as const

/** SQLite 시각 식 — 서버 DateTime 과 같은 'YYYY-MM-DD HH:MM:SS' (naive UTC) */
const at = (...mods: string[]) =>
  `strftime('%Y-%m-%d %H:%M:%S', ${['now', ...mods].map((m) => `'${m}'`).join(', ')})`
const acked = (type: string, ago: number, secs: number) =>
  `('e2e-m1', 'E', 401, 1, '${type}', '{}', 5, NULL, 'acked', 1, ${at(`-${ago} minutes`)}, ` +
  `${at(`-${ago} minutes`)}, ${at(`-${ago} minutes`, `+${secs} seconds`)}, NULL)`

// ponytail: 이 문자열은 리터럴에서만 만든다(변수 보간 금지) — sql() 은 executescript 로 그대로 실행한다.
// 멱등성은 값 이스케이프가 아니라 seedMonitoring 의 건물 E 존재 검사(가드)에 기대고 있다.
const SEED_SQL = `
UPDATE modems SET connected = 1, agent_ver = '0.4.1', modem_fw = '1.2.0', last_seen_at = ${at()}
  WHERE modem_id = 'e2e-m1';
INSERT OR REPLACE INTO terminal_status
  (bld, room, unit, modem_id, mac, fw, batt_mv, rssi, snr, sched_ver, resv_ver, exam_ver, ident_ver,
   layout, clock_stale, low_batt, uptime_h, last_seen_at, last_ack_at, last_status_at, sync_state)
VALUES
  ('E', 401, 1, 'e2e-m1', '0A1B2C3D4E01', 3, 3980, -71, 7.5, 41, 12, 3, 2, 1, 0, 0, 120,
   ${at('-2 minutes')}, ${at('-2 minutes')}, ${at('-2 minutes')}, 'synced'),
  ('E', 402, 1, 'e2e-m1', '0A1B2C3D4E02', 3, 3420, -95, -3.5, 40, 12, 3, 2, 2, 0, 1, 300,
   ${at('-50 hours')}, ${at('-50 hours')}, ${at('-50 hours')}, 'synced'),
  ('E', 403, 1, 'e2e-m1', '0A1B2C3D4E03', 3, 3900, -82, 2.0, 41, 11, 3, 2, 1, 0, 1, 10,
   ${at('-10 minutes')}, NULL, ${at('-10 minutes')}, 'resync');
INSERT OR REPLACE INTO pending_devices (mac, modem_id, fw, batt_mv, rssi, first_seen_at, last_seen_at)
VALUES ('A1B2C3D4E5F6', 'e2e-m1', 3, 4100, -68, ${at('-3 hours')}, ${at('-1 minutes')});
INSERT INTO outbox
  (modem_id, bld, room, unit, type, payload, priority, new_ver, state, attempts,
   created_at, dispatched_at, finished_at, last_error)
VALUES
  ${[
    acked('SLOT_SET', 90, 8),
    acked('SLOT_SET', 85, 18),
    acked('SLOT_SET', 80, 25),
    acked('SLOT_SET', 75, 28),
    acked('RESV_SET', 70, 12),
    acked('RESV_SET', 65, 35),
    acked('RESV_SET', 60, 50),
    acked('SLOT_SET', 55, 95),
  ].join(',\n  ')},
  -- 실패는 25시간 전 — 서버 기동 60초 뒤 도는 일일 작업의 '24시간 내 실패 재동기'가 FILE 행을
  -- 더하면 최근 전송 7행이 시드 시각과 경합한다. 7일 실패 타일에는 그대로 잡힌다
  ('e2e-m1', 'E', 401, 1, 'SLOT_SET', '{}', 5, NULL, 'failed', 5, ${at('-26 hours')},
   ${at('-26 hours')}, ${at('-25 hours')}, 'max_retries'),
  ('e2e-m1', 'E', 402, 1, 'RESV_SET', '{}', 5, NULL, 'queued', 0, ${at('-1 minutes')}, NULL, NULL, NULL);
`

/** 노드·전송 화면용 시드 (멱등 — 건물 E 가 있으면 건너뛴다. 서버는 E2E 실행마다 새 DB).
 * 건물·방·모뎀은 실제 관리자 REST 로, 무선에서만 오는 행만 sql() 로 */
export async function seedMonitoring(request: APIRequestContext) {
  const headers = { authorization: `Bearer ${await apiLogin(request, cfg.ADMINS[0])}` }
  const r = await request.get('/api/buildings', { headers })
  expect(r.status()).toBe(200)
  if (((await r.json()) as { bld: string }[]).some((b) => b.bld === SEED.bld)) return
  for (const modem_id of [SEED.modem, SEED.offlineModem]) {
    const m = await request.post('/api/lora/modems', { headers, data: { modem_id } })
    expect(m.status(), modem_id).toBe(200)
  }
  const b = await request.post('/api/buildings', {
    headers,
    data: { school_id: 1, name: SEED.building, bld: SEED.bld, modem_id: SEED.modem },
  })
  expect(b.status()).toBe(200)
  const building_id = ((await b.json()) as { id: number }).id
  for (const [room, units] of [
    [401, 1],
    [402, 2],
    [403, 1],
  ]) {
    const rr = await request.post('/api/rooms', { headers, data: { building_id, room, units } })
    expect(rr.status(), String(room)).toBe(200)
  }
  sql(SEED_SQL)
}

// ---- F2 관리자 운영 ----

/** KST 오늘 + n일 'YYYY-MM-DD' — 날짜 흐름은 상대 날짜로 (서버 시계를 고정할 수 없다, spec §7.2) */
export const kstDate = (offsetDays = 0) =>
  new Date(Date.now() + 9 * 3_600_000 + offsetDays * 86_400_000).toISOString().slice(0, 10)

/** 우리 학교 모뎀 등록 (이미 있으면 건너뛴다 — 같은 실행 안에서 여러 spec 이 부른다) */
export async function ensureModems(request: APIRequestContext, ids: string[]) {
  const headers = { authorization: `Bearer ${await apiLogin(request, cfg.ADMINS[0])}` }
  const r = await request.get('/api/lora/modems', { headers })
  expect(r.status()).toBe(200)
  const have = ((await r.json()) as { modem_id: string }[]).map((m) => m.modem_id)
  for (const modem_id of ids.filter((i) => !have.includes(i))) {
    const m = await request.post('/api/lora/modems', { headers, data: { modem_id } })
    expect(m.status(), modem_id).toBe(200)
  }
}

/** 강의실 설정·주간 시간표 E2E 용 — 운영관(K) 101·102·201·202, 학생 예약은 101 만.
 * 모뎀은 등록만 한다(연결 없음) → outbox 는 대기로 남고, 무선 결과는 테스트가 sql() 로 흉내 낸다 */
export const OPS = {
  building: '운영관',
  bld: 'K',
  modem: 'e2e-m6',
  rooms: [101, 102, 201, 202],
} as const

export async function seedOps(
  request: APIRequestContext,
): Promise<{ buildingId: number; roomIds: Record<number, number> }> {
  const headers = { authorization: `Bearer ${await apiLogin(request, cfg.ADMINS[0])}` }
  const get = async <T>(p: string): Promise<T> => {
    const r = await request.get(p, { headers })
    expect(r.status(), p).toBe(200)
    return (await r.json()) as T
  }
  let b = (await get<{ id: number; bld: string }[]>('/api/buildings')).find(
    (x) => x.bld === OPS.bld,
  )
  if (!b) {
    await ensureModems(request, [OPS.modem])
    const r = await request.post('/api/buildings', {
      headers,
      data: { school_id: 1, name: OPS.building, bld: OPS.bld, modem_id: OPS.modem },
    })
    expect(r.status()).toBe(200)
    b = (await r.json()) as { id: number; bld: string }
    for (const room of OPS.rooms) {
      const rr = await request.post('/api/rooms', {
        headers,
        data: { building_id: b.id, room, units: 1, reservable: room === 101 },
      })
      expect(rr.status(), String(room)).toBe(200)
    }
  }
  const buildingId = b.id
  const rooms = await get<{ id: number; building_id: number; room: number }[]>('/api/rooms')
  return {
    buildingId,
    roomIds: Object.fromEntries(
      rooms.filter((r) => r.building_id === buildingId).map((r) => [r.room, r.id]),
    ),
  }
}
