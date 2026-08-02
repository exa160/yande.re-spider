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
  --bg-secondary-rgb: 255, 255, 255;
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
  --bg-secondary-rgb: 45, 45, 45;
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

/* el-input / el-input-number 暗色适配 */
.dark-mode .el-input__wrapper,
.dark-mode .el-input-number {
  background-color: var(--bg-secondary);
  box-shadow: 0 0 0 1px var(--border-color) inset;
}

.dark-mode .el-input__wrapper.is-focus,
.dark-mode .el-input-number.is-focus {
  box-shadow: 0 0 0 1px #409EFF inset !important;
}

.dark-mode .el-input__inner {
  color: var(--text-primary);
}

.dark-mode .el-input__inner::placeholder {
  color: var(--text-muted);
}

.dark-mode .el-textarea__inner {
  background-color: var(--bg-secondary);
  color: var(--text-primary);
  border-color: var(--border-color);
}

/* el-input-number 边上的 +/- 按钮暗色适配 */
.dark-mode .el-input-number__decrease,
.dark-mode .el-input-number__increase {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border-color: var(--border-color);
}

.dark-mode .el-input-number__decrease:hover,
.dark-mode .el-input-number__increase:hover {
  background: var(--hover-bg);
  color: #409EFF;
}

/* el-button 暗色适配 — element-plus 2.5 的 .el-button--default 直接写死 background/color,
   CSS 变量覆盖无效,必须直接覆盖属性 + !important */
.dark-mode .el-button.el-button--default,
.dark-mode .el-button.el-button--success,
.dark-mode .el-button.el-button--warning,
.dark-mode .el-button.el-button--info {
  --el-button-bg-color: var(--bg-tertiary);
  --el-button-text-color: var(--text-primary);
  --el-button-border-color: var(--border-color);
  --el-button-hover-bg-color: var(--hover-bg);
  --el-button-hover-text-color: #409EFF;
  --el-button-hover-border-color: #409EFF;
  --el-button-active-bg-color: var(--hover-bg);
  --el-button-active-border-color: #409EFF;
  background-color: var(--bg-tertiary) !important;
  border-color: var(--border-color) !important;
  color: var(--text-primary) !important;
}

.dark-mode .el-button.el-button--default:hover,
.dark-mode .el-button.el-button--success:hover,
.dark-mode .el-button.el-button--warning:hover,
.dark-mode .el-button.el-button--info:hover {
  background-color: var(--hover-bg) !important;
  border-color: #409EFF !important;
  color: #409EFF !important;
}

.dark-mode .el-button--text {
  color: var(--text-secondary);
}

/* el-switch 暗色适配 — 关闭时深色杆,开启时深蓝色,圆点也变暗 */
.dark-mode .el-switch {
  --el-switch-off-color: var(--bg-tertiary);
  --el-switch-on-color: #1e6fd9;
  --el-switch-border-color: var(--border-color);
}

.dark-mode .el-switch__core {
  border-color: var(--border-color);
  background-color: var(--bg-tertiary);
}

.dark-mode .el-switch.is-checked .el-switch__core {
  background-color: #1e6fd9 !important;
  border-color: #1e6fd9 !important;
}

/* 圆点变暗:关闭时深灰,开启时也用深灰 */
.dark-mode .el-switch__core .el-switch__action {
  background-color: #c0c4cc !important;
}

/* el-checkbox / el-radio 暗色适配 */
.dark-mode .el-checkbox__label,
.dark-mode .el-radio__label {
  color: var(--text-primary);
}

/* el-alert 暗色适配 */
.dark-mode .el-alert {
  background-color: var(--bg-tertiary);
  color: var(--text-primary);
}

/* 深色模式下自定义 tooltip 样式 */
.dark-mode .el-tooltip__popper.is-light {
  background: var(--bg-secondary) !important;
  color: var(--text-primary) !important;
  border: 1px solid var(--border-color) !important;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.3) !important;
}

.dark-mode .el-tooltip__popper.is-light .el-tooltip__arrow::before {
  border-color: var(--bg-secondary) !important;
}
</style>
