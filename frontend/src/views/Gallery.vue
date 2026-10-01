<template>
  <div class="gallery-page">
    <!-- 顶部工具栏 -->
    <div class="top-toolbar">
      <!-- 搜索框 + 模式按钮 -->
      <div class="toolbar-left" ref="toolbarLeftRef">
        <el-button-group class="mode-buttons">
          <el-button
            :type="querySource === 'yande' ? 'primary' : ''"
            @click="handleSourceChange('yande')"
          >
            在线
          </el-button>
          <el-button
            :type="querySource === 'local' ? 'primary' : ''"
            @click="handleSourceChange('local')"
          >
            本地
          </el-button>
          <el-button
            v-if="buttonMode !== 'hidden' && querySource !== 'yande'"
            :type="isFavoritesActive ? 'primary' : ''"
            @click="handleSourceChange('favorites')"
          >
            收藏夹
          </el-button>
        </el-button-group>
        <el-tooltip content="省流模式" :effect="isDarkMode ? 'dark' : 'light'" :trigger="isTouchDevice ? 'click' : 'hover'" :auto-close="isTouchDevice ? 1000 : 0" :show-after="isTouchDevice ? 0 : 100" :enterable="false">
          <el-button
            :type="saveDataMode ? 'warning' : ''"
            circle
            @click="saveDataMode = !saveDataMode"
          >
            <el-icon><Connection /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip content="安全模式" :effect="isDarkMode ? 'dark' : 'light'" :trigger="isTouchDevice ? 'click' : 'hover'" :auto-close="isTouchDevice ? 1000 : 0" :show-after="isTouchDevice ? 0 : 100" :enterable="false">
          <el-button
            :type="safeMode ? 'danger' : ''"
            circle
            class="safe-mode-btn"
            @click="safeMode = !safeMode"
          >
            <el-icon><MagicStick /></el-icon>
          </el-button>
        </el-tooltip>
      </div>
      <!-- 右侧工具按钮 -->
      <div class="toolbar-right" ref="toolbarRightRef">
        <!-- 移动端圆点菜单 -->
        <template v-if="useMobileMenu">
          <el-button circle class="mobile-menu-btn" @click="mobileMenuExpanded = !mobileMenuExpanded">
            <span class="menu-dots">···</span>
          </el-button>
          <transition name="menu-expand">
            <div v-if="mobileMenuExpanded" class="mobile-expand-menu">
              <el-button circle @click="toggleDarkMode(); mobileMenuExpanded = false">
                <el-icon v-if="isDarkMode"><Sunny /></el-icon>
                <el-icon v-else><Moon /></el-icon>
              </el-button>
              <DownloadIndicator
                :count="activeDownloadCount"
                @click="showDownloadDialog = true; mobileMenuExpanded = false"
              />
              <el-button circle @click="showConfigDialog = true; mobileMenuExpanded = false">
                <el-icon><Setting /></el-icon>
              </el-button>
            </div>
          </transition>
        </template>
        <!-- 桌面端显示完整按钮 -->
        <template v-else>
          <el-tooltip content="夜间模式" :effect="isDarkMode ? 'dark' : 'light'" :trigger="isTouchDevice ? 'click' : 'hover'" :auto-close="isTouchDevice ? 1000 : 0" :show-after="isTouchDevice ? 0 : 100" :enterable="false">
            <el-button circle @click="toggleDarkMode">
              <el-icon v-if="isDarkMode"><Sunny /></el-icon>
              <el-icon v-else><Moon /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip :content="downloadTooltipText" :effect="isDarkMode ? 'dark' : 'light'" :trigger="isTouchDevice ? 'click' : 'hover'" :auto-close="isTouchDevice ? 1000 : 0" :show-after="isTouchDevice ? 0 : 100" :enterable="false">
            <DownloadIndicator
              :count="activeDownloadCount"
              @click="showDownloadDialog = true"
            />
          </el-tooltip>
          <el-tooltip content="配置" :effect="isDarkMode ? 'dark' : 'light'" :trigger="isTouchDevice ? 'click' : 'hover'" :auto-close="isTouchDevice ? 1000 : 0" :show-after="isTouchDevice ? 0 : 100" :enterable="false">
            <el-button circle @click="showConfigDialog = true">
              <el-icon><Setting /></el-icon>
            </el-button>
          </el-tooltip>
        </template>
      </div>
    </div>

    <!-- 搜索组件（独立于 toolbar） -->
    <BackButton
      :visible="isBackVisible"
      @click="handleBackClick"
    />

    <AdvancedQuery
      @search="handleSearch"
      @favorites-filter="handleFavoritesFilter"
      @virtual-tile-navigate="handleVirtualTileNavigate"
      ref="queryRef"
      :source-mode="querySource"
      :mode="modeProp"
      :lock-favorite-chip="favoritesView === 'folder-detail'"
      :virtual-favorite="virtualSelectedFavorite"
    />

    <!-- 瀑布流图库组件 -->
    <div class="gallery-content">
      <!-- 收藏夹文件夹列表 -->
      <template v-if="querySource === 'favorites' && favoritesView === 'folders'">
        <WaterfallGallery
          item-type="folder"
          :images="displayFolders"
          :loading="folderLoading"
          :has-more="folderHasMore"
          :is-loading-more="isLoadingMore"
          :load-error="false"
          :selected-images="[]"
          :selectable="false"
          :source-mode="'favorites'"
          :save-data-mode="saveDataMode"
          :safe-mode="safeMode"
          @load-more="loadMoreFolders"
        >
          <template #default="{ folder }">
            <FolderTile
              :folder="folder"
              :save-data-mode="saveDataMode"
              :safe-mode="safeMode"
              @click="handleFolderClick"
            />
          </template>
        </WaterfallGallery>
      </template>

      <!-- 普通瀑布流（在线 / 本地 / 文件夹图片） -->
      <template v-else>
        <WaterfallGallery
          :images="images"
          :loading="loading"
          :has-more="hasMore"
          :is-loading-more="isLoadingMore"
          :load-error="loadError"
          :selected-images="selectedImages"
          :selectable="querySource === 'yande'"
          :source-mode="waterfallSourceMode"
          :save-data-mode="saveDataMode"
          :safe-mode="safeMode"
          :show-heart="showHeart"
          @image-click="handleImageClick"
          @image-select="handleImageSelect"
          @load-more="loadMore"
          @load-error="handleLoadError"
          @multi-select-start="handleMultiSelectStart"
          @favorite-toggled="onFavoriteChanged"
        />
      </template>
    </div>

    <!-- 左下角多选操作栏 -->
    <transition name="el-fade-in-linear">
      <div v-if="selectedImages.length > 0" class="multi-select-actions">
        <div class="action-column">
          <el-button type="primary" circle @click="batchDownload" class="action-btn download-btn-large">
            <el-icon><Download /></el-icon>
          </el-button>
          <div class="selection-count">{{ selectedImages.length }}</div>
        </div>
        <div class="action-buttons-vertical">
          <el-button circle @click="handleSelectAll" class="action-btn">
            <el-icon><Select /></el-icon>
          </el-button>
          <el-button circle @click="selectedImages = []" class="action-btn">
            <el-icon><Close /></el-icon>
          </el-button>
        </div>
      </div>
    </transition>

            <!-- 全屏查看器 -->
            <el-image-viewer
              v-if="viewerVisible"
              :url-list="imageUrlList"
              :initial-index="currentImageIndex"
              @close="viewerVisible = false"
              @switch="onViewerSwitch"
            />
    <!-- 图片预览弹窗 - 自定义浮层 -->
    <teleport to="body">
      <transition name="preview-fade">
        <div
          v-if="previewVisible && currentImage && !viewerVisible"
          class="image-preview-overlay"
          @click.self="previewVisible = false"
        >
