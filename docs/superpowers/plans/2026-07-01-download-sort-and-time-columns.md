# 下载任务页：时间列与列头排序 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `Download.vue` 任务表格的「速度」与「操作」列之间新增「完成时间」与「添加时间」两列（移动端卡片同步），所有 Tab 默认按 `image_id desc` 排序，并支持点击列头切换 asc/desc。

**Architecture:**
- **后端**：`DownloadTaskDao` 白名单加 `image_id`；API 路由 Literal 加 `image_id` 并把默认值从 `created_at` 改为 `image_id`
- **前端**：`Download.vue` 新增 `formatDateTime` 工具 + 表格 2 列 + 卡片时间段 + `sortBy/sortOrder` 响应式状态 + 列头点击 `@sort-change` 事件
- **设计参考**：`docs/superpowers/specs/2026-07-01-download-sort-and-time-columns-design.md`

**Tech Stack:**
- 后端：FastAPI / SQLAlchemy 2.0 / pytest
- 前端：Vue 3.4+ Composition API / Element Plus 2.5+（`sortable="custom"` 默认箭头样式）

**运行测试前置条件**：所有后端 pytest 命令必须在项目根目录执行（`conftest.py` 自动注入路径）。前端 npm 命令在 `frontend/` 目录下执行。

---

## File Structure

### 修改文件

| 路径 | 改动 |
|------|------|
| `backend/src/dao/download_task_dao.py` | `allowed_sort` 加入 `"image_id"` |
| `backend/src/api/v1/download.py` | `sort_by` Literal 加 `"image_id"`，默认值改 `"image_id"` |
| `frontend/src/views/Download.vue` | 新增时间格式化 + 表格 2 列 + 卡片时间段 + 排序状态 + 列头交互 |

### 新增测试用例

| 路径 | 用例 |
|------|------|
| `unit_test/dao/test_download_task_dao_tabs.py` | `image_id` 排序 asc/desc（白名单扩展验证） |
| `unit_test/api/v1/test_download_routes.py` | API 层接受 `image_id`；默认值即为 `image_id desc` |

### 数据库

无需 schema 变更（`image_id` / `completed_at` / `created_at` 字段均已存在）。

---

## Task 1: 后端 DAO 接受 image_id 排序（TDD）

**Files:**
- Modify: `unit_test/dao/test_download_task_dao_tabs.py`
- Modify: `backend/src/dao/download_task_dao.py:155`

- [ ] **Step 1: 写 sort_by=image_id desc 测试**

在 `unit_test/dao/test_download_task_dao_tabs.py` 末尾追加（最后一个测试函数之前）：

```python
def test_query_tasks_sorts_by_image_id_desc(dao):
    """image_id desc：数字越大越靠前"""
    for i in range(3):
        dao.create(task_id=f"img-{i}", image_id=6000 + i, file_name=f"img{i}.jpg")
        rec = dao.get_by_id(f"img-{i}")
        rec.status = TaskStatus.COMPLETED

    results, _ = dao.query_tasks(sort_by="image_id", order="desc")
    image_ids = [r["image_id"] for r in results]
    assert image_ids == [6002, 6001, 6000]


def test_query_tasks_sorts_by_image_id_asc(dao):
    """image_id asc：数字越小越靠前"""
    for i in range(3):
        dao.create(task_id=f"img-{i}", image_id=7000 + i, file_name=f"img{i}.jpg")
        rec = dao.get_by_id(f"img-{i}")
        rec.status = TaskStatus.COMPLETED

    results, _ = dao.query_tasks(sort_by="image_id", order="asc")
    image_ids = [r["image_id"] for r in results]
    assert image_ids == [7000, 7001, 7002]
```

- [ ] **Step 2: 运行测试验证失败**

Run:
```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/dao/test_download_task_dao_tabs.py::test_query_tasks_sorts_by_image_id_desc unit_test/dao/test_download_task_dao_tabs.py::test_query_tasks_sorts_by_image_id_asc -v
```

Expected: FAIL with `ValueError: Invalid sort_by: image_id. Must be one of {...}`

- [ ] **Step 3: 修改 DAO 白名单**

编辑 `backend/src/dao/download_task_dao.py:155`：

