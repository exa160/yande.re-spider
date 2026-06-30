<template>
  <div class="preview-cleanup-panel">
    <div class="panel-header">
      <div class="panel-title">预览图清理</div>
      <div class="panel-desc">删除 <code>downloads/previews/</code> 下的缩略图缓存</div>
    </div>

    <!-- 状态 ① 初始 -->
    <div v-if="currentState === 'idle'" class="panel-body">
      <el-alert type="warning" :closable="false" show-icon class="panel-alert">
        本地清理会释放几百 MB ~ 几 GB；全量清理会丢失所有未下载原图的预览。
      </el-alert>
      <div class="button-row">
        <el-button
          type="primary"
          :loading="evaluating"
          :disabled="evaluating"
          class="action-btn"
          @click="handleEvaluate('clean_local_previews')"
        >
          <div class="btn-title">本地清理</div>
          <div class="btn-subtitle">仅清有原图可再生的</div>
        </el-button>
        <el-button
          type="warning"
          :loading="evaluating"
          :disabled="evaluating"
          class="action-btn"
          @click="handleEvaluate('clean_all_previews')"
        >
          <div class="btn-title">全量清理</div>
          <div class="btn-subtitle">清空整个 previews/</div>
        </el-button>
      </div>
    </div>

    <!-- 状态 ② 评估完成 / 清理中 -->
    <div v-else-if="currentState === 'evaluated' || currentState === 'cleaning'" class="panel-body">
      <h4 class="state-h4">清理信息</h4>
      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-card-label">命中文件</div>
          <div class="stat-card-value">{{ formatNumber(evalResult?.matched) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-card-label">预计释放</div>
          <div class="stat-card-value">{{ formatBytes(evalResult?.total_bytes) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-card-label">模式</div>
          <div class="stat-card-value mode-label">{{ modeLabel }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-card-label">耗时</div>
          <div class="stat-card-value">{{ evalResult?.duration_ms ?? 0 }} ms</div>
        </div>
      </div>
      <el-alert type="error" :closable="false" show-icon class="panel-alert">
        清理后将无法恢复。再次点击"确认清理"才真正执行。
      </el-alert>
      <div class="action-row">
        <el-button @click="resetState" :disabled="cleaning">取消</el-button>
        <el-button
          type="danger"
          :loading="cleaning"
          :disabled="cleaning || (evalResult?.matched ?? 0) === 0"
          @click="handleConfirmClean"
        >
          确认清理
        </el-button>
      </div>
    </div>

    <!-- 状态 ③ 清理完成 -->
    <div v-else-if="currentState === 'done'" class="panel-body">
      <h4 class="state-h4 done-title">✓ 清理完成</h4>
      <div class="stat-grid">
        <div class="stat-card success">
          <div class="stat-card-label">实际删除</div>
          <div class="stat-card-value">{{ formatNumber(cleanResult?.deleted) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-card-label">实际释放</div>
          <div class="stat-card-value">{{ formatBytes(cleanResult?.total_bytes) }}</div>
        </div>
        <div class="stat-card" :class="{ failed: (cleanResult?.failed ?? 0) > 0 }">
          <div class="stat-card-label">失败</div>
          <div class="stat-card-value">{{ cleanResult?.failed ?? 0 }} 个文件</div>
        </div>
        <div class="stat-card">
          <div class="stat-card-label">耗时</div>
          <div class="stat-card-value">{{ formatDuration(cleanResult?.duration_ms) }}</div>
        </div>
      </div>
      <div class="action-row">
        <el-button type="primary" @click="resetState">关闭</el-button>
      </div>
    </div>

    <!-- 错误条 -->
    <el-alert
      v-if="error"
      type="error"
      :closable="false"
      show-icon
      class="panel-alert"
    >
      {{ error }}
    </el-alert>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { cleanupPreviews } from '@/api'

const currentState = ref('idle')  // 'idle' | 'evaluated' | 'cleaning' | 'done'
const evaluating = ref(false)
const cleaning = ref(false)
const error = ref(null)
const selectedMode = ref(null)
const evalResult = ref(null)
const cleanResult = ref(null)

const modeLabel = computed(() => {
  return selectedMode.value === 'clean_local_previews' ? '本地清理' : '全量清理'
})

function resetState() {
  currentState.value = 'idle'
  evaluating.value = false
  cleaning.value = false
  error.value = null
  selectedMode.value = null
  evalResult.value = null
  cleanResult.value = null
}

async function handleEvaluate(mode) {
  if (evaluating.value || cleaning.value) return
  selectedMode.value = mode
  evaluating.value = true
  error.value = null
  try {
    const resp = await cleanupPreviews(mode, true)
    evalResult.value = resp.data
    currentState.value = 'evaluated'
  } catch (e) {
    error.value = `评估失败：${e.message || '未知错误'}`
  } finally {
    evaluating.value = false
  }
}

async function handleConfirmClean() {
  if (cleaning.value || evaluating.value) return
  if (!selectedMode.value) return
  cleaning.value = true
  error.value = null
  try {
    const resp = await cleanupPreviews(selectedMode.value, false)
    cleanResult.value = resp.data
    currentState.value = 'done'
  } catch (e) {
    error.value = `清理失败：${e.message || '未知错误'}`
  } finally {
    cleaning.value = false
  }
}

function formatNumber(n) {
  if (n == null) return '0'
  return Number(n).toLocaleString('en-US')
}

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const k = 1024
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  const value = bytes / Math.pow(k, i)
  return `${value.toFixed(value >= 100 ? 0 : value >= 10 ? 1 : 2)} ${units[i]}`
}

function formatDuration(ms) {
  if (!ms || ms <= 0) return '0 ms'
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(2)} s`
}
</script>

<style scoped>
.preview-cleanup-panel {
  margin-top: 16px;
  padding: 16px;
  background: var(--bg-secondary, #ffffff);
  border: 1px solid var(--border-color, #ebeef5);
  border-radius: 6px;
}

.panel-header {
  margin-bottom: 12px;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #303133);
  margin-bottom: 4px;
}

.panel-desc {
  font-size: 12px;
  color: var(--text-secondary, #606266);
  line-height: 1.5;
}

.panel-desc code {
  background: var(--bg-primary, #f5f7fa);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 11px;
}

.panel-body {
  padding-top: 4px;
}

.panel-alert {
  margin: 12px 0;
}

.state-h4 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #303133);
  margin: 0 0 12px 0;
}

.state-h4.done-title {
  color: #67c23a;
}

.button-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-top: 12px;
}

.action-btn {
  height: auto !important;
  padding: 14px 10px !important;
  white-space: normal;
  line-height: 1.4;
}

.btn-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 4px;
}

.btn-subtitle {
  font-size: 11px;
  opacity: 0.85;
}

.action-row {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 12px;
}

.stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 4px;
}

.stat-card {
  padding: 10px 12px;
  background: var(--bg-primary, #f5f7fa);
  border-radius: 6px;
  border-left: 3px solid #dcdfe6;
}

.stat-card.success {
  border-left-color: #67c23a;
  background: #f0f9eb;
}

.stat-card.failed {
  border-left-color: #f56c6c;
  background: #fef0f0;
}

.stat-card-label {
  font-size: 12px;
  color: var(--text-muted, #909399);
  margin-bottom: 4px;
}

.stat-card-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #303133);
}

.mode-label {
  font-size: 14px;
}

/* 暗色模式 */
html.dark-mode .preview-cleanup-panel {
  background: #1f1f2e;
  border-color: #3a3a4a;
}

html.dark-mode .stat-card {
  background: #1a1a2e;
}

html.dark-mode .stat-card.success {
  background: #1a2e1a;
}

html.dark-mode .stat-card.failed {
  background: #2e1a1a;
}

html.dark-mode .panel-desc {
  color: #c0c4cc;
}

html.dark-mode .panel-desc code {
  background: #2a2a3a;
  color: #d0d0e0;
}

/* 移动端 */
@media screen and (max-width: 768px) {
  .button-row {
    grid-template-columns: 1fr;
  }

  .stat-grid {
    gap: 8px;
  }

  .stat-card {
    padding: 8px 10px;
  }

  .stat-card-value {
    font-size: 14px;
  }
}
</style>