import { describe, it, expect, vi, beforeEach } from 'vitest'

// 每个 test 重新 import module，确保 module-scope refs 干净（vi.resetModules 清缓存）
// vi.mock 会被 vitest 自动 hoist 到文件顶部，对每次 await import() 生效

beforeEach(async () => {
  await vi.resetModules()
  localStorage.clear()
  // vi.resetModules 不清 spy 历史 — 必须 mockClear 避免跨测试累积断言干扰
  const mockedApi = (await import('@/api')).default
  vi.mocked(mockedApi.get).mockClear()
  vi.mocked(mockedApi.put).mockClear()
  const { myFavoritesApi } = await import('@/api/myFavorites')
  vi.mocked(myFavoritesApi.count).mockClear()
  const { recentDownloadsApi } = await import('@/api/recentDownloads')
  vi.mocked(recentDownloadsApi.getCount).mockClear()
  vi.mocked(recentDownloadsApi.clear).mockClear()
})

vi.mock('@/api', () => ({
  default: {
    get: vi.fn().mockRejectedValue(new Error('default mock — override per test')),
    put: vi.fn().mockResolvedValue({ data: {} }),
  },
}))

// myFavoritesApi 是独立的 API 封装模块（fix(hotfix-3) 后 fetchMyFavoritesCount 走它，
// 而不是 api.get('/my-favorites/count') 直接调用）— 单独 mock 让 spy 可追踪。
vi.mock('@/api/myFavorites', () => ({
  myFavoritesApi: {
    count: vi.fn().mockRejectedValue(new Error('default mock — override per test')),
  },
}))

// recentDownloadsApi 同理：最近下载角标 / 清除记录都走独立封装模块
vi.mock('@/api/recentDownloads', () => ({
  recentDownloadsApi: {
    getCount: vi.fn().mockRejectedValue(new Error('default mock — override per test')),
    clear: vi.fn().mockRejectedValue(new Error('default mock — override per test')),
  },
}))

describe('useFavoritesConfig — 4 新开关（brief Step 2 test 1）', () => {
  it('loads 4 new switches from /config/favorites', async () => {
    const api = (await import('@/api')).default
    vi.mocked(api.get).mockResolvedValueOnce({
      data: {
        enable_my_favorites: true,
        enable_random_browse: false,
        enable_favorite_folder: true,
        enable_favorite_autodownload: false,
      },
    })

    const { useFavoritesConfig } = await import('./useFavoritesConfig')
    const s = useFavoritesConfig()
    // 等待异步加载完成（microtask flush）
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(s.enableMyFavorites.value).toBe(true)
    expect(s.enableRandomBrowse.value).toBe(false)
    expect(s.enableFavoriteFolder.value).toBe(true)
    expect(s.enableFavoriteAutodownload.value).toBe(false)
    expect(api.get).toHaveBeenCalledWith('/config/favorites')
  })
})

describe('useFavoritesConfig — myFavoritesCount（brief Step 2 test 2）', () => {
  it('fetches myFavoritesCount when enable_my_favorites is true', async () => {
    const api = (await import('@/api')).default
    const { myFavoritesApi } = await import('@/api/myFavorites')
    vi.mocked(api.get).mockResolvedValueOnce({
      data: { enable_my_favorites: true },
    })
    vi.mocked(myFavoritesApi.count).mockResolvedValueOnce({ data: { count: 42 } })

    const { useFavoritesConfig } = await import('./useFavoritesConfig')
    const s = useFavoritesConfig()
    // 等待两次 microtask：1) config resolve 2) count resolve
    await new Promise(resolve => setTimeout(resolve, 10))

    expect(s.myFavoritesCount.value).toBe(42)
    expect(api.get).toHaveBeenCalledWith('/config/favorites')
    expect(myFavoritesApi.count).toHaveBeenCalled()
  })

  it('does not fetch myFavoritesCount when enable_my_favorites is false', async () => {
    const api = (await import('@/api')).default
    const { myFavoritesApi } = await import('@/api/myFavorites')
    vi.mocked(api.get).mockResolvedValueOnce({
      data: { enable_my_favorites: false },
    })

    const { useFavoritesConfig } = await import('./useFavoritesConfig')
    const s = useFavoritesConfig()
    await new Promise(resolve => setTimeout(resolve, 10))

    expect(s.enableMyFavorites.value).toBe(false)
    expect(s.myFavoritesCount.value).toBe(0)
    // count() 绝不应被触发
    expect(myFavoritesApi.count).not.toHaveBeenCalled()
  })
})

