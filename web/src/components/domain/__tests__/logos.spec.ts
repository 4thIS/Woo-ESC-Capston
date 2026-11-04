import { readdirSync, readFileSync, statSync } from 'node:fs'
import { extname, join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const DIR = resolve(process.cwd(), 'src/assets/logos')
interface Entry {
  slug: string
  name: string
  rank: number
  file: string
  source: string
  license: string
  aspect: number
}
const list = JSON.parse(readFileSync(join(DIR, 'logos.json'), 'utf8')) as Entry[]
const path = (e: Entry) => join(DIR, e.file)

function pngInfo(buf: Buffer) {
  expect(buf.subarray(1, 4).toString()).toBe('PNG')
  return {
    w: buf.readUInt32BE(16),
    h: buf.readUInt32BE(20),
    alpha: buf[25] === 4 || buf[25] === 6 || buf.includes('tRNS'),
  }
}

function svgAspect(text: string) {
  const vb = /viewBox\s*=\s*["']\s*[-\d.e]+[\s,]+[-\d.e]+[\s,]+([\d.e]+)[\s,]+([\d.e]+)/i.exec(text)
  if (vb) return Number(vb[1]) / Number(vb[2])
  const w = /<svg[^>]*\swidth\s*=\s*["']([\d.]+)/i.exec(text)
  const h = /<svg[^>]*\sheight\s*=\s*["']([\d.]+)/i.exec(text)
  return Number(w?.[1]) / Number(h?.[1])
}

function fileAspect(e: Entry) {
  if (e.file.endsWith('.png')) {
    const { w, h } = pngInfo(readFileSync(path(e)))
    return w / h
  }
  return svgAspect(readFileSync(path(e), 'utf8'))
}

describe('대학 로고 파일 (spec §2)', () => {
  it('16~26개, rank 오름차순·중복 없음, 필수 값이 있다', () => {
    expect(list.length).toBeGreaterThanOrEqual(16)
    expect(list.length).toBeLessThanOrEqual(26)
    const ranks = list.map((e) => e.rank)
    expect(ranks).toEqual([...new Set(ranks)].sort((a, b) => a - b))
    for (const e of list) {
      expect(e.slug).toMatch(/^[a-z0-9-]+$/)
      expect(e.name).not.toBe('')
      expect(e.license).not.toBe('')
    }
  })

  it('file 이 모두 있고 목록 밖 파일은 없다. 확장자는 svg 또는 png', () => {
    const onDisk = readdirSync(DIR)
      .filter((f) => f !== 'logos.json')
      .sort()
    expect(onDisk).toEqual(list.map((e) => e.file).sort())
    for (const f of onDisk) expect(['.svg', '.png']).toContain(extname(f))
  })

  it('svg 40 KB · png 120 KB 이하, 합계 800 KB 이하', () => {
    let total = 0
    for (const e of list) {
      const size = statSync(path(e)).size
      total += size
      expect(size, e.file).toBeLessThanOrEqual((e.file.endsWith('.png') ? 120 : 40) * 1024)
    }
    expect(total).toBeLessThanOrEqual(800 * 1024)
  })

  it('aspect 는 파일 비율(svg viewBox, png IHDR)과 ±5% 안에서 같고 4 이하', () => {
    for (const e of list) {
      expect(e.aspect, e.file).toBeLessThanOrEqual(4)
      expect(Math.abs(fileAspect(e) / e.aspect - 1), e.file).toBeLessThanOrEqual(0.05)
    }
  })

  it('png 는 알파가 있다(IHDR color type 4·6 또는 tRNS)', () => {
    for (const e of list.filter((x) => x.file.endsWith('.png'))) {
      expect(pngInfo(readFileSync(path(e))).alpha, e.file).toBe(true)
    }
  })

  it('svg 에 <script · on*= · 외부 href(http) 가 없다', () => {
    for (const e of list.filter((x) => x.file.endsWith('.svg'))) {
      const text = readFileSync(path(e), 'utf8')
      expect(text, e.file).not.toMatch(/<script/i)
      expect(text, e.file).not.toMatch(/\son[a-z]+\s*=/i)
      expect(text, e.file).not.toMatch(/href\s*=\s*["']https?:/i)
    }
  })

  it('source 는 https 주소다', () => {
    for (const e of list) expect(e.source, e.slug).toMatch(/^https:\/\//)
  })
})
