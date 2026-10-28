import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import Button from '@/components/ui/Button.vue'
import Badge from '@/components/ui/Badge.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import EmptyState from '@/components/ui/EmptyState.vue'

describe('Button', () => {
  it('기본은 primary·md·type=button', () => {
    const w = mount(Button, { slots: { default: '저장' } })
    const b = w.get('button')
    expect(b.text()).toBe('저장')
    expect(b.classes()).toEqual(expect.arrayContaining(['btn--primary', 'btn--md']))
    expect(b.attributes('type')).toBe('button')
  })

  it('loading 은 라벨을 유지하고 잠근다', () => {
    const w = mount(Button, { props: { loading: true }, slots: { default: '저장' } })
    expect(w.get('button').text()).toBe('저장')
    expect(w.get('button').element.disabled).toBe(true)
    expect(w.find('.btn__spin').exists()).toBe(true)
  })

  it('loadingLabel — 진행도를 보이고, 숫자를 가장 긴 자릿수로 채운 문자열로 폭을 미리 잡는다', async () => {
    const w = mount(Button, {
      props: { loading: false, loadingLabel: '0/12 적용 중' },
      slots: { default: '선택한 12곳에 기간 추가' },
    })
    // 평소 — 기본 라벨이 보이고, 폭 잡이만 숨어 있다
    expect(w.find('.btn__progress').exists()).toBe(false)
    expect(w.findAll('.btn__ghost').map((g) => g.text())).toEqual(['00/00 적용 중'])
    // 진행 중 — 진행도가 보이고 기본 라벨은 숨은 채 폭을 지킨다 ("3/12" 와 "10/12" 폭이 같다)
    await w.setProps({ loading: true, loadingLabel: '3/12 적용 중' })
    expect(w.get('.btn__progress').text()).toBe('3/12 적용 중')
    expect(w.findAll('.btn__ghost').map((g) => g.text())).toEqual([
      '선택한 12곳에 기간 추가',
      '00/00 적용 중',
    ])
    expect(w.get('button').element.disabled).toBe(true)
  })

  it('disabled 면 click 이 나가지 않는다', async () => {
    const onClick = vi.fn()
    const w = mount(Button, { props: { disabled: true }, attrs: { onClick } })
    await w.get('button').trigger('click')
    expect(onClick).not.toHaveBeenCalled()
  })
})

describe('Badge', () => {
  it.each([
    ['busy', 'tint'],
    ['neutral', 'outline'],
    ['neutral', 'solid'],
    ['danger', 'outline'],
  ])('%s + %s', (tone, variant) => {
    const w = mount(Badge, { props: { tone, variant } as never, slots: { default: '대기중' } })
    expect(w.classes()).toEqual(expect.arrayContaining([`badge--${tone}`, `badge--${variant}`]))
    expect(w.text()).toBe('대기중')
  })
})

describe('Skeleton', () => {
  it('text 는 rows 줄, 마지막 줄은 60%', () => {
    const w = mount(Skeleton, { props: { rows: 3 } })
    const lines = w.findAll('.sk__line')
    expect(lines).toHaveLength(3)
    expect(lines[2].attributes('style')).toContain('width: 60%')
    expect(lines[0].attributes('style')).toContain('width: 100%')
  })

  it('한 줄이면 60% 로 줄이지 않는다', () => {
    const w = mount(Skeleton)
    expect(w.get('.sk__line').attributes('style')).toContain('width: 100%')
  })
})

describe('EmptyState', () => {
  it('버튼은 최대 2개, 누르면 onClick', async () => {
    const a = vi.fn()
    const w = mount(EmptyState, {
      props: {
        message: '이 건물에 등록된 시간표가 없습니다',
        actions: [
          { label: 'CSV 가져오기', variant: 'secondary', onClick: a },
          { label: '슬롯 추가', onClick: vi.fn() },
          { label: '세 번째', onClick: vi.fn() },
        ],
      },
    })
    expect(w.text()).toContain('이 건물에 등록된 시간표가 없습니다')
    const buttons = w.findAll('button')
    expect(buttons).toHaveLength(2)
    await buttons[0].trigger('click')
    expect(a).toHaveBeenCalledOnce()
  })
})
