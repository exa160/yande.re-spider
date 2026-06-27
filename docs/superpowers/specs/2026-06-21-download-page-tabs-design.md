# 下载管理页 Tabs 分组改造 — 设计

**日期**：2026-06-21
**状态**：待批准
**作者**：Sisyphus
**范围**：后端（API/Service/DAO）+ 前端（Download.vue）+ 单元测试
**相关背景**：`next_dev` 分支 50 个本地未推送提交，含多站点重构；`Download.vue` 当前无状态分组（单列表）

---

## 1. 背景

### 1.1 现状

`Download.vue`（459 行）当前实现：

- 单一列表展示所有任务（无分组）
- 已有 `isMobile` 响应式分支：移动端 `.task-card` 卡片视图、PC 端 `el-table` 表格
- 已有 `status` 字段（6 个枚举：`pending` / `downloading` / `paused` / `completed` / `failed` / `cancelled`）
- 已有轮询逻辑：`hasActiveTasks` 时 2s 拉取，任务都进入终态后停止
- 后端 `GET /api/v1/download/tasks` 已支持 `status` 单值过滤和分页
- 后端 `DownloadTaskDao` 模型字段：`task_id`, `image_id`, `site`, `file_name`, `file_size`, `downloaded_size`, `progress`, `speed`, `status`, `error_message`, `started_at`, `completed_at`, `created_at`, `updated_at`

### 1.2 触发问题

用户反馈：任务数量增长后，**无法快速区分下载中 / 已完成 / 错误**三类任务，需要列表里肉眼过滤，体验差。移动端同样问题，且卡片在长列表中滚动难定位。

### 1.3 目标

- **核心**：在前端用 Tabs 把任务分为 5 类（全部 / 下载中 / 已完成 / 错误 / 已取消），每个 Tab 单独拉取和分页
- **次要**：Tab 头部显示各状态任务数（实时计数）
- **次要**：移动端友好（Tabs 横向滑动、卡片操作区不拥挤、错误信息可折叠）
- **次要**：仅"下载中" Tab 轮询，离开即停，减少无效请求

### 1.4 非目标

- 不改数据库 schema（`status` 字段已就位）
- 不改下载器实现（`MultiDown` / `DownloadQueue`）
- 不改其他页面（Gallery / Config / Favorites）
- 不做任务批量操作（多选 / 批量删除 / 批量重试）—— 本期不实现
- 不做进度推送（WebSocket / SSE）—— 维持现有轮询
- 不改"下载历史"独立页面（`GET /download/history`）—— 本次范围仅改主列表

---

## 2. 状态归类

| Tab | 包含的 `TaskStatus` | 排序默认 | 排序方向 | 备注 |
|---|---|---|---|---|
| 全部 | 所有 6 个 | `created_at` | `desc` | 总览 |
| 下载中 | `pending` + `downloading` + `paused` | `created_at` | `asc` | 最早创建的先看到（快完成的优先） |
| 已完成 | `completed` | `completed_at` | `desc` | 最近完成的优先 |
| 错误 | `failed` | `completed_at` | `desc` | 最近失败的优先，便于定位新错误 |
| 已取消 | `cancelled` | `completed_at` | `desc` | 最近取消的优先 |

**取消与失败的区分**：用户主动 `cancel` → `cancelled`；系统下载失败 → `failed`。语义不同，分开两个 Tab 避免误判。

---

## 3. 架构概览

