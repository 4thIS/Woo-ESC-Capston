import { ref } from 'vue'

// 즐겨찾기·마지막 건물은 localStorage (student-room.md — 서버 필드 없음, 기기를 바꾸면 사라짐을 감수).
// 자격증명은 여기 두지 않는다(auth.md). 사생활 보호 모드면 읽기·쓰기가 던진다 — 이번 방문 동안만 기억한다.
const FAV = 'esc.fav'
const LAST = 'esc.lastBld'
const KEY_RE = /^[A-Z]-\d{1,4}$/

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* 기억 못 해도 화면은 동작한다 */
  }
}
function parse(raw: string | null): string[] {
  try {
    const v: unknown = JSON.parse(raw ?? '[]')
    return Array.isArray(v)
      ? v.filter((x): x is string => typeof x === 'string' && KEY_RE.test(x))
      : []
  } catch {
    return []
  }
}

/** 'E-401' */
export const favKey = (bld: string, room: number) => `${bld}-${room}`
export const favorites = ref<string[]>(parse(read(FAV)))

export function toggleFavorite(key: string): void {
  favorites.value = favorites.value.includes(key)
    ? favorites.value.filter((k) => k !== key)
    : [...favorites.value, key]
  write(FAV, JSON.stringify(favorites.value))
}

/** `/` 로 들어왔을 때 보낼 건물 — 대문자 한 글자만 믿는다 */
export function lastBld(): string | null {
  const v = read(LAST)
  return v && /^[A-Z]$/.test(v) ? v : null
}
export const rememberBld = (bld: string) => write(LAST, bld)
