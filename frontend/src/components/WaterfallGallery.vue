<template>
  <div class="waterfall-gallery" ref="galleryRef">
    <!-- 骨架屏加载状态 -->
    <div 
      v-if="loading" 
      class="skeleton-container"
      :style="`column-count: ${columnCount}`"
    >
      <div
        v-for="i in skeletonCount"
        :key="i"
        class="skeleton-item"
        :style="{ height: skeletonHeights[i - 1] + 'px' }"
      >
        <div class="skeleton-shimmer"></div>
      </div>
    </div>

    <!-- 瀑布流布局 -->
    <div v-else ref="containerRef" class="waterfall-container" :style="`column-count: ${columnCount}`">
      <div
        v-for="image in reorderedImages"
        :key="image.id"
        :data-image-id="image.id"
        class="waterfall-item"
        :class="{ 
          'selected': isSelected(image),
          'image-loaded': pendingImages.has(image.id) || !image.preview_url?.startsWith('http'),
          'touch-focused': touchFocusedId === image.id || mouseFocusedId === image.id
        }"
        @click="handleImageClick(image)"
        @touchstart="handleTouchStart(image, $event)"
        @touchmove="handleTouchMove($event)"
        @touchend="handleTouchEnd(image, $event)"
        @contextmenu.prevent="handleLongPress(image)"
        @mousedown="handleMouseDown(image, $event)"
        @mouseup="handleMouseUp(image, $event)"
        @mousemove="handleMouseMove(image, $event)"
      >
        <!-- 长按选择提示 -->
        <div v-if="isSelected(image)" class="selection-indicator">
          <el-icon><Check /></el-icon>
        </div>

        <!-- 图片 -->
        <el-image
          :key="image.id"
          :src="getPreviewUrl(image)"
          :alt="image.id.toString()"
          fit="cover"
          class="waterfall-image"
          :style="{ height: getPlaceholderHeight(image) + 'px' }"
          :class="{ 
            'fade-in': pendingImages.has(image.id),
            'safe-blur': safeMode && image.rating !== 'Safe'
          }"
          @error="handleImageError(image)"
          @load="handleImageLoad(image)"
        >
          <template #error>
            <div class="image-error">
              <el-icon><Picture /></el-icon>
            </div>
          </template>
          <template #placeholder>
            <div class="image-placeholder skeleton-shimmer"></div>
          </template>
        </el-image>

        <!-- 重试按钮 -->
        <div v-if="shouldShowRetry(image)" class="retry-button" @click="(e) => handleImageRetry(image, e)">
          <el-icon v-if="retryingImages.has(image.id)" class="is-loading"><Loading /></el-icon>
          <el-icon v-else><RefreshRight /></el-icon>
        </div>

        <!-- 图片信息悬浮层 -->
        <div class="image-info-overlay">
          <div class="image-info-content">
            <span class="info-id">ID: {{ image.id }}</span>
            <span class="info-size">{{ image.width }}x{{ image.height }}</span>
            <el-tag :type="getRatingType(image.rating)" size="small" class="info-rating">
              {{ image.rating }}
            </el-tag>
            <div v-if="image.down_flag" class="downloaded-dot"></div>
          </div>
        </div>

        <!-- 选中遮罩 -->
        <div v-if="isSelected(image)" class="selection-overlay"></div>
      </div>
    </div>

    <!-- 空状态 -->
    <el-empty v-if="!loading && images.length === 0 && !loadError" description="暂无图片" />

    <!-- 加载更多 -->
    <div v-if="(hasMore || loadError) && !loading" ref="loadMoreRef" class="load-more">
      <el-button
        @click="handleLoadMoreClick"
        :disabled="loadingMore"
        class="load-more-btn"
      >
        <span v-if="loadingMore" class="load-more-loading">
          <el-icon class="is-loading"><Loading /></el-icon>
          加载中...
        </span>
        <span v-else-if="loadError">重新加载</span>
        <span v-else>加载更多</span>
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
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
  },
  isLoadingMore: {
    type: Boolean,
    default: false
  },
  loadError: {
    type: Boolean,
    default: false
  },
  safeMode: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['image-click', 'image-select', 'load-more', 'load-error', 'multi-select-start'])

