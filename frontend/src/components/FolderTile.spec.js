import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import FolderTile from './FolderTile.vue'

let observerInstances
let observedTargets

beforeEach(() => {
  observerInstances = []
  observedTargets = []
  globalThis.IntersectionObserver = vi.fn().mockImplementation((cb) => {
    const instance = {
      cb,
      observe: vi.fn((el) => observedTargets.push(el)),
      disconnect: vi.fn(),
    }
    observerInstances.push(instance)
    return instance
  })
})

const mkFolder = (previewCount) => ({
  id: 1,
  name: '风景',
  color: '#409EFF',
  local_count: 42,
  preview_images: Array.from({ length: previewCount }, (_, i) => ({
    id: 1000 + i,
    width: 100,
    height: 100,
  })),
})

const factory = (props = {}) => mount(FolderTile, {
  props: { folder: mkFolder(4), saveDataMode: false, ...props },
  global: {
    stubs: {
      'el-icon': { template: '<i><slot/></i>' },
      'el-tag': { template: '<span class="el-tag-stub"><slot/></span>' },
    },
  },
})

describe('FolderTile', () => {
  it('渲染文件夹名和数量', () => {
    const wrapper = factory()
    expect(wrapper.text()).toContain('风景')
    expect(wrapper.text()).toContain('42')
  })

  it('saveDataMode=true 时不渲染 <img>', () => {
    const wrapper = factory({ saveDataMode: true })
    expect(wrapper.findAll('img')).toHaveLength(0)
    // 应有占位元素
    expect(wrapper.findAll('.folder-preview-placeholder').length).toBeGreaterThan(0)
  })

  it('saveDataMode=false 时初始 srcEnabled 为空，所有 <img> 不显示', () => {
    const wrapper = factory({ saveDataMode: false })
    const imgs = wrapper.findAll('img')
    expect(imgs.length).toBe(4)
    imgs.forEach(img => {
      expect(img.attributes('src')).toBeUndefined()
    })
  })

  it('点击触发 click 事件', async () => {
    const wrapper = factory()
    await wrapper.find('.folder-tile').trigger('click')
    expect(wrapper.emitted('click')).toHaveLength(1)
    expect(wrapper.emitted('click')[0][0]).toMatchObject({ id: 1 })
  })

  it('gridCols 根据 preview_images 数量计算', () => {
    const w4 = factory({ folder: mkFolder(4) })
    expect(w4.vm.gridCols).toBe(2)  // 4 张 → 2 列
    const w6 = factory({ folder: mkFolder(6) })
    expect(w6.vm.gridCols).toBe(3)
    const w8 = factory({ folder: mkFolder(8) })
    expect(w8.vm.gridCols).toBe(4)
  })

  it('saveDataMode 由 true 切到 false 后，已可见 cell 重新入队并填充 src', async () => {
    const wrapper = factory({ saveDataMode: true })
    await flushPromises()

    // happy-dom 不挂 wrapper 到 document.body，组件 onMounted 的 document.querySelector 拿不到根，
    // 这里手动 observe 当前 tile 自身的 cells 来模拟首屏可见
    const cells = Array.from(wrapper.element.querySelectorAll('[data-image-id]'))
    expect(cells.length).toBe(4)
    const observer = observerInstances[0]
    cells.forEach(cell => observer.observe(cell))

    observer.cb(cells.map(el => ({ isIntersecting: true, target: el })))
    await flushPromises()

    // 确认 saveDataMode=true 时 srcEnabled 仍为空（0 <img>，4 placeholder）
    expect(wrapper.findAll('img')).toHaveLength(0)

    // 切到非省流：watcher 把 visibleIds 重新入队 + processQueue
    await wrapper.setProps({ saveDataMode: false })
    await flushPromises()
    await flushPromises()

    const imgs = wrapper.findAll('img')
    expect(imgs.length).toBe(4)
    imgs.forEach((img, i) => {
      expect(img.attributes('src')).toBe(`/api/v1/gallery/cache/preview/${1000 + i}`)
    })
  })
})
