import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import FolderGrid from './FolderGrid.vue'

let observerInstances
let observedTargets
let resizeObserverInstances

beforeEach(() => {
  observerInstances = []
  observedTargets = []
  resizeObserverInstances = []
  globalThis.IntersectionObserver = vi.fn().mockImplementation((cb) => {
    const instance = {
      cb,
      observe: vi.fn((el) => observedTargets.push(el)),
      disconnect: vi.fn(),
    }
    observerInstances.push(instance)
    return instance
  })
  globalThis.ResizeObserver = vi.fn().mockImplementation((cb) => {
    const instance = {
      cb,
      observe: vi.fn(),
      disconnect: vi.fn(),
    }
    resizeObserverInstances.push(instance)
    return instance
  })
})

const mkFolder = (id) => ({
  id,
  name: `folder_${id}`,
  local_count: 3,
  preview_images: [],
})

const factory = (props = {}, opts = {}) => {
  const wrapper = mount(FolderGrid, {
    props: { folders: [mkFolder(1), mkFolder(2)], ...props },
    global: {
      stubs: {
        'el-icon': { template: '<i><slot/></i>' },
        'el-button': { template: '<button><slot/></button>' },
        FolderTile: {
          name: 'FolderTile',
          props: ['folder'],
          emits: ['click', 'visible'],
          template:
            '<div class="folder-tile-stub" :data-folder-id="folder.id" @click="$emit(\'click\', folder)"></div>',
        },
      },
    },
  })
  const width = opts.width ?? 1600
  vi.spyOn(wrapper.element, 'offsetWidth', 'get').mockReturnValue(width)
  resizeObserverInstances.forEach((ro) => ro.cb())
  return wrapper
}

describe('FolderGrid - 收藏夹一级页磁贴网格', () => {
  it('渲染每个磁贴并带 data-folder-id（Gallery 返回一级页按 folder 定位）', () => {
    const wrapper = factory({ folders: [mkFolder(1), mkFolder(2), mkFolder(3)] })
    const items = wrapper.findAll('.folder-grid-item')
    expect(items).toHaveLength(3)
    expect(items.map((el) => el.attributes('data-folder-id'))).toEqual(['1', '2', '3'])
  })

  it('列数由容器宽度决定（JS 显式下发，不使用 CSS auto-fill）', async () => {
    const wrapper = factory({}, { width: 1880 })
    await flushPromises()
    // 1880 → folder 模式 4 列
    const style = wrapper.find('.folder-grid').attributes('style')
    expect(style).toContain('repeat(4')
  })

  it('窄屏（手机竖屏 350px）→ 1 列，且磁贴不会超出容器', async () => {
    const wrapper = factory({}, { width: 350 })
    await flushPromises()
    const style = wrapper.find('.folder-grid').attributes('style')
    expect(style).toContain('repeat(1')
    expect(style).not.toContain('420px')
  })

  it('手机横屏（804px）→ 3 列，与图片瀑布流一致', async () => {
    const wrapper = factory({}, { width: 804 })
    await flushPromises()
    expect(wrapper.find('.folder-grid').attributes('style')).toContain('repeat(3')
  })

  it('列数变化时上报 columns-change（Gallery 用它对齐分页条数）', async () => {
    const wrapper = factory({}, { width: 1880 })
    await flushPromises()
    const emitted = wrapper.emitted('columns-change')
    expect(emitted).toBeTruthy()
    expect(emitted[emitted.length - 1][0]).toBe(4)
  })

  it('宽度为 0（v-show 隐藏）时保留上一次的列数，不误判成 1 列', async () => {
    const wrapper = factory({}, { width: 1880 })
    await flushPromises()
    const before = wrapper.emitted('columns-change').length
    vi.spyOn(wrapper.element, 'offsetWidth', 'get').mockReturnValue(0)
    resizeObserverInstances.forEach((ro) => ro.cb())
    await flushPromises()
    expect(wrapper.emitted('columns-change')).toHaveLength(before)
  })

  it('hasMore 时挂载 sentinel 并能 emit load-more', async () => {
    const wrapper = factory({ hasMore: true })
    await flushPromises()
    // sentinel 存在
    expect(wrapper.find('.folder-grid-load-more').exists()).toBe(true)
    // 触发 IntersectionObserver → emit load-more
    const observer = observerInstances[observerInstances.length - 1]
    const target = observedTargets[observedTargets.length - 1]
    observer.cb([{ isIntersecting: true, target }])
    await flushPromises()
    expect(wrapper.emitted('load-more')).toBeTruthy()
  })

  it('loading 时渲染骨架屏，且列数与真实网格一致', async () => {
    const wrapper = factory({ loading: true }, { width: 1880 })
    await flushPromises()
    expect(wrapper.findAll('.folder-grid-skeleton').length).toBeGreaterThan(0)
    expect(wrapper.find('.folder-grid').attributes('style')).toContain('repeat(4')
  })

  it('点击磁贴 → emit folder-click', async () => {
    const wrapper = factory()
    await wrapper.find('.folder-tile-stub').trigger('click')
    expect(wrapper.emitted('folder-click')).toBeTruthy()
    expect(wrapper.emitted('folder-click')[0][0]).toMatchObject({ id: 1 })
  })
})