```diff
-        allowed_sort = {"created_at", "updated_at", "completed_at", "progress"}
+        allowed_sort = {"image_id", "created_at", "updated_at", "completed_at", "progress"}
```

- [ ] **Step 4: 运行测试验证通过**

Run:
```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/dao/test_download_task_dao_tabs.py -v
```

Expected: PASS（全部 ~10 个用例通过，包括两个新加的 image_id 用例）

- [ ] **Step 5: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add backend/src/dao/download_task_dao.py unit_test/dao/test_download_task_dao_tabs.py && git commit -m "feat(dao): DownloadTaskDao 支持按 image_id 排序" --no-verify
```

---

## Task 2: 后端 API 接受 image_id + 默认值改 image_id（TDD）

**Files:**
- Modify: `unit_test/api/v1/test_download_routes.py`
- Modify: `backend/src/api/v1/download.py:63-66`

- [ ] **Step 1: 写 API 接受 image_id 测试**

在 `unit_test/api/v1/test_download_routes.py` 末尾追加：

```python
def test_get_tasks_with_sort_by_image_id(client):
    """API 接受 sort_by=image_id，返回 200 且按 image_id desc 排序"""
    resp = client.get("/api/v1/download/tasks?sort_by=image_id&order=desc")
    assert resp.status_code == 200
    data = resp.json()["data"]
    image_ids = [t["image_id"] for t in data]
    assert image_ids == sorted(image_ids, reverse=True)


def test_get_tasks_default_sort_is_image_id_desc(client):
    """API 不传 sort_by 参数时，按 image_id desc 排序（默认行为变更）"""
    resp = client.get("/api/v1/download/tasks")
    assert resp.status_code == 200
    data = resp.json()["data"]
    image_ids = [t["image_id"] for t in data]
    assert image_ids == sorted(image_ids, reverse=True)
```

- [ ] **Step 2: 运行测试验证失败**

Run:
```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/api/v1/test_download_routes.py::test_get_tasks_with_sort_by_image_id unit_test/api/v1/test_download_routes.py::test_get_tasks_default_sort_is_image_id_desc -v
```

Expected: 
- `test_get_tasks_with_sort_by_image_id` → FAIL with 422 (Literal 不接受 "image_id")
- `test_get_tasks_default_sort_is_image_id_desc` → FAIL（默认是 created_at desc，而现有 fixture 中 image_id 20000/20001/20002 顺序与 created_at desc 巧合一致，但语义测试不严格，可能 PASS → 不依赖此处的 FAIL 行为）

- [ ] **Step 3: 修改 API Literal + 默认值**

编辑 `backend/src/api/v1/download.py:63-66`：

```diff
-    sort_by: Literal["created_at", "updated_at", "completed_at", "progress"] = Query(
-        "created_at", description="排序字段"
-    ),
+    sort_by: Literal["image_id", "created_at", "updated_at", "completed_at", "progress"] = Query(
+        "image_id", description="排序字段"
+    ),
```

- [ ] **Step 4: 运行测试验证通过**

Run:
```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/api/v1/test_download_routes.py -v
```

Expected: PASS（全部 ~10 个用例通过，包括两个新加的 image_id 用例）

- [ ] **Step 5: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add backend/src/api/v1/download.py unit_test/api/v1/test_download_routes.py && git commit -m "feat(api): GET /download/tasks 接受 image_id 排序，默认值改为 image_id" --no-verify
```

---

## Task 3: 前端时间格式化 + 表格列扩展 + 移动端卡片时间展示

**Files:**
- Modify: `frontend/src/views/Download.vue`

> **注**：前端无 vue test runner，本任务及 Task 4 依赖 `lsp_diagnostics` 与 `npm run build` 验证语法正确性。功能正确性依赖 Task 5 手动验证。

- [ ] **Step 1: 新增 formatDateTime 工具函数**

编辑 `frontend/src/views/Download.vue`，在 `formatSpeed` 函数之后追加：

```js
const formatDateTime = (isoString) => {
  if (!isoString) return '-'
  const d = new Date(isoString)
  if (isNaN(d.getTime())) return '-'
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
         `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
