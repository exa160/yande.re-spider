<template>
  <div ref="tileRef" class="folder-tile" @click="$emit('click', folder)">
    <div class="folder-preview-grid" :style="`--cols: ${gridCols}`">
      <div
        v-for="img in displayedImages"
        :key="img.id"
        :data-image-id="img.id"
        class="folder-preview-cell"
      >
        <img
          v-if="!saveDataMode"
          :src="srcEnabled.has(img.id) ? previewUrl(img.id) : undefined"
          :alt="img.id.toString()"
          loading="lazy"
          :class="{ 'safe-blur': safeMode && img.rating && img.rating !== 'Safe' }"
          @error="handlePreviewError(img.id)"
        />
        <div v-else class="folder-preview-placeholder">
          <el-icon><Picture /></el-icon>
        </div>
      </div>
    </div>
    <div class="folder-info">
      <span class="folder-name">{{ folder.name }}</span>
      <el-tag size="small">{{ folder.local_count || 0 }}</el-tag>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { Picture } from '@element-plus/icons-vue'
import api from '@/api'

const props = defineProps({
  folder: { type: Object, required: true },
  saveDataMode: { type: Boolean, default: false },
  safeMode: { type: Boolean, default: false },
})

defineEmits(['click'])

// 预览图 URL 策略：所有模式统一用 /cache/preview/{id}（最便宜的路径）
// 缓存命中直接返回文件；缓存未命中走 @error fallback chain：
//   1. /cache/preview/local/{id}（缓存未命中 + 有本地原图 → 从原图生成）
//   2. /cache/preview/fetch/{id}（无本地原图 → 远端下载并缓存，未来「我的最爱」收藏未下载图时启用）
// cache-buster 时间戳（previewCacheBuster）让 <img> 在 fallback 写盘后重新请求 /cache/preview/{id}。
//
// 修复前 FolderTile 硬编码 /cache/preview/{id}，收藏夹预览场景下大量 404；
// 原 handleCellError 只是 srcEnabled 重置，没有真正 fallback —— 本次重写。
const previewUrl = (imageId) => {
  const ts = previewCacheBuster.value.get(imageId)
  return `/api/v1/gallery/cache/preview/${imageId}${ts ? `?ts=${ts}` : ''}`
}

// fallback chain 防重入：同一 image_id 多个 <img> 同时失败时只触发一次链
const fallbackInFlight = ref(new Set())
// cache-buster：fallback 写盘后给 URL 加时间戳让浏览器绕过缓存重新请求 /cache/preview/{id}
// 用 Map 而非普通对象，确保 Vue 3 响应式追踪（Map.set 触发 reactivity）
const previewCacheBuster = ref(new Map())

const handlePreviewError = async (imageId) => {
  if (fallbackInFlight.value.has(imageId)) return
  fallbackInFlight.value.add(imageId)
  try {
    // 步骤 1：尝试本地生成（缓存未命中 + 有本地原图）
    try {
      await api.get(`/gallery/cache/preview/local/${imageId}`)
      // /local/ 成功后文件已写盘，加时间戳让 <img> 重新请求 /cache/preview/{id}
      previewCacheBuster.value.set(imageId, Date.now())
      return
    } catch (_) {
      // /local/ 失败（无本地原图），继续试 /fetch/
    }
    // 步骤 2：尝试远端下载（无本地原图 → 远端下载并缓存）
    try {
      await api.get(`/gallery/cache/preview/fetch/${imageId}`)
      previewCacheBuster.value.set(imageId, Date.now())
    } catch (_) {
      // 两步都失败：保持原 broken 图状态，不打扰用户
    }
  } finally {
    fallbackInFlight.value.delete(imageId)
  }
}

// 与 WaterfallGallery.vue 保持一致的并发门控模式：
// srcEnabled 是「真实 URL 准入白名单」，只有 ID 加入此 Set 后 <img> 才会请求真实 URL。
// IntersectionObserver 在图片进入视口时把 ID push 到 loadingQueue（FIFO），
// processQueue 按 MAX_PREVIEW_CONCURRENT 限额把 ID 从队列挪到 srcEnabled。
const MAX_PREVIEW_CONCURRENT = 10
const loadingQueue = ref([])
const srcEnabled = ref(new Set())
const visibleIds = ref(new Set())
const tileRef = ref(null)
let observer = null
let resizeObserver = null

