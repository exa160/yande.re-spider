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

    <!-- 批量选择工具栏 -->
    <div v-if="querySource === 'yande' && selectedImages.length > 0" class="selection-toolbar">
      <el-checkbox 
        :indeterminate="isIndeterminate" 
        v-model="selectAll" 
        @change="handleSelectAll"
      >
        全选当页
      </el-checkbox>
      <span class="selection-info">已选择 {{ selectedImages.length }} 张图片</span>
      <el-button type="primary" size="small" @click="batchDownload">
        <el-icon><Download /></el-icon>
        批量下载 ({{ selectedImages.length }})
      </el-button>
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
      />
    </div>

    <!-- 图片预览对话框 -->
    <el-dialog
      v-model="previewVisible"
      width="80%"
      top="5vh"
      :show-close="true"
      class="preview-dialog"
    >
      <template #header>
        <span>图片详情 - ID: {{ currentImage?.id }}</span>
      </template>
      <div v-if="currentImage" class="preview-content">
        <el-row :gutter="20">
          <el-col :span="16">
            <el-image
              :src="getDetailUrl(currentImage)"
              :preview-src-list="[getDetailUrl(currentImage)]"
              fit="contain"
              style="width: 100%; max-height: 70vh;"
            />
          </el-col>
          <el-col :span="8">
            <el-descriptions :column="1" border>
              <el-descriptions-item label="ID">{{ currentImage.id }}</el-descriptions-item>
              <el-descriptions-item label="分辨率">
                {{ currentImage.width }} x {{ currentImage.height }}
              </el-descriptions-item>
              <el-descriptions-item label="评分">
                <el-tag :type="getRatingType(currentImage.rating)">
                  {{ currentImage.rating }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="文件大小">
                {{ formatFileSize(currentImage.file_size) }}
              </el-descriptions-item>
              <el-descriptions-item label="作者">{{ currentImage.author }}</el-descriptions-item>
              <el-descriptions-item label="创建时间">{{ currentImage.created_at }}</el-descriptions-item>
              <el-descriptions-item label="MD5">{{ currentImage.md5 }}</el-descriptions-item>
              <el-descriptions-item label="Tags">
                <div class="tags-container">
                  <div class="tags-list" :class="{ collapsed: !tagsExpanded && currentImage.tags?.length > 10 }">
                    <el-tag
                      v-for="tag in (tagsExpanded ? currentImage.tags : currentImage.tags?.slice(0, 10))"
                      :key="tag"
                      size="small"
                      style="margin-right: 5px; margin-bottom: 5px;"
                    >
                      {{ tag }}
                    </el-tag>
                  </div>
                  <el-button
                    v-if="currentImage.tags?.length > 10"
                    size="small"
                    text
                    @click="tagsExpanded = !tagsExpanded"
                    style="margin-top: 5px;"
                  >
                    {{ tagsExpanded ? '收起' : `展开更多 (${currentImage.tags.length})` }}
                  </el-button>
                </div>
              </el-descriptions-item>
            </el-descriptions>

            <div style="margin-top: 20px;">
              <el-button type="primary" @click="handleDownload" :loading="downloading">
                <el-icon><Download /></el-icon>
                下载
              </el-button>
              <el-button v-if="currentImage.is_downloaded" type="success" disabled>
                <el-icon><Check /></el-icon>
                已下载
              </el-button>
            </div>
          </el-col>
        </el-row>
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
import { Download, Check, Connection, Setting, Sunny, Moon } from '@element-plus/icons-vue'
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
  previewVisible.value = true
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
  if (image.preview_url) {
    return image.preview_url
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
  background: #8B5A00;
  border-color: #8B5A00;
  color: white;
}

html.dark-mode .toolbar-left :deep(.el-button--warning:hover) {
  background: #A06900;
  border-color: #A06900;
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
}

.preview-content {
  min-height: 400px;
}

.tags-container {
  max-height: none;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.tags-list.collapsed {
  max-height: 120px;
  overflow: hidden;
}

.preview-dialog :deep(.el-dialog__header) {
  margin-right: 0;
  padding: 15px 20px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-secondary);
}

.preview-dialog :deep(.el-dialog__body) {
  padding: 20px;
  background: var(--bg-secondary);
}

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
