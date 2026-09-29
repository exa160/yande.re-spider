# 我的最爱 + 随机浏览功能 — 设计文档

**状态**：Draft（待用户审阅）
**日期**：2026-09-19
**分支**：`feature/my-favorites-and-random`（基于当前 `next_dev`）
**类型**：新功能（双模块：图片级收藏 + 本地随机浏览）+ 配置中心化重构

---

## 1. 目标

在现有收藏夹体系（按 tags 订阅）之上，新增两个独立功能：

1. **我的最爱**：图片级别的标记能力 —— 所有图片右下角展示爱心组件，点击后变为实心并把图片信息加入我的最爱；同时支持配置总开关与「收藏夹页置顶」展示，并具备「非本地图片加入即自动下载」能力。
2. **随机浏览**：从本地已下载图片中随机抽样浏览，支持配置总开关。

同时按用户要求，**将现有 localStorage 持久化的 5 个收藏夹 UI 偏好（buttonMode / tileSize / previewOrder / includeOnline / folderPageSize）迁移到后端 config.yaml**，新增 `favorites` section，并补充 2 个新功能开关。

### 1.1 范围内

| 模块 | 范围 |
|------|------|
| 后端数据 | 新增 `my_favorite` 中间表（含迁移脚本） |
| 后端服务 | 新增 `MyFavoritesService` / `RandomBrowseService`，扩 `ConfigService` |
| 后端 API | 新增 `/api/v1/my-favorites/*`、`/api/v1/random`、`/api/v1/config/favorites` |
| 后端配置 | 新增 `FavoritesConfig` Pydantic 模型，挂到 `Config.favorites` |
| 前端组件 | 新增 `HeartOverlay.vue`、`RandomBrowser.vue`（Dialog）；扩 `FolderTile.vue`、`WaterfallGallery.vue`、`AdvancedQuery.vue`、`Config.vue` |
| 前端状态 | `useFavoritesConfig.js` 重构：localStorage → 后端 `GET/PUT /config/favorites` |
| 自动下载 | 加入我的最爱时，若图片未下载（`down_flag=False`）即推送 `DownloadTask` |

### 1.2 不在范围内（YAGNI）

- 在线随机（仅本地随机）
- 后台扫描器自动补抓（采用「加入即触发」即可，避免与现有 Scheduler 重复）
- 我的最爱导入 / 导出 / 分享 / 标签 / 备注 UI（`note` 字段先预留，不上 UI）
- 我的最爱跨设备同步
- 收藏夹的拖拽排序界面改造（已有，本次不碰）
- 我的最爱图片分组 / 标签管理（先做扁平列表）
- 收藏夹配置之外的其他 UI 偏好迁移（仅迁这 5 项）

---

## 2. 背景与现状

### 2.1 现有收藏夹体系

`FavoriteFolder` 表是「按 tags 批量订阅」语义，用户订阅的是「标签条件」（如 `rating:s score:>100`），系统按 tags 拉图入库。用户**不能针对单张图片表达「我特别喜欢这张」** —— 现有 1.2.0 计划的「我的最爱」在多个 TODO 注释中已被预留：

| 位置 | 现有注释 |
|------|----------|
| `services/favorites.py:85` | `include_online: True 时预览图同时包含未下载的在线图片（未来「我的最爱」支持收藏未下载图时启用）` |
| `api/v1/favorites.py:172` | `# TODO: 后续「我的最爱」功能会用到此接口（单 folder 全量预览）` |

本设计正是兑现这两处预留。

### 2.2 现有收藏夹 UI 配置分散在 localStorage

`frontend/src/composables/useFavoritesConfig.js` 当前用 5 个 localStorage key 持久化：

```
gallery_favorites_button_mode      : 'hidden' | 'shown' | 'default'
gallery_favorites_tile_size        : 'adaptive' | '4' | '6' | '8'
gallery_favorites_preview_order    : 'random' | 'asc' | 'desc'
gallery_favorites_include_online   : 'true' | 'false'
favorites_folder_page_size         : '8' | '12' | '20'
```

**问题**：
- 配置分散（一些在 localStorage，一些在 yaml），不在 Config.vue 中统一管理
- 后端无法参与联动（如根据开关决定是否插入「我的最爱」虚拟 folder）
- 多端同步靠运气

### 2.3 现有收藏夹接口扩展点

`/api/v1/favorites/with-preview` 已支持 `include_online` 参数 + `tile_size` 4 档 + `preview_order` 3 模式，可直接复用其 `preview_images` 渲染管线（仅本地路径，无需修改）。

`FavoriteFolder` 表完全不动，本设计与现有收藏夹**互不污染**。

### 2.4 现有下载服务入口

`backend/src/services/download.py:DownloadService.create_task(image_id)`：

```python
async def create_task(image_id: int) -> str:
    with YandeDataRepository() as repo:
        yande_data = repo.get_by_id(image_id)
    if not yande_data:
        raise ValueError(f"Image {image_id} not found in database")
    task_id = str(uuid.uuid4())
    task_store.create_task(task_id, yande_data)
    await download_queue.add_task(task_id)
    return task_id
```