describe('useFavoritesConfig — saveFavoritesConfig（brief Step 2 test 3）', () => {
  it('saveFavoritesConfig syncs local state', async () => {
    const api = (await import('@/api')).default
    vi.mocked(api.put).mockResolvedValue({ data: {} })

    const { saveFavoritesConfig } = await import('./useFavoritesConfig')
    await saveFavoritesConfig({ enable_my_favorites: true })

    expect(api.put).toHaveBeenCalledWith('/config/favorites', { enable_my_favorites: true })
  })

  it('saveFavoritesConfig maps snake_case keys to local state refs', async () => {
    const api = (await import('@/api')).default
    vi.mocked(api.get).mockRejectedValue(new Error('no need to call'))
    vi.mocked(api.put).mockResolvedValue({ data: {} })

    const { useFavoritesConfig, saveFavoritesConfig } = await import('./useFavoritesConfig')
    const s = useFavoritesConfig()

    await saveFavoritesConfig({
      enable_my_favorites: true,
      enable_random_browse: true,
      enable_favorite_folder: false,
      enable_favorite_autodownload: false,
    })

    expect(s.enableMyFavorites.value).toBe(true)
    expect(s.enableRandomBrowse.value).toBe(true)
    expect(s.enableFavoriteFolder.value).toBe(false)
    expect(s.enableFavoriteAutodownload.value).toBe(false)
  })

  it('saveFavoritesConfig triggers fetchMyFavoritesCount when enabling', async () => {
    const { myFavoritesApi } = await import('@/api/myFavorites')
    vi.mocked(myFavoritesApi.count).mockResolvedValue({ data: { count: 7 } })

    const { useFavoritesConfig, saveFavoritesConfig } = await import('./useFavoritesConfig')
    const s = useFavoritesConfig()

    expect(s.myFavoritesCount.value).toBe(0)
    await saveFavoritesConfig({ enable_my_favorites: true })
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(s.myFavoritesCount.value).toBe(7)
    expect(myFavoritesApi.count).toHaveBeenCalled()
  })
})

