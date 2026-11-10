<template>
  <div ref="wrapperRef" class="folder-grid-wrapper">
    <!-- 骨架屏：与真实网格同宽同列数，避免加载完成时的布局跳变 -->
    <div v-if="loading" class="folder-grid" :style="gridStyle">
      <div v-for="i in skeletonCount" :key="i" class="folder-grid-skeleton">
        <div class="folder-grid-skeleton-preview"></div>
        <div class="folder-grid-skeleton-info"></div>
      </div>
    </div>

    <!-- 磁贴网格 -->
    <div v-else class="folder-grid" :style="gridStyle">
      <div
        v-for="f in folders"
        :key="f.id"
        class="folder-grid-item"
        :data-folder-id="f.id"
      >
        <FolderTile
          :folder="f"
          :tile-size="tileSize"
          :save-data-mode="saveDataMode"
          :safe-mode="safeMode"
          :preview-epoch="previewEpoch"
          observe-visibility
          @click="$emit('folder-click', f)"
          @visible="$emit('visible', f)"
        />
      </div>
    </div>

    <!-- 加载更多 -->
    <div
      v-show="(hasMore || loadError) && !loading"
      ref="loadMoreRef"
      class="folder-grid-load-more"
    >
      <el-button
        @click="handleLoadMoreClick"
        :disabled="isLoadingMore"
        class="load-more-btn"
      >
        <span v-if="isLoadingMore" class="load-more-loading">
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
/**
 * 收藏夹一级页的文件夹磁贴网格（替代瀑布流的 folder 模式）
 *
 * 为什么不用瀑布流：
 *   收藏夹磁贴高度是固定的（预览区 4:3 + 固定信息栏），瀑布流的「错落高度」没有收益，
 *   反而带来两个问题：
 *     1. 每列底部参差（看起来不整齐）；
 *     2. 分页条数与列数不对齐时，最后一行必然缺几块。
 *   改为等宽 CSS Grid 后：磁贴等宽、行对齐。
 *
 * 列数由 JS 显式下发（grid-template-columns: repeat(N, 1fr)），不用 CSS auto-fill：
 *   auto-fill 的 minmax(420px, 1fr) 有两个问题 →
 *     1. 轨道宽有 420px 硬下限 → 窄屏（手机竖屏 390px）轨道超出容器 → 内容被裁；
 *     2. 手机横屏（844px）只放得下 1 条轨道 → 出现「图片 3 列、收藏夹 1 列」的割裂。
 *   显式列数后，列数与图片瀑布流共用同一套窄屏档位（1/2/3），且永远不会超出容器。
 *
 * 与分页的关系：
 *   本组件把实际列数通过 columns-change 上报给 Gallery.vue，
 *   Gallery 用它把「每页收藏夹个数」向下取整到列数整数倍 → 每页都填满行。
 */
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import FolderTile from '@/components/FolderTile.vue'
import {
  FOLDER_GRID_GAP,
  getColumnCount,
} from '@/composables/columnLayout'

const props = defineProps({
  // 当前已加载的收藏夹列表（虚拟磁贴已在 Gallery 侧 prepend 进来）
  folders: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  hasMore: { type: Boolean, default: false },
  isLoadingMore: { type: Boolean, default: false },
  loadError: { type: Boolean, default: false },
  tileSize: { type: String, default: 'adaptive' },
  saveDataMode: { type: Boolean, default: false },
  safeMode: { type: Boolean, default: false },
  previewEpoch: { type: Number, default: 0 },
})

const emit = defineEmits(['folder-click', 'visible', 'load-more', 'columns-change'])

const wrapperRef = ref(null)
const loadMoreRef = ref(null)
const columnCount = ref(1)
let loadMoreObserver = null
let resizeObserver = null

// 骨架屏数量：铺满 2 行（与真实磁贴的预览比例一致，切换时不跳）
const skeletonCount = computed(() => Math.max(6, columnCount.value * 2))

// 网格参数直接用内联样式下发（列数 + 间距）→ 与 columnLayout 的常量同源，
// 不会出现「CSS 轨道数」与「JS 推算列数」不一致的情况。
// （不用 CSS 变量包 repeat() 的计数，避免 var() 在 repeat() 中的兼容性坑）
const gridStyle = computed(() => ({
  gridTemplateColumns: `repeat(${columnCount.value}, minmax(0, 1fr))`,
  gap: `${FOLDER_GRID_GAP}px`,
}))

const updateColumnCount = () => {
  const el = wrapperRef.value
  if (!el) return
  const width = el.offsetWidth
  // 被 v-show 隐藏时宽度为 0 → 保留上一次的测量值（否则列数被误判成 1，重新显示时整页重排）
  if (!width) return
  const next = getColumnCount(width, 'folder')
  if (next !== columnCount.value) {
    columnCount.value = next
    emit('columns-change', next)
  }
}

