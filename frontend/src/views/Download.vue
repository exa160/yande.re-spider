<template>
  <div class="download-page">
    <div class="toolbar">
      <span class="title">下载任务</span>
      <el-button type="primary" size="small" @click="refreshAll">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </div>

    <el-tabs v-model="activeTab" class="task-tabs" @tab-change="onTabChange">
      <el-tab-pane
        v-for="tab in tabs"
        :key="tab.key"
        :name="tab.key"
      >
        <template #label>
          <span class="tab-label">
            {{ tab.label }}
            <el-badge
              v-if="counts[tab.key] !== null && counts[tab.key] > 0"
              :value="counts[tab.key]"
              :type="tab.badgeType"
              :max="999"
              class="tab-badge"
            />
          </span>
        </template>

        <div v-if="isMobile" v-loading="loading" class="task-cards">
          <div v-for="task in tasks" :key="task.task_id" class="task-card">
            <div class="card-header">
              <span class="card-id">{{ getFileName(task) }}</span>
              <el-tag :type="getStatusType(task.status)" size="small">
                {{ getStatusText(task.status) }}
              </el-tag>
            </div>
            <div class="card-progress">
              <el-progress
                :percentage="Math.round(task.progress * 100)"
                :status="getProgressStatus(task.status)"
                :stroke-width="6"
              />
            </div>
            <div class="card-info">
              <span class="card-size">
                {{ formatFileSize(task.downloaded_size) }} / {{ task.file_size ? formatFileSize(task.file_size) : '-' }}
              </span>
              <span v-if="task.speed" class="card-speed">{{ formatSpeed(task.speed) }}</span>
            </div>
            <div v-if="activeTab === 'failed' && task.error_message" class="card-error">
              <el-button text size="small" @click="toggleError(task.task_id)">
                <el-icon><Warning /></el-icon>
                {{ errorExpanded[task.task_id] ? '收起错误' : '查看错误' }}
              </el-button>
              <div v-show="errorExpanded[task.task_id]" class="error-detail">
                {{ task.error_message }}
              </div>
            </div>
            <div class="card-actions">
              <el-button
                v-if="task.status === 'failed'"
                type="primary"
                size="small"
                @click="onCardAction({action:'start', task})"
              >重试</el-button>
              <el-button
                v-if="task.status === 'cancelled'"
                type="primary"
                size="small"
                @click="onCardAction({action:'start', task})"
              >重试</el-button>
              <el-button
                v-if="task.status === 'downloading'"
                type="warning"
                size="small"
                @click="onCardAction({action:'pause', task})"
              >暂停</el-button>
              <el-button
                v-if="task.status === 'paused'"
                type="success"
                size="small"
                @click="onCardAction({action:'resume', task})"
              >恢复</el-button>
              <!-- TODO 取消功能暂未开放：worker 在下载期间无 stop signal（F bug），
                   取消后状态会被强制覆盖为 COMPLETED。等修复后再启用。 -->
              <el-button
                v-if="['pending', 'downloading', 'paused'].includes(task.status)"
                size="small"
                disabled
                title="取消功能暂未开放"
              >取消</el-button>
              <el-button
                type="danger"
                size="small"
                @click="onCardAction({action:'delete', task})"
              >删除</el-button>
            </div>
          </div>
          <el-empty
            v-if="tasks.length === 0 && !loading"
            :description="emptyText"
          />
        </div>

        <el-table
          v-else
          v-loading="loading"
          :data="tasks"
          style="width: 100%"
          size="small"
        >
          <el-table-column prop="image_id" label="图片ID" width="90" />
          <el-table-column label="文件名" show-overflow-tooltip>
            <template #default="{ row }">
              {{ getFileName(row) }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="getStatusType(row.status)" size="small">
                {{ getStatusText(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="进度" width="140">
            <template #default="{ row }">
              <el-progress
                :percentage="Math.round(row.progress * 100)"
                :status="getProgressStatus(row.status)"
                :stroke-width="8"
              />
            </template>
          </el-table-column>
          <el-table-column label="大小" width="160" show-overflow-tooltip>
            <template #default="{ row }">
              {{ formatFileSize(row.downloaded_size) }} / {{ row.file_size ? formatFileSize(row.file_size) : '-' }}
            </template>
          </el-table-column>
          <el-table-column
            v-if="activeTab === 'failed'"
            label="错误信息"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              {{ row.error_message || '-' }}
            </template>
          </el-table-column>
          <el-table-column label="速度" width="90">
            <template #default="{ row }">
              <span v-if="row.speed">{{ formatSpeed(row.speed) }}</span>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="240" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.status === 'failed'"
                type="primary"
                size="small"
                link
                @click="onCardAction({action:'start', task:row})"
              >重试</el-button>
              <el-button
                v-if="row.status === 'cancelled'"
                type="primary"
                size="small"
                link
                @click="onCardAction({action:'start', task:row})"
              >重试</el-button>
              <el-button
                v-if="row.status === 'downloading'"
                type="warning"
                size="small"
                link
                @click="onCardAction({action:'pause', task:row})"
              >暂停</el-button>
              <el-button
                v-if="row.status === 'paused'"
                type="success"
                size="small"
                link
                @click="onCardAction({action:'resume', task:row})"
              >恢复</el-button>
              <!-- TODO 取消功能暂未开放：worker 在下载期间无 stop signal（F bug），
                   取消后状态会被强制覆盖为 COMPLETED。等修复后再启用。 -->
              <el-button
                v-if="['pending', 'downloading', 'paused'].includes(row.status)"
                size="small"
                link
                disabled
                title="取消功能暂未开放"
              >取消</el-button>
              <el-button
                type="danger"
                size="small"
                link
                @click="onCardAction({action:'delete', task:row})"
              >删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination
          v-model:current-page="currentPage"
          :page-size="isMobile ? 10 : 20"
          :total="total"
          :layout="isMobile ? 'total, prev, next' : 'total, prev, pager, next'"
          class="pagination"
          @current-change="loadTasks"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, onBeforeMount, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Warning } from '@element-plus/icons-vue'
import api from '@/api'

const tabs = [
  { key: 'all',       label: '全部',    badgeType: 'primary' },
  { key: 'active',    label: '下载中',  badgeType: 'primary' },
  { key: 'completed', label: '已完成',  badgeType: 'success' },
  { key: 'failed',    label: '错误',    badgeType: 'danger'  },
  { key: 'cancelled', label: '已取消',  badgeType: 'info'    },
]

const TAB_STATUS_MAP = {
  all:       null,
  active:    ['pending', 'downloading', 'paused'],
  completed: ['completed'],
  failed:    ['failed'],
  cancelled: ['cancelled'],
}

const TAB_SORT_MAP = {
  all:       { sort_by: 'created_at',   order: 'desc' },
  active:    { sort_by: 'created_at',   order: 'asc'  },
  completed: { sort_by: 'completed_at', order: 'desc' },
  failed:    { sort_by: 'completed_at', order: 'desc' },
  cancelled: { sort_by: 'completed_at', order: 'desc' },
}

const activeTab = ref('active')
const tasks = ref([])
const loading = ref(false)
const currentPage = ref(1)
const total = ref(0)
const isMobile = ref(false)
const errorExpanded = ref({})
const counts = ref({
  all: null, active: null, completed: null, failed: null, cancelled: null
})

const checkMobile = () => {
  isMobile.value = window.innerWidth <= 768
}

onBeforeMount(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

const getStatusText = (status) => ({
  pending:    '等待中',
  downloading:'下载中',
  paused:     '已暂停',
  completed:  '已完成',
  failed:     '失败',
  cancelled:  '已取消',
}[status] || status)

const getStatusType = (status) => {
  const types = {
    pending:    'info',
    downloading:'primary',
    paused:     'warning',
    completed:  'success',
    failed:     'danger',
    cancelled:  'info'
  }
  return types[status] || 'info'
}

const getProgressStatus = (status) => {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'exception'
  return null
}

const getFileName = (task) => {
  return task.file_name || task.yande_data?.id || task.image_id || '-'
}

const formatFileSize = (bytes) => {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(2)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

const formatSpeed = (bytesPerSecond) => {
  if (!bytesPerSecond) return '0 B/s'
  if (bytesPerSecond < 1024) return `${bytesPerSecond.toFixed(0)} B/s`
  if (bytesPerSecond < 1024 * 1024) return `${(bytesPerSecond / 1024).toFixed(1)} KB/s`
  return `${(bytesPerSecond / 1024 / 1024).toFixed(1)} MB/s`
}

const emptyText = computed(() => {
  const map = {
    all:       '暂无下载任务',
    active:    '当前没有进行中的任务',
    completed: '还没有完成的任务',
    failed:    '没有失败的任务',
    cancelled: '没有取消的任务',
  }
  return map[activeTab.value] || '暂无下载任务'
})

const loadCounts = async () => {
  try {
    const resp = await api.get('/download/tasks/count')
    const data = resp.data?.data || resp.data || {}
    counts.value = {
      all:       (data.pending || 0) + (data.downloading || 0) + (data.paused || 0)
                 + (data.completed || 0) + (data.failed || 0) + (data.cancelled || 0),
      active:    (data.pending || 0) + (data.downloading || 0) + (data.paused || 0),
      completed: data.completed || 0,
      failed:    data.failed || 0,
      cancelled: data.cancelled || 0,
    }
  } catch (e) {
    console.warn('[Download] load counts failed', e)
  }
}

const loadTasks = async (showLoading = true) => {
  if (showLoading) loading.value = true
  try {
    const tab = activeTab.value
    const statusList = TAB_STATUS_MAP[tab]
    const sort = TAB_SORT_MAP[tab]
    const params = {
      page: currentPage.value,
      page_size: isMobile.value ? 10 : 20,
      sort_by: sort.sort_by,
      order: sort.order,
    }
    if (statusList) {
      params.status = [...statusList]
    }
    const response = await api.get('/download/tasks', { params })
    const body = response.data?.data !== undefined ? response.data : response
    tasks.value = Array.isArray(body.data) ? body.data : []
    total.value = body.total || 0
  } catch (error) {
    ElMessage.error('加载任务列表失败：' + (error?.response?.data?.message || error.message))
  } finally {
    if (showLoading) loading.value = false
  }
}

const refreshAll = async () => {
  await Promise.all([loadTasks(), loadCounts()])
}

let pollTimer = null
const startPolling = () => {
  if (pollTimer) return
  pollTimer = setInterval(() => {
    if (activeTab.value === 'active') {
      loadTasks(false)
    }
  }, 2000)
}
const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const onTabChange = () => {
  currentPage.value = 1
  errorExpanded.value = {}
  loadTasks()
  loadCounts()
}

watch(activeTab, (v) => {
  if (v === 'active') startPolling()
  else stopPolling()
})

const onCardAction = async ({ action, task }) => {
  const actions = {
    start:   { url: `/download/task/${task.task_id}/start`,   msg: '任务已启动' },
    pause:   { url: `/download/task/${task.task_id}/pause`,   msg: '任务已暂停' },
    resume:  { url: `/download/task/${task.task_id}/resume`,  msg: '任务已恢复' },
    cancel:  { url: `/download/task/${task.task_id}/cancel`,  msg: '任务已取消', confirm: '确定要取消该任务吗？' },
    delete:  { url: `/download/task/${task.task_id}`,         msg: '任务已删除', method: 'delete', confirm: '确定要删除该任务吗？' },
  }
  const cfg = actions[action]
  if (!cfg) return

  if (cfg.confirm) {
    try {
      await ElMessageBox.confirm(cfg.confirm, '提示', { type: 'warning' })
    } catch (e) {
      if (e === 'cancel') return
      throw e
    }
  }

  try {
    const method = cfg.method || 'post'
    await api[method](cfg.url)
    ElMessage.success(cfg.msg)
    await Promise.all([loadTasks(), loadCounts()])
  } catch (e) {
    ElMessage.error(`${cfg.msg}失败：${e?.response?.data?.message || e.message}`)
  }
}

const toggleError = (taskId) => {
  errorExpanded.value[taskId] = !errorExpanded.value[taskId]
}

onMounted(async () => {
  await Promise.all([loadTasks(), loadCounts()])
  if (activeTab.value === 'active') startPolling()
})

onUnmounted(() => {
  stopPolling()
  window.removeEventListener('resize', checkMobile)
})
</script>

<style scoped>
.download-page {
  padding: 15px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.task-tabs {
  margin-bottom: 10px;
}
.task-tabs :deep(.el-tabs__nav-wrap--scrollable) {
  padding: 0 8px;
}
.task-tabs :deep(.el-tabs__item) {
  font-size: 13px;
  padding: 0 12px !important;
}

.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.tab-badge {
  margin-left: 2px;
}

.task-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 0 8px;
}

.task-card {
  background: var(--bg-primary);
  border-radius: 8px;
  padding: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.card-id {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  word-break: break-all;
}

.card-progress {
  margin-bottom: 6px;
}

.card-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.card-size {
  font-size: 12px;
  color: var(--text-muted);
}

.card-speed {
  font-size: 12px;
  color: var(--text-primary);
  font-weight: 500;
}

.card-error {
  margin: 8px 0;
  padding: 8px;
  background: #fef0f0;
  border-radius: 4px;
  font-size: 12px;
}
.error-detail {
  margin-top: 6px;
  color: #f56c6c;
  word-break: break-all;
  white-space: pre-wrap;
}

.card-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.card-actions .el-button {
  flex: 1;
  min-width: 60px;
}

.pagination {
  margin-top: 15px;
  justify-content: center;
}

@media screen and (max-width: 768px) {
  .toolbar {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
  .toolbar .el-button {
    width: 100%;
  }
  .task-tabs :deep(.el-tabs__header) {
    margin-bottom: 10px;
  }
  .task-card {
    padding: 10px;
  }
}
</style>
