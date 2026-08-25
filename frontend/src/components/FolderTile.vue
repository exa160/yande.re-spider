<template>
  <div class="folder-tile" @click="$emit('click', folder)">
    <div class="folder-preview-grid" :style="`--cols: ${gridCols}`">
      <div
        v-for="img in folder.preview_images"
        :key="img.id"
        :data-image-id="img.id"
        class="folder-preview-cell"
      >
        <img
          v-if="!saveDataMode"
          :src="srcEnabled.has(img.id) ? `/api/v1/gallery/cache/preview/${img.id}` : undefined"
          :alt="img.id.toString()"
          loading="lazy"
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

const props = defineProps({
  folder: { type: Object, required: true },
  saveDataMode: { type: Boolean, default: false },
})

defineEmits(['click'])

// 与 WaterfallGallery.vue 保持一致的并发门控模式：
// srcEnabled 是「真实 URL 准入白名单」，只有 ID 加入此 Set 后 <img> 才会请求真实 URL。
// IntersectionObserver 在图片进入视口时把 ID push 到 loadingQueue（FIFO），
// processQueue 按 MAX_PREVIEW_CONCURRENT 限额把 ID 从队列挪到 srcEnabled。
const MAX_PREVIEW_CONCURRENT = 10
const loadingQueue = ref([])
const srcEnabled = ref(new Set())
const visibleIds = ref(new Set())
let observer = null

const gridCols = computed(() => {
  const n = props.folder.preview_images?.length || 0
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
  setupObserver()
  // 观察所有当前已挂载的 cell（首屏可见时立即进入队列）
  const root = document.querySelector('.folder-tile')
  if (!root || !observer) return
  const cells = root.querySelectorAll('[data-image-id]')
  cells.forEach(cell => observer.observe(cell))
})

onUnmounted(() => {
  observer?.disconnect()
  observer = null
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
  border-radius: 12px;
  overflow: hidden;
  background: var(--bg-secondary);
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  break-inside: avoid;
  margin-bottom: 16px;
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
</style>
