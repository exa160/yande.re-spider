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

    <!-- 图片预览对话框 - 无边框，四周10%边距 -->
    <el-dialog
      v-model="previewVisible"
      :show-close="false"
      class="preview-frameless-dialog"
      :close-on-click-modal="true"
      :width="'80%'"
      top="10vh"
      bottom="10vh"
    >
      <div v-if="currentImage" class="preview-frameless">
        <!-- 图片区域 - 顶部信息栏悬浮在图片上方 -->
        <div class="frameless-image-wrapper">
          <!-- 顶部信息栏 - 悬浮在图片顶部 -->
          <div class="frameless-header">
            <div class="header-left">
              <span class="preview-id">ID: {{ currentImage.id }}</span>
              <el-tag :type="getRatingType(currentImage.rating)" size="small">
                {{ currentImage.rating }}
              </el-tag>
              <span class="preview-size">{{ currentImage.width }} × {{ currentImage.height }}</span>
            </div>
            <div class="header-right">
              <el-button circle @click="previewVisible = false" class="frameless-close-btn">
                <el-icon><Close /></el-icon>
              </el-button>
            </div>
          </div>

          <!-- 图片 -->
          <el-image
            :src="getDetailUrl(currentImage)"
            :preview-src-list="[getDetailUrl(currentImage)]"
            fit="contain"
            class="frameless-image"
            :zoom-rate="1.1"
            :preview-teleported="true"
          />
        </div>

        <!-- 底部面板 - 半透明，包含操作栏和详情 -->
        <div class="frameless-bottom-panel">
          <!-- 操作栏 -->
          <div class="frameless-actions">
            <div class="actions-left">
              <template v-if="!currentImage.is_downloaded">
                <el-button 
                  type="primary" 
                  @click.stop="handleDownload" 
                  :loading="downloading" 
                  class="frameless-download-btn"
                >
                  <el-icon><Download /></el-icon>
                  下载原图
                </el-button>
              </template>
              <template v-else>
                <el-button 
                  @click.stop="handleDownload" 
                  :loading="downloading" 
                  class="frameless-redownload-btn"
                  title="重新下载"
                >
                  <el-icon><Download /></el-icon>
                </el-button>
                <el-tag type="success" class="frameless-downloaded-tag">
                  <el-icon><Check /></el-icon>
                  已下载
                </el-tag>
              </template>
            </div>
            
            <div class="actions-right" @click="toggleInfoPanel">
              <span class="actions-expand-text">{{ infoPanelExpanded ? '收起详情' : '展开详情' }}</span>
              <el-icon class="actions-expand-icon">
                <ArrowUp v-if="infoPanelExpanded" />
                <ArrowDown v-else />
              </el-icon>
            </div>
          </div>

          <!-- 详情面板 -->
          <transition name="panel-slide">
            <div v-if="infoPanelExpanded" class="frameless-detail">
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
              
              <div class="detail-tags-section">
                <div class="detail-tags-title">标签 ({{ currentImage.tags?.length || 0 }})</div>
                <div class="detail-tags-wrap">
                  <el-tag
                    v-for="tag in currentImage.tags"
                    :key="tag"
                    size="default"
                    class="detail-tag"
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
  infoPanelExpanded.value = true  // 默认展开详情
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

/* 无边框预览对话框 */
.preview-frameless-dialog {
  background: transparent !important;
}

.preview-frameless-dialog :deep(.el-dialog) {
  background: transparent !important;
  box-shadow: none !important;
  border-radius: 0 !important;
  overflow: hidden !important;
}

.preview-frameless-dialog :deep(.el-dialog__body) {
  padding: 0 !important;
  overflow: hidden !important;
}

.preview-frameless {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 80vh;
  background: rgba(0, 0, 0, 0.85);
}

/* 图片区域 */
.frameless-image-wrapper {
  flex: 1;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  min-height: 0;
}

/* 顶部信息栏 - 悬浮在图片上方，轻微半透明 */
.frameless-header {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.preview-id {
  font-weight: bold;
  color: white;
  font-size: 14px;
}

.preview-size {
  color: rgba(255, 255, 255, 0.75);
  font-size: 13px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.frameless-close-btn {
  background: rgba(255, 255, 255, 0.12) !important;
  border-color: rgba(255, 255, 255, 0.2) !important;
  color: white !important;
}

.frameless-close-btn:hover {
  background: rgba(255, 255, 255, 0.22) !important;
}

/* 图片 */
.frameless-image {
  max-width: 100%;
  max-height: 100%;
}

.frameless-image :deep(.el-image__inner) {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.frameless-image :deep(.el-image__error) {
  background: transparent;
}

/* 底部面板 - 半透明操作栏+详情 */
.frameless-bottom-panel {
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  flex-shrink: 0;
}

/* 操作栏 */
.frameless-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.actions-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.actions-right {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 4px;
  transition: background 0.2s;
}

.actions-right:hover {
  background: rgba(255, 255, 255, 0.1);
}

.actions-expand-text {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.85);
}

.actions-expand-icon {
  color: rgba(255, 255, 255, 0.85);
}

.frameless-download-btn {
  background: rgba(64, 158, 255, 0.85) !important;
  border-color: rgba(64, 158, 255, 0.85) !important;
  color: white !important;
}

.frameless-download-btn:hover {
  background: rgba(64, 158, 255, 1) !important;
}

.frameless-redownload-btn {
  background: rgba(255, 255, 255, 0.12) !important;
  border-color: rgba(255, 255, 255, 0.2) !important;
  color: white !important;
  width: 32px;
  height: 32px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.frameless-downloaded-tag {
  background: rgba(103, 194, 58, 0.85) !important;
  border-color: rgba(103, 194, 58, 0.85) !important;
  color: white !important;
}

/* 详情面板 */
.frameless-detail {
  padding: 12px 14px;
  max-height: 35vh;
  overflow-y: auto;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  margin-bottom: 12px;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.detail-label {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.5);
}

.detail-value {
  font-size: 12px;
  color: white;
  word-break: break-all;
}

.detail-value.md5 {
  font-size: 10px;
  font-family: monospace;
}

.detail-tags-section {
  margin-top: 4px;
}

.detail-tags-title {
  font-size: 11px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.6);
  margin-bottom: 6px;
}

.detail-tags-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  max-height: 80px;
  overflow-y: auto;
}

.detail-tag {
  background: rgba(255, 255, 255, 0.1) !important;
  border-color: rgba(255, 255, 255, 0.15) !important;
  color: white !important;
  cursor: pointer;
}

.detail-tag:hover {
  background: rgba(255, 255, 255, 0.2) !important;
}

/* 详情面板过渡动画 */
.panel-slide-enter-active,
.panel-slide-leave-active {
  transition: all 0.2s ease;
}

.panel-slide-enter-from,
.panel-slide-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

/* 深色模式适配 */
html.dark-mode .preview-frameless-dialog {
  background: transparent !important;
}

html.dark-mode .preview-frameless-dialog :deep(.el-dialog) {
  background: transparent !important;
}

html.dark-mode .preview-frameless {
  background: rgba(0, 0, 0, 0.92);
}

html.dark-mode .frameless-header {
  background: rgba(0, 0, 0, 0.5);
}

html.dark-mode .frameless-bottom-panel {
  background: rgba(0, 0, 0, 0.5);
}

html.dark-mode .detail-tag {
  background: rgba(255, 255, 255, 0.08) !important;
  border-color: rgba(255, 255, 255, 0.12) !important;
}

html.dark-mode .detail-tag:hover {
  background: rgba(255, 255, 255, 0.15) !important;
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
