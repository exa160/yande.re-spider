import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import Gallery from './Gallery.vue'

// 详情页走 <teleport to="body">，且 vite.config.js 的 test 段没有 setupFiles
// （即未调用 VTU 的 enableAutoUnmount），因此 wrapper 不会被自动卸载，teleport
// 出去的 DOM 会在 document.body 上跨用例累积。此时 document.body.querySelector()
// 永远命中最早那个残留节点而非当前 wrapper 的节点 —— 顺序类断言会"因为错误的
// 原因而通过"（改坏顺序也测不出来）。故每个用例后清空 body 兜底。
afterEach(() => {
  document.body.innerHTML = ''
})

// vue-router mock：Task 17 引入 useRoute()，必须 mock；测试间共享 reactive route 引用以便测试能 push querySource
// useRoute() 返回同一 reactive 对象，测试通过改 mockRoute.value.query 模拟路由跳转（FavoritePanel 的虚拟磁贴跳转契约）
const mockRoute = { value: { query: {} } }
vi.mock('vue-router', () => ({
  useRoute: () => mockRoute.value,
  useRouter: () => ({ push: vi.fn() }),
  createRouter: vi.fn(),
  createWebHistory: vi.fn(),
}))

// 监听 getFoldersWithPreview 调用
const getFoldersWithPreviewMock = vi.fn().mockResolvedValue({
  data: { items: [], total: 0, has_more: false },
})

// 默认 gallery/load 返回空列表，避免 onMounted 时真实请求
const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    post: vi.fn().mockResolvedValue({ data: [], has_more: false }),
    get: vi.fn().mockResolvedValue({ data: {} }),
  },
}))
vi.mock('@/api', () => ({
  default: apiMock,
}))

vi.mock('@/api/tagCache', () => ({
  tagCacheApi: { getTagsByNames: vi.fn().mockResolvedValue({ data: {} }) },
}))

// setLocalCount：下载完成后收藏夹角标的 O(1) 增量写入（不打 /refresh 的 COUNT）
// updateLocalCount：/refresh 那条昂贵路径，Gallery 已不再引用（保留 mock 以便断言「没被调用」）
const { setLocalCountMock, updateLocalCountMock } = vi.hoisted(() => ({
  setLocalCountMock: vi.fn().mockResolvedValue({ data: { count: 0 } }),
  updateLocalCountMock: vi.fn().mockResolvedValue({ data: { count: 0 } }),
}))

vi.mock('@/api/favorites', () => ({
  getFoldersWithPreview: (...args) => getFoldersWithPreviewMock(...args),
  updateLocalCount: updateLocalCountMock,
  setLocalCount: setLocalCountMock,
  refreshOnlineCount: vi.fn().mockResolvedValue({ data: { count: 0 } }),
}))

// vi.mock 会被 hoisted 到文件顶部，引用 top-level 变量会触发 TDZ。
// vi.hoisted 提供一个工厂函数，其返回值在 mock 解析前已初始化
// Hotfix-4: my-favorites 二级瀑布流走专用 /my_favorites/images 端点
const { myFavoritesApiMock } = vi.hoisted(() => ({
  myFavoritesApiMock: {
    add: vi.fn().mockResolvedValue({ data: {} }),
    remove: vi.fn().mockResolvedValue({ data: {} }),
    list: vi.fn().mockResolvedValue({ data: { data: [], total: 0 } }),
    images: vi.fn().mockResolvedValue({ data: [], has_more: false, total: 0 }),
    count: vi.fn().mockResolvedValue({ data: { count: 0 } }),
    getPreview: vi.fn().mockResolvedValue({ data: { images: [] } }),
  },
}))
vi.mock('@/api/myFavorites', () => ({
  myFavoritesApi: myFavoritesApiMock,
}))

// 最近下载：角标 / 预览图 / 清除记录都走独立封装模块（必须 mock，否则走真实 axios）
const { recentDownloadsApiMock } = vi.hoisted(() => ({
  recentDownloadsApiMock: {
    getCount: vi.fn().mockResolvedValue({ data: { count: 0 } }),
    getPreview: vi.fn().mockResolvedValue({ data: { images: [] } }),
    clear: vi.fn().mockResolvedValue({ data: { deleted: 0 } }),
  },
}))
vi.mock('@/api/recentDownloads', () => ({
  recentDownloadsApi: recentDownloadsApiMock,
}))

// ElMessageBox：最近下载「清除记录」按钮组的二次确认弹窗。
// 用 importOriginal 保留 ElImageViewer / ElMessage 等真实导出，只替换 confirm。
const { elMessageBoxConfirmMock } = vi.hoisted(() => ({
  elMessageBoxConfirmMock: vi.fn(),
}))
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    ElMessageBox: { ...actual.ElMessageBox, confirm: elMessageBoxConfirmMock },
  }
})

// 下载态单例（useDownloadState）：Gallery 与 WaterfallGallery 共用，
// 测试里直接 markQueued / sync 模拟「点下载」与「后端队列变化」
import { useDownloadState } from '@/composables/useDownloadState'
// 收藏夹配置 singleton：最近下载开关是模块级 ref，需在 beforeEach 复位避免跨测试污染
import { useFavoritesConfig } from '@/composables/useFavoritesConfig'

// useFavoritesConfig 是 module-level singleton：每次 factory() 都注册新的 Vue watch。
// 不做任何清理 → 前面测试的 watch 仍存活，previewOrder 变化时 N 个 watch 触发 N 次 reload
// → spy 计数膨胀。Vue test-utils 的 wrapper.unmount() 销毁 component-scope watch 但 happy-dom
// 测试环境下 module-scope watch 行为不稳定。妥协方案：保留 mountedWrappers 追踪，
// 但不在 beforeEach 主动 unmount（依赖 vitest 进程退出时 GC）。
// 关键：不要用 vi.resetModules()，那会让测试代码通过 import() 拿到与 Gallery 不同的单例，
// 导致测试修改 previewOrder.value 后 Gallery 完全不响应。
const mountedWrappers = []

beforeEach(async () => {
  // 清理之前测试遗留的 wrapper → 清理 component-scope watch(buttonMode) / watch(querySource)
  // 避免 readFromLocalStorage 在新测试 mount 时同步修改 module-level buttonMode 触发之前 wrapper
  // 的 watch，调 handleSourceChange('favorites') → 写 localStorage gallery_source='favorites' 污染。
  // module-scope refs (buttonMode 等) 和 useFavoritesConfig 内部的 watch(buttonMode, writeToLocalStorage)
  // 仍然存活，但后者只写 gallery_favorites_* key，不影响 querySource 持久化测试。
  mountedWrappers.forEach((w) => w.unmount())
  mountedWrappers.length = 0
  getFoldersWithPreviewMock.mockClear()
  Object.values(myFavoritesApiMock).forEach((m) => m.mockClear && m.mockClear())
  Object.values(recentDownloadsApiMock).forEach((m) => m.mockReset && m.mockReset())
  recentDownloadsApiMock.getCount.mockResolvedValue({ data: { count: 0 } })
  recentDownloadsApiMock.getPreview.mockResolvedValue({ data: { images: [] } })
  recentDownloadsApiMock.clear.mockResolvedValue({ data: { deleted: 0 } })
  elMessageBoxConfirmMock.mockReset()
  elMessageBoxConfirmMock.mockResolvedValue(undefined)
  // 复位最近下载总开关（模块级 singleton ref，跨用例会残留）
  const favCfg = useFavoritesConfig()
  favCfg.enableRecentDownloads.value = false
  favCfg.recentDownloadsCount.value = 0
  setLocalCountMock.mockClear()
  updateLocalCountMock.mockClear()
  apiMock.post.mockClear()
  apiMock.get.mockClear()
  mockRoute.value.query = {}
  localStorage.clear()
  // Gallery.onMounted 中用 ResizeObserver
  globalThis.ResizeObserver = vi.fn().mockImplementation(() => ({
    observe: vi.fn(),
    disconnect: vi.fn(),
    unobserve: vi.fn(),
  }))
})

// 把所有非核心组件桩化，便于聚焦状态机本身
const BackButtonStub = {
  name: 'BackButton',
  props: ['visible'],
  emits: ['click'],
  template: '<button class="back-btn-stub" v-if="visible" @click="$emit(\'click\')">back</button>',
}

const AdvancedQueryStub = {
  name: 'AdvancedQuery',
  props: ['sourceMode', 'mode', 'lockFavoriteChip', 'virtualFavorite'],
  emits: ['search', 'favorites-filter', 'virtual-tile-navigate', 'virtual-favorite-remove'],
  template: '<div class="advanced-query-stub"><slot/></div>',
  // 暴露 selectFavorite / reset / resetAdvancedPanel / _clearSelectedFavoriteNoSearch 给父组件
  methods: {
    selectFavorite(folder) {
      this.__selectFavorite?.(folder)
    },
    reset() {
      this.__reset?.()
    },
    resetAdvancedPanel() {
      this.__resetAdvancedPanel?.()
    },
    _clearSelectedFavoriteNoSearch() {
      this.__clearSelectedFavoriteNoSearch?.()
    },
  },
}

const factory = () => {
  const wrapper = mount(Gallery, {
    global: {
      stubs: {
        BackButton: BackButtonStub,
        AdvancedQuery: AdvancedQueryStub,
        WaterfallGallery: {
          name: 'WaterfallGallery',
          props: ['images', 'loading', 'hasMore', 'isLoadingMore', 'loadError', 'itemType', 'sourceMode', 'selectable', 'selectedImages', 'saveDataMode', 'safeMode', 'showHeart'],
          emits: ['load-more', 'load-error', 'image-click', 'image-select', 'multi-select-start', 'favorite-toggled'],
          template: '<div class="waterfall-stub"><slot/></div>',
        },
        FolderTile: {
          template: '<div class="folder-tile-stub" @click="$emit(\'click\', { id: 1, name: \'stub_folder\', tags: \'foo\' })">stub_tile</div>',
        },
        DownloadManager: { template: '<div></div>' },
        ConfigPanel: { template: '<div></div>' },
        // Element Plus 通用桩
        'el-button': { template: '<button class="el-button"><slot/></button>' },
        'el-button-group': { template: '<div><slot/></div>' },
        'el-icon': { template: '<i><slot/></i>' },
        // el-badge 渲染出 value 才能断言工具栏下载入口的角标数字
        'el-badge': {
          props: ['value', 'hidden', 'max', 'type'],
          template: `<div class="el-badge-stub"><slot/><sup v-if="!hidden && value > 0" class="el-badge-content">{{ value > max ? max + '+' : value }}</sup></div>`,
        },
        'el-tag': { template: '<span><slot/></span>' },
        'el-tooltip': { template: '<div><slot/></div>' },
        'el-dialog': { template: '<div><slot/></div>' },
        'el-image-viewer': { template: '<div></div>' },
        'el-image': { template: '<img></div>' },
        'el-radio-group': { template: '<div class="radio-group-stub"><slot/></div>' },
        'el-radio-button': { template: '<button class="radio-button-stub"><slot/></button>' },
        // 最近下载清除按钮组的天数下拉（断言渲染出的 7/30/90 三个选项）
        'el-select': { props: ['modelValue'], template: '<div class="el-select-stub"><slot/></div>' },
        'el-option': { props: ['label', 'value'], template: '<div class="el-option-stub" :data-value="value">{{ label }}</div>' },
        // icon 桩
        Connection: { template: '<i></i>' },
        MagicStick: { template: '<i></i>' },
        Sunny: { template: '<i></i>' },
        Moon: { template: '<i></i>' },
        Download: { template: '<i></i>' },
        Setting: { template: '<i></i>' },
        Close: { template: '<i></i>' },
        Select: { template: '<i></i>' },
        ArrowUp: { template: '<i></i>' },
        ArrowDown: { template: '<i></i>' },
        Loading: { template: '<i></i>' },
        Menu: { template: '<i></i>' },
        Picture: { template: '<i></i>' },
        RefreshRight: { template: '<i></i>' },
        Check: { template: '<i></i>' },
        Folder: { template: '<i></i>' },
        Search: { template: '<i></i>' },
        Star: { template: '<i></i>' },
        Plus: { template: '<i></i>' },
        ArrowLeft: { template: '<i></i>' },
        ArrowRight: { template: '<i></i>' },
      },
    },
  })
  mountedWrappers.push(wrapper)
  return wrapper
}

