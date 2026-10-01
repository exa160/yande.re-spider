<template>
  <div class="download-page">
    <div class="toolbar">
      <span class="title">下载任务</span>
      <div class="toolbar-actions">
        <el-button type="primary" size="small" @click="refreshAll">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>

        <!-- 清除下载完成记录：默认收成一个小图标按钮，点开才展开清除选项。
             为什么放刷新旁边而不是 tabs 右侧：element-plus 2.13 的 el-tabs 只渲染
             default / add-icon 两个 slot（tabs.d.ts 的 slots 类型为 {}），没有
             extra slot，要塞进 el-tabs__nav-scroll 只能靠 :deep() 绝对定位硬撑，
             属于长期维护的脆弱 hack。放在工具栏里语义也更直白——它是页面级操作。
             清理的只有 status=completed 的记录，所以只在「全部 / 已完成」出现。 -->
        <el-popover
          v-if="CLEAR_VISIBLE_TABS.includes(activeTab)"
          v-model:visible="clearPopoverVisible"
          placement="bottom-end"
          :width="270"
          trigger="click"
          @hide="resetClearArm"
        >
          <template #reference>
            <el-button
              type="danger"
              plain
              size="small"
              class="clear-trigger"
              :disabled="completedCount === 0"
              title="清除下载完成记录"
            >
              <el-icon><Delete /></el-icon>
            </el-button>
          </template>

          <div class="clear-pop">
            <div class="clear-pop-title">清除下载完成记录</div>
            <div class="clear-pop-hint">
              只删除下载任务记录，<b>不会删除本地图片文件</b>。清除后「最近下载」列表会同步变少。
            </div>
            <!-- teleported=false 是必须的（不是性能优化）：
                 el-select 下拉默认 teleported 到 body，点击下拉里的选项时，
                 事件目标落在 popper 之外 → element-plus tooltip content 的
                 onClickOutside(popperContentRef) 判定为「点击外部」→ trigger="click"
                 的 popover 直接关闭，表现为「选完时间弹窗就没了」。
                 关掉 teleport 后下拉内联渲染在 popper 子树内，判定为内部点击，
                 弹窗保持打开。 -->
            <el-select
              v-model="clearScope"
              size="small"
              class="clear-scope"
              :teleported="false"
              @change="resetClearArm"
            >
              <el-option
                v-for="opt in CLEAR_SCOPE_OPTIONS"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
            <el-button
              type="danger"
              size="small"
              class="clear-confirm"
              :loading="clearingRecords"
              :disabled="completedCount === 0"
              @click="onClearClick"
            >
              {{ clearingRecords ? '清除中…' : (clearArmed ? '再次点击确认清除' : '清除') }}
            </el-button>
            <div v-if="clearArmed && !clearingRecords" class="clear-armed-tip">
              再次点击即执行，5 秒后自动取消
            </div>
          </div>
        </el-popover>
      </div>
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
import { Refresh, Warning, Delete } from '@element-plus/icons-vue'
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
    // 网络恢复后由「刷新」按钮或下一次成功请求纠正。
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
// UI：收起成一个图标按钮 → 点开小弹窗（el-popover）→ 选范围 →
// 「清除」进入待确认态 → 5 秒内再点一次才真正执行。
// 两步点击都在弹窗内完成，不再叠加 ElMessageBox 模态框。
// ============================================================================
/** 仅在能看见「已完成」记录的两个页签出现清除入口 */
const CLEAR_VISIBLE_TABS = ['all', 'completed']
/** 清除范围：0 = 全部已完成（其余为「N 天前」） */
const CLEAR_SCOPE_OPTIONS = [
  { value: 7,  label: '7 天前的记录' },
  { value: 30, label: '30 天前的记录' },
  { value: 90, label: '90 天前的记录' },
  { value: 0,  label: '全部已完成记录' },
]
/** 清除按钮进入「待确认」态后自动回弹的时长（ms） */
const CLEAR_ARM_TIMEOUT = 5000

