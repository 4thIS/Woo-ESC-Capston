import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, type APIRequestContext, type Page } from '@playwright/test'
import cfg from './env.json' with { type: 'json' }

const web = fileURLToPath(new URL('..', import.meta.url))
const serverDir = path.resolve(web, '../server')
const logPath = path.join(web, 'e2e/.tmp/server.log')

export const SIZES = {
  admin: { width: 1440, height: 900 },
  student: { width: 390, height: 844 },
} as const
export const PASSWORD = cfg.ADMIN_PASSWORD

let rr = 0
/** 로그인 상한(이메일당 분당 5회)을 피하려고 관리자 계정을 돌려 쓴다 */
export const nextAdmin = () => cfg.ADMINS[rr++ % cfg.ADMINS.length]

export const uniqEmail = (prefix: string) =>
  `${prefix}${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}@${cfg.SCHOOL_DOMAIN}`

export async function shot(page: Page, name: string) {
  await page.screenshot({ path: path.join(web, 'e2e/.shots', `${name}.png`), fullPage: true })
}

/** 콘솔 메일 백엔드가 stdout 에 찍은 마지막 링크의 토큰 (메일은 응답 뒤 BackgroundTasks 로 나간다) */
export async function mailToken(to: string): Promise<string> {
  const re = new RegExp(
    `\\[mail\\] to=${to.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')} [^\\n]*\\n[^\\n]*?(?:\\n[^\\n]*?)*?#token=([A-Za-z0-9_-]+)`,
    'g',
  )
  let token: string | undefined
  await expect
    .poll(
      () => {
        const log = existsSync(logPath) ? readFileSync(logPath, 'utf8') : ''
        token = [...log.matchAll(re)].at(-1)?.[1]
        return token
      },
      { timeout: 5_000 },
    )
    .toBeTruthy()
  return token!
}

export function cli(args: string[], input?: string) {
  const r = spawnSync('uv', ['run', 'python', '-m', 'app.cli', ...args], {
    cwd: serverDir,
    env: {
      ...process.env,
      SERVER_DB: path.join(web, 'e2e/.tmp/e2e.db'),
      JWT_SECRET: cfg.JWT_SECRET,
      STUDENT_WEB_URL: cfg.STUDENT_WEB_URL,
      MAIL_BACKEND: cfg.MAIL_BACKEND,
      DEBUG: cfg.DEBUG,
      PYTHONIOENCODING: cfg.PYTHONIOENCODING,
    },
    input,
    encoding: 'utf8',
    shell: process.platform === 'win32',
  })
  expect(r.status, r.stderr).toBe(0)
}

export async function apiLogin(request: APIRequestContext, email: string, pw = PASSWORD) {
  const r = await request.post('/api/auth/login', { data: { email, password: pw } })
  expect(r.status()).toBe(200)
  return (await r.json()).token as string
}

/** 가입 신청 → 메일 토큰 → verify/open → verify (+ 승인). 화면을 거치지 않는 준비용 */
export async function createStudent(
  request: APIRequestContext,
  opts: { email?: string; name?: string; studentNo?: string; approve?: boolean } = {},
) {
  const email = opts.email ?? uniqEmail('s')
  const studentNo = opts.studentNo ?? `S${Date.now().toString(36)}`
  expect((await request.post('/api/auth/signup', { data: { email } })).status()).toBe(202)
  const token = await mailToken(email)
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

export async function fillLogin(page: Page, email: string, pw = PASSWORD) {
  await page.getByLabel(/웹메일|이메일/).fill(email)
  await page.getByLabel('비밀번호').fill(pw)
  await page.getByRole('button', { name: '로그인' }).click()
}
