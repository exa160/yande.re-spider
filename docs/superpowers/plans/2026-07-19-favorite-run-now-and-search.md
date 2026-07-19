# 收藏夹立即执行 + 搜索 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给收藏夹面板增加"立即执行"小图标按钮（所有 folder 均可触发，包括未启用定时）+ 列表下方搜索栏（按 name / tags 过滤）。

**Architecture:** 后端解除 schedule_enabled 限制但定时入口加防御性检查；前端在 FavoritePanel.vue 单文件内整合状态 + UI + CSS。

**Tech Stack:** FastAPI + SQLAlchemy + APScheduler (Python 3.12) / Vue 3.4 + Element Plus 2.5 + Vitest 3.x

**前置阅读：**
- Spec：`docs/superpowers/specs/2026-07-19-favorite-run-now-and-search-design.md`
- 项目规范：`AGENTS.md`
- 全局规则：`~/.config/opencode/AGENTS.md`（中文回复 / 不推送代码，等用户确认）

---

## Task 1：后端 - 解除 trigger endpoint 的 schedule_enabled 检查

**Files:**
- Modify: `backend/src/api/v1/favorites.py:189-197`

- [ ] **Step 1: 删除 trigger endpoint 的 schedule_enabled 检查**

打开 `backend/src/api/v1/favorites.py`，定位 `trigger_folder_schedule` 函数（约 184-202 行）。删除 `if not folder.schedule_enabled` 整块（包含前后空行）：

```diff
 async def trigger_folder_schedule(folder_id: int) -> ScheduleTriggerResponse:
     """手动触发收藏夹调度（异步执行，立即返回）

     调度任务在后台异步执行，不会阻塞当前 HTTP 响应。
     通过 GET /{folder_id}/schedule/status 查询实时进度。
     """
     from src.services.favorite_scheduler import run_folder_schedule

     folder = favorite_dao.get_by_id(folder_id)
     if not folder:
         raise APIException(ErrMsg.FAVORITE_FOLDER_NOT_FOUND)
-    if not folder.schedule_enabled:
-        raise APIException(ErrMsg.SCHEDULE_DISABLED)
     asyncio.create_task(run_folder_schedule(folder_id))
     return ScheduleTriggerResponse(
         message="已触发，请通过 /schedule/status 查询进度",
         data=ScheduleTriggerStatsData(status="queued"),
     )
```

- [ ] **Step 2: 验证改动**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
grep -n "SCHEDULE_DISABLED" backend/src/api/v1/favorites.py
```

预期：无输出（该错误码已不再被 trigger endpoint 抛出）

- [ ] **Step 3: 语法检查**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
/home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "import ast; ast.parse(open('backend/src/api/v1/favorites.py').read()); print('OK')"
```

预期输出：`OK`

- [ ] **Step 4: 暂不 commit**

按用户指示不推送，本任务完成。

---

## Task 2：后端 - 解除 run_folder_schedule 的 schedule_enabled 检查

**Files:**
- Modify: `backend/src/services/favorite_scheduler.py:30-31`

- [ ] **Step 1: 删除 run_folder_schedule 的 schedule_enabled 跳过逻辑**

打开 `backend/src/services/favorite_scheduler.py`，定位 `run_folder_schedule` 函数（约 23-150 行）。删除 `if not folder.schedule_enabled` 块：

```diff
 async def run_folder_schedule(folder_id: int) -> dict:
     async with _schedule_semaphore:
         with FavoriteDao() as dao:
             folder = dao.get_by_id(folder_id)
             if not folder:
                 logger.warning(f"Folder {folder_id} not found, skip")
                 return {"skipped": True, "reason": "not_found"}
-            if not folder.schedule_enabled:
-                return {"skipped": True, "reason": "disabled"}

             dao.update(
                 folder_id,
                 last_schedule_status="running",
                 last_scheduled_at=datetime.now(),
             )
```

- [ ] **Step 2: 验证改动**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
grep -n 'reason.*disabled' backend/src/services/favorite_scheduler.py
```

预期：无输出

- [ ] **Step 3: 语法检查**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
/home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "import ast; ast.parse(open('backend/src/services/favorite_scheduler.py').read()); print('OK')"
```

预期输出：`OK`

- [ ] **Step 4: 暂不 commit**

---

## Task 3：后端 - 定时入口防御性检查 + 顺手清理残留 job

**Files:**
- Modify: `backend/src/infrastructure/scheduler.py:103-105`

