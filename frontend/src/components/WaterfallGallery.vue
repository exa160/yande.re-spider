<template>
  <div class="waterfall-gallery">
    <!-- 加载状态 -->
    <div v-if="loading" class="loading-container">
      <el-icon class="is-loading" :size="40"><Loading /></el-icon>
      <p>加载中...</p>
    </div>

    <!-- 瀑布流布局 -->
    <div v-else ref="containerRef" class="waterfall-container" :style="`column-count: ${columnCount}`">
      <div
        v-for="image in reorderedImages"
        :key="image.id"
        class="waterfall-item"
        :class="{ 'selected': isSelected(image) }"
        @click="handleImageClick(image)"
      >
        <!-- 选择框 -->
        <div v-if="selectable" class="selection-checkbox" @click.stop>
          <el-checkbox
            :model-value="isSelected(image)"
            @change="(checked) => handleSelect(image, checked)"
          />
        </div>

        <!-- 图片 -->
        <el-image
          :key="retryKeys.value + '-' + image.id"
          :src="getPreviewUrl(image)"
          :alt="image.id.toString()"
          fit="cover"
          @error="handleImageError(image)"
          @load="handleImageLoad(image)"
        >
          <template #error>
            <div class="image-error">
              <el-icon><Picture /></el-icon>
            </div>
          </template>
          <template #placeholder>
            <div class="image-placeholder">
              <el-icon class="is-loading"><Loading /></el-icon>
            </div>
          </template>
        </el-image>

        <!-- 重试按钮 -->
        <div v-if="shouldShowRetry(image)" class="retry-button" @click="(e) => handleImageRetry(image, e)">
          <el-icon v-if="retryingImages.has(image.id)" class="is-loading"><Loading /></el-icon>
          <el-icon v-else><RefreshRight /></el-icon>
        </div>

        <!-- 图片信息 -->
        <div class="image-info">
          <div class="image-id">ID: {{ image.id }}</div>
          <div class="image-size">{{ image.width }} x {{ image.height }}</div>
          <div class="image-rating">
            <el-tag :type="getRatingType(image.rating)" size="small">
              {{ image.rating }}
            </el-tag>
          </div>
          <div v-if="image.local_file_path || image.local_preview_path" class="downloaded-badge">
            <el-icon><Check /></el-icon>
          </div>
        </div>

        <!-- 选中遮罩 -->
        <div v-if="isSelected(image)" class="selection-overlay"></div>
      </div>
    </div>

    <!-- 空状态 -->
    <el-empty v-if="!loading && images.length === 0" description="暂无图片" />

    <!-- 加载更多 -->
    <div v-if="hasMore && !loading" class="load-more">
      <el-button @click="loadMore" :loading="loadingMore">
        加载更多
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { Loading, Picture, Check, RefreshRight } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import api from '@/api'

