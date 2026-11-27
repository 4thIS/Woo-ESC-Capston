/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'
import { defineConfig, type Connect, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'

// /admin, /admin/users 처럼 확장자 없는 경로는 관리자 앱 HTML 로. 나머지 SPA fallback 은 index.html(학생).
const ADMIN_PAGE = /^\/admin(\/[^.?]*)?(\?.*)?$/
const adminFallback: Connect.NextHandleFunction = (req, _res, next) => {
  if (req.url && ADMIN_PAGE.test(req.url)) req.url = '/admin.html'
  next()
}
function adminPages(): Plugin {
  return {
    name: 'admin-pages',
    configureServer: (s) => void s.middlewares.use(adminFallback),
    configurePreviewServer: (s) => void s.middlewares.use(adminFallback),
  }
}

// 개발 중에는 메인Pi 서버(uvicorn, 기본 :8000 — VITE_API_TARGET 으로 바꾼다)로 /api·/ws 를 프록시한다.
// 빌드 산출물은 같은 오리진에서 서빙된다.
const API = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000'
export default defineConfig({
  plugins: [vue(), adminPages()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  build: {
    rollupOptions: {
      input: {
        student: fileURLToPath(new URL('./index.html', import.meta.url)),
        admin: fileURLToPath(new URL('./admin.html', import.meta.url)),
      },
    },
  },
  // AI 비서 Worker(모델 실행) 청크를 따로 모은다 — nginx 가 /assets/worker/ 에만 넓힌 CSP 를 붙인다
  worker: {
    format: 'es',
    rollupOptions: {
      output: {
        entryFileNames: 'assets/worker/[name]-[hash].js',
        chunkFileNames: 'assets/worker/[name]-[hash].js',
      },
    },
  },
  server: {
    proxy: {
      '/api': API,
      '/ws': { target: API.replace(/^http/, 'ws'), ws: true },
    },
  },
  test: { environment: 'jsdom', include: ['src/**/*.spec.ts'] },
})