- [ ] **Step 1: 改写 _on_folder_trigger 函数**

打开 `backend/src/infrastructure/scheduler.py`，定位 `_on_folder_trigger` 函数（约 103-105 行）。完整替换为：

```python
async def _on_folder_trigger(folder_id: int) -> None:
    """定时触发入口：防御性检查 + 顺手清理残留 job

    若 DB 中 folder 已不存在或 schedule_enabled=False，
    跳过本次触发并调用 unregister_folder 清理 APScheduler 中可能残留的 job。
    """
    from src.services.favorite_scheduler import run_folder_schedule
    from src.dao.favorite_dao import favorite_dao

    folder = favorite_dao.get_by_id(folder_id)
    if not folder:
        logger.warning(
            f"Scheduled trigger skipped: folder {folder_id} not found, cleanup residual job"
        )
        schedule_manager.unregister_folder(folder_id)
        return
    if not folder.schedule_enabled:
        logger.info(
            f"Scheduled trigger skipped: folder {folder_id} schedule disabled, cleanup residual job"
        )
        schedule_manager.unregister_folder(folder_id)
        return

    asyncio.create_task(run_folder_schedule(folder_id))
```

- [ ] **Step 2: 验证改动**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
grep -n "_on_folder_trigger" backend/src/infrastructure/scheduler.py
sed -n '103,130p' backend/src/infrastructure/scheduler.py
```

预期：能看到完整的 `_on_folder_trigger` 函数，含两个 early return

- [ ] **Step 3: 语法检查**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
/home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "import ast; ast.parse(open('backend/src/infrastructure/scheduler.py').read()); print('OK')"
```

预期输出：`OK`

- [ ] **Step 4: 暂不 commit**

---

## Task 4：后端 - 单元测试（未启用 schedule 触发 + 残留 job 清理）

**Files:**
- Create: `backend/unit_test/api/v1/test_trigger_unenabled_schedule.py`

- [ ] **Step 1: 创建测试目录**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
mkdir -p backend/unit_test/api/v1
ls backend/unit_test/
```

预期：能看到 `api/v1` 目录创建成功

- [ ] **Step 2: 查看现有 conftest.py 配置**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
cat conftest.py 2>/dev/null | head -30
```

预期：能看到现有 conftest 中的 fixture（如 autouse fixture 保护 DB）

- [ ] **Step 3: 写测试文件**

创建 `backend/unit_test/api/v1/test_trigger_unenabled_schedule.py`：

