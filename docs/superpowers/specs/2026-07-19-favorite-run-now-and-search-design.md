# 收藏夹立即执行 + 搜索 — 设计文档

**状态**：Draft
**日期**：2026-07-19
**分支**：`feature`
**类型**：新功能 + 行为变更（解除 schedule 限制）

---

## 1. 目标

为收藏夹面板增加两类用户级功能：

1. **立即执行任务**：在收藏夹面板中任意收藏夹项上点击小图标按钮，立即触发该收藏夹的调度抓取（不依赖 cron、不依赖 `schedule_enabled`）。
2. **收藏夹搜索**：在收藏夹列表下方增加一个搜索栏，按 `name` 或 `tags` 字段过滤列表（纯前端过滤）。

明确**不在范围内**：

- 进度条 / SSE 实时回报（fire-and-forget + `ElMessage` 提示足够）
- 批量执行所有收藏夹
- 编辑面板内增加"立即执行"按钮（hover 按钮已够用，避免改动扩散）
- 后端 API 重命名 / 新增端点（现有 `/schedule/trigger` 已足够）
- 区分手动触发 / 定时调度的字段（统一记录为"最近执行"）

---

## 2. 背景与根因

### 2.1 当前触发能力

- 后端 `POST /api/v1/favorites/{id}/schedule/trigger` 已实现（`backend/src/api/v1/favorites.py:184`）
- 后端 `run_folder_schedule` 已实现（`backend/src/services/favorite_scheduler.py:23`）
- 刚修过的阻塞 bug（`time.sleep(10)` → `await asyncio.sleep(10)`、trigger 改为 fire-and-forget）已应用
- **但存在两条 schedule_enabled 校验**：
  - API 端点：`if not folder.schedule_enabled: raise APIException(ErrMsg.SCHEDULE_DISABLED)`
  - Service 入口：`if not folder.schedule_enabled: return {"skipped": True, "reason": "disabled"}`
- 这意味着：**未启用定时的收藏夹无法手动触发**——而"立即执行"在产品语义上应与 cron 解耦

### 2.1.1 残留 job 风险（解除限制后新增边缘问题）

解除 `schedule_enabled` 限制**会放大**一个潜在问题：APScheduler 中残留 job 的影响。

**残留 job 来源**：

| 来源 | 概率 | 说明 |
|------|------|------|
| `unregister_folder` 异常被吞 | 低 | `try/except Exception:` 太宽，可能漏掉清理 |
| 直接 DB 修改（绕过 API） | 中 | 用户/运维误操作导致 DB 与 APScheduler 不同步 |
| `update_folder` 时 `schedule_fields_changed=False` | 极低 | 当前实现已正确判断 |

**行为对比**：

| 触发路径 | 解除限制前 | 解除限制后（无防御） |
|---------|------------|------------------|
| 残留 job 的 cron 触发 | `run_folder_schedule` 静默跳过 | **真正执行抓取**，更新 `last_schedule_*` |
| 用户感知 | DB 状态不变，感觉"关了" | DB 状态更新，UI 显示"刚刚运行"，但用户以为定时是关的 |

**结论**：必须在 `_on_folder_trigger` 入口加防御性检查 + 顺手清理残留 job，确保**定时触发仍受 DB `schedule_enabled` 控制**，而**手动触发路径不受影响**。

### 2.2 前端现状

- `frontend/src/api/favorites.js` 暴露 `triggerFolderSchedule` 和 `getFolderScheduleStatus`，但**前端任何 .vue/.js 文件均无 import 调用**
- `FavoritePanel.vue`（收藏夹主面板）已渲染 `schedule-badge` / `cursor-badge` / `count`，但**无"立即执行"按钮**
- `FavoritePanel.vue` 完全未做移动端 CSS 适配（无 `@media`），但项目其他组件（`Download.vue` / `Config.vue` / `PreviewCleanupDialog.vue`）均按 `window.innerWidth <= 768` 做了响应式
- 项目已有"标签搜索" UI 参考：`AdvancedQuery.vue:120-132` 的 `.tag-search-bar` 样式（`<el-input>` + `Search` 图标 + `clearable`）

