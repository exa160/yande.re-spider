<template>
  <div class="gallery-page">
    <!-- 高级查询组件 -->
    <AdvancedQuery @search="handleSearch" ref="queryRef" />

    <!-- 数据源选择工具栏 -->
    <div class="source-toolbar">
      <el-card shadow="never" class="source-card">
        <div class="source-controls">
          <el-switch
            v-model="querySource"
            active-text="在线 (yande.re)"
            inactive-text="本地 (已下载)"
            active-value="yande"
            inactive-value="local"
            @change="handleSourceChange"
          />
          <el-divider direction="vertical" />
          <el-tooltip content="开启后不加载远程缩略图，节省流量" placement="bottom">
            <el-switch
              v-model="saveDataMode"
              active-text="省流"
              inactive-text=""
            />
          </el-tooltip>
          <el-divider direction="vertical" />
          <span class="source-hint">
            <el-icon><InfoFilled /></el-icon>
            {{ querySource === 'yande' ? '从 yande.re 获取最新图片' : '从本地数据库读取已下载图片' }}
          </span>
          <el-divider direction="vertical" />
          <el-button 
            v-if="querySource === 'yande' && selectedImages.length > 0" 
            type="primary" 
            size="small"
            @click="batchDownload"
          >
            <el-icon><Download /></el-icon>
            批量下载 ({{ selectedImages.length }})
          </el-button>
        </div>
      </el-card>
    </div>

    <!-- 批量选择工具栏 -->
    <div v-if="querySource === 'yande'" class="selection-toolbar">
      <el-checkbox 
        :indeterminate="isIndeterminate" 
        v-model="selectAll" 
        @change="handleSelectAll"
      >
        全选当页
      </el-checkbox>
      <span class="selection-info">已选择 {{ selectedImages.length }} 张图片</span>
    </div>

    <!-- 瀑布流图库组件 -->
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

    <!-- 图片预览对话框 -->
    <el-dialog
      v-model="previewVisible"
      :title="`图片详情 - ID: ${currentImage?.id}`"
      width="80%"
      top="5vh"
    >
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
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Check, InfoFilled } from '@element-plus/icons-vue'
import AdvancedQuery from '@/components/AdvancedQuery.vue'
import WaterfallGallery from '@/components/WaterfallGallery.vue'
import api from '@/api'

const images = ref([])
const loading = ref(false)
const hasMore = ref(false)
const currentPage = ref(1)
const queryParams = ref({})
const querySource = ref('local')
const saveDataMode = ref(true)

const previewVisible = ref(false)
const currentImage = ref(null)
const downloading = ref(false)
const tagsExpanded = ref(false)

// 多选相关
const selectedImages = ref([])
const selectAll = ref(false)
const isIndeterminate = ref(false)

const handleSearch = async (params) => {
  queryParams.value = { ...params, source: querySource.value }
  currentPage.value = 1
  images.value = []
  selectedImages.value = []  // 清空选择
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
  padding: 20px;
}

.source-toolbar {
  margin-bottom: 15px;
}

.source-card {
  background: #f5f7fa;
  border: 1px solid #e4e7ed;
}

.source-card :deep(.el-card__body) {
  padding: 10px 20px;
}

.source-controls {
  display: flex;
  align-items: center;
  gap: 15px;
}

.source-hint {
  font-size: 13px;
  color: #909399;
  display: flex;
  align-items: center;
  gap: 5px;
}

.selection-toolbar {
  margin-bottom: 15px;
  padding: 10px 15px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 20px;
}

.selection-info {
  font-size: 13px;
  color: #909399;
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
</style>