// =============================================================================
// 最近下载开关 / 角标（设计文档 §4.1）
// =============================================================================
describe('useFavoritesConfig — enable_recent_downloads / recentDownloadsCount', () => {
  it('loads enable_recent_downloads from /config/favorites and fetches count when true', async () => {
    const api = (await import('@/api')).default
    const { recentDownloadsApi } = await import('@/api/recentDownloads')
    vi.mocked(api.get).mockResolvedValueOnce({
      data: { enable_recent_downloads: true },
    })
    vi.mocked(recentDownloadsApi.getCount).mockResolvedValueOnce({ data: { count: 55 } })

    const { useFavoritesConfig } = await import('./useFavoritesConfig')
    const s = useFavoritesConfig()
    await new Promise(resolve => setTimeout(resolve, 10))

    expect(s.enableRecentDownloads.value).toBe(true)
    expect(s.recentDownloadsCount.value).toBe(55)
    expect(recentDownloadsApi.getCount).toHaveBeenCalled()
  })

  it('does not fetch recentDownloadsCount when enable_recent_downloads is false', async () => {
    const api = (await import('@/api')).default
    const { recentDownloadsApi } = await import('@/api/recentDownloads')
    vi.mocked(api.get).mockResolvedValueOnce({
      data: { enable_recent_downloads: false },
    })

    const { useFavoritesConfig } = await import('./useFavoritesConfig')
    const s = useFavoritesConfig()
    await new Promise(resolve => setTimeout(resolve, 10))

    expect(s.enableRecentDownloads.value).toBe(false)
    expect(s.recentDownloadsCount.value).toBe(0)
    expect(recentDownloadsApi.getCount).not.toHaveBeenCalled()
  })

  it('saveFavoritesConfig syncs enable_recent_downloads and fetches the badge', async () => {
    const api = (await import('@/api')).default
    const { recentDownloadsApi } = await import('@/api/recentDownloads')
    vi.mocked(api.get).mockRejectedValue(new Error('no need to call'))
    vi.mocked(api.put).mockResolvedValue({ data: {} })
    vi.mocked(recentDownloadsApi.getCount).mockResolvedValue({ data: { count: 9 } })

    const { useFavoritesConfig, saveFavoritesConfig } = await import('./useFavoritesConfig')
    const s = useFavoritesConfig()
    expect(s.recentDownloadsCount.value).toBe(0)

    await saveFavoritesConfig({ enable_recent_downloads: true })
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(api.put).toHaveBeenCalledWith('/config/favorites', { enable_recent_downloads: true })
    expect(s.enableRecentDownloads.value).toBe(true)
    expect(s.recentDownloadsCount.value).toBe(9)
  })

  it('saveFavoritesConfig does NOT fetch the badge when disabling', async () => {
    const api = (await import('@/api')).default
    const { recentDownloadsApi } = await import('@/api/recentDownloads')
    vi.mocked(api.put).mockResolvedValue({ data: {} })

    const { useFavoritesConfig, saveFavoritesConfig } = await import('./useFavoritesConfig')
    const s = useFavoritesConfig()

    await saveFavoritesConfig({ enable_recent_downloads: false })
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(s.enableRecentDownloads.value).toBe(false)
    expect(recentDownloadsApi.getCount).not.toHaveBeenCalled()
  })

  it('fetchRecentDownloadsCount updates state and swallows network errors', async () => {
    const { recentDownloadsApi } = await import('@/api/recentDownloads')

    const { useFavoritesConfig, fetchRecentDownloadsCount } = await import('./useFavoritesConfig')
    const s = useFavoritesConfig()

    vi.mocked(recentDownloadsApi.getCount).mockResolvedValue({ data: { count: 123 } })
    await fetchRecentDownloadsCount()
    expect(s.recentDownloadsCount.value).toBe(123)

    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.mocked(recentDownloadsApi.getCount).mockRejectedValue(new Error('network down'))
    await expect(fetchRecentDownloadsCount()).resolves.toBeUndefined()
    expect(warnSpy).toHaveBeenCalled()
    warnSpy.mockRestore()
  })

  it('clearRecentDownloads posts the payload then refreshes the badge to 0', async () => {
    const { recentDownloadsApi } = await import('@/api/recentDownloads')

    const { useFavoritesConfig, clearRecentDownloads, fetchRecentDownloadsCount } = await import('./useFavoritesConfig')
    const s = useFavoritesConfig()

    // 先模拟「有历史记录」：角标 30
    vi.mocked(recentDownloadsApi.getCount).mockResolvedValue({ data: { count: 30 } })
    await fetchRecentDownloadsCount()
    expect(s.recentDownloadsCount.value).toBe(30)

    // 清除成功：后端返回删除条数，随后角标刷新为 0
    vi.mocked(recentDownloadsApi.clear).mockResolvedValue({ data: { deleted: 12 } })
    vi.mocked(recentDownloadsApi.getCount).mockResolvedValue({ data: { count: 0 } })

    const res = await clearRecentDownloads({ mode: 'before_days', days: 30 })

    expect(recentDownloadsApi.clear).toHaveBeenCalledWith({ mode: 'before_days', days: 30 })
    expect(res?.data?.deleted).toBe(12)
    expect(recentDownloadsApi.getCount).toHaveBeenCalled()
    expect(s.recentDownloadsCount.value).toBe(0)
  })

  it('clearRecentDownloads propagates API failure (caller shows the error)', async () => {
    const { recentDownloadsApi } = await import('@/api/recentDownloads')
    vi.mocked(recentDownloadsApi.clear).mockRejectedValue(new Error('boom'))

    const { clearRecentDownloads } = await import('./useFavoritesConfig')

    await expect(clearRecentDownloads({ mode: 'all' })).rejects.toThrow('boom')
    // 失败时不该刷新角标
    expect(recentDownloadsApi.getCount).not.toHaveBeenCalled()
  })
})

