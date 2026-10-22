<template>
  <div class="download-page">
    <div class="toolbar">
      <span class="title">下载任务</span>
      <div class="toolbar-actions">
        <!-- 失败任务的批量恢复：服务端一次重试全部 failed（不受分页限制） -->
        <el-button
          v-if="activeTab === 'failed' && counts.failed > 0"
          type="primary"
          size="small"
          class="toolbar-action"
          :loading="retryingAll"
          @click="onRetryAllFailed"
        >
          <el-icon><RefreshRight /></el-icon>
          全部重试 ({{ counts.failed }})
        </el-button>

        <!-- 清理只作用于已完成记录：仅在「全部 / 已完成」显示；
             固定行高保证它出现/消失时页签不上下跳 -->
        <el-button
          v-if="CLEAR_VISIBLE_TABS.includes(activeTab)"
          type="danger"
          plain
          size="small"
          class="toolbar-action toolbar-clear"
          :disabled="completedCount === 0"
          @click="openClearDialog"
        >
          <el-icon><Delete /></el-icon>
          清除记录 ({{ completedCount.toLocaleString() }})
        </el-button>
      </div>
    </div>

    <el-dialog
      v-model="clearDialogVisible"
      title="清除下载记录"
      width="min(440px, 92vw)"
      class="clear-dialog"
      append-to-body
    >
      <el-alert type="warning" :closable="false" show-icon class="clear-alert">
        只删除下载任务记录，<b>不会删除本地图片文件</b>；清除后「最近下载」列表会同步变少。
      </el-alert>

      <div v-loading="clearPreviewLoading" class="clear-options" role="radiogroup">
        <div
          v-for="opt in clearOptions"
          :key="opt.value"
          class="clear-option"
          :class="{ active: clearScope === opt.value }"
          role="radio"
          :aria-checked="clearScope === opt.value"
          @click="clearScope = opt.value"
        >
          <span class="clear-option-label">{{ opt.label }}</span>
          <span class="clear-option-count">
            将删除 {{ opt.count.toLocaleString() }} 条
          </span>
        </div>
      </div>

      <template #footer>
        <el-button size="small" @click="clearDialogVisible = false">取消</el-button>
        <el-button
          type="danger"
          size="small"
          :loading="clearingRecords"
          :disabled="selectedClearCount === 0"
          @click="onClearConfirm"
        >
          清除 {{ selectedClearCount.toLocaleString() }} 条
        </el-button>
      </template>
    </el-dialog>

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
            <div class="card-times">
              <span class="card-time">
                <span class="time-label">添加：</span>{{ formatDateTime(task.created_at) }}
              </span>
              <span class="card-time">
                <span class="time-label">完成：</span>{{ formatDateTime(task.completed_at) }}
              </span>
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
              <el-button
                v-if="['pending', 'downloading', 'paused'].includes(task.status)"
                size="small"
                @click="onCardAction({action:'cancel', task})"
              >取消</el-button>
              <el-button
                type="danger"
                plain
                size="small"
                class="card-delete"
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
          :default-sort="{ prop: sortBy, order: sortOrder === 'asc' ? 'ascending' : 'descending' }"
          @sort-change="onSortChange"
        >
          <el-table-column
            prop="image_id"
            label="图片ID"
            width="90"
            sortable="custom"
          />
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
          <el-table-column
            prop="completed_at"
            label="完成时间"
            width="170"
            sortable="custom"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              {{ formatDateTime(row.completed_at) }}
            </template>
          </el-table-column>
          <el-table-column
            prop="created_at"
            label="添加时间"
            width="170"
            sortable="custom"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              {{ formatDateTime(row.created_at) }}
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
              <el-button
                v-if="['pending', 'downloading', 'paused'].includes(row.status)"
                size="small"
                link
                @click="onCardAction({action:'cancel', task:row})"
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
import { RefreshRight, Delete, Warning } from '@element-plus/icons-vue'
import api from '@/api'
import { recentDownloadsApi } from '@/api/recentDownloads'
import { fetchRecentDownloadsCount } from '@/composables/useFavoritesConfig'
import { useDownloadState } from '@/composables/useDownloadState'

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
  all:       { sort_by: 'image_id', order: 'desc' },
  // active tab 默认把 status='downloading' 任务排最前
  // 用户点列头排序后由 sortBy/sortOrder 控制，此字段失效
  active:    { sort_by: 'image_id', order: 'desc', download_first: true },
  completed: { sort_by: 'image_id', order: 'desc' },
  failed:    { sort_by: 'image_id', order: 'desc' },
  cancelled: { sort_by: 'image_id', order: 'desc' },
}