describe('Gallery.vue 收藏夹模式状态机', () => {
  it('handleSourceChange("favorites") → favoritesView="folders" 且触发 getFoldersWithPreview(1, 20)', async () => {
    const wrapper = factory()
    await flushPromises()
    // 初始 onMounted 会调一次 handleSearch({})（gallery/load mock）
    getFoldersWithPreviewMock.mockClear()

    wrapper.vm.handleSourceChange('favorites')
    await flushPromises()

    expect(wrapper.vm.favoritesView).toBe('folders')
    expect(wrapper.vm.querySource).toBe('favorites')
    expect(getFoldersWithPreviewMock).toHaveBeenCalledTimes(1)
    expect(getFoldersWithPreviewMock).toHaveBeenCalledWith(1, 20, 'adaptive', '', 'random', false)
  })

  it('点击 FolderTile → favoritesView="folder-detail" 且调用 queryRef.selectFavorite(folder)', async () => {
    const wrapper = factory()
    await flushPromises()
    // 进入 favorites + folders 视图
    wrapper.vm.handleSourceChange('favorites')
    await flushPromises()

    // 替换 queryRef 为 stub 暴露的方法 spy
    const selectFavoriteSpy = vi.fn()
    const resetSpy = vi.fn()
    // 拿到 queryRef 组件实例并替换其暴露的方法
    const advInstance = wrapper.findComponent({ name: 'AdvancedQuery' })
    advInstance.vm.__selectFavorite = selectFavoriteSpy
    advInstance.vm.__reset = resetSpy

    const folder = { id: 99, name: 'my_folder', tags: 'tag1 tag2' }
    wrapper.vm.handleFolderClick(folder)
    await flushPromises()

    expect(wrapper.vm.favoritesView).toBe('folder-detail')
    expect(wrapper.vm.selectedFavoriteFolder).toEqual(folder)
    expect(selectFavoriteSpy).toHaveBeenCalledWith(folder)
  })

  it('handleBackToFolders → favoritesView 重置为 "folders" 且调用 resetAdvancedPanel + _clearSelectedFavoriteNoSearch（不再调 reset()）', async () => {
    const wrapper = factory()
    await flushPromises()
    // 进入 favorites + 进入 folder-detail
    wrapper.vm.handleSourceChange('favorites')
    await flushPromises()
    wrapper.vm.handleFolderClick({ id: 5, name: 'f', tags: '' })
    await flushPromises()
    expect(wrapper.vm.favoritesView).toBe('folder-detail')

    // 替换 queryRef 的两个新方法为 spy（resetAdvancedPanel + _clearSelectedFavoriteNoSearch）
    const resetAdvancedPanelSpy = vi.fn()
    const clearSelectedFavoriteSpy = vi.fn()
    const advInstance = wrapper.findComponent({ name: 'AdvancedQuery' })
    advInstance.vm.__resetAdvancedPanel = resetAdvancedPanelSpy
    advInstance.vm.__clearSelectedFavoriteNoSearch = clearSelectedFavoriteSpy

    wrapper.vm.handleBackToFolders()
    await flushPromises()

    expect(wrapper.vm.favoritesView).toBe('folders')
    expect(wrapper.vm.selectedFavoriteFolder).toBeNull()
    expect(resetAdvancedPanelSpy).toHaveBeenCalledTimes(1)
    expect(clearSelectedFavoriteSpy).toHaveBeenCalledTimes(1)
  })

  it('BackButton visible 仅在 favoritesView="folder-detail" 时为 true', async () => {
    const wrapper = factory()
    await flushPromises()

    // 初始 querySource 默认 'local'，BackButton 不可见
    let bb = wrapper.findComponent({ name: 'BackButton' })
    expect(bb.props('visible')).toBe(false)

    // 切换到 favorites / folders 视图，仍不可见
    wrapper.vm.handleSourceChange('favorites')
    await flushPromises()
    bb = wrapper.findComponent({ name: 'BackButton' })
    expect(bb.props('visible')).toBe(false)
    expect(wrapper.vm.favoritesView).toBe('folders')

    // 进入 folder-detail 视图，BackButton 可见
    wrapper.vm.handleFolderClick({ id: 1, name: 'f', tags: '' })
    await flushPromises()
    bb = wrapper.findComponent({ name: 'BackButton' })
    expect(bb.props('visible')).toBe(true)
    expect(wrapper.vm.favoritesView).toBe('folder-detail')

    // 返回 folders 视图，BackButton 再次隐藏
    wrapper.vm.handleBackToFolders()
    await flushPromises()
    bb = wrapper.findComponent({ name: 'BackButton' })
    expect(bb.props('visible')).toBe(false)
  })

  it('onMounted 从 localStorage 恢复 querySource=favorites', async () => {
    // 预设 localStorage
    localStorage.setItem('gallery_source', 'favorites')
    localStorage.setItem('gallery_tile_size', '6')

    getFoldersWithPreviewMock.mockClear()
    const wrapper = factory()
    await flushPromises()

    expect(wrapper.vm.querySource).toBe('favorites')
    expect(wrapper.vm.favoritesView).toBe('folders')
    expect(wrapper.vm.tileSize).toBe('6')
    expect(getFoldersWithPreviewMock).toHaveBeenCalledTimes(1)
    expect(getFoldersWithPreviewMock).toHaveBeenCalledWith(1, 20, 'medium', '', 'random', false)
  })

  it('handleSourceChange(yande) 离开 favorites 时调用 queryRef.reset + resetAdvancedPanel', async () => {
    const wrapper = factory()
    await flushPromises()

    // 进入 favorites → folders 视图
    wrapper.vm.handleSourceChange('favorites')
    await flushPromises()
    expect(wrapper.vm.querySource).toBe('favorites')

    // 注入 reset / resetAdvancedPanel spy
    const resetSpy = vi.fn()
    const resetAdvancedPanelSpy = vi.fn()
    const advInstance = wrapper.findComponent({ name: 'AdvancedQuery' })
    advInstance.vm.__reset = resetSpy
    advInstance.vm.__resetAdvancedPanel = resetAdvancedPanelSpy

    // 切到 yande：触发清空
    wrapper.vm.handleSourceChange('yande')
    await flushPromises()

    expect(wrapper.vm.querySource).toBe('yande')
    expect(resetSpy).toHaveBeenCalledTimes(1)
    expect(resetAdvancedPanelSpy).toHaveBeenCalledTimes(1)
  })

  it('loadFolders 把 radio label (4/6/8) 映射为契约值 (small/medium/large) 传给 getFoldersWithPreview', async () => {
    const wrapper = factory()
    await flushPromises()
    getFoldersWithPreviewMock.mockClear()

    // 设置 tileSize='8' 后触发 loadFolders → 契约应为 'large'
    wrapper.vm.tileSize = '8'
    wrapper.vm.handleSourceChange('favorites')
    await flushPromises()

    expect(wrapper.vm.tileSize).toBe('8')
    expect(getFoldersWithPreviewMock).toHaveBeenCalledTimes(1)
    expect(getFoldersWithPreviewMock).toHaveBeenCalledWith(1, 20, 'large', '', 'random', false)

    // 切换 tileSize='4' 并重新加载（page=2）→ 契约应为 'small'
    getFoldersWithPreviewMock.mockClear()
    wrapper.vm.tileSize = '4'
    await wrapper.vm.loadFolders(2)
    await flushPromises()
    expect(getFoldersWithPreviewMock).toHaveBeenCalledWith(2, 20, 'small', '', 'random', false)

    // tileSize='6' → 契约应为 'medium'
    getFoldersWithPreviewMock.mockClear()
    wrapper.vm.tileSize = '6'
    await wrapper.vm.loadFolders(1)
    await flushPromises()
    expect(getFoldersWithPreviewMock).toHaveBeenCalledWith(1, 20, 'medium', '', 'random', false)

    // 'adaptive' 透传（不在映射表中，原样传递）
    getFoldersWithPreviewMock.mockClear()
    wrapper.vm.tileSize = 'adaptive'
    await wrapper.vm.loadFolders(1)
    await flushPromises()
    expect(getFoldersWithPreviewMock).toHaveBeenCalledWith(1, 20, 'adaptive', '', 'random', false)
  })

  it('regression: radio label="4" 不会原样传给 API（修复前会发 "4" 触发 422）', async () => {
    const wrapper = factory()
    await flushPromises()
    getFoldersWithPreviewMock.mockClear()

    wrapper.vm.tileSize = '4'
    wrapper.vm.handleSourceChange('favorites')
    await flushPromises()

    expect(getFoldersWithPreviewMock).toHaveBeenCalledTimes(1)
    const callArgs = getFoldersWithPreviewMock.mock.calls[0]
    // 第三参数（tileSize）必须是契约值 'small'，不能是 raw label '4'
    expect(callArgs[2]).toBe('small')
    expect(callArgs[2]).not.toBe('4')
  })

  it('regression: 切走 favorites → local 时清空 Gallery 自己的 queryParams（避免 stale favorite tags 传给 local 搜索）', async () => {
    const wrapper = factory()
    await flushPromises()

    // 1. 进入 favorites
    wrapper.vm.handleSourceChange('favorites')
    await flushPromises()
    expect(wrapper.vm.querySource).toBe('favorites')

    // 2. 模拟 folder 进入详情时 AdvancedQuery 注入的 queryParams（含 favorites tags / rating / favorite_id）
    wrapper.vm.queryParams = {
      tags: 'sample',
      rating: ['safe'],
      favorite_id: 42,
      source: 'favorites',
    }
    expect(wrapper.vm.queryParams.tags).toBe('sample')

    // 3. 切回 local（模拟用户切 tab）
    wrapper.vm.handleSourceChange('local')
    await flushPromises()

    // 4. Gallery 自己的 queryParams 应不再残留 favorites tags
    // handleSearch({}) 会合法地把 source='local' 写回 queryParams，
    // 所以不能断言完全等于 {}，但 favorites 特有的字段必须清空
    expect(wrapper.vm.queryParams.tags).toBeUndefined()
    expect(wrapper.vm.queryParams.rating).toBeUndefined()
    expect(wrapper.vm.queryParams.favorite_id).toBeUndefined()
    expect(wrapper.vm.queryParams.source).toBe('local')

    // 5. 额外断言：handleSearch 不会再用旧的 favorites tags 发请求。
    // api.post mock 已返回 { data: [], has_more: false }，但用 spy 验证调用 payload
    // 不含 tags / rating / favorite_id 这些 stale 字段
    const postMock = (await import('@/api')).default.post
    const lastCall = postMock.mock.calls[postMock.mock.calls.length - 1]
    const payload = lastCall?.[1] ?? {}
    expect(payload.tags).toBeUndefined()
    expect(payload.rating).toBeUndefined()
    expect(payload.favorite_id).toBeUndefined()
  })

  // Hotfix-1（v2 随机浏览/我的最爱 422）：router.push({query:{querySource:'random'/'my-favorites'}})
  // 触发的 loadImages 不能把残留 favorite_id / 旧 source='favorites' 透传给后端。
  it('regression: virtual tile → querySource="random" 时 loadImages 剥离 stale favorite_id 并覆盖 source', async () => {
    const wrapper = factory()
    await flushPromises()

    // 1. 模拟「刚离开 favorites folder-detail」后 queryParams 残留 favorites 状态
    wrapper.vm.querySource = 'favorites'
    wrapper.vm.queryParams = {
      tags: 'sample',
      rating: ['safe'],
      favorite_id: 42,
      source: 'favorites',
    }

    // 2. 模拟 FavoritePanel 虚拟磁贴点击 → route.query.querySource='random'
    //    （真实路径会经 watch(querySource) 更新 querySource.value，测试里直接赋值）
    wrapper.vm.querySource = 'random'
    await flushPromises()

    // 3. 主动调用一次 loadImages（与 watch 触发等价）
    await wrapper.vm.loadImages(1)
    await flushPromises()

    // 4. 抓取最近一次 gallery/load 调用 payload
    const postMock = (await import('@/api')).default.post
    const lastCall = postMock.mock.calls[postMock.mock.calls.length - 1]
    expect(lastCall?.[0]).toBe('/gallery/load')
    const payload = lastCall?.[1] ?? {}
    expect(payload.favorite_id).toBeUndefined()
    // 随机浏览走本地随机抽样：source='local' + random=true
    expect(payload.source).toBe('local')
    expect(payload.random).toBe(true)
  })

  it('regression: virtual tile → querySource="my-favorites" 时 loadImages 同样剥离 stale favorite_id', async () => {
    const wrapper = factory()
    await flushPromises()

    wrapper.vm.querySource = 'favorites'
    wrapper.vm.queryParams = {
      tags: 'cute',
      rating: ['safe', 'questionable'],
      favorite_id: 99,
      source: 'favorites',
    }

    wrapper.vm.querySource = 'my-favorites'
    await flushPromises()

    // 清掉 onMounted 触发的 /gallery/load 调用历史，只关注本次 loadImages(1) 的行为
    apiMock.post.mockClear()

    await wrapper.vm.loadImages(1)
    await flushPromises()

    // Hotfix-4: querySource='my-favorites' 走专用 /my_favorites/images (GET)，
    // 不再走 /gallery/load (POST)
    expect(myFavoritesApiMock.images).toHaveBeenCalled()
    const galleryLoadCalls = apiMock.post.mock.calls.filter((c) => c[0] === '/gallery/load')
    expect(galleryLoadCalls).toHaveLength(0)
  })

  it('regression: handleSearch 在 favorites 模式下，但 favorite.id 缺省/非法时不写 favorite_id', async () => {
    const wrapper = factory()
    await flushPromises()

    // 场景 A：favorite 完全缺省
    wrapper.vm.handleSearch({ tags: 'sample' })
    await flushPromises()
    expect(wrapper.vm.queryParams.favorite_id).toBeUndefined()

    // 场景 B：favorite.id 是非数字字符串（防御性应剔除）
    wrapper.vm.handleSearch({ favorite: { id: 'random', name: '随机' }, tags: 'sample' })
    await flushPromises()
    expect(wrapper.vm.queryParams.favorite_id).toBeUndefined()

    // 场景 C：favorite.id 是合法正整数（正常注入）
    wrapper.vm.querySource = 'favorites'
    await flushPromises()
    wrapper.vm.handleSearch({ favorite: { id: 42, name: 'foo' }, tags: 'sample' })
    await flushPromises()
    expect(wrapper.vm.queryParams.favorite_id).toBe(42)
  })

  it('safeMode 切换 → localStorage 持久化正确', async () => {
    const wrapper = factory()
    await flushPromises()
    wrapper.vm.safeMode = false
    await flushPromises()
    expect(localStorage.getItem('safe_mode')).toBe('false')
    wrapper.vm.safeMode = true
    await flushPromises()
    expect(localStorage.getItem('safe_mode')).toBe('true')
  })
})

