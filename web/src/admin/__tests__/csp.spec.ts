import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const read = (name: string) =>
  // new URL(`…${name}`, import.meta.url) 는 Vite 가 자산 주소로 바꿔 버린다 — 경로로 잇는다
  readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../..', name), 'utf8')
const cspOf = (conf: string) => conf.match(/Content-Security-Policy "([^"]+)"/)?.[1] ?? ''
const dir = (csp: string, name: string) =>
  csp
    .split(';')
    .map((s) => s.trim())
    .find((s) => s.startsWith(`${name} `)) ?? ''
const HEADERS = ['X-Content-Type-Options', 'X-Frame-Options', 'Referrer-Policy']

describe('CSP — AI 비서 모델 받기·실행 (관리자 앱만)', () => {
  it('관리자 헤더: Hugging Face 와 그 CDN 으로만 연결, WASM 실행 허용, Worker 는 자기 출처', () => {
    const csp = cspOf(read('security-headers-admin.conf'))
    expect(dir(csp, 'connect-src')).toBe(
      "connect-src 'self' https://huggingface.co https://*.huggingface.co https://*.hf.co",
    )
    expect(dir(csp, 'script-src')).toBe("script-src 'self' 'wasm-unsafe-eval'")
    expect(dir(csp, 'worker-src')).toBe("worker-src 'self'")
    expect(dir(csp, 'default-src')).toBe("default-src 'self'")
    expect(csp).toContain("frame-ancestors 'none'")
  })

  it('관리자 헤더는 공용 헤더의 나머지 보안 헤더를 모두 되풀이한다 (location add_header 는 상속이 끊긴다)', () => {
    const admin = read('security-headers-admin.conf')
    for (const h of HEADERS) expect(admin).toContain(`add_header ${h} `)
  })

  it('공용(학생 앱) 헤더는 넓히지 않는다', () => {
    const csp = cspOf(read('security-headers.conf'))
    expect(csp).not.toContain('huggingface')
    expect(csp).not.toContain('hf.co')
    expect(csp).not.toContain('wasm-unsafe-eval')
  })

  it('nginx: /admin location 만 관리자 헤더를 include 한다', () => {
    const nginx = read('nginx.conf')
    const admin = nginx.match(/location \/admin \{([^}]+)\}/)?.[1] ?? ''
    expect(admin).toContain('security-headers-admin.conf')
    expect(admin).not.toMatch(/snippets\/security-headers\.conf/)
  })

  it('nginx: Worker 청크(/assets/worker/)도 관리자 헤더 — Worker 의 CSP 는 Worker 스크립트 응답 헤더로 정해진다', () => {
    const nginx = read('nginx.conf')
    const worker = nginx.match(/location \/assets\/worker\/ \{([^}]+)\}/)?.[1] ?? ''
    expect(worker).toContain('security-headers-admin.conf')
    expect(worker).toContain('immutable')
    expect(read('vite.config.ts')).toContain("'assets/worker/[name]-[hash].js'")
    expect(read('Dockerfile')).toContain('security-headers-admin.conf')
  })
})
