import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import BackButton from './BackButton.vue'

const factory = (props = {}) => mount(BackButton, {
  props: { visible: true, ...props },
})

describe('BackButton', () => {
  it('visible=true 时渲染按钮', () => {
    const wrapper = factory()
    expect(wrapper.find('.floating-back-btn').exists()).toBe(true)
  })

  it('visible=false 时不渲染', () => {
    const wrapper = factory({ visible: false })
    expect(wrapper.find('.floating-back-btn').exists()).toBe(false)
  })

  it('点击触发 click 事件', async () => {
    const wrapper = factory()
    await wrapper.find('.floating-back-btn').trigger('click')
    expect(wrapper.emitted('click')).toHaveLength(1)
  })
})