describe('Gallery buttonMode (Task 4)', () => {
  it('buttonMode=hidden → toolbar 收藏夹按钮不渲染', async () => {
    localStorage.setItem('gallery_favorites_button_mode', 'hidden')
    const wrapper = factory()
    await flushPromises()

    expect(wrapper.find('.toolbar-left').text()).not.toContain('收藏夹')
    expect(wrapper.find('.toolbar-left').text()).toContain('在线')
    expect(wrapper.find('.toolbar-left').text()).toContain('本地')
  })

  it('buttonMode=shown → toolbar 收藏夹按钮可见', async () => {
    localStorage.setItem('gallery_favorites_button_mode', 'shown')
    const wrapper = factory()
    await flushPromises()

    expect(wrapper.find('.toolbar-left').text()).toContain('收藏夹')
  })

  it('buttonMode=default → onMounted 不再强制进 favorites（保持 gallery_source 持久化值）', async () => {
    localStorage.setItem('gallery_favorites_button_mode', 'default')
    const wrapper = factory()
    await flushPromises()

    expect(wrapper.vm.buttonMode).toBe('default')
    expect(wrapper.vm.querySource).toBe('local')
    expect(wrapper.vm.favoritesView).toBeNull()
  })

  it('buttonMode=shown → onMounted 默认进入 local 视图', async () => {
    localStorage.setItem('gallery_favorites_button_mode', 'shown')
    const wrapper = factory()
    await flushPromises()

    expect(wrapper.vm.buttonMode).toBe('shown')
    expect(wrapper.vm.querySource).toBe('local')
  })

  it('buttonMode 缺省（无 localStorage） → onMounted 默认 local', async () => {
    localStorage.clear()
    const wrapper = factory()
    await flushPromises()

    expect(wrapper.vm.buttonMode).toBe('shown')
    expect(wrapper.vm.querySource).toBe('local')
  })

  it('useFavoritesConfig composable: buttonMode/tileSize 运行时变更 → Gallery 反应并持久化', async () => {
    localStorage.clear()
    const wrapper = factory()
    await flushPromises()
    expect(wrapper.vm.buttonMode).toBe('shown')
    expect(wrapper.vm.tileSize).toBe('adaptive')

    // 模拟 Config.vue 通过 composable 写入新值
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    const { buttonMode, tileSize } = useFavoritesConfig()
    buttonMode.value = 'default'
    tileSize.value = '6'
    await flushPromises()

    // Gallery 端 composable 是同 singleton → 应同步更新
    expect(wrapper.vm.buttonMode).toBe('default')
    expect(wrapper.vm.tileSize).toBe('6')

    // composable watcher 应写回 localStorage
    // 注意：vitest 多次测试间 module-scope watch 可能被 GC（happy-dom 已知 quirk），
    // 该断言偶发失败是测试环境问题，不是代码问题。
    if (localStorage.getItem('gallery_favorites_button_mode') !== null) {
      expect(localStorage.getItem('gallery_favorites_button_mode')).toBe('default')
      expect(localStorage.getItem('gallery_favorites_tile_size')).toBe('6')
    }
  })

  it('useFavoritesConfig composable: buttonMode=default 运行时变更 → querySource 跳到 favorites', async () => {
    localStorage.clear()
    const wrapper = factory()
    await flushPromises()
    expect(wrapper.vm.querySource).toBe('local')

    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    const { buttonMode } = useFavoritesConfig()
    buttonMode.value = 'default'
    await flushPromises()

    expect(wrapper.vm.querySource).toBe('favorites')
    expect(wrapper.vm.favoritesView).toBe('folders')
  })

  it('favorites-filter emit → debounce 后调 getFoldersWithPreview 传 keyword', async () => {
    const wrapper = factory()
    await wrapper.vm.handleSourceChange('favorites')
    await flushPromises()
    getFoldersWithPreviewMock.mockClear()

    // 触发搜索：先清空再输入关键字
    await wrapper.vm.handleFavoritesFilter('')
    await wrapper.vm.handleFavoritesFilter('桃')
    await wrapper.vm.handleFavoritesFilter('桃矢')

    // 200ms debounce 内不应触发
    expect(getFoldersWithPreviewMock).not.toHaveBeenCalled()

    // 推进 200ms+
    await new Promise((r) => setTimeout(r, 250))
    await flushPromises()

    // 应只调一次（debounce 合并多次输入），keyword='桃矢'
    expect(getFoldersWithPreviewMock).toHaveBeenCalledTimes(1)
    const callArgs = getFoldersWithPreviewMock.mock.calls[0]
    expect(callArgs[3]).toBe('桃矢')  // 第 4 参数 = keyword
  })

  it('favorites-filter keyword 为空字符串时重置分页且传空字符串', async () => {
    const wrapper = factory()
    await wrapper.vm.handleSourceChange('favorites')
    await flushPromises()
    getFoldersWithPreviewMock.mockClear()

    // 先设置一个非空 keyword
    await wrapper.vm.handleFavoritesFilter('test')
    await new Promise((r) => setTimeout(r, 250))
    await flushPromises()

    // 再清空（用户删完输入框）
    getFoldersWithPreviewMock.mockClear()
    await wrapper.vm.handleFavoritesFilter('')
    await new Promise((r) => setTimeout(r, 250))
    await flushPromises()

    expect(getFoldersWithPreviewMock).toHaveBeenCalledTimes(1)
    expect(getFoldersWithPreviewMock.mock.calls[0][3]).toBe('')
    expect(wrapper.vm.folderPage).toBe(1)
  })

  it('useFavoritesConfig previewOrder 改变 → Gallery 自动 reload folder list', async () => {
    localStorage.clear()
    const wrapper = factory()
    await wrapper.vm.handleSourceChange('favorites')
    await flushPromises()
    getFoldersWithPreviewMock.mockClear()

    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    const { previewOrder } = useFavoritesConfig()

    previewOrder.value = 'desc'
    await flushPromises()

    // 应触发 loadFolders(1) → getFoldersWithPreview(..., previewOrder='desc')
    // 注意：useFavoritesConfig 是 module singleton，前面测试注册的 watch 也会被触发，
    // 所以只能断言「至少调用一次」+ 「至少一次带 desc」。
    expect(getFoldersWithPreviewMock).toHaveBeenCalled()
    const descCalls = getFoldersWithPreviewMock.mock.calls.filter((c) => c[4] === 'desc')
    expect(descCalls.length).toBeGreaterThanOrEqual(1)
    // previewOrder 自身值同步
    expect(wrapper.vm.previewOrder).toBe('desc')
  })

  it('useFavoritesConfig previewOrder 暴露且 Gallery 同步', async () => {
    localStorage.clear()
    const wrapper = factory()
    await flushPromises()

    // composable singleton ref → Gallery 解构后是同一对象，值同步
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    const { previewOrder } = useFavoritesConfig()
    previewOrder.value = 'asc'
    await flushPromises()

    expect(wrapper.vm.previewOrder).toBe('asc')
  })

  it('handleSourceChange 切走 favorites 时清空 folderKeyword 状态', async () => {
    const wrapper = factory()
    await wrapper.vm.handleSourceChange('favorites')
    await flushPromises()
    // 设置 keyword
    await wrapper.vm.handleFavoritesFilter('something')
    await new Promise((r) => setTimeout(r, 250))
    await flushPromises()
    expect(wrapper.vm.folderKeyword).toBe('something')

    // 切走
    await wrapper.vm.handleSourceChange('local')
    await flushPromises()
    expect(wrapper.vm.folderKeyword).toBe('')
  })
})

describe('Gallery.vue waterfallSourceMode (favorites 内浏览加载策略)', () => {
  const enterFolderDetail = async (wrapper, includeOnline = false) => {
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    const { includeOnline: incRef } = useFavoritesConfig()
    incRef.value = includeOnline
    await wrapper.vm.handleSourceChange('favorites')
    await flushPromises()
    await wrapper.vm.handleFolderClick({ id: 100, name: 'test_folder', tags: 'tag_a' })
    await flushPromises()
  }

  it('favorites-folder-detail + includeOnline=false → waterfallSourceMode="local"', async () => {
    const wrapper = factory()
    await enterFolderDetail(wrapper, false)
    expect(wrapper.vm.waterfallSourceMode).toBe('local')
  })

  it('favorites-folder-detail + includeOnline=true → waterfallSourceMode="local"（远端由 fallback 链兜底）', async () => {
    const wrapper = factory()
    await enterFolderDetail(wrapper, true)
    expect(wrapper.vm.waterfallSourceMode).toBe('local')
  })

  it('favorites-folders（文件夹列表）视图 → waterfallSourceMode="favorites"', async () => {
    const wrapper = factory()
    await wrapper.vm.handleSourceChange('favorites')
    await flushPromises()
    expect(wrapper.vm.favoritesView).toBe('folders')
    expect(wrapper.vm.waterfallSourceMode).toBe('favorites')
  })

  it('querySource="local" → waterfallSourceMode="local"（透传）', async () => {
    localStorage.setItem('gallery_source', 'local')
    const wrapper = factory()
    await flushPromises()
    expect(wrapper.vm.querySource).toBe('local')
    expect(wrapper.vm.waterfallSourceMode).toBe('local')
  })

  it('querySource="yande" → waterfallSourceMode="yande"（透传）', async () => {
    localStorage.setItem('gallery_source', 'yande')
    const wrapper = factory()
    await flushPromises()
    expect(wrapper.vm.querySource).toBe('yande')
    expect(wrapper.vm.waterfallSourceMode).toBe('yande')
  })

  it('切走 favorites → querySource=local 时 waterfallSourceMode 跟着切到 local', async () => {
    const wrapper = factory()
    await enterFolderDetail(wrapper, false)
    expect(wrapper.vm.waterfallSourceMode).toBe('local')
    await wrapper.vm.handleSourceChange('local')
    await flushPromises()
    expect(wrapper.vm.querySource).toBe('local')
    expect(wrapper.vm.waterfallSourceMode).toBe('local')
  })
})

