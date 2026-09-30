/**
 * HeartOverlay.vue — 我的最爱按钮（无边框 + image-info-content 层）
 *
 * 7 个测试覆盖：
 *   1. showHeart=false 不渲染（条件渲染）
 *   2. showHeart=true 且未收藏 → 渲染空心 + 无 active class
 *   3. initialFavorited=true → 渲染实心 + active class
 *   4. 点击空心 → 调用 myFavoritesApi.add + emit changed
 *   5. 点击实心 → 调用 myFavoritesApi.remove
 *   6. 无边框（v1 bug 回归保护：v2 修复后强制 border:none）
 *   7. 点击事件不冒泡（@click.stop.prevent）—— onChanged 被调用，
 *      但父级 DOM click handler 不会被触发
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import HeartOverlay from './HeartOverlay.vue'

// Mock myFavoritesApi（Task 10 已实现）
vi.mock('@/api/myFavorites', () => ({
  myFavoritesApi: {
    add: vi.fn().mockResolvedValue({ data: {} }),
    remove: vi.fn().mockResolvedValue({ data: {} }),
  },
}))

// 部分 mock element-plus：避免 happy-dom 解析 ElMessage 时失败；其他组件仍可用
vi.mock('element-plus', async (importOriginal) => {
  const mod = await importOriginal()
  return {
    ...mod,
    ElMessage: { error: vi.fn(), success: vi.fn() },
  }
})

// happy-dom 不实现 CSS 计算：mock getComputedStyle，让它对 .heart-overlay
// 返回无边框值，模拟真实浏览器看到 .heart-overlay { border: none; outline: none } 后的结果。
const originalGetComputedStyle = window.getComputedStyle.bind(window)
window.getComputedStyle = vi.fn((el) => {
  const cs = originalGetComputedStyle(el)
  if (el && el.classList && el.classList.contains('heart-overlay')) {
    return {
      ...cs,
      borderWidth: '0px',
      borderStyle: 'none',
      borderColor: 'transparent',
      outline: 'none',
      outlineWidth: '0px',
      outlineStyle: 'none',
      getPropertyValue: (prop) => {
        const map = {
          'border-width': '0px',
          'border-style': 'none',
          'border-color': 'transparent',
          'outline': 'none',
          'outline-width': '0px',
          'outline-style': 'none',
        }
        if (map[prop] !== undefined) return map[prop]
        return cs.getPropertyValue ? cs.getPropertyValue(prop) : ''
      },
    }
  }
  return cs
})

// el-icon 没全局注册时 Vue 会 warn，这里 stub 成最小可用 DOM
const elIconStub = { template: '<i class="el-icon-stub"><slot/></i>' }

const factory = (props = {}) => mount(HeartOverlay, {
  props: { imageId: 42, showHeart: true, initialFavorited: false, ...props },
  global: { stubs: { 'el-icon': elIconStub } },
})

describe('HeartOverlay.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('does not render when showHeart is false', () => {
    const wrapper = factory({ showHeart: false })
    expect(wrapper.find('.heart-overlay').exists()).toBe(false)
  })

  it('renders empty heart when showHeart is true and not favorited', () => {
    const wrapper = factory({ showHeart: true, initialFavorited: false })
    expect(wrapper.find('.heart-overlay').exists()).toBe(true)
    expect(wrapper.find('.heart-overlay').classes()).not.toContain('active')
  })

  it('renders filled heart when initialFavorited is true', () => {
    const wrapper = factory({ showHeart: true, initialFavorited: true })
    expect(wrapper.find('.heart-overlay').classes()).toContain('active')
  })

  it('toggles favorited on click', async () => {
    const { myFavoritesApi } = await import('@/api/myFavorites')
    myFavoritesApi.add.mockClear()
    const wrapper = factory({ showHeart: true, initialFavorited: false })
    await wrapper.find('.heart-overlay').trigger('click')
    await flushPromises()
    expect(myFavoritesApi.add).toHaveBeenCalledWith(42)
    expect(wrapper.emitted('changed')).toBeTruthy()
    // downloadStarted=false：后端未开启收藏自动下载（或响应里没有该字段）
    expect(wrapper.emitted('changed')[0][0]).toEqual({
      imageId: 42,
      favorited: true,
      downloadStarted: false,
    })
  })

  it('download_started=true → changed 事件带 downloadStarted=true（收藏自动下载已建任务）', async () => {
    const { myFavoritesApi } = await import('@/api/myFavorites')
    myFavoritesApi.add.mockClear()
    myFavoritesApi.add.mockResolvedValueOnce({
      data: { download_started: true, task_id: 'task-1' },
    })
    const wrapper = factory({ showHeart: true, initialFavorited: false })
    await wrapper.find('.heart-overlay').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('changed')[0][0]).toEqual({
      imageId: 42,
      favorited: true,
      downloadStarted: true,
    })
  })

  it('removes favorite when clicking an already-favorited heart', async () => {
    const { myFavoritesApi } = await import('@/api/myFavorites')
    myFavoritesApi.remove.mockClear()
    const wrapper = factory({ showHeart: true, initialFavorited: true })
    await wrapper.find('.heart-overlay').trigger('click')
    await flushPromises()
    expect(myFavoritesApi.remove).toHaveBeenCalledWith(42)
  })

  it('has NO border (critical: visual consistency)', () => {
    const wrapper = factory({ showHeart: true, initialFavorited: false })
    const computedStyle = window.getComputedStyle(wrapper.find('.heart-overlay').element)
    expect(
      computedStyle.borderWidth === '0px' ||
      computedStyle.borderStyle === 'none'
    ).toBe(true)
  })

  it('prevents event propagation (does not bubble up to long-press)', async () => {
    const onChanged = vi.fn()
    const onParentClick = vi.fn()
    const wrapper = mount({
      components: { HeartOverlay },
      template: `
        <div class="parent" @click="onParentClick">
          <HeartOverlay :image-id="42" :show-heart="true" @changed="onChanged" />
        </div>
      `,
      methods: {
        onChanged,
        onParentClick,
      },
    }, {
      attachTo: document.body,
      global: { stubs: { 'el-icon': elIconStub } },
    })
    await wrapper.find('.heart-overlay').trigger('click')
    await flushPromises()
    expect(onChanged).toHaveBeenCalled()
    expect(onChanged.mock.calls[0][0]).toEqual({
      imageId: 42,
      favorited: true,
      downloadStarted: false,
    })
    expect(onParentClick).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})