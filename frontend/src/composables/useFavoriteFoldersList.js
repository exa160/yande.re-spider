/**
 * 收藏夹文件夹列表 composable
 *
 * 职责：
 *   在收藏夹文件夹视图（favorites-folders）下，把 2 个虚拟磁贴（我的最爱 / 随机浏览）prepend
 *   到真实 folders 列表前面。2 个磁贴的可见性受 useFavoritesConfig 4 个开关控制。
 *
 * 设计要点：
 * 1. **复用而非重复**：FavoritePanel.vue（Task 16）与 Gallery.vue folders 视图都需要 prepend
 *    同一组虚拟磁贴。把 prepend 逻辑提到本 composable，避免两份实现各自漂移。
 * 2. **分页语义保护**：虚拟磁贴只 prepend 到第一页；后续页（page>1）就是真实 folders 追加，
 *    避免翻页时反复 prepend 同一组磁贴导致用户视觉上看到重复的"我的最爱 / 随机浏览"。
 * 3. **可选预览图回填**：当 `fetchPreview=true` 时，「我的最爱」磁贴的 preview_images 通过
 *    GET /my-favorites/preview?limit=N 异步拉取，N 取自 useFavoritesConfig.tileSize
 *    （adaptive/small/medium/large → 8/4/6/8），与后端 `_preview_count_for_local_count`
 *    契约保持一致。`fetchPreview=false`（默认，与 FavoritePanel 行为一致）则不请求预览。
 * 4. **防抖与失败容忍**：API 失败时返回空预览图数组，磁贴仍显示，只是没有缩略图。
 *
 * @example
 *   // Gallery.vue folders 视图（需要缩略图）
 *   const { displayFolders } = useFavoriteFoldersList({
 *     realFolders: currentFolders,
 *     page: folderPage,
 *     fetchPreview: true,
 *   })
 *   :images="displayFolders"
 *
 *   // FavoritePanel.vue 列表（不需要 API 调，保持原行为）
 *   const { displayFolders } = useFavoriteFoldersList({
 *     realFolders: foldersProp,
 *     page: ref(1),
 *   })
 */
import { computed, ref, watch } from 'vue'
import { useFavoritesConfig, fetchMyFavoritesCount } from './useFavoritesConfig'
import { myFavoritesApi } from '@/api/myFavorites'

// 与后端 src/services/favorites.py:_preview_count_for_local_count 契约对齐
const PREVIEW_COUNT_FOR_TILE_SIZE = {
  adaptive: 8,
  small: 4,
  medium: 6,
  large: 8,
}

/**
 * @typedef {import('vue').Ref<number>} NumberRef
 * @typedef {import('vue').Ref<Array<any>>} FoldersRef
 *
 * @param {object} options
 * @param {FoldersRef|(() => Array<any>)} options.realFolders - 真实收藏夹列表（来自后端）
 * @param {NumberRef|(() => number)} options.page - 当前分页号（1 = 首页，>1 = 加载更多）
 * @param {boolean} [options.fetchPreview=false] - 是否为「我的最爱」磁贴拉取预览图
 *        Gallery.vue folders 视图 = true（需要缩略图）；FavoritePanel = false（保持原行为）
 * @returns {{
 *   displayFolders: import('vue').ComputedRef<Array<any>>,
 *   myFavoritesPreview: import('vue').Ref<Array<any>>,
 *   reloadPreview: () => Promise<void>,
 * }}
 */
