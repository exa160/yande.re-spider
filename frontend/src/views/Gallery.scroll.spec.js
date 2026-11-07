// =============================================================================
// Gallery.vue 滚动位置策略（scroll-position policy）专项测试
//
// 契约（对应 Gallery.vue 中的统一滚动策略实现）：
//   1) 进入新视图（二级页 / 切 source / 新搜索 / 切路由）→ 回到顶部 scrollTo(0, 0)
//   2) 从二级页返回收藏夹一级页 → 恢复进入前的位置（锚点优先，锚点不可用回退像素）
//   3) 自动定位过程中用户主动滚动（scroll 事件 isTrusted === true）→ 立即停止干预
//
// 本文件只测滚动行为，mock 脚手架与 Gallery.spec.js 保持一致（只复制，不修改那份文件）。
// =============================================================================
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { nextTick } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import Gallery from './Gallery.vue'

// 详情页走 <teleport to="body">，teleport 出去的 DOM 会跨用例累积 → 每个用例后清空 body
afterEach(() => {
  document.body.innerHTML = ''
})

// vue-router mock：Gallery 用 useRoute()/useRouter()
const mockRoute = { value: { query: {} } }
vi.mock('vue-router', () => ({
  useRoute: () => mockRoute.value,
  useRouter: () => ({ push: vi.fn() }),
  createRouter: vi.fn(),
  createWebHistory: vi.fn(),
}))

const getAllFoldersMock = vi.fn().mockResolvedValue({ data: [] })
const previewFolderMock = vi.fn().mockResolvedValue({
  data: { total: 0, preview_images: [] },
})

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

const { setLocalCountMock, updateLocalCountMock, refreshOnlineCountMock } = vi.hoisted(() => ({
  setLocalCountMock: vi.fn().mockResolvedValue({ data: { count: 0 } }),
  updateLocalCountMock: vi.fn().mockResolvedValue({ data: { count: 0 } }),
  refreshOnlineCountMock: vi.fn().mockResolvedValue({ data: { count: 0 } }),
}))
vi.mock('@/api/favorites', () => ({
  getAllFolders: (...args) => getAllFoldersMock(...args),
  previewFolder: (...args) => previewFolderMock(...args),
  updateLocalCount: updateLocalCountMock,
  setLocalCount: setLocalCountMock,
  refreshOnlineCount: refreshOnlineCountMock,
}))

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

const { recentDownloadsApiMock } = vi.hoisted(() => ({
  recentDownloadsApiMock: {
    getCount: vi.fn().mockResolvedValue({ data: { count: 0 } }),
    getPreview: vi.fn().mockResolvedValue({ data: { images: [] } }),
    clearRecords: vi.fn().mockResolvedValue({ data: { deleted: 0 } }),
    clear: vi.fn().mockResolvedValue({ data: { deleted: 0 } }),
  },
}))
vi.mock('@/api/recentDownloads', () => ({
  recentDownloadsApi: recentDownloadsApiMock,
}))

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

import { useFavoritesConfig } from '@/composables/useFavoritesConfig'

const mountedWrappers = []

beforeEach(async () => {
  mountedWrappers.forEach((w) => w.unmount())
  mountedWrappers.length = 0
  getAllFoldersMock.mockClear()
  previewFolderMock.mockClear()
  getAllFoldersMock.mockResolvedValue({ data: [] })
  previewFolderMock.mockResolvedValue({ data: { total: 0, preview_images: [] } })
  Object.values(myFavoritesApiMock).forEach((m) => m.mockClear && m.mockClear())
  Object.values(recentDownloadsApiMock).forEach((m) => m.mockReset && m.mockReset())
  elMessageBoxConfirmMock.mockReset()
  elMessageBoxConfirmMock.mockResolvedValue(undefined)
  stubEmitSearchOnSelectFavorite = false
  // 复位收藏夹配置 singleton（模块级 ref，跨用例会残留）
  const favCfg = useFavoritesConfig()
  favCfg.enableMyFavorites.value = false
  favCfg.enableRandomBrowse.value = false
  favCfg.enableRecentDownloads.value = false
  favCfg.folderPageSize.value = 20
  favCfg.previewOrder.value = 'random'
  favCfg.includeOnline.value = false
  favCfg.tileSize.value = 'adaptive'
  favCfg.recentDownloadsCount.value = 0
  favCfg.myFavoritesCount.value = 0
  setLocalCountMock.mockClear()
  updateLocalCountMock.mockClear()
  refreshOnlineCountMock.mockClear()
  apiMock.post.mockReset()
  apiMock.post.mockResolvedValue({ data: [], has_more: false })
  apiMock.get.mockClear()
  mockRoute.value.query = {}
  localStorage.clear()
  globalThis.ResizeObserver = vi.fn().mockImplementation(() => ({
    observe: vi.fn(),
    disconnect: vi.fn(),
    unobserve: vi.fn(),
  }))
})

