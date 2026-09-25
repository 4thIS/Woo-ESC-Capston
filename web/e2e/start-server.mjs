// E2E 용 메인Pi 서버 — 매번 빈 DB, CLI 로 학교·관리자 시드, 메일은 콘솔(stdout → e2e/.tmp/server.log)
import { spawn, spawnSync } from 'node:child_process'
import { createWriteStream, mkdirSync, rmSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import cfg from './env.json' with { type: 'json' }

const web = fileURLToPath(new URL('..', import.meta.url))
const serverDir = path.resolve(web, '../server')
const tmp = path.join(web, 'e2e/.tmp')
rmSync(tmp, { recursive: true, force: true })
mkdirSync(tmp, { recursive: true })

const env = {
  ...process.env,
  SERVER_DB: path.join(tmp, 'e2e.db'),
  JWT_SECRET: cfg.JWT_SECRET,
  STUDENT_WEB_URL: cfg.STUDENT_WEB_URL,
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
cli(['create-school', '--name', '우송대', '--net-id', '75', '--email-domain', cfg.SCHOOL_DOMAIN])
cfg.ADMINS.forEach((email, i) =>
  cli(
    ['create-admin', '--school-id', '1', '--email', email, '--name', `관리자${i + 1}`],
    `${cfg.ADMIN_PASSWORD}\n`,
  ),
)

const log = createWriteStream(path.join(tmp, 'server.log'))
const p = spawn(
  'uv',
  ['run', 'uvicorn', '--factory', 'app.main:create_app', '--host', '127.0.0.1', '--port', '8000'],
  { cwd: serverDir, env, shell },
)
p.stdout.pipe(log)
p.stderr.pipe(log)
p.on('exit', (code) => process.exit(code ?? 0))
for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => p.kill())
