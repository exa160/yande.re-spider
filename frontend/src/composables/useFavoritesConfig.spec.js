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
})

vi.mock('@/api', () => ({
  default: {
    get: vi.fn().mockRejectedValue(new Error('default mock — override per test')),
    put: vi.fn().mockResolvedValue({ data: {} }),
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
    vi.mocked(api.get).mockImplementation((url) => {
      if (url === '/config/favorites') {
        return Promise.resolve({ data: { enable_my_favorites: true } })
      }
      if (url === '/my-favorites/count') {
        return Promise.resolve({ data: { count: 42 } })
      }
      return Promise.reject(new Error('not mocked'))
    })

    const { useFavoritesConfig } = await import('./useFavoritesConfig')
    const s = useFavoritesConfig()
    // 等待两次 microtask：1) config resolve 2) count resolve
    await new Promise(resolve => setTimeout(resolve, 10))

    expect(s.myFavoritesCount.value).toBe(42)
    expect(api.get).toHaveBeenCalledWith('/config/favorites')
    expect(api.get).toHaveBeenCalledWith('/my-favorites/count')
  })

  it('does not fetch myFavoritesCount when enable_my_favorites is false', async () => {
    const api = (await import('@/api')).default
    vi.mocked(api.get).mockImplementation((url) => {
      if (url === '/config/favorites') {
        return Promise.resolve({ data: { enable_my_favorites: false } })
      }
      if (url === '/my-favorites/count') {
        return Promise.reject(new Error('should NOT be called when switch off'))
      }
      return Promise.reject(new Error('not mocked'))
    })

    const { useFavoritesConfig } = await import('./useFavoritesConfig')
    const s = useFavoritesConfig()
    await new Promise(resolve => setTimeout(resolve, 10))

    expect(s.enableMyFavorites.value).toBe(false)
    expect(s.myFavoritesCount.value).toBe(0)
    // /my-favorites/count 绝不应被触发
    expect(api.get).not.toHaveBeenCalledWith('/my-favorites/count')
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
    const api = (await import('@/api')).default
    vi.mocked(api.get).mockImplementation((url) => {
      if (url === '/my-favorites/count') {
        return Promise.resolve({ data: { count: 7 } })
      }
      return Promise.reject(new Error('not mocked'))
    })
    vi.mocked(api.put).mockResolvedValue({ data: {} })

    const { useFavoritesConfig, saveFavoritesConfig } = await import('./useFavoritesConfig')
    const s = useFavoritesConfig()

    expect(s.myFavoritesCount.value).toBe(0)
    await saveFavoritesConfig({ enable_my_favorites: true })
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(s.myFavoritesCount.value).toBe(7)
    expect(api.get).toHaveBeenCalledWith('/my-favorites/count')
  })
})

// =============================================================================
// 向后兼容：保留 5 个原有 ref（Config.spec.js / Gallery.spec.js 依赖）
// =============================================================================
describe('useFavoritesConfig — backward compatibility (5 legacy refs)', () => {
  it('exposes 5 legacy refs + 4 new refs + myFavoritesCount + loaded', async () => {
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
    expect(s).toHaveProperty('myFavoritesCount')
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
    const api = (await import('@/api')).default
    vi.mocked(api.get).mockRejectedValue(new Error('network down'))
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const { fetchMyFavoritesCount } = await import('./useFavoritesConfig')
    await fetchMyFavoritesCount()  // 不应抛

    expect(warnSpy).toHaveBeenCalled()
    warnSpy.mockRestore()
  })

  it('fetchMyFavoritesCount updates state.myFavoritesCount on success', async () => {
    const api = (await import('@/api')).default
    vi.mocked(api.get).mockResolvedValue({ data: { count: 100 } })

    const { useFavoritesConfig, fetchMyFavoritesCount } = await import('./useFavoritesConfig')
    const s = useFavoritesConfig()

    await fetchMyFavoritesCount()
    expect(s.myFavoritesCount.value).toBe(100)
  })
})