// 监听 isLoadingMore prop，当父组件重置时同步状态
watch(() => props.isLoadingMore, (newVal) => {
  if (!newVal) {
    loadingMore.value = false
  }
})

const loadingMore = ref(false)
const failedImages = ref(new Set())
const pendingImages = ref(new Set())
const retryingImages = ref(new Set())
const retrySuccessImages = ref(new Map())
const displayedImages = ref([])
const imageLoadTimeouts = ref(new Map()) // 跟踪图片加载超时

// 长按选择相关
const touchFocusedId = ref(null)
const longPressTimer = ref(null)
const isLongPress = ref(false)
const longPressSelectedId = ref(null) // 长按刚选中的图片 ID，滑动时跳过
const touchMoved = ref(false) // 标记当前触摸是否已移动
const LONG_PRESS_DURATION = 500
const MOVE_THRESHOLD = 10 // 移动阈值，超过则不触发长按
const touchStartPos = ref({ x: 0, y: 0 })
const longPressTriggered = ref(false) // 长按是否已触发
const touchTargetImageId = ref(null) // 触摸目标图片 ID

// 鼠标长按支持
const isMouseDown = ref(false)
const mouseFocusedId = ref(null)
const mouseStartPos = ref({ x: 0, y: 0 })
const LONG_PRESS_DURATION_PC = 400 // PC端长按时长

// 懒加载：追踪已进入可视区的图片
const visibleImages = ref(new Set())
let observer = null
let loadMoreObserver = null

const containerRef = ref(null)
const galleryRef = ref(null)
const loadMoreRef = ref(null)
const columnCount = ref(4)
const columnHeights = ref([])
const containerWidth = ref(1200)

// 骨架屏数量和宽高比（模拟真实图片比例分布）
const skeletonCount = 20
// 宽高比数组（height/width），模拟不同比例的图片
const skeletonRatios = [
  0.75, 1.2, 0.6, 1.5, 0.8,
  1.33, 0.67, 1.0, 1.4, 0.7,
  0.85, 1.6, 0.9, 1.25, 0.65,
  1.45, 0.72, 1.1, 0.55, 1.35
]

// 根据容器宽度和比例计算骨架屏高度
const getSkeletonWidth = () => {
  const gap = 15
  // 使用 galleryRef 获取实际容器宽度
  if (galleryRef.value) {
    containerWidth.value = galleryRef.value.offsetWidth
  }
  return (containerWidth.value - gap * (columnCount.value - 1)) / columnCount.value
}

const skeletonHeights = computed(() => {
  const width = getSkeletonWidth()
  return skeletonRatios.map(ratio => Math.round(width * ratio))
})

// 监听 loading 状态变化，确保骨架屏显示时宽度正确
watch(() => props.loading, (isLoading) => {
  if (isLoading) {
    // 骨架屏显示时，使用 galleryRef 获取实际宽度
    nextTick(() => {
      if (galleryRef.value) {
        containerWidth.value = galleryRef.value.offsetWidth
        columnCount.value = getColumnCount(containerWidth.value)
      }
    })
  }
}, { immediate: true })

const getColumnCount = (width) => {
  containerWidth.value = width
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

// 计算骨架屏占位图高度（基于图片宽高比和列宽）
const getPlaceholderHeight = (image) => {
  if (image.width && image.height) {
    const gap = 15
    const galleryWidth = galleryRef.value?.offsetWidth || containerWidth.value
    const cols = getColumnCount(galleryWidth)
    const columnWidth = (galleryWidth - gap * (cols - 1)) / cols
    return (columnWidth / image.width) * image.height
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
    visibleImages.value.clear()
    failedImages.value.clear()
    retryingImages.value.clear()
    pendingImages.value.clear()
    retrySuccessImages.value.clear()
    // 清除所有超时
    imageLoadTimeouts.value.forEach(t => clearTimeout(t))
    imageLoadTimeouts.value.clear()
    return
  }
  const existingIds = new Set(displayedImages.value.map(img => img.id))
  const newItems = newImages.filter(img => !existingIds.has(img.id))
  if (newItems.length > 0) {
    displayedImages.value = [...displayedImages.value, ...newItems]
    // 为新图片设置加载超时
    newItems.forEach(img => {
      // 延迟设置超时，等图片开始加载
      nextTick(() => setImageTimeout(img))
    })
  }
  // 新图片加入后，重新观察
  nextTick(() => observeNewImages())
}, { immediate: true })

