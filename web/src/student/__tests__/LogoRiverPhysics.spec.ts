import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'
import { LOGOS, layoutLogos, riverCoverEdge } from '@/components/domain/logoRiver'
import LogoRiverPhysics from '@/student/views/landing/LogoRiverPhysics.vue'
import { useRiverMode, useRiverWide } from '@/student/views/landing/useRiverMode'

const PC = '(min-width: 1024px) and (hover: hover) and (pointer: fine)'
const REDUCE = '(prefers-reduced-motion: reduce)'
const HERO_W = 1280

function stubMatchMedia(state: Record<string, boolean>) {
  const lists = new Map<string, Set<() => void>>()
  vi.stubGlobal(
    'matchMedia',
    vi.fn((q: string) => {
      const ls = lists.get(q) ?? new Set()
      lists.set(q, ls)
      return {
        get matches() {
          return state[q] ?? false
        },
        addEventListener: (_: string, f: () => void) => ls.add(f),
        removeEventListener: (_: string, f: () => void) => ls.delete(f),
      }
    }),
  )
  return {
    set(q: string, v: boolean) {
      state[q] = v
      lists.get(q)?.forEach((f) => f())
    },
    count: (q: string) => lists.get(q)?.size ?? 0,
  }
}

describe('useRiverMode', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('두 조건이 맞을 때만 true, change 이벤트에 따라간다', async () => {
    const mm = stubMatchMedia({ [PC]: true, [REDUCE]: false })
    const scope = effectScope()
    const mode = scope.run(() => useRiverMode())!
    expect(mode.value).toBe(true)
    mm.set(REDUCE, true)
    await nextTick()
    expect(mode.value).toBe(false)
    mm.set(REDUCE, false)
    mm.set(PC, false)
    await nextTick()
    expect(mode.value).toBe(false)
    scope.stop()
    expect(mm.count(PC)).toBe(0)
    expect(mm.count(REDUCE)).toBe(0)
  })

  it('matchMedia 없으면 false', () => {
    vi.stubGlobal('matchMedia', undefined)
    const scope = effectScope()
    expect(scope.run(() => useRiverMode())!.value).toBe(false)
    expect(scope.run(() => useRiverWide())!.value).toBe(false)
    scope.stop()
  })
})

