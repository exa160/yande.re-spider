import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { MagicStick, StarFilled } from '@element-plus/icons-vue'
import ShuffleIcon from './ShuffleIcon.vue'
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

  // 预览图 URL 回归：磁贴缩略图必须走同源自愈路由，不能直连 yande_data.preview_url
  // （那是 yande.re 远端 URL，跨域/防盗链 → 加载失败；且旧实现在该分支不追加 ts，
  //   fallback 写盘后 src 永不变化 → 永久失败占位）
  it('preview_url 为远端 URL 时仍走同源 /cache/preview/{id}', async () => {
    const folder = {
      id: 1, name: 'my-favorites', isVirtual: true, local_count: 1,
      preview_images: [{
        id: 1000,
        preview_url: 'https://yande.re/previews/1000/1000.jpg',
        width: 100, height: 100,
      }],
    }
    const wrapper = factory({ folder, saveDataMode: true })
    await wrapper.setProps({ saveDataMode: false })
    const cells = Array.from(wrapper.element.querySelectorAll('[data-image-id]'))
    observerInstances[0].cb(cells.map(el => ({ isIntersecting: true, target: el })))
    await flushPromises()

    const src = wrapper.find('img').attributes('src')
    expect(src).toBe('/api/v1/gallery/cache/preview/1000')
    expect(src).not.toContain('yande.re')
  })

  it('fallback 写盘后 src 追加 ?ts= cache-buster（重新请求同源路由）', async () => {
    const folder = {
      id: 1, name: 'my-favorites', isVirtual: true, local_count: 1,
      preview_images: [{ id: 1000, width: 100, height: 100 }],
    }
    const wrapper = factory({ folder, saveDataMode: true })
    await wrapper.setProps({ saveDataMode: false })
    const cells = Array.from(wrapper.element.querySelectorAll('[data-image-id]'))
    observerInstances[0].cb(cells.map(el => ({ isIntersecting: true, target: el })))
    await flushPromises()
    expect(wrapper.find('img').attributes('src')).toBe('/api/v1/gallery/cache/preview/1000')

    // 模拟 fallback chain 成功写盘：previewCacheBuster 写入时间戳
    wrapper.vm.previewCacheBuster.set(1000, 1700000000000)
    await flushPromises()

    expect(wrapper.find('img').attributes('src'))
      .toBe('/api/v1/gallery/cache/preview/1000?ts=1700000000000')
  })

  // 虚拟磁贴 preview_images 异步到达时的懒加载回归：
  // 刷新页面时 onMounted 时 preview_images 还是空数组 → 当时没有 cell 被 observe；
  // 之后 cells 渲染出来若没人补注册 observe，id 永远进不了 loadingQueue
  // → srcEnabled 缺 id → <img> 无 src（表现为空的 loading="lazy" 图片）
  it('回归：preview_images 异步到达后新 cells 会被 observe 并最终填充 src', async () => {
    const emptyFolder = { id: 1, name: 'my-favorites', isVirtual: true, local_count: 1, preview_images: [] }
    const wrapper = factory({ folder: emptyFolder, saveDataMode: false })

    // 挂载时没有任何 cell 被 observe
    expect(wrapper.element.querySelectorAll('[data-image-id]').length).toBe(0)
    expect(observedTargets.length).toBe(0)

    // 预览图异步到达
    await wrapper.setProps({
      folder: {
        ...emptyFolder,
        preview_images: [
          { id: 1000, width: 100, height: 100 },
          { id: 1001, width: 100, height: 100 },
        ],
      },
    })
    await flushPromises()

    // 新 cells 已注册到 observer
    expect(wrapper.element.querySelectorAll('[data-image-id]').length).toBe(2)
    expect(observedTargets.length).toBe(2)

    // 模拟 IntersectionObserver 回调（进入视口）→ 应填充 src
    const cells = Array.from(wrapper.element.querySelectorAll('[data-image-id]'))
    observerInstances[0].cb(cells.map(el => ({ isIntersecting: true, target: el })))
    await flushPromises()

    const srcs = wrapper.findAll('img').map(img => img.attributes('src'))
    expect(srcs).toContain('/api/v1/gallery/cache/preview/1000')
    expect(srcs).toContain('/api/v1/gallery/cache/preview/1001')
  })

  it('随机浏览虚拟磁贴用 ShuffleIcon 交叉箭头图标（不与安全模式的 MagicStick 冲突）', () => {
    const wrapper = factory({
      folder: { id: 'random', name: '随机浏览', isVirtual: true, local_count: 0, preview_images: [] },
    })
    const badge = wrapper.find('.virtual-badge')
    expect(badge.exists()).toBe(true)
    // 图标以组件身份断言（Element Plus 图标渲染为内联 SVG，无稳定 class）
    expect(badge.findComponent(ShuffleIcon).exists()).toBe(true)
    expect(badge.findComponent(MagicStick).exists()).toBe(false)
  })

  it('ShuffleIcon 继承 currentColor（不硬编码色值），随主题主色变化', () => {
    const wrapper = factory({
      folder: { id: 'random', name: '随机浏览', isVirtual: true, local_count: 0, preview_images: [] },
    })
    const svg = wrapper.find('.virtual-badge svg')
    expect(svg.attributes('viewBox')).toBe('0 0 16 16')
    expect(svg.attributes('fill')).toBe('currentColor')
    expect(svg.attributes('width')).toBe('1em')
    // IcoMoon 导出的 #444444 硬编码色值必须已改为 currentColor
    expect(wrapper.find('.virtual-badge').html()).not.toContain('#444444')
  })

  it('我的最爱虚拟磁贴用 StarFilled 图标', () => {
    const wrapper = factory({
      folder: { id: 'my-favorites', name: '我的最爱', isVirtual: true, local_count: 3, preview_images: [] },
    })
    const badge = wrapper.find('.virtual-badge')
    expect(badge.findComponent(StarFilled).exists()).toBe(true)
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

  describe('虚拟磁贴 (isVirtual)', () => {
    it('renders virtual tile for 我的最爱 when folder.isVirtual=true and id="my-favorites"（默认 compactMode=false → 渲染 grid 容器保留 4:3 占位）', () => {
      const wrapper = mount(FolderTile, {
        props: { folder: { id: 'my-favorites', name: '我的最爱', isVirtual: true, local_count: 5 } },
        global: {
          stubs: {
            'el-icon': { template: '<i><slot/></i>' },
            'el-tag': { template: '<span class="el-tag-stub"><slot/></span>' },
          },
        },
      })
      expect(wrapper.find('.virtual-tile').exists()).toBe(true)
      expect(wrapper.find('.virtual-tile').classes()).toContain('virtual-my-favorites')
      // 不带 compactMode prop → 默认 false（Gallery 收藏夹瀑布流场景）
      // 虚拟磁贴无预览图时仍渲染 grid 容器（保留 4:3 占位，与真实磁贴视觉节奏一致）
      expect(wrapper.find('.virtual-tile').classes()).not.toContain('compact-mode')
      expect(wrapper.find('.folder-preview-grid').exists()).toBe(true)
      expect(wrapper.findAll('.folder-preview-cell')).toHaveLength(0)
      expect(wrapper.text()).toContain('我的最爱')
      expect(wrapper.text()).toContain('5')
    })

    it('compactMode=true（FavoritePanel 弹窗场景） → 虚拟磁贴无预览图时不渲染 grid', () => {
      const wrapper = mount(FolderTile, {
        props: {
          folder: { id: 'my-favorites', name: '我的最爱', isVirtual: true, local_count: 0 },
          compactMode: true,
        },
        global: {
          stubs: {
            'el-icon': { template: '<i><slot/></i>' },
            'el-tag': { template: '<span class="el-tag-stub"><slot/></span>' },
          },
        },
      })
      // compact-mode class 存在
      expect(wrapper.find('.virtual-tile').classes()).toContain('compact-mode')
      // grid 容器不渲染（消除 FavoritePanel 弹窗内的空白占位）
      expect(wrapper.find('.folder-preview-grid').exists()).toBe(false)
    })

    it('renders virtual tile for 随机浏览 when id="random"', () => {
      const wrapper = mount(FolderTile, {
        props: { folder: { id: 'random', name: '随机浏览', isVirtual: true, local_count: 0 } },
        global: {
          stubs: {
            'el-icon': { template: '<i><slot/></i>' },
            'el-tag': { template: '<span class="el-tag-stub"><slot/></span>' },
          },
        },
      })
      expect(wrapper.find('.virtual-tile').exists()).toBe(true)
      expect(wrapper.find('.virtual-tile').classes()).toContain('virtual-random')
      expect(wrapper.text()).toContain('随机浏览')
      expect(wrapper.text()).toContain('0')
    })

    it('does not emit long-press event for virtual tiles (no edit menu)', async () => {
      const wrapper = mount(FolderTile, {
        props: { folder: { id: 'my-favorites', name: '我的最爱', isVirtual: true, local_count: 0 } },
        global: {
          stubs: {
            'el-icon': { template: '<i><slot/></i>' },
            'el-tag': { template: '<span class="el-tag-stub"><slot/></span>' },
          },
        },
      })
      await wrapper.find('.virtual-tile').trigger('long-press')
      expect(wrapper.emitted('long-press')).toBeUndefined()
    })

    it('renders normal tile for non-virtual folder (isVirtual=false)', () => {
      const wrapper = mount(FolderTile, {
        props: { folder: { id: 1, name: 'test', isVirtual: false, local_count: 1 } },
        global: {
          stubs: {
            'el-icon': { template: '<i><slot/></i>' },
            'el-tag': { template: '<span class="el-tag-stub"><slot/></span>' },
          },
        },
      })
      expect(wrapper.find('.virtual-tile').exists()).toBe(false)
      expect(wrapper.find('.folder-preview-grid').exists()).toBe(true)
    })

    // ---- Bug 2 hotfix: virtual tile skeleton aligned with real folder tile ----
    // given 虚拟磁贴 isVirtual=true
    // when 渲染 FolderTile
    // then 应复用真实磁贴的 folder-preview-grid + folder-info 骨架

    it('test_virtual_tile_renders_folder_preview_grid_when_has_preview_images', () => {
      const wrapper = mount(FolderTile, {
        props: {
          folder: {
            id: 'my-favorites',
            name: '我的最爱',
            isVirtual: true,
            local_count: 4,
            preview_images: [
              { id: 9001 }, { id: 9002 }, { id: 9003 }, { id: 9004 },
            ],
          },
        },
        global: {
          stubs: {
            'el-icon': { template: '<i><slot/></i>' },
            'el-tag': { template: '<span class="el-tag-stub"><slot/></span>' },
          },
        },
      })
      // 虚拟磁贴有预览图时仍渲染 grid（缩略图展示）
      expect(wrapper.find('.folder-preview-grid').exists()).toBe(true)
    })

    it('test_virtual_tile_has_folder_info_class', () => {
      const wrapper = mount(FolderTile, {
        props: { folder: { id: 'random', name: '随机浏览', isVirtual: true, local_count: 0 } },
        global: {
          stubs: {
            'el-icon': { template: '<i><slot/></i>' },
            'el-tag': { template: '<span class="el-tag-stub"><slot/></span>' },
          },
        },
      })
      expect(wrapper.find('.folder-info').exists()).toBe(true)
      expect(wrapper.find('.folder-name').text()).toBe('随机浏览')
      expect(wrapper.find('.el-tag-stub').exists()).toBe(true)
    })

    it('test_virtual_tile_renders_preview_images (when folder.preview_images provided)', () => {
      const folder = {
        id: 'my-favorites',
        name: '我的最爱',
        isVirtual: true,
        local_count: 5,
        preview_images: [
          { id: 9001, width: 100, height: 100 },
          { id: 9002, width: 100, height: 100 },
          { id: 9003, width: 100, height: 100 },
          { id: 9004, width: 100, height: 100 },
        ],
      }
      const wrapper = mount(FolderTile, {
        props: { folder, saveDataMode: false },
        global: {
          stubs: {
            'el-icon': { template: '<i><slot/></i>' },
            'el-tag': { template: '<span class="el-tag-stub"><slot/></span>' },
          },
        },
      })
      expect(wrapper.find('.folder-preview-grid').exists()).toBe(true)
      expect(wrapper.findAll('.folder-preview-cell')).toHaveLength(4)
      expect(wrapper.find('.virtual-tile').exists()).toBe(true)
      expect(wrapper.find('.virtual-badge').exists()).toBe(true)
    })

    it('test_virtual_tile_does_not_have_red_dashed_gradient (regression: removed old style)', () => {
      const wrapper = mount(FolderTile, {
        props: { folder: { id: 'my-favorites', name: '我的最爱', isVirtual: true, local_count: 0 } },
        global: {
          stubs: {
            'el-icon': { template: '<i><slot/></i>' },
            'el-tag': { template: '<span class="el-tag-stub"><slot/></span>' },
          },
        },
      })
      const rootEl = wrapper.element
      // given 旧 .virtual-tile 用了 #f56c6c dashed border + linear-gradient
      // when 虚拟磁贴渲染
      // then 不应残留上述样式
      const tileStyle = window.getComputedStyle(rootEl)
      expect(tileStyle.backgroundImage || '').not.toMatch(/#f56c6c|linear-gradient/)
      expect(tileStyle.borderStyle || '').not.toBe('dashed')
    })
  })
})