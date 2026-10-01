# 最近下载功能 — 设计文档

**状态**：已定稿（用户确认）
**日期**：2026-09-21
**类型**：新功能（收藏夹第三个虚拟磁贴）
**前置**：「我的最爱」「随机浏览」已完成（见 [2026-09-20-my-favorites-and-random-browse-v2-design.md](2026-09-20-my-favorites-and-random-browse-v2-design.md)）

---

## 1. 目标

在收藏夹磁贴列表末尾新增第三个虚拟磁贴「最近下载」，按**下载完成时间倒序**浏览本地已下载图片，支持配置总开关与记录清除。

### 1.1 范围内

| 模块 | 范围 |
|---|---|
| 后端 DAO | `download_task_dao` 新增 4 个方法（列表/计数/按时间删/全删） |
| 后端 Service | `DownloadService` 新增对应方法 |
| 后端 API | 新增 `/api/v1/recent_downloads/{count,preview,clear}` |
| 后端排序 | `services/gallery.py` 新增「最近下载」排序分支 |
| 后端配置 | `FavoritesConfig` 新增 `enable_recent_downloads` |
| 前端 | 第三个虚拟磁贴 + 二级页 + 清除按钮组 + Config 开关 |

### 1.2 不在范围内（YAGNI）

- ❌ 不改数据库表结构（不加 `downloaded_at` 字段）
- ❌ 不做时间范围筛选（本期不做 `since` 参数）
- ❌ 不做自动过期清理（只做手动清除）
- ❌ 不动 `api/v1/download.py` 与 `Download.vue`
- ❌ 不动 `download_queue.py`（含 `completed_at` NULL 缺陷，本期不修）
- ❌ 不动 `get_folders_with_preview`

---

## 2. 核心决策

### 2.1 数据源：`download_task` JOIN `yande_data`（不改表结构）

**背景**：`YandeData` 表**没有**下载时间字段，只有 `down_flag`(bool)。
`created_at`/`updated_at` 是 **yande.re 图源的上传/更新时间**（API 同步而来），与本地下载时间无关 —— `update_down_flag`（`yande_data_dao.py:318`）刻意不更新 `updated_at`。

**选定方案**：复用 `download_task` 表的 `completed_at`。

**筛选条件**（三者缺一不可）：

```sql
dt.status = 'completed'          -- 排除 pending/downloading/paused/failed/cancelled
AND dt.completed_at IS NOT NULL -- 排除「已存在跳过下载」分支产生的 NULL
```

**去重**：同一图片可能有多条 completed 任务（重复下载）→ `GROUP BY image_id` 取 `MAX(completed_at)`。

**已知取舍**（必须写入文档与 OpenAPI 注释）：
1. 用户删除任务记录 → 该图从「最近下载」消失，但**图片文件仍在磁盘**，`down_flag` 不变
2. 清除记录同时清空下载管理页的「已完成」历史（共用数据，用户已确认接受）
3. 重复下载的任务 `completed_at` 为 NULL（`download_queue.py:472` 跳过分支未写该字段）→ 沉底，用户已确认接受
4. 清除**只删任务日志，不删图片文件**

### 2.2 磁贴顺序

**我的最爱 → 随机浏览 → 最近下载**（最近下载放**最后**，用户指定）

在 `useFavoriteFoldersList.js` 的 `virtualTiles` computed 中，push 到数组**末尾**（现有两个的相对顺序不变）。

### 2.3 角标口径

`COUNT(DISTINCT image_id)` —— **不是** `COUNT(*)`，避免重复下载导致数字虚高。
（对比：`randomBrowseCount` = `count_downloaded()` = `yande_data` 表 down_flag=True 总数，两者口径不同，不会再撞数字。）

### 2.4 清除机制

二级页顶部两个按钮，**均需二次确认**：

| 按钮 | API 参数 | 行为 |
|---|---|---|
| 清除 N 天前记录（N=7/30/90） | `{"mode": "before_days", "days": 30}` | 删 `completed_at < now - N days` 且 status=completed |
| 清空全部记录 | `{"mode": "all"}` | 删全部 status=completed 且 completed_at 非空的记录 |

**安全红线（必须实现）**：清除**只允许** `status == COMPLETED`。
**绝不**删除 `pending` / `downloading` / `paused` / `failed` / `cancelled` 记录。

---