```
┌──────────────────────────────────────────────────────────────────┐
│  Download.vue (Vue 3 Composition API)                            │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ <el-tabs v-model="activeTab" @tab-change="onTabChange">   │  │
│  │   <el-tab-pane name="all"        :label="tabLabel('all')"/>│  │
│  │   <el-tab-pane name="active"     :label="tabLabel('active')"/>│
│  │   <el-tab-pane name="completed"  :label="tabLabel('completed')"/>│
│  │   <el-tab-pane name="failed"     :label="tabLabel('failed')"/>│
│  │   <el-tab-pane name="cancelled"  :label="tabLabel('cancelled')"/>│
│  │ </el-tabs>                                                 │  │
│  │ <DownloadList :tasks="tasks" :tab="activeTab" ... />       │  │
│  │   ├─ PC: <el-table>                                        │  │
│  │   └─ Mobile: <div class="task-cards">                      │  │
│  └────────────────────────────────────────────────────────────┘  │
│       │                                                          │
│       │ activeTab='active' → startPolling (2s)                   │
│       │ activeTab!='active' → stopPolling                       │
│       ▼                                                          │
│  api.get('/download/tasks', { status: [...], sort_by, order,    │
│                                page, page_size })                │
│  api.get('/download/tasks/count')                                │
└──────────────────────────────────────────────────────────────────┘
                              ↓ HTTP
┌──────────────────────────────────────────────────────────────────┐
│  Backend (FastAPI)                                               │
│  GET /api/v1/download/tasks                                      │
│    QueryParams: status: List[TaskStatus] (multi-value)           │
│                sort_by: enum (created_at|updated_at|...          │
│                                  completed_at|progress)          │
│                order: enum (asc|desc)                            │
│                page, page_size                                   │
│    Response: TaskListResponse { total, page, page_size, data }   │
│                                                                  │
│  GET /api/v1/download/tasks/count (NEW)                          │
│    Response: { pending:n, downloading:n, paused:n,              │
│                completed:n, failed:n, cancelled:n }              │
│                                                                  │
│  DownloadService                                                 │
│    ├─ get_tasks(status_list, sort_by, order, page, page_size)   │
│    └─ get_status_counts()                                        │
│                                                                  │
│  DownloadTaskDao                                                 │
│    ├─ get_tasks(status_list, sort_by, order, page, page_size)   │
│    └─ count_by_status()  # GROUP BY status                      │
└──────────────────────────────────────────────────────────────────┘
```

---

## 4. 后端变更

### 4.1 `GET /api/v1/download/tasks` 参数扩展

#### 4.1.1 新增请求参数

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `status` | `Optional[List[TaskStatus]]` | `None` | 接受多值，如 `?status=pending&status=downloading`。不传返回所有 |
| `sort_by` | `Literal["created_at", "updated_at", "completed_at", "progress"]` | `"created_at"` | 排序字段；非法值走 Pydantic 422 |
| `order` | `Literal["asc", "desc"]` | `"desc"` | 排序方向；非法值走 Pydantic 422 |

#### 4.1.2 实现

```python
# backend/src/api/v1/download.py
from typing import List, Literal, Optional
from fastapi import Query

@router.get("/tasks", response_model=TaskListResponse, summary="获取任务列表")
async def get_download_tasks(
    status: Optional[List[TaskStatus]] = Query(None),
    sort_by: Literal["created_at", "updated_at", "completed_at", "progress"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> TaskListResponse:
    """获取下载任务列表（支持多状态过滤、排序、分页）"""
    try:
        tasks, total = DownloadService.get_tasks(
            status_list=status, sort_by=sort_by, order=order,
            page=page, page_size=page_size,
        )
        return TaskListResponse(total=total, page=page, page_size=page_size, data=tasks)
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)
```

#### 4.1.3 DAO 层签名变更

```python
# backend/src/dao/download_task_dao.py
from typing import List, Optional, Tuple

class DownloadTaskDao:
    @staticmethod
    def get_tasks(
        status_list: Optional[List[TaskStatus]] = None,
        sort_by: str = "created_at",
        order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[DownloadTask], int]:
        """查询任务（多状态过滤 + 排序 + 分页）
        
        Args:
            status_list: 状态列表；None/[] 表示所有
            sort_by: 排序字段（白名单校验）
            order: 'asc' | 'desc'
        
        Returns:
            (task_list, total)
        """
        # 1. 白名单校验 sort_by
        allowed = {"created_at", "updated_at", "completed_at", "progress"}
        if sort_by not in allowed:
            raise ValueError(f"Invalid sort_by: {sort_by}")
        if order not in ("asc", "desc"):
            raise ValueError(f"Invalid order: {order}")
        
        # 2. 构造 query
        with get_session() as session:
            q = session.query(DownloadTask)
            if status_list:
                q = q.filter(DownloadTask.status.in_([s.value for s in status_list]))
            
            total = q.count()
            
            sort_col = getattr(DownloadTask, sort_by)
            q = q.order_by(sort_col.asc() if order == "asc" else sort_col.desc())
            q = q.offset((page - 1) * page_size).limit(page_size)
            
            return q.all(), total
```