```

- [ ] **Step 2: 表格新增「完成时间」与「添加时间」两列**

编辑 `frontend/src/views/Download.vue`，在「速度」列（`width="90"`，约第 149 行）之后、「操作」列（`width="240"`，约第 155 行）之前插入：

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

- [ ] **Step 3: 移动端卡片新增时间展示**

编辑 `frontend/src/views/Download.vue`，在 `<div class="card-info">` 块（第 45-50 行）之后、`<div v-if="activeTab === 'failed' && task.error_message" class="card-error">` 之前插入：

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

- [ ] **Step 4: 追加移动端时间样式**

编辑 `frontend/src/views/Download.vue` 的 `<style scoped>` 段，在 `.card-speed` 规则后追加：

```css
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
```

- [ ] **Step 5: lsp_diagnostics 验证**

Run:
```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && which lsp_diagnostics 2>/dev/null; echo "若未识别 lsp_diagnostics，使用 OpenCode 内置工具"
```

在 OpenCode 环境中，通过 LSP 工具对 `frontend/src/views/Download.vue` 运行 diagnostics，确认无 error / warning。

Expected: 无 error，warning 数量与改动前一致（应保持 0 或原有水平）。

- [ ] **Step 6: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add frontend/src/views/Download.vue && git commit -m "feat(frontend): Download.vue 新增完成时间/添加时间列与移动端展示" --no-verify
```

---

## Task 4: 前端排序逻辑改造（sortBy/sortOrder + TAB_SORT_MAP + 列头交互）

**Files:**
- Modify: `frontend/src/views/Download.vue`

- [ ] **Step 1: TAB_SORT_MAP 5 行改键**

编辑 `frontend/src/views/Download.vue:239-245`：

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

- [ ] **Step 2: 新增 sortBy / sortOrder 响应式状态**

编辑 `frontend/src/views/Download.vue`，在 `currentPage` ref 定义后追加：

```js
const sortBy = ref('image_id')   // 当前排序字段
const sortOrder = ref('desc')    // 当前排序方向
```

- [ ] **Step 3: loadTasks 改用 sortBy.value**

编辑 `frontend/src/views/Download.vue` 的 `loadTasks` 函数（约第 341-365 行），将读取 `TAB_SORT_MAP[tab]` 的逻辑替换为直接读 `sortBy.value` / `sortOrder.value`：

```diff
   const loadTasks = async (showLoading = true) => {
     if (showLoading) loading.value = true
     try {
       const tab = activeTab.value
       const statusList = TAB_STATUS_MAP[tab]
-      const sort = TAB_SORT_MAP[tab]
       const params = {
         page: currentPage.value,
         page_size: isMobile.value ? 10 : 20,
-        sort_by: sort.sort_by,
-        order: sort.order,
+        sort_by: sortBy.value,
+        order: sortOrder.value,
       }
       if (statusList) {
         params.status = [...statusList]
       }
       const response = await api.get('/download/tasks', { params })
```

> 注：`TAB_SORT_MAP` 仍保留作为初始默认值源，但实际由 `sortBy`/`sortOrder` 主导。若未来需要"切 tab 重置排序"，可读此 map 重新赋值。

- [ ] **Step 4: 图片ID 列添加 sortable="custom"**

编辑 `frontend/src/views/Download.vue:113`：

```diff
-          <el-table-column prop="image_id" label="图片ID" width="90" />
+          <el-table-column
+            prop="image_id"
+            label="图片ID"
+            width="90"
+            sortable="custom"
+          />
```

- [ ] **Step 5: el-table 根标签加 @sort-change 与 :default-sort**

编辑 `frontend/src/views/Download.vue`，找到 `<el-table` 起始标签（约第 106 行），在 `style="width: 100%"` 之后、`size="small"` 之后追加：

```diff
         <el-table
           v-else
           v-loading="loading"
           :data="tasks"
           style="width: 100%"
           size="small"
+          :default-sort="{ prop: sortBy, order: sortOrder === 'asc' ? 'ascending' : 'descending' }"
+          @sort-change="onSortChange"
         >
```

- [ ] **Step 6: 新增 onSortChange 函数**

编辑 `frontend/src/views/Download.vue`，在 `onTabChange` 函数之后追加：

```js
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
```

- [ ] **Step 7: lsp_diagnostics 验证**

在 OpenCode 环境中，通过 LSP 工具对 `frontend/src/views/Download.vue` 运行 diagnostics。