```python
"""验证 trigger_folder_schedule 解除 schedule_enabled 限制后行为正确"""
import pytest

from src.api.v1.favorites import trigger_folder_schedule
from src.common.constant import ErrMsg
from src.dao.favorite_dao import FavoriteDao
from src.middleware.errors import APIException


def _create_test_folder(name: str, schedule_enabled: bool = False, tags: str = "cat") -> int:
    """创建测试用收藏夹，返回 id"""
    with FavoriteDao() as dao:
        folder = dao.create(
            name=name,
            tags=tags,
            color="#409EFF",
            icon="folder",
            sort_order=999,
            schedule_enabled=schedule_enabled,
            schedule_cron="",
            schedule_mode="last_id",
            schedule_max_images=None,
        )
        return folder.id


def _delete_test_folder(folder_id: int) -> None:
    """清理测试用收藏夹"""
    with FavoriteDao() as dao:
        dao.delete(folder_id)


class TestTriggerScheduleDisabled:
    """未启用 schedule 的 folder 也能触发（不再被 SCHEDULE_DISABLED 拒绝）"""

    def test_trigger_unenabled_schedule_does_not_raise_schedule_disabled(self):
        """核心：未启用 schedule 的 folder 触发不应抛 SCHEDULE_DISABLED"""
        folder_id = _create_test_folder("test_unenabled", schedule_enabled=False)
        try:
            # 不应抛 APIException(ErrMsg.SCHEDULE_DISABLED)
            # 实际会 fire-and-forget create_task，可能因 DB session 关闭而略有延迟
            # 这里仅验证不抛 SCHEDULE_DISABLED 即可
            try:
                result = trigger_folder_schedule(folder_id)
                # 成功路径：返回 ScheduleTriggerResponse
                assert result is not None
            except APIException as e:
                # 如果抛 APIException，必须不是 SCHEDULE_DISABLED
                assert e.err_msg != ErrMsg.SCHEDULE_DISABLED, (
                    f"未启用 schedule 的 folder 不应被 SCHEDULE_DISABLED 拒绝，但抛出了: {e}"
                )
        finally:
            _delete_test_folder(folder_id)

    def test_trigger_not_found_still_raises(self):
        """不存在的 folder 仍应抛 FAVORITE_FOLDER_NOT_FOUND"""
        with pytest.raises(APIException) as exc_info:
            trigger_folder_schedule(99999999)
        assert exc_info.value.err_msg == ErrMsg.FAVORITE_FOLDER_NOT_FOUND


class TestOnFolderTriggerDefense:
    """_on_folder_trigger 定时入口防御性检查（残留 job 清理）"""

    def test_on_folder_trigger_skips_disabled_folder(self):
        """残留 job 触发 schedule_enabled=False 的 folder 时跳过"""
        from src.infrastructure.scheduler import _on_folder_trigger, schedule_manager

        folder_id = _create_test_folder("test_residual", schedule_enabled=False)
        try:
            # 注入残留 job（模拟 DB 已改 schedule_enabled=False 但 APScheduler 中还有 job）
            schedule_manager.register_folder(
                folder_id=folder_id,
                cron="0 3 * * *",  # 任意 cron
                mode="last_id",
                max_images=None,
            )
            assert folder_id in [v for v in schedule_manager._job_folder_map.values()]

            # 触发 - 不应抛异常，应清理残留 job
            import asyncio
            asyncio.run(_on_folder_trigger(folder_id))

            # 残留 job 应被清理
            assert folder_id not in [v for v in schedule_manager._job_folder_map.values()], (
                "残留 job 应被清理，但仍然存在"
            )
        finally:
            schedule_manager.unregister_folder(folder_id)
            _delete_test_folder(folder_id)

    def test_on_folder_trigger_skips_nonexistent_folder(self):
        """残留 job 指向已删除的 folder 时跳过"""
        from src.infrastructure.scheduler import _on_folder_trigger, schedule_manager

        # 注入一个不存在的 folder_id 的 job
        nonexistent_id = 99999998
        schedule_manager.register_folder(
            folder_id=nonexistent_id,
            cron="0 3 * * *",
            mode="last_id",
            max_images=None,
        )

        # 触发 - 应清理
        import asyncio
        asyncio.run(_on_folder_trigger(nonexistent_id))

        # 残留 job 应被清理
        assert nonexistent_id not in [v for v in schedule_manager._job_folder_map.values()], (
            "残留 job 应被清理，但仍然存在"
        )
        # 清理
        schedule_manager.unregister_folder(nonexistent_id)
```

- [ ] **Step 4: 运行测试验证**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
/home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m pytest backend/unit_test/api/v1/test_trigger_unenabled_schedule.py -v
```

预期：3 个测试全部通过（test_trigger_unenabled_schedule_does_not_raise_schedule_disabled、test_trigger_not_found_still_raises、test_on_folder_trigger_skips_disabled_folder、test_on_folder_trigger_skips_nonexistent_folder）

- [ ] **Step 5: 暂不 commit**

---

## Task 5：前端 - FavoritePanel.vue 状态层（ref + computed + function）

**Files:**
- Modify: `frontend/src/components/FavoritePanel.vue:220-260`

- [ ] **Step 1: 读取当前 script setup 区域**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
sed -n '220,260p' frontend/src/components/FavoritePanel.vue
```

预期：能看到当前 import + props/emit + mode/editingFolder + currentEditingFolder + form 等定义

- [ ] **Step 2: 修改 import 区域**

将 `<script setup>` 顶部（line 221-223）改为：

```js
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Clock, Delete, Edit, Folder, FolderOpened, RefreshRight, Search, Star, VideoPlay } from '@element-plus/icons-vue'
import { triggerFolderSchedule } from '@/api/favorites'
```

变更点：
- `Search` 和 `VideoPlay` 加入 icons 导入
- 新增 `onMounted, onUnmounted` 从 vue
- 新增 `triggerFolderSchedule` 从 `@/api/favorites`

- [ ] **Step 3: 新增状态变量**

在 `const form = reactive({...})` 块（line 247-259）**之后**插入：

```js
// 搜索状态
const folderSearchKeyword = ref('')

// 触发中状态：正在触发的 folder.id 集合（用于按钮 loading 防重复点击）
const triggeringSet = ref(new Set())

// 设备是否支持精细 hover（用于决定按钮是 hover 显示还是常驻）
const hasHover = ref(true)

// matchMedia 监听引用（用于 onUnmounted 清理）
let mqlRef = null
const onMqChange = (e) => { hasHover.value = e.matches }
```

