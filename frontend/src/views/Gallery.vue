<template>
  <div class="gallery-page">
    <!-- 顶部工具栏 -->
    <div class="top-toolbar">
      <!-- 搜索框 + 模式按钮 -->
      <div class="toolbar-left">
        <AdvancedQuery @search="handleSearch" ref="queryRef" :source-mode="querySource" />
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
        </el-button-group>
        <el-tooltip content="省流模式">
          <el-button 
            :type="saveDataMode ? 'warning' : ''"
            circle
            @click="saveDataMode = !saveDataMode"
          >
            <el-icon><Connection /></el-icon>
          </el-button>
        </el-tooltip>
      </div>
      <!-- 右侧工具按钮 -->
      <div class="toolbar-right">
        <el-tooltip content="夜间模式">
          <el-button circle @click="toggleDarkMode">
            <el-icon v-if="isDarkMode"><Sunny /></el-icon>
            <el-icon v-else><Moon /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip content="下载管理">
          <el-button circle @click="showDownloadDialog = true">
            <el-icon><Download /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip content="配置">
          <el-button circle @click="showConfigDialog = true">
            <el-icon><Setting /></el-icon>
          </el-button>
        </el-tooltip>
      </div>
    </div>

    <!-- 瀑布流图库组件 -->
    <div class="gallery-content">
      <WaterfallGallery
        :images="images"
        :loading="loading"
        :has-more="hasMore"
        :selected-images="selectedImages"
        :selectable="querySource === 'yande'"
        :source-mode="querySource"
        :save-data-mode="saveDataMode"
        @image-click="handleImageClick"
        @image-select="handleImageSelect"
        @load-more="loadMore"
        @multi-select-start="handleMultiSelectStart"
      />
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

    <!-- 图片预览对话框 - 无边框抽屉式 -->
    <el-dialog
      v-model="previewVisible"
      :show-close="false"
      class="preview-drawer-dialog"
      :close-on-click-modal="true"
      :width="'100%'"
      :fullscreen="true"
    >
      <div v-if="currentImage" class="preview-drawer-container">
        <!-- 顶部透明工具栏 -->
        <div class="preview-topbar">
          <div class="topbar-left">
            <span class="preview-id">ID: {{ currentImage.id }}</span>
            <el-tag :type="getRatingType(currentImage.rating)" size="small">
              {{ currentImage.rating }}
            </el-tag>
            <span class="preview-size">{{ currentImage.width }} × {{ currentImage.height }}</span>
          </div>
          <div class="topbar-right">
            <el-button circle @click="previewVisible = false" class="close-btn">
              <el-icon><Close /></el-icon>
            </el-button>
          </div>
        </div>

        <!-- 图片区域 - 自适应高度，展开时收缩 -->
        <div 
          class="preview-image-wrapper"
          :style="{ flex: infoPanelExpanded ? '0 0 50%' : '1' }"
        >
          <el-image
            :src="getDetailUrl(currentImage)"
            :preview-src-list="[getDetailUrl(currentImage)]"
            fit="contain"
            class="preview-main-image"
            :zoom-rate="1.1"
            :preview-teleported="true"
          />
        </div>

        <!-- 底部抽屉面板 -->
        <div 
          class="preview-drawer"
          :class="{ expanded: infoPanelExpanded }"
          @click="toggleInfoPanel"
        >
          <!-- 抽屉把手 -->
          <div class="drawer-handle">
            <div class="handle-bar"></div>
          </div>

          <!-- 抽屉头部 - 下载按钮和展开提示 -->
          <div class="drawer-header">
            <div class="drawer-header-left">
              <template v-if="!currentImage.is_downloaded">
                <el-button 
                  type="primary" 
                  @click.stop="handleDownload" 
                  :loading="downloading" 
                  class="download-btn"
                >
                  <el-icon><Download /></el-icon>
                  下载原图
                </el-button>
              </template>
              <template v-else>
                <el-button 
                  @click.stop="handleDownload" 
                  :loading="downloading" 
                  class="re-download-btn"
                  title="重新下载"
                >
                  <el-icon><Download /></el-icon>
                </el-button>
                <el-tag type="success" size="large" class="downloaded-tag">
                  <el-icon><Check /></el-icon>
                  已下载
                </el-tag>
              </template>
            </div>
            <div class="drawer-header-right">
              <span class="expand-hint">
                {{ infoPanelExpanded ? '点击收起' : '点击展开详情' }}
              </span>
              <el-icon class="expand-icon">
                <ArrowUp v-if="infoPanelExpanded" />
                <ArrowDown v-else />
              </el-icon>
            </div>
          </div>

          <!-- 抽屉内容 - 详情信息 -->
          <transition name="drawer-content">
            <div v-if="infoPanelExpanded" class="drawer-content">
              <div class="info-grid">
                <div class="info-item">
                  <span class="info-label">大小</span>
                  <span class="info-value">{{ formatFileSize(currentImage.file_size) }}</span>
                </div>
                <div class="info-item">
                  <span class="info-label">作者</span>
                  <span class="info-value">{{ currentImage.author }}</span>
                </div>
                <div class="info-item full-width">
                  <span class="info-label">MD5</span>
                  <span class="info-value md5">{{ currentImage.md5 }}</span>
                </div>
                <div class="info-item">
                  <span class="info-label">时间</span>
                  <span class="info-value">{{ currentImage.created_at }}</span>
                </div>
              </div>
              
              <div class="tags-area">
                <div class="tags-header">标签 ({{ currentImage.tags?.length || 0 }})</div>
                <div class="tags-cloud">
                  <el-tag
                    v-for="tag in currentImage.tags"
                    :key="tag"
                    size="default"
                    class="tag-chip"
                  >
                    {{ tag }}
                  </el-tag>
                </div>
              </div>
            </div>
          </transition>
        </div>
      </div>
    </el-dialog>

    <!-- 下载管理对话框 -->
    <el-dialog
      v-model="showDownloadDialog"
      title="下载管理"
      width="80%"
      class="center-dialog"
    >
      <DownloadManager />
    </el-dialog>

    <!-- 配置对话框 -->
    <el-dialog
      v-model="showConfigDialog"
      title="配置"
      width="80%"
      class="center-dialog"
    >
      <ConfigPanel />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Check, Connection, Setting, Sunny, Moon, Close, Select, ArrowUp, ArrowDown } from '@element-plus/icons-vue'
