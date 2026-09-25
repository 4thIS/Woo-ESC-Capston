import { defineConfig, devices } from '@playwright/test'

// 서버는 매번 새 DB 로 띄운다(재사용 안 함). 서버 상태를 공유하므로 직렬 실행.
export default defineConfig({
  testDir: './e2e',
  workers: 1,
  fullyParallel: false,
  timeout: 30_000,
  use: { baseURL: 'http://127.0.0.1:5173', trace: 'retain-on-failure', locale: 'ko-KR' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: 'node e2e/start-server.mjs',
      url: 'http://127.0.0.1:8000/api/health',
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: 'pnpm dev --host 127.0.0.1 --port 5173 --strictPort',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: !process.env.CI,
    },
  ],
})
