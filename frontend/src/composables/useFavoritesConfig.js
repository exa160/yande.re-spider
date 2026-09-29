/**
 * 收藏夹 UI 配置 + 我的最爱/随机浏览总开关（singleton composable）
 *
 * - module-level refs → 跨组件共享（任何地方 useFavoritesConfig() 都返回同一组 ref）
 * - 每次调用都从 localStorage legacy key 重读 5 个 UI 偏好（保证刷新即拿到上次的设置）
 * - 首次调用额外异步拉取后端 GET /config/favorites（成功则覆盖 LS 兜底；字段缺失则保留 LS 值）
 * - 5 个 UI 偏好的写回：ref → watch → localStorage（向后兼容；不依赖后端 100% 可达）
 * - 4 个开关 + myFavoritesCount：saveFavoritesConfig() 走 PUT /config/favorites 后端持久化
 *   fetchMyFavoritesCount() 在 enable_my_favorites=true 时拉取总数
 *
 * 后端字段（snake_case）：
 *   button_mode | tile_size | preview_order | include_online | folder_page_size
 *   enable_my_favorites | enable_random_browse | enable_favorite_folder | enable_favorite_autodownload
 *
 * localStorage keys（向后兼容 legacy UI 偏好）：
 *   gallery_favorites_button_mode    : 'hidden' | 'shown' | 'default'
 *   gallery_favorites_tile_size      : 'adaptive' | '4' | '6' | '8'
 *   gallery_favorites_preview_order  : 'random' | 'asc' | 'desc'
 *   gallery_favorites_include_online : 'true' | 'false'
 *   favorites_folder_page_size       : 数字字符串
 */
import { ref, watch } from 'vue'
import api from '@/api'
import { myFavoritesApi } from '@/api/myFavorites'
import { randomBrowseApi } from '@/api/randomBrowse'

/**
 * @typedef {import('vue').Ref} Ref
 */

// 合法值白名单（防御性：localStorage 可能被外部篡改；后端响应同样校验）
const VALID_BUTTON_MODES = ['hidden', 'shown', 'default']
const VALID_TILE_SIZES = ['adaptive', '4', '6', '8']
const VALID_PREVIEW_ORDERS = ['random', 'asc', 'desc']
const VALID_FOLDER_PAGE_SIZES = [8, 12, 20]

// 模块级状态（singleton）：所有调用共享同一组 ref
const state = {
  // 5 个原有 UI 偏好（必须保留 — Config.vue / Gallery.vue / AdvancedQuery.vue 仍在解构）
  buttonMode: ref('shown'),
  tileSize: ref('adaptive'),
  previewOrder: ref('random'),
  includeOnline: ref(false),
  folderPageSize: ref(20),
  // 4 个新开关（我的最爱 / 随机浏览 / 收藏文件夹 / 收藏自动下载）
  enableMyFavorites: ref(false),
  enableRandomBrowse: ref(false),
  enableFavoriteFolder: ref(true),
  enableFavoriteAutodownload: ref(true),
  // 我的最爱总数（用于 FavoritePanel 角标 / 摘要）
  myFavoritesCount: ref(0),
  // 随机浏览候选池总数（down_flag=True 的本地图片数，用于随机浏览磁贴角标）
  randomBrowseCount: ref(0),
  // 首次加载完成标记（避免重复 GET）
  loaded: ref(false),
}

// 是否已注册 watcher（module-scope，避免重复注册）
let watcherInitialized = false

/**
 * 每次调用都重新读 localStorage legacy key（与 v1 行为一致：LS 是 5 个 UI 偏好的事实来源）
 *
 * 为什么不只在首次读：
 *   Gallery.spec.js / Config.spec.js 的 beforeEach 清空 LS 后单独 setItem('6') 模拟「已
 *   持久化的偏好」，依赖下次 mount 立刻拿到该值。如果只在首次读，后续 test 默认值就
 *   会被卡住，断言失败。
 *
 * 每次读 + watcher 写回的代价仅 5 次 getItem/sync，hot path 也只在每个组件 setup 调一次，可接受。
 */