import AdvancedQuery from '@/components/AdvancedQuery.vue'
import WaterfallGallery from '@/components/WaterfallGallery.vue'
import DownloadManager from '@/views/Download.vue'
import ConfigPanel from '@/views/Config.vue'
import api from '@/api'

const images = ref([])
const loading = ref(false)
const hasMore = ref(false)
const currentPage = ref(1)
const queryParams = ref({})

// 从 localStorage 读取保存的设置，默认本地模式
const querySource = ref(localStorage.getItem('gallery_source') || 'local')
const saveDataMode = ref(localStorage.getItem('gallery_saveData') === 'true')

const previewVisible = ref(false)
const currentImage = ref(null)
const downloading = ref(false)
const tagsExpanded = ref(false)
const infoPanelExpanded = ref(false)

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

// 监听模式变化，保存到 localStorage
const stopSourceWatch = watch(querySource, (val) => {
  localStorage.setItem('gallery_source', val)
})

const stopSaveDataWatch = watch(saveDataMode, (val) => {
  localStorage.setItem('gallery_saveData', val ? 'true' : 'false')
})

onUnmounted(() => {
  stopSourceWatch()
  stopSaveDataWatch()
})

const handleSearch = async (searchData) => {
  let params
  if (searchData.mode) {
    // 来自高级搜索组件的新格式
    params = { ...searchData.params, source: searchData.mode }
  } else {
    // 兼容旧格式
    params = { ...searchData, source: querySource.value }
  }
  queryParams.value = params
  currentPage.value = 1
  images.value = []
  selectedImages.value = []
  selectAll.value = false
  await loadImages()
}

const handleSourceChange = (newSource) => {
  querySource.value = newSource
  selectedImages.value = []  // 清空选择
  selectAll.value = false
  isIndeterminate.value = false
  if (Object.keys(queryParams.value).length > 0) {
    queryParams.value.source = newSource
    handleSearch(queryParams.value)
  } else {
    // 初始加载
    handleSearch({})
  }
}

