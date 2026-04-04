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
          'image-loaded': pendingImages.has(image.id) || image.local_preview_path,
          'touch-focused': touchFocusedId === image.id || mouseFocusedId === image.id
        }"
        @click="handleImageClick(image)"
        @touchstart="handleTouchStart(image, $event)"
        @touchmove="handleTouchMove($event)"
        @touchend="handleTouchEnd($event)"
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
          :key="retryKeys.value + '-' + image.id"
          :src="getPreviewUrl(image)"
          :alt="image.id.toString()"
          fit="cover"
          class="waterfall-image"
          :class="{ 'fade-in': pendingImages.has(image.id) || image.local_preview_path }"
          @error="handleImageError(image)"
          @load="handleImageLoad(image)"
        >
          <template #error>
            <div class="image-error" :style="{ height: getPlaceholderHeight(image) + 'px' }">
              <el-icon><Picture /></el-icon>
            </div>
          </template>
          <template #placeholder>
            <div class="image-placeholder skeleton-shimmer" :style="{ height: getPlaceholderHeight(image) + 'px' }"></div>
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
            <div v-if="image.local_file_path || image.local_preview_path" class="downloaded-dot"></div>
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
  }
})

const emit = defineEmits(['image-click', 'image-select', 'load-more', 'multi-select-start'])

const loadingMore = ref(false)
const failedImages = ref(new Set())
const pendingImages = ref(new Set())
const retryKeys = ref(0)
const retryingImages = ref(new Set())
const displayedImages = ref([])

// 长按选择相关
const touchFocusedId = ref(null)
const longPressTimer = ref(null)
const isLongPress = ref(false)
const longPressSelectedId = ref(null) // 长按刚选中的图片 ID，滑动时跳过
const LONG_PRESS_DURATION = 500
const MOVE_THRESHOLD = 10 // 移动阈值，超过则不触发长按
const touchStartPos = ref({ x: 0, y: 0 })

// 鼠标长按支持
const isMouseDown = ref(false)
const mouseFocusedId = ref(null)
const mouseStartPos = ref({ x: 0, y: 0 })
const LONG_PRESS_DURATION_PC = 400 // PC端长按时长

// 懒加载：追踪已进入可视区的图片
const visibleImages = ref(new Set())
let observer = null

