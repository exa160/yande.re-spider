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
            :type="querySource === 'favorites' ? 'primary' : ''"
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
              <el-button circle @click="showDownloadDialog = true; mobileMenuExpanded = false">
                <el-icon><Download /></el-icon>
              </el-button>
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
          <el-tooltip content="下载管理" :effect="isDarkMode ? 'dark' : 'light'" :trigger="isTouchDevice ? 'click' : 'hover'" :auto-close="isTouchDevice ? 1000 : 0" :show-after="isTouchDevice ? 0 : 100" :enterable="false">
            <el-button circle @click="showDownloadDialog = true">
              <el-icon><Download /></el-icon>
            </el-button>
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
      :visible="querySource === 'favorites' && favoritesView === 'folder-detail'"
      @click="handleBackToFolders"
    />
    <AdvancedQuery
      @search="handleSearch"
      ref="queryRef"
      :source-mode="querySource"
      :mode="modeProp"
      :lock-favorite-chip="favoritesView === 'folder-detail'"
    />

    <!-- 瀑布流图库组件 -->
    <div class="gallery-content">
      <!-- 收藏夹文件夹列表 -->
      <template v-if="querySource === 'favorites' && favoritesView === 'folders'">
        <WaterfallGallery
          item-type="folder"
          :images="currentFolders"
          :loading="folderLoading"
          :has-more="folderHasMore"
          :is-loading-more="false"
          :load-error="false"
          :selected-images="[]"
          :selectable="false"
          :source-mode="'favorites'"
          :save-data-mode="saveDataMode"
          :safe-mode="safeMode"
          @load-more="handleFolderScrollBottom"
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
          :source-mode="querySource"
          :save-data-mode="saveDataMode"
          :safe-mode="safeMode"
          @image-click="handleImageClick"
          @image-select="handleImageSelect"
          @load-more="loadMore"
          @load-error="handleLoadError"
          @multi-select-start="handleMultiSelectStart"
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
                <el-tag :type="getRatingType(currentImage.rating)" size="small">
                  {{ currentImage.rating }}
                </el-tag>
                <span class="float-size">{{ currentImage.width }} × {{ currentImage.height }}</span>
              </div>
              <el-button circle @click="previewVisible = false" class="float-close-btn">
                <el-icon><Close /></el-icon>
              </el-button>
            </div>

          <div class="float-footer" :class="`overlay-${overlayColorScheme}`">
            <div class="float-footer-left">
              <template v-if="!currentImage.down_flag">
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
              <template v-else>
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
                  <span class="detail-value">{{ currentImage.author }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">MD5</span>
                  <span class="detail-value md5">{{ currentImage.md5 }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">时间</span>
                  <span class="detail-value">{{ currentImage.created_at }}</span>
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
import AdvancedQuery from '@/components/AdvancedQuery.vue'
import WaterfallGallery from '@/components/WaterfallGallery.vue'
import FolderTile from '@/components/FolderTile.vue'
import BackButton from '@/components/BackButton.vue'
import DownloadManager from '@/views/Download.vue'
import ConfigPanel from '@/views/Config.vue'
import api from '@/api'
import { tagCacheApi } from '@/api/tagCache'
import { updateOnlineCount, updateLocalCount, refreshOnlineCount, getFoldersWithPreview } from '@/api/favorites'
import { useFavoritesConfig } from '@/composables/useFavoritesConfig'

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
const allFolders = ref([])  // 未过滤的完整列表（favorites-filter 用）
const folderLoading = ref(false)
const folderHasMore = ref(false)
const folderPage = ref(1)
const FOLDER_PAGE_SIZE = 20

// 从 localStorage 读取保存的设置，默认本地模式
const querySource = ref(localStorage.getItem('gallery_source') || 'local')
const saveDataMode = ref(localStorage.getItem('gallery_saveData') === 'true')

// 收藏夹 UI 配置（singleton composable，跨组件共享 + localStorage 持久化）
// - buttonMode: 'hidden' / 'shown' / 'default'（default → 进首页直接跳 favorites）
// - tileSize:   'adaptive' / '4' / '6' / '8'
// 持久化 + 旧 key `gallery_tile_size` 向后兼容由 composable 内部处理
const { buttonMode, tileSize } = useFavoritesConfig()

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

const previewVisible = ref(false)
const currentImage = ref(null)
const previewContainerStyle = ref({})
const downloading = ref(false)
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
  let params
  if (searchData.mode) {
    params = { ...searchData.params, source: searchData.mode }
    // source='favorites' 时注入 favorite_id（后端用其定位 folder → 取其 tags）
    if (searchData.mode === 'favorites' && searchData.favorite?.id) {
      params.favorite_id = searchData.favorite.id
    }
  } else {
    params = { ...searchData, source: querySource.value }
    if (params.source === 'favorites' && searchData.favorite?.id) {
      params.favorite_id = searchData.favorite.id
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
  if (folderLoading.value) return
  folderLoading.value = true
  try {
    // 前端 radio 用 4/6/8 直觉数字，契约要 small/medium/large（spec §3.2）
    const apiTileSize = API_TILE_SIZE[tileSize.value] || tileSize.value
    const res = await getFoldersWithPreview(page, FOLDER_PAGE_SIZE, apiTileSize)
    const { items, has_more } = res.data
    if (page === 1) {
      allFolders.value = items
      currentFolders.value = items
    } else {
      allFolders.value.push(...items)
      currentFolders.value.push(...items)
    }
    folderHasMore.value = has_more
    folderPage.value = page
  } catch (e) {
    ElMessage.error('加载收藏夹失败：' + (e?.message || '未知错误'))
  } finally {
    folderLoading.value = false
  }
}

// 收藏夹一级搜索过滤已迁到 AdvancedQuery 内部处理（c6330bb 前的旧逻辑不再使用）
const handleFolderScrollBottom = () => {
  if (folderHasMore.value && !folderLoading.value) {
    loadFolders(folderPage.value + 1)
  }
}

const handleFolderClick = (folder) => {
  selectedFavoriteFolder.value = folder
  favoritesView.value = 'folder-detail'
  // 复用 AdvancedQuery 的 selectFavorite 设置搜索栏状态
  queryRef.value?.selectFavorite(folder)
}

const handleBackToFolders = () => {
  selectedFavoriteFolder.value = null
  favoritesView.value = 'folders'
  queryRef.value?.reset()
  images.value = []
}

// 收藏夹配置现由 useFavoritesConfig composable 全局共享，
// Config.vue（高级功能 tab）修改后 Gallery 自动响应
const handleSourceChange = (newSource) => {
  const prevSource = querySource.value

  // 切走 favorites 时清空 queryRef 状态（避免 stale tags / favorite 残留）
  if (prevSource === 'favorites' && newSource !== 'favorites') {
    queryRef.value?.reset()
    queryRef.value?.resetAdvancedPanel()
    // Gallery 自己的 queryParams 也需要清空——folder-detail 期间
    // AdvancedQuery 通过 handleSearch 注入的 favorites tags / favorite_id 不能
    // 残留用于后续 local/yande 搜索（与 AdvancedQuery 内部 queryParams 是两份独立状态）
    queryParams.value = {}
  }

  querySource.value = newSource
  favoritesView.value = null
  selectedFavoriteFolder.value = null
  currentFolders.value = []
  allFolders.value = []
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
    const response = await api.post('/gallery/load', {
      ...queryParams.value,
      page: targetPage
    })
    const data = response.data
    // 重构后 data 直接是图片数组
    const imageList = Array.isArray(data) ? data : []
    if (currentPage.value === 1) {
      images.value = imageList
      if (currentFavorite.value) {
        if (querySource.value === 'local') {
          updateLocalCount(currentFavorite.value.id).catch(() => {})
        } else {
          refreshOnlineCount(currentFavorite.value.id).catch(() => {})
        }
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
  if (image.tags && image.tags.length > 0) {
    try {
      const response = await tagCacheApi.getTagsByNames(image.tags)
      tagTypesMap.value = {}
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

const handleDownload = async () => {
  if (!currentImage.value) return

  downloading.value = true
  try {
    await api.post('/download/task', {
      image_id: currentImage.value.id
    })
    ElMessage.success('下载任务已创建')
    currentImage.value.down_flag = true
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

const formatFileSize = (bytes) => {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(2)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

const getDetailUrl = (image) => {
  if (!image) return ''
  // file_url 是本地原图路径，preview_url 是本地预览图路径
  // file_url 不以 http 开头则是本地原图
  if (image.file_url && !image.file_url.startsWith('http')) {
    return `/api/v1/gallery/cache/original/${image.file_url}`
  }
  // 在线模式：使用 fetch 缓存原图（避免直接访问远程URL导致CORS）
  return `/api/v1/gallery/cache/preview/fetch/${image.id}`
}

// 页面加载时自动查询本地
onMounted(() => {
  // buttonMode 决定初始视图：
  //   'default' → 直接进 favorites（无论 gallery_source 持久化值）
  //   'shown'/'hidden' → 保持 gallery_source 持久化值（默认 'local'）
  if (buttonMode.value === 'default') {
    querySource.value = 'favorites'
    favoritesView.value = 'folders'
    loadFolders(1)
  } else if (querySource.value === 'favorites') {
    favoritesView.value = 'folders'
    loadFolders(1)
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
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
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

.mobile-expand-menu .el-button {
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
