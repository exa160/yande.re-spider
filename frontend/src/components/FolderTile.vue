<template>
  <div
    ref="tileRef"
    class="folder-tile"
    :class="{ 'virtual-tile': folder.isVirtual, [`virtual-${folder.id}`]: folder.isVirtual, 'compact-mode': compactMode }"
    @click="$emit('click', folder)"
    @long-press="onLongPress"
  >
    <!-- folder-preview-grid 渲染条件（修复问题 10）：
         - 真实磁贴（!isVirtual）永远渲染（保持瀑布流视觉节奏）
         - 虚拟磁贴：
           - 有预览图 → 渲染（缩略图展示）
           - 无预览图：
             - compactMode=true（FavoritePanel 弹窗）→ 不渲染（消除空白占位，磁贴更紧凑）
             - compactMode=false（Gallery 收藏夹瀑布流）→ 渲染（保留 4:3 占位，与真实磁贴视觉一致）
    -->
    <div
      v-if="!folder.isVirtual || hasPreviewImages || !compactMode"
      class="folder-preview-grid"
      :style="`--cols: ${gridCols}`"
    >
      <div
        v-for="img in displayedImages"
        :key="img.id"
        :data-image-id="img.id"
        class="folder-preview-cell"
      >
        <img
          v-if="!saveDataMode"
          :src="srcEnabled.has(img.id) ? previewUrl(img) : undefined"
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
    <div class="folder-info" :class="{ 'hide-name': hideName }">
      <span class="folder-name">{{ folder.name }}</span>
      <el-icon
        v-if="folder.isVirtual"
        class="virtual-badge"
        :title="VIRTUAL_TILE_TITLES[folder.id] || folder.name"
      >
        <StarFilled v-if="folder.id === 'my-favorites'" />
        <Clock v-else-if="folder.id === 'recent-downloads'" />
        <ShuffleIcon v-else />
      </el-icon>
      <el-tag size="small">{{ folder.local_count || 0 }}</el-tag>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { Clock, Picture, StarFilled } from '@element-plus/icons-vue'
import ShuffleIcon from './ShuffleIcon.vue'
import api from '@/api'

// 虚拟磁贴的角标 tooltip 文案（我的最爱 / 随机浏览 / 最近下载）
const VIRTUAL_TILE_TITLES = {
  'my-favorites': '我的最爱',
  random: '随机浏览',
  'recent-downloads': '最近下载',
}

const props = defineProps({
  folder: { type: Object, required: true },
  saveDataMode: { type: Boolean, default: false },
  safeMode: { type: Boolean, default: false },
  // 紧凑模式（修复问题 10）：
  // - compactMode=true：虚拟磁贴无预览图时不渲染 .folder-preview-grid 容器（消除占位）
  // - compactMode=false（默认）：虚拟磁贴无预览图时仍渲染 grid 容器（保留瀑布流视觉节奏）
  // FavoritePanel 弹窗场景传 true，Gallery 收藏夹瀑布流场景不传（默认 false）
  compactMode: { type: Boolean, default: false },
  // 隐藏磁贴名称文字，仅保留图标 + 数量角标。
  // 用于磁贴较多、横向单行空间不足的场景（FavoritePanel 中 3 个虚拟磁贴等分时）。
  // 图标自带 title tooltip（VIRTUAL_TILE_TITLES），悬停仍可看到完整名称。
  hideName: { type: Boolean, default: false },
})

const emit = defineEmits(['click', 'long-press'])

// 虚拟磁贴（我的最爱 / 随机浏览）不弹编辑菜单：
// 转发父组件事件之前先 short-circuit，让上层 @long-press handler 走 no-op。
// 真实磁贴保持原有行为，原样转发事件。
const onLongPress = (e) => {
  if (props.folder?.isVirtual) return
  emit('long-press', e, props.folder)
}

