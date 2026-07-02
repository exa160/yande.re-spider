# 下载任务页：时间列展示与列头排序 — 设计

**日期**：2026-07-01
**状态**：待批准
**作者**：Sisyphus
**范围**：后端（API / DAO）+ 前端（Download.vue）+ 单元测试
**前置**：[2026-06-21-download-page-tabs-design.md](2026-06-21-download-page-tabs-design.md)（Tabs 分组 + 状态排序）

---

## 1. 背景

### 1.1 现状

`frontend/src/views/Download.vue` 当前实现的下载任务表格：
- 桌面端 el-table 列：图片ID / 文件名 / 状态 / 进度 / 大小 / （错误信息，failed tab 可见） / 速度 / 操作
- 移动端卡片：仅展示文件名 / 状态 / 进度 / 大小 / 速度
- 排序硬编码在 `TAB_SORT_MAP` 中（5 个 tab 各自固定一种排序），用户无法点击列头切换

后端 DAO `query_tasks` 当前白名单（`dao/download_task_dao.py:155`）：
```python
allowed_sort = {"created_at", "updated_at", "completed_at", "progress"}
```

`image_id` 不在白名单中，前端也无法通过 sort_by=image_id 请求排序。

### 1.2 触发问题

1. 用户无法直观看到任务何时创建、何时完成（数据存在但未展示）
2. 排序行为固定，用户无法按"最新图片优先"或"文件大小"等需求切换

### 1.3 目标

- **核心 1**：在表格「速度」与「操作」之间新增「完成时间」与「添加时间」两列，移动端卡片同步展示
- **核心 2**：所有 Tab 默认按 `image_id` 降序（最新图片/最新任务在前）
- **核心 3**：支持点击列头切换排序（asc / desc 双态切换），所有可排序列均参与

### 1.4 非目标

- 不做多级排序（sort by A, then by B）
- 不持久化用户排序选择到 localStorage
- 不改数据库 schema（`completed_at` / `created_at` / `image_id` 字段已存在）
- 不改下载器实现（`MultiDown` / `DownloadQueue`）
- 不改其他页面（Gallery / Config / Favorites）

---

## 2. 设计决策

| 维度 | 决策 | 备选 | 理由 |
|------|------|------|------|
| "id" 字段含义 | `image_id` | `task_id`（UUID 无业务含义） / `created_at` | image_id 在 yande 站是递增的，desc 意味着"最新图片在前"，符合"新任务优先"的直觉；UUID 字符串排序无意义；created_at 实际效果接近但语义不如 image_id 直接 |
| 时间显示格式 | `YYYY-MM-DD HH:mm:ss` | 短格式 / 相对时间 | 绝对时间戳信息最完整，便于审计与问题追溯；项目未引入 dayjs，相对时间需新增依赖 |
| 移动端展示 | 卡片同步显示 | 仅桌面端 | 保持两端信息一致，避免"手机上能看时间但 PC 看不到"的不一致体验 |
| 列头排序视觉 | Element Plus `sortable` 默认箭头 | 自定义双箭头 | Element Plus 原生支持，零额外样式成本；用户已熟悉 Element Plus 组件库风格 |
| 后端 sort_by 默认值 | 改为 `"image_id"` | 保持 `"created_at"` | 前端不传参时落到后端默认值；保持全局一致需要后端默认也对齐 |

---

## 3. 数据契约

### 3.1 后端 API 变化

`GET /api/v1/download/tasks` 现有参数：

| 参数 | 当前默认 | 新默认 | 候选值扩充 |
|---|---|---|---|
| `sort_by` | `"created_at"` | **`"image_id"`** | + `"image_id"` |
| `order` | `"desc"` | `"desc"`（不变） | 不变 |
| `status` | `None` | `None`（不变） | 不变 |
| `page`, `page_size` | `1`, `20` | 不变 | 不变 |

响应字段无变化（`completed_at` / `created_at` 已在 `_to_dict` 中序列化）。

### 3.2 前端字段映射