## 3. 后端契约

### 3.1 DAO：`backend/src/dao/download_task_dao.py`

```python
def list_completed_image_ids(self, page: int, page_size: int) -> List[Tuple[int, datetime]]:
    """分页返回已完成任务的 image_id + MAX(completed_at)，按 MAX(completed_at) DESC。

    Returns: [(image_id, latest_completed_at), ...]
    """

def count_completed_distinct_images(self) -> int:
    """COUNT(DISTINCT image_id)，口径与 list_completed_image_ids 对齐。"""

def delete_completed_before(self, cutoff: datetime) -> int:
    """删除 completed_at < cutoff 且 status=completed 的记录。返回删除条数。"""

def delete_all_completed(self) -> int:
    """删除全部 status=completed 且 completed_at IS NOT NULL 的记录。返回删除条数。"""
```

### 3.2 Service：`backend/src/services/download.py`

```python
@staticmethod
def delete_completed_records(days: Optional[int] = None) -> int:
    """days=None → 全清；days=N → 清除 N 天前。内部走 download_task_dao。"""
```

> **注意**：DAO 是同步 DB 调用，API 层需 `await asyncio.to_thread(...)` 包装
> （与现有 `delete_download_task` 的 `asyncio.to_thread(DownloadService.delete_task, ...)` 一致）。

### 3.3 API：新建 `backend/src/api/v1/recent_downloads.py`

对齐 `api/v1/random_browse.py` 的范式（响应模型复用 `MyFavoriteCountResponse` /
`MyFavoritePreviewImage` / `MyFavoritePreviewResponse`，前端 `FolderTile` 可直接复用渲染）。

| 方法 | 路由 | 参数 | 响应 |
|---|---|---|---|
| GET | `/recent_downloads/count` | — | `BaseResponse[MyFavoriteCountResponse]` |
| GET | `/recent_downloads/preview` | `limit`(1-20, 默认8), `tile_size` | `BaseResponse[MyFavoritePreviewResponse]` |
| POST | `/recent_downloads/clear` | body: `ClearRecordsRequest` | `BaseResponse[ClearRecordsResponse]` |

请求/响应模型（新建 `backend/src/models/request/recent_downloads.py` 与
`backend/src/models/response/recent_downloads.py`）：

```python
class ClearRecordsRequest(BaseModel):
    mode: Literal["before_days", "all"]
    days: Optional[int] = Field(default=None, ge=1, le=3650,
                                description="mode=before_days 时必填：清除 N 天前的记录")

class ClearRecordsResponse(BaseModel):
    deleted: int = Field(..., ge=0, description="删除的记录条数")
```

**校验**：`mode="before_days"` 时 `days` 为 None → 抛 `ValueError` → `APIException`。

### 3.4 排序分支：`backend/src/services/gallery.py`

在 `query_local_database` / `load_images` 链路新增 `sort_by="downloaded_at"` 支持。
`SortBy` 枚举（`yande_data_dao.py:37`）新增：

```python
DOWNLOADED_AT = "downloaded_at"
```

排序实现：在 `_query_local_with_options` 中，当 `sort_by == "downloaded_at"` 时
改用 **子查询 + JOIN** 而非简单 `getattr(YandeData, sort_by)`：

```sql
SELECT yande_data.* FROM yande_data
JOIN (
    SELECT image_id, MAX(completed_at) AS t FROM download_task
    WHERE status='completed' AND completed_at IS NOT NULL
    GROUP BY image_id
) latest ON latest.image_id = yande_data.id
ORDER BY latest.t DESC
```

> ⚠️ **不可**用 `getattr(YandeData, "downloaded_at", ...)` —— 该列不存在。
> 需在 `GalleryService` 中单独分支处理，且 count 语句同样要 JOIN 后再 count。
> 保留其余 filter_funcs（tags/rating/分辨率等）以继承筛选能力。

### 3.5 配置：`backend/src/common/settings.py`

```python
enable_recent_downloads: bool = Field(
    default=False, description="最近下载功能总开关"
)
```

`Config.update_config()` 通过 `isinstance` 自动适配，**无需修改**。

---

## 4. 前端契约

### 4.1 `frontend/src/composables/useFavoritesConfig.js`