function loadLegacyLocalStorage() {
  if (typeof window === 'undefined' || !window.localStorage) return

  // 先 reset 到默认值，再用 LS 值覆盖（如果有且合法）
  // 不先 reset 会导致跨测试/跨场景时 singleton ref 残留旧 mutation 值
  state.buttonMode.value = 'shown'
  const savedMode = window.localStorage.getItem('gallery_favorites_button_mode')
  if (VALID_BUTTON_MODES.includes(savedMode)) {
    state.buttonMode.value = savedMode
  }

  state.tileSize.value = 'adaptive'
  const savedSize = window.localStorage.getItem('gallery_favorites_tile_size')
    || window.localStorage.getItem('gallery_tile_size')  // v1 早期 key 兜底
  if (VALID_TILE_SIZES.includes(savedSize)) {
    state.tileSize.value = savedSize
  }

  state.previewOrder.value = 'random'
  const savedOrder = window.localStorage.getItem('gallery_favorites_preview_order')
  if (VALID_PREVIEW_ORDERS.includes(savedOrder)) {
    state.previewOrder.value = savedOrder
  }

  state.includeOnline.value = false
  const savedIncludeOnline = window.localStorage.getItem('gallery_favorites_include_online')
  if (savedIncludeOnline === 'true') {
    state.includeOnline.value = true
  }

  state.folderPageSize.value = 20
  const savedFolderPageSize = window.localStorage.getItem('favorites_folder_page_size')
  const parsed = savedFolderPageSize !== null ? parseInt(savedFolderPageSize, 10) : NaN
  if (VALID_FOLDER_PAGE_SIZES.includes(parsed)) {
    state.folderPageSize.value = parsed
  }
}

/**
 * 把当前 ref 写回 localStorage（5 个 legacy UI 偏好）
 */
function writeLegacyLocalStorage() {
  if (typeof window === 'undefined' || !window.localStorage) return
  window.localStorage.setItem('gallery_favorites_button_mode', state.buttonMode.value)
  window.localStorage.setItem('gallery_favorites_tile_size', state.tileSize.value)
  window.localStorage.setItem('gallery_favorites_preview_order', state.previewOrder.value)
  window.localStorage.setItem(
    'gallery_favorites_include_online', state.includeOnline.value ? 'true' : 'false'
  )
  window.localStorage.setItem('favorites_folder_page_size', String(state.folderPageSize.value))
}

/**
 * 拉取我的最爱总数写入 state.myFavoritesCount（失败仅警告，不抛）
 * 仅在调用方已经判断 enable_my_favorites=true 时调用
 */
export async function fetchMyFavoritesCount() {
  try {
    const res = await myFavoritesApi.count()
    const count = res?.data?.count
    if (typeof count === 'number') {
      state.myFavoritesCount.value = count
    } else if (count && typeof count === 'object' && typeof count.count === 'number') {
      // 兼容 res.data 直接是 { count } 的 mock 场景
      state.myFavoritesCount.value = count.count
    } else {
      state.myFavoritesCount.value = 0
    }
  } catch (e) {
    // 静默 — 角标无数据不影响主功能
    if (typeof console !== 'undefined') {
      console.warn('Fetch my favorites count failed:', e?.message || e)
    }
  }
}

/**
 * 拉取随机浏览候选池总数写入 state.randomBrowseCount（失败仅警告，不抛）
 * 仅在调用方已经判断 enable_random_browse=true 时调用
 */
export async function fetchRandomBrowseCount() {
  try {
    const res = await randomBrowseApi.getCount()
    const count = res?.data?.count
    if (typeof count === 'number') {
      state.randomBrowseCount.value = count
    } else if (count && typeof count === 'object' && typeof count.count === 'number') {
      state.randomBrowseCount.value = count.count
    } else {
      state.randomBrowseCount.value = 0
    }
  } catch (e) {
    // 静默 — 角标无数据不影响主功能
    if (typeof console !== 'undefined') {
      console.warn('Fetch random browse count failed:', e?.message || e)
    }
  }
}

/**
 * 把部分配置变更同步写回后端，并同步本地 state。
 *
 * @param {Record<string, any>} updates - snake_case 键值对（与后端契约一致）
 *        合法键：button_mode / tile_size / preview_order / include_online / folder_page_size
 *               enable_my_favorites / enable_random_browse / enable_favorite_folder / enable_favorite_autodownload
 * @returns {Promise<void>}
 */