<div class="float-image-wrapper" :style="previewContainerStyle">
            <!-- 左侧导航按钮 -->
            <el-button
              v-if="images.length > 1"
              class="image-nav-btn image-nav-btn-left"
              circle
              @click.stop="goToPrevImage"
              :disabled="currentImageIndex <= 0"
            >
              <el-icon><ArrowLeft /></el-icon>
            </el-button>

            <el-image
              :src="getDetailUrl(currentImage)"
              fit="contain"
              class="float-main-image"
              :preview-teleported="true"
              @click.stop="viewerVisible = true"
            />

            <!-- 右侧导航按钮 -->
            <el-button
              v-if="images.length > 1"
              class="image-nav-btn image-nav-btn-right"
              circle
              @click.stop="goToNextImage"
              :disabled="currentImageIndex >= images.length - 1"
            >
              <el-icon><ArrowRight /></el-icon>
            </el-button>

            <div class="float-header" :class="`overlay-${overlayColorScheme}`">
              <div class="float-header-left">
                <span class="float-id">ID: {{ currentImage.id }}</span>
                <span class="float-size">{{ currentImage.width }} × {{ currentImage.height }}</span>
                <el-tag :type="getRatingType(currentImage.rating)" size="small">
                  {{ currentImage.rating }}
                </el-tag>
              </div>
              <el-button circle @click="previewVisible = false" class="float-close-btn">
                <el-icon><Close /></el-icon>
              </el-button>
            </div>

          <div class="float-footer" :class="`overlay-${overlayColorScheme}`">
            <div class="float-footer-left">
              <!-- 三态：下载中（后端队列里有任务）/ 已下载（down_flag 或本次会话下载完成）/ 未下载。
                   任务下发即打上 queued 态（useDownloadState），因此「点下载 → 看到下载中」
                   无网络等待；收藏自动下载由轮询对账兜住。 -->
              <template v-if="currentDownState === 'downloading'">
                <el-button
                  type="primary"
                  disabled
                  class="float-download-btn"
                >
                  <span class="download-loading">
                    <el-icon class="is-loading"><Loading /></el-icon>
                    下载中...
                  </span>
                </el-button>
              </template>
              <template v-else-if="currentDownState === 'downloaded'">
                <el-button
                  @click.stop="handleDownload"
                  :disabled="downloading"
                  class="float-redownload-btn"
                  title="重新下载"
                >
                  <el-icon><Download /></el-icon>
                </el-button>
                <el-tag type="success" class="float-downloaded-tag">
                  <el-icon><Check /></el-icon>
                  已下载
                </el-tag>
              </template>
              <template v-else>
                <el-button
                  type="primary"
                  @click.stop="handleDownload"
                  :disabled="downloading"
                  class="float-download-btn"
                >
                  <span v-if="downloading" class="download-loading">
                    <el-icon class="is-loading"><Loading /></el-icon>
                    下载中...
                  </span>
                  <template v-else>
                    <el-icon><Download /></el-icon>
                    下载原图
                  </template>
                </el-button>
              </template>
              <HeartOverlay
                v-if="enableMyFavorites"
                class="float-heart"
                :image-id="currentImage.id"
                :initial-favorited="currentImage.is_favorited === true"
                :show-heart="true"
                @changed="onFavoriteChanged"
              />
            </div>
            
            <div class="float-footer-right" @click="toggleInfoPanel">
              <span class="float-expand-text">{{ infoPanelExpanded ? '收起详情' : '展开详情' }}</span>
              <el-icon class="float-expand-icon">
                <ArrowUp v-if="infoPanelExpanded" />
                <ArrowDown v-else />
              </el-icon>
            </div>
          </div>

          <transition name="detail-slide-up">
            <div v-if="infoPanelExpanded" class="float-detail-panel" :class="`overlay-${overlayColorScheme}`">
              <div class="detail-grid">
                <div class="detail-item">
                  <span class="detail-label">大小</span>
                  <span class="detail-value">{{ formatFileSize(currentImage.file_size) }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">作者</span>
                  <span class="detail-value">{{ detailAuthor || '-' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">上传用户</span>
                  <span class="detail-value">{{ currentImage.author || '-' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">MD5</span>
                  <span class="detail-value md5">{{ currentImage.md5 }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">时间</span>
                  <span class="detail-value">{{ currentImage.created_at }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">来源</span>
                  <span class="detail-value">
                    <a
                      v-if="detailSource"
                      class="detail-source-link"
                      :href="detailSource"
                      :title="detailSource"
                      target="_blank"
                      rel="noopener noreferrer"
                    >{{ detailSourceLabel }}</a>
                    <span v-else>-</span>
                  </span>
                </div>
              </div>
              
              <div class="detail-tags-area">
                <div class="detail-tags-label">标签 ({{ currentImage.tags?.length || 0 }})</div>
                <div class="detail-tags-list">
                  <el-tag
                    v-for="tag in currentImage.tags"
                    :key="tag"
                    size="default"
                    class="detail-tag"
                    :style="getTagStyle(tag)"
                  >
                    {{ tag }}
                  </el-tag>
                </div>
              </div>
            </div>
          </transition>
        </div>
        </div>
      </transition>
    </teleport>

    <!-- 下载管理对话框 -->
    <!-- destroy-on-close 必要：DownloadManager 内部有 setInterval 轮询，
         el-dialog 默认关闭时只隐藏不销毁内部组件，会导致 onUnmounted 不触发
         → stopPolling 不调用 → 轮询 timer 残留持续请求后端 -->
    <el-dialog
      v-model="showDownloadDialog"
      title="下载管理"
      width="80%"
      destroy-on-close
      class="center-dialog"
    >
      <DownloadManager />
    </el-dialog>

    <!-- 配置对话框 -->
    <el-dialog
      v-model="showConfigDialog"
      title="配置"
      width="80%"
      destroy-on-close
      class="center-dialog"
    >
      <ConfigPanel />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, onUnmounted, nextTick } from 'vue'
import { ElImageViewer } from 'element-plus'
import { ElMessage } from 'element-plus'
import { Download, Check, Connection, Setting, Sunny, Moon, Close, Select, ArrowUp, ArrowDown, Loading, MagicStick, Menu } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import AdvancedQuery from '@/components/AdvancedQuery.vue'
import WaterfallGallery from '@/components/WaterfallGallery.vue'
import FolderTile from '@/components/FolderTile.vue'
import BackButton from '@/components/BackButton.vue'
import HeartOverlay from '@/components/HeartOverlay.vue'
import DownloadIndicator from '@/components/DownloadIndicator.vue'
import DownloadManager from '@/views/Download.vue'
import ConfigPanel from '@/views/Config.vue'
import api from '@/api'
import { tagCacheApi } from '@/api/tagCache'
import { myFavoritesApi } from '@/api/myFavorites'
// 注意：updateLocalCount 打的是 /favorites/{id}/refresh（后端重跑 COUNT，昂贵），
// 本文件的角标写入一律走 setLocalCount（O(1) 的 /local-count）
// refreshOnlineCount 打的是 yande.re 远程 API —— 后端已加 600s TTL 兜底，
// 重复调用直接命中缓存，不会真的打远端
import { setLocalCount, refreshOnlineCount, getFoldersWithPreview } from '@/api/favorites'
import { useFavoritesConfig, whenFavoritesConfigReady } from '@/composables/useFavoritesConfig'
import { useFavoriteFoldersList } from '@/composables/useFavoriteFoldersList'
import { useDownloadState } from '@/composables/useDownloadState'

const images = ref([])
const loading = ref(false)
const hasMore = ref(false)
const isLoadingMore = ref(false)
const loadError = ref(false)
const currentPage = ref(1)
const queryParams = ref({})
const currentFavorite = ref(null)
const queryRef = ref(null)  // template ref 绑定 AdvancedQuery 暴露的 selectFavorite/reset

// 收藏夹模式状态机
const favoritesView = ref(null)  // null | 'folders' | 'folder-detail'
const selectedFavoriteFolder = ref(null)
const currentFolders = ref([])
const folderLoading = ref(false)
const folderHasMore = ref(false)
const folderPage = ref(1)
// 收藏夹一级搜索关键字（受 AdvancedQuery 的 favorites-filter emit 驱动）。
// 服务端按 folder.name / folder.tags 模糊匹配，多 token 之间 OR 关系。
const folderKeyword = ref('')
let folderSearchDebounce = null

// 从 localStorage 读取保存的设置，默认本地模式
// v2 优先级：route.query.querySource 优先（FavoritePanel 虚拟磁点击中后 router.push 会带 query），
// 否则读 localStorage 的 gallery_source，否则默认 'local'
const route = useRoute()
const router = useRouter()
const initialSource = (() => {
  const fromRoute = route?.query?.querySource
  if (typeof fromRoute === 'string' && fromRoute) {
    // 路由 query 覆盖持久化值时同步写一次 localStorage，确保下次刷新保留用户的「我的最爱 / 随机浏览」入口
    localStorage.setItem('gallery_source', fromRoute)
    return fromRoute
  }
  return localStorage.getItem('gallery_source') || 'local'
})()
const querySource = ref(initialSource)
const saveDataMode = ref(localStorage.getItem('gallery_saveData') === 'true')

// 虚拟 favorite chip（搜索栏显示用）—— 基于 querySource 派生：
//   - 'my-favorites'    → 显示 "★ 我的最爱"
//   - 'random'          → 显示 "★ 随机浏览"
//   - 'recent-downloads' → 显示 "★ 最近下载"
//   - 其它              → null（不显示 chip）
// 与 selectedFavorite（真实收藏夹 chip）互斥：favorites → 虚拟视图时 handleSourceChange
// 已 _clearSelectedFavoriteNoSearch 清空 selectedFavorite；favorites folder-detail 时
// virtualSelectedFavorite 必为 null（querySource='favorites'）。
const VIRTUAL_FAVORITES = {
  'my-favorites': { id: 'my-favorites', name: '我的最爱' },
  'random': { id: 'random', name: '随机浏览' },
  'recent-downloads': { id: 'recent-downloads', name: '最近下载' },
}
const virtualSelectedFavorite = computed(() => VIRTUAL_FAVORITES[querySource.value] || null)

// 收藏夹 UI 配置（singleton composable，跨组件共享 + localStorage 持久化）
// - buttonMode: 'hidden' / 'shown' / 'default'（default → 进首页直接跳 favorites）
// - tileSize:   'adaptive' / '4' / '6' / '8'
// - previewOrder: 'random' / 'desc' / 'asc'（控制 with-preview 返回的预览图顺序）
// - includeOnline: bool（控制 with-preview 是否返回未下载图片；Config.vue 高级功能开关）
// - enableMyFavorites: 我的最爱功能总开关（v2）
// 持久化 + 旧 key `gallery_tile_size` 向后兼容由 composable 内部处理
const {
  buttonMode,
  tileSize,
  previewOrder,
  includeOnline,
  folderPageSize,
  enableMyFavorites,
} = useFavoritesConfig()

// Task 19 修复：favorites-folders 视图 prepend 虚拟磁贴（我的最爱 / 随机浏览）
// 仅在第 1 页 prepend — 分页时真实 folder 列表继续 push，虚拟磁贴不重复
// fetchPreview=true → 「我的最爱」磁贴通过 GET /my-favorites/preview 拉缩略图；
//   「随机浏览」磁贴无预览（preview_images 始终空）
// displayFolders 直接绑给 WaterfallGallery 的 :images
const { displayFolders } = useFavoriteFoldersList({
  realFolders: currentFolders,
  page: folderPage,
  fetchPreview: true,
})

// v2 我的最爱 / 随机浏览：是否在 WaterfallGallery 显示 HeartOverlay
//   - showHeart=true → 渲染 HeartOverlay，并在 showHeart && enableMyFavorites 时调 /gallery/load 加 include_favorite_status
//   - showHeart=false → 不渲染 HeartOverlay，也不加参数（保持旧 querySource 行为不变）
const showHeart = computed(() => {
  return enableMyFavorites.value === true
})

// 前端 radio 用 4/6/8 直觉数字，契约要 small/medium/large（spec §3.2）
// 'adaptive' 透传；其它值 fallback 到原值（防御性）
const API_TILE_SIZE = {
  '4': 'small',
  '6': 'medium',
  '8': 'large',
}

// AdvancedQuery mode 计算属性
//   querySource='favorites' → favorites-folders / favorites-folder-detail
//   其它 → 'gallery'
const modeProp = computed(() => {
  if (querySource.value === 'favorites') {
    return favoritesView.value === 'folder-detail'
      ? 'favorites-folder-detail'
      : 'favorites-folders'
  }
  return 'gallery'
})

// WaterfallGallery 实际加载策略 sourceMode
//   - favorites-folder-detail → 'local'
//     复用本地瀑布流的 L1 静态缓存 / L2 本地生成路径；
//     远端下载由 WaterfallGallery.runFallbackChain（步骤 2 /cache/preview/fetch/）
//     在本地两步都失败时兜底，无需按 includeOnline 分流。
//   - 其他场景 → 透传 querySource
const waterfallSourceMode = computed(() => {
  if (querySource.value === 'favorites' && favoritesView.value === 'folder-detail') {
    return 'local'
  }
  return querySource.value
})

const previewVisible = ref(false)
const currentImage = ref(null)
const previewContainerStyle = ref({})
const downloading = ref(false)
// 任务下发请求在途标记（防重复点击）；「下载中」的权威来源是 useDownloadState
const {
  downStateOf,
  activeCount: activeDownloadCount,
  markQueued,
  sync: syncDownloadStates,
  start: startDownloadSync,
  stop: stopDownloadSync,
  onCompleted: onDownloadCompleted,
} = useDownloadState()
// 当前大图的下载态：'downloading' | 'paused' | 'downloaded' | 'none'
const currentDownState = computed(() => downStateOf(currentImage.value))
// 工具栏下载入口的 tooltip：有任务在跑时把数量说清楚，否则用户点进去才知道
const downloadTooltipText = computed(() => {
  const n = activeDownloadCount.value
  return n > 0 ? `下载管理（${n} 个下载中）` : '下载管理'
})
// 下载完成订阅的退订句柄（onMounted 注册 / onUnmounted 注销）
let unsubscribeDownloadCompleted = null
const overlayColorScheme = ref('dark') // 'dark' or 'light'
const safeMode = ref(localStorage.getItem('safe_mode') !== 'false')
const viewerVisible = ref(false)
const mobileMenuExpanded = ref(false)
const mobileMenuActive = ref(false)
const toolbarLeftRef = ref(null)
const triggerUpdate = ref(0)

// 右边按钮的估算宽度（固定值，避免反馈循环）
const RIGHT_BUTTON_WIDTH = 112 // 单个按钮 + gap
const RIGHT_MOBILE_MENU_WIDTH = 48 // 圆点菜单按钮宽度

// 检测是否需要使用移动端圆点菜单（两边按钮重叠时）
const useMobileMenu = computed(() => {
  if (typeof window === 'undefined') return false

  const leftEl = toolbarLeftRef.value
  if (!leftEl) return false

  void triggerUpdate.value

  // 只测量左边的宽度，右边用固定值估算
  const getChildrenWidth = (el) => {
    return Array.from(el.children).reduce((sum, child) => {
      return sum + child.offsetWidth + 12
    }, 0)
  }

  const leftWidth = getChildrenWidth(leftEl)
  const toolbar = leftEl.closest('.top-toolbar')
  const containerWidth = toolbar ? toolbar.offsetWidth - 40 : window.innerWidth - 40

  // 滞回区间
  const threshold = 20

  // 根据当前状态决定使用哪个右边宽度
  const rightWidth = mobileMenuActive.value ? RIGHT_MOBILE_MENU_WIDTH : RIGHT_BUTTON_WIDTH
  const totalWidth = leftWidth + rightWidth

  const shouldShow = totalWidth >= containerWidth + threshold
  const shouldHide = leftWidth + RIGHT_BUTTON_WIDTH < containerWidth - threshold

  if (mobileMenuActive.value) {
    mobileMenuActive.value = !shouldHide
  } else {
    mobileMenuActive.value = shouldShow
  }

  return mobileMenuActive.value
})

// 监听窗口大小变化，使用 ResizeObserver 检测 toolbar 宽度变化
onMounted(() => {
  const toolbar = document.querySelector('.top-toolbar')
  if (toolbar) {
    const resizeObserver = new ResizeObserver(() => {
      triggerUpdate.value++
    })
    resizeObserver.observe(toolbar)
  }
})

// 图片导航
const currentImageIndex = computed(() => {
  if (!currentImage.value) return -1
  return images.value.findIndex(img => img.id === currentImage.value.id)
})

// 计算所有图片的 URL 列表（用于 el-image-viewer）
const imageUrlList = computed(() => {
  return images.value.map(img => getDetailUrl(img))
})

const goToPrevImage = () => {
  const idx = currentImageIndex.value
  if (idx > 0) {
    currentImage.value = images.value[idx - 1]
  }
}

const goToNextImage = () => {
  const idx = currentImageIndex.value
  if (idx >= 0 && idx < images.value.length - 1) {
    currentImage.value = images.value[idx + 1]
  }
}

// viewer 切换时同步 currentImage
const onViewerSwitch = (index) => {
  if (images.value[index]) {
    currentImage.value = images.value[index]
  }
}

// v2 我的最爱 / 随机浏览：HeartOverlay 切换后乐观更新 currentImage.is_favorited
// 详情页浮层与 WaterfallGallery 共享同一份 image 数据源（来自 /gallery/load + include_favorite_status），
// 直接写入当前 currentImage，避免再发一次 /gallery/{id} 拉详情
//
// 两个触发源都走这里：详情页 HeartOverlay 的 @changed，以及**瀑布流卡片**红心的
// @favorite-toggled（WaterfallGallery 把卡片上的 changed 透传成 favorite-toggled）。
// 早期只接了详情页，导致卡片上收藏时这里完全不执行 —— 收藏自动下载被后端触发后
// 前端无感知，没有「下载中」，只等得到轮询对账后的「已下载」小绿点。
//
// payload.downloadStarted：开启收藏自动下载时后端顺带建了下载任务，立即标记「下载中」
// （后端触发、前端无感知，是「收藏自动下载打开时标识不变」的根因修复）
const onFavoriteChanged = (payload) => {
  if (!payload) return
  if (currentImage.value && currentImage.value.id === payload.imageId) {
    currentImage.value.is_favorited = payload.favorited
  }
  if (payload.downloadStarted) {
    markQueued([payload.imageId])
    syncDownloadStates()
  }
}

// 分析图片主色调，决定浮层文字颜色
const analyzeImageColor = (imgUrl) => {
  if (!imgUrl) {
    overlayColorScheme.value = 'dark'
    return
  }
  
  const img = new Image()
  img.crossOrigin = 'Anonymous'
  img.onload = () => {
    try {
      const canvas = document.createElement('canvas')
      const ctx = canvas.getContext('2d')
      const sampleSize = 50 // 采样大小，越小越快
      
      canvas.width = sampleSize
      canvas.height = sampleSize
      ctx.drawImage(img, 0, 0, sampleSize, sampleSize)
      
      const imageData = ctx.getImageData(0, 0, sampleSize, sampleSize)
      const data = imageData.data
      
      let totalBrightness = 0
      let pixelCount = 0
      
      for (let i = 0; i < data.length; i += 4) {
        const r = data[i]
        const g = data[i + 1]
        const b = data[i + 2]
        // 计算亮度 (公式: 0.299*R + 0.587*G + 0.114*B)
        const brightness = 0.299 * r + 0.587 * g + 0.114 * b
        totalBrightness += brightness
        pixelCount++
      }
      
      const avgBrightness = totalBrightness / pixelCount
      // 如果平均亮度大于 180，认为是浅色图片，使用深色文字
      overlayColorScheme.value = avgBrightness > 180 ? 'light' : 'dark'
    } catch (e) {
      // 跨域或其他错误，使用默认深色
      overlayColorScheme.value = 'dark'
    }
  }
  img.onerror = () => {
    overlayColorScheme.value = 'dark'
  }
  img.src = imgUrl
}

// 监听 currentImage 变化，分析图片颜色
watch(currentImage, (img) => {
  if (previewVisible.value && img) {
    // 使用本地预览图进行分析，无本地路径时不尝试加载远程图片（避免CORS）
    // preview_url 不以 http 开头则是本地路径
    const isLocalPreview = img.preview_url && !img.preview_url.startsWith('http')
    const imgUrl = isLocalPreview
      ? `/api/v1/gallery/cache/preview/${img.id}`
      : ''
    analyzeImageColor(imgUrl)
  }
})

// 计算图片预览容器尺寸，保持图片原始比例，80vh 高度
const calculatePreviewSize = () => {
  if (!currentImage.value) {
    previewContainerStyle.value = {}
    return
  }
  
  const imgWidth = currentImage.value.width || 1920
  const imgHeight = currentImage.value.height || 1080
  const imgRatio = imgWidth / imgHeight
  
  // 最大可用高度（80vh）
  const maxHeight = window.innerHeight * 0.8
  const maxWidth = window.innerWidth * 0.8
  
  let width, height
  if (imgRatio > maxWidth / maxHeight) {
    // 图片更宽，以宽度为准
    width = maxWidth
    height = maxWidth / imgRatio
  } else {
    // 图片更高，以高度为准
    height = maxHeight
    width = maxHeight * imgRatio
  }
  
  previewContainerStyle.value = {
    width: `${width}px`,
    height: `${height}px`
  }
}

// 监听 currentImage 变化，重新计算尺寸
watch(currentImage, (img) => {
  if (previewVisible.value && img) {
    calculatePreviewSize()
  }
})
const tagsExpanded = ref(false)
const infoPanelExpanded = ref(false)

// Tag 类型颜色映射（背景透明度保持和原来一致 0.1，边框用对应颜色）
const TAG_TYPE_COLORS = {
  0: { bg: 'rgba(238, 136, 135, 0.1)', border: '#ee8887' },  // 通用
  1: { bg: 'rgba(204, 204, 0, 0.1)', border: '#cccc00' },     // 艺术家
  3: { bg: 'rgba(221, 0, 221, 0.1)', border: '#D0D' },        // 版权
  4: { bg: 'rgba(0, 170, 0, 0.1)', border: '#0A0' },         // 角色
}

// 存储 tag 类型信息
const tagTypesMap = ref({})

// 多选相关
const selectedImages = ref([])
const selectAll = ref(false)
const isIndeterminate = ref(false)

// 弹框状态
const showDownloadDialog = ref(false)
const showConfigDialog = ref(false)

// 夜间模式
const isDarkMode = ref(localStorage.getItem('dark_mode') === 'true')
const toggleDarkMode = () => {
  isDarkMode.value = !isDarkMode.value
  localStorage.setItem('dark_mode', isDarkMode.value ? 'true' : 'false')
  document.documentElement.classList.toggle('dark-mode', isDarkMode.value)
}

// 检测触摸设备 - 优先使用 CSS media query（更可靠，避免虚拟机误判）
const isTouchDevice = computed(() => {
  // 媒体查询能更准确反映设备能力
  const hasCoarsePointer = window.matchMedia('(pointer: coarse)').matches
  const hasNoHover = window.matchMedia('(hover: none)').matches
  return hasCoarsePointer && hasNoHover
})

// 监听模式变化，保存到 localStorage
const stopSourceWatch = watch(querySource, (val) => {
  localStorage.setItem('gallery_source', val)
})

// v2 我的最爱 / 随机浏览入口：FavoritePanel 点击虚拟磁贴 → router.push({query:{querySource:'my-favorites'|'random'}})
// → 这里把 route.query.querySource 同步进 Gallery 的 querySource ref，触发持久化 watch 与 loadImages。
// 仅在路由上出现 querySource 时才覆盖 localStorage 默认值（与 FavoritePanel 契约一致）；
// 用户手动切 source 按钮时不写入路由（避免污染浏览器历史）。
watch(() => route?.query?.querySource, (val) => {
  if (typeof val === 'string' && val && val !== querySource.value) {
    querySource.value = val
    // 虚拟磁贴跳转后必须重新触发 loadImages（onMounted 已跑过，仅靠 ref 变化不重 fetch）
    currentPage.value = 1
    images.value = []
    selectedImages.value = []
    selectAll.value = false
    // 切走 favorites 时清空 currentFavorite（防止 stale string id 进 favorites 端点 422）
    if (val !== 'favorites') {
      currentFavorite.value = null
    }
    loadImages()
  }
})

const stopSaveDataWatch = watch(saveDataMode, (val) => {
  localStorage.setItem('gallery_saveData', val ? 'true' : 'false')
})

const stopSafeModeWatch = watch(safeMode, (val) => {
  localStorage.setItem('safe_mode', val ? 'true' : 'false')
})

// 收藏夹配置由 composable 全局共享：buttonMode 切到 'default' 时跳转到 favorites 视图
// （取代原 AdvancedQuery 的 @favorites-config-change 回调，触发源迁到 Config.vue）
watch(buttonMode, (newMode, oldMode) => {
  if (newMode === 'default' && oldMode !== 'default' && querySource.value !== 'favorites') {
    handleSourceChange('favorites')
  }
})

// previewOrder 改变时，在收藏夹列表视图重新加载第一页（用户切换顺序后立即生效）
watch(previewOrder, () => {
  if (querySource.value === 'favorites' && favoritesView.value === 'folders') {
    folderPage.value = 1
    currentFolders.value = []
    folderHasMore.value = false
    loadFolders(1)
  }
})

// includeOnline 改变时，在收藏夹列表视图重新加载第一页（用户在 Config.vue 高级功能切换后立即生效）
// 注意：folder-detail 视图（搜索主图）由 AdvancedQuery 内 handleSearch 走 /gallery/load 触发，
// 本 watch 只负责 folder-list（favorites-folders 模式）的预览图元数据刷新。
watch(includeOnline, () => {
  if (querySource.value === 'favorites' && favoritesView.value === 'folders') {
    folderPage.value = 1
    currentFolders.value = []
    folderHasMore.value = false
    loadFolders(1)
  }
})

// folderPageSize 改变时重新加载第一页（与 previewOrder / includeOnline 一致：用户切换立即生效）
watch(folderPageSize, () => {
  if (querySource.value === 'favorites' && favoritesView.value === 'folders') {
    folderPage.value = 1
    currentFolders.value = []
    folderHasMore.value = false
    loadFolders(1)
  }
})

// 图片预览


// 解析收藏夹的 tags 字符串
const parseFavoriteTags = (tagsStr) => {
  const params = {}
  if (!tagsStr) return params

  const parts = tagsStr.split(/\s+/)
  for (const part of parts) {
    if (part.startsWith('rating:')) {
      params.rating = [part.split(':')[1]]
    } else if (part.startsWith('score:>')) {
      params.min_score = parseInt(part.split(':')[1])
    } else if (part.startsWith('score:<=')) {
      params.max_score = parseInt(part.split(':')[1])
    } else if (part.startsWith('sort_order:')) {
      const orderVal = part.split(':')[1]
      params.sort_order = orderVal
    } else if (part.startsWith('sort_by:')) {
      const sortByVal = part.split(':')[1]
      params.sort_by = sortByVal
    } else if (part.startsWith('width:>=')) {
      params.min_width = parseInt(part.split(':')[1])
    } else if (part.startsWith('width:<=')) {
      params.max_width = parseInt(part.split(':')[1])
    } else if (part.startsWith('ext:')) {
      params.file_types = [part.split(':')[1]]
    } else if (!part.startsWith('-')) {
      // 普通标签
      if (!params.tags) {
        params.tags = part
      } else {
        params.tags += ' ' + part
      }
    }
  }
  return params
}

// 收藏夹创建/更新成功后
const handleFavoriteCreate = async (folder) => {
  showFavoritePanel.value = false
}

onUnmounted(() => {
  stopSourceWatch()
  stopSaveDataWatch()
  stopSafeModeWatch()
})

const handleSearch = async (searchData) => {
  // 防御性解析 favorite_id：仅当是合法正整数才注入，避免后端 Pydantic int 校验失败（422）。
  // v2 路径里 searchData.favorite?.id 可能是 undefined（mode 路径）/ 整数 / 字符串占位符
  // （如虚拟磁贴点击经 handleSearch({favorite:{id:'random'}, ...}) 等场景）。
  const favoriteIdNum = Number(searchData.favorite?.id)
  const hasValidFavoriteId =
    Number.isInteger(favoriteIdNum) && favoriteIdNum > 0 && String(favoriteIdNum) === String(searchData.favorite.id)
  const injectedFavoriteId = hasValidFavoriteId ? favoriteIdNum : undefined

  // 模式降级：searchData.mode='favorites' 但未传有效 favorite_id（用户在收藏夹 tab
  // 没选具体 folder 就点了搜索）→ 后端 favorites 分支必然返回空。降级为 'local'
  // 至少用当前 tags/评分/排序拉本地 DB，避免误发 /gallery/load source='favorites' 无效请求。
  const requestedMode = searchData.mode
  const effectiveMode =
    requestedMode === 'favorites' && injectedFavoriteId === undefined ? 'local' : requestedMode

  let params
  if (effectiveMode) {
    // 模式分支：effectiveMode 是 AdvancedQuery 内部传入的 source 候选值
    // （'local' / 'yande' / 'favorites' / 'random' / 'recent-downloads'）
    // 同 loadImages 防护：'random' / 'recent-downloads' 映射到 'local'
    // （随机浏览走本地随机抽样由 random=true 触发；最近下载由 sort_by=downloaded_at 触发）
    params = {
      ...searchData.params,
      source: (effectiveMode === 'random' || effectiveMode === 'recent-downloads') ? 'local' : effectiveMode,
    }
    // source='favorites' 时注入 favorite_id（后端用其定位 folder → 取其 tags）
    if (effectiveMode === 'favorites' && injectedFavoriteId !== undefined) {
      params.favorite_id = injectedFavoriteId
    }
  } else {
    // 仅当 source 解析为 favorites 且 favorite_id 合法时才注入，避免切 querySource 时
    // 残留的 favorite/搜索组合把脏 favorite_id 写进 queryParams（后续 loadImages 会带出去 → 422）
    // 'random' / 'recent-downloads' 同 loadImages 映射到 'local'
    const resolvedSource = (querySource.value === 'random' || querySource.value === 'recent-downloads')
      ? 'local'
      : querySource.value
    const shouldInjectFavorite = resolvedSource === 'favorites' && injectedFavoriteId !== undefined
    params = { ...searchData, source: resolvedSource }
    if (shouldInjectFavorite) {
      params.favorite_id = injectedFavoriteId
    } else {
      // 非合法情况显式剔除，避免从上级 spread 透传脏 favorite_id
      delete params.favorite_id
    }
  }
  queryParams.value = params
  currentPage.value = 1
  images.value = []
  selectedImages.value = []
  selectAll.value = false
  currentFavorite.value = searchData.favorite || null
  await loadImages()
}

const loadFolders = async (page) => {
  // isFirstPage 守卫：仅在加载第一页时切换 loading 状态以触发 skeleton
  // page>1 时通过 loadMoreFolders → isLoadingMore 通道管理「加载中…」按钮，
  // 避免 set folderLoading=true 触发 WaterfallGallery 顶层 v-if 卸载整个瀑布流 DOM
  const isFirstPage = page === 1 || folderPage.value === 1
  if (isFirstPage) {
    folderLoading.value = true
  }
  try {
    // 前端 radio 用 4/6/8 直觉数字，契约要 small/medium/large（spec §3.2）
    const apiTileSize = API_TILE_SIZE[tileSize.value] || tileSize.value
    // previewOrder / includeOnline 从 useFavoritesConfig composable 取
    // （用户在 Config.vue 高级功能设置）
    const previewOrderVal = previewOrder.value || 'random'
    const includeOnlineVal = includeOnline.value === true
    const res = await getFoldersWithPreview(
      page,
      folderPageSize.value,
      apiTileSize,
      folderKeyword.value,
      previewOrderVal,
      includeOnlineVal
    )
    const { items, has_more } = res.data
    if (page === 1) {
      currentFolders.value = items
    } else {
      currentFolders.value.push(...items)
    }
    folderHasMore.value = has_more
    folderPage.value = page
  } catch (e) {
    ElMessage.error('加载收藏夹失败：' + (e?.message || '未知错误'))
    throw e  // 让 loadMoreFolders 能 catch 回退 folderPage
  } finally {
    if (isFirstPage) {
      folderLoading.value = false
    }
  }
}

// 收藏夹加载更多：folderHasMore 在 server 端控制（基于 total + page_size）
const handleFolderScrollBottom = () => {
  if (folderHasMore.value && !folderLoading.value) {
    loadMoreFolders()
  }
}

// 与 image 模式 loadMore 对称：先自增 page，再调 loadFolders；
// loadFolders 在 isFirstPage=false 时不会 set folderLoading=true → 不会触发 skeleton 全刷
// 复用 image 模式共享的 isLoadingMore ref（两个 WaterfallGallery 实例 v-if/v-else 互斥渲染，无冲突）
const loadMoreFolders = async () => {
  if (isLoadingMore.value) return
  isLoadingMore.value = true
  folderPage.value++
  try {
    await loadFolders(folderPage.value)
  } catch {
    folderPage.value--
  }
  isLoadingMore.value = false
}

// AdvancedQuery 在 mode='favorites-folders' 输入框变化时 emit 'favorites-filter'
// 200ms debounce 后回调查后端，重置分页到第 1 页。
const handleFavoritesFilter = (value) => {
  const keyword = (value || '').trim()
  if (folderSearchDebounce) clearTimeout(folderSearchDebounce)
  folderSearchDebounce = setTimeout(() => {
    folderKeyword.value = keyword
    folderPage.value = 1
    currentFolders.value = []
    folderHasMore.value = false
    loadFolders(1)
  }, 200)
}

// AdvancedQuery 转发 FavoritePanel 虚拟磁贴点击 → 直接 handleSourceChange 强制刷新。
// 绕过 vue-router 对同 url push 不发 navigation 事件的限制（修复问题 5：弹窗内
// 「我的收藏」重复点击失效，必须先点别的虚拟磁贴切走再点回来才能 reload）。
const handleVirtualTileNavigate = (source) => {
  if (source === 'my-favorites' || source === 'random' || source === 'recent-downloads') {
    handleSourceChange(source)
  }
}

// BackButton 可见性：favorites folder-detail（真实收藏夹二级）+ 虚拟视图（我的最爱 / 随机浏览 / 最近下载）
// 虚拟视图的 chip 显示 🔒 锁定，返回只能通过 BackButton（与 favorites folder-detail 一致）
const isBackVisible = computed(() => {
  if (querySource.value === 'favorites' && favoritesView.value === 'folder-detail') return true
  if (
    querySource.value === 'my-favorites' ||
    querySource.value === 'random' ||
    querySource.value === 'recent-downloads'
  ) return true
  return false
})

// BackButton click 调度：根据当前视图分发
// - folder-detail → handleBackToFolders（保留 selectedFavorite 等状态精确清理）
// - 虚拟视图 → handleSourceChange('favorites')（统一走 favorites tab 入口）
const handleBackClick = () => {
  if (querySource.value === 'favorites' && favoritesView.value === 'folder-detail') {
    handleBackToFolders()
  } else {
    handleSourceChange('favorites')
  }
}

// toolbar "收藏夹" 按钮高亮条件：扩展到虚拟视图（my-favorites / random / recent-downloads 也属于收藏夹上下文）
// 修复问题 8：进入虚拟视图后 toolbar 收藏夹 tab 焦点消失
const isFavoritesActive = computed(() => {
  return (
    querySource.value === 'favorites' ||
    querySource.value === 'my-favorites' ||
    querySource.value === 'random' ||
    querySource.value === 'recent-downloads'
  )
})

const handleFolderClick = (folder) => {
  // 虚拟磁贴（我的最爱 / 随机浏览 / 最近下载）：直接 handleSourceChange 切换 querySource，
  // 让 loadImages 走对应端点（my-favorites → /my_favorites/images；
  //   random → /gallery/load?random=true；recent-downloads → /gallery/load?sort_by=downloaded_at），
  //   避免误入 favorites folder-detail 触发防御性拦截清空 images（修复问题 4）。
  //
  // 不 router.push：之前写 ?querySource=my-favorites 到 URL 后，用户切回 favorites
  // 再点我的收藏 → URL 仍带旧 querySource → vue-router 同 url 不发事件 → 失效。
  // 新设计只走 Gallery 内部 handleSourceChange，URL 保持干净（state 由 localStorage
  // 持久化 + URL 仅作为分享链接初始入口使用）。
  if (folder?.isVirtual) {
    if (folder.id === 'my-favorites') {
      handleSourceChange('my-favorites')
    } else if (folder.id === 'random') {
      handleSourceChange('random')
    } else if (folder.id === 'recent-downloads') {
      handleSourceChange('recent-downloads')
    }
    return
  }
  // 真实收藏夹：进入 folder-detail 视图（原有逻辑）
  selectedFavoriteFolder.value = folder
  favoritesView.value = 'folder-detail'
  // 复用 AdvancedQuery 的 selectFavorite 设置搜索栏状态
  queryRef.value?.selectFavorite(folder)
}

const handleBackToFolders = () => {
  selectedFavoriteFolder.value = null
  favoritesView.value = 'folders'
  // 不调 reset()（reset 会清 searchText/selectedTags/queryParams，进入 folder-list 不需要这些）
  // 改用更精细的清理：resetAdvancedPanel 仅清 queryParams + 关闭面板，再用静默方法清 selectedFavorite
  // 这样 includeOnline 等全局偏好保留（composable 持久化），且不触发空搜索请求
  queryRef.value?.resetAdvancedPanel()
  queryRef.value?._clearSelectedFavoriteNoSearch?.()
  images.value = []
  // 用户在 folder-detail 可能改过 includeOnline，返回时刷新 folder-list 让新设置生效
  folderPage.value = 1
  currentFolders.value = []
  folderHasMore.value = false
  loadFolders(1)
}

// 收藏夹配置现由 useFavoritesConfig composable 全局共享，
// Config.vue（高级功能 tab）修改后 Gallery 自动响应
const handleSourceChange = (newSource) => {
  const prevSource = querySource.value

  // favorites ↔ 非 favorites 切换时清理搜索栏 stale state
  if (prevSource !== newSource && (prevSource === 'favorites' || newSource === 'favorites')) {
    if (newSource === 'favorites' && prevSource !== 'favorites') {
      // 从 local/yande 切到 favorites：清空旧 source 的 searchText/selectedTags/selectedFavorite
      // 进入 favorites-folders 视图后 searchText 会被复用为 favorites-filter 输入，
      // 但旧的 selectedFavorite chip 不应保留（已脱离原 favorite 上下文）。
      queryRef.value?.resetAdvancedPanel()
      queryRef.value?._clearSelectedFavoriteNoSearch?.()
      queryParams.value = {}
    } else if (prevSource === 'favorites' && newSource !== 'favorites') {
      // 切走 favorites 时清空 queryRef 状态（避免 stale tags / favorite 残留）
      queryRef.value?.reset()
      queryRef.value?.resetAdvancedPanel()
      // Gallery 自己的 queryParams 也需要清空——folder-detail 期间
      // AdvancedQuery 通过 handleSearch 注入的 favorites tags / favorite_id 不能
      // 残留用于后续 local/yande 搜索（与 AdvancedQuery 内部 queryParams 是两份独立状态）
      queryParams.value = {}
    }
  }

  querySource.value = newSource
  favoritesView.value = null
  selectedFavoriteFolder.value = null
  currentFolders.value = []
  folderKeyword.value = ''
  if (folderSearchDebounce) {
    clearTimeout(folderSearchDebounce)
    folderSearchDebounce = null
  }
  selectedImages.value = []
  selectAll.value = false
  isIndeterminate.value = false

  if (newSource === 'favorites') {
    favoritesView.value = 'folders'
    loadFolders(1)
    return
  }

  if (Object.keys(queryParams.value).length > 0) {
    queryParams.value.source = newSource
    handleSearch(queryParams.value)
  } else {
    handleSearch({})
  }
}

const loadImages = async (page) => {
  const isFirstPage = page === 1 || currentPage.value === 1
  const targetPage = page !== undefined ? page : currentPage.value
  if (isFirstPage) {
    loading.value = true
  }
  try {
    // v2 我的最爱 / 随机浏览：
    //   - querySource === 'my-favorites'：走独立的 /my_favorites/images 端点
    //     （专门为收藏夹二级瀑布流服务，按收藏时间倒序分页 JOIN yande_data，
    //     响应 shape 与 /gallery/load 对齐，前端无需特殊解析）
    //   - 其它模式走 /gallery/load，按 querySource 注入 random / include_favorite_status
    if (querySource.value === 'my-favorites') {
      const pageSize = queryParams.value.page_size || 20
      const response = await myFavoritesApi.images(targetPage, pageSize)
      const data = response.data
      const imageList = Array.isArray(data) ? data : []
      if (currentPage.value === 1) {
        images.value = imageList
      } else {
        images.value.push(...imageList)
      }
      hasMore.value = Boolean(response.has_more)
      loadError.value = false
      return
    }

    // 防御性拦截：querySource='favorites' 但缺少 folder context（currentFavorite 无合法 id
    // 且 queryParams.favorite_id 也不存在）→ 跳过 /gallery/load，避免触发后端空查询。
    // 正常路径只在 selectFavorite(folder) → handleSearch 时注入 favorite_id；其它路径
    // 误发 source='favorites' 都会因后端 favorite_dao.get_by_id(None) 返回空 → 用户看到 0 图。
    if (
      querySource.value === 'favorites' &&
      !(currentFavorite.value && Number.isInteger(currentFavorite.value.id)) &&
      !Number.isInteger(queryParams.value.favorite_id)
    ) {
      images.value = []
      hasMore.value = false
      loadError.value = false
      return
    }

    // v2 我的最爱 / 随机浏览 / 最近下载（其余模式）：根据当前 querySource 注入额外参数
    //   - random=true: 仅在 querySource === 'random' 时追加（后端走 ORDER BY RANDOM() + DISTINCT image_id）
    //   - sort_by=downloaded_at + sort_order=desc: 仅在 querySource === 'recent-downloads' 时追加
    //     （后端走 download_task JOIN 子查询按 MAX(completed_at) 倒序）
    //   - include_favorite_status=true: 仅在 showHeart && enableMyFavorites 时追加（双判断见 spec §6.6），
    //     后端仍会再判断一次 config.favorites.enable_my_favorites，关闭时强制不连表
    const extraParams = {}
    if (querySource.value === 'random') {
      extraParams.random = true
    }
    if (querySource.value === 'recent-downloads') {
      extraParams.sort_by = 'downloaded_at'
      extraParams.sort_order = 'desc'
    }
    if (enableMyFavorites.value) {
      extraParams.include_favorite_status = true
    }
    // 防御性清理：querySource 切到非 favorites 模式时（前次 favorites folder-detail 残留的
    // queryParams 含 favorite_id / source='favorites'），剔除 favorite_id 并把 source 对齐
    // 当前 querySource。避免 FavoritePanel 虚拟磁贴点击 → router.push({query:{querySource:'random'|'my-favorites'}})
    // 触发 loadImages 时把字符串 favorite_id / 旧 source 发给后端导致 422。
    //
    // querySource='random' / 'recent-downloads' 不直接映射到后端 source（同名字符串）
    // （后端只识别 local/yande/favorites，未知 source 会落到 query_yande_api 在线分支）。
    //   random          → source='local' + random=true → query_local_database(..., random=True) → ORDER BY RANDOM()
    //   recent-downloads → source='local' + sort_by=downloaded_at → download_task JOIN 子查询排序
    const safeBase = { ...queryParams.value }
    if (querySource.value !== 'favorites') {
      delete safeBase.favorite_id
      safeBase.source = (querySource.value === 'random' || querySource.value === 'recent-downloads')
        ? 'local'
        : querySource.value
    }
    const response = await api.post('/gallery/load', {
      ...safeBase,
      ...extraParams,
      page: targetPage
    })
    const data = response.data
    // 重构后 data 直接是图片数组
    const imageList = Array.isArray(data) ? data : []
    if (currentPage.value === 1) {
      images.value = imageList
      const folder = currentFavorite.value
      if (folder && Number.isInteger(folder.id) && querySource.value === 'favorites') {
        // 收藏夹二级页：把 local_count 直接对齐成 /gallery/load 返回的 total。
        //
        // 依据：api/v1/gallery.py 的 favorites 分支是「先取 folder.tags → 查本地
        // (downloaded_only=True)」，所以 response.total 恰好等于「匹配该收藏夹标签的
        // 已下载图片数」= local_count 的定义。一条 UPDATE by PK 搞定（O(1)），
        // 不需要 /favorites/{id}/refresh 那种 tags LIKE + COUNT 全表扫描。
        //
        // 沿革：本分支最早是 534f776 的外层 `if (querySource === 'local')`，
        // 后来被外层 `querySource === 'favorites'` 守卫包住 → 变成永不可达的死代码，
        // 只剩 else 分支的 refreshOnlineCount 还在跑（那是打 yande.re 远程 API 的）。
        folder.local_count = response.total
        setLocalCount(folder.id, response.total).catch(() => {})
        refreshOnlineCount(folder.id).catch(() => {})
      }
    } else {
      images.value.push(...imageList)
    }
    hasMore.value = response.has_more
    loadError.value = false
  } catch (error) {
    if (isFirstPage) {
      // 根据错误码显示不同提示
      const errorCode = error.code || ''
      if (errorCode === '0101') {
        ElMessage.error('网络错误：请检查网络连接')
      } else if (errorCode === '0102') {
        ElMessage.error('代理错误：请检查代理设置')
      } else if (errorCode === '0103') {
        ElMessage.error('请求超时：请稍后重试')
      } else if (error.detail) {
        ElMessage.error(error.detail)
      } else {
        ElMessage.error(error.message || '加载图片失败')
      }
      loadError.value = true
    }
    // 非首页失败不设置 loadError，保持显示"加载更多"
  } finally {
    if (isFirstPage) {
      loading.value = false
    }
  }
}

const loadMore = async () => {
  if (isLoadingMore.value) return
  isLoadingMore.value = true
  currentPage.value++
  try {
    await loadImages()
  } catch {
    // 失败时回退页码
    currentPage.value--
  }
  isLoadingMore.value = false
}

const handleLoadError = async () => {
  // 重新加载当前页
  loadError.value = false
  isLoadingMore.value = true
  try {
    await loadImages()
  } catch {}
  isLoadingMore.value = false
}

const handleImageClick = async (image) => {
  currentImage.value = image
  tagsExpanded.value = false
  infoPanelExpanded.value = false
  previewVisible.value = true
  calculatePreviewSize()
  
  // 获取 tag 类型信息
  //
  // 请求竞态防护：by-names 是异步的，连续快速点开两张图时，先发的响应可能后到，
  // 把后一张图的 tagTypesMap 覆盖成前一张的（tag 配色会串色，新加的「作者」也会
  // 认错人）。用点击瞬间的 image.id 做后到校验，丢弃已过期图片的响应。
  const requestImageId = image.id
  tagTypesMap.value = {}
  if (image.tags && image.tags.length > 0) {
    try {
      const response = await tagCacheApi.getTagsByNames(image.tags)
      if (currentImage.value?.id !== requestImageId) return
      // 重构后 BaseResponse.data 是 {tag_name: type} 格式的字典
      if (response?.data && typeof response.data === 'object') {
        Object.assign(tagTypesMap.value, response.data)
      }
    } catch (e) {
      console.warn('获取 tag 类型失败:', e)
    }
  }
}

const toggleInfoPanel = () => {
  infoPanelExpanded.value = !infoPanelExpanded.value
}

const handleImageSelect = (image, selected) => {
  if (selected) {
    if (!selectedImages.value.find(img => img.id === image.id)) {
      selectedImages.value.push(image)
    }
  } else {
    selectedImages.value = selectedImages.value.filter(img => img.id !== image.id)
  }
  updateSelectionState()
}

const handleSelectAll = (checked) => {
  if (checked) {
    selectedImages.value = [...images.value]
  } else {
    selectedImages.value = []
  }
  updateSelectionState()
}

const updateSelectionState = () => {
  isIndeterminate.value = selectedImages.value.length > 0 && selectedImages.value.length < images.value.length
}

const handleMultiSelectStart = () => {
  // 长按开始多选时的回调
}

const batchDownload = async () => {
  if (selectedImages.value.length === 0) {
    ElMessage.warning('请先选择要下载的图片')
    return
  }

  downloading.value = true

  try {
    const tasks = selectedImages.value.map(image => ({
      image_id: image.id
    }))

    const response = await api.post('/download/task/batch', tasks)
    const { data } = response

    // 乐观标记：任务已入队，UI 立刻转「下载中」（原先批量下载完全不改标识）
    markQueued(tasks.map(t => t.image_id))
    syncDownloadStates()

    ElMessage.success(`成功创建 ${data.task_ids?.length || tasks.length} 个下载任务`)
    selectedImages.value = []
    selectAll.value = false
    isIndeterminate.value = false
  } catch (error) {
    ElMessage.error('批量创建下载任务失败')
  } finally {
    downloading.value = false
  }
}

// 下载完成 → 当前收藏夹角标增量 +N（O(1)，不触发 /favorites/{id}/refresh 的 COUNT 扫描）
//
// 为什么不用 updateLocalCount：那个封装打的是 POST /favorites/{id}/refresh，
// 后端会跑一遍 `tags LIKE ... AND down_flag=1` 的 COUNT（随已下载库线性放大，
// 且路由未走 to_thread 会阻塞事件循环）。这里改走后端已有的
// POST /favorites/{id}/local-count（一条 UPDATE by PK）。
//
// 正确性边界（刻意接受的弱一致）：
//   - 只对「当前收藏夹页里已经加载出来的图」计数，避免给无关收藏夹虚增；
//   - 用户返回收藏夹列表时 handleBackToFolders → loadFolders(1) 会全量重算，
//     任何期间的漂移（漏加/多加）都会在那一步被纠正回真实值。
const handleImagesDownloaded = (ids) => {
  if (!Array.isArray(ids) || ids.length === 0) return
  const folder = currentFavorite.value
  const folderId = Number(folder?.id)
  if (querySource.value !== 'favorites' || !Number.isInteger(folderId)) return

  const visible = new Set(images.value.map((img) => img.id))
  const newly = ids.filter((id) => visible.has(id))
  if (newly.length === 0) return

  folder.local_count = (folder.local_count || 0) + newly.length
  setLocalCount(folderId, folder.local_count).catch(() => {
    // 失败不打扰用户：下次进入收藏夹列表会全量重算
  })
}

const handleDownload = async () => {
  if (!currentImage.value) return
  // 「下载中」期间禁止重复下发（重新下载同样走这里）
  if (downStateOf(currentImage.value) === 'downloading') return

  const imageId = currentImage.value.id
  downloading.value = true
  try {
    await api.post('/download/task', {
      image_id: imageId
    })
    // 不再乐观写 down_flag —— DB 要等下载完成才更新，那样会标出「假已下载」。
    // 改为标记 queued，由 useDownloadState 轮询后端队列收敛为已下载/失败。
    markQueued([imageId])
    syncDownloadStates()
    ElMessage.success('下载任务已创建')
  } catch (error) {
    ElMessage.error('创建下载任务失败')
  } finally {
    downloading.value = false
  }
}

const getRatingType = (rating) => {
  const types = {
    'Safe': 'success',
    'Questionable': 'warning',
    'Explicit': 'danger'
  }
  return types[rating] || 'info'
}

// 根据 tag 类型获取样式（只返回背景和边框，不改文字颜色）
const getTagStyle = (tagName) => {
  const type = tagTypesMap.value[tagName]
  if (type !== undefined && TAG_TYPE_COLORS[type]) {
    const colors = TAG_TYPE_COLORS[type]
    return {
      backgroundColor: colors.bg,
      borderColor: colors.border
    }
  }
  return {}
}

// ---------------------------------------------------------------------------
// 大图详情面板：作者 / 上传用户 / 来源
// ---------------------------------------------------------------------------

// 标签类型常量：1 = 艺术家（artist），见 TAG_TYPE_COLORS 的注释
const TAG_TYPE_ARTIST = 1

/**
 * 「作者」= 当前图片中类型为 artist(1) 的标签名。
 *
 * 数据来自打开大图时已发起的 /tag_cache/tags/by-names 请求
 * （见 handleImageClick → tagTypesMap），响应形如 { tag_name: type }。
 * 该图没有 artist 标签（或标签尚未进缓存）时返回空串，模板回退显示 '-'。
 */
const detailAuthor = computed(() => {
  const tags = currentImage.value?.tags || []
  // Number() 兜底：后端 type 来自 Integer 列，但若某天改成字符串 "1" 也能命中
  return tags.find(tag => Number(tagTypesMap.value[tag]) === TAG_TYPE_ARTIST) || ''
})

/** 「来源」= 原始 source URL，无值时为空串（模板显示 '-'） */
const detailSource = computed(() => (currentImage.value?.source || '').trim())

/**
 * 从 source URL 摘取「一级域名去掉后缀」的部分作为超链接的显示标记：
 *   https://www.pixiv.net/artworks/1  → www.pixiv.net     → pixiv.net → pixiv
 *   http://danbooru.donmai.us/posts/1 → danbooru.donmai.us → donmai.us → donmai
 *   https://twitter.com/u/status/1    → twitter.com       → twitter.com → twitter
 *
 * 规则：去掉 www. 前缀 → 切分 → 取最后两段（一级域名）→ 再丢掉其中的后缀，
 * 最终得到「次级域名」。两步都不可省：
 * - 只取一级域名 → 保留后缀（pixiv.net）
 * - 只丢掉后缀 → danbooru.donmai.us 会退化成 danbooru.donmai（错，主站是 donmai）
 *
 * URL 解析失败时返回空串，由 detailSourceLabel 回退成原始 URL 文本。
 */
const extractSourceLabel = (url) => {
  if (!url) return ''
  let hostname = ''
  try {
    hostname = new URL(url).hostname
  } catch {
    return ''
  }
  const segments = hostname.replace(/^www\./i, '').split('.').filter(Boolean)
  if (segments.length === 0) return ''
  // 单段（如 localhost）既无子域也无后缀，整段即标记
  if (segments.length === 1) return segments[0]
  // slice(-2, -1)：取一级域名的两段，再切掉末段后缀 → 只剩次级域名
  return segments.slice(-2, -1).join('.')
}

/** 超链接显示文本：优先次级域名，解析不出时退回完整 URL */
const detailSourceLabel = computed(
  () => extractSourceLabel(detailSource.value) || detailSource.value
)

const formatFileSize = (bytes) => {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(2)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

const getDetailUrl = (image) => {
  if (!image) return ''
  const favStatusParam = enableMyFavorites.value
    ? `?include_favorite_status=${enableMyFavorites.value}`
    : ''
  // file_url 是本地原图路径，preview_url 是本地预览图路径
  // file_url 不以 http 开头则是本地原图
  if (image.file_url && !image.file_url.startsWith('http')) {
    return `/api/v1/gallery/cache/original/${image.file_url}${favStatusParam}`
  }
  // 在线模式：使用 fetch 缓存原图（避免直接访问远程URL导致CORS）
  return `/api/v1/gallery/cache/preview/fetch/${image.id}${favStatusParam}`
}

// 页面加载时自动查询本地
onMounted(async () => {
  // 行为变更：mount 阶段不再根据 buttonMode 强制覆盖 querySource
  //   之前 buttonMode='default' 会强制 querySource = 'favorites'，无视 gallery_source 持久化值
  //   现统一保持 gallery_source 持久化值（默认 'local'）
  // buttonMode='default' 仍保留运行时切换语义：用户在 Config.vue 改 buttonMode 到 'default' 时
  //   由 Gallery.vue:686-690 的 watch(buttonMode) 触发跳 favorites
  //
  // 修复「刷新页面 vs 点击左上角 tab 收藏夹参数不一致」：
  //   enableMyFavorites 只持久化在后端（GET /config/favorites），localStorage 不含该开关。
  //   之前 mount 立即 handleSearch({})，此时配置尚未返回 → 首屏 /gallery/load 不带
  //   include_favorite_status；用户稍后点击「本地」tab 时配置已就绪 → 同一请求却带
  //   include_favorite_status=true。两条路径参数不一致（刷新后首屏红心状态缺失）。
  //   现等待配置落定再做首屏加载，保证两条路径携带一致的收藏夹参数。
  const startedInFavorites = querySource.value === 'favorites'
  if (startedInFavorites) {
    folderLoading.value = true
  } else {
    loading.value = true
  }
  await whenFavoritesConfigReady()
  if (startedInFavorites) {
    favoritesView.value = 'folders'
    loadFolders(1)
  } else if (querySource.value === 'favorites') {
    // 等待配置期间 watch(buttonMode='default') 已切到 favorites 并触发过 loadFolders，
    // 不再重复加载；回滚预置的 loading（favorites 视图用的是 folderLoading）
    loading.value = false
  } else {
    handleSearch({})
  }
  // 窗口尺寸变化时重新计算预览尺寸
  window.addEventListener('resize', () => {
    if (previewVisible.value && currentImage.value) {
      calculatePreviewSize()
    }
  })
  // 键盘左右箭头切换图片
  window.addEventListener('keydown', handleKeydown)
  // 启动下载状态轮询（单例，引用计数）：既对账本前端下的任务，
  // 也发现「收藏自动下载」这类后端触发的任务
  startDownloadSync()
  unsubscribeDownloadCompleted = onDownloadCompleted(handleImagesDownloaded)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
  stopDownloadSync()
  unsubscribeDownloadCompleted?.()
  unsubscribeDownloadCompleted = null
})

// 键盘事件处理
const handleKeydown = (e) => {
  if (!previewVisible.value || !currentImage.value) return
  if (e.key === 'ArrowLeft') {
    goToPrevImage()
    e.preventDefault()
  } else if (e.key === 'ArrowRight') {
    goToNextImage()
    e.preventDefault()
  }
}
</script>

<style scoped>
.gallery-page {
  min-height: 100vh;
  width: 100vw;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
}

.top-toolbar {
  position: sticky;
  top: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: rgba(var(--bg-secondary-rgb, 255, 255, 255), 0.75);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.15);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  z-index: 100;
}

/* 深色模式 */
html.dark-mode .top-toolbar {
  background: rgba(var(--bg-secondary-rgb, 45, 45, 45), 0.75);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.toolbar-right :deep(.el-button) {
  background: var(--bg-tertiary);
  border-color: var(--border-color);
  color: var(--text-primary);
}

.toolbar-right :deep(.el-button:hover) {
  background: var(--bg-primary);
  border-color: #409EFF;
  color: #409EFF;
}

/* 移动端圆点菜单 */
.mobile-menu-btn {
  font-size: 18px;
  font-weight: bold;
}

.menu-dots {
  display: inline-block;
  transform: rotate(90deg);
  letter-spacing: 2px;
}

.mobile-expand-menu {
  position: absolute;
  top: 100%;
  right: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  background: var(--bg-secondary);
  border-radius: 12px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
  z-index: 101;
}

/* :deep 必需：DownloadIndicator 内部的 el-button 属于子组件作用域，
   普通的 scoped 选择器匹配不到，暗色模式下会退回 EP 默认白底 */
.mobile-expand-menu :deep(.el-button) {
  background: var(--bg-tertiary);
  border-color: var(--border-color);
}

.menu-expand-enter-active,
.menu-expand-leave-active {
  transition: all 0.2s ease;
}

.menu-expand-enter-from,
.menu-expand-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

.mode-buttons {
  flex-shrink: 0;
}

.mode-buttons :deep(.el-button) {
  background: var(--bg-tertiary);
  border-color: var(--border-color);
  color: var(--text-secondary);
}

.safe-mode-btn {
  margin-left: 0 !important;
}

/* tile 尺寸 4 档切换（仅 favorites folders 视图显示） */
.tile-size-group {
  margin-left: 8px;
  flex-shrink: 0;
}

.tile-size-group :deep(.el-radio-button__inner) {
  padding: 6px 10px;
  font-size: 12px;
}

.mode-buttons :deep(.el-button:hover) {
  color: #409EFF;
  border-color: #409EFF;
}

.mode-buttons :deep(.el-button--primary) {
  background: #409EFF;
  border-color: #409EFF;
  color: white;
}

/* 深色模式下选中按钮 */
html.dark-mode .mode-buttons :deep(.el-button--primary) {
  background: #1a4fc4;
  border-color: #1a4fc4;
  color: white;
}

/* 深色模式下省流按钮 */
html.dark-mode .toolbar-left :deep(.el-button--warning),
html.dark-mode .toolbar-left :deep(.el-button[type="warning"]) {
  background: #993300 !important;
  border-color: #993300 !important;
  color: white !important;
}

html.dark-mode .toolbar-left :deep(.el-button--warning:hover),
html.dark-mode .toolbar-left :deep(.el-button[type="warning"]:hover) {
  background: #AA4400 !important;
  border-color: #AA4400 !important;
  color: white !important;
}

/* 深色模式下省流按钮未选中状态 */
html.dark-mode .toolbar-left :deep(.el-button.is-circle) {
  background: var(--bg-tertiary);
  border-color: var(--border-color);
  color: var(--text-primary);
}

html.dark-mode .toolbar-left :deep(.el-button.is-circle:hover) {
  background: var(--bg-primary);
  border-color: #E6A23C;
  color: #E6A23C;
}

/* 深色模式下安全模式按钮 */
html.dark-mode .toolbar-left :deep(.el-button--danger),
html.dark-mode .toolbar-left :deep(.el-button[type="danger"]) {
  background: #A02020 !important;
  border-color: #A02020 !important;
  color: white !important;
}

html.dark-mode .toolbar-left :deep(.el-button--danger:hover),
html.dark-mode .toolbar-left :deep(.el-button[type="danger"]:hover) {
  background: #B03030 !important;
  border-color: #B03030 !important;
  color: white !important;
}

.selection-toolbar {
  padding: 8px 20px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  gap: 15px;
}

.selection-info {
  font-size: 13px;
  color: var(--text-muted);
}

.gallery-content {
  flex: 1;
  padding: 15px 20px 80px;
  overflow-y: auto;
}

/* 左下角多选操作按钮 */
.multi-select-actions {
  position: fixed;
  left: 20px;
  bottom: 80px;
  display: flex;
  flex-direction: row;
  align-items: flex-end;
  gap: 12px;
  z-index: 1000;
}

.action-column {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.download-btn-large {
  width: 52px;
  height: 52px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}

.action-buttons-vertical {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.action-btn {
  width: 44px;
  height: 44px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.selection-count {
  background: var(--el-color-primary);
  color: white;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: bold;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

html.dark-mode .action-btn,
html.dark-mode .download-btn-large {
  background: var(--bg-secondary);
  border-color: var(--border-color);
  color: var(--text-primary);
}

html.dark-mode .action-btn:hover {
  background: var(--bg-tertiary);
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}

html.dark-mode .selection-count {
  background: var(--el-color-primary);
}

/* 图片预览弹窗 - 自定义浮层 */
.image-preview-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 2000;
  background: rgba(0, 0, 0, 0.75);
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 图片容器 - 动态尺寸（由JS计算保持图片比例），图片自适应缩放 */
.float-image-wrapper {
  position: relative;
  border-radius: 12px;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.9);
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 图片 - 适应容器 */
.float-main-image {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}

.float-main-image :deep(.el-image__inner) {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.float-main-image :deep(.el-image__error) {
  background: transparent;
}

/* 左右导航按钮 */
.image-nav-btn {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  z-index: 20;
  width: 40px;
  height: 40px;
  opacity: 0.6;
  transition: opacity 0.2s, transform 0.2s;
}

.image-nav-btn:hover {
  opacity: 1;
  transform: translateY(-50%) scale(1.1);
}

.image-nav-btn-left {
  left: 16px;
}

.image-nav-btn-right {
  right: 16px;
}

.image-nav-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

/* 顶部信息栏 */
.float-header {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
}

.float-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.float-id {
  font-weight: bold;
  color: rgba(255, 255, 255, 0.95);
  font-size: 14px;
}

.float-size {
  color: rgba(255, 255, 255, 0.7);
  font-size: 13px;
}

.float-close-btn {
  background: rgba(255, 255, 255, 0.1) !important;
  border-color: rgba(255, 255, 255, 0.15) !important;
  color: rgba(255, 255, 255, 0.9) !important;
}

.float-close-btn:hover {
  background: rgba(255, 255, 255, 0.2) !important;
}

/* 底部操作栏 */
.float-footer {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
}

.float-footer-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* 大图底部的收藏标识：紧跟下载按钮，视觉上与 footer 右侧文字同色。
   flex-shrink:0 防止「已下载」分支变长时星标被压扁。 */
.float-heart {
  flex-shrink: 0;
  color: rgba(255, 255, 255, 0.85);
}

.float-footer-right {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 4px;
  transition: background 0.2s;
}

.float-footer-right:hover {
  background: rgba(255, 255, 255, 0.1);
}

.float-expand-text {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.8);
}

.float-expand-icon {
  color: rgba(255, 255, 255, 0.8);
}

.float-download-btn {
  background: rgba(64, 158, 255, 0.85) !important;
  border-color: rgba(64, 158, 255, 0.85) !important;
  color: white !important;
}

.float-download-btn:hover:not(:disabled) {
  background: rgba(64, 158, 255, 1) !important;
}

.float-download-btn:disabled {
  opacity: 0.8 !important;
  cursor: not-allowed !important;
}

.download-loading {
  display: flex;
  align-items: center;
  gap: 6px;
}

.float-redownload-btn {
  background: rgba(255, 255, 255, 0.1) !important;
  border-color: rgba(255, 255, 255, 0.15) !important;
  color: rgba(255, 255, 255, 0.9) !important;
  width: 32px;
  height: 32px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.float-downloaded-tag {
  background: rgba(103, 194, 58, 0.85) !important;
  border-color: rgba(103, 194, 58, 0.85) !important;
  color: white !important;
}

/* 详情面板 - 向上展开 */
.float-detail-panel {
  position: absolute;
  bottom: 48px;
  left: 0;
  right: 0;
  z-index: 9;
  padding: 14px 16px;
  background: rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  max-height: 35vh;
  overflow-y: auto;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 12px;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.detail-label {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.5);
}

.detail-value {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.9);
  word-break: break-all;
}

.detail-value.md5 {
  font-size: 11px;
  font-family: monospace;
}

/* 「来源」超链接：与 detail-value 同色系但可点击，避免抢过 MD5 等关键信息 */
.detail-source-link {
  color: var(--el-color-primary, #409EFF);
  text-decoration: none;
  word-break: break-all;
  transition: color 0.15s;
}
.detail-source-link:hover {
  color: var(--el-color-primary-light-3, #79bbff);
  text-decoration: underline;
}

.detail-tags-area {
  margin-top: 4px;
}

.detail-tags-label {
  font-size: 12px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.7);
  margin-bottom: 8px;
}

.detail-tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-height: 80px;
  overflow-y: auto;
}

.detail-tag {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.15);
  color: rgba(255, 255, 255, 0.9);
  cursor: pointer;
  transition: all 0.2s ease;
}

.detail-tag:hover {
  background: rgba(255, 255, 255, 0.2) !important;
}

/* 图片预览浮层淡入淡出 */
.preview-fade-enter-active,
.preview-fade-leave-active {
  transition: opacity 0.25s ease;
}
.preview-fade-enter-from,
.preview-fade-leave-to {
  opacity: 0;
}

/* 详情面板过渡动画 */
.detail-slide-up-enter-active,
.detail-slide-up-leave-active {
  transition: all 0.2s ease;
}

.detail-slide-up-enter-from,
.detail-slide-up-leave-to {
  opacity: 0;
  transform: translateY(20px);
}

/* 深色模式适配 */
html.dark-mode .float-header,
html.dark-mode .float-footer,
html.dark-mode .float-detail-panel {
  /* 保持一致的极透明效果 */
}

html.dark-mode .image-preview-overlay {
  background: rgba(0, 0, 0, 0.86);
}

/* 图片自适应浅色/深色文字 */
.float-header.overlay-light,
.float-footer.overlay-light,
.float-detail-panel.overlay-light {
  background: rgba(0, 0, 0, 0.45);
}

.float-header.overlay-light .float-id,
.float-footer.overlay-light .float-id {
  color: rgba(255, 255, 255, 0.95);
}

.float-header.overlay-light .float-size,
.float-footer.overlay-light .float-size,
.float-footer.overlay-light .float-expand-text,
.float-footer.overlay-light .float-expand-icon {
  color: rgba(255, 255, 255, 0.8);
}

.float-header.overlay-light .float-close-btn,
.float-footer.overlay-light .float-redownload-btn {
  background: rgba(0, 0, 0, 0.3) !important;
  border-color: rgba(255, 255, 255, 0.25) !important;
  color: rgba(255, 255, 255, 0.9) !important;
}

.float-header.overlay-light .float-close-btn:hover,
.float-footer.overlay-light .float-redownload-btn:hover {
  background: rgba(0, 0, 0, 0.5) !important;
}

.float-footer.overlay-light .float-footer-right:hover {
  background: rgba(0, 0, 0, 0.2);
}

/* 详情面板浅色文字 */
.float-detail-panel.overlay-light .detail-label {
  color: rgba(255, 255, 255, 0.6);
}

.float-detail-panel.overlay-light .detail-value {
  color: rgba(255, 255, 255, 0.9);
}

.float-detail-panel.overlay-light .detail-tags-label {
  color: rgba(255, 255, 255, 0.8);
}

.float-detail-panel.overlay-light .detail-tags-list :deep(.el-tag) {
  background: rgba(0, 0, 0, 0.4);
  border-color: rgba(255, 255, 255, 0.2);
  color: rgba(255, 255, 255, 0.9);
}

/* 中心对话框样式 */
.center-dialog {
  border-radius: 12px;
}

.center-dialog :deep(.el-dialog) {
  border-radius: 12px;
  overflow: hidden;
  background: var(--bg-secondary);
}

.center-dialog :deep(.el-dialog__header) {
  padding: 15px 20px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-secondary);
}

.center-dialog :deep(.el-dialog__body) {
  padding: 0;
  max-height: 70vh;
  overflow-y: auto;
  background: var(--bg-secondary);
}

.center-dialog :deep(.el-dialog__footer) {
  padding: 15px 20px;
  border-top: 1px solid var(--border-color);
  background: var(--bg-secondary);
}

</style>
