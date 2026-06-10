# 收藏夹定时异步任务功能 — 设计文档

## 文档信息

- **项目名称**: yande.re-spider-next
- **功能名称**: 收藏夹定时异步任务 (Favorite Folder Scheduled Tasks)
- **版本**: v1.0
- **创建日期**: 2026-06-05
- **作者**: Sisyphus (brainstorming)
- **状态**: 待审阅
- **关联**: README 架构优化未完成项"增加异步定时任务功能（根据 tag 定时启动下载器）"

---

## 1. 目标与背景

### 1.1 现状

- 收藏夹 (`FavoriteFolder`) 已实现完整的 CRUD、排序、本地/在线数量刷新
- 下载器 (`MultiDown`) + 下载队列 (`DownloadQueue`，5 workers 限流) 已实现异步并发
- 标签搜索订阅 UI 已存在，但**所有下载均需手动触发**
- 后端**无任何调度器**（无 `apscheduler`/`celery`/`schedule` 痕迹）
- `pyproject.toml` 无相关依赖

### 1.2 目标

为收藏夹增加**按 cron 表达式定时自动拉取新图**的能力，复用现有"在线模式浏览"流程将未下载图片自动入下载队列。

### 1.3 非目标 (YAGNI)

- 不做多机分布式调度（仅单进程 FastAPI 部署）
- 不做复杂的任务依赖、优先级调度
- 不做邮件/通知推送
- 不做调度历史的多月统计（仅保留最近一次执行结果）

---

## 2. 需求决策汇总

| 维度 | 决策 |
|---|---|
| 触发模式 | 每收藏夹独立 cron 表达式 |
| 抓取策略 | 模拟"在线模式浏览"：`YandeDataRepository.upsert` 流程，仅未下载入队 |
| 增量模式 | `last_id` 模式：循环到本地最大 ID 为止；`max` 模式：循环到 API 最后一页 |
| 并发控制 | 抓取阶段：全局 `asyncio.Semaphore(N)`；下载阶段：复用 `download_queue` 5 workers |
| 调度库 | `apscheduler>=3.10,<4.0` + `AsyncIOScheduler` |
| 持久化 | `FavoriteFolder` 表新增字段，lifespan 启动时重载 |
| 前端 | 扩展 `FavoritePanel.vue` 弹窗 + 卡片状态展示 |
| 边界保护 | 每收藏夹可设 `schedule_max_images`，全局 `config.scheduler` 提供兜底 |
| 多收藏夹并发限流 | `max_concurrent_schedules` 全局配置项（默认 2）|

---

## 3. 架构

### 3.1 整体架构图

```
                          FastAPI 进程
  ┌─────────────────────────────────────────────────────────────┐
  │                                                              │
  │  ┌──────────────────┐    ┌──────────────────────────────┐   │
  │  │  middleware/     │    │  infrastructure/             │   │
  │  │  scheduler.py    │───▶│  scheduler.py                │   │
  │  │  (lifespan)      │    │   • AsyncIOScheduler         │   │
  │  └──────────────────┘    │   • 注册/反注册 job           │   │
  │                          │   • reload_from_db()          │   │
  │                          └──────────┬───────────────────┘   │
  │                                     │ trigger               │
  │  ┌──────────────────┐               │                       │
  │  │  services/        │◀──────────────┘                       │
  │  │  favorite_        │                                       │
  │  │  scheduler.py     │                                       │
  │  │  (业务逻辑)       │                                       │
  │  └────┬──────────────┘                                       │
  │       │                                                      │
  │       │  asyncio.create_task (不阻塞 scheduler)              │
  │       ▼                                                      │
  │  ┌──────────────────────────────────────────┐               │
  │  │  执行流程:                                │               │
  │  │  1. 解析收藏夹 tags                       │               │
  │  │  2. 模式判断: last_id / max               │               │
  │  │  3. 循环调用 yande_api.get_posts(...)     │               │
  │  │  4. YandeDataRepository.upsert()          │               │
  │  │  5. 过滤 down_flag=False → 入下载队列     │               │
  │  │  6. 受 max_images_per_run 限制            │               │
  │  │  7. 更新 last_scheduled_at / 统计信息     │               │
  │  └──────────────────────────────────────────┘               │
  │                                                              │
  │  复用: download_queue (5 workers 限流) + MultiDown            │
  └─────────────────────────────────────────────────────────────┘
```

### 3.2 文件变更清单