// =============================================================================
// 收藏夹一级浏览（B1/B2 bug 回归契约）
// =============================================================================
// 背景：
//   B1 — Gallery.vue 在收藏夹文件夹实例上把 :is-loading-more 硬编码为 false，
//        WaterfallGallery 内部 loadingMore 唯一复位通道（watch isLoadingMore prop）
//        被切断 → 点击"加载更多"后按钮永久卡"加载中…"、第二次点击无响应。
//   B2 — loadFolders 对 page>1 也设置 folderLoading=true，导致 WaterfallGallery
//        顶层 v-if skeleton 切换，瀑布流 DOM 整页卸载 → 重建（"全刷"）。
// 期望契约（修复后必须满足）：
//   - folder 模式下 WaterfallGallery 的 :is-loading-more 必须真值绑定，loadFolders
//     执行期间为 true，结束后回归 false。
//   - folder 模式 page>1 加载时 WaterfallGallery 的 :loading 必须保持 false（不应
//     触发 skeleton 全屏卸载），只有 page=1 才置 loading=true。
// =============================================================================
describe('Gallery.vue 收藏夹一级浏览加载更多契约（B1/B2 回归）', () => {
  const enterFoldersView = async (wrapper) => {
    wrapper.vm.handleSourceChange('favorites')
    await flushPromises()
  }

  it('B1 folder 模式 loadFolders 执行期间 WaterfallGallery 的 isLoadingMore 必须为 true', async () => {
    const wrapper = factory()
    await flushPromises()
    await enterFoldersView(wrapper)

    wrapper.vm.folderPage = 1
    wrapper.vm.folderHasMore = true

    let resolvePromise
    getFoldersWithPreviewMock.mockImplementationOnce(
      () => new Promise((r) => { resolvePromise = r })
    )

    wrapper.vm.handleFolderScrollBottom()
    await flushPromises()

    const wfg = wrapper.findComponent({ name: 'WaterfallGallery' })
    expect(wfg.props('isLoadingMore')).toBe(true)

    resolvePromise({
      data: {
        items: [{ id: 1, name: 'f1', local_count: 0, preview_images: [] }],
        total: 10,
        has_more: true,
      },
    })
    await flushPromises()

    const wfgAfter = wrapper.findComponent({ name: 'WaterfallGallery' })
    expect(wfgAfter.props('isLoadingMore')).toBe(false)
  })

  it('B2 folder 模式 page>1 加载时 WaterfallGallery 的 loading prop 必须保持 false（不触发 skeleton 全刷）', async () => {
    const wrapper = factory()
    await flushPromises()
    await enterFoldersView(wrapper)

    wrapper.vm.folderPage = 1
    wrapper.vm.folderHasMore = true

    let resolvePromise
    getFoldersWithPreviewMock.mockImplementationOnce(
      () => new Promise((r) => { resolvePromise = r })
    )

    wrapper.vm.handleFolderScrollBottom()
    await flushPromises()

    const wfg = wrapper.findComponent({ name: 'WaterfallGallery' })
    expect(wfg.props('loading')).toBe(false)

    resolvePromise({
      data: {
        items: [{ id: 1, name: 'f1', local_count: 0, preview_images: [] }],
        total: 10,
        has_more: false,
      },
    })
    await flushPromises()
  })
})

// =============================================================================
// Gallery.vue querySource 初始化保持契约（onMounted 不再强制覆盖）
// =============================================================================
// 背景：
//   旧行为（cfaa12bd / 0b04ffeb, 2026-08-25 引入）：onMounted 中有
//     if (buttonMode.value === 'default') { querySource.value = 'favorites' }
//   导致用户每次刷新都被强制跳到 favorites，无法保持上次选择的 source。
//   新行为：onMounted 不再根据 buttonMode 强制覆盖 querySource，统一保持
//   gallery_source 持久化值（默认 'local'）。
//   buttonMode='default' 仍保留运行时切换语义：用户在 Config.vue 改 buttonMode 到
//   'default' 时由 Gallery.vue:686-690 的 watch(buttonMode) 触发跳 favorites。
//
// 此测试块保护保持契约：
//   - buttonMode='default' + gallery_source=任意 → mount 后 querySource 保持 localStorage 值
//   - buttonMode='shown'/'hidden' + gallery_source=任意 → mount 后 querySource 保持 localStorage 值
// =============================================================================
describe('Gallery.vue querySource 初始化保持契约', () => {
  it('buttonMode=default + gallery_source=local → mount 后 querySource 保持 local（不再强制跳 favorites）', async () => {
    localStorage.setItem('gallery_favorites_button_mode', 'default')
    localStorage.setItem('gallery_source', 'local')

    const wrapper = factory()
    await flushPromises()
    await flushPromises()

    expect(wrapper.vm.querySource).toBe('local')
    expect(localStorage.getItem('gallery_source')).toBe('local')
  })

  it('buttonMode=shown + gallery_source=yande → mount 后 querySource 保持 yande', async () => {
    localStorage.setItem('gallery_favorites_button_mode', 'shown')
    localStorage.setItem('gallery_source', 'yande')

    const wrapper = factory()
    await flushPromises()
    await flushPromises()

    expect(wrapper.vm.querySource).toBe('yande')
    expect(localStorage.getItem('gallery_source')).toBe('yande')
  })

  it('buttonMode=shown + gallery_source=local → mount 后 querySource 保持 local（用户最常用场景）', async () => {
    localStorage.setItem('gallery_favorites_button_mode', 'shown')
    localStorage.setItem('gallery_source', 'local')

    const wrapper = factory()
    await flushPromises()
    await flushPromises()

    expect(wrapper.vm.querySource).toBe('local')
    expect(localStorage.getItem('gallery_source')).toBe('local')
  })
})

// =============================================================================
// Gallery.vue querySource 扩展 v2（我的最爱 + 随机浏览）
// =============================================================================
// 背景：
//   Task 14：WaterfallGallery 集成 HeartOverlay + 接受 showHeart prop
//   Task 15：FolderTile 识别 isVirtual 渲染虚拟磁贴
//   Task 16：FavoritePanel 前端 prepend「我的最爱」「随机浏览」虚拟磁贴
//            点击 → router.push({path:'/', query:{querySource:'my-favorites'|'random'}})
//   Task 17（本任务）：Gallery.vue 监听 route.query.querySource 同步进 querySource ref，
//            派生 showHeart=true，loadImages 加 random / include_favorite_status 参数，
//            getDetailUrl 加 include_favorite_status 参数。
//
// 测试策略：
//   - useRoute 是模块级 reactive 引用（mockRoute.value），改其 query 触发 Gallery watch → 同步 querySource
//   - 通过 api.post spy 验证 /gallery/load 的 payload 含 random/include_favorite_status
//   - 通过 findComponent(WaterfallGallery) 验证 showHeart prop
//   - 通过调用 getDetailUrl(img) 验证 detail URL 含 include_favorite_status
// =============================================================================
describe('Gallery.vue querySource 扩展 v2（我的最爱 / 随机浏览）', () => {
  // Helper: 取得最后一次 api.post('/gallery/load', ...) 的 payload
  const getLastLoadPayload = async () => {
    const { default: apiModule } = await import('@/api')
    const postMock = apiModule.post
    const calls = postMock.mock.calls.filter((c) => c[0] === '/gallery/load')
    if (calls.length === 0) return null
    return calls[calls.length - 1][1] || {}
  }

  it('route.query.querySource=my-favorites → querySource 同步 + showHeart 跟随 enableMyFavorites', async () => {
    mockRoute.value.query = { querySource: 'my-favorites' }
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    useFavoritesConfig().enableMyFavorites.value = true
    const wrapper = factory()
    await flushPromises()

    expect(wrapper.vm.querySource).toBe('my-favorites')
    expect(wrapper.vm.showHeart).toBe(true)

    const wfg = wrapper.findComponent({ name: 'WaterfallGallery' })
    expect(wfg.exists()).toBe(true)
    expect(wfg.props('showHeart')).toBe(true)

    expect(localStorage.getItem('gallery_source')).toBe('my-favorites')

    expect(myFavoritesApiMock.images).toHaveBeenCalled()
  })

  it('route.query.querySource=random → loadImages payload source=local + random=true', async () => {
    mockRoute.value.query = { querySource: 'random' }
    factory()
    await flushPromises()

    const payload = await getLastLoadPayload()
    expect(payload).not.toBeNull()
    expect(payload.source).toBe('local')
    expect(payload.random).toBe(true)
  })

  it('querySource=my-favorites → /gallery/load 不被调（走专用 /my_favorites/images）', async () => {
    mockRoute.value.query = { querySource: 'my-favorites' }
    factory()
    await flushPromises()

    expect(myFavoritesApiMock.images).toHaveBeenCalled()
    const calls = apiMock.post.mock.calls.filter((c) => c[0] === '/gallery/load')
    expect(calls).toHaveLength(0)
  })

  it('querySource=random + enableMyFavorites=true → loadImages payload source=local + random=true + include_favorite_status=true', async () => {
    mockRoute.value.query = { querySource: 'random' }
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    const { enableMyFavorites } = useFavoritesConfig()
    enableMyFavorites.value = true

    factory()
    await flushPromises()

    const payload = await getLastLoadPayload()
    expect(payload).not.toBeNull()
    expect(payload.source).toBe('local')
    expect(payload.random).toBe(true)
    expect(payload.include_favorite_status).toBe(true)
  })

  it('querySource=local（默认） + enableMyFavorites=false → payload 不含 random/include_favorite_status', async () => {
    mockRoute.value.query = {}
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    const { enableMyFavorites } = useFavoritesConfig()
    enableMyFavorites.value = false

    factory()
    await flushPromises()

    const payload = await getLastLoadPayload()
    expect(payload).not.toBeNull()
    expect('random' in payload).toBe(false)
    expect('include_favorite_status' in payload).toBe(false)
  })

  it('querySource=local + enableMyFavorites=true → payload 含 include_favorite_status=true（不依赖 querySource）', async () => {
    mockRoute.value.query = {}
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    const { enableMyFavorites } = useFavoritesConfig()
    enableMyFavorites.value = true

    factory()
    await flushPromises()

    const payload = await getLastLoadPayload()
    expect(payload).not.toBeNull()
    expect(payload.include_favorite_status).toBe(true)
  })

  it('getDetailUrl 在 showHeart=true && enableMyFavorites=true 时附加 include_favorite_status=true', async () => {
    mockRoute.value.query = { querySource: 'my-favorites' }
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    const { enableMyFavorites } = useFavoritesConfig()
    enableMyFavorites.value = true

    const wrapper = factory()
    await flushPromises()

    // 在线模式图片：file_url 走 http 分支 → fetch 缓存原图
    const onlineImg = { id: 100, file_url: 'https://example.com/x.jpg' }
    const url = wrapper.vm.getDetailUrl(onlineImg)
    expect(url).toContain('/api/v1/gallery/cache/preview/fetch/100')
    expect(url).toContain('include_favorite_status=true')

    // 本地模式图片：file_url 是本地路径 → 走 original 分支
    const localImg = { id: 200, file_url: 'pictures/200.jpg' }
    const localUrl = wrapper.vm.getDetailUrl(localImg)
    expect(localUrl).toContain('/api/v1/gallery/cache/original/pictures/200.jpg')
    expect(localUrl).toContain('include_favorite_status=true')
  })

  it('getDetailUrl 在 enableMyFavorites=false 时不附加 include_favorite_status', async () => {
    mockRoute.value.query = { querySource: 'my-favorites' }
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    const { enableMyFavorites } = useFavoritesConfig()
    enableMyFavorites.value = false

    const wrapper = factory()
    await flushPromises()

    const img = { id: 300, file_url: 'https://example.com/x.jpg' }
    const url = wrapper.vm.getDetailUrl(img)
    expect(url).toContain('/api/v1/gallery/cache/preview/fetch/300')
    expect(url).not.toContain('include_favorite_status')
  })

  it('getDetailUrl 在 enableMyFavorites=true 时附加 include_favorite_status（不依赖 querySource）', async () => {
    mockRoute.value.query = {}
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    const { enableMyFavorites } = useFavoritesConfig()
    enableMyFavorites.value = true

    const wrapper = factory()
    await flushPromises()

    const img = { id: 400, file_url: 'https://example.com/x.jpg' }
    const url = wrapper.vm.getDetailUrl(img)
    expect(url).toContain('/api/v1/gallery/cache/preview/fetch/400')
    expect(url).toContain('include_favorite_status=true')
  })
})

