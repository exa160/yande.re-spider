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

.dark-mode .el-table td.el-table__cell {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.dark-mode .el-table__body-wrapper {
  background: var(--bg-secondary);
}

.dark-mode .el-table__empty-block {
  background: var(--bg-secondary);
}

.dark-mode .el-table__empty-text {
  color: var(--text-muted);
}

.dark-mode .el-table__fixed-right-patch {
  background: var(--bg-secondary) !important;
}

.dark-mode .el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell {
  background: var(--bg-tertiary);
}

.dark-mode .el-table__body tr:hover > td.el-table__cell {
  background: var(--hover-bg);
}

.dark-mode .el-table th.el-table__cell {
  background: var(--bg-tertiary);
}

/* Config.vue sidebar tab 激活态暗色适配 */
.dark-mode .config-menu .menu-item.active {
  background: #1a1a2e;
  border-right-color: #5b9bd5;
}

.dark-mode .el-pagination {
  color: var(--text-secondary);
  --el-pagination-bg-color: var(--bg-tertiary);
  --el-pagination-button-disabled-bg-color: var(--bg-secondary);
  --el-pagination-button-color: var(--text-secondary);
  --el-pagination-button-disabled-color: var(--text-muted);
}

.dark-mode .el-pagination .btn-prev,
.dark-mode .el-pagination .btn-next {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.dark-mode .el-pagination .btn-prev:disabled,
.dark-mode .el-pagination .btn-next:disabled {
  background: var(--bg-secondary);
}

.dark-mode .el-pager li {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.dark-mode .el-pager li.active {
  background: var(--el-color-primary);
  color: #fff;
}

.dark-mode .el-pager li:hover {
  color: var(--el-color-primary);
}

.dark-mode .el-pagination__sizes .el-select .el-input__wrapper {
  background: var(--bg-tertiary);
}

.dark-mode .el-pagination__total {
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

/* el-button 暗色适配 — 排除 primary/danger/text（各自有专用规则），其余全变深灰 */
.dark-mode .el-button:not(.el-button--primary):not(.el-button--danger):not(.el-button--text),
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

.dark-mode .el-button:not(.el-button--primary):not(.el-button--danger):not(.el-button--text):hover,
.dark-mode .el-button.el-button--success:hover,
.dark-mode .el-button.el-button--warning:hover,
.dark-mode .el-button.el-button--info:hover {
  background-color: var(--hover-bg) !important;
  border-color: #409EFF !important;
  color: #409EFF !important;
}

/* el-button primary/danger 暗色适配 — 用绝对色值替代 EP 浅色变量（dark/css-vars.css 未导入） */
.dark-mode .el-button.el-button--primary {
  background-color: #2563eb !important;
  border-color: #2563eb !important;
  color: #e0e0e0 !important;
}

.dark-mode .el-button.el-button--primary:hover {
  background-color: #1d4ed8 !important;
  border-color: #1d4ed8 !important;
  color: #fff !important;
}

.dark-mode .el-button.el-button--primary:active {
  background-color: #1e40af !important;
  border-color: #1e40af !important;
  color: #fff !important;
}

.dark-mode .el-button.el-button--danger {
  background-color: #dc2626 !important;
  border-color: #dc2626 !important;
  color: #e0e0e0 !important;
}

.dark-mode .el-button.el-button--danger:hover {
  background-color: #b91c1c !important;
  border-color: #b91c1c !important;
  color: #fff !important;
}

.dark-mode .el-button.el-button--danger:active {
  background-color: #991b1b !important;
  border-color: #991b1b !important;
  color: #fff !important;
}

/* el-segmented 暗色适配 */
.dark-mode .el-segmented {
  --el-segmented-bg-color: var(--bg-tertiary);
  --el-segmented-item-color: var(--text-primary);
  --el-segmented-item-hover-color: var(--text-primary);
  --el-segmented-item-active-color: #fff;
  --el-segmented-item-active-bg-color: var(--el-color-primary);
  --el-segmented-item-selected-bg-color: #2563eb;
  background-color: var(--bg-tertiary);
}

.dark-mode .el-segmented .el-segmented__item {
  color: var(--text-primary);
}

.dark-mode .el-segmented .el-segmented__item:hover {
  background-color: #4a4a4a;
  color: var(--text-primary);
}

.dark-mode .el-segmented .el-segmented__item.is-selected {
  background-color: var(--el-color-primary);
  color: #fff;
  border-color: var(--el-color-primary);
}

.dark-mode .el-segmented .el-segmented__item.is-selected:hover {
  background-color: var(--el-color-primary-light-3);
  color: #fff;
}

.dark-mode .el-segmented .el-segmented__group {
  background-color: var(--bg-tertiary);
}

/* el-tag 暗色适配 — status/type 标签在暗色下改深底浅字 */
.dark-mode .el-tag {
  background-color: var(--bg-tertiary);
  border-color: var(--border-color);
  color: var(--text-primary);
}

.dark-mode .el-tag.el-tag--primary {
  background-color: #1a3a6b;
  border-color: #2563eb;
  color: #93c5fd;
}

.dark-mode .el-tag.el-tag--success {
  background-color: #1a3d2e;
  border-color: #16a34a;
  color: #86efac;
}

.dark-mode .el-tag.el-tag--warning {
  background-color: #3d2e1a;
  border-color: #ca8a04;
  color: #fde68a;
}

.dark-mode .el-tag.el-tag--danger {
  background-color: #3d1a1a;
  border-color: #dc2626;
  color: #fca5a5;
}

.dark-mode .el-tag.el-tag--info {
  background-color: #2d2d3d;
  border-color: #6b7280;
  color: #d1d5db;
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
