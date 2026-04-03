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
  overflow-x: hidden;
}

#app {
  height: 100%;
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', Arial, sans-serif;
  overflow-x: hidden;
}

/* 自定义滚动条样式 */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.2);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.3);
}

.dark-mode ::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
}

.dark-mode ::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.3);
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