加入我的最爱时复用此入口即可，**不引入新下载基础设施**。

---

## 3. 数据模型

### 3.1 新增表 `my_favorite`

新建 `backend/src/models/database/my_favorite.py`：

```python
class MyFavorite(Base):
    """我的最爱 - 图片级标记（与 FavoriteFolder 互不污染）"""
    __tablename__ = table_constant.my_favorite

    id = Column(Integer, primary_key=True, autoincrement=True)
    image_id = Column(Integer, nullable=False, comment="yande 图片 ID")
    created_at = Column(DateTime, default=datetime.now, comment="收藏时间")
    note = Column(String(255), nullable=True, comment="预留备注字段")
```

**关键决策**：

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 主键 | 自增 `id` | 便于分页 / 按收藏时间排序 |
| 与 YandeData 关系 | `UNIQUE(image_id)` 约束，**不加 FK** | 与项目现有约定一致（`FavoriteFolder` 也不加 FK） |
| `note` 字段 | 预留，本期不上 UI | 扩展性强、零成本 |
| 索引 | `UNIQUE(image_id)` + `INDEX(created_at DESC)` | 加我的最爱幂等、按时间倒序列表 |
| 软删除 | 不做（直接 `DELETE`） | YandeData 主表已有完整元数据，删除我的最爱不会丢失图片信息 |

### 3.2 `table_constant` 新增条目

```python
# backend/src/common/constant.py (扩展)
my_favorite: str = "my_favorite"
```

### 3.3 数据库迁移脚本

新建 `backend/migrations/versions/xxxx_add_my_favorite.py`（沿用现有 Alembic / SQL 脚本约定，需复核项目实际迁移工具）：

```sql
CREATE TABLE my_favorite (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    note VARCHAR(255),
    UNIQUE(image_id)
);
CREATE INDEX idx_my_favorite_created_at ON my_favorite (created_at DESC);
```

> 注：项目若使用 SQLite，开发模式自动建表（沿用 `Base.metadata.create_all`）；若用 MariaDB / MySQL，需用户提供迁移路径。本次设计默认 SQLite 自动建表，MariaDB 由用户在升级时执行迁移脚本。

---

## 4. 后端配置

### 4.1 新增 `FavoritesConfig` 模型

`backend/src/common/settings.py` 新增：

```python
class FavoritesConfig(ConfigModel):
    """收藏夹 UI 配置 + 我的最爱/随机浏览总开关（从 localStorage 迁移）"""

    # 从前端 localStorage 迁过来的 5 个 UI 偏好
    button_mode: str = Field("shown", description="主页收藏夹按钮显示模式: hidden | shown | default")
    tile_size: str = Field("adaptive", description="收藏夹 tile 大小: adaptive | 4 | 6 | 8")
    preview_order: str = Field("random", description="预览图排序: random | asc | desc")
    include_online: bool = Field(False, description="预览是否包含未下载图片")
    folder_page_size: int = Field(20, description="收藏夹一级每页条数: 8 | 12 | 20")

    # 新功能总开关
    my_favorites_enabled: bool = Field(True, description="我的最爱功能总开关")
    random_browse_enabled: bool = Field(True, description="随机浏览功能总开关")

    @field_validator("button_mode")
    @classmethod
    def _validate_button_mode(cls, v):
        if v not in ("hidden", "shown", "default"):
            raise ValueError("button_mode must be 'hidden' | 'shown' | 'default'")
        return v

    @field_validator("tile_size")
    @classmethod
    def _validate_tile_size(cls, v):
        if v not in ("adaptive", "4", "6", "8"):
            raise ValueError("tile_size must be 'adaptive' | '4' | '6' | '8'")
        return v

    @field_validator("preview_order")
    @classmethod
    def _validate_preview_order(cls, v):
        if v not in ("random", "asc", "desc"):
            raise ValueError("preview_order must be 'random' | 'asc' | 'desc'")
        return v

    @field_validator("folder_page_size")
    @classmethod
    def _validate_folder_page_size(cls, v):
        if v not in (8, 12, 20):
            raise ValueError("folder_page_size must be 8 | 12 | 20")
        return v
```

### 4.2 `Config` 类挂载

```python
class Config(ConfigModel):
    app: AppConfig = AppConfig()
    database: DatabaseConfig = DatabaseConfig()
    yande_api: ApiConfig = ApiConfig()
    downloader: DownloaderConfig = DownloaderConfig()
    scheduler: SchedulerConfig = SchedulerConfig()
    favorites: FavoritesConfig = FavoritesConfig()   # 新增
```

`Config.update_config()` 已通过 `isinstance` 自动适配新 section，**无需修改**。

### 4.3 `ConfigService` 新增方法

`backend/src/services/config.py` 新增：

```python
def get_favorites_config() -> FavoritesConfig:
    return config.favorites

def update_favorites_config(favorites_config: FavoritesConfig) -> bool:
    config.update_config(favorites_config)
    return True
```

### 4.4 API 端点

`backend/src/api/v1/config.py` 新增：