- [ ] **Step 4: 新增过滤 computed**

在 `const formatLastScheduled = ...` 函数（line 397-405）**之后**插入：

```js
// 按 name / tags 过滤收藏夹（纯前端，零后端调用）
const filteredFolders = computed(() => {
  const kw = folderSearchKeyword.value.trim().toLowerCase()
  if (!kw) return props.folders
  return props.folders.filter(f =>
    (f.name || '').toLowerCase().includes(kw) ||
    (f.tags || '').toLowerCase().includes(kw)
  )
})
```

- [ ] **Step 5: 新增触发函数**

在 `filteredFolders` computed **之后**插入：

```js
// 立即执行：手动触发指定 folder 的调度抓取
const handleTrigger = async (folder) => {
  if (triggeringSet.value.has(folder.id)) return  // 防重复点击
  triggeringSet.value.add(folder.id)
  try {
    await triggerFolderSchedule(folder.id)
    ElMessage.success(`已触发：${folder.name}`)
    emit('triggered', folder)
  } catch (e) {
    const msg = e?.response?.data?.message || e?.message || '未知错误'
    ElMessage.error(`触发失败：${msg}`)
  } finally {
    triggeringSet.value.delete(folder.id)
  }
}
```

- [ ] **Step 6: 修改 defineEmits 增加 'triggered'**

将 line 231 的：

```js
const emit = defineEmits(['select', 'longPress', 'create', 'update', 'delete', 'reset-sync', 'mode-change'])
```

改为：

```js
const emit = defineEmits(['select', 'longPress', 'create', 'update', 'delete', 'reset-sync', 'mode-change', 'triggered'])
```

- [ ] **Step 7: 验证改动**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
grep -nE "folderSearchKeyword|triggeringSet|hasHover|filteredFolders|handleTrigger" frontend/src/components/FavoritePanel.vue | head -20
```

预期：能看到所有新增的状态变量、computed、函数名

- [ ] **Step 8: 暂不 commit**

---

## Task 6：前端 - matchMedia 生命周期管理

**Files:**
- Modify: `frontend/src/components/FavoritePanel.vue`（在 Task 5 新增代码附近）

- [ ] **Step 1: 添加 onMounted / onUnmounted**

在 `const handleTrigger = ...` 函数（Task 5 Step 5 新增）**之后**插入：

```js
// 设备能力检测：精细指针设备才支持 hover
onMounted(() => {
  mqlRef = window.matchMedia('(hover: hover) and (pointer: fine)')
  hasHover.value = mqlRef.matches
  mqlRef.addEventListener('change', onMqChange)
})

onUnmounted(() => {
  if (mqlRef) {
    mqlRef.removeEventListener('change', onMqChange)
    mqlRef = null
  }
})
```

- [ ] **Step 2: 验证**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
grep -nE "onMounted|onUnmounted|mqlRef" frontend/src/components/FavoritePanel.vue
```

预期：能看到 onMounted、onUnmounted、mqlRef 三处引用

- [ ] **Step 3: 暂不 commit**

---

## Task 7：前端 - UI 模板改造（按钮 + 搜索栏）

**Files:**
- Modify: `frontend/src/components/FavoritePanel.vue:1-218`

- [ ] **Step 1: 修改列表迭代数据源**

将 `<div v-for="folder in folders"` （line 6）改为：

```html
<div
  v-for="folder in filteredFolders"
  :key="folder.id"
```

- [ ] **Step 2: 在 folder-meta 内插入触发按钮**

定位 `folder-meta` div（约 line 23-48）。在 `<span class="folder-count">` 之前插入：

```html
<el-button
  v-if="folder.tags && folder.tags.trim()"
  link
  size="small"
  :loading="triggeringSet.has(folder.id)"
  class="folder-trigger-btn"
  :title="`立即执行：${folder.name}`"
  @click.stop="handleTrigger(folder)"
>
  <el-icon><VideoPlay /></el-icon>
</el-button>
```

注意：`v-if` 条件确保无 tags 的 folder 不显示按钮（无法抓取）

- [ ] **Step 3: 修改空状态显示**

将 line 50-53 的空状态改为根据过滤结果显示不同文案：

