<template>
  <button v-if="visible" class="floating-back-btn" @click="$emit('click')">
    <el-icon><ArrowLeft /></el-icon>
  </button>
</template>

<script setup>
import { ArrowLeft } from '@element-plus/icons-vue'

defineProps({
  visible: { type: Boolean, default: false },
})

defineEmits(['click'])
</script>

<style scoped>
.floating-back-btn {
  position: fixed;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: rgba(var(--bg-secondary-rgb, 255, 255, 255), 0.8);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 1000;
  transition: opacity 0.2s, background 0.2s;
}
html.dark-mode .floating-back-btn {
  background: rgba(var(--bg-secondary-rgb, 45, 45, 45), 0.8);
  border: 1px solid rgba(255, 255, 255, 0.1);
}
.floating-back-btn:hover {
  background: rgba(var(--bg-secondary-rgb, 255, 255, 255), 1);
}

/* 桌面端：与 AdvancedQuery 同一基线，悬浮于搜索栏左侧 */
@media (min-width: 980px) {
  .floating-back-btn {
    bottom: 28px;
    left: calc(50% - 450px - 60px);
    opacity: 0.8;
  }
}

/* 移动端：搜索栏上方左对齐，更透明 */
@media (max-width: 979px) {
  .floating-back-btn {
    bottom: 78px;
    left: 20px;
    opacity: 0.5;
  }
}
</style>