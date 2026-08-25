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
  props: ['sourceMode'],
  emits: ['search'],
  template: '<div class="advanced-query-stub"><slot/></div>',
  // 暴露 selectFavorite / reset 给父组件
  methods: {
    selectFavorite(folder) {
      this.__selectFavorite?.(folder)
    },
    reset() {
      this.__reset?.()
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
        'el-button': { template: '<button><slot/></button>' },
        'el-button-group': { template: '<div><slot/></div>' },
        'el-icon': { template: '<i><slot/></i>' },
        'el-tag': { template: '<span><slot/></span>' },
        'el-tooltip': { template: '<div><slot/></div>' },
        'el-dialog': { template: '<div><slot/></div>' },
        'el-image-viewer': { template: '<div></div>' },
        'el-image': { template: '<img></div>' },
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
    expect(getFoldersWithPreviewMock).toHaveBeenCalledWith(1, 20)
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
})