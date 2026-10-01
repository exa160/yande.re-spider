/**
 * FavoritePanel.vue — 虚拟磁贴 prepend 测试（Task 16）
 *
 * 验证：
 * 1. enableMyFavorites=true 时 prepend「我的最爱」虚拟磁贴
 * 2. enableMyFavorites=false 时不 prepend
 * 3. enableRandomBrowse=true 时 prepend「随机浏览」虚拟磁贴
 * 4. enableRandomBrowse=false 时不 prepend
 * 5. 点击「我的最爱」虚拟磁贴 → router.push 包含 querySource=my-favorites
 * 6. 既有真实收藏夹 prop 仍可接收（folders / realFolders 兼容）
 * 7. 最近下载：第三个虚拟磁贴（顺序固定在末尾）+ 点击 emit 分支（设计文档 §2.2 / §4.4）
 *
 * 设计要点：
 * - useFavoritesConfig 是模块级 singleton（state 在 module scope 共享），
 *   不能用 vi.doMock 在测试间切换（vi.doMock 不会 re-run import-time side effects，
 *   且 module registry 不会 reset）。改用「直接 import 并 mutate ref.value」：
 *   state 已载入 → mutate ref.value → mount → 触发 computed 重算 → 断言。
 * - FolderTile 必须真实渲染（不能 stub），因为测试断言 `.virtual-tile.virtual-my-favorites`
 *   这个 class 是 FolderTile 在 isVirtual=true 分支渲染出来的。
 * - @/api 必须 mock 掉，否则 useFavoritesConfig 内部 GET /config/favorites 会真实发请求。
 * - vue-router 的 useRouter() 必须 mock 掉（注入 mock router 提供 push spy）。
 *   测试环境未安装 vue-router 插件，useRouter() 本身会抛 "No router provided"。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// router mock：使用 router 仅用于 useRoute 上下文（FavoritePanel 已不再用 useRouter）
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({}),
  createRouter: vi.fn(),
  createWebHistory: vi.fn(),
}))

vi.mock('@/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    put: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
  },
}))

const FavoritePanel = (await import('./FavoritePanel.vue')).default
const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')

// Element Plus stubs（与项目其他 spec 保持一致）
const elementStubs = {
  'el-icon': { template: '<i class="el-icon-stub"><slot/></i>' },
  'el-tag': { template: '<span class="el-tag-stub"><slot/></span>' },
  'el-button': { template: '<button class="el-button-stub" @click="$emit(\'click\')"><slot/></button>' },
  'el-input': { template: '<input class="el-input-stub" />' },
  'el-form': { template: '<form><slot/></form>' },
  'el-form-item': { template: '<div class="el-form-item-stub"><slot/></div>' },
  'el-radio-group': { template: '<div><slot/></div>' },
  'el-radio': { template: '<div><slot/></div>' },
  'el-checkbox-group': { template: '<div><slot/></div>' },
  'el-checkbox': { template: '<div><slot/></div>' },
  'el-switch': { template: '<div><slot/></div>' },
  'el-popconfirm': { template: '<div><slot/></slot></div>' },
  'el-time-picker': { template: '<div></div>' },
  'el-input-number': { template: '<div></div>' },
}

const factory = (props = {}) =>
  mount(FavoritePanel, {
    props: { realFolders: [], colorOptions: ['#409EFF'], ...props },
    global: {
      stubs: elementStubs,
    },
  })

beforeEach(() => {
  // 每个测试前重置 singleton 状态到已知值（避免跨测试 state 污染）
  const cfg = useFavoritesConfig()
  cfg.enableMyFavorites.value = false
  cfg.enableRandomBrowse.value = false
  cfg.enableRecentDownloads.value = false
  cfg.myFavoritesCount.value = 0
  cfg.recentDownloadsCount.value = 0
  // 注意：FavoritePanel 不再 router.push（URL 污染修复），故此处不验证 router.push 调用
})

describe('FavoritePanel.vue 虚拟磁贴 prepend', () => {
  it('enableMyFavorites=true 时 prepend「我的最爱」虚拟磁贴', async () => {
    const cfg = useFavoritesConfig()
    cfg.enableMyFavorites.value = true
    cfg.myFavoritesCount.value = 42

    const wrapper = factory()
    await flushPromises()

    expect(wrapper.text()).toContain('我的最爱')
    // virtual-tile 是 FolderTile 在 isVirtual=true 分支渲染的 class
    const myFavTile = wrapper.find('.virtual-tile.virtual-my-favorites')
    expect(myFavTile.exists()).toBe(true)
    // 角标显示总数
    expect(myFavTile.text()).toContain('42')
  })

  it('enableMyFavorites=false 时不 prepend「我的最爱」', async () => {
    const wrapper = factory()
    await flushPromises()

    expect(wrapper.find('.virtual-tile.virtual-my-favorites').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('我的最爱')
  })

  it('enableRandomBrowse=true 时 prepend「随机浏览」虚拟磁贴', async () => {
    const cfg = useFavoritesConfig()
    cfg.enableRandomBrowse.value = true

    const wrapper = factory()
    await flushPromises()

    expect(wrapper.text()).toContain('随机浏览')
    const randomTile = wrapper.find('.virtual-tile.virtual-random')
    expect(randomTile.exists()).toBe(true)
    // 角标固定 0（随机浏览没有"总数"概念）
    expect(randomTile.text()).toContain('0')
  })

  it('enableRandomBrowse=false 时不 prepend「随机浏览」', async () => {
    const wrapper = factory()
    await flushPromises()

    expect(wrapper.find('.virtual-tile.virtual-random').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('随机浏览')
  })

  it('点击「我的最爱」虚拟磁贴 → emit virtual-tile-click + emit virtual-tile-navigate（修复问题 3、5、9：URL 污染 + 重复点击失效）', async () => {
    const cfg = useFavoritesConfig()
    cfg.enableMyFavorites.value = true

    const wrapper = factory()
    await flushPromises()

    const myFavTile = wrapper.find('.virtual-tile.virtual-my-favorites')
    expect(myFavTile.exists()).toBe(true)
    await myFavTile.trigger('click')

    // emit 'virtual-tile-click' 让 AdvancedQuery 关闭弹窗
    expect(wrapper.emitted('virtual-tile-click')).toBeTruthy()
    expect(wrapper.emitted('virtual-tile-click').length).toBe(1)
    expect(wrapper.emitted('virtual-tile-click')[0][0].id).toBe('my-favorites')

    // emit 'virtual-tile-navigate' 让 Gallery handleSourceChange 强制刷新（绕过 vue-router 同 url 不发事件的限制）
    expect(wrapper.emitted('virtual-tile-navigate')).toBeTruthy()
    expect(wrapper.emitted('virtual-tile-navigate').length).toBe(1)
    expect(wrapper.emitted('virtual-tile-navigate')[0][0]).toBe('my-favorites')

    // 不再 router.push（修复问题 9：URL 污染 + 返回后我的收藏点击失效）
    //   之前的实现：router.push 同 url 写 querySource 到 URL → 用户切回 favorites 再点我的收藏 → vue-router 检测到同 url 不发事件 → 失效
    //   新实现：仅 emit，URL 保持干净（state 由 localStorage 持久化 + URL 仅作为分享链接初始入口）
  })

  it('点击「随机浏览」虚拟磁贴 → emit virtual-tile-click + emit virtual-tile-navigate', async () => {
    const cfg = useFavoritesConfig()
    cfg.enableRandomBrowse.value = true

    const wrapper = factory()
    await flushPromises()

    const randomTile = wrapper.find('.virtual-tile.virtual-random')
    expect(randomTile.exists()).toBe(true)
    await randomTile.trigger('click')

    // emit 'virtual-tile-click' 让 AdvancedQuery 关闭弹窗
    expect(wrapper.emitted('virtual-tile-click')).toBeTruthy()
    expect(wrapper.emitted('virtual-tile-click').length).toBe(1)
    expect(wrapper.emitted('virtual-tile-click')[0][0].id).toBe('random')

    // emit 'virtual-tile-navigate' 让 Gallery handleSourceChange 强制刷新
    expect(wrapper.emitted('virtual-tile-navigate')).toBeTruthy()
    expect(wrapper.emitted('virtual-tile-navigate').length).toBe(1)
    expect(wrapper.emitted('virtual-tile-navigate')[0][0]).toBe('random')
  })

  it('两个开关同时开启时 prepend 两个虚拟磁贴，按「我的最爱 → 随机浏览」顺序', async () => {
    const cfg = useFavoritesConfig()
    cfg.enableMyFavorites.value = true
    cfg.myFavoritesCount.value = 7
    cfg.enableRandomBrowse.value = true

    const wrapper = factory()
    await flushPromises()

    // 两个都存在
    expect(wrapper.find('.virtual-tile.virtual-my-favorites').exists()).toBe(true)
    expect(wrapper.find('.virtual-tile.virtual-random').exists()).toBe(true)

    // 顺序：我的最爱在前（prepend 顺序在 virtualTiles computed 里 hardcoded）
    const allVirtualTiles = wrapper.findAll('.virtual-tile')
    expect(allVirtualTiles.length).toBe(2)
    expect(allVirtualTiles[0].classes()).toContain('virtual-my-favorites')
    expect(allVirtualTiles[1].classes()).toContain('virtual-random')
  })

  it('真实收藏夹仍可通过 `folders` prop（旧 AdvancedQuery 调用方式）传入', async () => {
    const realFolders = [
      { id: 1, name: '真实收藏夹', color: '#409EFF', local_count: 5 },
    ]
    // 注意：传 folders（不是 realFolders），验证 fallback 兼容
    const wrapper = factory({ folders: realFolders, realFolders: undefined })
    await flushPromises()

    expect(wrapper.text()).toContain('真实收藏夹')
  })
})

// =============================================================================
// 最近下载磁贴（第三个虚拟磁贴）— 设计文档 §2.2 顺序 / §4.4 点击分支
// =============================================================================
describe('FavoritePanel.vue 最近下载虚拟磁贴', () => {
  it('enableRecentDownloads=true 时 prepend「最近下载」虚拟磁贴并显示角标', async () => {
    const cfg = useFavoritesConfig()
    cfg.enableRecentDownloads.value = true
    cfg.recentDownloadsCount.value = 66

    const wrapper = factory()
    await flushPromises()

    expect(wrapper.text()).toContain('最近下载')
    const tile = wrapper.find('.virtual-tile.virtual-recent-downloads')
    expect(tile.exists()).toBe(true)
    expect(tile.text()).toContain('66')
  })

  it('enableRecentDownloads=false 时不 prepend「最近下载」', async () => {
    const wrapper = factory()
    await flushPromises()

    expect(wrapper.find('.virtual-tile.virtual-recent-downloads').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('最近下载')
  })

  it('点击「最近下载」虚拟磁贴 → emit virtual-tile-click + emit virtual-tile-navigate', async () => {
    const cfg = useFavoritesConfig()
    cfg.enableRecentDownloads.value = true

    const wrapper = factory()
    await flushPromises()

    const tile = wrapper.find('.virtual-tile.virtual-recent-downloads')
    expect(tile.exists()).toBe(true)
    await tile.trigger('click')

    expect(wrapper.emitted('virtual-tile-click')).toBeTruthy()
    expect(wrapper.emitted('virtual-tile-click').length).toBe(1)
    expect(wrapper.emitted('virtual-tile-click')[0][0].id).toBe('recent-downloads')

    expect(wrapper.emitted('virtual-tile-navigate')).toBeTruthy()
    expect(wrapper.emitted('virtual-tile-navigate').length).toBe(1)
    expect(wrapper.emitted('virtual-tile-navigate')[0][0]).toBe('recent-downloads')
  })

  it('三个开关全开时按「我的最爱 → 随机浏览 → 最近下载」顺序渲染（最近下载在末尾）', async () => {
    const cfg = useFavoritesConfig()
    cfg.enableMyFavorites.value = true
    cfg.myFavoritesCount.value = 7
    cfg.enableRandomBrowse.value = true
    cfg.enableRecentDownloads.value = true
    cfg.recentDownloadsCount.value = 3

    const wrapper = factory()
    await flushPromises()

    const allVirtualTiles = wrapper.findAll('.virtual-tile')
    expect(allVirtualTiles.length).toBe(3)
    expect(allVirtualTiles[0].classes()).toContain('virtual-my-favorites')
    expect(allVirtualTiles[1].classes()).toContain('virtual-random')
    expect(allVirtualTiles[2].classes()).toContain('virtual-recent-downloads')
  })
})
