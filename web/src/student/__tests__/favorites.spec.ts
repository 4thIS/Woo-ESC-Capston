import { beforeEach, describe, expect, it, vi } from 'vitest'

// favorites 는 모듈이 뜰 때 한 번 읽는다 — 매 테스트 새로 import
const load = () => import('@/student/favorites')

beforeEach(() => {
  vi.restoreAllMocks()
  vi.resetModules()
  localStorage.clear()
})

describe('즐겨찾기 (student-room.md — localStorage 호수 배열)', () => {
  it('저장된 목록을 읽고, 토글하면 esc.fav 에 호수 배열로 남긴다', async () => {
    localStorage.setItem('esc.fav', JSON.stringify(['E-401']))
    const f = await load()
    expect(f.favorites.value).toEqual(['E-401'])
    f.toggleFavorite(f.favKey('E', 405))
    expect(JSON.parse(localStorage.getItem('esc.fav')!)).toEqual(['E-401', 'E-405'])
    f.toggleFavorite('E-401')
    expect(f.favorites.value).toEqual(['E-405'])
    expect(localStorage.getItem('esc.fav')).toBe('["E-405"]')
  })

  it('깨진 값·모양이 다른 값은 버린다', async () => {
    localStorage.setItem('esc.fav', '{oops')
    expect((await load()).favorites.value).toEqual([])
    vi.resetModules()
    localStorage.setItem('esc.fav', JSON.stringify(['E-401', 3, '<img>', 'e-1', 'K-12345']))
    expect((await load()).favorites.value).toEqual(['E-401'])
    vi.resetModules()
    localStorage.setItem('esc.fav', JSON.stringify({ a: 1 }))
    expect((await load()).favorites.value).toEqual([])
  })

  it('localStorage 가 막혀도(사생활 보호 모드) 이번 방문 동안은 동작한다', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('quota', 'QuotaExceededError')
    })
    const f = await load()
    expect(f.favorites.value).toEqual([])
    expect(() => f.toggleFavorite('E-401')).not.toThrow()
    expect(f.favorites.value).toEqual(['E-401'])
    expect(f.lastBld()).toBeNull()
    expect(() => f.rememberBld('E')).not.toThrow()
  })

  it('마지막 건물 — 대문자 한 글자만 믿는다', async () => {
    const f = await load()
    expect(f.lastBld()).toBeNull()
    f.rememberBld('K')
    expect(f.lastBld()).toBe('K')
    localStorage.setItem('esc.lastBld', '../admin')
    expect(f.lastBld()).toBeNull()
  })
})