// 懒加载：观察图片是否进入可视区
const observeNewImages = () => {
  if (!observer && typeof IntersectionObserver !== 'undefined') {
    observer = new IntersectionObserver(
      (entries) => {
        entries.forEach(entry => {
          const imageId = parseInt(entry.target.dataset.imageId)
          if (entry.isIntersecting) {
            visibleImages.value.add(imageId)
            // 非省流模式下，图片重新进入可视区时清除失败状态让其自动重试
            // 省流模式下需要用户手动点击重试，所以不清除
            if (!props.saveDataMode) {
              failedImages.value.delete(imageId)
            }
          }
        })
      },
      { rootMargin: '200px' }
    )
  }
  
  if (observer) {
    const items = containerRef.value?.querySelectorAll('.waterfall-item')
    items?.forEach(item => {
      const imageId = parseInt(item.dataset.imageId)
      if (!visibleImages.value.has(imageId)) {
        observer.observe(item)
      }
    })
  }
}

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
  // 如果刚完成长按选择，忽略这次点击
  if (longPressTriggered.value && touchTargetImageId.value === image.id) {
    return
  }
  
  // 如果处于多选模式，点击切换选中状态
  if (props.selectedImages.length > 0) {
    handleSelect(image, !isSelected(image))
    return
  }
  
  emit('image-click', image)
}

// 长按处理
const handleLongPress = (image) => {
  if (!props.selectable) return
  emit('multi-select-start')
  handleSelect(image, !isSelected(image))
  
  // 标记刚选中的图片，用于滑动时跳过不取消
  longPressSelectedId.value = image.id
}

// 触控开始
const handleTouchStart = (image, event) => {
  if (!props.selectable) return
  
  isLongPress.value = false
  touchMoved.value = false
  touchFocusedId.value = image.id
  touchTargetImageId.value = image.id
  longPressTriggered.value = false
  
  if (event.touches && event.touches.length > 0) {
    touchStartPos.value = {
      x: event.touches[0].clientX,
      y: event.touches[0].clientY
    }
  }
    
  longPressTimer.value = setTimeout(() => {
    // 阻止后续的 click 事件
    const el = event.currentTarget
    el.addEventListener('click', function once(e) {
      e.stopPropagation()
      el.removeEventListener('click', once, true)
    }, true)
    
    event.preventDefault()
    event.stopPropagation()
    touchMoved.value = true
    longPressTriggered.value = true
    handleLongPress(image)
  }, LONG_PRESS_DURATION)
}

// 触控移动 - 移动时不处理（去除滑动多选功能）
const handleTouchMove = (event) => {
  if (!props.selectable || !event.touches || event.touches.length === 0) return
    
  const touch = event.touches[0]
  const deltaX = Math.abs(touch.clientX - touchStartPos.value.x)
  const deltaY = Math.abs(touch.clientY - touchStartPos.value.y)
   
  if (deltaX > MOVE_THRESHOLD || deltaY > MOVE_THRESHOLD) {
    touchMoved.value = true
    if (longPressTimer.value) {
      clearTimeout(longPressTimer.value)
      longPressTimer.value = null
    }
  }
}

// 触控结束
const handleTouchEnd = (image, event) => {
  if (longPressTimer.value) {
    clearTimeout(longPressTimer.value)
    longPressTimer.value = null
  }
  
  touchFocusedId.value = null
  
  if (touchMoved.value) {
    event.preventDefault()
  } else if (longPressTriggered.value && touchTargetImageId.value === image.id) {
    event.preventDefault()
  }
  
  // 1.5秒后清除长按触发标志
  setTimeout(() => {
    longPressTriggered.value = false
    touchTargetImageId.value = null
  }, 1500)
}

// 根据 ID 查找图片是否选中
const isSelectedById = (imageId) => {
  return props.selectedImages.some(img => img.id === imageId)
}

