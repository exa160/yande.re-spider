<template>
  <div id="app" :class="{ 'dark-mode': isDarkMode }">
    <router-view />
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'

const isDarkMode = ref(localStorage.getItem('dark_mode') === 'true')

watch(isDarkMode, (val) => {
  localStorage.setItem('dark_mode', val ? 'true' : 'false')
  document.documentElement.classList.toggle('dark-mode', val)
})

onMounted(() => {
  document.documentElement.classList.toggle('dark-mode', isDarkMode.value)
})
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body {
  height: 100%;
  width: 100%;
}

#app {
  height: 100%;
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', Arial, sans-serif;
}

/* 浅色模式变量 */
:root {
  --bg-primary: #f5f7fa;
  --bg-secondary: #ffffff;
  --bg-tertiary: #ffffff;
  --text-primary: #303133;
  --text-secondary: #606266;
  --text-muted: #909399;
  --border-color: #e4e7ed;
  --skeleton-bg: #e8e8e8;
  --skeleton-shimmer: #f0f0f0;
  --hover-bg: #f5f7fa;
}

/* 深色模式变量 */
:root.dark-mode {
  --bg-primary: #1a1a1a;
  --bg-secondary: #2d2d2d;
  --bg-tertiary: #3d3d3d;
  --text-primary: #e0e0e0;
  --text-secondary: #a0a0a0;
  --text-muted: #707070;
  --border-color: #404040;
  --skeleton-bg: #3d3d3d;
  --skeleton-shimmer: #4d4d4d;
  --hover-bg: #3d3d3d;
}

/* 全局背景色 */
body {
  background-color: var(--bg-primary);
  color: var(--text-primary);
}

/* 半透明滚动条（仅纵向） */
::-webkit-scrollbar {
  width: 6px;
  height: 0;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: rgba(128, 128, 128, 0.4);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: rgba(128, 128, 128, 0.6);
}

/* Firefox 滚动条（仅纵向） */
* {
  scrollbar-width: thin;
  scrollbar-color: rgba(128, 128, 128, 0.4) transparent;
}

/* 禁用横向滚动 */
html, body {
  overflow-x: hidden;
}

/* Element Plus 深色模式适配 */
.dark-mode .el-table {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.dark-mode .el-table th {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.dark-mode .el-pagination {
  color: var(--text-secondary);
}

.dark-mode .el-dialog {
  background: var(--bg-secondary);
}

.dark-mode .el-card {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.dark-mode .el-form-item__label {
  color: var(--text-secondary);
}
</style>