// 预览图 URL：统一走同源 /cache/preview/{id}，与 WaterfallGallery.getPreviewUrl 同源。
//
// 为什么不直接用 API 返回的 img.preview_url：
//   yande_data.preview_url 存的是 yande.re 远端缩略图 URL（DB 原值），
//   浏览器直连会跨域 / 防盗链失败；且旧实现在该分支从不追加 cache-buster，
//   handlePreviewError 把缓存写盘后 <img> 的 src 不会变化 → 永久失败占位。
//
// 三步自愈链（与 get_preview_for_local / fetch_and_cache_preview 一致）：
//   1. /cache/preview/{id}      缓存命中直接返回；未命中 404 → @error
//   2. /cache/preview/local/{id} 有本地原图则生成缩略图写盘
//   3. /cache/preview/fetch/{id} 无本地原图则按 DB preview_url 在线下载写盘
// 步骤 2/3 成功后写 previewCacheBuster，让 <img> 带上 ?ts= 重新请求步骤 1。
const previewUrl = (image) => {
  const imageId = image?.id
  const ts = imageId !== undefined ? previewCacheBuster.value.get(imageId) : null
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

// 虚拟磁贴 + 预览图占位控制：虚拟磁贴无预览图时不应渲染 .folder-preview-grid
// 容器（否则 aspect-ratio: 4/3 会占用空白区域）。仅当「非虚拟磁贴」或「有预览图」才渲染。
// hasPreviewImages 是 grid 容器 v-if 的依据；displayedImages 控制 grid 内部 cells 数量。
const hasPreviewImages = computed(() =>
  (props.folder.preview_images || []).length > 0
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

// 已注册的 cell（避免重复 observe 同一个 DOM 节点）
// 用 WeakSet 而非 Set：cell 被 v-for 复用/替换后旧引用可被 GC
const observedCells = new WeakSet()

// 注册当前已挂载的所有 cell 到 IntersectionObserver。
// 必须用实例作用域的 template ref（tileRef）而非 document.querySelector，
// 否则多个 FolderTile 共存时只有第一个 tile 的 cells 被 observe（C1 bug）。
const observeCells = () => {
  const root = tileRef.value
  if (!root || !observer) return
  root.querySelectorAll('[data-image-id]').forEach((cell) => {
    if (observedCells.has(cell)) return
    observedCells.add(cell)
    observer.observe(cell)
  })
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
  observeCells()

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

// 虚拟磁贴的 preview_images 是异步到达的（useFavoriteFoldersList 拉 /random_browse/preview
// 与 /my_favorites/preview），刷新页面时 onMounted 时数组还是空的 → 当时没有任何 cell
// 被 observe；等 cells 渲染出来后再没人 observe 它们 → id 永远进不了 loadingQueue
// → srcEnabled 缺 id → <img> 没有 src（表现为 loading="lazy" 的空图 + 失败占位）。
// 这里在 preview 列表变化后补注册新 cell。签名用 id 列表，避免数组引用变化导致重复触发。
watch(
  () => displayedImages.value.map((img) => img.id).join(','),
  async () => {
    await nextTick()
    observeCells()
  }
)

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

/* 隐藏名称（磁贴过多、横向空间不足时）：只留图标 + 数量角标并居中 */
.folder-info.hide-name {
  justify-content: center;
  gap: 6px;
  padding: 8px 6px;
}
.folder-info.hide-name .folder-name {
  display: none;
}

html.dark-mode .folder-tile {
  background: var(--bg-secondary);
}

.folder-preview-cell .safe-blur {
  filter: blur(20px) brightness(var(--safe-blur-brightness, 0.7));
}

/* 虚拟磁贴（我的最爱 / 随机浏览）
 * 区分两种使用场景：
 * 1. compact-mode（FavoritePanel 弹窗）：无预览图时 grid 不渲染，整体紧凑
 * 2. 非 compact（Gallery 收藏夹瀑布流）：保留 .folder-preview-grid 占位
 *    让虚拟磁贴与真实磁贴视觉节奏一致（min-height: 120px + bg-secondary 灰底）
 */
.virtual-tile .folder-preview-grid {
  min-height: 120px;
  background: var(--bg-tertiary);
}
.virtual-tile.compact-mode .folder-preview-grid {
  /* compact 模式（FavoritePanel）：无论是否有预览图都不强制 120px 占位
     —— 由 v-if 控制 grid 是否渲染，此规则仅影响背景色和最小高度的细微差异 */
  min-height: 0;
  background: transparent;
}

.virtual-badge {
  font-size: 14px;
  color: var(--el-color-primary, #409EFF);
  flex-shrink: 0;
}
html.dark-mode .virtual-badge {
  color: var(--el-color-primary, #79bbff);
}
</style>