#### 4.1.4 NULL 排序处理

`completed_at` 在 pending/downloading 状态下为 `NULL`。SQL 排序时：
- MySQL：`NULL` 默认最小 → `desc` 时 NULL 在最后
- SQLite：`NULL` 默认最小 → `desc` 时 NULL 在最后
- 行为一致，无需 `NULLS LAST`（SQLite 不支持）

**结论**：使用数据库默认行为即可，前端不会出现"未完成任务"按 completed_at desc 排到顶部的问题（因为"全部" Tab 用 `created_at` desc，"下载中" Tab 用 `created_at` asc，"已完成/错误/已取消" Tab 的任务都有 completed_at）。

### 4.2 `GET /api/v1/download/tasks/count`（新增）

#### 4.2.1 Response Model

```python
# backend/src/models/response/download.py
class TaskStatusCount(BaseModel):
    """各状态任务计数"""
    pending: int = 0
    downloading: int = 0
    paused: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0

class TaskStatusCountResponse(BaseResponse[TaskStatusCount]):
    """任务状态计数响应"""
    ...
```

#### 4.2.2 路由

```python
@router.get("/tasks/count", response_model=TaskStatusCountResponse, summary="获取各状态任务计数")
async def get_task_status_counts() -> TaskStatusCountResponse:
    """获取各状态任务数量（单次 SQL GROUP BY）"""
    try:
        counts = DownloadService.get_status_counts()
        return TaskStatusCountResponse(message=ErrMsg.OK.msg, data=counts)
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)
```

#### 4.2.3 DAO 实现

```python
@staticmethod
def count_by_status() -> dict:
    """按 status 统计任务数（单 SQL）"""
    with get_session() as session:
        rows = session.query(
            DownloadTask.status, 
            func.count(DownloadTask.task_id)
        ).group_by(DownloadTask.status).all()
        
        # 初始化所有状态为 0（确保返回字段完整）
        result = {s.value: 0 for s in TaskStatus}
        for status_val, count in rows:
            result[status_val] = count
        return result
```

### 4.3 文件改动清单

| 文件 | 改动 | 行数估算 |
|---|---|---|
| `backend/src/api/v1/download.py` | 路由参数扩展 + 新增 `/tasks/count` 路由 | +30 / -5 |
| `backend/src/services/download.py` | `get_tasks` 支持多 status/排序；新增 `get_status_counts` | +20 / -10 |
| `backend/src/dao/download_task_dao.py` | `get_tasks` 重构（参数化）；新增 `count_by_status` | +40 / -10 |
| `backend/src/models/response/download.py` | 新增 `TaskStatusCount` 和 `TaskStatusCountResponse` | +15 |
| `unit_test/api/v1/test_download.py` | 新增 / 更新测试 | +120 |

---

## 5. 前端变更（`frontend/src/views/Download.vue`）

### 5.1 模板结构

