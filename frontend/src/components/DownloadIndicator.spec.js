import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import DownloadIndicator from './DownloadIndicator.vue'

// Element Plus 桩：el-badge 需要真正渲染出 value 才能断言角标数字
const ElBadgeStub = {
  name: 'ElBadge',
  props: ['value', 'hidden', 'max', 'type'],
  template: `<div class="el-badge-stub">
    <slot />
    <sup v-if="!hidden && value > 0" class="el-badge-content-stub">{{ value > max ? max + '+' : value }}</sup>
  </div>`,
}

const factory = (props = {}) =>
  mount(DownloadIndicator, {
    props: { count: 0, ...props },
    global: {
      stubs: {
        'el-badge': ElBadgeStub,
        'el-button': { template: '<button class="el-button"><slot/></button>' },
        'el-icon': { template: '<i><slot/></i>' },
        Download: { template: '<i class="download-icon"></i>' },
      },
    },
  })

describe('DownloadIndicator', () => {
  it('空闲（count=0）：不显示角标，用普通 Download 图标', () => {
    const wrapper = factory({ count: 0 })
    expect(wrapper.find('.el-badge-content-stub').exists()).toBe(false)
    expect(wrapper.find('.download-icon').exists()).toBe(true)
    // 下载中的动效 SVG 不应出现
    expect(wrapper.find('.dl-anim').exists()).toBe(false)
  })

  it('下载中（count>0）：显示角标数字 + 动效箭头，隐藏普通图标', () => {
    const wrapper = factory({ count: 3 })
    expect(wrapper.find('.el-badge-content-stub').text()).toBe('3')
    expect(wrapper.find('.dl-anim').exists()).toBe(true)
    expect(wrapper.find('.download-icon').exists()).toBe(false)
    // 箭头与托盘线是两层独立 SVG（各自 keyframes）
    expect(wrapper.find('.dl-anim-arrow').exists()).toBe(true)
    expect(wrapper.find('.dl-anim-base').exists()).toBe(true)
  })

  it('count 从 0 变为 2：角标出现、图标切换为动效', async () => {
    const wrapper = factory({ count: 0 })
    expect(wrapper.find('.el-badge-content-stub').exists()).toBe(false)
    await wrapper.setProps({ count: 2 })
    expect(wrapper.find('.el-badge-content-stub').text()).toBe('2')
    expect(wrapper.find('.dl-anim').exists()).toBe(true)
  })

  it('全部完成（count 回到 0）：角标与动效一并撤掉，不留残影', async () => {
    const wrapper = factory({ count: 4 })
    expect(wrapper.find('.el-badge-content-stub').exists()).toBe(true)
    await wrapper.setProps({ count: 0 })
    expect(wrapper.find('.el-badge-content-stub').exists()).toBe(false)
    expect(wrapper.find('.dl-anim').exists()).toBe(false)
    expect(wrapper.find('.download-icon').exists()).toBe(true)
  })

  it('超大数量按 max=99 收敛成 99+', () => {
    const wrapper = factory({ count: 128 })
    expect(wrapper.find('.el-badge-content-stub').text()).toBe('99+')
  })

  it('点击冒泡为 click 事件（由调用方决定打开下载管理）', async () => {
    const wrapper = factory({ count: 2 })
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('click')).toHaveLength(1)
  })
})