```html
<div v-if="folders.length === 0" class="empty-state">
  <el-icon class="empty-icon"><FolderOpened /></el-icon>
  <div class="empty-text">暂无收藏夹</div>
</div>
<div v-else-if="filteredFolders.length === 0 && folderSearchKeyword" class="empty-state">
  <el-icon class="empty-icon"><Search /></el-icon>
  <div class="empty-text">无匹配收藏夹</div>
</div>
```

- [ ] **Step 4: 在 folder-list 后添加搜索栏**

定位 `</div>` (line 54) 即 folder-list 的结束标签。在其后（仍是 `<div v-else class="inline-form">` 之前）插入：

```html
<div v-if="folders.length > 0" class="tag-search-bar">
  <el-input
    v-model="folderSearchKeyword"
    placeholder="搜索收藏夹..."
    size="small"
    clearable
  >
    <template #prefix>
      <el-icon><Search /></el-icon>
    </template>
  </el-input>
</div>
```

注意：放在 `v-if="mode === 'list'"` 块内的末尾，确保只在列表模式显示（编辑时不显示搜索栏）

- [ ] **Step 5: 验证改动**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
grep -nE "filteredFolders|folder-trigger-btn|tag-search-bar|folderSearchKeyword" frontend/src/components/FavoritePanel.vue
```

预期：能看到所有新增的模板引用

- [ ] **Step 6: 暂不 commit**

---

## Task 8：前端 - CSS 改造（hover 显示 + 移动常驻 + 搜索栏样式）

**Files:**
- Modify: `frontend/src/components/FavoritePanel.vue`（在 `<style scoped>` 区域）

- [ ] **Step 1: 定位 style 区域起始**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
grep -n "folder-count\|<style scoped>" frontend/src/components/FavoritePanel.vue | head -5
```

预期：能看到 `.folder-count` 样式（约 line 568-571）和 `<style scoped>` 起始

- [ ] **Step 2: 在 .folder-count 样式之后插入触发按钮 CSS**

在 `.folder-count` 块（line 568-571）**之后**插入：

```css
/* 触发按钮：默认透明，hover 显示 */
.folder-trigger-btn {
  opacity: 0;
  transition: opacity 0.15s;
  padding: 2px 4px;
  margin: 0;
  flex-shrink: 0;
}
.folder-item:hover .folder-trigger-btn,
.folder-trigger-btn:focus,
.folder-trigger-btn.is-loading {
  opacity: 1;
}

/* 移动端常驻（hover: none 设备） */
@media (hover: none) {
  .folder-trigger-btn {
    opacity: 1;
  }
}
```

- [ ] **Step 3: 在 style 末尾追加 tag-search-bar 样式**

将 `<style scoped>` 内末尾（在最后一个 `}` 之前）追加：

```css
/* 搜索栏：与 AdvancedQuery.vue 保持一致 */
.tag-search-bar {
  padding: 8px 12px;
  border-top: 1px solid var(--border-color);
}
.tag-search-bar .el-input {
  width: 100%;
}
```

- [ ] **Step 4: 验证**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
grep -nE "folder-trigger-btn|tag-search-bar|@media.*hover.*none" frontend/src/components/FavoritePanel.vue
```

预期：能看到所有新增的 CSS

- [ ] **Step 5: 暂不 commit**

---

## Task 9：手动测试矩阵 + 验收标准核对

**Files:**
- 无（验证步骤）

- [ ] **Step 1: 启动后端服务**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
cd backend && /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python service.py
```

预期：服务启动成功，监听 8000 端口

- [ ] **Step 2: 启动前端 dev server**

