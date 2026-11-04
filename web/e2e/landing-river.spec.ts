import { expect, test, type Page } from '@playwright/test'

// e2e 는 node 타입(tsconfig.node.json) — page.evaluate 콜백은 브라우저에서 도는데 DOM lib 이 없다
interface Box {
  getBoundingClientRect(): {
    left: number
    top: number
    right: number
    bottom: number
    width: number
    height: number
  }
}
declare const document: {
  querySelector(s: string): Box | null
  querySelectorAll(s: string): Box[]
  documentElement: { scrollWidth: number; clientWidth: number }
}

// 메인 페이지 로고 강 (docs/specs/2026-11-04-landing-logo-river-design.md §8)
// 프로젝트 기본은 움직임 줄이기라 물리는 여기서 켠다
test.use({ reducedMotion: 'no-preference', viewport: { width: 1280, height: 800 } })

/** 덮이지 않은 곳의 로고 하나 — 번호와 화면 중심 */
async function visibleLogo(page: Page) {
  return page.evaluate(() => {
    const imgs = [...document.querySelectorAll('.river--physics img')]
    const hero = document.querySelector('.hero')!.getBoundingClientRect()
    const i = imgs.findIndex((el) => {
      const r = el.getBoundingClientRect()
      const cx = r.left + r.width / 2
      const cy = r.top + r.height / 2
      return cx > 800 && cx < hero.right - 150 && cy > 120 && cy < hero.bottom - 120
    })
    const r = imgs[i].getBoundingClientRect()
    return { i, x: r.left + r.width / 2, y: r.top + r.height / 2 }
  })
}
async function centerOf(page: Page, i: number) {
  return page.evaluate((n) => {
    const r = document.querySelectorAll('.river--physics img')[n].getBoundingClientRect()
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 }
  }, i)
}
async function openPc(page: Page) {
  await page.goto('/')
  await expect(page.locator('.river--physics img').first()).toBeVisible()
}

test('PC — 잡으면 포인터를 따라 멈춰 있고, 다른 로고는 계속 흐른다', async ({ page }) => {
  await openPc(page)
  const { i, x, y } = await visibleLogo(page)
  const other = i === 0 ? 1 : 0
  await page.mouse.move(x, y)
  await page.mouse.down()
  await page.mouse.move(x + 40, y + 60, { steps: 5 })
  await page.waitForTimeout(400)
  const held = await centerOf(page, i)
  expect(Math.abs(held.x - (x + 40))).toBeLessThan(10)
  expect(Math.abs(held.y - (y + 60))).toBeLessThan(10)
  const before = await centerOf(page, other)
  await page.waitForTimeout(800)
  expect(Math.abs((await centerOf(page, i)).x - held.x)).toBeLessThan(3)
  expect((await centerOf(page, other)).x).not.toBe(before.x)
  await page.mouse.up()
})

test('PC — 던지면 날아갔다가 5초 안에 왼쪽 약 60 px/s 로 돌아온다', async ({ page }) => {
  await openPc(page)
  const { i, x, y } = await visibleLogo(page)
  await page.mouse.move(x, y)
  await page.mouse.down()
  for (let n = 1; n <= 6; n++) {
    await page.mouse.move(x - n * 30, y)
    await page.waitForTimeout(16)
  }
  const atRelease = await centerOf(page, i)
  await page.mouse.up()
  await page.waitForTimeout(250)
  expect((await centerOf(page, i)).x).toBeLessThan(atRelease.x - 20)
  await page.waitForTimeout(5000)
  const a = await centerOf(page, i)
  await page.waitForTimeout(1000)
  const b = await centerOf(page, i)
  expect(a.x - b.x).toBeGreaterThan(35)
  expect(a.x - b.x).toBeLessThan(90)
})

test('PC — 로그인 링크는 잡기와 상관없이 /login 으로 간다', async ({ page }) => {
  await openPc(page)
  await page.locator('.hero').getByRole('link', { name: '로그인' }).click()
  await expect(page).toHaveURL(/\/login$/)
})