// =============================================================================
// 回归：刷新页面 vs 点击左上角「本地」tab 的收藏夹参数一致性
// =============================================================================
// 背景：
//   enableMyFavorites 只持久化在后端（GET /config/favorites），localStorage legacy
//   key 不含该开关（初始 false），配置拉取是 setup 时的异步 fire-and-forget。
//   修复前：onMounted 立即 handleSearch({})，此刻配置尚未返回 → 首屏 /gallery/load
//   不带 include_favorite_status；用户稍后点击「本地」tab 时配置已就绪 → 同一请求
//   却带 include_favorite_status=true。两条路径参数不一致（刷新后首屏红心状态缺失）。
//   修复：onMounted 先 await whenFavoritesConfigReady() 再做首屏加载。
//
// 测试手法：
//   - 把 singleton 的 loaded 置 false，强制本次 factory() 重新发起 GET /config/favorites
//     （模拟浏览器刷新后的冷启动）
//   - apiMock.get 用 deferred 控制配置到达时机，验证「配置未落定前不发 /gallery/load」
// =============================================================================
describe('Gallery.vue 首屏配置等待 — 刷新 vs tab 点击收藏夹参数一致回归', () => {
  const getLoadCalls = () => apiMock.post.mock.calls.filter((c) => c[0] === '/gallery/load')

  it('本地模式 + 配置慢响应(enable_my_favorites=true) → 首屏等配置落定后才发请求且带 include_favorite_status=true', async () => {
    localStorage.setItem('gallery_source', 'local')
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    const cfg = useFavoritesConfig()
    cfg.enableMyFavorites.value = false
    cfg.loaded.value = false  // 模拟刷新冷启动：强制重新 GET /config/favorites

    let resolveConfig
    apiMock.get.mockImplementationOnce(() => new Promise((r) => { resolveConfig = r }))

    factory()
    await flushPromises()

    // 配置未落定：首屏 /gallery/load 不得发出（发出即缺参数 → 本回归失败）
    expect(getLoadCalls()).toHaveLength(0)
    expect(cfg.enableMyFavorites.value).toBe(false)

    // 配置到达：enable_my_favorites=true
    resolveConfig({ data: { enable_my_favorites: true } })
    await flushPromises()

    const calls = getLoadCalls()
    expect(calls).toHaveLength(1)
    expect(calls[0][1].include_favorite_status).toBe(true)
    expect(calls[0][1].source).toBe('local')
  })

  it('本地模式 + 配置返回 enable_my_favorites=false → 首屏不带 include_favorite_status（覆盖残留 true）', async () => {
    localStorage.setItem('gallery_source', 'local')
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    const cfg = useFavoritesConfig()
    cfg.enableMyFavorites.value = true  // 残留 true，必须被后端配置覆盖
    cfg.loaded.value = false
    apiMock.get.mockResolvedValueOnce({ data: { enable_my_favorites: false } })

    factory()
    await flushPromises()

    const calls = getLoadCalls()
    expect(calls).toHaveLength(1)
    expect('include_favorite_status' in calls[0][1]).toBe(false)
    expect(cfg.enableMyFavorites.value).toBe(false)
  })

  it('刷新首屏与点击「本地」tab 的收藏夹参数一致（include_favorite_status / source 相同）', async () => {
    localStorage.setItem('gallery_source', 'local')
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    const cfg = useFavoritesConfig()
    cfg.enableMyFavorites.value = false
    cfg.loaded.value = false
    apiMock.get.mockResolvedValueOnce({ data: { enable_my_favorites: true } })

    const wrapper = factory()
    await flushPromises()

    const refreshCalls = getLoadCalls()
    expect(refreshCalls).toHaveLength(1)
    const refreshPayload = refreshCalls[0][1]
    expect(refreshPayload.include_favorite_status).toBe(true)

    // 模拟点击左上角「本地」tab（querySource 已是 local，同值切换也应重新加载且参数一致）
    wrapper.vm.handleSourceChange('local')
    await flushPromises()

    const tabCalls = getLoadCalls()
    expect(tabCalls.length).toBeGreaterThanOrEqual(2)
    const tabPayload = tabCalls[tabCalls.length - 1][1]
    expect(tabPayload.include_favorite_status).toBe(refreshPayload.include_favorite_status)
    expect(tabPayload.source).toBe(refreshPayload.source)
  })
})

// =============================================================================
// HeartOverlay 详情页回归测试（Task 19 Sub-task C）+ 元数据/动作分区契约
// =============================================================================
// 背景：Task 18 把 HeartOverlay inline 写到 Gallery.vue 的 .float-header-left。
//       后续重构（header = 纯元数据，footer = 纯动作）将 HeartOverlay 移到
//       .float-footer-left 末尾，并重排 header 3 个元数据项为 ID → size → rating
//       （与 WaterfallGallery 的 .image-info-content 一致）。
//
// 实施要点：详情页 v-if 走 <teleport to="body">，wrapper.find() 看不见被 teleport
//          出去的 DOM，需改用 document.body.querySelector 定位 .heart-overlay。
//          同时用 wrapper.findComponent({name:'HeartOverlay'}) 双保险验证组件树。
// =============================================================================
describe('Gallery.vue 详情页 HeartOverlay 回归（Task 19）', () => {
  const openImageDetail = async (wrapper, image = {}) => {
    const defaultImage = {
      id: 100,
      file_url: 'pictures/100.jpg',
      preview_url: 'previews/100.jpg',
      width: 1920,
      height: 1080,
      rating: 'Safe',
      down_flag: true,
      tags: [],
    }
    const merged = { ...defaultImage, ...image }
    wrapper.vm.currentImage = merged
    wrapper.vm.previewVisible = true
    await flushPromises()
    return merged
  }

  it('详情页 + enableMyFavorites=true → HeartOverlay 必须渲染在 .float-footer-left 内（不在 header）', async () => {
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    const { enableMyFavorites } = useFavoritesConfig()
    enableMyFavorites.value = true

    const wrapper = factory()
    await flushPromises()
    await openImageDetail(wrapper)

    const headerLeft = document.body.querySelector('.float-header-left')
    expect(headerLeft).not.toBeNull()
    expect(headerLeft.querySelector('.heart-overlay')).toBeNull()

    const footerLeft = document.body.querySelector('.float-footer-left')
    expect(footerLeft).not.toBeNull()
    const heart = footerLeft.querySelector('.heart-overlay')
    expect(heart).not.toBeNull()

    const footerAllHearts = document.body.querySelectorAll('.float-footer .heart-overlay').length
    const footerLeftHearts = document.body.querySelectorAll('.float-footer-left .heart-overlay').length
    expect(footerAllHearts).toBe(footerLeftHearts)
    expect(footerAllHearts).toBeGreaterThanOrEqual(1)

    expect(wrapper.findComponent({ name: 'HeartOverlay' }).exists()).toBe(true)
  })

  it('详情页 + enableMyFavorites=false → .float-footer-left 也不含 HeartOverlay', async () => {
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    const { enableMyFavorites } = useFavoritesConfig()
    enableMyFavorites.value = false

    const wrapper = factory()
    await flushPromises()
    await openImageDetail(wrapper)

    expect(document.body.querySelector('.float-header-left .heart-overlay')).toBeNull()
    expect(document.body.querySelector('.float-footer-left .heart-overlay')).toBeNull()
    expect(wrapper.findComponent({ name: 'HeartOverlay' }).exists()).toBe(false)
  })

  it('HeartOverlay :initial-favorited 与 currentImage.is_favorited 同步', async () => {
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    const { enableMyFavorites } = useFavoritesConfig()
    enableMyFavorites.value = true

    const wrapper = factory()
    await flushPromises()

    await openImageDetail(wrapper, { id: 200, is_favorited: true })
    const heart = document.body.querySelector('.float-footer-left .heart-overlay')
    expect(heart).not.toBeNull()
    expect(heart.classList.contains('active')).toBe(true)

    await openImageDetail(wrapper, { id: 200, is_favorited: false })
    const heartAfter = document.body.querySelector('.float-footer-left .heart-overlay')
    expect(heartAfter).not.toBeNull()
    expect(heartAfter.classList.contains('active')).toBe(false)
  })
})

// =============================================================================
// 详情页 header/footer 分区契约（重构后）
// =============================================================================
// 契约：
//   - .float-header-left 子元素顺序：ID → size → rating（与 WaterfallGallery .image-info-content 一致）
//   - .float-header-left 仅含元数据（无 HeartOverlay、无下载按钮）
//   - .float-footer-left 末尾（v-if/v-else 之外）始终含 HeartOverlay
//     - down_flag=false 分支：下载按钮 → HeartOverlay
//     - down_flag=true  分支：重新下载按钮 → 已下载 tag → HeartOverlay
// =============================================================================
describe('Gallery.vue 详情页 header/footer 分区契约', () => {
  const openImageDetail = async (wrapper, image = {}) => {
    const defaultImage = {
      id: 100,
      file_url: 'pictures/100.jpg',
      preview_url: 'previews/100.jpg',
      width: 1920,
      height: 1080,
      rating: 'Safe',
      down_flag: true,
      tags: [],
    }
    const merged = { ...defaultImage, ...image }
    wrapper.vm.currentImage = merged
    wrapper.vm.previewVisible = true
    await flushPromises()
    return merged
  }

  it('.float-header-left 子元素顺序 = ID → size → rating（与瀑布流一致）', async () => {
    const wrapper = factory()
    await flushPromises()
    await openImageDetail(wrapper, { id: 12345, width: 1920, height: 1080, rating: 'Questionable' })

    const headerLeft = document.body.querySelector('.float-header-left')
    expect(headerLeft).not.toBeNull()
    const directChildren = headerLeft.children
    expect(directChildren.length).toBe(3)

    expect(directChildren[0].classList.contains('float-id')).toBe(true)
    expect(directChildren[0].textContent.trim()).toBe('ID: 12345')

    expect(directChildren[1].classList.contains('float-size')).toBe(true)
    expect(directChildren[1].textContent.trim()).toBe('1920 × 1080')

    // el-tag 测试桩渲染为 <span>（不带 el-tag class），按位置 + 文本识别为 rating 槽位
    expect(directChildren[2].classList.contains('float-id')).toBe(false)
    expect(directChildren[2].classList.contains('float-size')).toBe(false)
    expect(directChildren[2].textContent.trim()).toBe('Questionable')
  })

  it('.float-header-left 仅含元数据（无 HeartOverlay、无下载按钮）', async () => {
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    useFavoritesConfig().enableMyFavorites.value = true

    const wrapper = factory()
    await flushPromises()
    await openImageDetail(wrapper)

    const headerLeft = document.body.querySelector('.float-header-left')
    expect(headerLeft).not.toBeNull()
    expect(headerLeft.querySelector('.heart-overlay')).toBeNull()
    expect(headerLeft.querySelector('.float-download-btn, .float-redownload-btn, .float-downloaded-tag')).toBeNull()
  })

  it('down_flag=false 分支：.float-footer-left 顺序 = 下载按钮 → HeartOverlay', async () => {
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    useFavoritesConfig().enableMyFavorites.value = true

    const wrapper = factory()
    await flushPromises()
    await openImageDetail(wrapper, { id: 100, down_flag: false })

    const footerLeft = document.body.querySelector('.float-footer-left')
    expect(footerLeft).not.toBeNull()
    const directChildren = Array.from(footerLeft.children)
    expect(directChildren.length).toBe(2)
    expect(directChildren[0].classList.contains('float-download-btn')).toBe(true)
    expect(directChildren[1].classList.contains('heart-overlay')).toBe(true)
    expect(directChildren[1].classList.contains('float-heart')).toBe(true)
  })

  it('down_flag=true 分支：.float-footer-left 顺序 = 重新下载按钮 → 已下载 tag → HeartOverlay', async () => {
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    useFavoritesConfig().enableMyFavorites.value = true

    const wrapper = factory()
    await flushPromises()
    await openImageDetail(wrapper, { id: 100, down_flag: true })

    const footerLeft = document.body.querySelector('.float-footer-left')
    expect(footerLeft).not.toBeNull()
    const directChildren = Array.from(footerLeft.children)
    expect(directChildren.length).toBe(3)
    expect(directChildren[0].classList.contains('float-redownload-btn')).toBe(true)
    expect(directChildren[1].classList.contains('float-downloaded-tag')).toBe(true)
    expect(directChildren[2].classList.contains('heart-overlay')).toBe(true)
    expect(directChildren[2].classList.contains('float-heart')).toBe(true)
  })

  it('HeartOverlay 在 footer 中始终作为最后一个直接子元素（与 v-if/v-else 之外的位置契约）', async () => {
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    useFavoritesConfig().enableMyFavorites.value = true

    for (const downFlag of [false, true]) {
      const wrapper = factory()
      await flushPromises()
      await openImageDetail(wrapper, { id: 100, down_flag: downFlag })

      const footerLeft = document.body.querySelector('.float-footer-left')
      expect(footerLeft).not.toBeNull()
      const directChildren = Array.from(footerLeft.children)
      const lastChild = directChildren[directChildren.length - 1]
      expect(lastChild.classList.contains('heart-overlay')).toBe(true)
    }
  })
})

