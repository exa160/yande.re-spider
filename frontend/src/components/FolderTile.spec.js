import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import FolderTile from './FolderTile.vue'

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

const mkFolder = (id, previewCount) => ({
  id,
  name: `folder_${id}`,
  color: '#409EFF',
  local_count: 42,
  preview_images: Array.from({ length: previewCount }, (_, i) => ({
    id: id * 1000 + i,
    width: 100,
    height: 100,
  })),
})

const factory = (props = {}, opts = {}) => {
  const wrapper = mount(FolderTile, {
    props: { folder: mkFolder(1, 4), saveDataMode: false, ...props },
    global: {
      stubs: {
        'el-icon': { template: '<i><slot/></i>' },
        'el-tag': { template: '<span class="el-tag-stub"><slot/></span>' },
      },
    },
  })
  const width = opts.width ?? 500
  vi.spyOn(wrapper.element, 'offsetWidth', 'get').mockReturnValue(width)
  resizeObserverInstances.forEach(ro => ro.cb())
  return wrapper
}

describe('FolderTile', () => {
  it('渲染文件夹名和数量', () => {
    const wrapper = factory()
    expect(wrapper.text()).toContain('folder_1')
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
    const w4 = factory({ folder: mkFolder(1, 4) })
    expect(w4.vm.gridCols).toBe(2)  // 4 张 → 2 列
    const w6 = factory({ folder: mkFolder(1, 6) })
    expect(w6.vm.gridCols).toBe(3)
    const w8 = factory({ folder: mkFolder(1, 8) })
    expect(w8.vm.gridCols).toBe(4)
  })

  it('saveDataMode 由 true 切到 false 后，已可见 cell 重新入队并填充 src', async () => {
    const wrapper = factory({ saveDataMode: true })
    await flushPromises()

    // 修复 C1 后：onMounted 使用 tileRef 引用实例根，不再需要手动 observe 兼容层。
    // happy-dom 会把单个组件挂载到独立的 document 片段，tileRef.value 即 wrapper.element，
    // onMounted 会自动 observe 当前 tile 自身的 cells 来模拟首屏可见。
    const cells = Array.from(wrapper.element.querySelectorAll('[data-image-id]'))
    expect(cells.length).toBe(4)

    // 触发 IntersectionObserver 回调，把这些 cell 标记为可见
    const observer = observerInstances[0]
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

  it('safeMode=true 且 rating=Explicit 时 <img> 有 safe-blur class', () => {
    const folder = {
      id: 1, name: 'f', color: '#000', local_count: 1,
      preview_images: [{ id: 1000, width: 100, height: 100, rating: 'Explicit' }],
    }
    const wrapper = mount(FolderTile, {
      props: { folder, saveDataMode: false, safeMode: true },
    })
    const img = wrapper.find('img')
    expect(img.exists()).toBe(true)
    expect(img.classes()).toContain('safe-blur')
  })

  it('safeMode=true 且 rating=Safe 时 <img> 无 safe-blur class', () => {
    const folder = {
      id: 1, name: 'f', color: '#000', local_count: 1,
      preview_images: [{ id: 1000, width: 100, height: 100, rating: 'Safe' }],
    }
    const wrapper = mount(FolderTile, {
      props: { folder, saveDataMode: false, safeMode: true },
    })
    const img = wrapper.find('img')
    expect(img.classes()).not.toContain('safe-blur')
  })

  // C1 回归测试：多个 FolderTile 实例共存时，每个实例的 cells 都应被独立 observe。
  // 修复前：document.querySelector('.folder-tile') 只命中第一个实例，
  // 第二个 tile 的所有 preview 永远停留在 placeholder 状态。
  // 修复后：使用 instance-scoped template ref (tileRef)，每个 tile 的 cells 都被各自的 observer 注册。
  it('C1 回归：多个实例共存时，每个 tile 的 cells 都应被各自的 observer 注册', async () => {
    const wrapperA = factory({ folder: mkFolder(1, 4) })
    const wrapperB = factory({ folder: mkFolder(2, 6) })

    await flushPromises()

    // 应有 2 个 observer 实例（每个 FolderTile 各自一个）
    expect(observerInstances.length).toBe(2)

    // 每个 observer.observe 调用应来自自己 tile 的 cells（不会跨实例 observe）
    // 模拟所有 observed targets 进入视口
    observerInstances[0].cb(observedTargets.map(el => ({ isIntersecting: true, target: el })))
    observerInstances[1].cb(observedTargets.map(el => ({ isIntersecting: true, target: el })))
    await flushPromises()
    await flushPromises()

    // 两个 tile 的 <img> 都应拿到 src（不再卡在 placeholder）
    const imgsA = wrapperA.findAll('img')
    const imgsB = wrapperB.findAll('img')
    expect(imgsA.length).toBe(4)
    expect(imgsB.length).toBe(6)
    imgsA.forEach(img => {
      expect(img.attributes('src')).toMatch(/^\/api\/v1\/gallery\/cache\/preview\//)
    })
    imgsB.forEach(img => {
      expect(img.attributes('src')).toMatch(/^\/api\/v1\/gallery\/cache\/preview\//)
    })
  })

  // 像素自适应：后端 tile_size='adaptive' 永远返 8 张，前端按 tile 实际宽度裁剪 4 / 6 / 8 张
  describe('像素自适应', () => {
    const renderAtWidth = async (width) => {
      const folder = mkFolder(1, 8)
      const wrapper = factory({ folder }, { width })
      await flushPromises()
      return wrapper.findAll('img').length
    }

    it('tile 宽度=500px 时显示 8 张', async () => {
      expect(await renderAtWidth(500)).toBe(8)
    })

    it('tile 宽度=350px 时显示 6 张', async () => {
      expect(await renderAtWidth(350)).toBe(6)
    })

    it('tile 宽度=200px 时显示 4 张', async () => {
      expect(await renderAtWidth(200)).toBe(4)
    })
  })
})