const props = defineProps({
  images: {
    type: Array,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  },
  hasMore: {
    type: Boolean,
    default: false
  },
  selectable: {
    type: Boolean,
    default: false
  },
  selectedImages: {
    type: Array,
    default: () => []
  },
  sourceMode: {
    type: String,
    default: 'local'
  },
  saveDataMode: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['image-click', 'image-select', 'load-more'])

const loadingMore = ref(false)
const failedImages = ref(new Set())
const pendingImages = ref(new Set())
const retryKeys = ref(0)
const retryingImages = ref(new Set())
const displayedImages = ref([])

const containerRef = ref(null)
const columnCount = ref(4)
const columnHeights = ref([])

const getColumnCount = (width) => {
  if (width >= 1200) return 4
  if (width >= 768) return 3
  if (width >= 480) return 2
  return 1
}

const estimateImageHeight = (image) => {
  if (image.width && image.height) {
    return (200 / image.width) * image.height
  }
  return 200
}

const reorderedImages = computed(() => {
  const cols = columnCount.value
  const colHeights = Array(cols).fill(0)
  const colArrays = Array.from({ length: cols }, () => [])
  
  props.images.forEach((img) => {
    let shortestCol = 0
    let minHeight = colHeights[0]
    for (let i = 1; i < cols; i++) {
      if (colHeights[i] < minHeight) {
        minHeight = colHeights[i]
        shortestCol = i
      }
    }
    colArrays[shortestCol].push(img)
    colHeights[shortestCol] += estimateImageHeight(img) + 15
  })
  
  return colArrays.flat()
})

watch(() => props.images.length, () => {
  const newImages = props.images
  if (newImages.length === 0) {
    displayedImages.value = []
    return
  }
  const existingIds = new Set(displayedImages.value.map(img => img.id))
  const newItems = newImages.filter(img => !existingIds.has(img.id))
  if (newItems.length > 0) {
    displayedImages.value = [...displayedImages.value, ...newItems]
  }
}, { immediate: true })

const updateColumnCount = () => {
  if (containerRef.value) {
    const width = containerRef.value.offsetWidth
    const newCount = getColumnCount(width)
    if (newCount !== columnCount.value) {
      columnCount.value = newCount
    }
  }
}

onMounted(() => {
  updateColumnCount()
  window.addEventListener('resize', updateColumnCount)
})

const isSelected = (image) => {
  return props.selectedImages.some(img => img.id === image.id)
}

const handleImageClick = (image) => {
  emit('image-click', image)
}

const handleSelect = (image, checked) => {
  emit('image-select', image, checked)
}

const loadMore = () => {
  loadingMore.value = true
  emit('load-more')
  setTimeout(() => {
    loadingMore.value = false
  }, 1000)
}

const getRatingType = (rating) => {
  const types = {
    'Safe': 'success',
    'Questionable': 'warning',
    'Explicit': 'danger'
  }
  return types[rating] || 'info'
}

const getPreviewUrl = (image) => {
  const isPending = pendingImages.value.has(image.id)
  const ts = isPending && retryKeys.value > 0 ? `&t=${retryKeys.value}` : ''
  
  if (props.sourceMode === 'local') {
    if (isPending && image.local_preview_path) {
      return `/api/v1/gallery/cache/preview/${image.id}.${image.file_ext || 'jpg'}?t=${retryKeys.value}`
    }
    if (isPending && image.local_file_path) {
      return `/api/v1/gallery/cache/preview/generate/${image.id}?file_ext=${image.file_ext || 'jpg'}${ts}`
    }
    if (props.saveDataMode) {
      return ''
    }
    if (image.local_preview_path) {
      return `/api/v1/gallery/cache/preview/${image.id}.${image.file_ext || 'jpg'}`
    }
    if (image.local_file_path) {
      return `/api/v1/gallery/cache/preview/generate/${image.id}?file_ext=${image.file_ext || 'jpg'}`
    }
    return ''
  }
  if (props.saveDataMode && !isPending) {
    return ''
  }
  return `/api/v1/gallery/cache/preview/fetch/${image.id}?preview_url=${encodeURIComponent(image.preview_url)}&file_ext=${image.file_ext || 'jpg'}`
}

const handleImageError = (image) => {
  failedImages.value.add(image.id)
  pendingImages.value.delete(image.id)
}

const handleImageLoad = (image) => {
  failedImages.value.delete(image.id)
  pendingImages.value.add(image.id)
}

const shouldShowRetry = (image) => {
  return failedImages.value.has(image.id) || retryingImages.value.has(image.id)
}

const handleImageRetry = async (image, event) => {
  if (event) {
    event.stopPropagation()
  }
  
  retryingImages.value.add(image.id)
  failedImages.value.delete(image.id)
  
  let apiSuccess = false
  if (props.sourceMode === 'local') {
    if (image.local_file_path) {
      try {
        await api.get(`/gallery/cache/preview/generate/${image.id}?file_ext=${image.file_ext || 'jpg'}`)
        apiSuccess = true
      } catch (e) {
        ElMessage.error('生成缩略图失败')
      }
    }
  } else {
    try {
      await api.get(`/gallery/cache/preview/fetch/${image.id}?preview_url=${encodeURIComponent(image.preview_url)}&file_ext=${image.file_ext || 'jpg'}`)
      apiSuccess = true
    } catch (e) {
      ElMessage.error('缓存预览图失败')
    }
  }
  
  retryingImages.value.delete(image.id)
  
  if (apiSuccess) {
    pendingImages.value.add(image.id)
    retryKeys.value++
  } else {
    failedImages.value.add(image.id)
  }
}

// 无限滚动
const handleScroll = () => {
  const scrollTop = window.pageYOffset || document.documentElement.scrollTop
  const windowHeight = window.innerHeight
  const documentHeight = document.documentElement.scrollHeight

  if (scrollTop + windowHeight >= documentHeight - 100) {
    if (props.hasMore && !props.loading && !loadingMore.value) {
      loadMore()
    }
  }
}

onMounted(() => {
  window.addEventListener('scroll', handleScroll)
})

onUnmounted(() => {
  window.removeEventListener('resize', updateColumnCount)
  window.removeEventListener('scroll', handleScroll)
})
</script>

<style scoped>
.waterfall-gallery {
  min-height: 400px;
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 400px;
}

.waterfall-container {
  column-gap: 15px;
}

.waterfall-item {
  break-inside: avoid;
  margin-bottom: 15px;
  position: relative;
  cursor: pointer;
  border-radius: 8px;
  overflow: hidden;
  transition: transform 0.3s;
}

.waterfall-item:hover {
  transform: scale(1.05);
}

.waterfall-item.selected {
  box-shadow: 0 0 0 3px #409EFF;
}

.waterfall-item .el-image {
  width: 100%;
  display: block;
  min-height: 200px;
}

.waterfall-item .el-image__placeholder,
.waterfall-item .el-image__error {
  min-height: 200px;
  background: #f5f7fa;
}

.selection-checkbox {
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 10;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 4px;
  padding: 2px;
}

.selection-checkbox :deep(.el-checkbox__inner) {
  background-color: rgba(255, 255, 255, 0.3);
  border-color: rgba(255, 255, 255, 0.5);
}

.selection-checkbox :deep(.el-checkbox__input.is-checked .el-checkbox__inner) {
  background-color: rgba(64, 158, 255, 0.7);
  border-color: rgba(64, 158, 255, 0.7);
}

.selection-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(64, 158, 255, 0.2);
  pointer-events: none;
}

.image-error,
.image-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  background: #f5f7fa;
  color: #909399;
}

.image-info {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.7));
  color: white;
  padding: 10px;
  font-size: 12px;
}

.image-id {
  font-weight: bold;
  margin-bottom: 5px;
}

.image-size {
  margin-bottom: 5px;
}

.downloaded-badge {
  position: absolute;
  bottom: 10px;
  right: 10px;
  background: rgba(103, 194, 58, 0.9);
  color: white;
  border-radius: 12px;
  padding: 4px 10px;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.downloaded-badge .el-icon {
  font-size: 14px;
}

.retry-button {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 20;
  width: 40px;
  height: 40px;
  background: rgba(128, 128, 128, 0.8);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: white;
  font-size: 20px;
}

.retry-button:hover {
  background: rgba(64, 158, 255, 0.9);
}

.load-more {
  text-align: center;
  margin-top: 20px;
}
</style>
