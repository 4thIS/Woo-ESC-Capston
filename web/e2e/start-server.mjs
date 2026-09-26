// E2E 용 메인Pi 서버 — 매번 빈 DB, CLI 로 학교·관리자 시드, 메일은 콘솔(stdout → e2e/.tmp/server.log)
// 서버 체크아웃: E2E_SERVER_DIR (web/ 기준 상대 또는 절대 경로, 기본 ../server) — web/CLAUDE.md §E2E
// 포트: E2E_API_PORT(기본 8000) · E2E_WEB_PORT(기본 5173, 메일 링크 STUDENT_WEB_URL 용)
import { spawn, spawnSync } from 'node:child_process'
import { createWriteStream, existsSync, mkdirSync, rmSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import cfg from './env.json' with { type: 'json' }

const web = fileURLToPath(new URL('..', import.meta.url))
const serverDir = path.resolve(web, process.env.E2E_SERVER_DIR ?? '../server')
if (!existsSync(path.join(serverDir, 'app', 'main.py'))) {
  console.error(`E2E_SERVER_DIR 가 메인Pi 서버 체크아웃이 아닙니다: ${serverDir}`)
  process.exit(1)
}
const apiPort = process.env.E2E_API_PORT ?? '8000'
const webPort = process.env.E2E_WEB_PORT ?? '5173'
const tmp = path.join(web, 'e2e/.tmp')
rmSync(tmp, { recursive: true, force: true })
mkdirSync(tmp, { recursive: true })

const env = {
  ...process.env,
  SERVER_DB: path.join(tmp, 'e2e.db'),
  JWT_SECRET: cfg.JWT_SECRET,
  STUDENT_WEB_URL: `http://127.0.0.1:${webPort}`,
  MAIL_BACKEND: cfg.MAIL_BACKEND,
  DEBUG: cfg.DEBUG,
  PYTHONUNBUFFERED: cfg.PYTHONUNBUFFERED,
  PYTHONIOENCODING: cfg.PYTHONIOENCODING,
}
const shell = process.platform === 'win32'

function cli(args, input) {
  const r = spawnSync('uv', ['run', 'python', '-m', 'app.cli', ...args], {
    cwd: serverDir,
    env,
    input,
    encoding: 'utf8',
    shell,
  })
  if (r.status !== 0) {
    console.error(r.stdout, r.stderr)
    process.exit(1)
  }
}

// CLI 가 alembic upgrade head 를 먼저 돈다. 비밀번호는 stdin(비TTY)으로
cli([
  'create-school',
  '--name',
  '명지전문대학',
  '--net-id',
  '75',
  '--email-domain',
  cfg.SCHOOL_DOMAIN,
])
cfg.ADMINS.forEach((email, i) =>
  cli(
    ['create-admin', '--school-id', '1', '--email', email, '--name', `관리자${i + 1}`],
    `${cfg.ADMIN_PASSWORD}\n`,
  ),
)
// 다른 학교(id 2) — 학교 스코프·빈 상태 E2E 용 (monitor.spec.ts)
cli(['create-school', '--name', '타학교', '--net-id', '76', '--email-domain', cfg.OTHER_DOMAIN])
cli(
  ['create-admin', '--school-id', '2', '--email', cfg.OTHER_ADMIN, '--name', '타학교관리자'],
  `${cfg.ADMIN_PASSWORD}\n`,
)

const log = createWriteStream(path.join(tmp, 'server.log'))
log.write(`[e2e] server dir ${serverDir}\n`)
const p = spawn(
  'uv',
  ['run', 'uvicorn', '--factory', 'app.main:create_app', '--host', '127.0.0.1', '--port', apiPort],
  { cwd: serverDir, env, shell },
)
p.stdout.pipe(log)
p.stderr.pipe(log)
p.on('exit', (code) => process.exit(code ?? 0))
for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => p.kill())
