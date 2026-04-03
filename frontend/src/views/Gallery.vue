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

    <!-- 图片预览对话框 - 适应屏幕，保持图片比例，四边10%边距 -->
    <el-dialog
      v-model="previewVisible"
      :show-close="false"
      class="preview-immersive-dialog"
      :close-on-click-modal="true"
      :width="'auto'"
      :fullscreen="false"
      top="5vh"
    >
      <div 
        v-if="currentImage" 
        class="preview-immersive"
        :style="previewStyle"
      >
        <!-- 顶部信息栏 - 悬浮在图片顶部 -->
        <div class="immersive-header">
          <div class="header-left">
            <span class="preview-id">ID: {{ currentImage.id }}</span>
            <el-tag :type="getRatingType(currentImage.rating)" size="small">
              {{ currentImage.rating }}
            </el-tag>
            <span class="preview-size">{{ currentImage.width }} × {{ currentImage.height }}</span>
          </div>
          <div class="header-right">
            <el-button circle @click="previewVisible = false" class="immersive-close-btn">
              <el-icon><Close /></el-icon>
            </el-button>
          </div>
        </div>

        <!-- 图片区域 - 自适应图片尺寸 -->
        <div class="immersive-image-area">
          <el-image
            :src="getDetailUrl(currentImage)"
            :preview-src-list="[getDetailUrl(currentImage)]"
            fit="contain"
            class="immersive-image"
            :zoom-rate="1.1"
            :preview-teleported="true"
          />
        </div>

        <!-- 详情面板 - 默认展开，向上展开覆盖图片 -->
        <transition name="detail-slide-up">
          <div v-if="infoPanelExpanded" class="immersive-detail-panel">
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

        <!-- 底部操作栏 - 悬浮在图片底部 -->
        <div class="immersive-footer">
          <div class="footer-left">
            <template v-if="!currentImage.is_downloaded">
              <el-button 
                type="primary" 
                @click.stop="handleDownload" 
                :loading="downloading" 
                class="immersive-download-btn"
              >
                <el-icon><Download /></el-icon>
                下载原图
              </el-button>
            </template>
            <template v-else>
              <el-button 
                @click.stop="handleDownload" 
                :loading="downloading" 
                class="immersive-redownload-btn"
                title="重新下载"
              >
                <el-icon><Download /></el-icon>
              </el-button>
              <el-tag type="success" class="immersive-downloaded-tag">
                <el-icon><Check /></el-icon>
                已下载
              </el-tag>
            </template>
          </div>
          
          <div class="footer-right" @click="toggleInfoPanel">
            <span class="footer-expand-text">{{ infoPanelExpanded ? '收起详情' : '展开详情' }}</span>
            <el-icon class="footer-expand-icon">
              <ArrowUp v-if="infoPanelExpanded" />
              <ArrowDown v-else />
            </el-icon>
          </div>
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
import { ref, computed, onMounted, watch, onUnmounted } from 'vue'
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
const infoPanelExpanded = ref(true)

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

// 计算预览弹框样式 - 适应屏幕，保持图片比例，四边10%边距
const previewStyle = computed(() => {
  if (!currentImage.value) return {}
  const imgWidth = currentImage.value.width || 1920
  const imgHeight = currentImage.value.height || 1080
  const aspectRatio = imgWidth / imgHeight
  
  // 屏幕可用尺寸 (80% = 四边10%边距)
  const maxWidth = window.innerWidth * 0.8
  const maxHeight = window.innerHeight * 0.8
  
  // 根据比例计算实际尺寸
  let width = imgWidth
  let height = imgHeight
  
  if (width > maxWidth) {
    width = maxWidth
    height = width / aspectRatio
  }
  if (height > maxHeight) {
    height = maxHeight
    width = height * aspectRatio
  }
  
  return {
    width: `${width}px`,
    height: `${height}px`
  }
})

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
  infoPanelExpanded.value = true
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

/* 全屏沉浸式预览对话框 */
.preview-immersive-dialog {
  background: transparent !important;
}

.preview-immersive-dialog :deep(.el-dialog) {
  background: transparent !important;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35) !important;
  border-radius: 12px;
  overflow: visible;
  width: auto !important;
  max-width: 90vw;
  max-height: 90vh;
}

.preview-immersive-dialog :deep(.el-dialog__body) {
  padding: 0;
  overflow: visible;
}