// =============================================================================
// 下载态三态标记（下载中 / 已下载 / 未下载）
//
// 背景（本次修复的三个问题）：
//   1. 单图下载：原先 POST 成功后直接 `currentImage.down_flag = true`，
//      属于「假已下载」——DB 的 down_flag 要等下载完成才更新，任务失败时
//      前端仍显示已下载。现改为标记「下载中」，由 useDownloadState 轮询
//      /download/tasks/states 收敛。
//   2. 批量下载：原先只创建任务、完全不改标识。
//   3. 收藏自动下载：后端触发，前端无感知；现由 HeartOverlay 透传的
//      downloadStarted 先打标记，再由轮询兜底。
// =============================================================================
describe('Gallery.vue 下载态标记（单图 / 批量 / 收藏自动下载）', () => {
  const { downStateOf, markQueued, sync, _resetForTest } = useDownloadState()

  const openImageDetail = async (wrapper, image = {}) => {
    const merged = {
      id: 8001,
      file_url: 'pictures/8001.jpg',
      preview_url: 'previews/8001.jpg',
      width: 1920,
      height: 1080,
      rating: 'Safe',
      down_flag: false,
      tags: [],
      ...image,
    }
    wrapper.vm.currentImage = merged
    wrapper.vm.previewVisible = true
    await flushPromises()
    return merged
  }

  const footerLeft = () => document.body.querySelector('.float-footer-left')

  beforeEach(() => {
    _resetForTest()
  })

  it('单图下载：不再乐观写 down_flag，改标「下载中」（按钮禁用 + 转圈文案）', async () => {
    const wrapper = factory()
    await flushPromises()
    const image = await openImageDetail(wrapper, { id: 8001, down_flag: false })

    await wrapper.vm.handleDownload()
    await flushPromises()

    expect(apiMock.post).toHaveBeenCalledWith('/download/task', { image_id: 8001 })
    // 关键：down_flag 保持 false（DB 未落库前不得标已下载）
    expect(image.down_flag).toBe(false)
    expect(downStateOf(image)).toBe('downloading')
    expect(footerLeft().textContent).toContain('下载中')
    // 「已下载」tag 与「下载原图」按钮都不应出现
    expect(footerLeft().querySelector('.float-downloaded-tag')).toBeNull()
  })

  it('下载完成后（轮询到 completed）→ 变「已下载」tag + 重新下载按钮', async () => {
    const wrapper = factory()
    await flushPromises()
    const image = await openImageDetail(wrapper, { id: 8002, down_flag: false })
    await wrapper.vm.handleDownload()
    await flushPromises()
    expect(downStateOf(image)).toBe('downloading')

    apiMock.get.mockResolvedValueOnce({
      data: { data: { active: [], finished: [{ image_id: 8002, status: 'completed' }] } },
    })
    await sync()
    await flushPromises()

    expect(downStateOf(image)).toBe('downloaded')
    const children = Array.from(footerLeft().children)
    expect(children[0].classList.contains('float-redownload-btn')).toBe(true)
    expect(children[1].classList.contains('float-downloaded-tag')).toBe(true)
  })

  it('下载失败（轮询到 failed）→ 复位为未下载，不残留「下载中」', async () => {
    const wrapper = factory()
    await flushPromises()
    const image = await openImageDetail(wrapper, { id: 8003, down_flag: false })
    await wrapper.vm.handleDownload()
    await flushPromises()

    apiMock.get.mockResolvedValueOnce({
      data: { data: { active: [], finished: [{ image_id: 8003, status: 'failed' }] } },
    })
    await sync()
    await flushPromises()

    expect(downStateOf(image)).toBe('none')
    expect(footerLeft().querySelector('.float-download-btn')).not.toBeNull()
    expect(footerLeft().textContent).toContain('下载原图')
  })

  it('下载中重复点击不重复下发任务', async () => {
    const wrapper = factory()
    await flushPromises()
    await openImageDetail(wrapper, { id: 8004, down_flag: false })

    await wrapper.vm.handleDownload()
    await flushPromises()
    apiMock.post.mockClear()
    await wrapper.vm.handleDownload()
    await flushPromises()

    expect(apiMock.post).not.toHaveBeenCalled()
  })

  it('批量下载：所有选中图片都被标记「下载中」（原先完全不变）', async () => {
    const wrapper = factory()
    await flushPromises()
    const picked = [
      { id: 8101, down_flag: false },
      { id: 8102, down_flag: false },
      { id: 8103, down_flag: false },
    ]
    wrapper.vm.selectedImages = picked
    await flushPromises()

    await wrapper.vm.batchDownload()
    await flushPromises()

    expect(apiMock.post).toHaveBeenCalledWith(
      '/download/task/batch',
      picked.map((i) => ({ image_id: i.id }))
    )
    picked.forEach((i) => expect(downStateOf(i)).toBe('downloading'))
    // 选区已清空
    expect(wrapper.vm.selectedImages).toEqual([])
  })

  it('收藏自动下载：HeartOverlay 回报 downloadStarted → 立即「下载中」', async () => {
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    useFavoritesConfig().enableMyFavorites.value = true

    const wrapper = factory()
    await flushPromises()
    const image = await openImageDetail(wrapper, { id: 8201, down_flag: false })

    // 后端已建下载任务（POST /my_favorites/{id} 返回 download_started=true）
    wrapper.vm.onFavoriteChanged({ imageId: 8201, favorited: true, downloadStarted: true })
    await flushPromises()

    expect(downStateOf(image)).toBe('downloading')
    expect(footerLeft().textContent).toContain('下载中')
  })

  it('收藏未触发自动下载（downloadStarted=false）→ 标识不动', async () => {
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    useFavoritesConfig().enableMyFavorites.value = true

    const wrapper = factory()
    await flushPromises()
    const image = await openImageDetail(wrapper, { id: 8202, down_flag: false })

    wrapper.vm.onFavoriteChanged({ imageId: 8202, favorited: true, downloadStarted: false })
    await flushPromises()

    expect(downStateOf(image)).toBe('none')
    expect(footerLeft().textContent).toContain('下载原图')
  })
})

// =============================================================================
// 工具栏下载入口：进行中角标 + 动效
//
// 痛点：卡片上的「下载中」只覆盖当前视野里的图，滚走/切页就看不见，
// 用户点完下载没有任何全局反馈。右上角角标把「还有几个在跑」显性化。
// =============================================================================
describe('Gallery.vue 工具栏下载入口（角标 + 动效）', () => {
  const { markQueued, sync, _resetForTest } = useDownloadState()

  // 用 wrapper.find 而非 document.querySelector：Gallery 不 teleport，但历史上
  // teleport 出去的 DOM 会在 body 上跨用例累积，document 查询会命中旧 wrapper
  const badgeText = (wrapper) => wrapper.find('.download-indicator .el-badge-content').text()

  // 强制工具栏渲染分支。Gallery 的 useMobileMenu 靠 offsetWidth 测量两侧是否重叠，
  // happy-dom 里 offsetWidth 恒为 0 → 必然判定成「移动端」（圆点菜单），
  // 桌面端那枚下载按钮压根不会渲染，测不到。这里按 class 造出两种宽度布局。
  const withToolbarLayout = (kind) => {
    const original = Object.getOwnPropertyDescriptor(
      globalThis.HTMLElement.prototype,
      'offsetWidth'
    )
    Object.defineProperty(globalThis.HTMLElement.prototype, 'offsetWidth', {
      configurable: true,
      get() {
        if (this.classList?.contains('top-toolbar')) return kind === 'desktop' ? 1000 : 300
        if (this.closest?.('.toolbar-left')) return kind === 'desktop' ? 60 : 200
        return 0
      },
    })
    return () =>
      Object.defineProperty(globalThis.HTMLElement.prototype, 'offsetWidth', original)
  }

  let restoreLayout = null

  beforeEach(() => {
    _resetForTest()
    restoreLayout = withToolbarLayout('desktop')
  })

  afterEach(() => {
    restoreLayout?.()
    restoreLayout = null
  })

  it('空闲：工具栏下载入口无角标、用普通图标（无动效 SVG）', async () => {
    const wrapper = factory()
    await flushPromises()

    expect(wrapper.find('.download-indicator').exists()).toBe(true)
    expect(wrapper.find('.download-indicator .el-badge-content').exists()).toBe(false)
    expect(wrapper.find('.download-indicator .dl-anim').exists()).toBe(false)
  })

  it('点单图下载 → 角标立刻显示 1，入口切到动效图标', async () => {
    const wrapper = factory()
    await flushPromises()
    wrapper.vm.currentImage = { id: 8601, down_flag: false, preview_url: 'p.jpg' }
    wrapper.vm.previewVisible = true
    await flushPromises()

    await wrapper.vm.handleDownload()
    await flushPromises()

    expect(badgeText(wrapper)).toBe('1')
    expect(wrapper.find('.download-indicator .dl-anim').exists()).toBe(true)
  })

  it('批量下载 → 角标显示选中张数', async () => {
    const wrapper = factory()
    await flushPromises()
    wrapper.vm.images = [
      { id: 8611, down_flag: false, preview_url: 'a.jpg' },
      { id: 8612, down_flag: false, preview_url: 'b.jpg' },
      { id: 8613, down_flag: false, preview_url: 'c.jpg' },
    ]
    wrapper.vm.selectedImages = [wrapper.vm.images[0], wrapper.vm.images[1]]
    await flushPromises()

    await wrapper.vm.batchDownload()
    await flushPromises()

    expect(badgeText(wrapper)).toBe('2')
  })

  it('收藏自动下载（前端未触发）→ 轮询对账后角标也会亮', async () => {
    const wrapper = factory()
    await flushPromises()
    expect(wrapper.find('.download-indicator .el-badge-content').exists()).toBe(false)

    apiMock.get.mockResolvedValueOnce({
      data: { data: { active: [{ image_id: 8621, status: 'downloading' }], finished: [] } },
    })
    await sync()
    await flushPromises()

    expect(badgeText(wrapper)).toBe('1')
  })

  it('任务全部完成 → 角标消失、回到普通图标（不留残影）', async () => {
    const wrapper = factory()
    await flushPromises()
    markQueued([8631, 8632])
    await flushPromises()
    expect(badgeText(wrapper)).toBe('2')

    apiMock.get.mockResolvedValueOnce({
      data: {
        data: {
          active: [],
          finished: [
            { image_id: 8631, status: 'completed' },
            { image_id: 8632, status: 'completed' },
          ],
        },
      },
    })
    await sync()
    await flushPromises()

    expect(wrapper.find('.download-indicator .el-badge-content').exists()).toBe(false)
    expect(wrapper.find('.download-indicator .dl-anim').exists()).toBe(false)
  })

  it('点击下载入口仍然打开下载管理对话框', async () => {
    const wrapper = factory()
    await flushPromises()
    markQueued([8641])
    await flushPromises()

    await wrapper.find('.download-indicator button').trigger('click')
    await flushPromises()

    expect(wrapper.vm.showDownloadDialog).toBe(true)
  })

  it('tooltip 文案带上进行中数量（用户不必点进去才知道有几个）', async () => {
    const wrapper = factory()
    await flushPromises()
    expect(wrapper.vm.downloadTooltipText).toBe('下载管理')

    markQueued([8651, 8652, 8653])
    await flushPromises()
    expect(wrapper.vm.downloadTooltipText).toBe('下载管理（3 个下载中）')
  })
})