export async function saveFavoritesConfig(updates) {
  if (!updates || typeof updates !== 'object') return
  await api.put('/config/favorites', updates)
  // 同步本地 state — 把 snake_case 键映射到 camelCase ref
  Object.entries(updates).forEach(([k, v]) => {
    const camelKey = k.replace(/_([a-z])/g, (_, c) => c.toUpperCase())
    if (camelKey in state) {
      // @ts-ignore — 已知 camelKey 映射合法
      state[camelKey].value = v
    }
  })
  // 如果刚开启「我的最爱」，立即拉取总数（角标显示用）
  if ('enable_my_favorites' in updates && updates.enable_my_favorites) {
    await fetchMyFavoritesCount()
  }
  // 同理：刚开启「随机浏览」时拉取候选池总数（随机浏览磁贴角标）
  if ('enable_random_browse' in updates && updates.enable_random_browse) {
    await fetchRandomBrowseCount()
  }
}

/**
 * 获取收藏夹 UI 配置 + 4 个新开关的响应式引用
 *
 * 首次调用：同步读 localStorage → fire-and-forget GET /config/favorites → 注册 watch
 * 后续调用：直接返回已初始化的 refs（singleton）
 *
 * @returns {{
 *   buttonMode: Ref<string>,
 *   tileSize: Ref<string>,
 *   previewOrder: Ref<string>,
 *   includeOnline: Ref<boolean>,
 *   folderPageSize: Ref<number>,
 *   enableMyFavorites: Ref<boolean>,
 *   enableRandomBrowse: Ref<boolean>,
 *   enableFavoriteFolder: Ref<boolean>,
 *   enableFavoriteAutodownload: Ref<boolean>,
 *   myFavoritesCount: Ref<number>,
 *   loaded: Ref<boolean>
 * }}
 */
export function useFavoritesConfig() {
  // 1) 每次都重新读 localStorage legacy key（向后兼容：LS 是 5 个 UI 偏好的事实来源）
  loadLegacyLocalStorage()

  if (!state.loaded.value) {
    // 标记 loaded 优先于读 localStorage，避免循环（watch 写入时不会再次触发 load）
    state.loaded.value = true

    // 2) 仅首次调用异步拉取后端最新值（成功则覆盖 LS 兜底；字段缺失则保持 LS / default）
    api.get('/config/favorites').then((res) => {
      const c = res && res.data
      if (!c || typeof c !== 'object') return
      // 防御性赋值：仅当字段存在且值合法时才覆盖（避免 mock 返回的无关 schema 污染 ref）
      if ('button_mode' in c && VALID_BUTTON_MODES.includes(c.button_mode)) {
        state.buttonMode.value = c.button_mode
      }
      if ('tile_size' in c && VALID_TILE_SIZES.includes(c.tile_size)) {
        state.tileSize.value = c.tile_size
      }
      if ('preview_order' in c && VALID_PREVIEW_ORDERS.includes(c.preview_order)) {
        state.previewOrder.value = c.preview_order
      }
      if ('include_online' in c) {
        state.includeOnline.value = !!c.include_online
      }
      if ('folder_page_size' in c) {
        const ps = Number(c.folder_page_size)
        if (VALID_FOLDER_PAGE_SIZES.includes(ps)) state.folderPageSize.value = ps
      }
      if ('enable_my_favorites' in c) {
        state.enableMyFavorites.value = !!c.enable_my_favorites
      }
      if ('enable_random_browse' in c) {
        state.enableRandomBrowse.value = !!c.enable_random_browse
      }
      if ('enable_favorite_folder' in c) {
        state.enableFavoriteFolder.value = !!c.enable_favorite_folder
      }
      if ('enable_favorite_autodownload' in c) {
        state.enableFavoriteAutodownload.value = !!c.enable_favorite_autodownload
      }

      // 我的最爱开启 → 加载总数；关闭 → 不主动清零，保留最后一次已知值（避免角标闪烁）
      if (state.enableMyFavorites.value) {
        fetchMyFavoritesCount()
      }
    }).catch((err) => {
      // 后端不可达不致命 — ref 保持 localStorage 兜底或 default
      if (typeof console !== 'undefined') {
        console.warn('Load favorites config failed:', err?.message || err)
      }
    })
  }

  if (!watcherInitialized) {
    watcherInitialized = true
    // 持久化 5 个 legacy UI 偏好到 localStorage（向后兼容：保证页面刷新仍有兜底值；
    // 与后端持久化解耦，后端不可达时也能加载上次浏览配置）
    watch(state.buttonMode, writeLegacyLocalStorage)
    watch(state.tileSize, writeLegacyLocalStorage)
    watch(state.previewOrder, writeLegacyLocalStorage)
    watch(state.includeOnline, writeLegacyLocalStorage)
    watch(state.folderPageSize, writeLegacyLocalStorage)
  }

  return state
}