| 表格列 | prop | 格式化函数 | 是否 sortable |
|--------|------|------------|---------------|
| 图片ID | `image_id` | 直接展示 | ✅ custom |
| 文件名 | (custom) | `getFileName(row)` | ❌ |
| 状态 | (custom) | `getStatusText(row.status)` | ❌ |
| 进度 | (custom) | `el-progress` | ❌ |
| 大小 | (custom) | `formatFileSize(row.downloaded_size)` + `formatFileSize(row.file_size)` | ❌ |
| 错误信息（failed tab） | `error_message` | 直接展示 | ❌ |
| 速度 | (custom) | `formatSpeed(row.speed)` | ❌ |
| **完成时间** ⭐ | `completed_at` | `formatDateTime(row.completed_at)` | ✅ custom |
| **添加时间** ⭐ | `created_at` | `formatDateTime(row.created_at)` | ✅ custom |
| 操作 | (custom) | 按钮组 | ❌ |

> ⚠️ "图片ID"列虽然已有 `prop="image_id"`，但需追加 `sortable="custom"` 让其参与点击排序。

---

## 4. 架构概览

```
┌──────────────────────────────────────────────────────────────────┐
│  Download.vue                                                    │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ <el-table @sort-change="onSortChange" :default-sort="...">│  │
│  │   ...                                                      │  │
│  │   <el-table-column prop="image_id"     sortable="custom"/>│  │
│  │   <el-table-column prop="completed_at" sortable="custom"/>│  │
│  │   <el-table-column prop="created_at"   sortable="custom"/>│  │
│  │   ...                                                      │  │
│  │ </el-table>                                                │  │
│  │                                                             │  │
│  │ onSortChange({ prop, order }) →                            │  │
│  │   sortBy.value = prop                                       │  │
│  │   sortOrder.value = order === 'ascending' ? 'asc' : 'desc'│  │
│  │   currentPage.value = 1                                     │  │
│  │   loadTasks()                                               │  │
│  └────────────────────────────────────────────────────────────┘  │
│       │ sort_by=image_id, order=desc (TAB_SORT_MAP 默认)         │
│       │ 或用户点击列头后的 sortBy/sortOrder                       │
│       ▼                                                          │
│  api.get('/download/tasks', { status, sort_by, order, page, ...})│
└──────────────────────────────────────────────────────────────────┘
                               ↓ HTTP
┌──────────────────────────────────────────────────────────────────┐
│  GET /api/v1/download/tasks                                      │
│    sort_by: Literal["image_id", "created_at", "updated_at",      │
│                      "completed_at", "progress"] = "image_id"     │
│    order:   Literal["asc", "desc"] = "desc"                      │
│                                                                  │
│  DownloadService.get_tasks → DownloadTaskDao.query_tasks         │
│    allowed_sort = {"image_id", "created_at", "updated_at",      │
│                    "completed_at", "progress"}                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 5. 实施细节

### 5.1 后端改动

#### 5.1.1 `backend/src/dao/download_task_dao.py:155`

```diff
- allowed_sort = {"created_at", "updated_at", "completed_at", "progress"}
+ allowed_sort = {"image_id", "created_at", "updated_at", "completed_at", "progress"}
```

#### 5.1.2 `backend/src/api/v1/download.py:63`

```diff
- sort_by: Literal["created_at", "updated_at", "completed_at", "progress"] = Query(
-     "created_at", description="排序字段"
- ),
+ sort_by: Literal["image_id", "created_at", "updated_at", "completed_at", "progress"] = Query(
+     "image_id", description="排序字段"
+ ),
```

> **不改动** `services/download.py` 的 `get_tasks` 方法签名（`sort_by: str = "created_at"`），因为 Service 层不应当承担默认值约束，默认值是 API 层的契约。Service 层继续接受任意字符串（DAO 白名单会拦截非法值），与原代码保持解耦。

#### 5.1.3 单元测试

`unit_test/dao/test_download_task_dao_tabs.py` 新增用例：

```python
def test_query_tasks_sort_by_image_id_desc(...):
    """image_id desc 排序：数字越大越靠前"""
    tasks, _ = dao.query_tasks(
        sort_by="image_id", order="desc", page=1, page_size=20
    )
    image_ids = [t["image_id"] for t in tasks]
    assert image_ids == sorted(image_ids, reverse=True)