// ---------------------------------------------------------------- 组件桩
const BackButtonStub = {
  name: 'BackButton',
  props: ['visible'],
  emits: ['click'],
  template: '<button class="back-btn-stub" v-if="visible" @click="$emit(\'click\')">back</button>',
}

// 真实 AdvancedQuery.selectFavorite 会 emit('search') 触发 Gallery 重新搜索。
// 专项用例需要"慢搜索"来复现迟到的回顶，用开关控制；默认关闭以免影响既有用例。
let stubEmitSearchOnSelectFavorite = false

const AdvancedQueryStub = {
  name: 'AdvancedQuery',
  props: ['sourceMode', 'mode', 'lockFavoriteChip', 'virtualFavorite'],
  emits: ['search', 'favorites-filter', 'virtual-tile-navigate', 'virtual-favorite-remove', 'favorite-enter-folder-detail'],
  template: '<div class="advanced-query-stub"><slot/></div>',
  methods: {
    selectFavorite(folder) {
      this.__selectFavorite?.(folder)
      if (stubEmitSearchOnSelectFavorite) {
        this.$emit('search', { mode: 'favorites', params: {}, favorite: folder })
      }
    },
    reset() {
      this.__reset?.()
    },
    resetAdvancedPanel() {
      this.__resetAdvancedPanel?.()
    },
    _resetAdvancedParamsNoClose() {
      this.__resetAdvancedParamsNoClose?.()
    },
    _clearSelectedFavoriteNoSearch() {
      this.__clearSelectedFavoriteNoSearch?.()
    },
  },
}