| 路径 | 操作 | 用途 |
|---|---|---|
| `backend/pyproject.toml` | 修改 | 增加 `apscheduler>=3.10,<4.0` |
| `backend/src/middleware/scheduler.py` | 新增 | lifespan 启停 scheduler |
| `backend/src/__init__.py` | 修改 | 在 `init_app` 注册 `SchedulerMiddleware` |
| `backend/src/infrastructure/scheduler.py` | 新增 | `AsyncIOScheduler` 单例 + `reload_from_db()` + `register_folder()` / `unregister_folder()` |
| `backend/src/services/favorite_scheduler.py` | 新增 | 核心执行逻辑：`run_folder_schedule(folder_id)` |
| `backend/src/services/favorites.py` | 修改 | 创建/更新/删除收藏夹时同步 scheduler 注册/反注册 |
| `backend/src/dao/favorite_dao.py` | 修改 | 增加 cron 表达式等字段更新方法 |
| `backend/src/dao/yande_data_dao.py` | 修改 | 新增 `get_max_id_for_tags(tags: str) -> Optional[int]` |
| `backend/src/models/database/yande.py` | 修改 | `FavoriteFolder` 表新增字段 |
| `backend/src/models/request/favorites.py` | 修改 | `FavoriteFolderCreate/Update` 新增字段 |
| `backend/src/models/response/favorites.py` | 修改 | `FavoriteFolder` 响应模型新增字段 |
| `backend/src/common/constant.py` | 修改 | 新增 `ErrMsg.SCHEDULE_*` 错误码 |
| `backend/src/common/settings.py` | 修改 | 新增 `SchedulerConfig` 子模型 |
| `backend/src/api/v1/favorites.py` | 修改 | 新增 `POST /{id}/schedule/trigger`、`GET /{id}/schedule/status` |
| `backend/config/config.yaml` | 修改 | 新增 `scheduler:` 段 |
| `frontend/src/api/favorites.js` | 修改 | 新增 `triggerFolderSchedule`、`getFolderScheduleStatus` |
| `frontend/src/components/FavoritePanel.vue` | 修改 | 弹窗增加定时配置；卡片展示调度状态 |
| `unit_test/test_favorite_scheduler.py` | 新增 | 调度器核心逻辑测试 |

---

## 4. 数据模型

### 4.1 `FavoriteFolder` 表新增字段

```python
schedule_enabled: bool = Field(default=False)
schedule_cron: str = Field(default="", max_length=64)
schedule_mode: str = Field(default="last_id", max_length=16)  # "last_id" | "max"
schedule_max_images: Optional[int] = Field(default=None)
last_scheduled_at: Optional[datetime] = Field(default=None)
last_schedule_status: Optional[str] = Field(default=None, max_length=16)  # "running" | "success" | "failed"
last_schedule_stats: Optional[dict] = Field(default=None)  # JSON
```

### 4.2 新增 `SchedulerConfig`

```python
class SchedulerConfig(ConfigModel):
    max_concurrent_schedules: int = Field(2, ge=1, le=10, description="同时抓取的收藏夹数")
    max_images_per_run_default: int = Field(200, ge=1, description="单收藏夹单次拉取上限兜底")
    max_pages_per_run: int = Field(5, ge=1, le=20, description="单收藏夹单次分页上限兜底")
```

挂载到 `Config.scheduler`。

### 4.3 数据库迁移

由于项目使用 SQLAlchemy `Base = DeclarativeBase`，且尚未引入 alembic，本项目采用 **"启动时自动建表"** 模式（参考现有 `database.py`）。本次新增字段需要：
- 在 `models/database/yande.py` 的 `FavoriteFolder` 中声明
- 启动时 `Base.metadata.create_all()` 会**自动添加新列**（SQLAlchemy 对已有表会执行 `ALTER TABLE ADD COLUMN`）
- 对于现有数据，新字段会使用默认值，无破坏性

> **注意**: 如果用户已有生产数据，建议备份 `yande_data.db`。SQLAlchemy 自动迁移对 SQLite/MariaDB 均有效。

---

## 5. 核心流程

### 5.1 调度器初始化（lifespan 启动）

```
service.py 启动
  → init_app(app)
    → SchedulerMiddleware.init_app(app)
      → 注册 lifespan hook:
          ┌────────────────────────────────────────┐
          │ yield 之前:                            │
          │  1. 创建 AsyncIOScheduler()            │
          │  2. scheduler.start()                  │
          │  3. reload_from_db()                   │
          │     - SELECT * FROM favorite_folders   │
          │       WHERE schedule_enabled = 1       │
          │     - for each: register_folder(...)   │
          │                                        │
          │ yield 之后 (关闭):                     │
          │  1. scheduler.shutdown(wait=False)     │
          └────────────────────────────────────────┘
```