// 根据 ID 选中/取消
const handleSelectById = (imageId, checked) => {
  const image = props.images.find(img => img.id === imageId)
  if (image) {
    emit('image-select', image, checked)
  }
}

// PC端鼠标长按开始
const handleMouseDown = (image, event) => {
  if (!props.selectable || event.button !== 0) return // 只响应左键
  isMouseDown.value = true
  mouseFocusedId.value = image.id
  touchTargetImageId.value = image.id
  longPressTriggered.value = false
  mouseStartPos.value = { x: event.clientX, y: event.clientY }
  
  longPressTimer.value = setTimeout(() => {
    if (isMouseDown.value && mouseFocusedId.value === image.id) {
      longPressTriggered.value = true
      handleLongPress(image)
      isMouseDown.value = false
    }
  }, LONG_PRESS_DURATION_PC)
}

// PC端鼠标移动
const handleMouseMove = (image, event) => {
  if (!props.selectable || !isMouseDown.value) return
  
  const deltaX = Math.abs(event.clientX - mouseStartPos.value.x)
  const deltaY = Math.abs(event.clientY - mouseStartPos.value.y)
  
  // 移动超过阈值，取消长按计时器
  if (deltaX > MOVE_THRESHOLD || deltaY > MOVE_THRESHOLD) {
    if (longPressTimer.value) {
      clearTimeout(longPressTimer.value)
      longPressTimer.value = null
    }
  }
  
  // 多选模式下，鼠标滑动自动选中（跳过刚长按选中的）
  if (props.selectedImages.length > 0) {
    const target = event.target.closest('.waterfall-item')
    if (target) {
      const imageId = parseInt(target.dataset.imageId)
      if (imageId && imageId !== mouseFocusedId.value && imageId !== longPressSelectedId.value) {
        const isCurrentlySelected = isSelectedById(imageId)
        handleSelectById(imageId, !isCurrentlySelected)
        mouseFocusedId.value = imageId
      }
    }
  }
}

// PC端鼠标释放
const handleMouseUp = (image, event) => {
  if (longPressTimer.value) {
    clearTimeout(longPressTimer.value)
    longPressTimer.value = null
  }
  isMouseDown.value = false
  mouseFocusedId.value = null
  
  // 如果是长按触发，不阻止click（因为mouseup后click自然会被触发）
  // click的阻止由handleImageClick中的检查来处理
  setTimeout(() => {
    longPressTriggered.value = false
    touchTargetImageId.value = null
  }, 1500)
}

const handleSelect = (image, checked) => {
  emit('image-select', image, checked)
}

const loadMore = () => {
  if (loadingMore.value || props.loadError) return
  loadingMore.value = true
  emit('load-more')
}