### 2.3 用户决策记录

| 决策点 | 决策 | 理由 |
|--------|------|------|
| 按钮位置 | 双入口：列表项 + 编辑面板（后续） | 列表项 1 次点击触发；编辑面板入口留给后续 PR |
| 移动端 hover 行为 | 桌面 hover 显示 / 移动常驻 | 触摸设备无 hover 概念；项目已有触摸长按编辑功能 |
| 搜索栏位置 | 列表下方 | 与 `AdvancedQuery.vue` 的 `.tag-search-bar` 视觉一致 |
| 按钮形式 | 小图标按钮 | 节省列表项宽度 |
| schedule_enabled 限制 | **解除** | 手动触发应与 cron 解耦 |
| 字段语义 | `last_schedule_*` = "最近执行" | 零字段改动，向后兼容 |

---

## 3. 设计要点

### 3.1 后端改动

#### 改动 1：API 端点解除 schedule_enabled 限制

文件：`backend/src/api/v1/favorites.py`

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

#### 改动 2：Service 层解除 schedule_enabled 跳过逻辑

文件：`backend/src/services/favorite_scheduler.py`

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

#### 改动 3：字段语义调整（零代码改动）

`FavoriteFolder.last_scheduled_at` / `last_schedule_status` / `last_schedule_stats` / `last_synced_id` 字段语义由"上次定时调度执行"扩展为"**最近一次执行**"（手动触发或定时触发均会更新）。

**前端 UI 不做改动**：schedule badge 文案保持"30 分钟前运行过"即可。

#### 改动 4：定时触发入口防御性检查 + 顺手清理残留 job

文件：`backend/src/infrastructure/scheduler.py`

**问题**：解除 `schedule_enabled` 限制后，如果 APScheduler 中残留 job（比如 DB 直接修改、`unregister_folder` 异常被吞），cron 触发会真正执行抓取，与用户关闭定时任务的意图不符。

**方案**：在 `_on_folder_trigger` 入口检查 DB `schedule_enabled`，False 则跳过并清理残留 job。手动触发路径（API → `run_folder_schedule`）完全不受影响。

```python
async def _on_folder_trigger(folder_id: int) -> None:
    """定时触发入口：防御性检查 + 顺手清理残留 job"""
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

**语义边界**：

| 触发来源 | schedule_enabled 检查 | 入口 |
|---------|---------------------|------|
| 手动触发（API） | ❌ 不检查 | `POST /api/v1/favorites/{id}/schedule/trigger` |
| 定时触发（cron） | ✅ 检查 + 清理 | `_on_folder_trigger` |

**性能影响**：每次 cron 触发多一次 DB 查询（1-2ms，可忽略）。

### 3.2 前端改动

#### 改动 1：FavoritePanel.vue 整合触发按钮 + 搜索栏

文件：`frontend/src/components/FavoritePanel.vue`

新增状态：

```js
const folderSearchKeyword = ref('')
const triggeringSet = ref(new Set())  // 正在触发的 folder.id
const hasHover = ref(true)             // 设备是否支持精细 hover
```

新增 matchMedia 监听（完整生命周期）：

```js
let mqlRef = null
const onMqChange = (e) => { hasHover.value = e.matches }

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

搜索过滤（computed）：

```js
const filteredFolders = computed(() => {
  const kw = folderSearchKeyword.value.trim().toLowerCase()
  if (!kw) return props.folders
  return props.folders.filter(f =>
    (f.name || '').toLowerCase().includes(kw) ||
    (f.tags || '').toLowerCase().includes(kw)
  )
})
```

触发处理：