### 5.2 单次执行流程（job func）

```python
# infrastructure/scheduler.py 内的 job func

async def _on_folder_trigger(folder_id: int):
    """APScheduler 调度入口，立即创建 task，立即返回"""
    asyncio.create_task(
        favorite_scheduler.run_folder_schedule(folder_id)
    )
```

```python
# services/favorite_scheduler.py

_schedule_semaphore = asyncio.Semaphore(
    config.scheduler.max_concurrent_schedules  # 默认 2
)

async def run_folder_schedule(folder_id: int) -> dict:
    async with _schedule_semaphore:
        folder = favorite_dao.get_by_id(folder_id)
        if not folder or not folder.schedule_enabled:
            return {"skipped": True}

        favorite_dao.update(folder_id,
            last_schedule_status="running",
            last_scheduled_at=datetime.now())

        stats = {"new_images": 0, "enqueued": 0, "skipped": 0,
                 "pages_fetched": 0, "duration_sec": 0, "errors": []}
        start = time.monotonic()

        try:
            # 1. 解析收藏夹 tags
            query_params = FavoritesService._parse_tags_to_params(folder.tags)
            raw_tags_str = folder.tags.strip()  # 原始 tags 字符串，供 YandeDataRepository.get_max_id_for_tags 使用

            # 2. 模式判断
            last_id = None
            if folder.schedule_mode == "last_id":
                with YandeDataRepository() as repo:
                    last_id = repo.get_max_id_for_tags(raw_tags_str)
                # last_id 可能为 None（本地无匹配），表示从头开始抓

            # 3. 限流参数
            max_images = (folder.schedule_max_images
                          or config.scheduler.max_images_per_run_default)
            max_pages = config.scheduler.max_pages_per_run

            # 4. 分页抓取（使用 YandeApi.get_ranking，需在线程池中执行）
            yande_api = YandeApi()
            enqueued_count = 0
            page = 1
            stop = False
            while page <= max_pages and enqueued_count < max_images:
                try:
                    rank_params = YandeApi.PostRankQueryParams(
                        page=page, limit=100, tags=query_params.tags)
                    page_data = await asyncio.to_thread(
                        yande_api.get_ranking, rank_params)
                    items = page_data.root  # YandePostData 是 RootModel
                except Exception as api_err:
                    stats["errors"].append(f"page {page} api error: {api_err}")
                    logger.exception(f"Folder {folder_id} page {page} failed")
                    break  # 单页失败停止本次

                if not items:
                    break

                for item in items:
                    # 限流
                    if enqueued_count >= max_images:
                        stop = True
                        break

                    # last_id 模式: 到达本地最大 ID 即停止
                    if last_id is not None and item.id <= last_id:
                        stop = True
                        break

                    stats["new_images"] += 1
                    try:
                        with YandeDataRepository() as repo:
                            existing = repo.get_by_id(item.id)
                            repo.upsert(item)  # 复用在线浏览流程

                            if existing is None or not existing.down_flag:
                                await DownloadService.create_task(item.id)
                                enqueued_count += 1
                                stats["enqueued"] += 1
                            else:
                                stats["skipped"] += 1
                    except Exception as item_err:
                        stats["errors"].append(
                            f"item {item.id} error: {item_err}")
                        logger.exception(...)
                        continue

                if stop:
                    break
                page += 1

            stats["pages_fetched"] = page
            stats["duration_sec"] = round(time.monotonic() - start, 2)

            favorite_dao.update(folder_id,
                last_schedule_status="success",
                last_schedule_stats=json.dumps(stats))

            return stats

        except Exception as e:
            stats["errors"].append(str(e))
            stats["duration_sec"] = round(time.monotonic() - start, 2)
            favorite_dao.update(folder_id,
                last_schedule_status="failed",
                last_schedule_stats=json.dumps(stats))
            logger.exception(f"Folder {folder_id} schedule failed")
            return stats
```

### 5.2.1 需新增的辅助方法

由于 `YandeApi.get_ranking` 接受 `PostRankQueryParams`（与收藏夹的 `YandeDataQueryParams` 不同），且 `YandeDataRepository` 当前没有 "按 tags 查询 max(id)" 的方法，需新增以下辅助方法：