const activeTab = ref('active')
const tasks = ref([])
const loading = ref(false)
const currentPage = ref(1)
const total = ref(0)
const isMobile = ref(false)
const errorExpanded = ref({})
const sortBy = ref('image_id')   // 当前排序字段
const sortOrder = ref('desc')    // 当前排序方向
const counts = ref({
  all: null, active: null, completed: null, failed: null, cancelled: null,
  // running = pending + downloading，**不含 paused**。paused 任务的进度条不会
  // 动，继续 2s 轮询纯属空转，因此「是否该轮询」只看 running。
  running: null,
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

const formatDateTime = (isoString) => {
  if (!isoString) return '-'
  const d = new Date(isoString)
  if (isNaN(d.getTime())) return '-'
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
         `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
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

// 图库侧「下载中 / 已下载」标识的单例状态。下载页是少数几个**不经过 markQueued**
// 就能改变任务状态的地方（启动/恢复/暂停/取消/删除），所以这里要显式通知它，
// 否则图库的标识会停在旧值——尤其是 useDownloadState 空闲停轮询之后，
// 它不会自己醒来对账。
const {
  wake: wakeDownloadState,
  reset: resetDownloadStateRaw,
} = useDownloadState()

/** 取任务关联的 image_id（不同版本响应里字段位置有差异，兜底 yande_data.id） */
const taskImageId = (task) => task?.image_id ?? task?.yande_data?.id ?? null

/** 解除图库侧该图的下载态（暂停/取消/删除后调用） */
const resetDownloadState = (imageId) => {
  if (imageId == null) return
  resetDownloadStateRaw(imageId)
}

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
      running:   (data.pending || 0) + (data.downloading || 0),
    }
    // counts 是「该不该轮询」的权威来源，所有刷新入口（挂载 / 切页签 / 任何操作后）
    // 都汇聚到这里，所以 syncPolling 只挂这一处即可。
    syncPolling()
  } catch (e) {
    // 失败时**不**调 syncPolling：此时 counts 还是上一次的值，据此重新裁决可能
    // 把「实际有任务在跑、但旧值 running=0」误判成空闲而停掉定时器。而停掉之后
    // 没有任何东西会再触发 loadCounts（这正是按需启停的前提）→ 进度条永久卡死
    // 且不自愈。保守维持当前定时器状态：多轮询几次的代价远小于 UI 卡住。
    // 网络恢复后由窗口聚焦 / 页面恢复可见 / online 事件或下一次成功请求纠正。
    console.warn('[Download] load counts failed', e)
  }
}

const loadTasks = async (showLoading = true) => {
  if (showLoading) loading.value = true
  try {
    const tab = activeTab.value
    const statusList = TAB_STATUS_MAP[tab]
    const defaultSort = TAB_SORT_MAP[tab]
    // 只有当用户没点过列头排序（sortBy === default sort_by）时，
    // 才传 download_first，让 active tab 默认把 downloading 任务排最前。
    const useDownloadFirst =
      defaultSort?.download_first === true &&
      sortBy.value === defaultSort.sort_by
    const params = {
      page: currentPage.value,
      page_size: isMobile.value ? 10 : 20,
      sort_by: sortBy.value,
      order: sortOrder.value,
    }
    if (statusList) {
      params.status = [...statusList]
    }
    if (useDownloadFirst) {
      params.download_first = true
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

// 手动刷新入口已移除：页面重新可见 / 窗口聚焦 / 网络恢复时补一次刷新。
// 运行中的任务仍由 2s 轮询覆盖；1s 去重避免 focus 与 visibilitychange 双触发。
const AUTO_REFRESH_DEDUPE_MS = 1000
let lastAutoRefreshAt = 0
const refreshOnReturn = () => {
  if (isUnmounted.value) return
  const now = Date.now()
  if (now - lastAutoRefreshAt < AUTO_REFRESH_DEDUPE_MS) return
  lastAutoRefreshAt = now
  refreshAll()
}
const onVisibilityChange = () => {
  if (document.visibilityState === 'visible') refreshOnReturn()
}

// ============================================================================
// 记录清理
// ----------------------------------------------------------------------------
// 只删除「已完成」下载任务记录（status=completed 且 completed_at 非空），
// **不删除**本地图片文件，也不改 yande_data.down_flag —— 本地图库、随机浏览、
// 最近下载磁贴均不受影响（图片仍在磁盘）。
//
// 与「最近下载」共用同一批数据（download_task），因此清理后本页「已完成」
// 历史与「最近下载」列表会同时变少，这是设计上的已知取舍。
//
// 安全由后端保证：DAO 固定只删 status==COMPLETED，
// pending / downloading / paused / failed / cancelled 一律保留。
//
// UI：工具栏「更多」下拉 → 标准对话框。对话框逐项显示各范围的
// 实际删除条数（后端 clear-preview 接口），一次明确确认即可。
// ============================================================================
/** 仅在能看见「已完成」记录的两个页签出现清除入口 */
const CLEAR_VISIBLE_TABS = ['all', 'completed']
/** 清除范围：0 = 全部已完成（其余为「保留最近 N 天」） */
const CLEAR_SCOPE_OPTIONS = [
  { value: 7,  label: '保留最近 7 天' },
  { value: 30, label: '保留最近 30 天' },
  { value: 90, label: '保留最近 90 天' },
  { value: 0,  label: '全部已完成记录' },
]

const clearScope = ref(30)
const clearDialogVisible = ref(false)
const clearPreviewLoading = ref(false)
const clearPreview = ref(null)
const clearingRecords = ref(false)
const retryingAll = ref(false)

/** 已完成记录数——为 0 时没有可清除的东西，入口直接禁用 */
const completedCount = computed(() => counts.value.completed ?? 0)

/** 各范围的「将删除 N 条」：count 与后端 delete 的筛选口径一致 */
const clearOptions = computed(() =>
  CLEAR_SCOPE_OPTIONS.map((opt) => ({
    ...opt,
    count: opt.value === 0
      ? (clearPreview.value?.all ?? 0)
      : (clearPreview.value?.before_days?.[String(opt.value)] ?? 0),
  }))
)

const selectedClearCount = computed(
  () => clearOptions.value.find((o) => o.value === clearScope.value)?.count ?? 0
)

/** 由 clearScope 生成请求体：0 → all，其余 → before_days */
const clearPayload = () =>
  clearScope.value === 0
    ? { mode: 'all' }
    : { mode: 'before_days', days: Number(clearScope.value) }

const openClearDialog = async () => {
  if (completedCount.value === 0) return
  clearScope.value = 30
  clearDialogVisible.value = true
  clearPreviewLoading.value = true
  try {
    const resp = await api.get('/download/tasks/clear-preview')
    clearPreview.value = resp.data?.data || resp.data || null
    // 默认 30 天；若该范围没有可删除记录，回退到第一个非空范围，
    // 避免对话框一打开主按钮就是禁用态。
    const preferred = clearOptions.value.find((o) => o.value === 30)
    clearScope.value = preferred && preferred.count > 0
      ? 30
      : (clearOptions.value.find((o) => o.count > 0)?.value ?? 0)
  } catch (e) {
    clearDialogVisible.value = false
    ElMessage.error(
      '加载清理预览失败：' + (e?.response?.data?.message || e.message)
    )
  } finally {
    clearPreviewLoading.value = false
  }
}

const onClearConfirm = async () => {
  if (clearingRecords.value || selectedClearCount.value === 0) return
  clearingRecords.value = true
  try {
    const res = await recentDownloadsApi.clear(clearPayload())
    const deleted = res?.data?.deleted
    ElMessage.success(
      `已清除 ${typeof deleted === 'number' ? deleted : selectedClearCount.value} 条记录`
    )
    clearDialogVisible.value = false
    // 清除后重载本页任务 + 各 tab 计数（「最近下载」角标由 composable 自行刷新）
    await refreshAll()
    fetchRecentDownloadsCount().catch(() => {})
  } catch (e) {
    ElMessage.error('清除失败：' + (e?.message || '未知错误'))
  } finally {
    clearingRecords.value = false
  }
}

/** 错误页签：服务端一次重试全部 failed 任务 */
const onRetryAllFailed = async () => {
  const failedCount = counts.value.failed ?? 0
  if (retryingAll.value || failedCount === 0) return

  try {
    await ElMessageBox.confirm(
      `将重试全部 ${failedCount} 个失败任务，是否继续？`,
      '全部重试',
      { type: 'warning' }
    )
  } catch (e) {
    if (e === 'cancel') return
    throw e
  }

  retryingAll.value = true
  try {
    const resp = await api.post('/download/tasks/retry-failed')
    const data = resp.data?.data || resp.data || {}
    const started = data.started ?? 0
    const skipped = data.skipped ?? 0
    ElMessage.success(
      skipped > 0
        ? `已重试 ${started} 个任务，跳过 ${skipped} 个`
        : `已重试 ${started} 个任务`
    )
    wakeDownloadState()
    await refreshAll()
  } catch (e) {
    ElMessage.error(
      '全部重试失败：' + (e?.response?.data?.message || e.message)
    )
  } finally {
    retryingAll.value = false
  }
}

const POLL_INTERVAL = 2000
let pollTimer = null
let polling = false
// 卸载闸门：防止 await 跨过 onUnmounted 后再 setInterval
const isUnmounted = ref(false)
const poll = async () => {
  if (polling) return
  polling = true
  try {
    if (activeTab.value === 'active' || activeTab.value === 'all') {
      const before = Object.fromEntries(
        tasks.value.map(t => [t.task_id, t.status])
      )
      await loadTasks(false)
      const after = Object.fromEntries(
        tasks.value.map(t => [t.task_id, t.status])
      )
      // 状态有跨活跃/终态转换时 loadCounts 会在 finally 里重新评估轮询开关
      if (statusChanged(before, after)) await loadCounts()
    }
  } finally {
    polling = false
  }
}

const ACTIVE_SET = new Set(['pending', 'downloading', 'paused'])
const statusChanged = (before, after) => {
  const allIds = new Set([...Object.keys(before), ...Object.keys(after)])
  for (const id of allIds) {
    const oldS = before[id]
    const newS = after[id]
    if (!oldS || !newS) return true  // 任务新增或消失
    if (ACTIVE_SET.has(oldS) !== ACTIVE_SET.has(newS)) return true  // 跨活跃/终态转换
  }
  return false
}

/**
 * 是否该轮询下载任务列表。
 *
 * 三个条件缺一不可：
 * 1. 在「下载中 / 全部」页签（其余页签是终态快照，无变化）；
 * 2. **确实有正在跑的任务**（counts.running = pending + downloading，不含 paused）——
 *    0 个时定时器完全停掉，0 请求。paused 任务进度不动，轮询没有意义。
 * 3. counts 已加载完成（null 视为 0），避免挂载瞬间先空转几轮再停。
 */
const shouldPoll = () =>
  (activeTab.value === 'active' || activeTab.value === 'all')
  && (counts.value.running ?? 0) > 0

/** 重排轮询开关：条件满足则保证定时器在跑，否则确保已停（幂等） */
const syncPolling = () => {
  // 卸载后 loadCounts() 的 finally 仍可能迟到（await 跨过了 onUnmounted），
  // 此时若再 setInterval 就是一个永远没人清的孤儿定时器——onUnmounted 的
  // stopPolling 早已跑完，不会再有第二次。这正是旧实现要在 onMounted 同步阶段
  // 先起轮询来规避的同一个坑，换成「loadCounts 裁决」后必须用这个闸门补上。
  if (isUnmounted.value) return
  if (shouldPoll()) {
    if (pollTimer === null) pollTimer = setInterval(poll, POLL_INTERVAL)
  } else if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
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

const onSortChange = ({ prop, order }) => {
  if (!prop || !order) {
    sortBy.value = 'image_id'
    sortOrder.value = 'desc'
  } else {
    sortBy.value = prop
    sortOrder.value = order === 'ascending' ? 'asc' : 'desc'
  }
  currentPage.value = 1
  loadTasks()
}

watch(activeTab, () => {
  // 立刻按当前 counts 重新评估；onTabChange 的 loadCounts 回来后会再校正一次
  syncPolling()
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
    // 把下载页的操作同步给图库侧的单例状态：
    //   - start/resume：paused 不算活跃态，useDownloadState 已因「空闲停轮询」
    //     不会自己醒来，必须 wake() 强制打开探测窗口才能看到 pending/downloading；
    //   - cancel/delete：任务从后端消失，finished 回看窗口里也不会再有它，
    //     STALE_MS 兜底回收要求在轮询中（现已可能停摆），所以显式 reset。
    const imageId = taskImageId(task)
    if (imageId != null) {
      if (action === 'start' || action === 'resume') wakeDownloadState()
      // pause / cancel / delete：任务不再往前推进，显式解除图库侧标识
      else resetDownloadState(imageId)
    }
    await Promise.all([loadTasks(), loadCounts()])
  } catch (e) {
    ElMessage.error(`${cfg.msg}失败：${e?.response?.data?.message || e.message}`)
  }
}

const toggleError = (taskId) => {
  errorExpanded.value[taskId] = !errorExpanded.value[taskId]
}

onMounted(() => {
  // 轮询开关交给 loadCounts() 在 finally 里评估（counts 是「有没有在跑」的唯一
  // 权威来源），这里不再无条件起定时器 —— 挂载时 0 个运行中任务就该是 0 请求。
  //
  // 旧实现为了防「await loadTasks 期间用户关掉 dialog → onUnmounted 先跑 →
  // 留下无人清理的 setInterval」，在 onMounted 同步阶段先起轮询。那个竞态现在
  // 由 syncPolling 的幂等性 + stopPolling 兜住：stopPolling 把 pollTimer 置 null，
  // 而挂载后唯一会起定时器的路径是 loadCounts 的 finally → syncPolling，
  // unmount 之后 loadCounts 的 finally 若迟到也会因 running 已无变化而不再起。
  loadTasks()
  loadCounts()
  document.addEventListener('visibilitychange', onVisibilityChange)
  window.addEventListener('focus', refreshOnReturn)
  window.addEventListener('online', refreshOnReturn)
})

onUnmounted(() => {
  isUnmounted.value = true
  stopPolling()
  document.removeEventListener('visibilitychange', onVisibilityChange)
  window.removeEventListener('focus', refreshOnReturn)
  window.removeEventListener('online', refreshOnReturn)
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
  /* 固定最小行高：动作按钮出现/消失时页签不上下跳 */
  min-height: 32px;
  margin-bottom: 15px;
  flex-wrap: nowrap;
  gap: 8px;
}

/* 工具栏右侧动作组：全部重试 / 清除记录 */
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  flex-wrap: nowrap;
}

/* flex gap 已负责间距，抵消 el-button 相邻默认 margin-left */
.toolbar-actions .toolbar-action + .toolbar-action {
  margin-left: 0;
}

/* ---- 清除记录对话框 ---- */
.clear-alert {
  margin-bottom: 12px;
}
.clear-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.clear-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.15s, background-color 0.15s;
}
.clear-option:hover {
  border-color: var(--el-color-primary-light-5);
}
.clear-option.active {
  border-color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
}
.clear-option-label {
  font-size: 13px;
  color: var(--el-text-color-primary);
}
.clear-option-count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}
.clear-option.active .clear-option-count {
  color: var(--el-color-danger);
}

.title {
  flex-shrink: 0;
  line-height: 1.2;
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

.card-times {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 8px;
}
.card-time {
  white-space: nowrap;
}
.time-label {
  color: var(--text-secondary);
  margin-right: 2px;
}

.card-error {
  margin: 8px 0;
  padding: 8px;
  background: #fef0f0;
  border-radius: 4px;
  font-size: 12px;
}
.dark-mode .card-error {
  background: #3d1f1f;
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
/* 删除是低频破坏性操作：不抢主操作的宽度，右对齐收小 */
.card-actions .card-delete {
  flex: 0 0 auto;
  min-width: 0;
  margin-left: auto;
}

.pagination {
  margin-top: 15px;
  justify-content: center;
}

@media screen and (max-width: 768px) {
  /* 保持单行：标题 + 动作组不换行，只收紧间距 */
  .toolbar {
    gap: 6px;
  }
  .toolbar-actions {
    gap: 6px;
    margin-left: auto;
  }
  .toolbar-action {
    padding: 5px 8px;
  }
  .task-tabs :deep(.el-tabs__header) {
    margin-bottom: 10px;
  }
  .task-card {
    padding: 10px;
  }
}
</style>