```vue
<template>
  <div class="download-page">
    <!-- 工具栏 -->
    <div class="toolbar">
      <span class="title">下载任务</span>
      <el-button type="primary" size="small" @click="refreshAll">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </div>

    <!-- 5 Tabs -->
    <el-tabs v-model="activeTab" class="task-tabs" @tab-change="onTabChange">
      <el-tab-pane
        v-for="tab in tabs"
        :key="tab.key"
        :name="tab.key"
      >
        <template #label>
          <span>{{ tab.label }}</span>
          <el-badge
            v-if="counts[tab.key] !== null && counts[tab.key] > 0"
            :value="counts[tab.key]"
            :type="tab.badgeType"
            class="tab-badge"
          />
        </template>

        <!-- 移动端卡片（内联卡片结构，详见 5.3.1） -->
        <div v-if="isMobile" v-loading="loading" class="task-cards">
          <div v-for="task in tasks" :key="task.task_id" class="task-card">
            <!-- 完整卡片结构在 5.3.1 给出，此处简略示意 -->
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
            <!-- 错误信息（仅 failed Tab） -->
            <div v-if="activeTab === 'failed' && task.error_message" class="card-error">
              <el-button text size="small" @click="toggleError(task.task_id)">
                <el-icon><Warning /></el-icon>
                {{ errorExpanded[task.task_id] ? '收起错误' : '查看错误' }}
              </el-button>
              <div v-show="errorExpanded[task.task_id]" class="error-detail">
                {{ task.error_message }}
              </div>
            </div>
            <!-- 操作按钮 -->
            <div class="card-actions">
              <el-button v-if="task.status === 'failed'" type="primary" size="small" @click="onCardAction({action:'start', task})">重试</el-button>
              <el-button v-if="task.status === 'downloading'" type="warning" size="small" @click="onCardAction({action:'pause', task})">暂停</el-button>
              <el-button v-if="task.status === 'paused'" type="success" size="small" @click="onCardAction({action:'resume', task})">恢复</el-button>
              <el-button v-if="['pending', 'downloading', 'paused'].includes(task.status)" size="small" @click="onCardAction({action:'cancel', task})">取消</el-button>
              <el-button type="danger" size="small" @click="onCardAction({action:'delete', task})">删除</el-button>
            </div>
          </div>
          <el-empty v-if="tasks.length === 0 && !loading" :description="emptyText" />
        </div>

        <!-- PC 表格 -->
        <el-table
          v-else
          v-loading="loading"
          :data="tasks"
          style="width: 100%"
          size="small"
        >
          <!-- 列定义（见 5.4） -->
        </el-table>

        <!-- 分页 -->
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
```

### 5.2 Script 逻辑

#### 5.2.1 状态

```js
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

const activeTab = ref('active')  // 默认"下载中"
const tasks = ref([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(20)  // 移动端会在 loadTasks 中改为 10
const total = ref(0)
const isMobile = ref(false)
const errorExpanded = ref({})

const counts = ref({
  all: null, active: null, completed: null, failed: null, cancelled: null
})
```

#### 5.2.2 计数加载

```js
const loadCounts = async () => {
  try {
    const resp = await api.get('/download/tasks/count')
    const data = resp.data
    counts.value = {
      all:       (data.pending||0) + (data.downloading||0) + (data.paused||0) 
                 + (data.completed||0) + (data.failed||0) + (data.cancelled||0),
      active:    (data.pending||0) + (data.downloading||0) + (data.paused||0),
      completed: data.completed || 0,
      failed:    data.failed || 0,
      cancelled: data.cancelled || 0,
    }
  } catch (e) {
    // 失败不阻塞任务列表
    console.warn('load counts failed', e)
  }
}
```

#### 5.2.3 任务加载

```js
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
      statusList.forEach(s => {
        if (!params.status) params.status = []
        params.status.push(s)
      })
    }
    const response = await api.get('/download/tasks', { params })
    tasks.value = response.data?.data || []
    total.value = response.data?.total || 0
  } catch (error) {
    ElMessage.error('加载任务列表失败')
  } finally {
    if (showLoading) loading.value = false
  }
}
```

#### 5.2.4 轮询策略

```js
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

const onTabChange = (newTab) => {
  currentPage.value = 1
  errorExpanded.value = {}
  loadTasks()
  loadCounts()
  if (newTab === 'active') {
    startPolling()
  } else {
    stopPolling()
  }
}

watch(activeTab, (v) => {
  // 兜底：onTabChange 已处理，但 watch 用于外部状态变化
  if (v !== 'active') stopPolling()
  else startPolling()
})
```

#### 5.2.5 操作处理