// =============================================================================
// 向后兼容：保留 5 个原有 ref（Config.spec.js / Gallery.spec.js 依赖）
// =============================================================================
describe('useFavoritesConfig — backward compatibility (5 legacy refs)', () => {
  it('exposes 5 legacy refs + 5 new refs + myFavoritesCount + recentDownloadsCount + loaded', async () => {
    const { useFavoritesConfig } = await import('./useFavoritesConfig')
    const s = useFavoritesConfig()

    expect(s).toHaveProperty('buttonMode')
    expect(s).toHaveProperty('tileSize')
    expect(s).toHaveProperty('previewOrder')
    expect(s).toHaveProperty('includeOnline')
    expect(s).toHaveProperty('folderPageSize')
    expect(s).toHaveProperty('enableMyFavorites')
    expect(s).toHaveProperty('enableRandomBrowse')
    expect(s).toHaveProperty('enableFavoriteFolder')
    expect(s).toHaveProperty('enableFavoriteAutodownload')
    expect(s).toHaveProperty('enableRecentDownloads')
    expect(s).toHaveProperty('myFavoritesCount')
    expect(s).toHaveProperty('recentDownloadsCount')
    expect(s).toHaveProperty('loaded')
  })

  it('reads legacy localStorage keys as fallback (one-shot)', async () => {
    localStorage.setItem('gallery_favorites_button_mode', 'hidden')
    localStorage.setItem('gallery_favorites_tile_size', '8')
    localStorage.setItem('gallery_favorites_preview_order', 'desc')
    localStorage.setItem('gallery_favorites_include_online', 'true')
    localStorage.setItem('favorites_folder_page_size', '12')

    const { useFavoritesConfig } = await import('./useFavoritesConfig')
    const s = useFavoritesConfig()

    // 后端 get 已被 default mock 拒绝 → 走 catch 分支，ref 保持 localStorage 兜底
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(s.buttonMode.value).toBe('hidden')
    expect(s.tileSize.value).toBe('8')
    expect(s.previewOrder.value).toBe('desc')
    expect(s.includeOnline.value).toBe(true)
    expect(s.folderPageSize.value).toBe(12)
  })

  it('writes back to localStorage on ref mutation (backward compat for Config.spec.js)', async () => {
    const { useFavoritesConfig } = await import('./useFavoritesConfig')
    const s = useFavoritesConfig()

    // 等 watcher 注册（首调同步完成）
    expect(s.loaded.value).toBe(true)

    s.buttonMode.value = 'default'
    s.tileSize.value = '6'
    s.includeOnline.value = true
    s.folderPageSize.value = 8

    // watch 是异步 flush（默认 flush: 'pre'），等 microtask
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(localStorage.getItem('gallery_favorites_button_mode')).toBe('default')
    expect(localStorage.getItem('gallery_favorites_tile_size')).toBe('6')
    expect(localStorage.getItem('gallery_favorites_include_online')).toBe('true')
    expect(localStorage.getItem('favorites_folder_page_size')).toBe('8')
  })

  it('singleton pattern: same refs across multiple calls', async () => {
    const { useFavoritesConfig } = await import('./useFavoritesConfig')
    const a = useFavoritesConfig()
    const b = useFavoritesConfig()

    // 同一组 ref 对象（=== 同一引用）
    expect(a.buttonMode).toBe(b.buttonMode)
    expect(a.enableMyFavorites).toBe(b.enableMyFavorites)
    expect(a.myFavoritesCount).toBe(b.myFavoritesCount)

    // 跨调用修改立即可见
    a.tileSize.value = '8'
    expect(b.tileSize.value).toBe('8')
  })

  it('skips api.get on subsequent calls (loaded flag guard)', async () => {
    const api = (await import('@/api')).default
    vi.mocked(api.get).mockResolvedValue({
      data: { enable_my_favorites: true },
    })

    const { useFavoritesConfig } = await import('./useFavoritesConfig')
    useFavoritesConfig()
    await new Promise(resolve => setTimeout(resolve, 0))

    // 第二次调用 — 不应再发 GET /config/favorites
    useFavoritesConfig()
    await new Promise(resolve => setTimeout(resolve, 0))

    const configCalls = vi.mocked(api.get).mock.calls.filter(
      (c) => c[0] === '/config/favorites'
    )
    expect(configCalls.length).toBe(1)
  })

  it('defensive load: backend response missing button_mode does NOT corrupt existing values', async () => {
    localStorage.setItem('gallery_favorites_button_mode', 'default')

    const api = (await import('@/api')).default
    // 模拟后端响应中缺少 button_mode 等字段（Config.spec.js 全局 mock 就是这种 shape）
    vi.mocked(api.get).mockResolvedValue({
      data: {
        yande_api: { retry: 3 },
        downloader: { thread_num: 4 },
      },
    })

    const { useFavoritesConfig } = await import('./useFavoritesConfig')
    const s = useFavoritesConfig()
    await new Promise(resolve => setTimeout(resolve, 0))

    // button_mode 字段缺失 → 不覆盖 → 保持 localStorage 兜底 'default'
    expect(s.buttonMode.value).toBe('default')
    // 其他可能的开关字段也不应被错误赋值
    expect(typeof s.enableMyFavorites.value).toBe('boolean')
  })
})