```python
@router.get("/favorites", response_model=BaseResponse[FavoritesConfig], summary="获取收藏夹配置")
async def get_favorites_config() -> BaseResponse[FavoritesConfig]:
    return BaseResponse(message=ErrMsg.OK.msg, data=ConfigService.get_favorites_config())

@router.put("/favorites", response_model=BaseResponse, summary="更新收藏夹配置")
async def update_favorites_config(favorites_config: FavoritesConfig) -> BaseResponse:
    success = ConfigService.update_favorites_config(favorites_config)
    if not success:
        raise APIException(ErrMsg.CONFIG_UPDATE_ERROR)
    return BaseResponse(message=ErrMsg.CONFIG_UPDATE_SUCCESS)
```

`ResetConfig` 模型扩展可选值：

```python
class ResetConfig(BaseModel):
    section: Literal['api', 'downloader', 'database', 'favorites'] = Field(...)
```

---

## 5. 后端 API

### 5.1 `/api/v1/my-favorites/*`

新建 `backend/src/api/v1/my_favorites.py`：

| 方法 | 路由 | 用途 | 响应模型 |
|------|------|------|----------|
| GET | `/my-favorites` | 分页列出（按 created_at DESC） | `MyFavoritesListResponse` |
| GET | `/my-favorites` | 分页列出我的最爱记录（含 image_id / created_at） | `MyFavoritesListResponse` |
| GET | `/my-favorites/ids` | 返回所有 image_id 集合 —— ⚠️ **仅供特殊场景**：数据迁移、批量导入、修复工具、跨设备同步等；正常浏览请用主接口的 `include_favorite_status=true` JOIN 实现 | `MyFavoriteIdsResponse` |
| POST | `/my-favorites/{image_id}` | 加入我的最爱（幂等；未下载则触发下载） | `BaseResponse` |
| DELETE | `/my-favorites/{image_id}` | 取消我的最爱（幂等） | `BaseResponse` |
| POST | `/my-favorites/check` | 批量查询 `image_ids` 中哪些已收藏 —— ⚠️ **仅供特殊场景**：同上，正常浏览请用主接口 JOIN | `MyFavoriteCheckResponse` |
| GET | `/my-favorites/count` | 总数（用于收藏夹列表置顶的磁贴角标） | `MyFavoriteCountResponse` |

#### 5.1.1 加入时自动下载

```python
@router.post("/{image_id}", response_model=BaseResponse, summary="加入我的最爱")
async def add_my_favorite(image_id: int) -> BaseResponse:
    """加入我的最爱。幂等（UNIQUE image_id 兜底）。
    若图片未下载（down_flag=False），异步触发下载任务。"""
    try:
        await MyFavoritesService.add(image_id)
        return BaseResponse(message="已加入我的最爱")
    except ValueError as e:
        raise APIException(ErrMsg.NOT_FOUND, data={"detail": str(e)})
    except Exception as e:
        raise APIException(ErrMsg.CREATE_ERROR, e=e)
```

`MyFavoritesService.add` 编排：

```python
@staticmethod
async def add(image_id: int) -> None:
    """加入我的最爱；未下载时异步触发下载。"""
    with YandeDataRepository() as repo:
        yande_data = repo.get_by_id(image_id)
    if not yande_data:
        raise ValueError(f"Image {image_id} not found in database")

    # 1) 写入 my_favorite（UNIQUE 约束保证幂等）
    my_favorite_dao.add(image_id=image_id)

    # 2) 未下载则异步触发下载（复用现有 DownloadService.create_task）
    if not yande_data.down_flag:
        try:
            await DownloadService.create_task(image_id)
            logger.info(f"My favorite auto-download triggered for {image_id}")
        except Exception as e:
            # 下载触发失败不影响收藏已成功（用户视角：先收藏，下载后续补）
            logger.warning(f"Auto-download failed for {image_id}: {e}")
```

### 5.2 `/api/v1/random`

新建 `backend/src/api/v1/random.py`：

| 方法 | 路由 | 用途 |
|------|------|------|
| GET | `/random` | 本地随机浏览图片（可带 tags 过滤） |

```python
@router.get("", response_model=BaseResponse[list[YandeData]], summary="本地随机浏览")
async def get_random_images(
    limit: int = Query(20, ge=1, le=100, description="返回图片数"),
    tags: str = Query("", description="可选 tag 过滤（同 favorite.tags 语法）"),
    include_favorite_status: bool = Query(
        False,
        description="True 时响应中每个图片附带 is_favorited 字段（LEFT JOIN my_favorite 实现）；前端在 my_favorites_enabled=true 时自动传 True",
    ),
) -> BaseResponse[list[YandeData]]:
    """从本地 YandeData（down_flag=True）中随机抽样。
    tags 非空时按 _parse_tags_to_params 复用 FavoriteFolder 的解析逻辑。
    include_favorite_status=True 时走 LEFT JOIN，性能损耗 < 5ms（my_favorite 唯一索引命中）。
    """
    try:
        images = RandomBrowseService.get_random(limit=limit, tags=tags)
        return BaseResponse(message=ErrMsg.OK.msg, data=images)
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)
```

`RandomBrowseService` 用 SQL `ORDER BY RANDOM() LIMIT N` 实现，简单粗暴（数据集小，YandeData 通常 < 10w 行，性能可接受）；返回完整 `YandeData` 字段供前端直接渲染。