**`backend/src/dao/yande_data_dao.py`** 新增方法：
```python
def get_max_id_for_tags(self, tags: str) -> Optional[int]:
    """返回本地数据库中与 tags 匹配的最大 YandeData.id，无匹配返回 None。
    tags 字符串按空格拆分，每个 tag 视为 AND 条件（与 _tag_filter 行为一致）。
    """
    if not tags or not tags.strip():
        return None
    filter_funcs = [self._tag_filter(tags)]
    stmt = select(func.max(YandeData.id)).filter(*filter_funcs)
    return self.session.execute(stmt).scalar_one_or_none()
```

### 5.3 配置变更联动

```
用户在前端修改收藏夹的 schedule 字段
  → PUT /api/v1/favorites/{id}
    → FavoritesService.update_folder()
      → 1. favorite_dao.update()                  # DB 持久化
      → 2. scheduler_api.unregister_folder(id)    # 旧 job 卸载
      → 3. 如果 schedule_enabled → register_folder(id, new_cron, ...)
```

### 5.4 手动触发 API

```
POST /api/v1/favorites/{id}/schedule/trigger
  → 同步立即运行 run_folder_schedule(id)
  → 返回本次 stats
  → 注意: 不会修改 last_scheduled_at (避免和"自动触发"混淆)
```

---

## 6. API 设计

### 6.1 修改的接口

#### `POST /api/v1/favorites`
请求体增加字段（`FavoriteFolderCreate`）：
```json
{
  "name": "猫娘",
  "tags": "catgirl rating:s",
  "color": "#409EFF",
  "icon": "folder",
  "sort_order": 0,
  "schedule_enabled": false,
  "schedule_cron": "",
  "schedule_mode": "last_id",
  "schedule_max_images": null
}
```

#### `PUT /api/v1/favorites/{folder_id}`
请求体增加字段（`FavoriteFolderUpdate`）：同上可选字段。

#### `GET /api/v1/favorites`
响应体每项增加：
```json
{
  "id": 1,
  "name": "猫娘",
  "...": "...",
  "schedule_enabled": true,
  "schedule_cron": "0 3 * * *",
  "schedule_mode": "last_id",
  "schedule_max_images": 100,
  "last_scheduled_at": "2026-06-05T03:00:00",
  "last_schedule_status": "success",
  "last_schedule_stats": {
    "new_images": 5, "enqueued": 5, "skipped": 0,
    "pages_fetched": 1, "duration_sec": 3.21, "errors": []
  }
}
```

### 6.2 新增接口

#### `POST /api/v1/favorites/{folder_id}/schedule/trigger`
手动触发一次调度。

响应：
```json
{
  "code": "0000",
  "message": "触发成功",
  "data": {
    "new_images": 5, "enqueued": 5, "skipped": 0,
    "pages_fetched": 1, "duration_sec": 3.21, "errors": []
  }
}
```

错误码：
- `SCHEDULE_DISABLED` (5002) — 收藏夹未启用调度
- `SCHEDULE_TRIGGER_ERROR` (5003) — 执行异常

#### `GET /api/v1/favorites/{folder_id}/schedule/status`
查询最近一次执行状态。

响应：
```json
{
  "code": "0000",
  "message": "OK.",
  "data": {
    "schedule_enabled": true,
    "schedule_cron": "0 3 * * *",
    "schedule_mode": "last_id",
    "last_scheduled_at": "2026-06-05T03:00:00",
    "last_schedule_status": "success",
    "last_schedule_stats": { ... }
  }
}
```

---

## 7. 前端设计

### 7.1 `FavoritePanel.vue` 弹窗扩展

在现有"创建/编辑收藏夹"表单中**新增一节"定时任务"**（使用 `el-collapse-item` 折叠，默认折叠避免干扰）：

```vue
<el-collapse v-model="activeSections">
  <el-collapse-item title="定时任务" name="schedule">
    <el-form-item label="启用调度">
      <el-switch v-model="form.schedule_enabled" />
    </el-form-item>
    <el-form-item label="Cron 表达式">
      <el-input
        v-model="form.schedule_cron"
        placeholder="如 '0 3 * * *' 表示每天凌晨 3 点"
        :disabled="!form.schedule_enabled"
      />
      <div class="form-tip">
        5 字段：分 时 日 月 周
        <a href="..." target="_blank">语法参考</a>
      </div>
    </el-form-item>
    <el-form-item label="拉取模式">
      <el-radio-group v-model="form.schedule_mode" :disabled="!form.schedule_enabled">
        <el-radio value="last_id">增量（到本地已下载的最大 ID 为止）</el-radio>
        <el-radio value="max">最大（循环到 API 最后一页）</el-radio>
      </el-radio-group>
    </el-form-item>
    <el-form-item label="单次最大下载数">
      <el-input-number
        v-model="form.schedule_max_images"
        :min="1"
        :max="10000"
        placeholder="留空使用全局默认值"
        :disabled="!form.schedule_enabled"
      />
    </el-form-item>
  </el-collapse-item>
</el-collapse>
```