export function useFavoriteFoldersList(options) {
  const { realFolders, page, fetchPreview = false } = options || {}
  if (!realFolders) throw new Error('useFavoriteFoldersList: realFolders is required')
  if (!page) throw new Error('useFavoriteFoldersList: page is required')

  // 兼容 ref / getter 两种用法；统一成 getter（computed 表达式友好）
  const readRealFolders = typeof realFolders === 'function'
    ? realFolders
    : () => realFolders.value
  const readPage = typeof page === 'function'
    ? page
    : () => page.value

  const {
    enableMyFavorites,
    enableRandomBrowse,
    myFavoritesCount,
    tileSize,
  } = useFavoritesConfig()

  // 我的最爱预览图（独立 ref，由 watch 触发异步加载）
  const myFavoritesPreview = ref([])
  const myFavoritesPreviewLoading = ref(false)
  // 记录上次拉取的配置签名，避免相同签名重复请求
  let lastLoadedFor = ''

  // 计算「我的最爱」磁贴的预览图数量（基于当前 tileSize）
  const previewLimit = computed(() => {
    return PREVIEW_COUNT_FOR_TILE_SIZE[tileSize.value] ?? 8
  })

  // 异步加载我的最爱预览图（仅在 fetchPreview=true 且开关开时被触发）
  const loadMyFavoritesPreview = async () => {
    if (!fetchPreview || !enableMyFavorites.value) {
      // 不拉取预览 / 开关关闭 → 清空预览图
      myFavoritesPreview.value = []
      lastLoadedFor = ''
      return
    }
    const limit = previewLimit.value
    const sig = `${fetchPreview ? 1 : 0}:${tileSize.value}`
    if (lastLoadedFor === sig) return
    lastLoadedFor = sig

    myFavoritesPreviewLoading.value = true
    try {
      const res = await myFavoritesApi.getPreview(limit)
      // 响应兼容：res.data.images | res.data 直接是数组 | mock 兼容
      const images = res?.data?.images
      const arr = Array.isArray(images)
        ? images
        : (Array.isArray(res?.data) ? res.data : [])
      myFavoritesPreview.value = arr
      // 顺便刷新总数（如果之前没拉到）
      if (myFavoritesCount.value === 0) {
        fetchMyFavoritesCount().catch(() => {})
      }
    } catch (e) {
      // 失败时保持空数组，磁贴仍可见但无缩略图
      if (typeof console !== 'undefined') {
        console.warn('Load my favorites preview failed:', e?.message || e)
      }
      myFavoritesPreview.value = []
    } finally {
      myFavoritesPreviewLoading.value = false
    }
  }

  const reloadPreview = () => {
    lastLoadedFor = ''  // 强制 reload
    return loadMyFavoritesPreview()
  }

  // 监听开关 + tileSize 变化触发重新加载
  watch(
    [enableMyFavorites, tileSize],
    () => {
      loadMyFavoritesPreview()
    },
    { immediate: true }
  )

  // 虚拟磁贴：根据 4 个开关决定哪些出现在列表前
  // 顺序：「我的最爱 → 随机浏览」与 Task 16 FavoritePanel hardcoded 顺序保持一致
  const virtualTiles = computed(() => {
    const tiles = []
    if (enableMyFavorites.value) {
      tiles.push({
        id: 'my-favorites',
        name: '我的最爱',
        isVirtual: true,
        local_count: myFavoritesCount.value,
        preview_images: myFavoritesPreview.value,
      })
    }
    if (enableRandomBrowse.value) {
      tiles.push({
        id: 'random',
        name: '随机浏览',
        isVirtual: true,
        local_count: 0,
        preview_images: [],
      })
    }
    return tiles
  })

  // 合并显示列表：仅在第 1 页 prepend 虚拟磁贴，避免翻页重复
  const displayFolders = computed(() => {
    const folders = readRealFolders() || []
    if (readPage() === 1) {
      return [...virtualTiles.value, ...folders]
    }
    return folders
  })

  return {
    /** 给模板直接绑定的合并列表（page=1 含虚拟磁贴 + 真实列表；page>1 仅真实列表） */
    displayFolders,
    /** 我的最爱预览图数组（用于诊断 / 详情调试） */
    myFavoritesPreview,
    /** 当前是否正在异步加载预览图 */
    myFavoritesPreviewLoading: computed(() => myFavoritesPreviewLoading.value),
    /** 手动强制 reload 预览图（page refresh、keyword 切换时调用） */
    reloadPreview,
  }
}