const clearScope = ref(30)
const clearPopoverVisible = ref(false)
const clearArmed = ref(false)
const clearingRecords = ref(false)
let clearArmTimer = null

/** 已完成记录数——为 0 时没有可清除的东西，入口直接禁用 */
const completedCount = computed(() => counts.value.completed ?? 0)

/** 取消「待确认」态（切换清除范围、关闭弹窗、超时回弹都走这里） */
const resetClearArm = () => {
  if (clearArmTimer !== null) {
    clearTimeout(clearArmTimer)
    clearArmTimer = null
  }
  clearArmed.value = false
}

/** 由 clearScope 生成请求体：0 → all，其余 → before_days */
const clearPayload = () =>
  clearScope.value === 0
    ? { mode: 'all' }
    : { mode: 'before_days', days: Number(clearScope.value) }

const onClearClick = async () => {
  if (clearingRecords.value || completedCount.value === 0) return

  // 第一次点击：只进入待确认态，不发任何请求
  if (!clearArmed.value) {
    clearArmed.value = true
    if (clearArmTimer !== null) clearTimeout(clearArmTimer)
    clearArmTimer = setTimeout(() => {
      clearArmTimer = null
      clearArmed.value = false
    }, CLEAR_ARM_TIMEOUT)
    return
  }

  // 第二次点击：真正执行
  resetClearArm()
  clearingRecords.value = true
  try {
    const res = await recentDownloadsApi.clear(clearPayload())
    const deleted = res?.data?.deleted
    ElMessage.success(`已清除 ${typeof deleted === 'number' ? deleted : 0} 条记录`)
    // 清除后重载本页任务 + 各 tab 计数（「最近下载」角标由 composable 自行刷新）
    await refreshAll()
    fetchRecentDownloadsCount().catch(() => {})
    clearPopoverVisible.value = false
  } catch (e) {
    ElMessage.error('清除失败：' + (e?.message || '未知错误'))
  } finally {
    clearingRecords.value = false
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
})

onUnmounted(() => {
  isUnmounted.value = true
  stopPolling()
  // 待确认态的 5s 回弹定时器必须一起清掉，否则 dialog 关掉后它还会把 clearArmed
  // 改回去（已卸载的组件上的响应式写入），且 setTimeout 会泄漏到下一次打开。
  resetClearArm()
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
  flex-wrap: wrap;
  gap: 8px;
}

/* 工具栏右侧动作组：刷新 / 清除记录（图标按钮） */
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* 清除入口：danger + plain —— 淡红底 + 红边 + 红字。
   不用 text（无边框无底色）是因为它夹在带边框的「刷新」旁边会很突兀；
   也不用实心 danger（视觉权重压过主操作），plain 刚好是「危险但次要」的档位。
   配色全部走 --el-* 变量，亮/暗色自动跟随。 */
.clear-trigger {
  padding: 5px 9px;
}
.clear-trigger:not(.is-disabled):hover {
  background: var(--el-color-danger-light-8);
  border-color: var(--el-color-danger);
}

/* ---- 清除记录弹窗 ---- */
.clear-pop-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 6px;
}
.clear-pop-hint {
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
  margin-bottom: 10px;
}
.clear-scope {
  width: 100%;
  margin-bottom: 10px;
}
.clear-confirm {
  width: 100%;
}
/* 「再点一次确认」的待命提示——配合按钮文案变化，给用户明确的时间窗 */
.clear-armed-tip {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-color-danger);
  text-align: center;
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
  /* 窄屏：动作组横向排（刷新 + 清除图标），不给图标按钮撑满整行 */
  .toolbar-actions {
    width: 100%;
    justify-content: flex-end;
  }
  .task-tabs :deep(.el-tabs__header) {
    margin-bottom: 10px;
  }
  .task-card {
    padding: 10px;
  }
}
</style>