// 后端 tile_size='adaptive' 永远返 8 张，前端按 tile 实际宽度裁剪显示 4 / 6 / 8 张。
// 阈值 [最小宽度, 显示张数]，从大到小匹配；不命中兜底 4 张。
const ADAPTIVE_THRESHOLDS = [
  [450, 8],
  [300, 6],
  [0, 4],
]
const displayCount = ref(8)

const measureTileWidth = () => {
  if (!tileRef.value) return
  const w = tileRef.value.offsetWidth
  for (const [minW, count] of ADAPTIVE_THRESHOLDS) {
    if (w >= minW) {
      displayCount.value = count
      return
    }
  }
  displayCount.value = 4
}

const displayedImages = computed(() =>
  (props.folder.preview_images || []).slice(0, displayCount.value)
)

const gridCols = computed(() => {
  const n = displayedImages.value.length
  if (n <= 4) return 2
  if (n <= 6) return 3
  return 4  // 8 张 → 4 列
})

const processQueue = () => {
  if (props.saveDataMode) return
  const available = MAX_PREVIEW_CONCURRENT - srcEnabled.value.size
  if (available <= 0) return
  const toProcess = Math.min(available, loadingQueue.value.length)
  for (let i = 0; i < toProcess; i++) {
    srcEnabled.value.add(loadingQueue.value.shift())
  }
}

const setupObserver = () => {
  if (typeof IntersectionObserver === 'undefined') return
  observer = new IntersectionObserver(
    (entries) => {
      entries.forEach(entry => {
        const id = parseInt(entry.target.dataset.imageId)
        if (entry.isIntersecting && !visibleIds.value.has(id)) {
          visibleIds.value.add(id)
          if (!srcEnabled.value.has(id) && !loadingQueue.value.includes(id)) {
            loadingQueue.value.push(id)
            processQueue()
          }
        }
      })
    },
    { rootMargin: '200px' }
  )
}

onMounted(() => {
  measureTileWidth()
  setupObserver()
  // 观察所有当前已挂载的 cell（首屏可见时立即进入队列）
  // 必须用实例作用域的 template ref（tileRef）而非 document.querySelector，
  // 否则多个 FolderTile 共存时只有第一个 tile 的 cells 被 observe（C1 bug）。
  const root = tileRef.value
  if (!root || !observer) return
  const cells = root.querySelectorAll('[data-image-id]')
  cells.forEach(cell => observer.observe(cell))

  // ResizeObserver 监听 tile 宽度变化，触发重新裁剪
  if (typeof ResizeObserver !== 'undefined' && tileRef.value) {
    resizeObserver = new ResizeObserver(() => measureTileWidth())
    resizeObserver.observe(tileRef.value)
  }
})

onUnmounted(() => {
  observer?.disconnect()
  observer = null
  resizeObserver?.disconnect()
  resizeObserver = null
})

// 监听 folder 变化，防御性重置内部状态（虽 folder 一般不会变）
watch(() => props.folder.id, () => {
  loadingQueue.value = []
  srcEnabled.value = new Set()
  visibleIds.value = new Set()
})

// 监听 saveDataMode：开启省流时清空已加载状态；
// 关闭省流时，把历史上已可见过的 cell ID 重新入队（IntersectionObserver
// 不会对停留视口内的 cell 重复触发回调，所以必须自己入队）。
watch(() => props.saveDataMode, async (newMode) => {
  await nextTick()
  if (newMode) {
    srcEnabled.value = new Set()
    loadingQueue.value = []
    return
  }
  for (const id of visibleIds.value) {
    if (!srcEnabled.value.has(id) && !loadingQueue.value.includes(id)) {
      loadingQueue.value.push(id)
    }
  }
  processQueue()
})
</script>

<style scoped>
.folder-tile {
  display: block;
  width: 100%;
  border-radius: 12px;
  overflow: hidden;
  background: var(--bg-secondary);
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}
.folder-tile:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
}

.folder-preview-grid {
  display: grid;
  grid-template-columns: repeat(var(--cols), 1fr);
  gap: 2px;
  aspect-ratio: 4 / 3;
}
.folder-preview-cell {
  background: var(--bg-tertiary);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
.folder-preview-cell img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.folder-preview-placeholder {
  color: var(--text-muted);
  font-size: 20px;
  opacity: 0.5;
}

.folder-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
}
.folder-name {
  flex: 1;
  font-weight: 500;
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

html.dark-mode .folder-tile {
  background: var(--bg-secondary);
}

.folder-preview-cell .safe-blur {
  filter: blur(20px) brightness(var(--safe-blur-brightness, 0.7));
}
</style>