describe('LogoRiverPhysics', () => {
  let surface: HTMLDivElement
  let w: VueWrapper
  let frames: ((t: number) => void)[]
  let clock: number
  const capture = vi.fn()
  const releaseCapture = vi.fn()

  function tick(ms = 1000 / 60) {
    clock += ms
    const f = frames
    frames = []
    f.forEach((cb) => cb(clock))
  }
  function fire(
    type: string,
    x: number,
    y: number,
    extra: Partial<{ button: number; pointerType: string; target: Element }> = {},
  ) {
    const e = new MouseEvent(type, {
      bubbles: true,
      cancelable: true,
      clientX: x,
      clientY: y,
      button: extra.button ?? 0,
    })
    Object.defineProperty(e, 'pointerType', { value: extra.pointerType ?? 'mouse' })
    Object.defineProperty(e, 'pointerId', { value: 1 })
    Object.defineProperty(e, 'timeStamp', { value: clock })
    ;(extra.target ?? surface).dispatchEvent(e)
    return e
  }
  function logoAt(i: number) {
    const img = w.findAll('img')[i].element as HTMLImageElement
    const m = /translate3d\(([-\d.]+)px, ([-\d.]+)px/.exec(img.style.transform)!
    return {
      x: Number(m[1]) + parseFloat(img.style.width) / 2,
      y: Number(m[2]) + parseFloat(img.style.height) / 2,
    }
  }
  /** 덮이지 않은 화면 안 로고 번호 */
  function visibleLogo() {
    const edge = riverCoverEdge(HERO_W) + 140
    const i = w.findAll('img').findIndex((_, n) => {
      const p = logoAt(n)
      return p.x > edge + 60 && p.x < HERO_W - 60
    })
    expect(i).toBeGreaterThanOrEqual(0)
    return i
  }
  function coveredLogo() {
    const edge = riverCoverEdge(HERO_W) + 140
    const i = w.findAll('img').findIndex((_, n) => {
      const p = logoAt(n)
      return p.x > 60 && p.x < edge - 60
    })
    expect(i).toBeGreaterThanOrEqual(0)
    return i
  }

  beforeEach(() => {
    frames = []
    clock = 1000
    capture.mockClear()
    releaseCapture.mockClear()
    vi.stubGlobal('requestAnimationFrame', (cb: (t: number) => void) => {
      frames.push(cb)
      return frames.length
    })
    vi.stubGlobal('cancelAnimationFrame', () => {
      frames = []
    })
    surface = document.createElement('div')
    Object.defineProperty(surface, 'clientWidth', { value: HERO_W })
    surface.setPointerCapture = capture
    surface.releasePointerCapture = releaseCapture
    surface.hasPointerCapture = () => true
    document.body.appendChild(surface)
    w = mount(LogoRiverPhysics, { props: { surface }, attachTo: document.body })
  })
  afterEach(() => {
    w.unmount()
    surface.remove()
    vi.unstubAllGlobals()
  })

  it('img 수 = N(복제 없음), alt 빈 값, 로고 판 aria-hidden, 버튼은 그 밖', () => {
    const imgs = w.findAll('img')
    expect(imgs).toHaveLength(layoutLogos(LOGOS, { W: 2000, H: 648, k: 1 }).length)
    for (const img of imgs) expect(img.attributes('alt')).toBe('')
    expect(w.classes()).toEqual(expect.arrayContaining(['river', 'river--physics']))
    expect(w.get('.river__field').attributes('aria-hidden')).toBe('true')
    expect(w.get('.river__field').findAll('button')).toHaveLength(0)
    expect(w.get('button').text()).toBe('멈춤')
    // 로고 판을 숨겼으니 무엇을 멈추는지는 버튼이 말한다
    expect(w.get('button').attributes('aria-label')).toBe('로고 흐름 멈춤')
  })

  it('프레임마다 로고가 왼쪽으로 흐른다', () => {
    const i = visibleLogo() // 화면 안 로고 — 왼쪽 밖에 있으면 세계를 이어 오른쪽으로 넘어간다
    const before = logoAt(i).x
    for (let n = 0; n < 60; n++) tick()
    expect(logoAt(i).x).toBeLessThan(before)
  })

  it('덮인 곳의 로고는 잡히지 않는다', () => {
    const p = logoAt(coveredLogo())
    const e = fire('pointerdown', p.x, p.y)
    expect(capture).not.toHaveBeenCalled()
    expect(e.defaultPrevented).toBe(false)
  })

  it('링크에서 시작한 pointerdown 은 잡지 않고 preventDefault 도 안 한다', () => {
    const p = logoAt(visibleLogo())
    const a = document.createElement('a')
    surface.appendChild(a)
    const e = fire('pointerdown', p.x, p.y, { target: a })
    expect(capture).not.toHaveBeenCalled()
    expect(e.defaultPrevented).toBe(false)
  })

  it.each([
    ['touch', 0],
    ['mouse', 2],
  ])('마우스 왼쪽 버튼만 잡는다 — %s 버튼 %i 는 무시', (pointerType, button) => {
    const p = logoAt(visibleLogo())
    fire('pointerdown', p.x, p.y, { pointerType, button })
    expect(capture).not.toHaveBeenCalled()
  })

  it('로고 위 pointermove → 커서 grab, 잡으면 grabbing, 놓으면 해제', () => {
    const p = logoAt(visibleLogo())
    fire('pointermove', p.x, p.y)
    expect(surface.style.cursor).toBe('grab')
    fire('pointerdown', p.x, p.y)
    expect(surface.style.cursor).toBe('grabbing')
    fire('pointerup', p.x, p.y)
    expect(surface.style.cursor).toBe('grab')
    fire('pointermove', 5, 5)
    expect(surface.style.cursor).toBe('')
  })

  it('pointerdown → setPointerCapture + preventDefault, 잡으면 포인터를 따라온다', () => {
    const i = visibleLogo()
    const p = logoAt(i)
    const e = fire('pointerdown', p.x, p.y)
    expect(capture).toHaveBeenCalledWith(1)
    expect(e.defaultPrevented).toBe(true)
    // 왼쪽으로 — 오른쪽 끝에 가까우면 히어로 안으로 잘린다
    fire('pointermove', p.x - 100, p.y + 50)
    for (let n = 0; n < 40; n++) tick()
    const q = logoAt(i)
    expect(Math.abs(q.x - (p.x - 100))).toBeLessThan(3)
    // 누른 순간의 몽글몽글 오프셋(최대 BOB_PX)만큼은 어긋날 수 있다
    expect(Math.abs(q.y - (p.y + 50))).toBeLessThan(8)
  })

  it('pointerup — 포인터 속도로 던져 오른쪽으로 날아간다', () => {
    const i = visibleLogo()
    const p = logoAt(i)
    fire('pointerdown', p.x, p.y)
    for (let n = 1; n <= 5; n++) {
      tick(10)
      fire('pointermove', p.x + n * 5, p.y)
    }
    fire('pointerup', p.x + 25, p.y)
    const x0 = logoAt(i).x
    for (let n = 0; n < 20; n++) tick()
    // 던지지 않으면 왼쪽으로 흐른다. 옆 로고에 부딪혀 덜 날아갈 수 있어 방향만 본다
    expect(logoAt(i).x).toBeGreaterThan(x0 + 5)
  })

  it('멈춘 뒤 놓으면 던져지지 않는다', () => {
    const i = visibleLogo()
    const p = logoAt(i)
    fire('pointerdown', p.x, p.y)
    fire('pointermove', p.x + 50, p.y)
    for (let n = 0; n < 30; n++) tick()
    fire('pointerup', p.x + 50, p.y)
    const x0 = logoAt(i).x
    for (let n = 0; n < 20; n++) tick()
    expect(logoAt(i).x).toBeLessThanOrEqual(x0 + 5)
  })

  it.each(['pointercancel', 'lostpointercapture'])('%s — 속도 0으로 놓는다', (type) => {
    const i = visibleLogo()
    const p = logoAt(i)
    fire('pointerdown', p.x, p.y)
    tick(10)
    fire('pointermove', p.x + 30, p.y)
    fire(type, p.x + 30, p.y)
    expect(surface.style.cursor).not.toBe('grabbing')
    const x0 = logoAt(i).x
    for (let n = 0; n < 20; n++) tick()
    expect(logoAt(i).x).toBeLessThanOrEqual(x0 + 30)
    // 놓였으므로 포인터를 움직여도 따라오지 않는다
    fire('pointermove', p.x + 300, p.y)
    for (let n = 0; n < 20; n++) tick()
    expect(logoAt(i).x).toBeLessThan(p.x + 100)
  })

  it('window blur — 속도 0으로 놓는다', () => {
    const i = visibleLogo()
    const p = logoAt(i)
    fire('pointerdown', p.x, p.y)
    window.dispatchEvent(new Event('blur'))
    expect(surface.style.cursor).not.toBe('grabbing')
    fire('pointermove', p.x + 300, p.y)
    for (let n = 0; n < 20; n++) tick()
    expect(logoAt(i).x).toBeLessThan(p.x + 100)
  })

  it('unmount — 리스너 제거, rAF 취소, 커서 복구', () => {
    const remove = vi.spyOn(surface, 'removeEventListener')
    const p = logoAt(visibleLogo())
    fire('pointerdown', p.x, p.y)
    w.unmount()
    expect(frames).toHaveLength(0)
    expect(surface.style.cursor).toBe('')
    expect(remove.mock.calls.map((c) => c[0])).toEqual(
      expect.arrayContaining([
        'pointerdown',
        'pointermove',
        'pointerup',
        'pointercancel',
        'lostpointercapture',
      ]),
    )
    capture.mockClear()
    fire('pointerdown', p.x, p.y)
    expect(capture).not.toHaveBeenCalled()
    // afterEach 의 unmount 가 두 번 불리지 않게 다시 마운트
    w = mount(LogoRiverPhysics, { props: { surface: null } })
  })

  it('멈춤 — 문구 재생으로, 프레임 멈춤, 잡히지 않음. 재생하면 이어서', async () => {
    const i = visibleLogo()
    await w.get('button').trigger('click')
    expect(w.get('button').text()).toBe('재생')
    expect(frames).toHaveLength(0)
    const p = logoAt(i)
    fire('pointerdown', p.x, p.y)
    expect(capture).not.toHaveBeenCalled()
    fire('pointermove', p.x, p.y)
    expect(surface.style.cursor).toBe('')
    await w.get('button').trigger('click')
    expect(w.get('button').text()).toBe('멈춤')
    expect(frames).toHaveLength(1)
    for (let n = 0; n < 60; n++) tick()
    expect(logoAt(i).x).toBeLessThan(p.x)
  })

  it('히어로가 화면 밖이거나 탭이 숨겨지면 프레임을 돌리지 않는다', () => {
    let hidden = true
    const spy = vi.spyOn(document, 'hidden', 'get').mockImplementation(() => hidden)
    document.dispatchEvent(new Event('visibilitychange'))
    expect(frames).toHaveLength(0)
    hidden = false
    document.dispatchEvent(new Event('visibilitychange'))
    expect(frames).toHaveLength(1)
    spy.mockRestore()
  })

  it('IntersectionObserver — 보이지 않으면 멈추고 다시 보이면 돈다', () => {
    w.unmount()
    let notify: (e: { isIntersecting: boolean }[]) => void = () => {}
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        constructor(cb: typeof notify) {
          notify = cb
        }
        observe() {}
        disconnect() {}
      },
    )
    frames = []
    w = mount(LogoRiverPhysics, { props: { surface }, attachTo: document.body })
    notify([{ isIntersecting: false }])
    expect(frames).toHaveLength(0)
    notify([{ isIntersecting: true }])
    expect(frames).toHaveLength(1)
  })
})