const containerRef = ref(null)
const galleryRef = ref(null)
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
    return
  }
  const existingIds = new Set(displayedImages.value.map(img => img.id))
  const newItems = newImages.filter(img => !existingIds.has(img.id))
  if (newItems.length > 0) {
    displayedImages.value = [...displayedImages.value, ...newItems]
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
  if (isLongPress.value || longPressSelectedId.value === image.id) {
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
  isLongPress.value = true
  emit('multi-select-start')
  handleSelect(image, !isSelected(image))
  
  // 标记刚选中的图片，滑动时跳过不取消
  longPressSelectedId.value = image.id
  setTimeout(() => {
    longPressSelectedId.value = null
  }, 500)
  
  // 延迟重置isLongPress，让点击事件能正确检测到长按状态
  setTimeout(() => {
    isLongPress.value = false
  }, 300)
}

// 触控开始
const handleTouchStart = (image, event) => {
  if (!props.selectable) return
  isLongPress.value = false
  touchFocusedId.value = image.id
  
  // 记录初始触摸位置
  if (event.touches && event.touches.length > 0) {
    touchStartPos.value = {
      x: event.touches[0].clientX,
      y: event.touches[0].clientY
    }
  }
  
  longPressTimer.value = setTimeout(() => {
    handleLongPress(image)
    // 长按成功后阻止后续的点击事件
    event.stopPropagation()
    event.preventDefault()
  }, LONG_PRESS_DURATION)
}

// 触控移动 - 用 elementFromPoint 获取当前手指下的图片
const handleTouchMove = (event) => {
  if (!props.selectable || !event.touches || event.touches.length === 0) return
  
  const touch = event.touches[0]
  const deltaX = Math.abs(touch.clientX - touchStartPos.value.x)
  const deltaY = Math.abs(touch.clientY - touchStartPos.value.y)
  
  // 移动超过阈值，取消长按计时器
  if (deltaX > MOVE_THRESHOLD || deltaY > MOVE_THRESHOLD) {
    if (longPressTimer.value) {
      clearTimeout(longPressTimer.value)
      longPressTimer.value = null
    }
  }
  
  // 获取当前手指下的图片
  const target = document.elementFromPoint(touch.clientX, touch.clientY)
  if (target) {
    const waterfallItem = target.closest('.waterfall-item')
    if (waterfallItem) {
      const imageId = parseInt(waterfallItem.dataset.imageId)
      if (imageId) {
        // 多选模式下，手指滑过自动选中/取消
        // 但跳过刚长按选中的图片，避免取消选中
        if (props.selectedImages.length > 0 && imageId !== touchFocusedId.value && imageId !== longPressSelectedId.value) {
          const isCurrentlySelected = isSelectedById(imageId)
          handleSelectById(imageId, !isCurrentlySelected)
        }
        touchFocusedId.value = imageId
      }
    }
  }
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

// 触控结束
const handleTouchEnd = (event) => {
  if (longPressTimer.value) {
    clearTimeout(longPressTimer.value)
    longPressTimer.value = null
  }
  // 触控结束时检测是否需要加载更多
  handleTouchSlidEnd(event)
}

// PC端鼠标长按开始
const handleMouseDown = (image, event) => {
  if (!props.selectable || event.button !== 0) return // 只响应左键
  isMouseDown.value = true
  mouseFocusedId.value = image.id
  mouseStartPos.value = { x: event.clientX, y: event.clientY }
  
  longPressTimer.value = setTimeout(() => {
    if (isMouseDown.value && mouseFocusedId.value === image.id) {
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
    // 重试后或已缓存的图片，优先使用缓存的预览图
    if (isPending && image.local_preview_path) {
      return `/api/v1/gallery/cache/preview/${image.id}.${image.file_ext || 'jpg'}?t=${retryKeys.value}`
    }
    // 重试后没有预览图但有原图，生成缩略图
    if (isPending && image.local_file_path) {
      return `/api/v1/gallery/cache/preview/generate/${image.id}?file_ext=${image.file_ext || 'jpg'}${ts}`
    }
    // 省流模式且未缓存，不加载图片
    if (props.saveDataMode) {
      return ''
    }
    // 非省流模式，正常显示
    if (image.local_preview_path) {
      return `/api/v1/gallery/cache/preview/${image.id}.${image.file_ext || 'jpg'}`
    }
    if (image.local_file_path) {
      return `/api/v1/gallery/cache/preview/generate/${image.id}?file_ext=${image.file_ext || 'jpg'}`
    }
    return ''
  }
  // 在线模式：懒加载，未进入可视区时不加载
  if (props.sourceMode === 'yande' && !visibleImages.value.has(image.id)) {
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

  // 增加触底检测灵敏度，50px阈值
  if (scrollTop + windowHeight >= documentHeight - 50) {
    if (props.hasMore && !props.loading && !loadingMore.value) {
      loadMore()
    }
  }
}

// 触控滑动触底检测（移动端）
const handleTouchSlidEnd = (event) => {
  if (!props.hasMore || props.loading || loadingMore.value) return
  
  const container = containerRef.value
  if (!container) return
  
  const rect = container.getBoundingClientRect()
  const scrollTop = window.pageYOffset || document.documentElement.scrollTop
  const windowHeight = window.innerHeight
  const documentHeight = document.documentElement.scrollHeight
  
  // 检测是否滑到了接近底部
  if (scrollTop + windowHeight >= documentHeight - 100) {
    loadMore()
  }
}

onMounted(() => {
  updateColumnCount()
  window.addEventListener('resize', updateColumnCount)
  window.addEventListener('scroll', handleScroll)
  nextTick(() => observeNewImages())
})

onUnmounted(() => {
  window.removeEventListener('resize', updateColumnCount)
  window.removeEventListener('scroll', handleScroll)
  if (observer) {
    observer.disconnect()
    observer = null
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
  display: block;
  min-height: 200px;
}

.waterfall-item .el-image__placeholder,
.waterfall-item .el-image__error {
  min-height: 200px;
  background: #f5f7fa;
}

/* 懒加载骨架屏 */
.waterfall-item .el-image__placeholder {
  background: linear-gradient(
    90deg,
    #f0f0f0 0%,
    #e0e0e0 50%,
    #f0f0f0 100%
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
  background: var(--skeleton-bg, #f0f0f0);
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
  margin-top: 20px;
}
</style>