```js
import { triggerFolderSchedule } from '@/api/favorites'

const handleTrigger = async (folder) => {
  if (triggeringSet.value.has(folder.id)) return
  triggeringSet.value.add(folder.id)
  try {
    await triggerFolderSchedule(folder.id)
    ElMessage.success(`已触发：${folder.name}`)
    emit('triggered', folder)  // 通知父组件刷新 stats（可选）
  } catch (e) {
    ElMessage.error(`触发失败：${e?.message || '未知错误'}`)
  } finally {
    triggeringSet.value.delete(folder.id)
  }
}
```

#### 改动 2：UI 模板改造

**列表项右侧增加触发按钮**：

```diff
 <div class="folder-meta">
+  <el-button
+    v-if="folder.tags && folder.tags.trim()"
+    link
+    size="small"
+    :loading="triggeringSet.has(folder.id)"
+    class="folder-trigger-btn"
+    :title="`立即执行：${folder.name}`"
+    @click.stop="handleTrigger(folder)"
+  >
+    <el-icon><VideoPlay /></el-icon>
+  </el-button>
   <el-tag v-if="folder.schedule_enabled && folder.last_synced_id != null" ...>
     ...
   </el-tag>
   ...
 </div>
```

> **关于 `v-if="folder.tags && folder.tags.trim()"`**：没有 tags 的 folder 无法执行抓取（无 API 查询目标），应隐藏按钮。

**列表下方增加搜索栏**：

```diff
 <div v-if="folders.length === 0" class="empty-state">
   <el-icon class="empty-icon"><FolderOpened /></el-icon>
   <div class="empty-text">暂无收藏夹</div>
 </div>
+<div v-else-if="filteredFolders.length === 0 && folderSearchKeyword" class="empty-state">
+  <el-icon class="empty-icon"><Search /></el-icon>
+  <div class="empty-text">无匹配收藏夹</div>
+</div>
+<div class="tag-search-bar">
+  <el-input
+    v-model="folderSearchKeyword"
+    placeholder="搜索收藏夹..."
+    size="small"
+    clearable
+  >
+    <template #prefix>
+      <el-icon><Search /></el-icon>
+    </template>
+  </el-input>
+</div>
```

**列表迭代数据源切换**：

```diff
 <div
-  v-for="folder in folders"
+  v-for="folder in filteredFolders"
   :key="folder.id"
   ...
```

#### 改动 3：CSS 改造

```css
/* 触发按钮：默认透明，hover 显示 */
.folder-trigger-btn {
  opacity: 0;
  transition: opacity 0.15s;
  padding: 2px 4px;
  margin: 0;
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

/* 搜索栏样式：与 AdvancedQuery.vue 保持一致 */
.tag-search-bar {
  padding: 8px 12px;
  border-top: 1px solid var(--border-color);
}
```

### 3.3 数据流

```
用户输入搜索关键词
    ↓
folderSearchKeyword (ref)
    ↓
filteredFolders (computed)
    ↓
列表渲染

用户 hover / tap folder-item
    ↓
触发按钮可见（CSS）
    ↓
用户点击 ▶ 按钮
    ↓
triggerFolderSchedule(folder.id)  [POST /api/v1/favorites/{id}/schedule/trigger]
    ↓
后端 asyncio.create_task(run_folder_schedule(folder_id))
    ↓
前端收到 status="queued" 响应
    ↓
ElMessage.success("已触发：xxx")
    ↓
（可选）emit('triggered') 让父组件刷新 favoriteFolders
```

---

## 4. 验收标准