### 5.3 「我的最爱」置顶注入到收藏夹列表

**关键设计**：**不在前端合并**（避免前端拿不到总数 / 预览图），而是在 `FavoritesService.get_folders_with_preview` 中**总是**返回的列表最前面**插入**一个虚拟 folder 字典：

```python
# services/favorites.py:get_folders_with_preview 末尾追加
if config.favorites.my_favorites_enabled:
    fav_count = my_favorite_dao.count()
    fav_preview_meta = my_favorite_dao.get_preview_meta(limit=_preview_count_for_local_count(fav_count, tile_size))
    virtual_folder = FavoriteFolderWithMinimalPreview(
        id=-1,                                  # 特殊 ID，前端识别用
        name="我的最爱",
        tags="",
        color="#F56C6C",                        # 红色主题
        icon="star",
        sort_order=-1,                          # 强制置顶
        local_count=fav_count,
        online_count=0,
        preview_images=fav_preview_meta,
        is_system=True,                         # 标识为系统内置
    )
    items.insert(0, virtual_folder)
```

前端 FolderTile 看到 `id === -1` 时：
- 点击进入 `favoritesView='folder-detail'`，但 `querySource='my-favorites'`（新增第三态）
- 长按不弹出编辑菜单（`is_system=True` 短路）

`is_system` 字段需要扩展 `FavoriteFolder` 表 + `FavoriteFolderBase` 响应模型（迁移成本低，仅一列）。

### 5.4 「我的最爱」详情页（瀑布流）

新增 `GET /my-favorites/images`：

```python
@router.get("/images", response_model=YandeDataListResponse, summary="获取我的最爱图片列表")
async def list_my_favorite_images(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> YandeDataListResponse:
    """分页返回我的最爱图片（按 created_at DESC JOIN yande_data）。"""
    images, total = MyFavoritesService.list_paginated(page=page, page_size=page_size)
    return YandeDataListResponse(total=total, page=page, page_size=page_size, data=images)
```

前端 `Gallery.vue` 增加第三种 `querySource === 'my-favorites'` 模式，复用现有 `WaterfallGallery`，瀑布流加载走 `/my-favorites/images` 而非 `/gallery/load`。

### 5.5 主接口 JOIN 策略：`is_favorited` 字段

**核心原则**：所有「会返回多张图片」的主列表接口，在请求中新增 `include_favorite_status: bool = False` 参数。当客户端传 `True` 时，服务端通过 `LEFT JOIN my_favorite` 把每张图片的「是否我的最爱」直接附加到响应里，**避免额外的批量 check 调用**。

#### 5.5.1 受影响的接口

| 接口 | 是否支持 | 备注 |
|------|----------|------|
| `GET /api/v1/gallery/load`（瀑布流主入口） | ✅ **核心** | 前端进入画廊模式默认传 `True` |
| `GET /api/v1/favorites/{folder_id}/preview` | ✅ | 收藏夹详情页瀑布流 |
| `GET /api/v1/random`（随机浏览） | ✅ | 见 5.2 |
| `GET /api/v1/my-favorites/images` | ❌ 不需要 | 全是我的最爱，`is_favorited` 恒为 `True`，无意义 |
| `POST /api/v1/my-favorites/check` | ⚠️ 仅特殊场景 | 见 5.1（数据迁移、批量导入、修复工具） |

> 注：当前 spec 主要示例是 `/random`，其他主列表接口（如 `/gallery/load`）按完全相同的模式扩展。

#### 5.5.2 前端触发逻辑

```js
// 统一的请求辅助函数（建议封装在 api/index.js）
function loadGalleryImages(params) {
  return api.get('/gallery/load', {
    params: {
      ...params,
      // 关键：仅当我的最爱功能开启时才请求 is_favorited
      include_favorite_status: myFavoritesEnabled.value,
    }
  })
}
```

`myFavoritesEnabled` 来自 `useFavoritesConfig().myFavoritesEnabled`（已迁移到后端配置）。关闭时前端**根本不发**这个参数，**服务端不会产生任何 JOIN 开销**。

#### 5.5.3 SQL 实现

```sql
-- 普通模式（include_favorite_status=False）
SELECT * FROM yande_data WHERE ... ORDER BY ... LIMIT N;

-- 我的最爱模式（include_favorite_status=True）
SELECT
  yande_data.*,
  CASE WHEN my_favorite.id IS NOT NULL THEN 1 ELSE 0 END AS is_favorited
FROM yande_data
LEFT JOIN my_favorite ON my_favorite.image_id = yande_data.id
WHERE ...
ORDER BY ... LIMIT N;
```

**性能**：my_favorite 的 `image_id` 已有 UNIQUE 索引（见 3.1），LEFT JOIN 走索引查找，单次查询 < 5ms 损耗，可接受。

#### 5.5.4 响应模型扩展

`YandeData` 响应模型新增可选字段：

```python
class YandeData(BaseModel):
    # ... 现有字段 ...
    is_favorited: Optional[bool] = Field(
        default=None,
        description="是否已加入我的最爱；仅 include_favorite_status=True 时返回；None 表示未请求",
    )
```

