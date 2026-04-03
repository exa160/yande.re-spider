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

    <!-- 图片预览对话框 - 非全屏，图片自适应+底部悬浮信息 -->
    <el-dialog
      v-model="previewVisible"
      :show-close="false"
      class="preview-dialog-frameless"
      :close-on-click-modal="true"
      :width="'90%'"
      top="5vh"
    >
      <div v-if="currentImage" class="preview-frameless">
        <!-- 顶部简洁工具栏 -->
        <div class="preview-toolbar">
          <div class="preview-toolbar-left">
            <span class="preview-id">ID: {{ currentImage.id }}</span>
            <el-tag :type="getRatingType(currentImage.rating)" size="small">
              {{ currentImage.rating }}
            </el-tag>
            <span class="preview-size">{{ currentImage.width }} x {{ currentImage.height }}</span>
          </div>
          <div class="preview-toolbar-right">
            <el-button circle @click="previewVisible = false">
              <el-icon><Close /></el-icon>
            </el-button>
          </div>
        </div>

        <!-- 图片区域 - 自适应高度，留出底部空间给信息面板 -->
        <div class="preview-image-container">
          <el-image
            :src="getDetailUrl(currentImage)"
            :preview-src-list="[getDetailUrl(currentImage)]"
            fit="contain"
            class="preview-image"
            :zoom-rate="1.2"
            :preview-teleported="true"
          />
        </div>

        <!-- 底部半透明悬浮信息面板 -->
        <div class="preview-info-overlay" @click="toggleInfoPanel">
          <div class="info-toggle-bar">
            <div class="toggle-bar-left">
              <template v-if="!currentImage.is_downloaded">
                <el-button 
                  type="primary" 
                  size="small" 
                  @click.stop="handleDownload" 
                  :loading="downloading" 
                  class="download-action-btn"
                >
                  <el-icon><Download /></el-icon>
                  下载原图
                </el-button>
              </template>
              <template v-else>
                <el-button 
                  size="small" 
                  @click.stop="handleDownload" 
                  :loading="downloading" 
                  class="re-download-btn"
                  title="重新下载"
                >
                  <el-icon><Download /></el-icon>
                </el-button>
                <el-button type="success" size="small" disabled class="downloaded-btn">
                  <el-icon><Check /></el-icon>
                  已下载
                </el-button>
              </template>
            </div>
            <div class="toggle-bar-right">
              <span class="toggle-text">{{ infoPanelExpanded ? '收起详情' : '展开详情' }}</span>
              <el-icon class="toggle-icon"><ArrowUp v-if="!infoPanelExpanded" /><ArrowDown v-else /></el-icon>
            </div>
          </div>
          
          <transition name="slide-up">
            <div v-if="infoPanelExpanded" class="info-panel-content">
              <div class="info-row">
                <div class="info-item">
                  <span class="info-label">大小</span>
                  <span class="info-value">{{ formatFileSize(currentImage.file_size) }}</span>
                </div>
                <div class="info-item">
                  <span class="info-label">作者</span>
                  <span class="info-value">{{ currentImage.author }}</span>
                </div>
                <div class="info-item">
                  <span class="info-label">MD5</span>
                  <span class="info-value md5">{{ currentImage.md5 }}</span>
                </div>
                <div class="info-item">
                  <span class="info-label">时间</span>
                  <span class="info-value">{{ currentImage.created_at }}</span>
                </div>
              </div>
              
              <div class="tags-section">
                <div class="tags-label">标签 ({{ currentImage.tags?.length || 0 }})</div>
                <div class="tags-scroll">
                  <el-tag
                    v-for="tag in currentImage.tags"
                    :key="tag"
                    size="small"
                    class="tag-item"
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
html.dark-mode .toolbar-left :deep(.el-button--warning) {
  background: #CC5500;
  border-color: #CC5500;
  color: white;
}