新开终端：

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend
npm run dev
```

预期：前端启动，监听 3000 端口

- [ ] **Step 3: 验证 API 行为**

新建一个未启用 schedule 的收藏夹（或用现有），然后：

```bash
curl -X POST http://localhost:8000/src/api/v1/favorites/{folder_id}/schedule/trigger
```

预期：返回 200 + `status: "queued"`，**不再返回 5002 SCHEDULE_DISABLED**

- [ ] **Step 4: 验证前端行为 - 桌面端 hover**

1. 打开 http://localhost:3000
2. 找到收藏夹面板
3. 鼠标移到任意收藏夹项 → 右侧应出现 ▶ 按钮
4. 鼠标移开 → 按钮应淡出
5. 点击 ▶ → 按钮变 loading → ElMessage 提示"已触发"

- [ ] **Step 5: 验证前端行为 - 移动端常驻**

1. 打开 Chrome DevTools（F12）
2. 切换到 iPhone 12 Pro viewport（或 375px 宽度）
3. 刷新页面
4. 收藏夹项右侧应**常驻**显示 ▶ 按钮（不需要 hover）

- [ ] **Step 6: 验证搜索功能**

1. 在搜索栏输入 "pan"
2. 列表应过滤为 name 或 tags 含 "pan" 的 folder
3. 清空搜索 → 恢复完整列表
4. 输入不存在的关键词 → 显示"无匹配收藏夹"

- [ ] **Step 7: 验证触发保护**

1. 快速连续点击同一 folder 的 ▶ 按钮 2 次
2. 第二次点击应无效（按钮 loading 中）

- [ ] **Step 8: 验证无 tags 的 folder 不显示按钮**

找一个 tags 为空的 folder（如果不存在，先创建一个），hover 应**不显示** ▶ 按钮

- [ ] **Step 9: 验证残留 job 清理**

1. 用 curl 调用 `PUT /favorites/{id}` 设 `schedule_enabled: true`，注册一个 cron
2. 确认 APScheduler 中有该 job
3. 手动改 DB（或用 curl 设 `schedule_enabled: false` 后调用 unregister_folder 模拟失败）
4. 等待 cron 时间触发（或用 `_on_folder_trigger({folder_id})` 直接调用）
5. 验证：日志显示 `Scheduled trigger skipped: ... cleanup residual job`，残留 job 被清理

---

## Task 10：代码规范检查 + 提交

**Files:**
- 无（验证步骤）

- [ ] **Step 1: AGENTS.md 检查清单**

按 `AGENTS.md` 代码规范检查清单核对：

- [ ] 是否使用 `APIException(ErrMsg.XXX, e=e)` 模式 — N/A（本次未新增 endpoint 错误处理）
- [ ] 是否返回 `BaseResponse` 或继承类 — ✅ `ScheduleTriggerResponse`
- [ ] 是否声明返回类型注解 — ✅ trigger endpoint 已声明
- [ ] 是否添加 docstring — ✅ trigger endpoint 已有
- [ ] Request Model 是否使用 `Field()` 校验 — N/A（本次未新增 Request 模型）
- [ ] 本地 tag 匹配规则 — N/A

- [ ] **Step 2: Pyright 类型检查**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
pyright backend/src/api/v1/favorites.py backend/src/services/favorite_scheduler.py backend/src/infrastructure/scheduler.py
```

预期：错误数 ≤ 修改前（修改前 17 个已存在的 SQLAlchemy Column 类型问题不应增加）

- [ ] **Step 3: 后端测试**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
/home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m pytest backend/unit_test/api/v1/test_trigger_unenabled_schedule.py -v
```

预期：4 个测试全部通过

- [ ] **Step 4: 前端检查**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend
npm run build
```

预期：构建成功

- [ ] **Step 5: 用户确认**

按用户指示，**所有任务完成后不 commit、不 push**，等待用户最终确认后再走 dev 推送流程。

如需 commit 推送，参考 `AGENTS.md` 的版本升级流程：
1. 切到 `feature` 分支
2. 改 3 处 version 源 → commit → push
3. PR 到 `next_dev`

---

## 附录：完成检查清单

执行完所有 Task 后，确认：

- [ ] 后端 trigger endpoint 不再抛 SCHEDULE_DISABLED（Task 1）
- [ ] 后端 run_folder_schedule 不再跳过 schedule_enabled=False folder（Task 2）
- [ ] 后端 _on_folder_trigger 加防御性检查 + 清理残留 job（Task 3）
- [ ] 后端测试 4 个全部通过（Task 4）
- [ ] 前端状态层就绪（Task 5）
- [ ] 前端 matchMedia 生命周期就绪（Task 6）
- [ ] 前端 UI 模板改造完成（Task 7）
- [ ] 前端 CSS 改造完成（Task 8）
- [ ] 手动测试矩阵全过（Task 9）
- [ ] 代码规范检查通过（Task 10）

## 附录：相关文档

- Spec：`docs/superpowers/specs/2026-07-19-favorite-run-now-and-search-design.md`
- 阻塞 bug 修复（已修复未推送）：`time.sleep` → `await asyncio.sleep`、`trigger` 改为 fire-and-forget
- 相关 spec：`docs/superpowers/specs/2026-06-05-favorite-folder-scheduled-tasks-design.md`
- AGENTS.md：项目规范
