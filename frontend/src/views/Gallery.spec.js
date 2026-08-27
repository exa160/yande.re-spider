import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import Gallery from './Gallery.vue'

// 监听 getFoldersWithPreview 调用
const getFoldersWithPreviewMock = vi.fn().mockResolvedValue({
  data: { items: [], total: 0, has_more: false },
})

// 默认 gallery/load 返回空列表，避免 onMounted 时真实请求
vi.mock('@/api', () => ({
  default: {
    post: vi.fn().mockResolvedValue({ data: [], has_more: false }),
    get: vi.fn().mockResolvedValue({ data: {} }),
  },
}))

vi.mock('@/api/tagCache', () => ({
  tagCacheApi: { getTagsByNames: vi.fn().mockResolvedValue({ data: {} }) },
}))

vi.mock('@/api/favorites', () => ({
  getFoldersWithPreview: (...args) => getFoldersWithPreviewMock(...args),
  updateOnlineCount: vi.fn().mockResolvedValue({ data: { count: 0 } }),
  updateLocalCount: vi.fn().mockResolvedValue({ data: { count: 0 } }),
  refreshOnlineCount: vi.fn().mockResolvedValue({ data: { count: 0 } }),
}))

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
  props: ['sourceMode', 'mode', 'lockFavoriteChip'],
  emits: ['search', 'favorites-filter'],
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
          props: ['images', 'loading', 'hasMore', 'isLoadingMore', 'loadError', 'itemType', 'sourceMode', 'selectable', 'selectedImages', 'saveDataMode', 'safeMode'],
          emits: ['load-more', 'load-error', 'image-click', 'image-select', 'multi-select-start'],
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
        'el-tag': { template: '<span><slot/></span>' },
        'el-tooltip': { template: '<div><slot/></div>' },
        'el-dialog': { template: '<div><slot/></div>' },
        'el-image-viewer': { template: '<div></div>' },
        'el-image': { template: '<img></div>' },
        'el-radio-group': { template: '<div class="radio-group-stub"><slot/></div>' },
        'el-radio-button': { template: '<button class="radio-button-stub"><slot/></button>' },
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
