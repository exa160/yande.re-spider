<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="520px"
    :close-on-click-modal="false"
    :close-on-press-escape="currentState === 'idle' || currentState === 'done'"
    :show-close="canClose"
    @update:model-value="handleClose"
  >
    <!-- 状态 ① 初始 -->
    <div v-if="currentState === 'idle'" class="state-content">
      <p class="state-desc">
        删除 <code>downloads/previews/</code> 下的缩略图缓存。先点击按钮评估，再二次确认执行。
      </p>
      <el-alert type="warning" :closable="false" show-icon class="state-alert">
        本地清理会释放几百 MB ~ 几 GB；全量清理会丢失所有未下载原图的预览。
      </el-alert>
      <div class="button-row">
        <el-button
          type="primary"
          size="large"
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
          size="large"
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
    <div v-else-if="currentState === 'evaluated' || currentState === 'cleaning'" class="state-content">
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
      <el-alert type="error" :closable="false" show-icon class="state-alert">
        清理后将无法恢复。再次点击"确认清理"才真正执行。
      </el-alert>
    </div>

    <!-- 状态 ③ 清理完成 -->
    <div v-else-if="currentState === 'done'" class="state-content">
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
    </div>

    <!-- 错误条 -->
    <el-alert
      v-if="error"
      type="error"
      :closable="false"
      show-icon
      class="state-alert"
    >
      {{ error }}
    </el-alert>

    <template #footer>
      <!-- 状态 ①: 取消 -->
      <el-button
        v-if="currentState === 'idle'"
        @click="handleClose(false)"
      >
        取消
      </el-button>

      <!-- 状态 ②: 取消 + 确认清理 -->
      <template v-else-if="currentState === 'evaluated' || currentState === 'cleaning'">
        <el-button :disabled="cleaning" @click="handleClose(false)">取消</el-button>
        <el-button
          type="danger"
          :loading="cleaning"
          :disabled="cleaning || (evalResult?.matched ?? 0) === 0"
          @click="handleConfirmClean"
        >
          确认清理
        </el-button>
      </template>

      <!-- 状态 ③: 关闭 -->
      <el-button v-else type="primary" @click="handleClose(false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { cleanupPreviews } from '@/api'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
})

const emit = defineEmits(['update:modelValue'])

// 状态机
const currentState = ref('idle')  // 'idle' | 'evaluated' | 'cleaning' | 'done'
const evaluating = ref(false)
const cleaning = ref(false)
const error = ref(null)
const selectedMode = ref(null)
const evalResult = ref(null)
const cleanResult = ref(null)

// 计算属性
const dialogTitle = computed(() => {
  if (currentState.value === 'done') return '预览图清理'
  return '预览图清理'
})

const canClose = computed(() => {
  // 评估中 / 清理中禁止关闭弹窗
  return !evaluating.value && !cleaning.value
})

const modeLabel = computed(() => {
  return selectedMode.value === 'clean_local_previews' ? '本地清理' : '全量清理'
})

// 监听 modelValue：关闭时重置状态
watch(() => props.modelValue, (visible) => {
  if (!visible) {
    // 延迟重置，避免动画期间闪烁
    setTimeout(() => {
      if (!props.modelValue) {
        resetState()
      }
    }, 300)
  }
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

function handleClose(visible) {
  if (!canClose.value && visible === false) {
    return  // 拒绝关闭
  }
  emit('update:modelValue', visible)
}

async function handleEvaluate(mode) {
  if (evaluating.value || cleaning.value) return  // NEW GUARD
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
  if (cleaning.value || evaluating.value) return  // NEW GUARD
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

// 工具函数
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
.state-content {
  padding: 4px 0;
}

.state-desc {
  font-size: 13px;
  color: var(--text-secondary, #606266);
  line-height: 1.6;
  margin: 0 0 12px 0;
}

.state-desc code {
  background: var(--bg-primary, #f5f7fa);
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 12px;
}

.state-h4 {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #303133);
  margin: 0 0 16px 0;
}

.state-h4.done-title {
  color: #67c23a;
}

.state-alert {
  margin: 12px 0;
}

.button-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 16px;
}

.action-btn {
  height: auto !important;
  padding: 16px 12px !important;
  white-space: normal;
  line-height: 1.4;
}

.btn-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 4px;
}

.btn-subtitle {
  font-size: 11px;
  opacity: 0.85;
}

.stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 4px;
}

.stat-card {
  padding: 12px 14px;
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
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary, #303133);
}

.mode-label {
  font-size: 15px;
}

/* 暗色模式适配 */
html.dark-mode .stat-card {
  background: #1a1a2e;
}

html.dark-mode .stat-card.success {
  background: #1a2e1a;
}

html.dark-mode .stat-card.failed {
  background: #2e1a1a;
}

html.dark-mode .state-desc {
  color: #c0c4cc;
}

/* 移动端 */
@media screen and (max-width: 768px) {
  :global(.el-dialog) {
    width: 90vw !important;
  }

  .stat-grid {
    gap: 8px;
  }

  .stat-card {
    padding: 10px;
  }

  .stat-card-value {
    font-size: 16px;
  }
}
</style>