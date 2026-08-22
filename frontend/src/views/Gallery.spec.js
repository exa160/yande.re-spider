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

beforeEach(() => {
  getFoldersWithPreviewMock.mockClear()
  // localStorage 在 happy-dom 默认可用；显式清空避免其它测试残留
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
  props: ['sourceMode', 'mode', 'lockFavoriteChip', 'favoritesConfig'],
  emits: ['search', 'favorites-filter', 'favorites-config-change'],
  template: '<div class="advanced-query-stub"><slot/></div>',
  // 暴露 selectFavorite / reset / resetAdvancedPanel 给父组件
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
  },
}

const factory = () =>
  mount(Gallery, {
    global: {
      stubs: {
        BackButton: BackButtonStub,
        AdvancedQuery: AdvancedQueryStub,
        WaterfallGallery: { template: '<div class="waterfall-stub"><slot/></div>' },
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
        ArrowLeft: { template: '<i></i>' },
        ArrowRight: { template: '<i></i>' },
        Check: { template: '<i></i>' },
        Search: { template: '<i></i>' },
        Folder: { template: '<i></i>' },
        Menu: { template: '<i></i>' },
      },
    },
  })

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
    expect(getFoldersWithPreviewMock).toHaveBeenCalledWith(1, 20, 'adaptive')
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

  it('handleBackToFolders → favoritesView 重置为 "folders" 且调用 queryRef.reset', async () => {
    const wrapper = factory()
    await flushPromises()
    // 进入 favorites + 进入 folder-detail
    wrapper.vm.handleSourceChange('favorites')
    await flushPromises()
    wrapper.vm.handleFolderClick({ id: 5, name: 'f', tags: '' })
    await flushPromises()
    expect(wrapper.vm.favoritesView).toBe('folder-detail')

    // 替换 queryRef.reset 为 spy
    const resetSpy = vi.fn()
    const advInstance = wrapper.findComponent({ name: 'AdvancedQuery' })
    advInstance.vm.__reset = resetSpy

    wrapper.vm.handleBackToFolders()
    await flushPromises()

    expect(wrapper.vm.favoritesView).toBe('folders')
    expect(wrapper.vm.selectedFavoriteFolder).toBeNull()
    expect(resetSpy).toHaveBeenCalledTimes(1)
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
    expect(getFoldersWithPreviewMock).toHaveBeenCalledWith(1, 20, 'medium')
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
    expect(getFoldersWithPreviewMock).toHaveBeenCalledWith(1, 20, 'large')

    // 切换 tileSize='4' 并重新加载（page=2）→ 契约应为 'small'
    getFoldersWithPreviewMock.mockClear()
    wrapper.vm.tileSize = '4'
    await wrapper.vm.loadFolders(2)
    await flushPromises()
    expect(getFoldersWithPreviewMock).toHaveBeenCalledWith(2, 20, 'small')

    // tileSize='6' → 契约应为 'medium'
    getFoldersWithPreviewMock.mockClear()
    wrapper.vm.tileSize = '6'
    await wrapper.vm.loadFolders(1)
    await flushPromises()
    expect(getFoldersWithPreviewMock).toHaveBeenCalledWith(1, 20, 'medium')

    // 'adaptive' 透传（不在映射表中，原样传递）
    getFoldersWithPreviewMock.mockClear()
    wrapper.vm.tileSize = 'adaptive'
    await wrapper.vm.loadFolders(1)
    await flushPromises()
    expect(getFoldersWithPreviewMock).toHaveBeenCalledWith(1, 20, 'adaptive')
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

  it('buttonMode=default → onMounted 默认进入 favorites 视图', async () => {
    localStorage.setItem('gallery_favorites_button_mode', 'default')
    const wrapper = factory()
    await flushPromises()

    expect(wrapper.vm.buttonMode).toBe('default')
    expect(wrapper.vm.querySource).toBe('favorites')
    expect(wrapper.vm.favoritesView).toBe('folders')
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

  it('@favorites-config-change → 更新本地 buttonMode 与 tileSize', async () => {
    localStorage.clear()
    const wrapper = factory()
    await flushPromises()
    expect(wrapper.vm.buttonMode).toBe('shown')
    expect(wrapper.vm.tileSize).toBe('adaptive')

    const advInstance = wrapper.findComponent({ name: 'AdvancedQuery' })
    advInstance.vm.$emit('favorites-config-change', { buttonMode: 'default', tileSize: '6' })
    await flushPromises()

    expect(wrapper.vm.buttonMode).toBe('default')
    expect(wrapper.vm.tileSize).toBe('6')
  })

  it('@favorites-config-change → 切到 default 时 querySource 跳到 favorites', async () => {
    localStorage.clear()
    const wrapper = factory()
    await flushPromises()
    expect(wrapper.vm.querySource).toBe('local')

    const advInstance = wrapper.findComponent({ name: 'AdvancedQuery' })
    advInstance.vm.$emit('favorites-config-change', { buttonMode: 'default', tileSize: 'adaptive' })
    await flushPromises()

    expect(wrapper.vm.querySource).toBe('favorites')
    expect(wrapper.vm.favoritesView).toBe('folders')
  })
})