test('PC — 멈춤 누르면 위치 고정, 재생하면 이어서', async ({ page }) => {
  await openPc(page)
  await page.getByRole('button', { name: '멈춤' }).click()
  const a = await centerOf(page, 0)
  await page.waitForTimeout(500)
  expect(await centerOf(page, 0)).toEqual(a)
  await page.getByRole('button', { name: '재생' }).click()
  await page.waitForTimeout(500)
  expect((await centerOf(page, 0)).x).not.toBe(a.x)
})

test.describe('터치 화면', () => {
  test.use({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 844 } })
  test('폰 — 잡는 판이 없고 트랙이 흐른다', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.hero .river').first()).toBeAttached()
    await expect(page.locator('.river--physics')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '멈춤' })).toHaveCount(0)
    const left = () =>
      page.evaluate(() => document.querySelector('.river__track')!.getBoundingClientRect().left)
    const a = await left()
    await page.waitForTimeout(500)
    expect(await left()).toBeLessThan(a)
  })
})

test.describe('좁은 인증 왼쪽', () => {
  test.use({ viewport: { width: 700, height: 700 } })
  test('제목이 몇 줄이 되어도 글자 칸이 로고를 덮는다', async ({ page }) => {
    await page.goto('/login')
    const text = page.locator('.auth__intro-text')
    await expect(text).not.toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
    const panel = (await page.locator('.auth__intro').boundingBox())!
    const box = (await text.boundingBox())!
    const lead = (await page.locator('.auth__intro-lead').boundingBox())!
    // 칸 양옆과 바닥까지 덮고, 글자 윗줄도 덮는 칸 안에 있다
    expect(box.x).toBeLessThanOrEqual(panel.x)
    expect(box.x + box.width).toBeGreaterThanOrEqual(panel.x + panel.width - 1)
    expect(box.y + box.height).toBeGreaterThanOrEqual(panel.y + panel.height - 1)
    expect(lead.y).toBeGreaterThanOrEqual(box.y)
  })
})

test('로그인 1280 — 흐르기만 하고 잡히지 않는다', async ({ page }) => {
  await page.goto('/login')
  await expect(page.locator('.auth__intro .river')).toHaveCount(1)
  await expect(page.locator('.river--physics')).toHaveCount(0)
  await expect(page.locator('.auth__intro .river')).toHaveCSS('pointer-events', 'none')
})

test.describe('움직임 줄이기', () => {
  test.use({ reducedMotion: 'reduce' })
  test('두 시점의 위치가 같고 멈춤 버튼이 없다', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.hero .river')).toBeAttached()
    await expect(page.locator('.river--physics')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '멈춤' })).toHaveCount(0)
    const left = () =>
      page.evaluate(() => document.querySelector('.river__track')!.getBoundingClientRect().left)
    await page.waitForTimeout(100)
    const a = await left()
    await page.waitForTimeout(400)
    expect(await left()).toBe(a)
  })
})

for (const width of [390, 768, 1280, 2560]) {
  test.describe(`폭 ${width}`, () => {
    test.use({ viewport: { width, height: 900 } })
    test('가로 스크롤 없음, 스크린샷', async ({ page }) => {
      for (const path of ['/', '/login']) {
        await page.goto(path)
        await page.waitForTimeout(700)
        const over = await page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        )
        expect(over, path).toBeLessThanOrEqual(0)
        // 상단 바는 바탕색과 선으로 나뉘고, 로고 강은 그 아래에서만 흐른다
        if (path === '/') {
          const bar = page.locator('.lh')
          await expect(bar).toHaveCSS('background-color', 'rgb(255, 255, 255)')
          await expect(bar).not.toHaveCSS('border-bottom-style', 'none')
          const barBox = (await bar.boundingBox())!
          const heroBox = (await page.locator('.hero').boundingBox())!
          expect(heroBox.y).toBeGreaterThanOrEqual(barBox.y + barBox.height - 1)
        }
        // 폰 · 태블릿은 로고 띠가 글자 위에 있다 — 글자가 로고에 겹치지 않는다
        if (path === '/' && width < 1024) {
          const band = (await page.locator('.hero__band').boundingBox())!
          const text = (await page.locator('.hero__text').boundingBox())!
          expect(text.y, '글자가 띠 아래').toBeGreaterThanOrEqual(band.y + band.height - 1)
        }
        await page.screenshot({
          path: `e2e/.shots/river${path === '/' ? '-landing' : '-login'}-${width}.png`,
        })
      }
    })
  })
}
