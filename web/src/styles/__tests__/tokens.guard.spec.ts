import { describe, expect, it } from 'vitest'

// 화면·컴포넌트는 2·3층만 쓴다 (spec §3.1). 원시 팔레트와 16진 색은 styles/tokens.css 에서만.
const files = import.meta.glob('/src/**/*.vue', { query: '?raw', import: 'default', eager: true })
const PRIMITIVE = /--(gray|blue|red|teal|gold)-\d/
const HEX = /#[0-9a-fA-F]{3,8}\b/

describe('토큰 가드', () => {
  it.each(Object.entries(files))('%s 는 원시 팔레트·16진 색을 쓰지 않는다', (_path, src) => {
    const style =
      String(src)
        .match(/<style[\s\S]*?<\/style>/g)
        ?.join('\n') ?? ''
    const template = String(src).match(/<template>[\s\S]*<\/template>/)?.[0] ?? ''
    expect(style + template).not.toMatch(PRIMITIVE)
    expect(style + template).not.toMatch(HEX)
  })
})
