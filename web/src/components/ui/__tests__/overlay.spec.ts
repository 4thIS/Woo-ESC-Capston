import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import Modal from '@/components/ui/Modal.vue'
import Banner from '@/components/ui/Banner.vue'
import { dismissToast, showToast, toasts } from '@/components/ui/toast'

const stubs = { teleport: true }

describe('Modal', () => {
  it('닫혀 있으면 그리지 않는다', () => {
    const w = mount(Modal, { props: { open: false, title: '거절' }, global: { stubs } })
    expect(w.find('[role="dialog"]').exists()).toBe(false)
  })

  it('제목·본문·푸터, aria 연결', () => {
    const w = mount(Modal, {
      props: { open: true, title: '거절 사유' },
      slots: { default: '<p>본문</p>', footer: '<button>취소</button>' },
      global: { stubs },
    })
    const dlg = w.get('[role="dialog"]')
    expect(dlg.attributes('aria-modal')).toBe('true')
    expect(w.get(`#${dlg.attributes('aria-labelledby')}`).text()).toBe('거절 사유')
    expect(w.text()).toContain('본문')
  })

  it('Esc 로 닫힌다', async () => {
    const w = mount(Modal, { props: { open: true, title: 't' }, global: { stubs } })
    await w.get('[role="dialog"]').trigger('keydown', { key: 'Escape' })
    expect(w.emitted('close')).toHaveLength(1)
  })

  it('closeOnBackdrop 이 false 면 Esc 로도 닫지 않는다 (입력 중인 사유를 지키려고)', async () => {
    const w = mount(Modal, {
      props: { open: true, title: 't', closeOnBackdrop: false },
      global: { stubs },
    })
    await w.get('[role="dialog"]').trigger('keydown', { key: 'Escape' })
    expect(w.emitted('close')).toBeUndefined()
  })

  it('첫 포커스는 비활성 입력을 건너뛴다', async () => {
    const w = mount(Modal, {
      props: { open: false, title: 't' },
      slots: { default: '<input id="off" disabled /><input id="on" />' },
      global: { stubs },
      attachTo: document.body,
    })
    await w.setProps({ open: true })
    await new Promise((r) => setTimeout(r))
    expect(document.activeElement?.id).toBe('on')
    w.unmount()
  })

  it('배경 클릭 — closeOnBackdrop 이 false 면 닫지 않는다', async () => {
    const a = mount(Modal, { props: { open: true, title: 't' }, global: { stubs } })
    await a.get('.modal__backdrop').trigger('mousedown')
    expect(a.emitted('close')).toHaveLength(1)
    const b = mount(Modal, {
      props: { open: true, title: 't', closeOnBackdrop: false },
      global: { stubs },
    })
    await b.get('.modal__backdrop').trigger('mousedown')
    expect(b.emitted('close')).toBeUndefined()
  })

  it('열리면 첫 입력에 포커스, 닫히면 열었던 버튼으로', async () => {
    const opener = document.createElement('button')
    document.body.appendChild(opener)
    opener.focus()
    const w = mount(Modal, {
      props: { open: false, title: 't' },
      slots: { default: '<input id="first" />', footer: '<button>확인</button>' },
      global: { stubs },
      attachTo: document.body,
    })
    await w.setProps({ open: true })
    await new Promise((r) => setTimeout(r))
    expect(document.activeElement?.id).toBe('first')
    await w.setProps({ open: false })
    await new Promise((r) => setTimeout(r))
    expect(document.activeElement).toBe(opener)
    w.unmount()
    opener.remove()
  })

  it('Tab 은 패널 안에서 돈다', async () => {
    const w = mount(Modal, {
      props: { open: true, title: 't' },
      slots: { default: '<input id="a" />', footer: '<button id="z">확인</button>' },
      global: { stubs },
      attachTo: document.body,
    })
    await new Promise((r) => setTimeout(r))
    ;(document.getElementById('z') as HTMLElement).focus()
    await w.get('[role="dialog"]').trigger('keydown', { key: 'Tab' })
    expect(document.activeElement?.id).toBe('a')
    w.unmount()
  })
})

describe('toast', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    for (const t of [...toasts.value]) dismissToast(t.id)
  })
  afterEach(() => vi.useRealTimers())

  it('최대 3개 — 넘으면 오래된 것부터', () => {
    for (const m of ['1', '2', '3', '4']) showToast({ message: m })
    expect(toasts.value.map((t) => t.message)).toEqual(['2', '3', '4'])
  })

  it('neutral 은 5초 뒤 사라지고 danger 는 남는다', async () => {
    showToast({ message: '저장했습니다' })
    showToast({ tone: 'danger', message: '실패했습니다' })
    await vi.advanceTimersByTimeAsync(5000)
    expect(toasts.value.map((t) => t.message)).toEqual(['실패했습니다'])
  })
})

describe('Banner', () => {
  beforeEach(() => localStorage.clear())

  it('닫으면 사라지고 storageKey 를 남긴다', async () => {
    const w = mount(Banner, { props: { message: '1024px 이상', storageKey: 'narrow' } })
    await w.get('button').trigger('click')
    expect(w.find('.banner').exists()).toBe(false)
    expect(localStorage.getItem('banner:narrow')).toBe('1')
    expect(w.emitted('dismiss')).toHaveLength(1)
  })

  it('이미 닫은 배너는 다시 띄우지 않는다', () => {
    localStorage.setItem('banner:narrow', '1')
    const w = mount(Banner, { props: { message: 'x', storageKey: 'narrow' } })
    expect(w.find('.banner').exists()).toBe(false)
  })

  it('localStorage 가 막혀도 죽지 않는다', async () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    const w = mount(Banner, { props: { message: 'x', storageKey: 'k' } })
    expect(w.find('.banner').exists()).toBe(true)
    spy.mockRestore()
  })

  it('dismissible:false 면 닫기 버튼이 없다', () => {
    const w = mount(Banner, { props: { message: 'x', dismissible: false } })
    expect(w.find('button').exists()).toBe(false)
  })
})