const mountGallery = () => {
  const wrapper = mount(Gallery, {
    global: {
      stubs: {
        BackButton: BackButtonStub,
        AdvancedQuery: AdvancedQueryStub,
        WaterfallGallery: {
          name: 'WaterfallGallery',
          props: ['images', 'loading', 'hasMore', 'isLoadingMore', 'loadError', 'itemType', 'sourceMode', 'selectable', 'selectedImages', 'saveDataMode', 'safeMode', 'showHeart'],
          emits: ['load-more', 'load-error', 'image-click', 'image-select', 'multi-select-start', 'favorite-toggled'],
          // 与真实 WaterfallGallery 的 folder 模式一致：每个磁贴外层带 data-folder-id，
          // 供 Gallery 返回一级页时按 folder 定位滚动
          template: '<div class="waterfall-stub"><div v-for="img in images" :key="img.id" :data-folder-id="img.id"><slot :folder="img" /></div></div>',
        },
        FolderTile: {
          name: 'FolderTile',
          props: ['folder', 'tileSize', 'saveDataMode', 'safeMode', 'observeVisibility', 'previewEpoch'],
          emits: ['click', 'visible'],
          template: '<div class="folder-tile-stub" @click="$emit(\'click\', { id: 1, name: \'stub_folder\', tags: \'foo\' })">stub_tile</div>',
        },
        DownloadManager: { template: '<div></div>' },
        ConfigPanel: { template: '<div></div>' },
        'el-button': { template: '<button class="el-button"><slot/></button>' },
        'el-button-group': { template: '<div><slot/></div>' },
        'el-icon': { template: '<i><slot/></i>' },
        'el-badge': {
          props: ['value', 'hidden', 'max', 'type'],
          template: `<div class="el-badge-stub"><slot/><sup v-if="!hidden && value > 0" class="el-badge-content">{{ value > max ? max + '+' : value }}</sup></div>`,
        },
        'el-tag': { template: '<span><slot/></span>' },
        'el-tooltip': { template: '<div><slot/></div>' },
        'el-dialog': { template: '<div><slot/></div>' },
        'el-image-viewer': { template: '<div></div>' },
        'el-image': { template: '<img>' },
        'el-radio-group': { template: '<div class="radio-group-stub"><slot/></div>' },
        'el-radio-button': { template: '<button class="radio-button-stub"><slot/></button>' },
        'el-select': { props: ['modelValue'], template: '<div class="el-select-stub"><slot/></div>' },
        'el-option': { props: ['label', 'value'], template: '<div class="el-option-stub" :data-value="value">{{ label }}</div>' },
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

// ---------------------------------------------------------------- 小工具
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const mkFolders = (n = 12) =>
  Array.from({ length: n }, (_, i) => ({
    id: i + 1,
    name: `folder_${i + 1}`,
    tags: `tag_${i + 1}`,
    local_count: 100 + i,
    preview_images: [],
  }))

const enterFavorites = async (wrapper) => {
  await wrapper.vm.handleSourceChange('favorites')
  await flushPromises()
}

// 监听 window.scrollTo，并让被调用的 scrollY 真实变化（happy-dom 没有滚动实现）
const installScrollSpy = () => {
  const originalScrollY = window.scrollY
  const spy = vi.spyOn(window, 'scrollTo').mockImplementation((_x, y) => {
    Object.defineProperty(window, 'scrollY', { configurable: true, value: y })
  })
  return {
    spy,
    setScrollY: (v) => Object.defineProperty(window, 'scrollY', { configurable: true, value: v }),
    restore: () => {
      spy.mockRestore()
      Object.defineProperty(window, 'scrollY', { configurable: true, value: originalScrollY })
    },
  }
}

// happy-dom 没有布局：getBoundingClientRect 恒返回全 0（height === 0）。
// 锚点路径必须 stub 出 height > 0 才能被触发。
const stubTileRects = (getRect) => {
  const original = Element.prototype.getBoundingClientRect
  Element.prototype.getBoundingClientRect = function () {
    if (this && typeof this.getAttribute === 'function' && this.hasAttribute('data-folder-id')) {
      return getRect()
    }
    return original.call(this)
  }
  return {
    restore: () => {
      Element.prototype.getBoundingClientRect = original
    },
  }
}

const rect = (top, height) => ({
  top,
  height,
  bottom: top + height,
  left: 0,
  right: 200,
  width: 200,
  x: 0,
  y: top,
})

// =============================================================================
describe('Gallery.vue 滚动位置策略', () => {
  it('点开收藏夹磁贴进入二级页 → window.scrollTo(0, 0)（不沿用一级页旧 scrollY）', async () => {
    const folders = mkFolders(5)
    getAllFoldersMock.mockResolvedValue({ data: folders })

    const wrapper = mountGallery()
    await flushPromises()
    await enterFavorites(wrapper)

    const s = installScrollSpy()
    try {
      // 一级页已经滚到 420
      s.setScrollY(420)
      s.spy.mockClear()

      wrapper.vm.handleFolderClick(folders[0])
      await flushPromises()
      await nextTick()

      expect(wrapper.vm.favoritesView).toBe('folder-detail')
      expect(s.spy).toHaveBeenCalledWith(0, 0)
      expect(window.scrollY).toBe(0)
    } finally {
      s.restore()
    }
  })

  it('从收藏夹下拉面板进入二级页（handleEnterFavoriteFolderDetail）→ window.scrollTo(0, 0)', async () => {
    const folders = mkFolders(5)
    getAllFoldersMock.mockResolvedValue({ data: folders })

    const wrapper = mountGallery()
    await flushPromises()
    await enterFavorites(wrapper)

    const s = installScrollSpy()
    try {
      s.setScrollY(420)
      s.spy.mockClear()

      wrapper.vm.handleEnterFavoriteFolderDetail(folders[0])
      await flushPromises()
      await nextTick()

      expect(wrapper.vm.favoritesView).toBe('folder-detail')
      expect(s.spy).toHaveBeenCalledWith(0, 0)
      expect(window.scrollY).toBe(0)
    } finally {
      s.restore()
    }
  })

  it('切换 source（local）→ window.scrollTo(0, 0)', async () => {
    const wrapper = mountGallery()
    await flushPromises()

    const s = installScrollSpy()
    try {
      s.setScrollY(420)
      s.spy.mockClear()

      wrapper.vm.handleSourceChange('local')
      await flushPromises()

      expect(wrapper.vm.querySource).toBe('local')
      expect(s.spy).toHaveBeenCalledWith(0, 0)
      expect(window.scrollY).toBe(0)
    } finally {
      s.restore()
    }
  })

  it('切换 source（yande）→ window.scrollTo(0, 0)', async () => {
    const wrapper = mountGallery()
    await flushPromises()
    await enterFavorites(wrapper)

    const s = installScrollSpy()
    try {
      s.setScrollY(420)
      s.spy.mockClear()

      wrapper.vm.handleSourceChange('yande')
      await flushPromises()

      expect(wrapper.vm.querySource).toBe('yande')
      expect(s.spy).toHaveBeenCalledWith(0, 0)
      expect(window.scrollY).toBe(0)
    } finally {
      s.restore()
    }
  })

  it('新搜索结果集（handleSearch）→ window.scrollTo(0, 0)', async () => {
    const wrapper = mountGallery()
    await flushPromises()

    const s = installScrollSpy()
    try {
      s.setScrollY(420)
      s.spy.mockClear()

      await wrapper.vm.handleSearch({
        mode: 'local',
        params: { tags: 'landscape' },
        favorite: null,
      })
      await flushPromises()

      expect(s.spy).toHaveBeenCalledWith(0, 0)
      expect(window.scrollY).toBe(0)
    } finally {
      s.restore()
    }
  })

  it('二级页返回一级页 → 仍恢复进入前的 scrollTop（420），无回归', async () => {
    const folders = mkFolders(30)
    getAllFoldersMock.mockResolvedValue({ data: folders })

    const wrapper = mountGallery()
    await flushPromises()
    await enterFavorites(wrapper)

    const s = installScrollSpy()
    try {
      // 进入二级页前一级页停在 420
      s.setScrollY(420)
      s.spy.mockClear()

      wrapper.vm.handleFolderClick(folders[3])
      await flushPromises()
      expect(wrapper.vm.favoritesView).toBe('folder-detail')
      // 进入二级页 → 回顶
      expect(s.spy).toHaveBeenCalledWith(0, 0)

      s.spy.mockClear()
      wrapper.vm.handleBackToFolders()
      await flushPromises()
      await nextTick()
      await sleep(30)

      expect(wrapper.vm.favoritesView).toBe('folders')
      // 回到一级页 → 恢复进入前的像素位置
      expect(s.spy).toHaveBeenCalledWith(0, 420)
      expect(window.scrollY).toBe(420)
    } finally {
      s.restore()
    }
  })

  it('用户主动滚动（scroll 事件 isTrusted === true）→ 自动定位停止写回 scrollTo', async () => {
    const wrapper = mountGallery()
    await flushPromises()

    const s = installScrollSpy()
    try {
      // 触发一次自动定位（切 source → 回顶）。
      // 定位引擎现在是「一次性写入 + 偏差补写」：首次写入立即发生，
      // 之后只有在位置被外部改动且目标可达时才补写。
      wrapper.vm.handleSourceChange('favorites')
      await flushPromises()
      await sleep(200)

      const before = s.spy.mock.calls.length
      // 至少发生过一次写入（否则本用例无意义）
      expect(before).toBeGreaterThanOrEqual(1)
      expect(s.spy).toHaveBeenCalledWith(0, 0)

      // 用户主动滚动：happy-dom 的 Event 没有 isTrusted 实现，这里补一个 true
      const ev = new Event('scroll')
      Object.defineProperty(ev, 'isTrusted', { value: true })
      window.dispatchEvent(ev)
      // 用户的滚动位置必须被保留（不被自动定位拽回）
      s.setScrollY(260)

      await sleep(300)
      const after = s.spy.mock.calls.length
      // 用户接管后不再有任何新的 scrollTo 写回
      expect(after).toBe(before)
      expect(window.scrollY).toBe(260)
    } finally {
      s.restore()
    }
  })

  it('锚点可用（磁贴有布局信息）→ 返回一级页按锚点恢复，而不是按像素恢复', async () => {
    const folders = mkFolders(30)
    getAllFoldersMock.mockResolvedValue({ data: folders })

    const wrapper = mountGallery()
    await flushPromises()
    await enterFavorites(wrapper)

    // 进入时磁贴 top = 100（锚点 offset = 100）；返回时磁贴漂移到 top = 300
    const tileRect = { top: 100, height: 50 }
    const rectStub = stubTileRects(() => rect(tileRect.top, tileRect.height))
    const s = installScrollSpy()
    try {
      s.setScrollY(420)
      s.spy.mockClear()

      wrapper.vm.handleFolderClick(folders[3])
      await flushPromises()
      expect(wrapper.vm.favoritesView).toBe('folder-detail')

      // 二级页期间预览懒加载导致布局漂移
      tileRect.top = 300

      s.spy.mockClear()
      wrapper.vm.handleBackToFolders()
      await flushPromises()
      await nextTick()
      await sleep(30)

      // 锚点恢复：delta = 300 - 100 = 200，基准 scrollTop = 0（进入二级页时已回顶）
      expect(s.spy).toHaveBeenCalledWith(0, 200)
      // 走的是锚点分支，不应回退到像素恢复
      expect(s.spy).not.toHaveBeenCalledWith(0, 420)
    } finally {
      s.restore()
      rectStub.restore()
    }
  })

  it('锚点不可用（磁贴无布局信息 height === 0）→ 回退到像素恢复', async () => {
    const folders = mkFolders(30)
    getAllFoldersMock.mockResolvedValue({ data: folders })

    const wrapper = mountGallery()
    await flushPromises()
    await enterFavorites(wrapper)

    // 显式 stub 出「有元素但没有布局信息」：height === 0
    const rectStub = stubTileRects(() => rect(0, 0))
    const s = installScrollSpy()
    try {
      s.setScrollY(420)
      s.spy.mockClear()

      wrapper.vm.handleFolderClick(folders[3])
      await flushPromises()
      expect(wrapper.vm.favoritesView).toBe('folder-detail')

      s.spy.mockClear()
      wrapper.vm.handleBackToFolders()
      await flushPromises()
      await nextTick()
      await sleep(30)

      expect(wrapper.vm.favoritesView).toBe('folders')
      // 回退像素恢复 → 回到进入前的 420
      expect(s.spy).toHaveBeenCalledWith(0, 420)
      expect(window.scrollY).toBe(420)
    } finally {
      s.restore()
      rectStub.restore()
    }
  })
})

// =============================================================================
// 第二轮回归：「反复进出不同收藏夹，第二次进入某个收藏夹时，
// 向下滚动一点会突然触发回顶」
//
// 三个成因（生产代码已修）：
//   A. handleSearch 的回顶写在 await loadImages() 之后 → 迟到的回顶把当前视图拽回顶部
//   B. 循环中止判据只看"最近 300ms"→ 用户滚完停下后循环继续写 0
//   C. 只认 isTrusted → WebView 里用户滚动不被识别
// =============================================================================
describe('Gallery.vue 滚动位置策略 · 迟到的回顶与用户接管', () => {
  // happy-dom 的 Event 没有 isTrusted 实现，需要手动补一个 true
  const dispatchTrustedScroll = () => {
    const ev = new Event('scroll')
    Object.defineProperty(ev, 'isTrusted', { value: true })
    window.dispatchEvent(ev)
  }

  // 让 /gallery/load 挂起，由测试手动 resolve（模拟慢网络）
  const deferLoad = () => {
    let resolveLoad
    const promise = new Promise((res) => { resolveLoad = res })
    apiMock.post.mockImplementation(() => promise)
    return {
      resolve: (payload = { data: [], has_more: false }) => resolveLoad(payload),
    }
  }

  it('进入收藏夹后的搜索迟到 resolve → 不得把用户从当前位置拽回顶部', async () => {
    const folders = mkFolders(5)
    getAllFoldersMock.mockResolvedValue({ data: folders })

    const wrapper = mountGallery()
    await flushPromises()
    await enterFavorites(wrapper)

    const deferred = deferLoad()
    stubEmitSearchOnSelectFavorite = true
    const s = installScrollSpy()
    try {
      s.setScrollY(420)
      s.spy.mockClear()

      // 点开收藏夹 → 进入二级页 → 触发一次"慢搜索"
      wrapper.vm.handleFolderClick(folders[0])
      await flushPromises()
      expect(wrapper.vm.favoritesView).toBe('folder-detail')
      // 进入二级页时已回顶
      expect(s.spy).toHaveBeenCalledWith(0, 0)

      // 用户在二级页向下滚动
      s.setScrollY(300)
      dispatchTrustedScroll()

      s.spy.mockClear()
      // 慢搜索这时才回来
      deferred.resolve()
      await flushPromises()
      await sleep(60)

      // 迟到的结果不得再触发回顶，也不得改写用户的滚动位置
      expect(s.spy).not.toHaveBeenCalledWith(0, 0)
      expect(window.scrollY).toBe(300)
    } finally {
      s.restore()
      stubEmitSearchOnSelectFavorite = false
    }
  })

  it('反复进出不同收藏夹：A 的搜索迟到 resolve → 不得把 B 的当前位置拽回顶部', async () => {
    const folders = mkFolders(5)
    getAllFoldersMock.mockResolvedValue({ data: folders })

    const wrapper = mountGallery()
    await flushPromises()
    await enterFavorites(wrapper)

    const deferred = deferLoad()
    stubEmitSearchOnSelectFavorite = true
    const s = installScrollSpy()
    try {
      // 第一次进入收藏夹 A（搜索挂起）
      wrapper.vm.handleFolderClick(folders[0])
      await flushPromises()
      expect(wrapper.vm.favoritesView).toBe('folder-detail')

      // 返回一级页
      wrapper.vm.handleBackToFolders()
      await flushPromises()
      await nextTick()

      // 第二次进入收藏夹 B
      wrapper.vm.handleFolderClick(folders[1])
      await flushPromises()
      expect(wrapper.vm.favoritesView).toBe('folder-detail')

      // 用户在 B 里向下滚动
      s.setScrollY(280)
      dispatchTrustedScroll()

      s.spy.mockClear()
      // A 的慢搜索这时才回来（迟到的写回）
      deferred.resolve()
      await flushPromises()
      await sleep(60)

      expect(s.spy).not.toHaveBeenCalledWith(0, 0)
      expect(window.scrollY).toBe(280)
    } finally {
      s.restore()
      stubEmitSearchOnSelectFavorite = false
    }
  })

  it('用户滚动后，回顶写入循环立即停止（不再把用户拽回顶部）', async () => {
    const folders = mkFolders(5)
    getAllFoldersMock.mockResolvedValue({ data: folders })

    const wrapper = mountGallery()
    await flushPromises()
    await enterFavorites(wrapper)

    const s = installScrollSpy()
    try {
      // 触发一次回顶（进入收藏夹二级页）
      wrapper.vm.handleFolderClick(folders[0])
      await flushPromises()
      expect(s.spy).toHaveBeenCalledWith(0, 0)

      // 用户向下滚动
      s.setScrollY(350)
      dispatchTrustedScroll()

      s.spy.mockClear()
      // 等待超过稳定写入窗口（800ms）
      await sleep(900)

      // 循环必须已经停止，用户的位置没被覆盖
      expect(s.spy).not.toHaveBeenCalledWith(0, 0)
      expect(window.scrollY).toBe(350)
    } finally {
      s.restore()
    }
  })

  it('isTrusted 不可靠时（WebView）靠"位置被外部改动"兜底停止写回', async () => {
    const folders = mkFolders(5)
    getAllFoldersMock.mockResolvedValue({ data: folders })

    const wrapper = mountGallery()
    await flushPromises()
    await enterFavorites(wrapper)

    // 让目标位置"可达"（happy-dom 默认 scrollHeight = 0 → 会被判定为不可达）
    const docEl = document.documentElement
    const originalScrollHeight = Object.getOwnPropertyDescriptor(docEl, 'scrollHeight')
    Object.defineProperty(docEl, 'scrollHeight', {
      configurable: true,
      get: () => 5000,
    })

    const s = installScrollSpy()
    try {
      // 触发一次回顶
      wrapper.vm.handleFolderClick(folders[0])
      await flushPromises()
      expect(s.spy).toHaveBeenCalledWith(0, 0)

      // 模拟"浏览器没上报 isTrusted 的用户滚动"：只改位置，不派发事件
      s.setScrollY(260)

      s.spy.mockClear()
      await sleep(900)

      expect(s.spy).not.toHaveBeenCalledWith(0, 0)
      expect(window.scrollY).toBe(260)
    } finally {
      s.restore()
      if (originalScrollHeight) {
        Object.defineProperty(docEl, 'scrollHeight', originalScrollHeight)
      } else {
        delete docEl.scrollHeight
      }
    }
  })
})

// =============================================================================
// A 方案：返回一级页时列表"保持挂载"，不销毁重建
//
// 这是"闪一下"的根因修复：v-if/v-else 互斥渲染会让一级页整棵 DOM 被卸载，
// 返回时重建 → 每个 FolderTile 重新创建 → 组件内 srcEnabled 清空 →
// 预览图全部丢 src → 磁贴先空白再逐批重新出现（肉眼可见的闪）。
//
// 用 v-show 保持挂载后，组件实例（含 FolderTile 的 srcEnabled / 已加载的图片）
// 全程不变 → 不闪、列分布/高度也不变 → 恢复位置不会漂。
// =============================================================================
describe('Gallery.vue 返回一级页时列表保持挂载', () => {
  it('进入二级页再返回：一级列表的 WaterfallGallery / FolderTile 实例不重建', async () => {
    const folders = mkFolders(5)
    getAllFoldersMock.mockResolvedValue({ data: folders })

    const wrapper = mountGallery()
    await flushPromises()
    await enterFavorites(wrapper)

    const folderGalleryBefore = wrapper
      .findAllComponents({ name: 'WaterfallGallery' })
      .find((w) => w.props('itemType') === 'folder')
    const tileBefore = wrapper.findComponent({ name: 'FolderTile' })
    expect(folderGalleryBefore).toBeTruthy()
    expect(tileBefore.exists()).toBe(true)

    // 进入二级页
    wrapper.vm.handleFolderClick(folders[0])
    await flushPromises()
    expect(wrapper.vm.favoritesView).toBe('folder-detail')

    // 返回一级页
    wrapper.vm.handleBackToFolders()
    await flushPromises()
    await nextTick()

    expect(wrapper.vm.favoritesView).toBe('folders')

    // 关键断言：组件实例没有被销毁重建（否则预览图 src 会丢 → 闪一下）
    const folderGalleryAfter = wrapper
      .findAllComponents({ name: 'WaterfallGallery' })
      .find((w) => w.props('itemType') === 'folder')
    expect(folderGalleryAfter).toBeTruthy()
    expect(folderGalleryAfter.vm).toBe(folderGalleryBefore.vm)
    expect(wrapper.findComponent({ name: 'FolderTile' }).vm).toBe(tileBefore.vm)
  })

  it('返回一级页时不关闭高级面板（避免 collapse 高度动画把列表顶来顶去）', async () => {
    const folders = mkFolders(5)
    getAllFoldersMock.mockResolvedValue({ data: folders })

    const wrapper = mountGallery()
    await flushPromises()
    await enterFavorites(wrapper)

    const resetAdvancedPanelSpy = vi.fn()
    const resetParamsSpy = vi.fn()
    const advInstance = wrapper.findComponent({ name: 'AdvancedQuery' })
    advInstance.vm.__resetAdvancedPanel = resetAdvancedPanelSpy
    advInstance.vm.__resetAdvancedParamsNoClose = resetParamsSpy

    wrapper.vm.handleFolderClick(folders[0])
    await flushPromises()
    wrapper.vm.handleBackToFolders()
    await flushPromises()

    // 只重置参数，不关闭面板（关闭会触发 <el-collapse-transition> 高度动画）
    expect(resetParamsSpy).toHaveBeenCalled()
    expect(resetAdvancedPanelSpy).not.toHaveBeenCalled()
  })
})