const loadImages = async () => {
  const isFirstPage = currentPage.value === 1
  if (isFirstPage) {
    loading.value = true
  }
  try {
    const response = await api.post('/gallery/load', {
      ...queryParams.value,
      page: currentPage.value
    })
    if (currentPage.value === 1) {
      images.value = response.images
    } else {
      images.value.push(...response.images)
    }
    hasMore.value = response.has_more
  } catch (error) {
    ElMessage.error('加载图片失败')
  } finally {
    if (isFirstPage) {
      loading.value = false
    }
  }
}

const loadMore = async () => {
  currentPage.value++
  await loadImages()
}

const handleImageClick = (image) => {
  currentImage.value = image
  tagsExpanded.value = false
  infoPanelExpanded.value = false
  previewVisible.value = true
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
  let successCount = 0
  let failCount = 0

  try {
    for (const image of selectedImages.value) {
      try {
        await api.post('/download/task', {
          image_id: image.id,
          file_url: image.file_url,
          save_path: './downloads',
          file_name: `${image.id}.${image.file_ext || 'jpg'}`,
          thread_num: 4,
          tags: image.tags?.join ? image.tags.join(' ') : image.tags,
          width: image.width,
          height: image.height,
          rating: image.rating,
          author: image.author,
          md5: image.md5,
          total_size: image.file_size
        })
        successCount++
      } catch (e) {
        failCount++
      }
    }
    ElMessage.success(`成功创建 ${successCount} 个下载任务${failCount > 0 ? `, ${failCount} 个失败` : ''}`)
    selectedImages.value = []
    selectAll.value = false
    isIndeterminate.value = false
  } finally {
    downloading.value = false
  }
}

