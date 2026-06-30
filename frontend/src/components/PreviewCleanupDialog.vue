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
    <div v-if="currentState === 'evaluating'" class="state-content">
      <p class="state-desc">{{ modeSubtitle }}</p>
      <div class="loading-row">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在评估匹配文件...</span>
      </div>
    </div>

    <div v-else-if="currentState === 'evaluated' || currentState === 'cleaning'" class="state-content">
      <p class="state-desc">{{ modeSubtitle }}</p>
      <el-alert type="warning" :closable="false" show-icon class="state-alert">
        <span v-if="mode === 'clean_local_previews'">
          本地清理会释放几百 MB ~ 几 GB，仅删除有原图可再生的预览。
        </span>
        <span v-else>
          全量清理会丢失所有未下载原图的预览。
        </span>
      </el-alert>
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
      <span v-if="currentState === 'evaluating'"></span>

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

      <el-button v-else type="primary" @click="handleClose(false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { cleanupPreviews } from '@/api'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  mode: { type: String, default: null },
})

const emit = defineEmits(['update:modelValue'])

const currentState = ref('idle')
const cleaning = ref(false)
const error = ref(null)
const evalResult = ref(null)
const cleanResult = ref(null)

const dialogTitle = computed(() => {
  if (props.mode === 'clean_local_previews') return '本地清理预览图'
  if (props.mode === 'clean_all_previews') return '全量清理预览图'
  return '预览图清理'
})

const modeLabel = computed(() => {
  return props.mode === 'clean_local_previews' ? '本地清理' : '全量清理'
})

const modeSubtitle = computed(() => {
  if (props.mode === 'clean_local_previews') {
    return '仅删除 downloads/previews/ 中对应 yande_data down_flag=True（原图已下载）的文件，删除后下次访问会自动重新生成。'
  }
  if (props.mode === 'clean_all_previews') {
    return '清空整个 downloads/previews/ 目录，所有未下载原图的预览都会丢失。'
  }
  return ''
})

const canClose = computed(() => {
  return currentState.value !== 'cleaning'
})

watch(() => [props.modelValue, props.mode], ([visible, newMode]) => {
  if (visible && newMode && currentState.value === 'idle') {
    runEvaluate(newMode)
  }
  if (!visible) {
    setTimeout(() => {
      if (!props.modelValue) resetState()
    }, 300)
  }
})

function resetState() {
  currentState.value = 'idle'
  cleaning.value = false
  error.value = null
  evalResult.value = null
  cleanResult.value = null
}

function handleClose(visible) {
  if (!canClose.value && visible === false) return
  emit('update:modelValue', visible)
}

async function runEvaluate(selectedMode) {
  currentState.value = 'evaluating'
  error.value = null
  try {
    const resp = await cleanupPreviews(selectedMode, true)
    evalResult.value = resp.data
    currentState.value = 'evaluated'
  } catch (e) {
    error.value = `评估失败：${e.message || '未知错误'}`
    currentState.value = 'evaluated'
  }
}

async function handleConfirmClean() {
  if (!props.mode) return
  cleaning.value = true
  error.value = null
  try {
    const resp = await cleanupPreviews(props.mode, false)
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
.state-content {
  padding: 4px 0;
}

.state-desc {
  font-size: 13px;
  color: var(--text-secondary, #606266);
  line-height: 1.6;
  margin: 0 0 12px 0;
}

.state-h4 {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #303133);
  margin: 16px 0 12px 0;
}

.state-h4.done-title {
  color: #67c23a;
}

.state-alert {
  margin: 12px 0;
}

.loading-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 20px 0;
  color: var(--text-secondary, #606266);
  font-size: 13px;
}

.stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
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