**为何 Optional[bool] 而非 bool**：
- `include_favorite_status=False` 时字段为 `None`（明确语义：未查询）
- `include_favorite_status=True` 时字段为 `True`/`False`（明确语义：已查询）
- 前端用 `img.is_favorited === true` 即可判断是否已收藏，无需关心 `None`（`None !== true`）

#### 5.5.5 HeartOverlay 切换收藏时的本地更新

加入 / 取消我的最爱时，前端**不重新请求整页**，而是乐观更新：

```js
// WaterfallGallery.vue
async function handleFavoriteChanged({ imageId, favorited }) {
  // 1. 乐观更新本地列表（立刻反映 UI）
  const img = images.value.find(i => i.id === imageId)
  if (img) img.is_favorited = favorited
  // 2. 后端已保证持久化；失败回滚由 HeartOverlay 内部 toast 处理
}
```

后端 `POST /my-favorites/{id}` 与 `DELETE /my-favorites/{id}` 不需要任何响应体调整 —— **这两个接口本身已是权威数据源**。

#### 5.5.6 为什么 `/my-favorites/check` 仍保留

虽然 JOIN 方案在 99% 的场景下完全替代 `/check`，但以下场景需要它：

1. **数据迁移 / 导入**：批量比对「这些图片哪些已在我的最爱」
2. **离线同步**：客户端缓存了收藏状态，需要与服务端对账
3. **修复工具**：发现数据异常时批量校准
4. **未来跨设备同步**：上传本地收藏列表时与服务端比对

所以 `/check` 接口保留为「**特殊场景专用**」，文档与 OpenAPI summary 中明确标注，正常业务路径不调用。

---

## 6. 前端

### 6.1 文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `frontend/src/components/HeartOverlay.vue` | 新增 | 通用爱心按钮（空心 / 实心，hover 动画） |
| `frontend/src/components/RandomBrowser.vue` | 新增 | 随机浏览 Dialog（卡片式瀑布流 + 翻页按钮） |
| `frontend/src/components/WaterfallGallery.vue` | 修改 | props 新增 `showHeart` + `@favorite-toggled` 事件 |
| `frontend/src/components/FolderTile.vue` | 修改 | 识别 `id=-1` 渲染「我的最爱」虚拟磁贴 |
| `frontend/src/views/Gallery.vue` | 修改 | 增加 `querySource='my-favorites'` 第三态 |
| `frontend/src/views/Config.vue` | 修改 | 高级 tab 新增「收藏夹 + 我的最爱 + 随机浏览」section |
| `frontend/src/composables/useFavoritesConfig.js` | 重构 | localStorage → `GET/PUT /config/favorites` |
| `frontend/src/api/myFavorites.js` | 新增 | `add`, `remove`（**主路径**）；`checkBatch`, `listIds`（⚠️ 仅特殊场景：数据迁移、修复工具，不在正常浏览路径使用） |
| `frontend/src/api/random.js` | 新增 | `getRandom(limit, tags)` |
| `frontend/src/api/favorites.js` | 修改 | 已有 `getFoldersWithPreview` 等不动；新增 `getMyFavoritesImages` |

### 6.2 `HeartOverlay.vue`

```vue
<template>
  <button
    v-if="enabled"
    class="heart-overlay"
    :class="{ active: isFavorited, loading }"
    @click.stop.prevent="toggle"
    :aria-label="isFavorited ? '取消我的最爱' : '加入我的最爱'"
  >
    <el-icon><Star v-if="isFavorited" /><StarFilled v-else /></el-icon>
  </button>
</template>

<script setup>
import { Star, StarFilled } from '@element-plus/icons-vue'
import { ref } from 'vue'
import { myFavoritesApi } from '@/api/myFavorites'

const props = defineProps({
  imageId: { type: Number, required: true },
  initialFavorited: { type: Boolean, default: false },
  enabled: { type: Boolean, default: true },
})
const emit = defineEmits(['changed'])

const isFavorited = ref(props.initialFavorited)
const loading = ref(false)

async function toggle() {
  if (loading.value) return
  loading.value = true
  try {
    if (isFavorited.value) {
      await myFavoritesApi.remove(props.imageId)
    } else {
      await myFavoritesApi.add(props.imageId)
    }
    isFavorited.value = !isFavorited.value
    emit('changed', { imageId: props.imageId, favorited: isFavorited.value })
  } catch (e) {
    ElMessage.error('操作失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.heart-overlay {
  position: absolute;
  right: 8px;
  bottom: 8px;
  width: 32px; height: 32px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.4);
  color: #fff;
  /* ... */
}
.heart-overlay.active { color: #F56C6C; }
</style>
```

### 6.3 WaterfallGallery 集成爱心（JOIN 方案）

新增 props：`showHeart: Boolean`（默认 true，组件内根据 `useFavoritesConfig().myFavoritesEnabled` 二次判断）。事件：`@favorite-toggled`。