const handleDownload = async () => {
  if (!currentImage.value) return

  downloading.value = true
  try {
    await api.post('/download/task', {
      image_id: currentImage.value.id,
      file_url: currentImage.value.file_url,
      save_path: './downloads',
      file_name: `${currentImage.value.id}.${currentImage.value.file_ext || 'jpg'}`,
      thread_num: 4,
      tags: currentImage.value.tags?.join ? currentImage.value.tags.join(' ') : currentImage.value.tags,
      width: currentImage.value.width,
      height: currentImage.value.height,
      rating: currentImage.value.rating,
      author: currentImage.value.author,
      md5: currentImage.value.md5,
      total_size: currentImage.value.file_size
    })
    ElMessage.success('下载任务已创建')
    currentImage.value.is_downloaded = true
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

const formatFileSize = (bytes) => {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(2)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

const getDetailUrl = (image) => {
  if (!image) return ''
  if (image.local_file_path) {
    const filename = `${image.id}.${image.file_ext || 'jpg'}`
    return `/api/v1/gallery/cache/original/${filename}`
  }
  if (image.local_preview_path) {
    const filename = `${image.id}.${image.file_ext || 'jpg'}`
    return `/api/v1/gallery/cache/preview/${filename}`
  }
  // 在线模式：使用缓存的预览图API
  if (image.preview_url) {
    return `/api/v1/gallery/cache/preview/fetch/${image.id}?preview_url=${encodeURIComponent(image.preview_url)}&file_ext=${image.file_ext || 'jpg'}`
  }
  return image.file_url
}

// 页面加载时自动查询本地
onMounted(() => {
  handleSearch({})
})
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
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  z-index: 100;
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

.mode-buttons {
  flex-shrink: 0;
}

.mode-buttons :deep(.el-button) {
  background: var(--bg-tertiary);
  border-color: var(--border-color);
  color: var(--text-secondary);
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
  background: #CC5500 !important;
  border-color: #CC5500 !important;
  color: white !important;
}

html.dark-mode .toolbar-left :deep(.el-button--warning:hover),
html.dark-mode .toolbar-left :deep(.el-button[type="warning"]:hover) {
  background: #DD6600 !important;
  border-color: #DD6600 !important;
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
  padding: 15px 20px;
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

/* ===================== 无框抽屉式预览对话框 ===================== */
.preview-drawer-dialog {
  background: transparent !important;
}

.preview-drawer-dialog :deep(.el-dialog) {
  background: transparent !important;
  box-shadow: none !important;
  border-radius: 0 !important;
  overflow: hidden !important;
}

.preview-drawer-dialog :deep(.el-dialog__header) {
  display: none !important;
}

.preview-drawer-dialog :deep(.el-dialog__body) {
  padding: 0 !important;
  overflow: hidden !important;
}

/* 预览容器 - 垂直布局 */
.preview-drawer-container {
  width: 100vw;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
  position: relative;
}

/* 顶部工具栏 - 透明背景 */
.preview-topbar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  z-index: 10;
  background: linear-gradient(to bottom, rgba(0,0,0,0.5), transparent);
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.preview-id {
  font-weight: 600;
  color: white;
  text-shadow: 0 1px 3px rgba(0,0,0,0.5);
}

.preview-size {
  color: rgba(255,255,255,0.8);
  font-size: 13px;
  text-shadow: 0 1px 3px rgba(0,0,0,0.5);
}

.topbar-right {
  display: flex;
  align-items: center;
}

.close-btn {
  background: rgba(255,255,255,0.15) !important;
  border-color: rgba(255,255,255,0.3) !important;
  color: white !important;
  backdrop-filter: blur(8px);
}

.close-btn:hover {
  background: rgba(255,255,255,0.25) !important;
  border-color: rgba(255,255,255,0.5) !important;
}

/* 图片区域 - 自适应伸缩 */
.preview-image-wrapper {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  transition: flex 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  min-height: 200px;
}

.preview-main-image {
  max-width: 100%;
  max-height: 100%;
}

.preview-main-image :deep(.el-image__inner) {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.preview-main-image :deep(.el-image__error) {
  background: transparent;
}

/* ===================== 底部抽屉面板 ===================== */
.preview-drawer {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: var(--bg-secondary);
  border-radius: 20px 20px 0 0;
  box-shadow: 0 -4px 20px rgba(0,0,0,0.15);
  transition: transform 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  cursor: pointer;
  z-index: 20;
}

.preview-drawer.expanded {
  transform: translateY(0);
}

/* 抽屉把手 */
.drawer-handle {
  display: flex;
  justify-content: center;
  padding: 12px 0 8px;
}

.handle-bar {
  width: 40px;
  height: 4px;
  background: var(--border-color);
  border-radius: 2px;
}

/* 抽屉头部 */
.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px 16px;
}

.drawer-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.download-btn {
  display: flex;
  align-items: center;
  gap: 6px;
}

.re-download-btn {
  width: 40px;
  height: 40px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.downloaded-tag {
  display: flex;
  align-items: center;
  gap: 4px;
}

.drawer-header-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

.expand-hint {
  font-size: 13px;
  color: var(--text-secondary);
}

.expand-icon {
  color: var(--text-secondary);
  transition: transform 0.3s;
}

/* 抽屉内容 */
.drawer-content {
  padding: 0 20px 24px;
  max-height: 45vh;
  overflow-y: auto;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-item.full-width {
  grid-column: span 2;
}

.info-label {
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.info-value {
  font-size: 14px;
  color: var(--text-primary);
  word-break: break-all;
}

.info-value.md5 {
  font-size: 12px;
  font-family: 'SF Mono', Monaco, monospace;
  color: var(--text-secondary);
}

/* 标签区域 */
.tags-area {
  border-top: 1px solid var(--border-color);
  padding-top: 16px;
}

.tags-header {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 12px;
}

.tags-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-chip {
  cursor: pointer;
  transition: opacity 0.2s, transform 0.2s;
}

.tag-chip:hover {
  opacity: 0.8;
  transform: scale(1.02);
}

/* 抽屉内容过渡 */
.drawer-content-enter-active,
.drawer-content-leave-active {
  transition: opacity 0.3s, transform 0.3s;
}

.drawer-content-enter-from,
.drawer-content-leave-to {
  opacity: 0;
  transform: translateY(20px);
}

/* ===================== 中心对话框样式 ===================== */
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

/* ===================== 深色模式适配 ===================== */
html.dark-mode .preview-topbar {
  background: linear-gradient(to bottom, rgba(0,0,0,0.7), transparent);
}

html.dark-mode .close-btn {
  background: rgba(255,255,255,0.1) !important;
  border-color: rgba(255,255,255,0.2) !important;
}

html.dark-mode .close-btn:hover {
  background: rgba(255,255,255,0.2) !important;
}

html.dark-mode .preview-drawer {
  background: var(--bg-secondary);
}

html.dark-mode .handle-bar {
  background: rgba(255,255,255,0.2);
}

html.dark-mode .re-download-btn {
  background: var(--bg-tertiary);
  border-color: var(--border-color);
  color: var(--text-primary);
}
</style>