def test_query_tasks_sort_by_image_id_asc(...):
    """image_id asc 排序：数字越小越靠前"""
    tasks, _ = dao.query_tasks(
        sort_by="image_id", order="asc", page=1, page_size=20
    )
    image_ids = [t["image_id"] for t in tasks]
    assert image_ids == sorted(image_ids)


def test_query_tasks_invalid_sort_by_raises():
    """非法 sort_by 抛 ValueError"""
    with pytest.raises(ValueError, match="Invalid sort_by"):
        dao.query_tasks(sort_by="malicious_field", order="desc")
```

`unit_test/api/v1/test_download_routes.py` 新增：

```python
def test_download_tasks_sort_by_image_id_desc():
    """API 层接受 image_id 排序"""
    response = client.get("/api/v1/download/tasks?sort_by=image_id&order=desc")
    assert response.status_code == 200
    body = response.json()
    image_ids = [t["image_id"] for t in body["data"]]
    assert image_ids == sorted(image_ids, reverse=True)


def test_download_tasks_invalid_sort_by_422():
    """API 层非法 sort_by 返回 422"""
    response = client.get("/api/v1/download/tasks?sort_by=hacker_field")
    assert response.status_code == 422
```

### 5.2 前端改动

#### 5.2.1 `frontend/src/views/Download.vue` — 表格列扩展

在「速度」列（`width="90"`）和「操作」列（`width="240"`）之间插入：

```vue
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
```

`el-table` 根标签新增 `@sort-change="onSortChange"` 与 `:default-sort`：

```vue
<el-table
  ...
  :default-sort="{ prop: currentSortBy, order: currentSortOrder === 'asc' ? 'ascending' : 'descending' }"
  @sort-change="onSortChange"
>
```

#### 5.2.2 移动端卡片扩展

在 `.card-info` 与 `.card-error` 之间插入：

```vue
<div class="card-times">
  <span class="card-time">
    <span class="time-label">添加：</span>{{ formatDateTime(task.created_at) }}
  </span>
  <span class="card-time">
    <span class="time-label">完成：</span>{{ formatDateTime(task.completed_at) }}
  </span>