```js
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
    ElMessage.error(`${cfg.msg}失败`)
  }
}

const toggleError = (taskId) => {
  errorExpanded.value[taskId] = !errorExpanded.value[taskId]
}

const refreshAll = async () => {
  await Promise.all([loadTasks(), loadCounts()])
}

const emptyText = computed(() => {
  const map = {
    all: '暂无下载任务',
    active: '当前没有进行中的任务',
    completed: '还没有完成的任务',
    failed: '没有失败的任务',
    cancelled: '没有取消的任务',
  }
  return map[activeTab.value] || '暂无下载任务'
})
```

#### 5.2.6 移动端检测

```js
const checkMobile = () => {
  isMobile.value = window.innerWidth <= 768
}

onBeforeMount(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

onMounted(async () => {
  await Promise.all([loadTasks(), loadCounts()])
  if (activeTab.value === 'active') startPolling()
})

onUnmounted(() => {
  stopPolling()
  window.removeEventListener('resize', checkMobile)
})
```

### 5.3 移动端卡片设计

#### 5.3.1 卡片结构（内联在 Download.vue 中，与 5.1 模板一致）

```vue
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

  <!-- 错误信息（默认折叠，仅 failed Tab 显示） -->
  <div v-if="activeTab === 'failed' && task.error_message" class="card-error">
    <el-button text size="small" @click="toggleError(task.task_id)">
      <el-icon><Warning /></el-icon>
      {{ errorExpanded[task.task_id] ? '收起错误' : '查看错误' }}
    </el-button>
    <div v-show="errorExpanded[task.task_id]" class="error-detail">
      {{ task.error_message }}
    </div>
  </div>

  <!-- 操作按钮（按状态显示） -->
  <div class="card-actions">
    <el-button v-if="task.status === 'failed'" type="primary" size="small" @click="onCardAction({action:'start', task})">重试</el-button>
    <el-button v-if="task.status === 'downloading'" type="warning" size="small" @click="onCardAction({action:'pause', task})">暂停</el-button>
    <el-button v-if="task.status === 'paused'" type="success" size="small" @click="onCardAction({action:'resume', task})">恢复</el-button>
    <el-button v-if="['pending', 'downloading', 'paused'].includes(task.status)" size="small" @click="onCardAction({action:'cancel', task})">取消</el-button>
    <el-button type="danger" size="small" @click="onCardAction({action:'delete', task})">删除</el-button>
  </div>
</div>
```

#### 5.3.2 移动端响应式 CSS

```css
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

.tab-badge {
  margin-left: 4px;
}
.tab-badge :deep(.el-badge__content) {
  transform: translateY(-50%) translateX(100%);
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

.card-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
}
.card-actions .el-button {
  flex: 1;
  min-width: 60px;
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

.pagination {
  margin-top: 15px;
  justify-content: center;
}

@media screen and (max-width: 768px) {
  .task-tabs :deep(.el-tabs__header) {
    margin-bottom: 10px;
  }
  .task-card {
    padding: 10px;
  }
}
```

### 5.4 PC 端表格（保留 + 微调）