const handleLoadMoreClick = () => {
  if (loadingMore.value) return
  loadingMore.value = true
  if (props.loadError) {
    emit('load-error')
  } else {
    emit('load-more')
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

const getPreviewUrl = (image) => {
  const retryTs = retrySuccessImages.value.get(image.id)
  const tsSuffix = retryTs ? `?ts=${retryTs}` : ''

  if (props.sourceMode === 'local') {
    if (image.preview_url) {
      return `/api/v1/gallery/cache/preview/${image.preview_url}${tsSuffix}`
    }
    return `/api/v1/gallery/cache/preview/local/${image.id}${tsSuffix}`
  }
  return `/api/v1/gallery/cache/preview/fetch/${image.id}?file_ext=${image.file_ext || 'jpg'}${tsSuffix}`
}

const handleImageError = (image) => {
  failedImages.value.add(image.id)
  pendingImages.value.delete(image.id)
  clearImageTimeout(image.id)
}

const handleImageLoad = (image) => {
  failedImages.value.delete(image.id)
  pendingImages.value.add(image.id)
  retrySuccessImages.value.delete(image.id)
  clearImageTimeout(image.id)
}

// 超时检测图片加载失败
const IMAGE_LOAD_TIMEOUT = 10000 // 10秒超时

const clearImageTimeout = (imageId) => {
  if (imageLoadTimeouts.value.has(imageId)) {
    clearTimeout(imageLoadTimeouts.value.get(imageId))
    imageLoadTimeouts.value.delete(imageId)
  }
}

const setImageTimeout = (image) => {
  clearImageTimeout(image.id)
  const timeoutId = setTimeout(() => {
    // 超时后检查：如果图片有URL但不在pendingImages中，认为加载失败
    if (!pendingImages.value.has(image.id) && !retryingImages.value.has(image.id)) {
      const url = getPreviewUrl(image)
      if (url && !props.saveDataMode) {
        failedImages.value.add(image.id)
      }
    }
    imageLoadTimeouts.value.delete(image.id)
  }, IMAGE_LOAD_TIMEOUT)
  imageLoadTimeouts.value.set(image.id, timeoutId)
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
  clearImageTimeout(image.id)

  let apiSuccess = false
  if (props.sourceMode === 'local') {
    try {
      await api.get(`/gallery/cache/preview/local/${image.id}`)
      apiSuccess = true
    } catch (e) {
      ElMessage.error('生成缩略图失败')
    }
  } else {
    try {
      await api.get(`/gallery/cache/preview/fetch/${image.id}?file_ext=${image.file_ext || 'jpg'}`)
      apiSuccess = true
    } catch (e) {
      ElMessage.error('缓存预览图失败')
    }
  }

  retryingImages.value.delete(image.id)

  if (apiSuccess) {
    pendingImages.value.add(image.id)
    retrySuccessImages.value.set(image.id, Date.now())
  } else {
    failedImages.value.add(image.id)
    nextTick(() => setImageTimeout(image))
  }
}

// 使用 IntersectionObserver 监听加载更多元素
const setupLoadMoreObserver = () => {
  if (!loadMoreRef.value || loadMoreObserver) return
  
  loadMoreObserver = new IntersectionObserver(
    (entries) => {
      const entry = entries[0]
      if (entry.isIntersecting && props.hasMore && !props.loading && !loadingMore.value && !props.loadError) {
        loadMore()
      }
    },
    {
      root: null,
      rootMargin: '200px',
      threshold: 0
    }
  )
  
  loadMoreObserver.observe(loadMoreRef.value)
}

// 当 hasMore 或 loading 变化时，尝试设置 observer
watch(() => [props.hasMore, props.loading], ([hasMore, loading]) => {
  if (hasMore && !loading && !loadMoreObserver) {
    nextTick(() => setupLoadMoreObserver())
  }
})

// 监听 loadingMore，当变为 false 时重新设置 observer
watch(loadingMore, (loading) => {
  if (!loading && props.hasMore && !props.loading) {
    // 加载完成后，等待 DOM 更新后重新设置 observer
    nextTick(() => {
      if (loadMoreObserver) {
        loadMoreObserver.disconnect()
        loadMoreObserver = null
      }
      setupLoadMoreObserver()
    })
  }
})

onMounted(() => {
  updateColumnCount()
  window.addEventListener('resize', updateColumnCount)
  nextTick(() => {
    observeNewImages()
  })
})

onUnmounted(() => {
  window.removeEventListener('resize', updateColumnCount)
  if (observer) {
    observer.disconnect()
    observer = null
  }
  if (loadMoreObserver) {
    loadMoreObserver.disconnect()
    loadMoreObserver = null
  }
})
</script>

<style scoped>
.waterfall-gallery {
  min-height: 400px;
  width: 100%;
}

.skeleton-container {
  column-gap: 15px;
  width: 100%;
}

.skeleton-item {
  break-inside: avoid;
  margin-bottom: 15px;
  background: var(--skeleton-bg, #f0f0f0);
  border-radius: 8px;
  overflow: hidden;
  position: relative;
  width: 100%;
}

.skeleton-shimmer {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.5) 50%,
    transparent 100%
  );
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
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
  user-select: none;
  -webkit-user-select: none;
  -webkit-touch-callout: none;
  touch-action: manipulation;
  -webkit-touch-callout: none;
  -webkit-tap-highlight-color: transparent;
}

.waterfall-item:hover {
  transform: scale(1.05);
}

.waterfall-item.selected {
  box-shadow: 0 0 0 3px #409EFF;
}

.waterfall-item.touch-focused {
  transform: scale(1.02);
  z-index: 10;
}

.waterfall-item .el-image {
  width: 100%;
  height: 100%;
  display: block;
  -webkit-touch-callout: none;
  touch-action: pan-y pinch-zoom;  /* 允许垂直滚动和双指缩放 */
}

.waterfall-item .el-image__placeholder,
.waterfall-item .el-image__error {
  height: 100%;
  background: var(--skeleton-bg, #f5f7fa);
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 懒加载骨架屏 */
.waterfall-item .el-image__placeholder {
  background: linear-gradient(
    90deg,
    var(--skeleton-bg, #f0f0f0) 0%,
    var(--skeleton-shimmer, #e0e0e0) 50%,
    var(--skeleton-bg, #f0f0f0) 100%
  );
  background-size: 200% 100%;
  animation: placeholder-shimmer 1.5s infinite;
}

@keyframes placeholder-shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

/* 图片淡入效果 */
.waterfall-image {
  opacity: 0;
  transition: opacity 0.4s ease-in-out;
}

.waterfall-image.fade-in {
  opacity: 1;
}

/* 安全模式模糊 - 非 Safe 图片 */
.waterfall-image.safe-blur :deep(.el-image__inner) {
  filter: blur(20px) brightness(var(--safe-blur-brightness, 0.7));
  transition: filter 0.3s ease;
}

.waterfall-image.safe-blur:hover :deep(.el-image__inner) {
  filter: blur(15px) brightness(var(--safe-blur-brightness-hover, 0.8));
}

/* 日间模式模糊亮度 */
html:not(.dark-mode) .waterfall-image.safe-blur :deep(.el-image__inner) {
  --safe-blur-brightness: 0.95;
  --safe-blur-brightness-hover: 0.98;
}

/* 黑暗模式模糊亮度 */
html.dark-mode .waterfall-image.safe-blur :deep(.el-image__inner) {
  --safe-blur-brightness: 0.6;
  --safe-blur-brightness-hover: 0.7;
}

/* 选中指示器 - 右上角圆形勾选 */
.selection-indicator {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 10;
  width: 24px;
  height: 24px;
  background: rgba(64, 158, 255, 0.85);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 14px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.selection-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(64, 158, 255, 0.15);
  pointer-events: none;
}

.image-error,
.image-placeholder {
  width: 100%;
  height: 100%;
  min-height: 200px;
  background: var(--skeleton-bg, #f0f0f0);
  background-size: 200% 100%;
  animation: placeholder-shimmer 1.5s infinite;
}

.image-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--text-muted, #909399);
  background: var(--skeleton-bg, #f5f7fa);
  width: 100%;
  height: 100%;
}

.image-placeholder {
  width: 100%;
  height: 100%;
  background: var(--skeleton-bg, #f5f7fa);
}

/* 图片信息悬浮层 - 始终显示 */
.image-info-overlay {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.5));
  color: white;
  padding: 8px;
}

.image-info-content {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
}

.info-id {
  font-weight: bold;
}

.info-size {
  color: rgba(255, 255, 255, 0.8);
}

.info-rating {
  font-size: 10px;
}

.downloaded-dot {
  width: 8px;
  height: 8px;
  background: #67C23A;
  border-radius: 50%;
  margin-left: auto;
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
  margin-top: 24px;
  margin-bottom: 24px;
}

.load-more-btn {
  padding: 12px 32px !important;
  font-size: 14px !important;
  border-radius: 20px !important;
  background: var(--bg-tertiary) !important;
  border: 1px solid var(--border-color) !important;
  color: var(--text-primary) !important;
  transition: all 0.3s ease !important;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1) !important;
}

.load-more-btn:hover:not(:disabled) {
  background: var(--el-color-primary) !important;
  border-color: var(--el-color-primary) !important;
  color: white !important;
  transform: translateY(-2px) !important;
  box-shadow: 0 4px 16px rgba(64, 158, 255, 0.3) !important;
}

.load-more-btn:disabled {
  opacity: 0.7 !important;
  cursor: not-allowed !important;
}

.load-more-loading {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