</div>
```

#### 5.2.3 `TAB_SORT_MAP` 改造

```diff
const TAB_SORT_MAP = {
-   all:       { sort_by: 'created_at',   order: 'desc' },
-   active:    { sort_by: 'created_at',   order: 'asc'  },
-   completed: { sort_by: 'completed_at', order: 'desc' },
-   failed:    { sort_by: 'completed_at', order: 'desc' },
-   cancelled: { sort_by: 'completed_at', order: 'desc' },
+   all:       { sort_by: 'image_id', order: 'desc' },
+   active:    { sort_by: 'image_id', order: 'desc' },
+   completed: { sort_by: 'image_id', order: 'desc' },
+   failed:    { sort_by: 'image_id', order: 'desc' },
+   cancelled: { sort_by: 'image_id', order: 'desc' },
}
```

> **行为变化**：active tab 从 `created_at asc`（最早创建的在最前，便于"快完成的优先"）改为 `image_id desc`（最新图片在最前）。用户已确认接受此变化。

#### 5.2.4 新增响应式状态

```js
const sortBy = ref('image_id')   // 当前排序字段
const sortOrder = ref('desc')    // 当前排序方向
```

#### 5.2.5 `loadTasks` 改造

> **设计决策**：用户的 `sortBy` / `sortOrder` 在切换 tab 时**保持不重置**（延续用户意图）。只有用户主动清除排序（点击列头第三次回到无排序态）或刷新页面时，才回退到 `TAB_SORT_MAP` 默认。
>
> 同时 `TAB_SORT_MAP` 简化为：仅作为**初始默认值**（`onMounted` 首次加载时使用），之后完全由 `sortBy.value` / `sortOrder.value` 主导。

```diff
  const sortBy = ref('image_id')   // 当前排序字段
  const sortOrder = ref('desc')    // 当前排序方向

  const loadTasks = async (showLoading = true) => {
    if (showLoading) loading.value = true
    try {
      const tab = activeTab.value
      const statusList = TAB_STATUS_MAP[tab]
      const params = {
        page: currentPage.value,
        page_size: isMobile.value ? 10 : 20,
        sort_by: sortBy.value,
        order: sortOrder.value,
      }
      if (statusList) {
        params.status = [...statusList]
      }
      const response = await api.get('/download/tasks', { params })
      ...
```

`onTabChange` 行为不变（仍重置 `currentPage`），但**不重置** `sortBy` / `sortOrder`。

#### 5.2.6 `onSortChange` 处理函数

```js
const onSortChange = ({ prop, order }) => {
  // 用户清除排序（order === null）时重置为默认
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
```

#### 5.2.7 `formatDateTime` 工具函数

```js
const formatDateTime = (isoString) => {
  if (!isoString) return '-'
  // isoString 形如 "2026-07-01T14:32:15"（后端 isoformat() 无时区）
  const d = new Date(isoString)
  if (isNaN(d.getTime())) return '-'
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
         `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
```

#### 5.2.8 样式（追加）

```css
.card-times {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 8px;
}
.card-time { white-space: nowrap; }
.time-label { color: var(--text-secondary); margin-right: 2px; }
```

### 5.3 验证清单

| 项 | 命令 / 操作 | 期望 |
|----|-------------|------|
| 后端 DAO 白名单 | `pytest unit_test/dao/test_download_task_dao_tabs.py -v` | 3 个新用例通过 |
| 后端 API 路由 | `pytest unit_test/api/v1/test_download_routes.py -v` | 2 个新用例通过 |
| 后端类型检查 | `lsp_diagnostics backend/src/api/v1/download.py` | 无错 |
| 前端类型检查 | `lsp_diagnostics frontend/src/views/Download.vue` | 无错 |
| 前端构建 | `cd frontend && npm run build` | 编译通过 |
| 手动验证 | 启动 dev server，访问 /download | 5 个 tab 默认按 image_id desc；点击列头切换 asc/desc；时间列展示正确 |

---

## 6. 风险与回退

| 风险 | 等级 | 缓解 |
|------|------|------|
| 改变后端默认 `sort_by` 影响其他调用方 | 中 | grep 确认无其他后端 / 前端模块使用该 API 不传参；现有 6 处调用方均为下载模块自身 |
| active tab 默认排序从 `created_at asc` 改为 `image_id desc` 改变用户预期 | 中 | 用户在调研中明确接受；最坏情况 1 次性切换适应期 |
| `completed_at` 为 None 时显示 `-` | 低 | `formatDateTime` 已有 null guard |
| ISO 时间字符串浏览器解析兼容性 | 低 | `new Date(iso)` 支持 ISO 8601 字符串（含 'T' 分隔符），现代浏览器均通过 |
| 列头点击排序与现有 `loadTasks` 轮询交互 | 低 | 轮询仅在 active tab 触发，每次重新走 sortBy/sortOrder 当前值 |

### 回退方案

如发现严重体验问题：
1. 前端：恢复原 `TAB_SORT_MAP`（5 行 diff）
2. 后端：将 `image_id` 从白名单移除（1 行 diff），并回退默认值为 `created_at`
3. 数据库：无需 schema 变更

---

## 7. 后续优化（不在本期范围）

- 列头点击后展示高亮（hover/active 状态）
- 排序状态持久化到 localStorage
- 多级排序（先 image_id 再 created_at）
- 列宽可拖拽（Element Plus `border` + drag）
- 时间列提供快捷筛选（今日 / 本周 / 本月）