.preview-immersive {
  position: relative;
  background: #1a1a1a;
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* 图片区域 - 自适应图片尺寸 */
.immersive-image-area {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #1a1a1a;
  overflow: hidden;
  min-height: 0;
}

.immersive-image {
  width: 100%;
  height: 100%;
}

.immersive-image :deep(.el-image__inner) {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.immersive-image :deep(.el-image__error) {
  background: #1a1a1a;
}

/* 顶部信息栏 - 悬浮在图片顶部，减少模糊 */
.immersive-header {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
  border-radius: 12px 12px 0 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.preview-id {
  font-weight: bold;
  color: rgba(255, 255, 255, 0.95);
  text-shadow: 0 1px 2px rgba(0,0,0,0.5);
}

.preview-size {
  color: rgba(255, 255, 255, 0.7);
  font-size: 12px;
  text-shadow: 0 1px 2px rgba(0,0,0,0.5);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.immersive-close-btn {
  background: rgba(255, 255, 255, 0.08) !important;
  border-color: rgba(255, 255, 255, 0.15) !important;
  color: rgba(255, 255, 255, 0.9) !important;
}

.immersive-close-btn:hover {
  background: rgba(255, 255, 255, 0.15) !important;
}

/* 底部操作栏 - 悬浮在图片底部 */
.immersive-footer {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  background: rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
  border-radius: 0 0 12px 12px;
}

.footer-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.footer-right {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 4px;
  transition: background 0.2s;
}

.footer-right:hover {
  background: rgba(255, 255, 255, 0.08);
}

.footer-expand-text {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.75);
  text-shadow: 0 1px 2px rgba(0,0,0,0.5);
}

.footer-expand-icon {
  color: rgba(255, 255, 255, 0.75);
  text-shadow: 0 1px 2px rgba(0,0,0,0.5);
}

.immersive-download-btn {
  background: rgba(64, 158, 255, 0.85) !important;
  border-color: rgba(64, 158, 255, 0.85) !important;
  color: white !important;
}

.immersive-download-btn:hover {
  background: rgba(64, 158, 255, 1) !important;
}

.immersive-redownload-btn {
  background: rgba(255, 255, 255, 0.08) !important;
  border-color: rgba(255, 255, 255, 0.15) !important;
  color: rgba(255, 255, 255, 0.9) !important;
  width: 32px;
  height: 32px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.immersive-downloaded-tag {
  background: rgba(103, 194, 58, 0.85) !important;
  border-color: rgba(103, 194, 58, 0.85) !important;
  color: white !important;
}

/* 详情面板 - 悬浮在底部操作栏上方，向上展开 */
.immersive-detail-panel {
  position: absolute;
  bottom: 44px;
  left: 0;
  right: 0;
  z-index: 15;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
  max-height: 30vh;
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
  text-shadow: 0 1px 2px rgba(0,0,0,0.3);
}

.detail-value {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.9);
  text-shadow: 0 1px 2px rgba(0,0,0,0.5);
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
  color: rgba(255, 255, 255, 0.65);
  margin-bottom: 6px;
  text-shadow: 0 1px 2px rgba(0,0,0,0.3);
}

.detail-tags-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  max-height: 80px;
  overflow-y: auto;
}

.detail-tag {
  background: rgba(255, 255, 255, 0.08) !important;
  border-color: rgba(255, 255, 255, 0.15) !important;
  color: rgba(255, 255, 255, 0.85) !important;
  cursor: pointer;
}

.detail-tag:hover {
  background: rgba(255, 255, 255, 0.15) !important;
}

/* 详情面板向上展开/收起动画 */
.detail-slide-up-enter-active,
.detail-slide-up-leave-active {
  transition: all 0.28s ease;
}

.detail-slide-up-enter-from,
.detail-slide-up-leave-to {
  opacity: 0;
  transform: translateY(100%);
}

/* 深色模式适配 - 弹框背景 */
html.dark-mode .preview-immersive {
  background: #0d0d0d;
}

html.dark-mode .immersive-image-area {
  background: #0d0d0d;
}

html.dark-mode .immersive-header,
html.dark-mode .immersive-footer {
  background: rgba(0, 0, 0, 0.06);
}

html.dark-mode .immersive-detail-panel {
  background: rgba(0, 0, 0, 0.05);
}

/* 浅色模式适配 - 弹框背景 */
html:not(.dark-mode) .preview-immersive {
  background: #f5f5f5;
}

html:not(.dark-mode) .immersive-image-area {
  background: #f5f5f5;
}

html:not(.dark-mode) .immersive-header,
html:not(.dark-mode) .immersive-footer {
  background: rgba(0, 0, 0, 0.03);
}

html:not(.dark-mode) .immersive-detail-panel {
  background: rgba(0, 0, 0, 0.02);
}

html:not(.dark-mode) .preview-id,
html:not(.dark-mode) .preview-size,
html:not(.dark-mode) .footer-expand-text,
html:not(.dark-mode) .footer-expand-icon,
html:not(.dark-mode) .detail-label,
html:not(.dark-mode) .detail-value {
  text-shadow: none;
}

html:not(.dark-mode) .immersive-close-btn,
html:not(.dark-mode) .immersive-redownload-btn {
  background: rgba(0, 0, 0, 0.04) !important;
  border-color: rgba(0, 0, 0, 0.08) !important;
  color: rgba(0, 0, 0, 0.7) !important;
}

html:not(.dark-mode) .immersive-close-btn:hover,
html:not(.dark-mode) .immersive-redownload-btn:hover {
  background: rgba(0, 0, 0, 0.08) !important;
}

html:not(.dark-mode) .footer-right:hover {
  background: rgba(0, 0, 0, 0.04);
}

html:not(.dark-mode) .detail-tag {
  background: rgba(0, 0, 0, 0.04) !important;
  border-color: rgba(0, 0, 0, 0.08) !important;
  color: rgba(0, 0, 0, 0.7) !important;
}

html:not(.dark-mode) .detail-tag:hover {
  background: rgba(0, 0, 0, 0.08) !important;
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