const handleLoadMoreClick = () => {
  if (props.isLoadingMore) return
  emit('load-more')
}

// 滚动到底自动加载更多。
//
// root: null（视口）——与 WaterfallGallery 的既有实现保持一致。
// 实测本应用的滚动容器是 <body>（html/body height:100%，body 内容溢出后由 body 滚动），
// 元素相对视口的位置会随 body 滚动变化 → root:null 的 IntersectionObserver 能正常触发。
const setupLoadMoreObserver = () => {
  if (!loadMoreRef.value || loadMoreObserver) return
  loadMoreObserver = new IntersectionObserver(
    (entries) => {
      const entry = entries[0]
      if (
        entry.isIntersecting &&
        props.hasMore &&
        !props.loading &&
        !props.isLoadingMore &&
        !props.loadError
      ) {
        emit('load-more')
      }
    },
    { root: null, rootMargin: '200px', threshold: 0 }
  )
  loadMoreObserver.observe(loadMoreRef.value)
}

// 撑不满一屏时自动继续加载。
//
// 为什么需要：一屏可能装不满当页磁贴（网格磁贴比瀑布流磁贴大）→ 如果此时既不
// 可滚动、sentinel 又进不了可视区，后面的收藏夹就永远看不到。
// 这里在列表变化后补一次判断：网格高度没超过"可视高度"且还有更多 → 继续加载下一页。
// 加载是异步的（父组件用 isLoadingMore 串行化）→ 不会并发；有更多时才继续 → 不会死循环。
const fillViewportIfNeeded = async () => {
  const el = wrapperRef.value
  if (!el || !props.hasMore || props.loading || props.isLoadingMore || props.loadError) return
  // 可视高度 = 视口高度（body 是滚动容器，window.innerHeight 即一屏高度）
  if (el.offsetHeight <= window.innerHeight) {
    emit('load-more')
  }
}

watch(() => [props.hasMore, props.loading], ([hasMore, loading]) => {
  if (hasMore && !loading && !loadMoreObserver) {
    nextTick(() => setupLoadMoreObserver())
  }
})

// 加载完成后重建 observer（否则 sentinel 位置变化后不再触发）
watch(() => props.isLoadingMore, (loading) => {
  if (!loading && props.hasMore && !props.loading) {
    nextTick(() => {
      if (loadMoreObserver) {
        loadMoreObserver.disconnect()
        loadMoreObserver = null
      }
      setupLoadMoreObserver()
    })
  }
})

// 列表变化 → 内容可能仍撑不满一屏 → 继续加载
watch(
  () => props.folders.length,
  () => {
    nextTick(() => fillViewportIfNeeded())
  }
)

onMounted(() => {
  updateColumnCount()
  window.addEventListener('resize', updateColumnCount)
  if (typeof ResizeObserver !== 'undefined' && wrapperRef.value) {
    resizeObserver = new ResizeObserver(() => {
      updateColumnCount()
      fillViewportIfNeeded()
    })
    resizeObserver.observe(wrapperRef.value)
  }
  nextTick(() => {
    // hasMore 在挂载时已为 true 不会被 watch 捕获 → 挂载时补挂
    if (props.hasMore && !props.loading) setupLoadMoreObserver()
    fillViewportIfNeeded()
  })
})

onUnmounted(() => {
  window.removeEventListener('resize', updateColumnCount)
  resizeObserver?.disconnect()
  resizeObserver = null
  loadMoreObserver?.disconnect()
  loadMoreObserver = null
})
</script>

<style scoped>
.folder-grid-wrapper {
  width: 100%;
}

/* 等宽网格：列数由 JS 显式下发（内联 style 的 repeat(N, minmax(0,1fr))）
   → 永远不会超出容器宽度，也不会出现「CSS 轨道数 ≠ JS 列数」的漂移 */
.folder-grid {
  display: grid;
  grid-template-columns: repeat(1, minmax(0, 1fr));
  gap: var(--fg-gap, 15px);
  align-items: start;
}

.folder-grid-item {
  min-width: 0;
}

/* 骨架屏：与 FolderTile 的结构一致（4:3 预览区 + 信息栏） */
.folder-grid-skeleton {
  border-radius: 12px;
  overflow: hidden;
  background: var(--bg-secondary);
}

.folder-grid-skeleton-preview {
  aspect-ratio: 4 / 3;
  background: var(--bg-tertiary);
  position: relative;
  overflow: hidden;
}

.folder-grid-skeleton-preview::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(var(--bg-primary-rgb, 255, 255, 255), 0.35),
    transparent
  );
  animation: folder-grid-shimmer 1.4s infinite;
}

.folder-grid-skeleton-info {
  height: 36px;
  padding: 8px 12px;
}

@keyframes folder-grid-shimmer {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}

.folder-grid-load-more {
  display: flex;
  justify-content: center;
  padding: 20px 0 0;
}

.load-more-loading {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
</style>