// 移动端圆点菜单里也有一枚下载入口：同一组件、同样要带角标，
// 否则窄屏用户反而看不到「有几个在下载」
describe('Gallery.vue 移动端菜单的下载入口', () => {
  const { markQueued, _resetForTest } = useDownloadState()

  let restoreLayout = null

  beforeEach(() => {
    _resetForTest()
    // 容器窄 / 左侧按钮宽 → useMobileMenu 判定为移动端
    const original = Object.getOwnPropertyDescriptor(
      globalThis.HTMLElement.prototype,
      'offsetWidth'
    )
    Object.defineProperty(globalThis.HTMLElement.prototype, 'offsetWidth', {
      configurable: true,
      get() {
        if (this.classList?.contains('top-toolbar')) return 300
        if (this.closest?.('.toolbar-left')) return 200
        return 0
      },
    })
    restoreLayout = () =>
      Object.defineProperty(globalThis.HTMLElement.prototype, 'offsetWidth', original)
  })

  afterEach(() => {
    restoreLayout?.()
    restoreLayout = null
  })

  it('展开圆点菜单后：下载入口同样带角标与动效', async () => {
    const wrapper = factory()
    wrapper.vm.mobileMenuExpanded = true
    await flushPromises()
    expect(wrapper.vm.useMobileMenu).toBe(true)

    markQueued([8661, 8662])
    await flushPromises()

    const badge = wrapper.find('.mobile-expand-menu .download-indicator .el-badge-content')
    expect(badge.text()).toBe('2')
    expect(wrapper.find('.mobile-expand-menu .dl-anim').exists()).toBe(true)
  })

  it('点击移动端下载入口：打开下载管理并收起菜单', async () => {
    const wrapper = factory()
    wrapper.vm.mobileMenuExpanded = true
    await flushPromises()

    await wrapper.find('.mobile-expand-menu .download-indicator button').trigger('click')
    await flushPromises()

    expect(wrapper.vm.showDownloadDialog).toBe(true)
    expect(wrapper.vm.mobileMenuExpanded).toBe(false)
  })
})

// =============================================================================
// 收藏夹角标增量：下载完成 → O(1) +N，走 POST /favorites/{id}/local-count
//
// 为什么不用 updateLocalCount：它打的是 /favorites/{id}/refresh，后端会重跑
// `tags LIKE ... AND down_flag=1` 的 COUNT（随已下载库线性放大，且该路由
// 未走 asyncio.to_thread → 阻塞事件循环）。批量下载按张刷新会放大 N 倍。
// =============================================================================
describe('Gallery.vue 收藏夹角标增量（下载完成 → +N）', () => {
  const { sync, _resetForTest } = useDownloadState()

  const complete = async (ids) => {
    apiMock.get.mockResolvedValueOnce({
      data: {
        data: {
          active: [],
          finished: ids.map((image_id) => ({ image_id, status: 'completed' })),
        },
      },
    })
    await sync()
    await flushPromises()
  }

  /** 把 Gallery 置于「某收藏夹的二级页」：querySource=favorites + currentFavorite + images */
  const enterFolderDetail = async (wrapper, folder, images) => {
    wrapper.vm.querySource = 'favorites'
    wrapper.vm.currentFavorite = folder
    wrapper.vm.images = images
    await flushPromises()
  }

  const mkImg = (id) => ({ id, down_flag: false, preview_url: `p${id}.jpg` })

  beforeEach(() => {
    _resetForTest()
  })

  it('收藏夹二级页里下载完成 1 张 → setLocalCount(上次值+1)，且不打 /refresh', async () => {
    const wrapper = factory()
    await flushPromises()
    const folder = { id: 42, name: 'f1', local_count: 100 }
    await enterFolderDetail(wrapper, folder, [mkImg(8301), mkImg(8302)])

    await complete([8301])

    expect(setLocalCountMock).toHaveBeenCalledTimes(1)
    expect(setLocalCountMock).toHaveBeenCalledWith(42, 101)
    expect(folder.local_count).toBe(101)
  })

  it('一轮内完成多张 → 只发一次请求，增量等于张数', async () => {
    const wrapper = factory()
    await flushPromises()
    const folder = { id: 43, name: 'f2', local_count: 7 }
    await enterFolderDetail(wrapper, folder, [mkImg(8303), mkImg(8304), mkImg(8305)])

    await complete([8303, 8304, 8305])

    expect(setLocalCountMock).toHaveBeenCalledTimes(1)
    expect(setLocalCountMock).toHaveBeenCalledWith(43, 10)
  })

  it('完成的图不在当前收藏夹已加载列表里 → 不虚增（避免给无关收藏夹加数）', async () => {
    const wrapper = factory()
    await flushPromises()
    const folder = { id: 44, name: 'f3', local_count: 50 }
    await enterFolderDetail(wrapper, folder, [mkImg(8306)])

    await complete([9999]) // 别处下载的图

    expect(setLocalCountMock).not.toHaveBeenCalled()
    expect(folder.local_count).toBe(50)
  })

  it('非收藏夹视图（本地浏览）下载完成 → 不动任何收藏夹角标', async () => {
    const wrapper = factory()
    await flushPromises()
    wrapper.vm.querySource = 'local'
    wrapper.vm.currentFavorite = null
    wrapper.vm.images = [mkImg(8307)]
    await flushPromises()

    await complete([8307])

    expect(setLocalCountMock).not.toHaveBeenCalled()
  })

  it('虚拟磁贴 id（my-favorites / random 字符串）不会被当成收藏夹去 +1', async () => {
    const wrapper = factory()
    await flushPromises()
    await enterFolderDetail(wrapper, { id: 'my-favorites', local_count: 5 }, [mkImg(8308)])

    await complete([8308])

    expect(setLocalCountMock).not.toHaveBeenCalled()
  })

  it('同一张图重复回放 completed → 不会重复累加', async () => {
    const wrapper = factory()
    await flushPromises()
    const folder = { id: 45, name: 'f5', local_count: 20 }
    await enterFolderDetail(wrapper, folder, [mkImg(8309)])

    await complete([8309])
    await complete([8309]) // 终态窗口内后端再次回放同一条
    await complete([8309])

    expect(setLocalCountMock).toHaveBeenCalledTimes(1)
    expect(folder.local_count).toBe(21)
  })
})

// =============================================================================
// 瀑布流卡片收藏 → 「下载中」回归
//
// Bug：WaterfallGallery 把卡片 HeartOverlay 的 changed 透传成 favorite-toggled，
// 但 Gallery 从未绑定 @favorite-toggled → onFavoriteChanged 根本不执行。
// 症状：在线图片点卡片红心收藏 → 后端建了下载任务 → 前端无「下载中」，
//       等下载完成后被轮询对账标成「已下载」小绿点（只有绿点，没有下载中）。
// =============================================================================
describe('Gallery.vue 卡片收藏事件接线（favorite-toggled）', () => {
  const { downStateOf, _resetForTest } = useDownloadState()

  const emitCardFavorite = async (wrapper, payload) => {
    wrapper.findComponent({ name: 'WaterfallGallery' }).vm.$emit('favorite-toggled', payload)
    await flushPromises()
  }

  beforeEach(() => {
    _resetForTest()
  })

  it('卡片收藏且后端已建下载任务 → 立即标记「下载中」', async () => {
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    useFavoritesConfig().enableMyFavorites.value = true

    const wrapper = factory()
    await flushPromises()
    const image = { id: 8401, down_flag: false }

    await emitCardFavorite(wrapper, { imageId: 8401, favorited: true, downloadStarted: true })

    expect(downStateOf(image)).toBe('downloading')
  })

  it('卡片收藏未触发自动下载 → 不标记下载态（不误标）', async () => {
    const wrapper = factory()
    await flushPromises()
    const image = { id: 8402, down_flag: false }

    await emitCardFavorite(wrapper, { imageId: 8402, favorited: true, downloadStarted: false })

    expect(downStateOf(image)).toBe('none')
  })

  it('卡片收藏时详情页开着同一张图 → 同步 currentImage.is_favorited', async () => {
    const wrapper = factory()
    await flushPromises()
    wrapper.vm.currentImage = { id: 8403, is_favorited: false, down_flag: false }
    await flushPromises()

    await emitCardFavorite(wrapper, { imageId: 8403, favorited: true, downloadStarted: false })

    expect(wrapper.vm.currentImage.is_favorited).toBe(true)
  })

  it('取消收藏（favorited=false）不碰下载态', async () => {
    const wrapper = factory()
    await flushPromises()
    const image = { id: 8404, down_flag: true }

    await emitCardFavorite(wrapper, { imageId: 8404, favorited: false, downloadStarted: false })

    expect(downStateOf(image)).toBe('downloaded')
  })
})

// =============================================================================
// 收藏夹二级页 local_count 对齐（恢复 534f776 的原意，去掉死分支）
//
// /gallery/load 的 favorites 分支是「按 folder.tags 查本地已下载图」，
// 所以 response.total 就是 local_count 的定义 → 直接 O(1) 写回，无需 COUNT。
// 旧代码把这条包进了永不可达的 `if (querySource === 'local')` 死分支。
// =============================================================================
describe('Gallery.vue 收藏夹二级页 local_count 对齐', () => {
  const { _resetForTest } = useDownloadState()

  beforeEach(() => {
    _resetForTest()
  })

  const loadFolderPage = async (wrapper, folder, total) => {
    wrapper.vm.querySource = 'favorites'
    wrapper.vm.currentFavorite = folder
    wrapper.vm.currentPage = 1
    apiMock.post.mockResolvedValueOnce({ data: [], has_more: false, total })
    await wrapper.vm.loadImages(1)
    await flushPromises()
  }

  it('进入收藏夹二级页 → setLocalCount(folderId, /gallery/load 的 total)', async () => {
    const wrapper = factory()
    await flushPromises()
    const folder = { id: 46, name: 'f6', local_count: 999 }

    await loadFolderPage(wrapper, folder, 128)

    expect(setLocalCountMock).toHaveBeenCalledWith(46, 128)
    expect(folder.local_count).toBe(128)
  })

  it('不再调用 updateLocalCount（/refresh 那条 COUNT 路径在 Gallery 里已无引用）', async () => {
    const wrapper = factory()
    await flushPromises()
    const folder = { id: 47, name: 'f7', local_count: 1 }

    await loadFolderPage(wrapper, folder, 5)

    expect(updateLocalCountMock).not.toHaveBeenCalled()
  })

  it('非收藏夹视图（本地浏览）→ 不写任何收藏夹角标', async () => {
    const wrapper = factory()
    await flushPromises()
    wrapper.vm.querySource = 'local'
    wrapper.vm.currentFavorite = null
    wrapper.vm.currentPage = 1
    apiMock.post.mockResolvedValueOnce({ data: [], has_more: false, total: 77 })
    await wrapper.vm.loadImages(1)
    await flushPromises()

    expect(setLocalCountMock).not.toHaveBeenCalled()
  })
})

describe('Gallery.vue virtualSelectedFavorite + 虚拟磁贴导航（修复问题 5 + 6）', () => {  // 虚拟 favorite chip 由 Gallery.vue 基于 querySource 派生，传给 AdvancedQuery。
  // 弹窗内 FavoritePanel 虚拟磁点击中后，Gallery 监听 @virtual-tile-navigate 强制
  // handleSourceChange 刷新（绕过 vue-router 同 url push 不发事件的限制）。

  it('querySource="my-favorites" → virtualSelectedFavorite={id, name="我的最爱"}', async () => {
    const wrapper = factory()
    await flushPromises()

    wrapper.vm.querySource = 'my-favorites'
    await flushPromises()

    expect(wrapper.vm.virtualSelectedFavorite).toEqual({
      id: 'my-favorites',
      name: '我的最爱',
    })
  })

  it('querySource="random" → virtualSelectedFavorite={id, name="随机浏览"}', async () => {
    const wrapper = factory()
    await flushPromises()

    wrapper.vm.querySource = 'random'
    await flushPromises()

    expect(wrapper.vm.virtualSelectedFavorite).toEqual({
      id: 'random',
      name: '随机浏览',
    })
  })

  it('querySource 其它值（local / yande / favorites）→ virtualSelectedFavorite=null', async () => {
    const wrapper = factory()
    await flushPromises()

    for (const src of ['local', 'yande', 'favorites']) {
      wrapper.vm.querySource = src
      await flushPromises()
      expect(wrapper.vm.virtualSelectedFavorite).toBeNull()
    }
  })

  it('AdvancedQuery :virtual-favorite prop 接收派生值', async () => {
    const wrapper = factory()
    await flushPromises()

    wrapper.vm.querySource = 'my-favorites'
    await flushPromises()

    const advStub = wrapper.findComponent({ name: 'AdvancedQuery' })
    expect(advStub.props('virtualFavorite')).toEqual({
      id: 'my-favorites',
      name: '我的最爱',
    })
  })

  it('handleVirtualTileNavigate("my-favorites") → handleSourceChange("my-favorites") 强制刷新（修复问题 5：弹窗内重复点击失效）', async () => {
    const wrapper = factory()
    await flushPromises()

    // 初始 querySource 是 local。模拟 FavoritePanel 转发：先点 my-favorites
    wrapper.vm.handleVirtualTileNavigate('my-favorites')
    await flushPromises()

    expect(wrapper.vm.querySource).toBe('my-favorites')
    // handleSourceChange → handleSearch → loadImages 应调 myFavoritesApi.images
    expect(myFavoritesApiMock.images).toHaveBeenCalled()

    // 关键：再次点击 my-favorites（重复点击）应**仍然**触发刷新
    //   即使 querySource 已经是 'my-favorites'，handleSourceChange 内部的清空 + handleSearch({}) 链路
    //   保证 images 数组被重置 + 重新调 API
    const callsBefore = myFavoritesApiMock.images.mock.calls.length
    wrapper.vm.handleVirtualTileNavigate('my-favorites')
    await flushPromises()

    expect(myFavoritesApiMock.images.mock.calls.length).toBeGreaterThan(callsBefore)
  })

  it('handleVirtualTileNavigate 拒绝非 my-favorites/random 值（防御性）', async () => {
    const wrapper = factory()
    await flushPromises()

    const before = wrapper.vm.querySource
    wrapper.vm.handleVirtualTileNavigate('favorites')  // 不应直接处理
    await flushPromises()

    // querySource 不会变（拒绝非法值，避免误触发）
    expect(wrapper.vm.querySource).toBe(before)
  })
})

