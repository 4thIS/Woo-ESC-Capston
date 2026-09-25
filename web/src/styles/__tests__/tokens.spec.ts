import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8')
const doc = read('../../../../docs/design/tokens.md')
const tokens = read('../tokens.css')
const student = read('../surface-student.css')

const cssVar = (css: string, name: string) =>
  css
    .match(new RegExp(`--${name}:\\s*([^;]+);`))?.[1]
    .trim()
    .toLowerCase()

describe('tokens.css 는 tokens.md 를 그대로 옮긴다', () => {
  it('1층 원시 팔레트 값 — (A) 계산값이 어긋나면 실패', () => {
    const rows = [...doc.matchAll(/^\| `([a-z]+)\.(\d+)` \| `(#[0-9A-Fa-f]{6})`/gm)]
    expect(rows.length).toBeGreaterThanOrEqual(17) // gray 10 + 유채색 7
    for (const [, fam, step, hex] of rows) {
      expect(cssVar(tokens, `${fam}-${step}`), `${fam}.${step}`).toBe(hex.toLowerCase())
    }
  })

  it('치수 — admin 은 :root, student 는 [data-surface=student]', () => {
    const rows = [
      ...doc.matchAll(/^\| `((?:font\.size|control\.height|radius)\.\w+)` \| (\S+) \| (\S+) \|/gm),
    ]
    expect(rows.length).toBeGreaterThanOrEqual(11)
    for (const [, name, admin, stu] of rows) {
      const v = name.replace(/\./g, '-')
      expect(cssVar(tokens, v), `${name} admin`).toBe(admin)
      if (stu !== '—' && stu !== admin) expect(cssVar(student, v), `${name} student`).toBe(stu)
    }
  })

  it('2층은 1층을 가리킨다 (값을 복사하지 않는다)', () => {
    expect(cssVar(tokens, 'brand')).toBe('var(--blue-600)')
    expect(cssVar(tokens, 'danger')).toBe('var(--red-700)')
    expect(cssVar(tokens, 'text-3')).toBe('var(--gray-500)')
    expect(cssVar(tokens, 'room-busy-fill')).toBe('var(--red-50)')
    expect(cssVar(tokens, 'bg-student')).toBe('var(--gray-25)')
  })
})
