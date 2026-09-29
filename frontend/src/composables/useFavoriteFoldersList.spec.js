/**
 * useFavoriteFoldersList.js — 虚拟磁贴 prepend 行为测试
 *
 * 覆盖：
 * 1. 虚拟磁贴（我的最爱 / 随机浏览）prepend 到真实 folders 前
 * 2. 我的最爱预览图通过 myFavoritesApi.getPreview 拉取
 * 3. 随机浏览预览图通过 randomBrowseApi.getPreview 拉取（修复问题 11）
 * 4. 开关关闭时不拉取预览图、保持空数组
 * 5. 随机浏览的 preview_images 字段绑定到 randomBrowsePreview（而非硬编码空数组）
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

import { myFavoritesApi } from '@/api/myFavorites'
import { randomBrowseApi } from '@/api/randomBrowse'
import { useFavoritesConfig } from '@/composables/useFavoritesConfig'
import { useFavoriteFoldersList } from '@/composables/useFavoriteFoldersList'

beforeEach(() => {
  // 重置 singleton state 到默认值（避免跨测试污染）
  const cfg = useFavoritesConfig()
  cfg.enableMyFavorites.value = false
  cfg.enableRandomBrowse.value = false
  cfg.myFavoritesCount.value = 0
  cfg.randomBrowseCount.value = 0
  cfg.tileSize.value = 'adaptive'

  // 重置 mock implementation + 清空调用记录（mockReset 替代 mockClear，
  // 避免 spy 跨测试累积时计数偏差）
  vi.mocked(myFavoritesApi.getPreview).mockReset()
  vi.mocked(myFavoritesApi.getPreview).mockResolvedValue({ data: { images: [] } })
  vi.mocked(randomBrowseApi.getPreview).mockReset()
  vi.mocked(randomBrowseApi.getPreview).mockResolvedValue({ data: { images: [] } })
  vi.mocked(randomBrowseApi.getCount).mockReset()
  vi.mocked(randomBrowseApi.getCount).mockResolvedValue({ data: { count: 0 } })
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