html.dark-mode .toolbar-left :deep(.el-button--warning:hover) {
  background: #DD6600;
  border-color: #DD6600;
  color: white;
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
  overflow-x: hidden;
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

/* 无框预览对话框样式 */
.preview-dialog-frameless {
  background: rgba(0, 0, 0, 0.95) !important;
}

.preview-dialog-frameless :deep(.el-dialog__body) {
  padding: 0;
  overflow: hidden;
}

.preview-frameless {
  background: var(--bg-primary);
  position: relative;
}

.preview-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.preview-toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.preview-id {
  font-weight: bold;
  color: var(--text-primary);
}

.preview-size {
  color: var(--text-secondary);
  font-size: 13px;
}

.preview-toolbar-right :deep(.el-button) {
  background: var(--bg-tertiary);
  border-color: var(--border-color);
  color: var(--text-primary);
}

/* 图片容器 - 透明背景，无黑边 */
.preview-image-container {
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  min-height: 300px;
  max-height: calc(90vh - 120px);
  overflow: hidden;
}

.preview-image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.preview-image :deep(.el-image__inner) {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.preview-image :deep(.el-image__error) {
  background: transparent;
}

/* 底部半透明悬浮信息面板 */
.preview-info-overlay {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  display: flex;
  flex-direction: column;
  max-height: 50vh;
}

.info-toggle-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
  user-select: none;
}

.toggle-bar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.toggle-bar-center {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toggle-bar-right {
  display: flex;
  align-items: center;
  gap: 4px;
  justify-content: flex-end;
}

.toggle-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
}

.toggle-text {
  font-size: 13px;
  color: var(--text-secondary);
}

.download-action-btn {
  height: 28px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.download-btn {
  height: 28px;
}

.re-download-btn {
  width: 28px;
  height: 28px;
  padding: 0;
  margin-left: -1px;
  border-left: none;
  display: flex;
  align-items: center;
  justify-content: center;
}

.downloaded-btn {
  height: 28px;
  margin-left: -1px;
  border-left: none;
}

.info-panel-content {
  padding: 0 16px 16px;
  overflow-y: auto;
  max-height: calc(70vh - 50px);
}

.info-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.info-panel-content .info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-panel-content .info-label {
  font-size: 11px;
  color: var(--text-muted);
}

.info-panel-content .info-value {
  font-size: 13px;
  color: var(--text-primary);
  word-break: break-all;
}

.info-panel-content .info-value.md5 {
  font-size: 11px;
  font-family: monospace;
}

.tags-section {
  margin-bottom: 16px;
}

.tags-label {
  font-size: 12px;
  font-weight: bold;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.tags-scroll {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-height: 120px;
  overflow-y: auto;
}

.tag-item {
  cursor: pointer;
}

.tag-item:hover {
  opacity: 0.8;
}

.action-buttons {
  display: flex;
  gap: 12px;
}

.download-btn {
  flex: 1;
}

/* 过渡动画 */
.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.3s ease;
}

.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
  transform: translateY(20px);
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

/* 深色模式下无框预览对话框 */
html.dark-mode .preview-dialog-frameless {
  background: transparent !important;
}

html.dark-mode .preview-dialog-frameless :deep(.el-dialog) {
  background: transparent;
}

html.dark-mode .preview-frameless {
  background: var(--bg-primary);
}

html.dark-mode .preview-toolbar {
  background: rgba(30, 30, 30, 0.9);
  border-bottom-color: var(--border-color);
}

html.dark-mode .preview-toolbar-left .preview-id {
  color: var(--text-primary);
}

html.dark-mode .preview-info-overlay {
  background: rgba(30, 30, 30, 0.92);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

html.dark-mode .info-panel-content .info-label {
  color: var(--text-secondary);
}

html.dark-mode .info-panel-content .info-value {
  color: var(--text-primary);
}

html.dark-mode .tags-label {
  color: var(--text-secondary);
}

html.dark-mode .preview-toolbar-right :deep(.el-button) {
  background: var(--bg-tertiary);
  border-color: var(--border-color);
  color: var(--text-primary);
}

html.dark-mode .toggle-icon,
html.dark-mode .toggle-text {
  color: var(--text-secondary);
}

html.dark-mode .re-download-btn {
  background: var(--bg-tertiary);
  border-color: var(--border-color);
  color: var(--text-primary);
}
</style>
