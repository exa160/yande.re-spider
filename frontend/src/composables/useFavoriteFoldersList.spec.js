/**
 * useFavoriteFoldersList.js — 虚拟磁贴 prepend 行为测试
 *
 * 覆盖：
 * 1. 虚拟磁贴（我的最爱 / 随机浏览 / 最近下载）prepend 到真实 folders 前
 * 2. 我的最爱预览图通过 myFavoritesApi.getPreview 拉取
 * 3. 随机浏览预览图通过 randomBrowseApi.getPreview 拉取（修复问题 11）
 * 4. 开关关闭时不拉取预览图、保持空数组
 * 5. 随机浏览的 preview_images 字段绑定到 randomBrowsePreview（而非硬编码空数组）
 * 6. 最近下载：第三个磁贴（顺序固定在末尾）、预览图、角标（设计文档 §2.2 / §4.3）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

vi.mock('@/api/myFavorites', () => ({
  myFavoritesApi: {
    getPreview: vi.fn().mockResolvedValue({ data: { images: [] } }),
  },
}))
vi.mock('@/api/randomBrowse', () => ({
  randomBrowseApi: {
    getPreview: vi.fn().mockResolvedValue({ data: { images: [] } }),
    getCount: vi.fn().mockResolvedValue({ data: { count: 0 } }),
  },
}))
vi.mock('@/api/recentDownloads', () => ({
  recentDownloadsApi: {
    getPreview: vi.fn().mockResolvedValue({ data: { images: [] } }),
    getCount: vi.fn().mockResolvedValue({ data: { count: 0 } }),
    clear: vi.fn().mockResolvedValue({ data: { deleted: 0 } }),
  },
}))

import { myFavoritesApi } from '@/api/myFavorites'
import { randomBrowseApi } from '@/api/randomBrowse'
import { recentDownloadsApi } from '@/api/recentDownloads'
import { useFavoritesConfig } from '@/composables/useFavoritesConfig'
import { useFavoriteFoldersList } from '@/composables/useFavoriteFoldersList'

beforeEach(() => {
  // 重置 singleton state 到默认值（避免跨测试污染）
  const cfg = useFavoritesConfig()
  cfg.enableMyFavorites.value = false
  cfg.enableRandomBrowse.value = false
  cfg.enableRecentDownloads.value = false
  cfg.myFavoritesCount.value = 0
  cfg.randomBrowseCount.value = 0
  cfg.recentDownloadsCount.value = 0
  cfg.tileSize.value = 'adaptive'

  // 重置 mock implementation + 清空调用记录（mockReset 替代 mockClear，
  // 避免 spy 跨测试累积时计数偏差）
  vi.mocked(myFavoritesApi.getPreview).mockReset()
  vi.mocked(myFavoritesApi.getPreview).mockResolvedValue({ data: { images: [] } })
  vi.mocked(randomBrowseApi.getPreview).mockReset()
  vi.mocked(randomBrowseApi.getPreview).mockResolvedValue({ data: { images: [] } })
  vi.mocked(randomBrowseApi.getCount).mockReset()
  vi.mocked(randomBrowseApi.getCount).mockResolvedValue({ data: { count: 0 } })
  vi.mocked(recentDownloadsApi.getPreview).mockReset()
  vi.mocked(recentDownloadsApi.getPreview).mockResolvedValue({ data: { images: [] } })
  vi.mocked(recentDownloadsApi.getCount).mockReset()
  vi.mocked(recentDownloadsApi.getCount).mockResolvedValue({ data: { count: 0 } })
})

describe('useFavoriteFoldersList — 虚拟磁贴 + 预览图加载', () => {
  it('enableMyFavorites=true → virtualTiles 包含「我的最爱」（preview_images 来自 myFavoritesPreview）', async () => {
    const cfg = useFavoritesConfig()
    cfg.enableMyFavorites.value = true
    cfg.myFavoritesCount.value = 42
    vi.mocked(myFavoritesApi.getPreview).mockResolvedValue({
      data: { images: [{ id: 1 }, { id: 2 }] },
    })

    const realFolders = ref([])
    const page = ref(1)
    const { displayFolders, myFavoritesPreview } = useFavoriteFoldersList({
      realFolders,
      page,
      fetchPreview: true,
    })

    // wait microtasks
    await new Promise((r) => setTimeout(r, 0))

    const myFav = displayFolders.value.find((f) => f.id === 'my-favorites')
    expect(myFav).toBeTruthy()
    expect(myFav.local_count).toBe(42)
    expect(myFav.preview_images).toEqual([{ id: 1 }, { id: 2 }])
    expect(myFavoritesPreview.value).toEqual([{ id: 1 }, { id: 2 }])
  })

  it('enableRandomBrowse=true → virtualTiles 包含「随机浏览」（preview_images 来自 randomBrowsePreview，修复问题 11）', async () => {
    const cfg = useFavoritesConfig()
    cfg.enableRandomBrowse.value = true
    vi.mocked(randomBrowseApi.getPreview).mockResolvedValue({
      data: { images: [{ id: 100 }, { id: 101 }, { id: 102 }] },
    })

    const realFolders = ref([])
    const page = ref(1)
    const { displayFolders, randomBrowsePreview } = useFavoriteFoldersList({
      realFolders,
      page,
      fetchPreview: true,
    })

    await new Promise((r) => setTimeout(r, 0))

    const random = displayFolders.value.find((f) => f.id === 'random')
    expect(random).toBeTruthy()
    // 关键断言（修复问题 11）：随机浏览磁贴的 preview_images 来自 randomBrowsePreview
    expect(random.preview_images).toEqual([{ id: 100 }, { id: 101 }, { id: 102 }])
    expect(randomBrowsePreview.value).toEqual([{ id: 100 }, { id: 101 }, { id: 102 }])
    // 调用了 randomBrowseApi.getPreview（之前是硬编码空数组，未调 API）
    expect(randomBrowseApi.getPreview).toHaveBeenCalled()
  })

  it('enableRandomBrowse=false → 随机浏览预览图不加载（开关关闭）', async () => {
    const cfg = useFavoritesConfig()
    cfg.enableRandomBrowse.value = false

    const realFolders = ref([])
    const page = ref(1)
    const { displayFolders, randomBrowsePreview } = useFavoriteFoldersList({
      realFolders,
      page,
      fetchPreview: true,
    })

    await new Promise((r) => setTimeout(r, 0))

    expect(displayFolders.value.find((f) => f.id === 'random')).toBeUndefined()
    expect(randomBrowsePreview.value).toEqual([])
    // 开关关闭时不调 API
    expect(randomBrowseApi.getPreview).not.toHaveBeenCalled()
  })

  it('fetchPreview=false（FavoritePanel 场景）→ 不调 randomBrowseApi.getPreview', async () => {
    const cfg = useFavoritesConfig()
    cfg.enableRandomBrowse.value = true

    const realFolders = ref([])
    const page = ref(1)
    const { displayFolders, randomBrowsePreview } = useFavoriteFoldersList({
      realFolders,
      page,
      fetchPreview: false,  // FavoritePanel 场景：不拉预览
    })

    await new Promise((r) => setTimeout(r, 0))

    // 验证 1：randomBrowsePreview 始终为空数组（fetchPreview=false 时不加载）
    expect(randomBrowsePreview.value).toEqual([])
    // 验证 2：随机浏览磁贴仍存在（FavoritePanel 也显示虚拟磁贴）
    const random = displayFolders.value.find((f) => f.id === 'random')
    expect(random).toBeTruthy()
    expect(random.preview_images).toEqual([])
  })

  it('tileSize 变化时重新加载随机浏览预览图（limit 跟随 tileSize）', async () => {
    const cfg = useFavoritesConfig()
    cfg.enableRandomBrowse.value = true
    cfg.tileSize.value = 'large'  // PREVIEW_COUNT_FOR_TILE_SIZE.large = 8

    const realFolders = ref([])
    const page = ref(1)
    useFavoriteFoldersList({
      realFolders,
      page,
      fetchPreview: true,
    })

    await new Promise((r) => setTimeout(r, 0))

    expect(randomBrowseApi.getPreview).toHaveBeenCalledWith(8)
  })

  it('randomBrowseApi.getPreview 失败时 randomBrowsePreview 保持空数组（防降级）', async () => {
    const cfg = useFavoritesConfig()
    cfg.enableRandomBrowse.value = true
    vi.mocked(randomBrowseApi.getPreview).mockRejectedValue(new Error('API 500'))

    const realFolders = ref([])
    const page = ref(1)
    const { randomBrowsePreview, displayFolders } = useFavoriteFoldersList({
      realFolders,
      page,
      fetchPreview: true,
    })

    await new Promise((r) => setTimeout(r, 0))

    expect(randomBrowsePreview.value).toEqual([])
    // 磁贴仍可见，只是没缩略图
    const random = displayFolders.value.find((f) => f.id === 'random')
    expect(random).toBeTruthy()
    expect(random.preview_images).toEqual([])
  })

  it('随机浏览角标 = 本地已下载图片总数（getCount），不再是固定 0', async () => {
    const cfg = useFavoritesConfig()
    cfg.enableRandomBrowse.value = true
    vi.mocked(randomBrowseApi.getCount).mockResolvedValue({ data: { count: 12345 } })

    const realFolders = ref([])
    const page = ref(1)
    const { displayFolders } = useFavoriteFoldersList({
      realFolders,
      page,
      fetchPreview: true,
    })

    await new Promise((r) => setTimeout(r, 0))

    const random = displayFolders.value.find((f) => f.id === 'random')
    expect(random.local_count).toBe(12345)
    expect(cfg.randomBrowseCount.value).toBe(12345)
  })

  it('随机浏览角标在 fetchPreview=false（FavoritePanel）时也会拉取', async () => {
    const cfg = useFavoritesConfig()
    cfg.enableRandomBrowse.value = true
    vi.mocked(randomBrowseApi.getCount).mockResolvedValue({ data: { count: 777 } })

    const realFolders = ref([])
    const page = ref(1)
    const { displayFolders } = useFavoriteFoldersList({
      realFolders,
      page,
      fetchPreview: false,
    })

    await new Promise((r) => setTimeout(r, 0))

    const random = displayFolders.value.find((f) => f.id === 'random')
    expect(random.local_count).toBe(777)
  })
})

// =============================================================================
// 最近下载磁贴（第三个虚拟磁贴）— 设计文档 §2.2 磁贴顺序 / §2.3 角标口径 / §4.3
// =============================================================================
describe('useFavoriteFoldersList — 最近下载虚拟磁贴', () => {
  const mountList = (fetchPreview = true) => {
    const realFolders = ref([])
    const page = ref(1)
    return useFavoriteFoldersList({ realFolders, page, fetchPreview })
  }

  it('三个开关各自控制磁贴出现（我的最爱 / 随机浏览 / 最近下载）', async () => {
    const cfg = useFavoritesConfig()

    // 全关 → 没有任何虚拟磁贴
    let list = mountList()
    await new Promise((r) => setTimeout(r, 0))
    expect(list.displayFolders.value).toEqual([])

    // 只开「我的最爱」
    cfg.enableMyFavorites.value = true
    await new Promise((r) => setTimeout(r, 0))
    expect(list.displayFolders.value.map((f) => f.id)).toEqual(['my-favorites'])

    // 只开「随机浏览」（关掉我的最爱）
    cfg.enableMyFavorites.value = false
    cfg.enableRandomBrowse.value = true
    await new Promise((r) => setTimeout(r, 0))
    expect(list.displayFolders.value.map((f) => f.id)).toEqual(['random'])

    // 只开「最近下载」
    cfg.enableRandomBrowse.value = false
    cfg.enableRecentDownloads.value = true
    await new Promise((r) => setTimeout(r, 0))
    expect(list.displayFolders.value.map((f) => f.id)).toEqual(['recent-downloads'])
  })

  it('磁贴顺序固定：我的最爱 → 随机浏览 → 最近下载（最近下载在末尾）', async () => {
    const cfg = useFavoritesConfig()
    cfg.enableMyFavorites.value = true
    cfg.enableRandomBrowse.value = true
    cfg.enableRecentDownloads.value = true

    const { displayFolders } = mountList()
    await new Promise((r) => setTimeout(r, 0))

    expect(displayFolders.value.map((f) => f.id)).toEqual([
      'my-favorites',
      'random',
      'recent-downloads',
    ])
  })

  it('开关顺序打乱也不会改变磁贴顺序（顺序由 virtualTiles push 位置决定）', async () => {
    const cfg = useFavoritesConfig()
    // 先开最近下载，后开我的最爱
    cfg.enableRecentDownloads.value = true
    await new Promise((r) => setTimeout(r, 0))
    cfg.enableMyFavorites.value = true
    await new Promise((r) => setTimeout(r, 0))

    const { displayFolders } = mountList()
    await new Promise((r) => setTimeout(r, 0))

    expect(displayFolders.value.map((f) => f.id)).toEqual(['my-favorites', 'recent-downloads'])
  })

  it('最近下载磁贴 name/isVirtual/local_count 符合契约', async () => {
    const cfg = useFavoritesConfig()
    cfg.enableRecentDownloads.value = true
    cfg.recentDownloadsCount.value = 88

    const { displayFolders } = mountList()
    await new Promise((r) => setTimeout(r, 0))

    const tile = displayFolders.value.find((f) => f.id === 'recent-downloads')
    expect(tile).toBeTruthy()
    expect(tile.name).toBe('最近下载')
    expect(tile.isVirtual).toBe(true)
    expect(tile.local_count).toBe(88)
  })

  it('enableRecentDownloads=true → 预览图通过 recentDownloadsApi.getPreview 拉取', async () => {
    const cfg = useFavoritesConfig()
    cfg.enableRecentDownloads.value = true
    vi.mocked(recentDownloadsApi.getPreview).mockResolvedValue({
      data: { images: [{ id: 900 }, { id: 901 }] },
    })

    const { displayFolders, recentDownloadsPreview } = mountList()
    await new Promise((r) => setTimeout(r, 0))

    const tile = displayFolders.value.find((f) => f.id === 'recent-downloads')
    expect(tile.preview_images).toEqual([{ id: 900 }, { id: 901 }])
    expect(recentDownloadsPreview.value).toEqual([{ id: 900 }, { id: 901 }])
    expect(recentDownloadsApi.getPreview).toHaveBeenCalled()
  })

  it('enableRecentDownloads=false → 不拉预览图且 recentDownloadsPreview 为空', async () => {
    const { displayFolders, recentDownloadsPreview } = mountList()
    await new Promise((r) => setTimeout(r, 0))

    expect(displayFolders.value.find((f) => f.id === 'recent-downloads')).toBeUndefined()
    expect(recentDownloadsPreview.value).toEqual([])
    // 开关关闭时本实例不会拉预览（历史实例的调用在 beforeEach 的 mockReset 中清掉）
    expect(recentDownloadsApi.getPreview).not.toHaveBeenCalled()
  })

  it('fetchPreview=false（FavoritePanel 场景）→ 磁贴仍在但 preview_images 为空', async () => {
    const cfg = useFavoritesConfig()
    cfg.enableRecentDownloads.value = true
    // 本文件里 useFavoriteFoldersList 的 watch 注册在测试作用域（不会被卸载），
    // 之前用例里 fetchPreview=true 的实例在开关翻转时也会拉预览。
    // 因此先让这些历史 watcher flush 完并清零调用记录，再挂载「不拉预览」的实例，
    // 这样断言只覆盖本实例的行为。
    await new Promise((r) => setTimeout(r, 0))
    vi.mocked(recentDownloadsApi.getPreview).mockClear()

    const { displayFolders, recentDownloadsPreview } = mountList(false)
    await new Promise((r) => setTimeout(r, 0))

    const tile = displayFolders.value.find((f) => f.id === 'recent-downloads')
    expect(tile).toBeTruthy()
    expect(tile.preview_images).toEqual([])
    expect(recentDownloadsPreview.value).toEqual([])
    expect(recentDownloadsApi.getPreview).not.toHaveBeenCalled()
  })

  it('recentDownloadsApi.getPreview 失败时保持空数组（防降级，磁贴仍可见）', async () => {
    const cfg = useFavoritesConfig()
    cfg.enableRecentDownloads.value = true
    vi.mocked(recentDownloadsApi.getPreview).mockRejectedValue(new Error('API 500'))

    const { displayFolders, recentDownloadsPreview } = mountList()
    await new Promise((r) => setTimeout(r, 0))

    expect(recentDownloadsPreview.value).toEqual([])
    const tile = displayFolders.value.find((f) => f.id === 'recent-downloads')
    expect(tile).toBeTruthy()
    expect(tile.preview_images).toEqual([])
  })

  it('最近下载角标 = getCount 的去重图片数（fetchPreview=false 时也拉）', async () => {
    const cfg = useFavoritesConfig()
    cfg.enableRecentDownloads.value = true
    vi.mocked(recentDownloadsApi.getCount).mockResolvedValue({ data: { count: 321 } })

    const { displayFolders } = mountList(false)
    await new Promise((r) => setTimeout(r, 0))

    const tile = displayFolders.value.find((f) => f.id === 'recent-downloads')
    expect(tile.local_count).toBe(321)
    expect(cfg.recentDownloadsCount.value).toBe(321)
  })

  it('page>1 时虚拟磁贴仍置顶常驻（含最近下载）', async () => {
    // 回归测试（2026-10-01）：收藏夹是真分页（loadFolders 用第 N 页整体替换
    // currentFolders），旧实现按 page===1 条件 prepend，导致用户向下翻页后
    // 三个虚拟磁贴整体消失。现改为无条件 prepend，磁贴应始终置顶。
    const cfg = useFavoritesConfig()
    cfg.enableMyFavorites.value = true
    cfg.enableRandomBrowse.value = true
    cfg.enableRecentDownloads.value = true

    const realFolders = ref([{ id: 7, name: '真实收藏夹' }])
    const page = ref(1)
    const { displayFolders } = useFavoriteFoldersList({ realFolders, page, fetchPreview: true })
    await new Promise((r) => setTimeout(r, 0))
    expect(displayFolders.value.length).toBe(4)

    // 翻到第 2 页：真实列表被整体替换，虚拟磁贴必须依然在最前
    realFolders.value = [{ id: 8, name: '第二页收藏夹' }]
    page.value = 2
    await new Promise((r) => setTimeout(r, 0))
    expect(displayFolders.value.map((f) => f.id)).toEqual([
      'my-favorites',
      'random',
      'recent-downloads',
      8,
    ])
  })
})