**核心**：**正常瀑布流无需额外请求**——主接口（`/gallery/load`、`/random` 等）已通过 `include_favorite_status` 参数触发服务端 JOIN，响应里每个图片已带 `is_favorited: bool` 字段。WaterfallGallery 直接读 `img.is_favorited` 渲染即可，**不再调用 `/my-favorites/check`**。

```js
// WaterfallGallery.vue loadNewPage 末尾
// 关键：仅当 myFavoritesEnabled=true 时才请求 is_favorited（性能开关）
const params = {
  page, page_size,
  tags, rating, ...otherQueryParams,
  include_favorite_status: myFavoritesEnabled.value,
}
const res = await galleryApi.loadImages(params)
// newImages 元素已带 is_favorited 字段，无需额外 check
```

每个 image tile 用：

```vue
<HeartOverlay
  :image-id="img.id"
  :initial-favorited="img.is_favorited === true"
  @changed="handleFavoriteChanged"
/>
```

切换收藏时（`POST/DELETE /my-favorites/{id}`）调用 `handleFavoriteChanged`，**乐观更新** `img.is_favorited`，不重新请求整页。

### 6.4 FolderTile 「我的最爱」虚拟磁贴

```vue
<template v-if="folder.id === -1">
  <div class="folder-tile virtual-favorite">
    <div class="favorite-icon">⭐ 我的最爱</div>
    <div class="favorite-count">{{ folder.local_count }} 张</div>
  </div>
</template>
<template v-else>
  <!-- 现有 tile 逻辑 -->
</template>
```

### 6.5 Config.vue 「收藏夹」section 扩展

在现有「收藏夹」表单下方追加 2 个开关 + 一段说明：

```
收藏夹 UI 设置（已从 localStorage 迁移）
  - 主页按钮显示: hidden | shown | default
  - tile 尺寸: adaptive | 4 | 6 | 8
  - 预览图排序: random | asc | desc
  - 预览含未下载: [switch]
  - 每页条数: 8 | 12 | 20
  ──────── 分隔 ────────
我的最爱功能
  - [switch] 启用我的最爱
  说明：关闭后，瀑布流图片右下角爱心隐藏，收藏夹列表置顶的「我的最爱」磁贴也隐藏。
随机浏览功能
  - [switch] 启用随机浏览
  说明：关闭后，工具栏的随机按钮隐藏。
```

### 6.6 useFavoritesConfig 重构

```js
// frontend/src/composables/useFavoritesConfig.js（重构）
import { ref, watch } from 'vue'
import api from '@/api'

const state = {
  buttonMode: ref('shown'),
  tileSize: ref('adaptive'),
  previewOrder: ref('random'),
  includeOnline: ref(false),
  folderPageSize: ref(20),
  myFavoritesEnabled: ref(true),
  randomBrowseEnabled: ref(true),
  loaded: ref(false),
}

export function useFavoritesConfig() {
  if (!state.loaded.value) {
    state.loaded.value = true
    // 异步从后端加载；首次加载失败时 fallback 到默认值
    api.get('/config/favorites').then(res => {
      const c = res.data
      state.buttonMode.value = c.button_mode
      state.tileSize.value = c.tile_size
      state.previewOrder.value = c.preview_order
      state.includeOnline.value = c.include_online
      state.folderPageSize.value = c.folder_page_size
      state.myFavoritesEnabled.value = c.my_favorites_enabled
      state.randomBrowseEnabled.value = c.random_browse_enabled
    }).catch(err => console.warn('Load favorites config failed:', err))
  }

  return state
}

export async function saveFavoritesConfig(updates) {
  // 由 Config.vue 调用
  await api.put('/config/favorites', updates)
  // ... 更新本地 state
}
```

**兼容性**：
- 旧 localStorage key 保留 1 个版本作为一次性 fallback（读后即删除）
- Config.vue 保存成功后立刻同步 localStorage key 为空（避免下次启动再回退）

### 6.7 Gallery.vue 第三态

```js
const querySource = ref(localStorage.getItem('gallery_source') || 'local')
// 新增: 'yande' | 'local' | 'favorites' | 'my-favorites'
```

按钮组从 3 联 → 4 联（`[在线, 本地, 收藏夹, 我的最爱]`，但「我的最爱」受 `my_favorites_enabled` 开关控制）。

### 6.8 RandomBrowser.vue

Dialog 组件：标题栏「随机浏览 N 张」+ 卡片网格（每张图右上角有关闭按钮）+ 翻页按钮（`下一页` / `再抽 N 张`）。数据源：`GET /random?limit=20`（首次）/ `GET /random?limit=20&page=N`（后续）。

不引入新 view，直接挂到 Gallery.vue 工具栏右侧（受 `random_browse_enabled` 控制）。

---

## 7. 状态机更新

### 7.1 顶层状态机扩展

```
querySource: 'yande' | 'local' | 'favorites' | 'my-favorites'
favoritesView: null | 'folders' | 'folder-detail'
selectedFavoriteFolder: FavoriteFolder | null
```

