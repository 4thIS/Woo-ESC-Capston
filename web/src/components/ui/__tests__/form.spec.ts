import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import Input from '@/components/ui/Input.vue'
import Textarea from '@/components/ui/Textarea.vue'
import Select from '@/components/ui/Select.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import { clipBytes, utf8Bytes } from '@/lib/bytes'

describe('bytes', () => {
  it('UTF-8 바이트를 세고 코드 포인트 단위로 자른다', () => {
    expect(utf8Bytes('한글a')).toBe(7)
    expect(clipBytes('한글한글', 10)).toBe('한글한')
    expect(clipBytes('ab', 10)).toBe('ab')
    expect(clipBytes('😀a', 3)).toBe('') // 4바이트 이모지를 반으로 자르지 않는다
  })
})

describe('Input', () => {
  it('label 과 input 이 id 로 이어지고 required 면 * 가 붙는다', () => {
    const w = mount(Input, { props: { label: '이름', required: true } })
    const id = w.get('input').attributes('id')
    expect(w.get('label').attributes('for')).toBe(id)
    expect(w.get('label').text()).toBe('이름*')
  })

  it('error 는 hint 자리를 대체하고 aria-invalid', () => {
    const w = mount(Input, { props: { hint: '8자 이상', error: '비밀번호가 짧습니다' } })
    expect(w.text()).toContain('비밀번호가 짧습니다')
    expect(w.text()).not.toContain('8자 이상')
    expect(w.get('input').attributes('aria-invalid')).toBe('true')
  })

  it('v-model 과 속성 통과', async () => {
    const w = mount(Input, {
      props: { modelValue: '' },
      attrs: { type: 'password', autocomplete: 'new-password' },
    })
    expect(w.get('input').attributes('type')).toBe('password')
    await w.get('input').setValue('abc')
    expect(w.emitted('update:modelValue')![0]).toEqual(['abc'])
  })

  it('maxBytes — 남은 양을 보이고 넘으면 자른다', async () => {
    const w = mount(Input, { props: { modelValue: '한글', maxBytes: 10 } })
    expect(w.text()).toContain('6 / 10 B')
    await w.get('input').setValue('한글한글')
    expect(w.emitted('update:modelValue')!.at(-1)).toEqual(['한글한'])
    expect((w.get('input').element as HTMLInputElement).value).toBe('한글한')
  })
})

describe('Textarea', () => {
  it('textarea 로 그린다', async () => {
    const onUpdate = vi.fn()
    const w = mount(Textarea, {
      attrs: { label: '사유', modelValue: '', rows: 4, 'onUpdate:modelValue': onUpdate },
    })
    expect(w.find('textarea').attributes('rows')).toBe('4')
    await w.get('textarea').setValue('학번이 잘못되었습니다')
    expect(onUpdate).toHaveBeenCalledWith('학번이 잘못되었습니다')
  })
})

describe('Select', () => {
  const options = [
    { value: 1, label: '월' },
    { value: 2, label: '화' },
  ]
  it('네이티브 select, 원래 타입 값으로 emit', async () => {
    const w = mount(Select, { props: { options, modelValue: 1, label: '요일' } })
    expect(w.findAll('option')).toHaveLength(2)
    await w.get('select').setValue('2')
    expect(w.emitted('update:modelValue')![0]).toEqual([2])
  })
  it('placeholder 는 고를 수 없는 첫 항목', () => {
    const w = mount(Select, { props: { options, placeholder: '선택' } })
    const first = w.findAll('option')[0]
    expect(first.text()).toBe('선택')
    expect(first.attributes('disabled')).toBeDefined()
  })
})

describe('Checkbox', () => {
  it('boolean v-model', async () => {
    const w = mount(Checkbox, { props: { modelValue: false, label: '받음' } })
    await w.get('input').setValue(true)
    expect(w.emitted('update:modelValue')![0]).toEqual([true])
  })
  it('배열 v-model 은 value 를 넣고 뺀다', async () => {
    const w = mount(Checkbox, { props: { modelValue: [1], value: 2 } })
    await w.get('input').setValue(true)
    expect(w.emitted('update:modelValue')![0]).toEqual([[1, 2]])
    await w.setProps({ modelValue: [1, 2] })
    await w.get('input').setValue(false)
    expect(w.emitted('update:modelValue')![1]).toEqual([[1]])
  })
  it('indeterminate 는 DOM 속성으로', () => {
    const w = mount(Checkbox, { props: { modelValue: false, indeterminate: true } })
    expect((w.get('input').element as HTMLInputElement).indeterminate).toBe(true)
  })
})