| 编号 | 验收项 | 判定方法 |
|------|--------|----------|
| AC-1 | 桌面端 hover folder-item 时右侧显示触发按钮 | 手动 + 浏览器 DevTools 模拟 |
| AC-2 | 桌面端鼠标移开后按钮隐藏 | 手动 |
| AC-3 | 移动端（Chrome DevTools 切到 iPhone viewport）按钮常驻显示 | 手动 + DevTools |
| AC-4 | 触发按钮点击后变为 loading 态，期间不可重复点击 | 手动 |
| AC-5 | 未启用 schedule 的 folder 也能触发（不再被 SCHEDULE_DISABLED 拒绝） | curl 测试 + UI 测试 |
| AC-6 | 触发成功后 `last_scheduled_at` / `last_schedule_stats` 更新 | 看 DB |
| AC-7 | 触发无 tags 的 folder 不显示按钮（避免无效操作） | UI 测试 |
| AC-8 | 搜索关键词过滤 name + tags（任一命中） | 手动 |
| AC-9 | 搜索无结果显示"无匹配收藏夹" | 手动 |
| AC-10 | 清空搜索关键词恢复完整列表 | 手动 |
| AC-11 | 搜索栏视觉与 AdvancedQuery.vue 的 `.tag-search-bar` 一致 | 视觉对比 |
| AC-12 | 后端并发触发同 folder：第二次进入 semaphore 队列，不报错 | curl 并发测试 |
| AC-13 | APScheduler 残留 job 触发时（DB schedule_enabled=False 但 APScheduler 中存在 job），定时触发被跳过且残留 job 被清理 | 手动注入残留 job + cron 时间触发 |
| AC-14 | 手动触发路径不受影响：未启用 schedule 的 folder 仍能成功触发（schedule_enabled 检查只在定时入口） | curl + UI |

---

## 5. 测试清单

### 5.1 单元 / 集成测试

- **后端**：
  - `test_trigger_unenabled_schedule.py`：未启用 schedule 的 folder 触发后能正常返回 stats（不应被 SCHEDULE_DISABLED 拒绝）
  - 已有 `test_run_folder_schedule.py`（如有）覆盖 stats 写入逻辑

- **前端**：
  - 提取 `filteredFolders` computed 为纯函数（`(folders, kw) => filtered`），加 vitest 测试覆盖边界（空 kw、大小写、特殊字符）
  - 提取 `handleTrigger` 防重复逻辑测试（triggeringSet）

### 5.2 手动测试矩阵

| 场景 | 操作 | 预期 |
|------|------|------|
| 桌面 hover | 鼠标移到 folder 项 | ▶ 按钮淡入 |
| 桌面 移开 | 鼠标移走 | ▶ 按钮淡出 |
| 桌面 点击 | 点击 ▶ | 按钮 loading → ElMessage 成功 → 恢复 |
| 桌面 重复点击 | 短时间内点 2 次 | 第二次无效（loading 中） |
| 桌面 未启用 schedule | hover 未启用 schedule 的 folder | 按钮可见，点击可触发 |
| 桌面 无 tags | hover 无 tags 的 folder | **按钮不显示** |
| 移动 viewport | DevTools 切到 iPhone 375px | ▶ 按钮常驻 |
| 触摸 | 真机测试 | tap 触发 |
| 搜索 | 输入"pan" | 列表过滤为 name 或 tags 含 pan 的 folder |
| 搜索无结果 | 输入"不存在" | 显示"无匹配收藏夹" |
| 搜索清空 | 点 clear 图标 | 恢复完整列表 |
| 后端并发 | 同 folder 连发 2 个 trigger | 两个都 200，第二个排队 |
| 后端 SCHEDULE_DISABLED | curl POST trigger（修复后） | 返回 status=queued 而非 5002 |
| 残留 job 清理 | DB 改 schedule_enabled=False 但 APScheduler 仍有 job，cron 时间到 | 定时触发被跳过 + log warning + APScheduler job 被清理 |
| 残留 job 触发不污染 stats | 同上场景 | DB 的 last_schedule_* 字段不被更新 |

---