| 用户动作 | querySource | favoritesView | selectedFavoriteFolder |
|---------|-------------|---------------|------------------------|
| 首次加载 | 'local' | null | null |
| 点「收藏夹」 | 'favorites' | 'folders' | null |
| 点「我的最爱」按钮 | 'my-favorites' | null | null |
| 点 FolderTile (id=-1) | 'my-favorites' | null | null |
| 点 FolderTile (id>0) | 'favorites' | 'folder-detail' | folder |
| 点返回 | 恢复 | 'folders' | null |

### 7.2 我的最爱分页状态

- 瀑布流 + IntersectionObserver 懒加载，复用现有 `WaterfallGallery`
- 进入页面时 reset 到第 1 页

### 7.3 配置加载策略

- **首次加载**：`useFavoritesConfig()` 异步请求 `/config/favorites`，未返回前用默认值渲染
- **失败 fallback**：网络失败时静默用默认值（不影响主功能）
- **保存路径**：Config.vue 保存成功后同步本地 state + 写 localStorage 备份 key

---

## 8. 测试

### 8.1 后端

| 模块 | 测试用例 |
|------|----------|
| `dao/my_favorite_dao.py` | `add` 幂等（同 image_id 二次调用不抛异常） |
| | `check_batch` 返回 image_ids 子集正确（**仅 DAO 单元测试**；业务路径不调用，由 JOIN 方案替代） |
| | `count` 准确 |
| | `list_paginated` 按 created_at DESC |
| | `get_preview_meta` 限制 limit 正确 |
| `services/my_favorites.py` | `add` 已下载图片不触发 download_task |
| | `add` 未下载图片触发 `DownloadService.create_task` |
| | `add` 不存在的 image_id 抛 ValueError |
| | `remove` 幂等（不存在不报错） |
| `services/random_browse.py` | `get_random` 返回数量 = limit |
| | `get_random` 仅含 `down_flag=True` |
| | `get_random` 带 tags 过滤时正确 |
| `services/favorites.py` | `get_folders_with_preview` 启用开关时返回「我的最爱」虚拟 folder 在首位 |
| | 关闭开关时不返回虚拟 folder |
| `services/config.py` | `update_favorites_config` 写入 yaml 成功 |
| | `update_favorites_config` 非法值（Pydantic validator）抛 422 |

### 8.2 前端

| 模块 | 测试用例 |
|------|----------|
| `HeartOverlay.vue` | 空心 → 点击 → 实心 |
| | 实心 → 点击 → 空心 |
| | toggle 中重复点击防抖 |
| `WaterfallGallery.vue` | `myFavoritesEnabled=false` 时不渲染 HeartOverlay |
| | `myFavoritesEnabled=true` 时请求参数自动带 `include_favorite_status=true` |
| | 响应图片含 `is_favorited` 字段时直接渲染实心/空心 |
| | `myFavoritesEnabled=false` 时请求参数不带 `include_favorite_status`（不发请求） |
| `FolderTile.vue` | `id=-1` 时渲染虚拟磁贴样式 |
| | `id=-1` 时长按不弹编辑菜单 |
| `useFavoritesConfig.js` | 首次调用触发 `GET /config/favorites` |
| | 失败 fallback 到默认值 |
| | `saveFavoritesConfig` 成功后本地 state 同步 |
| `Gallery.vue` | 4 联按钮渲染（受开关控制显示/隐藏「我的最爱」） |
| | `querySource='my-favorites'` 走 `/my-favorites/images` |
| `RandomBrowser.vue` | Dialog 打开 → 加载第一页 |
| | 「再抽 N 张」追加渲染 |

---

## 9. 风险与权衡

| 风险 | 缓解 |
|------|------|
| 大量图片瀑布流加载时 `check` 接口被频繁调用 | 已重构为主接口 JOIN 方案（`include_favorite_status` 参数），正常瀑布流**不调用** `/check`，问题已消除 |
| LEFT JOIN 大量图片瀑布流时性能损耗 | my_favorite 的 `image_id` 已有 UNIQUE 索引，JOIN 走索引查找，单次查询 < 5ms 损耗；可接受。关闭 `my_favorites_enabled` 时前端根本不发该参数，服务端零 JOIN 开销 |
| 主接口响应体增大（每个 image 多 1 个 bool） | 20 张瀑布流 = 20 字节额外，可忽略 |
| `/my-favorites/check` 误用 | 文档与 OpenAPI summary 明确标注「仅特殊场景」；前端 `api/myFavorites.js` 中 `checkBatch` 加 `@deprecated-like` JSDoc 注释提醒 |
| 「我的最爱」虚拟 folder 注入改变 `total`，前端分页计算偏差 | 虚拟 folder 不计入 total（前端用 `has_more` 判断） |
| 加入我的最爱时下载任务被频繁创建（用户连续点图） | `DownloadQueue` 已有 `max_concurrent_tasks` 限流；`create_task` 已处理 race |
| `ORDER BY RANDOM()` 在大表上慢 | YandeData 通常 < 10w 行，可接受；未来若慢可改为 `ORDER BY id LIMIT N OFFSET RANDOM()*MAX(id)` |
| localStorage → 后端迁移时旧用户丢失配置 | 保留旧 key 作为一次性 fallback（读后即删） |
| 多用户场景下 `favorites` 共享冲突 | 项目为单用户工具，文档说明；后续多用户版引入 per-user namespace |
| `my_favorite` 与未来 yande.re API 同步删除产生孤立记录 | 不引入 FK；定期 `JOIN yande_data` 检查的清理脚本（不在本期） |
| `include_online=True` 时虚拟 folder 预览含未下载图，加载慢 | 复用现有 `/cache/preview → /local → /fetch` fallback 链，问题已存在，**不引入新慢路径** |
| `WaterfallGallery` 现有长按选择与爱心点击冲突 | `HeartOverlay` 使用 `.stop.prevent` 屏蔽冒泡；长按逻辑不变 |