### 7.2 收藏夹卡片状态展示

在每个 `folder-item` 内部（`folder-meta` 区域）增加调度状态徽标：

```vue
<div class="folder-meta">
  <span class="folder-count">{{ folder.local_count || 0 }} 张</span>
  <el-tag
    v-if="folder.schedule_enabled"
    :type="scheduleStatusType(folder.last_schedule_status)"
    size="small"
    effect="light"
  >
    <el-icon><Clock /></el-icon>
    {{ formatLastScheduled(folder.last_scheduled_at) }}
  </el-tag>
</div>
```

辅助函数：
- `scheduleStatusType(status)`: "success"→success, "failed"→danger, "running"→warning, null→info
- `formatLastScheduled(dt)`: 显示相对时间（"3 分钟前"、"刚刚"），超过 24h 显示日期

### 7.3 API 客户端 (`frontend/src/api/favorites.js`)

```javascript
// 新增
export const triggerFolderSchedule = (folderId) =>
  request.post(`/favorites/${folderId}/schedule/trigger`)

export const getFolderScheduleStatus = (folderId) =>
  request.get(`/favorites/${folderId}/schedule/status`)
```

---

## 8. 配置

### 8.1 `backend/config/config.yaml` 新增段

```yaml
scheduler:
  max_concurrent_schedules: 2
  max_images_per_run_default: 200
  max_pages_per_run: 5
```

### 8.2 `pyproject.toml` 新增依赖

```toml
dependencies = [
    # ... 现有依赖 ...
    "apscheduler>=3.10,<4.0",
]
```

---

## 9. 错误处理

### 9.1 错误分类

| 错误类型 | 触发场景 | 处理策略 | 用户感知 |
|---|---|---|---|
| yande_api 网络错误 | 连接失败 / 超时 | 记录到 `last_schedule_stats.errors[]`，中断本次抓取 | `last_schedule_status="failed"`，卡片红色徽标 |
| yande_api 限流（429） | 请求过于频繁 | sleep 60s 重试一次，仍失败则中断 | 日志告警 + 失败状态 |
| 数据库连接失败 | upsert 抛 SQLAlchemyError | 中断本次抓取，记录错误 | `last_schedule_status="failed"` |
| 单条 upsert 失败 | 某条图片数据脏数据 | try/except 包裹，记录错误后继续 | 不影响整体 |
| 下载任务创建失败 | DownloadService.create_task 抛异常 | try/except 包裹，记录错误后继续 | 不影响整体抓取 |
| scheduler 内部错误 | APScheduler 抛出 | logger.exception，不让 scheduler 崩溃 | 后端日志告警，下次触发继续 |
| cron 表达式非法 | 用户输入 "abc" | API 层 Pydantic + 启动时 `CronTrigger.from_crontab()` 验证，失败返回 `ErrMsg.SCHEDULE_INVALID_CRON` | API 400 错误 |

### 9.2 防御性设计

1. **抓取循环双层退出**：`page > max_pages` 或 `enqueued_count >= max_images` 或 `last_id 模式到达边界` — 任一命中即停止
2. **单条数据隔离**：每条 `upsert` / `create_task` 用 `try/except` 包裹
3. **scheduler 启动容错**：`reload_from_db()` 内每个收藏夹单独 try/except
4. **关闭时优雅停止**：`scheduler.shutdown(wait=False)`，正在执行的 job 允许完成
5. **重复触发去重**：使用 APScheduler 的 `coalesce=True, max_instances=1`，避免堆积

### 9.3 新增 ErrMsg

```python
# common/constant.py
SCHEDULE_INVALID_CRON = ("5001", "Invalid cron expression.", HTTPStatus.BAD_REQUEST)
SCHEDULE_DISABLED = ("5002", "Schedule is disabled for this folder.", HTTPStatus.BAD_REQUEST)
SCHEDULE_TRIGGER_ERROR = ("5003", "Failed to trigger schedule.", HTTPStatus.INTERNAL_SERVER_ERROR)
SCHEDULE_STATUS_NOT_FOUND = ("5404", "Schedule status not found.", HTTPStatus.NOT_FOUND)
```