新增（照搬 `randomBrowseCount` 模式）：
- `enableRecentDownloads: ref(false)` — 从 `/config/favorites` 的 `enable_recent_downloads` 读取
- `recentDownloadsCount: ref(0)`
- `fetchRecentDownloadsCount()` — 导出函数，调 `/recent_downloads/count`
- `clearRecentDownloads(payload)` — 导出函数，调 `/recent_downloads/clear`，成功后重刷角标
- `saveFavoritesConfig` 中：若 updates 含 `enable_recent_downloads` 且为 true → 拉取角标

### 4.2 `frontend/src/api/recentDownloads.js`（新建）

```js
export const recentDownloadsApi = {
  getCount(),        // GET /recent_downloads/count
  getPreview(limit), // GET /recent_downloads/preview?limit=N
  clear(payload),    // POST /recent_downloads/clear
}
```

### 4.3 `frontend/src/composables/useFavoriteFoldersList.js`

- 解构新增 `enableRecentDownloads` / `recentDownloadsCount`
- `virtualTiles` 中 **push 到末尾**：
  ```js
  { id: 'recent-downloads', name: '最近下载', isVirtual: true,
    local_count: recentDownloadsCount.value, preview_images: recentDownloadsPreview.value }
  ```
- 新增 `recentDownloadsPreview` ref + `loadRecentDownloadsPreview()`（同 `randomBrowsePreview` 模式）
- watch 依赖数组加入 `enableRecentDownloads`；开关关闭时清空预览

### 4.4 `frontend/src/components/FavoritePanel.vue`

`handleVirtualTileClick` 增加分支：
```js
} else if (tile.id === 'recent-downloads') {
  emit('virtual-tile-navigate', 'recent-downloads')
}
```

### 4.5 `frontend/src/views/Gallery.vue`

- `VIRTUAL_FAVORITES` 增加 `'recent-downloads': { id: 'recent-downloads', name: '最近下载' }`
- `loadImages` 中：`querySource === 'recent-downloads'` 时注入
  `sort_by: 'downloaded_at', sort_order: 'desc'`，且 `source` 映射为 `'local'`
  （后端 source 不认识 'recent-downloads'，同 'random' 的处理方式）
- 清除按钮组放在二级页顶部，仅 `querySource === 'recent-downloads'` 时渲染

### 4.6 `frontend/src/views/Config.vue`

新增开关 `enable_recent_downloads`，放在 `enable_random_browse` 之后。

---

## 5. 测试要点

### 后端
| 模块 | 用例 |
|---|---|
| DAO | `list_completed_image_ids` 按 MAX(completed_at) DESC；同图多任务只返回一条；排除 NULL completed_at；排除非 completed 状态 |
| DAO | `count_completed_distinct_images` 去重计数正确 |
| DAO | `delete_completed_before` 只删过期 completed，**不碰** pending/downloading/failed |
| DAO | `delete_all_completed` **不删**非 completed 记录（安全红线回归测试） |
| Service | `delete_completed_records(days=None)` 全清；`days=30` 按时间清 |
| API | `/clear` mode 非法值 → 422；`before_days` 缺 days → 抛 APIException |
| Gallery | `sort_by=downloaded_at` 排序正确；`enable_recent_downloads=false` 时前端不注入 |
| 回归 | `get_folders_with_preview` 行为完全不变（**不注入**虚拟 folder） |

### 前端
| 模块 | 用例 |
|---|---|
| `useFavoriteFoldersList` | 三个开关各自控制磁贴出现；顺序为 我的最爱→随机浏览→最近下载 |
| `useFavoritesConfig` | `enable_recent_downloads` 读取；`saveFavoritesConfig` 后拉角标 |
| `Gallery.vue` | `querySource='recent-downloads'` 注入 `sort_by=downloaded_at` |
| 清除按钮 | 二次确认弹窗；成功后角标刷新为 0 |

---

## 6. 兼容性

| 场景 | 行为 |
|---|---|
| 存量用户 `config.yaml` 无 `enable_recent_downloads` | Pydantic 默认 False，磁贴不显示 |
| `downloaded_at` 排序下 NULL | 子查询已 `completed_at IS NOT NULL` 过滤，无 NULL |
| 开关关闭 | 磁贴不显示；`/recent_downloads/*` 接口仍可用（只控 UI） |
| 清除后 | 角标归 0；已下载图片仍在随机浏览/本地图库中 |

---

*最后更新：2026-09-21（已定稿，待实现）*