## 6. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 连续触发同 folder | 重复抓取、API 限流 | triggeringSet 禁用 + 后端 `_schedule_semaphore` (max=2) 兜底 |
| 混合设备（触摸笔记本）误判 hover | 触摸时按钮不显示 | 用 `(hover: hover) AND (pointer: fine)` 复合判断（精细指针才有 hover） |
| 移动端常驻按钮挤压列表宽度 | 视觉拥挤 | 16px 小图标按钮（`size="small"` + 紧凑 padding） |
| schedule 字段语义变更 | 前端 UI 文案不准确 | 不改 UI 文案，"30 分钟前运行过"对手动/自动均合理 |
| matchMedia 内存泄漏 | 组件卸载后监听残留 | `onUnmounted` 清理（需保存 mql 引用） |
| 触发后 stats 不刷新 | 前端 schedule badge 显示旧时间 | 可选 `emit('triggered')` 让父组件刷新；本次最小实现可不做，留作后续 |

---

## 7. 实施步骤（供 writing-plans 拆分）

1. **后端 - 解除 schedule_enabled 限制**：
   - `backend/src/api/v1/favorites.py`：删除触发端点的 schedule_enabled 检查
   - `backend/src/services/favorite_scheduler.py`：删除 run_folder_schedule 内的 schedule_enabled 跳过逻辑

1.5. **后端 - 定时入口防御性检查 + 清理残留 job**：
   - `backend/src/infrastructure/scheduler.py`：改 `_on_folder_trigger`，加 DB 查询 + schedule_enabled 检查 + 顺手 `unregister_folder`
   - 手动触发路径完全不受影响（API 端点不查 schedule_enabled）

2. **前端 - 新增搜索栏**：
   - `frontend/src/components/FavoritePanel.vue`：加 folderSearchKeyword、filteredFolders computed、模板切换迭代源、加搜索栏 UI 和 empty state

3. **前端 - 新增触发按钮**：
   - `frontend/src/components/FavoritePanel.vue`：加 triggeringSet、hasHover、handleTrigger 函数
   - 加 matchMedia 生命周期管理
   - 加按钮 UI（folder-item 内、v-if 条件、loading 态）
   - 加 CSS（hover 显示、移动常驻、聚焦状态）

4. **测试**：
   - 后端：未启用 schedule 触发测试用例 + 残留 job 触发测试
   - 前端：filter computed 单测、handleTrigger 防重复测试
   - 手动：测试矩阵全过（含残留 job 场景）

5. **代码规范检查**：
   - AGENTS.md 检查清单：类型注解、docstring、Field 校验、错误码

---

## 8. 附录

### 8.1 关键文件路径

| 用途 | 路径 |
|------|------|
| 触发 API 端点 | `backend/src/api/v1/favorites.py:184` |
| 调度 Service 入口 | `backend/src/services/favorite_scheduler.py:23` |
| 调度 Service 内部禁用检查 | `backend/src/services/favorite_scheduler.py:30-31` |
| 收藏夹主面板 | `frontend/src/components/FavoritePanel.vue` |
| favorites API 封装 | `frontend/src/api/favorites.js:62-64` |
| tag 搜索 UI 参考 | `frontend/src/components/AdvancedQuery.vue:120-132` |

### 8.2 字段语义对照表

| 字段 | 旧语义 | 新语义 |
|------|--------|--------|
| `last_scheduled_at` | 上次定时调度时间 | **最近一次执行时间**（手动/自动） |
| `last_schedule_status` | 上次定时调度状态 | **最近一次执行状态** |
| `last_schedule_stats` | 上次定时调度 stats | **最近一次执行 stats** |
| `last_synced_id` | 上次定时调度游标 | **最近一次执行游标** |

### 8.3 相关文档

- 阻塞 bug 修复（已 commit 但未推送）：`time.sleep` → `await asyncio.sleep`、`trigger_folder_schedule` 改为 fire-and-forget
- 收藏夹调度功能 spec：`docs/superpowers/specs/2026-06-05-favorite-folder-scheduled-tasks-design.md`
- 调度 zombie 修复：`docs/superpowers/specs/2026-06-09-favorite-scheduler-zombie-fix-design.md`