---

## 10. 测试

### 10.1 单元测试 (`unit_test/test_favorite_scheduler.py`)

| 用例 | 验证点 |
|---|---|
| `test_run_folder_schedule_last_id_mode` | `last_id` 模式下，到达本地最大 ID 时停止 |
| `test_run_folder_schedule_max_mode` | `max` 模式下，循环到 API 最后一页 |
| `test_max_images_limit` | 命中 `max_images_per_run` 时立即停止 |
| `test_max_pages_limit` | 命中 `max_pages_per_run` 时停止 |
| `test_concurrent_folder_limit` | 同时触发 5 个收藏夹，仅 N 个并发抓取，其余排队 |
| `test_yande_api_failure` | yande_api 抛错时 `last_schedule_status="failed"`，stats 包含错误 |
| `test_partial_failure_isolation` | 单条 upsert 失败不影响其他条目 |
| `test_schedule_disabled_no_run` | `schedule_enabled=False` 时不执行 |
| `test_pagination_stops_on_empty` | 抓取到空页时停止循环 |
| `test_invalid_cron_at_register` | 非法 cron 在 `register_folder` 抛 `ErrMsg.SCHEDULE_INVALID_CRON` |

### 10.2 集成测试

| 用例 | 验证点 |
|---|---|
| `test_lifespan_reload_from_db` | 启动后从 DB 加载启用调度的收藏夹到 scheduler |
| `test_folder_update_re_registers` | 修改 cron 后，scheduler 中对应 job 被替换 |
| `test_folder_delete_unregisters` | 删除收藏夹时 scheduler 移除对应 job |
| `test_manual_trigger_api` | `POST /{id}/schedule/trigger` 同步执行并返回 stats |
| `test_cron_validation_api` | 非法 cron 表达式在 API 层返回 400 |

### 10.3 手动验收

1. 启动后端 + 前端
2. 创建收藏夹，tags 设为 `catgirl`，cron 设为 `* * * * *`（每分钟）
3. 等待 1-2 分钟，观察：
   - `last_scheduled_at` 持续更新
   - `last_schedule_status="success"`
   - `last_schedule_stats` 包含抓取数量
   - `Download.vue` 中出现新增的下载任务
4. 改为非法 cron `abc` → API 应返回 400
5. 删除收藏夹 → scheduler 中 job 消失（日志验证）

---

## 11. 风险与权衡

### 11.1 风险

| 风险 | 缓解 |
|---|---|
| yande.re API 限流 | `max_concurrent_schedules=2` + `max_pages_per_run=5` 兜底 |
| 数据库迁移失败 | 启动时 `Base.metadata.create_all()` 仅 ADD COLUMN，不会破坏现有数据；建议用户首次升级前备份 |
| 调度器与 FastAPI 生命周期不同步 | lifespan hook 严格管理启停，关闭用 `wait=False` 优雅退出 |
| `last_id` 模式对大量历史数据慢 | `last_id` 查询走 `YandeDataRepository` 的索引（已有 id 主键），毫秒级 |
| 重复触发堆积 | `coalesce=True, max_instances=1` |

### 11.2 权衡

- **APScheduler vs Celery**: 选择 APScheduler 因为本项目是单进程部署；Celery 需要 broker（Redis/RabbitMQ）成本不匹配。**未来多机部署时再迁移到 Celery**（README 远期计划）。
- **存 DB vs JobStore**: 选择存 `FavoriteFolder` 表，**单一数据源**，与现有架构一致；JobStore 引入额外表和序列化层，收益不匹配复杂度。
- **同步触发 API vs 异步**: 选择同步触发（`POST /trigger`），让用户立即看到结果便于调试。生产环境不推荐频繁调用。

---

## 12. 后续工作（不在本范围内）

- 调度历史的多月统计与可视化图表
- 多机部署的 Celery 迁移
- 调度失败重试策略（指数退避）
- 邮件/通知推送

---

## 13. 验收清单

- [ ] 所有 Pydantic 模型有返回类型注解
- [ ] 所有 API 路由遵循 `BaseResponse` + `APIException(ErrMsg.XXX, e=e)` 模式
- [ ] 新增字段无破坏性迁移
- [ ] 单元测试覆盖率 ≥ 80%
- [ ] 手动验收 5 步骤全部通过
- [ ] README「开发计划」勾选此功能
- [ ] 文档更新（`docs/structure.md` / `docs/api-route.md` 如有必要）