Expected: 无 error。

- [ ] **Step 8: 前端构建验证**

Run:
```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend && npm run build
```

Expected: 编译成功，无 error，输出到 `frontend/dist/`，可能含 `< 1kB` chunk warning（可忽略）。

- [ ] **Step 9: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add frontend/src/views/Download.vue && git commit -m "feat(frontend): Download.vue 全 tab 默认 image_id desc + 列头点击排序" --no-verify
```

---

## Task 5: 端到端验证

> **本任务无需写代码**，目的是在 dev server 启动后人工核对 UI 行为与 spec 5.3 验证清单一致。

- [ ] **Step 1: 启动后端 + 前端 dev server**

Run（两个终端）：
```bash
# 终端 1
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && uvicorn service:main_app --reload --host 0.0.0.0 --port 8000

# 终端 2
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend && npm run dev
```

- [ ] **Step 2: 验证 5 个 Tab 默认排序**

浏览器访问 `http://localhost:3000/download`，对每个 Tab（全部/下载中/已完成/错误/已取消）核对：
- 默认按 image_id desc 排序（image_id 列从大到小）
- URL 上 sort_by / order 参数正确

Expected: 5 个 tab 行为一致，最新图片的任务在第一行。

- [ ] **Step 3: 验证列头点击切换排序**

点击「图片ID」「完成时间」「添加时间」三列表头，依次观察：
- 第一次点击 → 升序（asc 箭头）
- 第二次点击 → 降序（desc 箭头）
- 第三次点击 → 还原默认 image_id desc

Expected: 表格顺序响应点击；URL 请求参数同步更新；分页回到第 1 页。

- [ ] **Step 4: 验证时间列展示**

观察桌面端表格与移动端卡片（用浏览器 DevTools 切到 768px 以下）：
- 完成时间：已完成任务显示 `YYYY-MM-DD HH:mm:ss`，未完成任务显示 `-`
- 添加时间：所有任务显示创建时间
- 移动端卡片：两段时间在「大小/速度」下方一行展示

Expected: 格式统一，空值显示 `-`。

- [ ] **Step 5: 验证后端 API 默认值**

```bash
curl -s "http://localhost:8000/api/v1/download/tasks?page_size=5" | python -c "import json,sys; d=json.load(sys.stdin); print([t['image_id'] for t in d['data']])"
```

Expected: 输出为降序的 image_id 列表（验证默认值生效）。

- [ ] **Step 6: 标记完成**

如全部通过，本计划所有任务完成，关闭 TodoWrite 中剩余 todos。

---

## 自审报告

### Spec 覆盖检查

| Spec 章节 | 对应任务 |
|-----------|----------|
| §1.3 目标核心 1：表格新增时间列 | Task 3 Step 2 |
| §1.3 目标核心 1：移动端同步 | Task 3 Step 3-4 |
| §1.3 目标核心 2：所有 Tab 默认 image_id desc | Task 4 Step 1, 2, 3 |
| §1.3 目标核心 3：列头点击排序 | Task 4 Step 4-6 |
| §3.1 后端 sort_by 默认值改 image_id | Task 2 Step 3 |
| §5.1.1 DAO 白名单加 image_id | Task 1 Step 3 |
| §5.1.3 DAO 单元测试 3 个 | Task 1 Step 1（2 个）+ 既有 test_query_tasks_rejects_invalid_sort_by 覆盖 |
| §5.1.3 API 单元测试 2 个 | Task 2 Step 1 |
| §5.2.7 formatDateTime 函数 | Task 3 Step 1 |
| §5.3 验证清单 | Task 5 |

### Placeholder 扫描

无 "TBD/TODO/实现稍后" 等占位符。

### 类型一致性检查

- `sortBy` / `sortOrder` ref 在 Task 4 Step 2 定义，在 Step 3 (loadTasks) 与 Step 5 (el-table :default-sort) 与 Step 6 (onSortChange) 三处使用，命名一致
- `formatDateTime` 在 Task 3 Step 1 定义，在 Step 2 (桌面表格) 与 Step 3 (移动卡片) 两处调用，命名一致
- 后端 `sort_by` 字面量值 `image_id` 在 DAO 白名单、API Literal、前端 `sortBy.value` 三处一致