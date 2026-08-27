/**
 * 收藏夹 UI 配置（singleton composable）
 *
 * 共享响应式状态：Gallery（toolbar 显示/隐藏 + tile 尺寸）与 Config.vue（高级功能编辑）
 * 通过本 composable 共享同一份 ref，避免 props/事件穿透 AdvancedQuery。
 *
 * - module-level refs → 跨组件共享（任何地方 useFavoritesConfig() 都返回同一组 ref）
 * - 首次调用从 localStorage 读取初始值（向后兼容旧 key `gallery_tile_size`）
 * - watch 监听变化写回 localStorage（持久化）
 *
 * localStorage keys:
 *   gallery_favorites_button_mode    : 'hidden' | 'shown' | 'default'
 *   gallery_favorites_tile_size      : 'adaptive' | '4' | '6' | '8'
 *   gallery_favorites_preview_order  : 'random' | 'asc' | 'desc'
 *   gallery_favorites_include_online : 'true' | 'false'
 *   favorites_folder_page_size       : '8' | '12' | '20'（数字字符串）
 */
import { ref, watch } from 'vue'

/**
 * @typedef {import('vue').Ref} Ref
 */

// 模块级状态（singleton）：所有调用共享同一组 ref
const buttonMode = ref('shown')
const tileSize = ref('adaptive')
const previewOrder = ref('random')
const includeOnline = ref(false)
// 收藏夹一级每页条数（用户可在 Config.vue 通过 radio 切换 8 / 12 / 20）
const folderPageSize = ref(20)
let initialized = false

// 合法值白名单（防御性：localStorage 可能被外部篡改）
const VALID_BUTTON_MODES = ['hidden', 'shown', 'default']
const VALID_TILE_SIZES = ['adaptive', '4', '6', '8']
const VALID_PREVIEW_ORDERS = ['random', 'asc', 'desc']
const VALID_FOLDER_PAGE_SIZES = [8, 12, 20]

function readFromLocalStorage() {
  if (typeof window === 'undefined' || !window.localStorage) return

  buttonMode.value = 'shown'
  const savedMode = window.localStorage.getItem('gallery_favorites_button_mode')
  if (VALID_BUTTON_MODES.includes(savedMode)) {
    buttonMode.value = savedMode
  }

  tileSize.value = 'adaptive'
  const savedSize = window.localStorage.getItem('gallery_favorites_tile_size')
    || window.localStorage.getItem('gallery_tile_size')
  if (VALID_TILE_SIZES.includes(savedSize)) {
    tileSize.value = savedSize
  }

  previewOrder.value = 'random'
  const savedOrder = window.localStorage.getItem('gallery_favorites_preview_order')
  if (VALID_PREVIEW_ORDERS.includes(savedOrder)) {
    previewOrder.value = savedOrder
  }

  includeOnline.value = false
  const savedIncludeOnline = window.localStorage.getItem('gallery_favorites_include_online')
  if (savedIncludeOnline === 'true') {
    includeOnline.value = true
  }

  // folderPageSize 用 parseInt 解析，非法值（NaN / 非白名单）fallback 到 20
  folderPageSize.value = 20
  const savedFolderPageSize = window.localStorage.getItem('favorites_folder_page_size')
  const parsed = savedFolderPageSize !== null ? parseInt(savedFolderPageSize, 10) : NaN
  if (VALID_FOLDER_PAGE_SIZES.includes(parsed)) {
    folderPageSize.value = parsed
  }
}

function writeToLocalStorage() {
  if (typeof window === 'undefined' || !window.localStorage) return
  window.localStorage.setItem('gallery_favorites_button_mode', buttonMode.value)
  window.localStorage.setItem('gallery_favorites_tile_size', tileSize.value)
  window.localStorage.setItem('gallery_favorites_preview_order', previewOrder.value)
  window.localStorage.setItem(
    'gallery_favorites_include_online', includeOnline.value ? 'true' : 'false'
  )
  window.localStorage.setItem('favorites_folder_page_size', String(folderPageSize.value))
}

/**
 * 获取收藏夹 UI 配置的响应式引用
 *
 * 首次调用时从 localStorage 初始化，并启动持久化 watcher；
 * 后续调用直接返回已初始化的 refs（同 module-level singleton）。
 *
 * @returns {{
 *   buttonMode: Ref<string>,
 *   tileSize: Ref<string>,
 *   previewOrder: Ref<string>,
 *   includeOnline: Ref<boolean>,
 *   folderPageSize: Ref<number>
 * }}
 */
export function useFavoritesConfig() {
  readFromLocalStorage()

  if (!initialized) {
    initialized = true
    watch(buttonMode, writeToLocalStorage)
    watch(tileSize, writeToLocalStorage)
    watch(previewOrder, writeToLocalStorage)
    watch(includeOnline, writeToLocalStorage)
    watch(folderPageSize, writeToLocalStorage)
  }

  return { buttonMode, tileSize, previewOrder, includeOnline, folderPageSize }
}