### 9.1 YAGNI 决策（再次明确）

- ❌ 不做后端后台调度器补抓「我的最爱」
- ❌ 不做在线随机浏览
- ❌ 不做我的最爱导入 / 导出 / 分享 / 标签分组
- ❌ 不做 per-user 配置命名空间（单用户工具）
- ❌ 不做「我的最爱」图片编辑（重命名 tag 等）
- ❌ 不在本次改动 `FavoriteFolder` 表结构之外的其他字段
- ❌ 不在本次改动现有 favorite_scheduler / 定时调度相关逻辑
- ❌ 不在本次迁移其他 localStorage 偏好（仅 5 项）

---

## 10. 实施步骤（高层）

### Phase 1：后端基础设施（无 UI 改动）
1. 新增 `models/database/my_favorite.py` + `table_constant.my_favorite`
2. 新增 `dao/my_favorite_dao.py`
3. 新增 `models/request/my_favorites.py` + `models/response/my_favorites.py`
4. 新增 `services/my_favorites.py` + `services/random_browse.py`
5. 新增 `api/v1/my_favorites.py` + `api/v1/random.py`
6. `FavoritesConfig` 注入 `Config`；扩 `services/config.py` + `api/v1/config.py`
7. `FavoriteFolder` 加 `is_system` 列 + 响应模型扩展

### Phase 2：收藏夹列表注入虚拟 folder
8. `services/favorites.py:get_folders_with_preview` 注入「我的最爱」虚拟 folder
9. 新增 `GET /my-favorites/images`（详情页瀑布流）
10. 后端测试 + LSP

### Phase 3：前端 useFavoritesConfig 重构
11. 重构 `composables/useFavoritesConfig.js` 为后端 API 版本
12. `views/Config.vue` 「收藏夹」section 表单切换为 PUT /config/favorites
13. 前端测试

### Phase 4：前端组件
14. 新增 `components/HeartOverlay.vue` + `api/myFavorites.js`
15. `components/WaterfallGallery.vue` 集成爱心 + props `showHeart`
16. `components/FolderTile.vue` 渲染 id=-1 虚拟磁贴
17. `views/Gallery.vue` 增加 `querySource='my-favorites'` 第三态 + 4 联按钮
18. 新增 `components/RandomBrowser.vue` + `api/random.js`
19. 前端测试 + 视觉 QA

### Phase 5：联调与发布
20. 端到端验证：加我的最爱 → 自动下载 → 取消 → 重新加入
21. 验证 random_browse_enabled=false 时按钮隐藏
22. 验证 my_favorites_enabled=false 时爱心 + 虚拟磁贴隐藏
23. 文档更新（README + AGENTS.md）
24. PR 提交 → next_dev 集成 → 发版流程（按 docs/release.md）

---

## 11. 兼容性矩阵

| 场景 | 行为 |
|------|------|
| 旧用户首次升级 | localStorage 5 个 key 作为一次性 fallback 读入；之后走后端 |
| 新用户首次安装 | config.yaml 默认值生效；前端读后端默认值 |
| `config.yaml` 中无 `favorites` 段 | Pydantic 自动用默认值（向后兼容） |
| 前端读 `my_favorites_enabled=false` | WaterfallGallery 不渲染爱心；收藏夹列表无虚拟 folder；Gallery 工具栏隐藏「我的最爱」按钮 |
| 后端 `my_favorites_enabled=false` | 「我的最爱」POST 仍允许（开关只控 UI 渲染，不控业务行为），避免开关切换时丢数据 |
| `down_flag=False` 时加入我的最爱 | 入 DownloadTask；前端 toast 提示「已加入收藏，正在下载」 |
| 用户删除已下载图片后保留我的最爱 | 我的最爱保留（`image_id` 仍引用 YandeData 主表记录） |
| YandeData 中图片被删除 | 我的最爱中保留孤立记录（不上 UI 时无感知；清理脚本后续） |

---

## 12. 文档交付

本次改动涉及以下文档更新：

| 文档 | 变更 |
|------|------|
| `docs/superpowers/specs/2026-09-19-my-favorites-and-random-browse-design.md` | 本文档（新增） |
| `docs/release.md` | 版本号更新（按发版流程） |
| `README.md` | 「主要功能」新增「我的最爱」「随机浏览」 |
| `AGENTS.md` | 「重构状态追踪」追加本次变更记录 |
| `docs/design.md` | 数据流图新增「我的最爱」「随机浏览」路径（可选，本次可仅补 README） |

---

*最后更新：2026-09-19（Draft，待用户审阅）*