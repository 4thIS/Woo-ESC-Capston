import { defineConfig, devices } from '@playwright/test'

// 서버는 매번 새 DB 로 띄운다(재사용 안 함). 서버 상태를 공유하므로 직렬 실행.
// 포트는 E2E_API_PORT(기본 8000)·E2E_WEB_PORT(기본 5173) — 수동 서버와 겹칠 때 (web/CLAUDE.md §E2E)
const API = `http://127.0.0.1:${process.env.E2E_API_PORT ?? '8000'}`
const WEB_PORT = process.env.E2E_WEB_PORT ?? '5173'
export default defineConfig({
  testDir: './e2e',
  // workers 1 은 필수 — monitor.spec 이 beforeAll 에서 다른 건물의 outbox 를 지운다(동시에 도는 spec 이 있으면 그 행이 사라진다)
  workers: 1,
  fullyParallel: false,
  timeout: 30_000,
  use: { baseURL: `http://127.0.0.1:${WEB_PORT}`, trace: 'retain-on-failure', locale: 'ko-KR' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: 'node e2e/start-server.mjs',
      url: `${API}/api/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `pnpm dev --host 127.0.0.1 --port ${WEB_PORT} --strictPort`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: !process.env.CI,
      env: { VITE_API_TARGET: API },
    },
  ],
})
