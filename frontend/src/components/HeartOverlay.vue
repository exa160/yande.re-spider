<template>
  <button
    v-if="showHeart"
    class="heart-overlay"
    :class="{ active: isFavorited, loading }"
    @click.stop.prevent="toggle"
    :aria-label="isFavorited ? '取消我的最爱' : '加入我的最爱'"
  >
    <el-icon>
        <StarFilled v-if="isFavorited" />
        <Star v-else />
      </el-icon>
  </button>
</template>

<script setup>
/**
 * HeartOverlay —— 我的最爱切换按钮
 *
 * v2 修复 v1 bug：
 *   - v1 加边框破坏视觉一致性 → v2 强制 border: none / outline: none
 *   - v1 独立定位 → v2 作为 .image-info-content 的子元素使用 flex/grid 布局
 *   - v1 全局点击 → v2 用 @click.stop.prevent 屏蔽冒泡，避免与长按卡片冲突
 *
 * Props:
 *   - imageId:          必填，目标图片 ID
 *   - initialFavorited: 初始收藏状态（默认 false）
 *   - showHeart:        是否渲染按钮（默认 false，外部按需控制显隐）
 *
 * Emits:
 *   - changed({ imageId, favorited, downloadStarted })  切换完成后通知父组件同步状态；
 *     downloadStarted=true 表示后端「收藏自动下载」已建任务，父组件据此打「下载中」标记
 */
import { ref, watch } from 'vue'
import { Star, StarFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { myFavoritesApi } from '@/api/myFavorites'

const props = defineProps({
  imageId: { type: Number, required: true },
  initialFavorited: { type: Boolean, default: false },
  showHeart: { type: Boolean, default: false },
})
const emit = defineEmits(['changed'])

const isFavorited = ref(props.initialFavorited)
const loading = ref(false)

// 同步外部 prop 变化到内部 ref：用户在瀑布流切图时同一 HeartOverlay 实例
// 不会被 Vue 重建（无 :key），需要主动 watch initialFavorited 来同步状态
// 同时兼容 imageId 切换：图片变了 state 也重置
watch(() => [props.imageId, props.initialFavorited], ([newId, newFav]) => {
  isFavorited.value = newFav
  // imageId 切换时清 loading（防止旧请求覆盖新状态）
  loading.value = false
})

async function toggle() {
  if (loading.value) return
  loading.value = true
  try {
    let downloadStarted = false
    if (isFavorited.value) {
      await myFavoritesApi.remove(props.imageId)
    } else {
      // 开启「收藏自动下载」时后端会顺带建下载任务，响应 data.download_started 告知前端，
      // 让该图立刻转「下载中」（否则只能等下一次状态轮询才发现）
      const resp = await myFavoritesApi.add(props.imageId)
      downloadStarted = resp?.data?.download_started === true
    }
    isFavorited.value = !isFavorited.value
    emit('changed', {
      imageId: props.imageId,
      favorited: isFavorited.value,
      downloadStarted,
    })
  } catch (e) {
    ElMessage.error('操作失败：' + (e?.message || ''))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.heart-overlay {
  /* 关键（v2 修复 v1 加边框的 bug）：显式覆盖 happy-dom / 浏览器 button 默认 border */
  border: none;
  outline: none;
  background: transparent;
  cursor: pointer;
  padding: 0;
  margin: 0;
  color: rgba(255, 255, 255, 0.85);
  font-size: 18px;
  line-height: 1;
  transition: color 0.2s, transform 0.2s;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.heart-overlay:hover {
  transform: scale(1.15);
  color: #fff;
}
.heart-overlay.active {
  color: #F56C6C;
}
.heart-overlay.loading {
  opacity: 0.6;
  cursor: wait;
}
</style>