```vue
<el-table v-else v-loading="loading" :data="tasks" style="width: 100%" size="small">
  <el-table-column prop="task_id" label="任务ID" width="100" show-overflow-tooltip />
  <el-table-column prop="image_id" label="图片ID" width="90" />
  <el-table-column label="文件名" show-overflow-tooltip>
    <template #default="{ row }">
      {{ getFileName(row) }}
    </template>
  </el-table-column>
  <el-table-column prop="status" label="状态" width="90">
    <template #default="{ row }">
      <el-tag :type="getStatusType(row.status)" size="small">
        {{ getStatusText(row.status) }}
      </el-tag>
    </template>
  </el-table-column>
  <el-table-column prop="progress" label="进度" width="140">
    <template #default="{ row }">
      <el-progress
        :percentage="Math.round(row.progress * 100)"
        :status="getProgressStatus(row.status)"
        :stroke-width="8"
      />
    </template>
  </el-table-column>
  <el-table-column label="大小" width="160">
    <template #default="{ row }">
      {{ formatFileSize(row.downloaded_size) }} / {{ row.file_size ? formatFileSize(row.file_size) : '-' }}
    </template>
  </el-table-column>
  <el-table-column v-if="activeTab === 'failed'" label="错误信息" show-overflow-tooltip>
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
  <el-table-column label="操作" width="200" fixed="right">
    <template #default="{ row }">
      <el-button v-if="row.status === 'failed'" type="primary" size="small" link @click="onCardAction({action:'start', task:row})">重试</el-button>
      <el-button v-if="row.status === 'downloading'" type="warning" size="small" link @click="onCardAction({action:'pause', task:row})">暂停</el-button>
      <el-button v-if="row.status === 'paused'" type="success" size="small" link @click="onCardAction({action:'resume', task:row})">恢复</el-button>
      <el-button v-if="['pending', 'downloading', 'paused'].includes(row.status)" size="small" link @click="onCardAction({action:'cancel', task:row})">取消</el-button>
      <el-button type="danger" size="small" link @click="onCardAction({action:'delete', task:row})">删除</el-button>
    </template>
  </el-table-column>
</el-table>
```

### 5.5 状态文本映射（中文显示）

```js
const getStatusText = (status) => ({
  pending:    '等待中',
  downloading:'下载中',
  paused:     '已暂停',
  completed:  '已完成',
  failed:     '失败',
  cancelled:  '已取消',
}[status] || status)
```

### 5.6 文件改动清单

| 文件 | 改动 | 行数估算 |
|---|---|---|
| `frontend/src/views/Download.vue` | 完整重写（保留 `formatFileSize` / `formatSpeed` 等工具函数） | 459 → 约 500 |
| `frontend/src/api/index.js` | 不变（已支持 `params` 数组） | 0 |

---

## 6. 错误处理

| 场景 | 行为 |
|---|---|
| `loadCounts` 失败 | 徽标显示 0 或不显示，不阻塞任务列表加载；console.warn |
| `loadTasks` 失败 | ElMessage 错误提示 + 列表清空 |
| 操作失败 | ElMessage 错误提示 + 不刷新列表 |
| 排序字段非法 | 后端 Pydantic 422 错误 + 前端 ElMessage 提示 |
| `count_by_status` 空结果 | 返回全 0（初始化所有状态） |
| 删除最后一个错误任务 | 当前页若变空，自动回到上一页（`if total>0 && currentPage>1 && tasks.length===0 → currentPage-- → reload`） |

---

## 7. 性能考虑

- 计数 API 单次 GROUP BY（不扫全表）
- 排序字段有索引（`status` 已有，`created_at` 已建索引，`completed_at` 需新增索引——见下文）
- 任务列表分页（PC 20/页，移动端 10/页）
- 仅"下载中" Tab 轮询（最多 1 个 Tab 拉取）

### 7.1 建议新增索引

```python
# 在 DownloadTask 模型 __table_args__ 中追加
Index("ix_task_status_completed", "status", "completed_at"),
Index("ix_task_status_created", "status", "created_at"),
```

`status` + `completed_at` 组合索引服务于"已完成/错误/已取消" Tab 查询；`status` + `created_at` 服务于"下载中" Tab。

---

## 8. 测试计划

### 8.1 后端（pytest）

| # | 测试 | 关注点 |
|---|---|---|
| T1 | `DownloadTaskDao.get_tasks(status_list=None)` | 返回所有 |
| T2 | `get_tasks(status_list=['pending','downloading'])` | 多值 IN 过滤 |
| T3 | `get_tasks(sort_by='completed_at', order='desc')` | 排序正确 |
| T4 | `get_tasks(sort_by='invalid')` | ValueError |
| T5 | `get_tasks(page=2, page_size=10)` | 分页正确 |
| T6 | `count_by_status()` | 返回完整 6 状态字段，0 默认 |
| T7 | API `GET /download/tasks?status=pending&status=paused&sort_by=created_at&order=asc` | 多 status 序列化正确 |
| T8 | API `GET /download/tasks?sort_by=invalid` | 422 |
| T9 | API `GET /download/tasks/count` | 返回结构正确 |
| T10 | API 现有调用无新参数 | 向后兼容（不传 status 返回所有） |