describe('useFavoritesConfig — fetchMyFavoritesCount exported helper', () => {
  it('fetchMyFavoritesCount handles network error silently', async () => {
    const { myFavoritesApi } = await import('@/api/myFavorites')
    vi.mocked(myFavoritesApi.count).mockRejectedValue(new Error('network down'))
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const { fetchMyFavoritesCount } = await import('./useFavoritesConfig')
    await fetchMyFavoritesCount()  // 不应抛

    expect(warnSpy).toHaveBeenCalled()
    warnSpy.mockRestore()
  })

  it('fetchMyFavoritesCount updates state.myFavoritesCount on success', async () => {
    const { myFavoritesApi } = await import('@/api/myFavorites')
    vi.mocked(myFavoritesApi.count).mockResolvedValue({ data: { count: 100 } })

    const { useFavoritesConfig, fetchMyFavoritesCount } = await import('./useFavoritesConfig')
    const s = useFavoritesConfig()

    await fetchMyFavoritesCount()
    expect(s.myFavoritesCount.value).toBe(100)
  })
})

// =============================================================================
// whenFavoritesConfigReady — 首屏配置等待契约
// =============================================================================
// 背景：enableMyFavorites 等 4 个开关只持久化在后端，localStorage 不含它们。
//   Gallery 首屏 /gallery/load 需要携带与后端一致的 include_favorite_status，
//   否则「刷新页面（配置未到 → 不带参）」与「点击 tab（配置已到 → 带参）」不一致。
//   本契约保证：
//   1. 首次 GET /config/favorites 落定后 Promise resolve，且 refs 已应用配置
//   2. 请求失败同样 resolve（后端不可达不阻塞首屏）
//   3. 从未调用 useFavoritesConfig() 时立即 resolve（不悬挂）
// =============================================================================
describe('useFavoritesConfig — whenFavoritesConfigReady（首屏配置等待契约）', () => {
  it('首次 GET /config/favorites 落定后才 resolve，且 refs 已应用配置', async () => {
    const api = (await import('@/api')).default
    let resolveConfig
    vi.mocked(api.get).mockImplementationOnce(() => new Promise((r) => { resolveConfig = r }))

    const { useFavoritesConfig, whenFavoritesConfigReady } = await import('./useFavoritesConfig')
    const s = useFavoritesConfig()

    let ready = false
    whenFavoritesConfigReady().then(() => { ready = true })
    await new Promise((r) => setTimeout(r, 0))
    // 配置未落定 → 不应 resolve
    expect(ready).toBe(false)
    expect(s.enableMyFavorites.value).toBe(false)

    resolveConfig({ data: { enable_my_favorites: true } })
    await new Promise((r) => setTimeout(r, 0))
    expect(ready).toBe(true)
    expect(s.enableMyFavorites.value).toBe(true)
  })

  it('配置请求失败时同样 resolve（不阻塞首屏）', async () => {
    const api = (await import('@/api')).default
    vi.mocked(api.get).mockRejectedValueOnce(new Error('network down'))
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const { useFavoritesConfig, whenFavoritesConfigReady } = await import('./useFavoritesConfig')
    useFavoritesConfig()

    await expect(whenFavoritesConfigReady()).resolves.toBeUndefined()
    warnSpy.mockRestore()
  })

  it('从未调用 useFavoritesConfig() 时立即 resolve（不悬挂）', async () => {
    const { whenFavoritesConfigReady } = await import('./useFavoritesConfig')
    await expect(whenFavoritesConfigReady()).resolves.toBeUndefined()
  })
})