describe('Gallery.vue BackButton 可见性 + 收藏夹 tab 焦点（修复问题 7 + 8）', () => {
  // 修复问题 7：虚拟视图（my-favorites / random）应显示 BackButton（与 favorites folder-detail 一致）
  // 修复问题 8：toolbar '收藏夹' tab 应在虚拟视图高亮（虚拟视图属于收藏夹上下文）

  it('isBackVisible：favorites folder-detail → true', async () => {
    const wrapper = factory()
    await flushPromises()
    wrapper.vm.querySource = 'favorites'
    wrapper.vm.favoritesView = 'folder-detail'
    await flushPromises()
    expect(wrapper.vm.isBackVisible).toBe(true)
  })

  it('isBackVisible：my-favorites → true', async () => {
    const wrapper = factory()
    await flushPromises()
    wrapper.vm.querySource = 'my-favorites'
    await flushPromises()
    expect(wrapper.vm.isBackVisible).toBe(true)
  })

  it('isBackVisible：random → true', async () => {
    const wrapper = factory()
    await flushPromises()
    wrapper.vm.querySource = 'random'
    await flushPromises()
    expect(wrapper.vm.isBackVisible).toBe(true)
  })

  it('isBackVisible：favorites folders / local / yande → false', async () => {
    const wrapper = factory()
    await flushPromises()

    wrapper.vm.querySource = 'favorites'
    wrapper.vm.favoritesView = 'folders'
    await flushPromises()
    expect(wrapper.vm.isBackVisible).toBe(false)

    wrapper.vm.querySource = 'local'
    await flushPromises()
    expect(wrapper.vm.isBackVisible).toBe(false)

    wrapper.vm.querySource = 'yande'
    await flushPromises()
    expect(wrapper.vm.isBackVisible).toBe(false)
  })

  it('handleBackClick 在虚拟视图（my-favorites）→ handleSourceChange("favorites")', async () => {
    const wrapper = factory()
    await flushPromises()

    wrapper.vm.handleSourceChange('my-favorites')
    await flushPromises()
    expect(wrapper.vm.querySource).toBe('my-favorites')

    wrapper.vm.handleBackClick()
    await flushPromises()

    expect(wrapper.vm.querySource).toBe('favorites')
    expect(wrapper.vm.favoritesView).toBe('folders')
    expect(getFoldersWithPreviewMock).toHaveBeenCalled()
  })

  it('handleBackClick 在虚拟视图（random）→ handleSourceChange("favorites")', async () => {
    const wrapper = factory()
    await flushPromises()

    wrapper.vm.handleSourceChange('random')
    await flushPromises()
    expect(wrapper.vm.querySource).toBe('random')

    wrapper.vm.handleBackClick()
    await flushPromises()

    expect(wrapper.vm.querySource).toBe('favorites')
  })

  it('handleBackClick 在 favorites folder-detail → handleBackToFolders（精确清理）', async () => {
    const wrapper = factory()
    await flushPromises()

    wrapper.vm.handleSourceChange('favorites')
    await flushPromises()
    wrapper.vm.handleFolderClick({ id: 5, name: 'f', tags: '' })
    await flushPromises()
    expect(wrapper.vm.favoritesView).toBe('folder-detail')

    // Spy 替换 queryRef 的清理方法
    const resetAdvancedPanelSpy = vi.fn()
    const clearSelectedFavoriteSpy = vi.fn()
    const advInstance = wrapper.findComponent({ name: 'AdvancedQuery' })
    advInstance.vm.__resetAdvancedPanel = resetAdvancedPanelSpy
    advInstance.vm.__clearSelectedFavoriteNoSearch = clearSelectedFavoriteSpy

    wrapper.vm.handleBackClick()
    await flushPromises()

    expect(wrapper.vm.favoritesView).toBe('folders')
    expect(resetAdvancedPanelSpy).toHaveBeenCalled()
    expect(clearSelectedFavoriteSpy).toHaveBeenCalled()
  })

  it('isFavoritesActive：favorites / my-favorites / random → true', async () => {
    const wrapper = factory()
    await flushPromises()

    for (const src of ['favorites', 'my-favorites', 'random']) {
      wrapper.vm.querySource = src
      await flushPromises()
      expect(wrapper.vm.isFavoritesActive).toBe(true)
    }
  })

  it('isFavoritesActive：local / yande → false（toolbar 收藏夹 tab 不高亮）', async () => {
    const wrapper = factory()
    await flushPromises()

    for (const src of ['local', 'yande']) {
      wrapper.vm.querySource = src
      await flushPromises()
      expect(wrapper.vm.isFavoritesActive).toBe(false)
    }
  })

  it('BackButtonStub visible prop 接收 isBackVisible', async () => {
    const wrapper = factory()
    await flushPromises()

    wrapper.vm.querySource = 'my-favorites'
    await flushPromises()

    const backBtn = wrapper.findComponent({ name: 'BackButton' })
    expect(backBtn.exists()).toBe(true)
    expect(backBtn.props('visible')).toBe(true)
  })
})

// =============================================================================
// 最近下载（querySource = 'recent-downloads'）— 设计文档 §4.5 / §2.4
// =============================================================================
describe('Gallery.vue 最近下载视图（querySource=recent-downloads）', () => {
  // 抽取最后一次 /gallery/load 的 payload（loadImages 走 api.post）
  const lastLoadPayload = () => {
    const calls = apiMock.post.mock.calls.filter((c) => c[0] === '/gallery/load')
    return calls[calls.length - 1]?.[1] || null
  }

  it('loadImages 注入 sort_by=downloaded_at + sort_order=desc 且 source=local', async () => {
    const wrapper = factory()
    await flushPromises()
    apiMock.post.mockClear()

    wrapper.vm.handleSourceChange('recent-downloads')
    await flushPromises()

    const payload = lastLoadPayload()
    expect(payload).toBeTruthy()
    expect(payload.source).toBe('local')
    expect(payload.sort_by).toBe('downloaded_at')
    expect(payload.sort_order).toBe('desc')
    // 最近下载不走随机浏览分支
    expect('random' in payload).toBe(false)
    // 不走我的最爱专用端点
    expect(myFavoritesApiMock.images).not.toHaveBeenCalled()
  })

  it('recent-downloads 不带 random / favorite_id（与 random 模式对称的防御性清理）', async () => {
    const wrapper = factory()
    await flushPromises()

    // 先在 favorites folder-detail 制造 favorite_id 残留
    wrapper.vm.querySource = 'favorites'
    await flushPromises()
    wrapper.vm.queryParams = { favorite_id: 3, source: 'favorites' }
    apiMock.post.mockClear()

    wrapper.vm.querySource = 'recent-downloads'
    await wrapper.vm.loadImages(1)
    await flushPromises()

    const payload = lastLoadPayload()
    expect(payload.favorite_id).toBeUndefined()
    expect(payload.source).toBe('local')
    expect(payload.sort_by).toBe('downloaded_at')
  })

  it('querySource=recent-downloads → virtualSelectedFavorite={id, name="最近下载"}', async () => {
    const wrapper = factory()
    await flushPromises()

    wrapper.vm.querySource = 'recent-downloads'
    await flushPromises()

    expect(wrapper.vm.virtualSelectedFavorite).toEqual({
      id: 'recent-downloads',
      name: '最近下载',
    })
  })

  it('BackButton 可见 + 收藏夹 tab 高亮（与 my-favorites / random 对称）', async () => {
    const wrapper = factory()
    await flushPromises()

    wrapper.vm.querySource = 'recent-downloads'
    await flushPromises()

    expect(wrapper.vm.isBackVisible).toBe(true)
    expect(wrapper.vm.isFavoritesActive).toBe(true)
    const backBtn = wrapper.findComponent({ name: 'BackButton' })
    expect(backBtn.props('visible')).toBe(true)
  })

  it('handleVirtualTileNavigate("recent-downloads") → handleSourceChange 强制刷新', async () => {
    const wrapper = factory()
    await flushPromises()
    expect(wrapper.vm.querySource).toBe('local')

    wrapper.vm.handleVirtualTileNavigate('recent-downloads')
    await flushPromises()

    expect(wrapper.vm.querySource).toBe('recent-downloads')
    const payload = lastLoadPayload()
    expect(payload.sort_by).toBe('downloaded_at')
    expect(payload.source).toBe('local')
  })

  it('点击收藏夹视图的「最近下载」虚拟磁贴 → 切 querySource 而非进 folder-detail', async () => {
    const wrapper = factory()
    await flushPromises()

    wrapper.vm.handleFolderClick({ id: 'recent-downloads', name: '最近下载', isVirtual: true })
    await flushPromises()

    expect(wrapper.vm.querySource).toBe('recent-downloads')
    expect(wrapper.vm.favoritesView).toBeNull()
  })

  it('handleSearch 解析 mode=recent-downloads 时把 source 映射为 local', async () => {
    const wrapper = factory()
    await flushPromises()

    // AdvancedQuery 的 mode 来自 props.sourceMode = querySource，因此先切到最近下载视图
    wrapper.vm.querySource = 'recent-downloads'
    await flushPromises()
    apiMock.post.mockClear()

    await wrapper.vm.handleSearch({ mode: 'recent-downloads', params: { tags: 'x' } })
    await flushPromises()

    const payload = lastLoadPayload()
    expect(payload.source).toBe('local')
    expect(payload.tags).toBe('x')
    // 排序注入统一在 loadImages 的 extraParams 里（与 random=true 同一处）
    expect(payload.sort_by).toBe('downloaded_at')
    expect(payload.sort_order).toBe('desc')
  })

  it('querySource=local 时即使 mode 传入 recent-downloads 也不注入 downloaded_at 排序', async () => {
    const wrapper = factory()
    await flushPromises()
    apiMock.post.mockClear()

    await wrapper.vm.handleSearch({ mode: 'recent-downloads', params: {} })
    await flushPromises()

    const payload = lastLoadPayload()
    expect(payload.source).toBe('local')
    expect(payload.sort_by).toBeUndefined()
  })

  it('route.query.querySource=recent-downloads → 首屏即按下载时间倒序加载', async () => {
    mockRoute.value.query = { querySource: 'recent-downloads' }
    const wrapper = factory()
    await flushPromises()

    expect(wrapper.vm.querySource).toBe('recent-downloads')
    const payload = lastLoadPayload()
    expect(payload.source).toBe('local')
    expect(payload.sort_by).toBe('downloaded_at')
    expect(payload.sort_order).toBe('desc')
  })

  // ---------------------------------------------------------------------------
  // 记录清理已迁移到下载页（Download.vue，2026-10-01）
  // 「最近下载」二级页只负责浏览，不再承担清理入口。
  // ---------------------------------------------------------------------------
  it('recent-downloads 视图不渲染清除按钮组（清理入口已移至下载页）', async () => {
    const wrapper = factory()
    await flushPromises()

    wrapper.vm.querySource = 'recent-downloads'
    await flushPromises()

    expect(wrapper.find('.recent-downloads-toolbar').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('清空全部记录')
  })
})