### 8.2 前端（手动 + 浏览器）

| # | 场景 | 期望 |
|---|---|---|
| F1 | 首次进入 | 默认"下载中" Tab，2s 轮询启动 |
| F2 | 切到"已完成" | 轮询停止，列表刷新 |
| F3 | 切回"下载中" | 轮询重启 |
| F4 | 点击"重试"失败任务 | 任务状态变 `downloading`，计数 -1 |
| F5 | 移动端 768px 视口 | 卡片视图，Tabs 横向滑动 |
| F6 | 错误 Tab 点击"查看错误" | 错误信息展开 |
| F7 | 删除最后一页唯一任务 | 自动跳到上一页 |
| F8 | 计数 API 失败 | Tab 徽标不显示，列表正常 |
| F9 | 操作后计数 | 计数徽标实时更新 |
| F10 | 全部 Tab 切换分页 | 总数正确 |

---

## 9. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 多值 `status` 在某些 HTTP 客户端下序列化异常 | 前端传 `?status=a&status=b` | 用 `qs.stringify({arrayFormat: 'repeat'})` 或手动拼（Element Plus 默认 axios 支持） |
| `completed_at` 为 NULL 的任务在排序中行为不可预期 | 错位 | 已在 4.1.4 节分析，默认行为可接受 |
| 旧前端代码 `task.status === 'downloading'` 仍依赖英文 status 字段 | 状态显示英文 | 新增 `getStatusText()` 映射，但保持 status 字段值不变（兼容性） |
| 轮询导致"已完成"任务短暂出现 | 任务刚切到 completed 时仍被轮询到 | 接受短暂出现（最多 2s），符合实际 |
| Element Plus el-tabs 移动端宽度不足 | Tab 文字被截断 | el-tabs 默认支持横向滑动；必要时 `:deep(.el-tabs__nav)` 调整 |

---

## 10. 后续优化（本次不实现）

- [ ] WebSocket 实时推送任务状态变化（替代轮询）
- [ ] 批量操作（多选 + 批量删除 / 重试）
- [ ] 任务搜索（按 file_name / image_id）
- [ ] 任务进度可视化（柱状图 / 时间线）
- [ ] 导出任务列表为 CSV
- [ ] 历史任务归档（`status=completed` 超过 N 天后移到 `download_history` 表）
- [ ] 任务详情抽屉（点击任务行展开）
- [ ] 与 `pr/download-storage` 分支的 `downloaded_size=file_size` 修复联动

---

## 11. 验收标准

- [ ] 后端 `GET /download/tasks` 支持 `status` 多值 + `sort_by` + `order`，现有调用无破坏
- [ ] 后端 `GET /download/tasks/count` 返回结构正确，单 SQL GROUP BY
- [ ] 后端单测 ≥ 10 个用例，覆盖多 status、排序、计数、错误码
- [ ] 前端 5 Tabs 切换正常，每个 Tab 单独分页
- [ ] Tab 头部显示各状态任务数（实时）
- [ ] 仅"下载中" Tab 轮询，离开即停
- [ ] 移动端 768px 视口下布局正常，操作按钮可点击
- [ ] 错误 Tab 错误信息默认折叠，可点击展开
- [ ] 状态文本显示中文（`等待中` / `下载中` / `已暂停` / `已完成` / `失败` / `已取消`）
- [ ] 所有操作（启动/暂停/恢复/重试/取消/删除）可用且操作后状态正确更新

---

**参考文档**：
- `docs/superpowers/specs/2026-06-13-booru-factory-design.md` - 多站点设计参考
- `docs/superpowers/specs/2026-06-16-multisite-favorites-tagcache-design.md` - 近期设计参考
- `AGENTS.md` - 项目代码规范
- `docs/dao.md` - DAO 编写规范
- `docs/api-route.md` - API 路由模板
- `docs/response.md` - BaseResponse 响应约定
