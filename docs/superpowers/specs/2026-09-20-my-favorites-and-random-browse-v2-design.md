# 我的最爱 + 随机浏览功能 — 设计文档 v2

**状态**：Draft（待用户审阅）
**日期**：2026-09-20
**分支**：`feature-lazy-load-gate-fix-v1.2.1`（基于当前 `next_dev`）
**类型**：新功能（图片级收藏 + 随机浏览）+ 配置中心化重构（不动现有收藏夹查询接口）
**v2 相对 v1 的关键差异**：v1 方案已废弃（破坏 `get_folders_with_preview` 接口导致收藏夹页报错）；v2 改为**前端插入**虚拟磁贴 + **复用** `/gallery/load` 接口（加 2 个可选 query param）+ 不改 `FavoriteFolder` 表

---

## 1. 目标

在现有收藏夹体系（`FavoriteFolder` 按 tags 批量订阅）之上，新增两个**独立展示**功能，**不动现有收藏夹查询接口**：

1. **我的最爱**：图片级标记能力 —— 所有图片右下角展示爱心组件（仅在文件夹展示页 + 文件夹标签页显示）；点击后变为实心、把图片信息加入 `my_favorite` 中间表；**前端**把虚拟"我的最爱"磁贴**插入到收藏夹列表最前**（不是后端注入）；点开后进入二级页，二级页复用 `/api/v1/gallery/load`（带 `include_favorite_status=true`）拿瀑布流；非本地图片加入即触发下载（受 `enable_favorite_autodownload` 控制）。
2. **随机浏览**：复用 `/api/v1/gallery/load` 接口，加 `random=true` 参数让后端用 `ORDER BY RANDOM() + DISTINCT image_id` 返回不重复的随机图片；前端**独立**插入"随机浏览"磁贴到收藏夹列表最前；点开后进入二级页。

**配置中心化**：
- 把现有 `useFavoritesConfig.js` 的 5 个 localStorage key（`button_mode` / `tile_size` / `preview_order` / `include_online` / `folder_page_size`）+ 新增 4 个开关（`enable_my_favorites` / `enable_random_browse` / `enable_favorite_folder` / `enable_favorite_autodownload`）全部迁移到后端 `config.yaml` 的 `favorites` section，暴露 `GET/PUT /config/favorites` API。

**关键约束**：
- ✅ **不动** `get_folders_with_preview` 接口（不注入虚拟 folder）
- ✅ **不动** `FavoriteFolder` 表（不加 `is_system` 列）
- ✅ **不动** 原收藏夹调用方（前端 `FavoritePanel.vue` 调用方式不变）
- ✅ **不动** `FavoriteFolder` 现有 CRUD 接口
- ✅ 新组件、新接口不破坏现有项目约定

### 1.1 范围内

| 模块 | 范围 |
|---|---|
| 后端数据 | 新增 `my_favorite` 中间表（自动建表） |
| 后端服务 | 新增 `MyFavoritesService`，扩 `GalleryService`（JOIN + random） |
| 后端 API | 新增 `/api/v1/my-favorites/*`（含独立 `/preview`）；扩 `/api/v1/gallery/load`、`/api/v1/gallery/{id}`、`/api/v1/config/favorites` |
| 后端配置 | 新增 `FavoritesConfig` Pydantic 模型，挂到 `Config.favorites` |
| 前端组件 | 新增 `HeartOverlay.vue`；扩 `FolderTile.vue`、`WaterfallGallery.vue`、`FavoritePanel.vue`、`Gallery.vue`、`Config.vue` |
| 前端状态 | `useFavoritesConfig.js` 重构：localStorage → 后端 `GET/PUT /config/favorites` + `myFavoritesCount` 缓存 |
| 自动下载 | 加入我的最爱时，若 `is_local=false` 且 `enable_favorite_autodownload=true`，推送 `DownloadTask` |

### 1.2 不在范围内（YAGNI）

- 在线随机（仅本地随机）
- 后台扫描器自动补抓（采用「加入即触发」即可）
- 我的最爱导入 / 导出 / 分享 / 标签 / 备注 UI（`note` 字段先预留，不上 UI）
- 我的最爱跨设备同步
- 我的最爱图片分组 / 标签管理（先做扁平列表）
- 后端注入虚拟 folder（v1 方案废弃，v2 由前端 prepend）
- `FavoriteFolder.is_system` 字段（v1 方案废弃）
- `/api/v1/random` 独立路由（v1 方案废弃，v2 复用 `/gallery/load?random=true`）
- `RandomBrowser.vue` 组件（v1 方案废弃，v2 随机浏览直接走 Gallery 二级页）

---

## 2. 背景与现状

### 2.1 现有收藏夹体系（不动）

- `FavoriteFolder` 表是「按 tags 批量订阅」语义，用户订阅的是「标签条件」（如 `rating:s score:>100`），系统按 tags 拉图入库
- 用户**不能**针对单张图片表达「我特别喜欢这张」 —— 这是本次新增「我的最爱」要解决的问题
- `get_folders_with_preview` 是收藏夹**一级**页（文件夹展示页）的入口，**本次保持不动**

### 2.2 现有「我的最爱」预留位

| 位置 | 现有注释 |
|---|---|
| `backend/src/services/favorites.py:85` | `include_online: True 时预览图同时包含未下载的在线图片（未来「我的最爱」支持收藏未下载图时启用）` |
| `backend/src/api/v1/favorites.py:172` | `# TODO: 后续「我的最爱」功能会用到此接口（单 folder 全量预览）` |

本次兑现这两处预留。

### 2.3 v1 实现的问题（必须避免重蹈覆辙）

v1 方案的核心错误**：在 `get_folders_with_preview` 中**注入**虚拟 folder（`id=-1`），且为 `FavoriteFolder` 表新增 `is_system` 列。

后果：
1. 后端接口行为变更 → 调用方报错（"收藏夹页报错"的根因）
2. DB schema 变更 → 迁移成本 + 兼容性矩阵复杂
3. 虚拟 folder 在 DB 中不存在 → 前端跳转 `/gallery/load?folder_id=-1` 时报外键错误或 N+1 查询性能劣化

**v2 解决方案**：完全不动后端收藏夹查询接口，虚拟磁贴**纯前端**插入；`/my-favorites/*` 业务接口 + `/my-favorites/preview` 独立预览接口是新增的、不破坏现有结构。

### 2.4 现有收藏夹 UI 配置（localStorage 分散）

`frontend/src/composables/useFavoritesConfig.js` 当前用 5 个 localStorage key：

```
gallery_favorites_button_mode      : 'hidden' | 'shown' | 'default'
gallery_favorites_tile_size        : 'adaptive' | '4' | '6' | '8'
gallery_favorites_preview_order    : 'random' | 'asc' | 'desc'
gallery_favorites_include_online   : 'true' | 'false'
favorites_folder_page_size         : '8' | '12' | '20'
```

**问题**：
- 配置分散（localStorage + yaml 两套），不在 Config.vue 中统一管理
- 后端无法参与联动（如根据开关决定是否连表 `is_favorited`）
- 多端同步靠运气

### 2.5 现有后端 `Config` 类（要扩）

`backend/src/common/settings.py:Config` 类当前 sections：
- `app` / `database` / `yande_api` / `downloader` / `scheduler`
- **无** `favorites` section —— 本次新增
- `update_config()` 已通过 `isinstance` 自动适配新 section，**无需修改**

### 2.6 现有下载入口（复用）

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

### 2.7 现有 `GalleryLoadRequest`（要扩）

`backend/src/api/v1/gallery.py` 当前 `load_gallery` 接口接收 `GalleryLoadRequest`，**无** `include_favorite_status` / `random` 参数 —— 本次新增为**可选** query param。

### 2.8 现有 `YandeData` 响应模型（要扩）

`backend/src/models/response/` 中 `YandeData` / `YandeDataDetail` 响应模型当前无 `is_favorited` 字段 —— 本次新增为 **Optional[bool]**（None=未查询，True/False=已查询）。

### 2.9 现有 `FolderTile.vue` / `FavoritePanel.vue`（要改）

- `FolderTile.vue`：当前只渲染 `FavoriteFolderWithMinimalPreview` 类型磁贴
- `FavoritePanel.vue`：当前展示收藏夹列表 + FolderTile 网格

**关键点**：本次新增**虚拟磁贴**（"我的最爱"+"随机浏览"）由 `FavoritePanel.vue` 在最前**前端**插入；`FolderTile.vue` **识别**虚拟项（`isVirtual=true`）并以不同样式渲染，但**FolderTile 本身不创建虚拟项数据**，虚拟项由 `FavoritePanel.vue` 注入 props。

### 2.10 现有 `WaterfallGallery.vue`（要扩 props）

当前 `WaterfallGallery.vue` 仅渲染图片瀑布流；本次新增 `showHeart` props（默认 false）+ `@favorite-toggled` 事件，由调用方（`Gallery.vue`）根据 `querySource` 决定是否传入 true。

---

## 3. 数据模型

### 3.1 新增 `my_favorite` 中间表

新建 `backend/src/models/database/my_favorite.py`：

```python
class MyFavorite(Base):
    """我的最爱 - 图片级标记（与 FavoriteFolder 互不污染）"""
    __tablename__ = table_constant.my_favorite

    id = Column(Integer, primary_key=True, autoincrement=True)
    image_id = Column(Integer, nullable=False, comment="yande 图片 ID")
    created_at = Column(DateTime, default=datetime.now, comment="收藏时间")
    note = Column(String(255), nullable=True, comment="预留备注字段（暂不上 UI）")
```

**关键决策**：

| 决策点 | 选择 | 理由 |
|---|---|---|
| 主键 | 自增 `id` | 便于分页、按收藏时间排序 |
| 与 YandeData 关系 | `UNIQUE(image_id)` 约束，**不加 FK** | 与项目现有约定一致（`FavoriteFolder` 也不加 FK） |
| `note` 字段 | 预留，本期不上 UI | 扩展性强、零成本 |
| 索引 | `UNIQUE(image_id)` + `INDEX(created_at DESC)` | 加入幂等、按时间倒序列表 |
| 软删除 | 不做（直接 `DELETE`） | YandeData 主表已有完整元数据 |

### 3.2 `table_constant` 新增

```python
# backend/src/common/constant.py (扩展)
my_favorite: str = "my_favorite"
```

### 3.3 数据库迁移

项目采用 SQLite 自动建表（沿用 `Base.metadata.create_all`），无 Alembic 迁移历史。`MyFavorite` 通过 `Base.metadata` 注册即自动建表。

### 3.4 `FavoriteFolder` 表 —— **完全不动**

不增加 `is_system` 列、不调整任何字段。原因：核心要求是「不动现有收藏夹查询接口」，虚拟磁贴由前端插入，DB 不感知。

---

## 4. 后端配置

### 4.1 新增 `FavoritesConfig` 模型

`backend/src/common/settings.py` 新增：

```python
class FavoritesConfig(ConfigModel):
    """收藏夹 UI 配置 + 我的最爱/随机浏览总开关（从 localStorage 迁移）"""

    # 从前端 localStorage 迁过来的 5 个 UI 偏好
    button_mode: str = Field("shown", description="主页收藏夹按钮显示: hidden | shown | default")
    tile_size: str = Field("adaptive", description="收藏夹 tile 大小: adaptive | 4 | 6 | 8")
    preview_order: str = Field("random", description="预览图排序: random | asc | desc")
    include_online: bool = Field(False, description="预览是否包含未下载图片")
    folder_page_size: int = Field(20, description="收藏夹一级每页: 8 | 12 | 20")

    # 新功能总开关
    enable_my_favorites: bool = Field(False, description="我的最爱功能总开关")
    enable_random_browse: bool = Field(False, description="随机浏览功能总开关")
    enable_favorite_folder: bool = Field(True, description="收藏夹展示总开关")
    enable_favorite_autodownload: bool = Field(True, description="我的最爱自动下载开关")

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

### 5.1 `/api/v1/my-favorites/*`（核心 CRUD）

新建 `backend/src/api/v1/my_favorites.py`：

| 方法 | 路由 | 用途 | 响应模型 |
|---|---|---|---|
| GET | `/my-favorites` | 分页列出（按 created_at DESC） | `MyFavoritesListResponse` |
| POST | `/my-favorites/{image_id}` | 加入我的最爱（幂等；未下载则触发下载） | `BaseResponse` |
| DELETE | `/my-favorites/{image_id}` | 取消我的最爱（幂等） | `BaseResponse` |
| GET | `/my-favorites/count` | 总数（用于收藏夹列表前端插入磁贴的角标） | `MyFavoriteCountResponse` |
| GET | `/my-favorites/preview` | **独立预览接口**（仅供文件夹展示页用） | `MyFavoritePreviewResponse` |

#### 5.1.1 加入时自动下载

```python
@router.post("/{image_id}", response_model=BaseResponse, summary="加入我的最爱")
async def add_my_favorite(image_id: int) -> BaseResponse:
    """加入我的最爱。幂等（UNIQUE image_id 兜底）。
    若图片未下载（down_flag=False）且 enable_favorite_autodownload=true，
    异步触发下载任务。"""
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
    """加入我的最爱；满足条件时异步触发下载。"""
    with YandeDataRepository() as repo:
        yande_data = repo.get_by_id(image_id)
    if not yande_data:
        raise ValueError(f"Image {image_id} not found in database")

    # 1) 写入 my_favorite（UNIQUE 约束保证幂等）
    my_favorite_dao.add(image_id=image_id)

    # 2) 仅当 is_local=false 且 enable_favorite_autodownload=true 才触发下载
    if not yande_data.down_flag and config.favorites.enable_favorite_autodownload:
        try:
            await DownloadService.create_task(image_id)
            logger.info(f"My favorite auto-download triggered for {image_id}")
        except Exception as e:
            # 下载触发失败不影响收藏已成功（用户视角：先收藏，下载后续补）
            logger.warning(f"Auto-download failed for {image_id}: {e}")
```

#### 5.1.2 独立预览接口

```python
@router.get("/preview", response_model=MyFavoritePreviewResponse, summary="我的最爱预览")
async def get_my_favorites_preview(
    limit: int = Query(20, ge=1, le=100, description="返回预览图数"),
    tile_size: str = Query("adaptive", description="tile 大小"),
) -> MyFavoritePreviewResponse:
    """为文件夹展示页提供我的最爱预览图（独立的、不复用 favorites 的接口）。

    返回最近加入我的爱好的图片缩略图元数据（按 created_at DESC）。
    不调用 get_folders_with_preview，不影响原收藏夹接口。
    """
    try:
        return MyFavoritesService.get_preview(limit=limit, tile_size=tile_size)
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)
```

`MyFavoritesService.get_preview` 实现要点：
- 用 `MyFavoriteDao.list_paginated(limit=limit)` 拿最近 image_ids
- `JOIN yande_data` 拿缩略图元数据（`id`, `preview_url`, `tags`, `rating` 等）
- 响应结构对齐 `FavoriteFolderWithMinimalPreview.preview_images`，便于 `FolderTile` 复用渲染

### 5.2 `/api/v1/gallery/load` 扩展（核心复用接口）

**新增 2 个可选 query param**：

```python
class GalleryLoadRequest(BaseModel):
    # ... 现有字段 ...

    include_favorite_status: bool = Field(
        default=False,
        description="True 时响应中每个图片附带 is_favorited 字段（LEFT JOIN my_favorite）。"
                    "前端仅当 enable_my_favorites=true 时才传 True。"
    )
    random: bool = Field(
        default=False,
        description="True 时使用 ORDER BY RANDOM() + DISTINCT image_id 返回随机图片（id 不重复）。"
                    "前端仅当 querySource='random' 时才传 True。"
    )
```

**`load_gallery` 实现要点**：

```python
@router.post("/load", response_model=GalleryLoadResponse, summary="加载图库")
async def load_gallery(request: GalleryLoadRequest) -> GalleryLoadResponse:
    try:
        # 双重判断：
        # 1. 后端配置开关关闭 → 强制不 JOIN（即使前端误传 True也不连表）
        # 2. 请求参数为 False → 不 JOIN
        # 只有开关开启 + 请求 True 才 JOIN
        effective_include_favorite = (
            request.include_favorite_status and config.favorites.enable_my_favorites
        )
        result = GalleryService.load_images(
            request=request,
            include_favorite_status=effective_include_favorite,
            random=request.random,
        )
        return result
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)
```

`GalleryService.load_images` 内部：

```python
def load_images(request, include_favorite_status=False, random=False):
    # 1. 基础 SQL 拼接（保持原有逻辑）
    base_query = select(YandeData).where(...)

    # 2. random=True 时添加 ORDER BY RANDOM() + DISTINCT
    if random:
        base_query = base_query.order_by(func.random()).distinct(YandeData.id).limit(request.page_size)

    # 3. include_favorite_status=True 时 LEFT JOIN
    if include_favorite_status:
        # 关键：一次 SQL 拿所有图片的 favorited 状态（高效，避免 for 循环）
        result_rows = session.execute(
            select(
                YandeData,
                case(
                    (MyFavorite.image_id.is_not(None), True),
                    else_=False,
                ).label("is_favorited")
            )
            .outerjoin(MyFavorite, MyFavorite.image_id == YandeData.id)
            .where(...)
            .order_by(...)
            .limit(...)
        ).all()
        # 展平为 YandeData + is_favorited 字段
    else:
        # 不连表，保持原行为
        result_rows = session.execute(base_query).all()
```

**关键不变量**：
- 当 `config.favorites.enable_my_favorites=False` 时，无论前端传什么，`include_favorite_status` **强制为 False**——零 JOIN 开销
- 当 `random=True` 时，**必须** 用 `DISTINCT image_id`（保证不重复）+ `ORDER BY RANDOM() LIMIT N`（高效）

### 5.3 `/api/v1/gallery/detail` 扩展（继承 is_favorited）

`get_image_detail` 接口扩展：

```python
@router.get("/{image_id}", response_model=BaseResponse[YandeDataDetail], summary="图片详情")
async def get_image_detail(
    image_id: int,
    include_favorite_status: bool = Query(
        default=False,
        description="True 时响应附带 is_favorited 字段；前端仅当 enable_my_favorites=true 时才传 True"
    )
) -> BaseResponse[YandeDataDetail]:
    """点开详情时复用上层传入的 is_favorited 决策。
    若 include_favorite_status=True 且 enable_my_favorites=True → JOIN 一次拿 favorited。
    否则不连表（响应中 is_favorited 为 None）。"""
    try:
        detail = GalleryService.get_image_detail(
            image_id=image_id,
            include_favorite_status=include_favorite_status and config.favorites.enable_my_favorites,
        )
        return BaseResponse(message=ErrMsg.OK.msg, data=detail)
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)
```

`YandeDataDetail` 响应模型：

```python
class YandeDataDetail(BaseModel):
    # ... 现有字段 ...
    is_favorited: Optional[bool] = Field(
        default=None,
        description="是否已加入我的最爱；仅 include_favorite_status=True 时返回 True/False，否则 None"
    )
```

**前端使用**：详情页打开时 `Gallery.vue` 传入 `include_favorite_status=useFavoritesConfig().enableMyFavorites`，详情组件接 `data.is_favorited`，在 `float-header-left` 显示空心/实心 HeartOverlay。

### 5.4 不新增 `/api/v1/random` 独立路由

**原因**：你明确要求"随机浏览也复用原有接口"。`/random` 通过 `/gallery/load?random=true` 实现，二级页 `Gallery.vue` 加 `querySource='random'` 模式调用即可。

**不引入**单独的 `/api/v1/random` endpoint——这是 v1 设计的遗留，v2 移除。

### 5.5 `/api/v1/favorites/*` 现有接口 —— **完全不动**

- `get_folders_with_preview` 不注入虚拟 folder
- `get_folder` / `create_folder` / `update_folder` / `delete_folder` / `refresh_local_count` 全部保持原样
- `FavoriteFolder` 表结构不变（不加 `is_system` 列）
- `FavoriteFolderBase` 响应模型不变（不加 `is_system` 字段）

**核心原则**：前端通过 `FavoritePanel.vue` **前端插入**虚拟磁贴，**完全不动** 后端收藏夹查询链路。

---

## 6. 前端

### 6.1 文件清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `frontend/src/composables/useFavoritesConfig.js` | 重构 | localStorage → 后端 `GET/PUT /config/favorites` |
| `frontend/src/api/myFavorites.js` | 新增 | `add`, `remove`, `list`, `count`, `getPreview` |
| `frontend/src/components/HeartOverlay.vue` | 新增 | 通用爱心按钮（空心/实心，**无边框**，放置 image-info-content 层） |
| `frontend/src/components/WaterfallGallery.vue` | 修改 | props 新增 `showHeart` + `@favorite-toggled` 事件；自动按配置决定是否带 `include_favorite_status` |
| `frontend/src/components/FolderTile.vue` | 修改 | 识别 `isVirtual` 字段渲染虚拟磁贴（"我的最爱"/"随机浏览"） |
| `frontend/src/components/FavoritePanel.vue` | 修改 | **前端 prepend** 虚拟磁贴（受 `enable_my_favorites` / `enable_random_browse` 控制） |
| `frontend/src/views/Gallery.vue` | 修改 | 新增 `querySource='my-favorites'` / `querySource='random'` 模式；工具栏按钮 |
| `frontend/src/views/Config.vue` | 修改 | 高级 tab 新增"收藏夹 + 我的最爱 + 随机浏览"section（含 4 个新开关） |

**不新增** `RandomBrowser.vue`（v1 设计遗留，v2 移除——随机浏览直接走 Gallery 二级页）。

### 6.2 `HeartOverlay.vue`（无边框 + image-info-content 层）

**关键要求**（来自你的反馈）：
- 放置在 `image-info-content` 层（**不**单独占位）
- **不**加边框
- 仅在 `showHeart=true`（由调用方传入）时显示

```vue
<template>
  <button
    v-if="showHeart"
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
  showHeart: { type: Boolean, default: false },
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
  /* 关键：无边框 */
  border: none;
  outline: none;
  background: transparent;
  cursor: pointer;
  padding: 0;
  color: rgba(255, 255, 255, 0.85);
  font-size: 18px;
  transition: color 0.2s, transform 0.2s;
}
.heart-overlay:hover {
  transform: scale(1.15);
}
.heart-overlay.active {
  color: #F56C6C;
}
.heart-overlay.loading {
  opacity: 0.6;
  cursor: wait;
}
</style>
```

**集成位置**：`<WaterfallGallery>` 的 `image-info-content` 槽内（在现有信息文字旁），不额外占位：

```vue
<div class="image-info-content">
  <span>{{ img.rating }} | {{ img.tags_summary }}</span>
  <HeartOverlay
    :image-id="img.id"
    :initial-favorited="img.is_favorited === true"
    :show-heart="showHeart"
    @changed="handleFavoriteChanged"
  />
</div>
```

### 6.3 `WaterfallGallery.vue` 集成（JOIN 方案）

新增 props：`showHeart: Boolean`（默认 false）。事件：`@favorite-toggled`。

```js
// WaterfallGallery.vue loadNewPage 末尾
const params = {
  page, page_size,
  tags, rating, ...otherQueryParams,
}
// 关键：仅当 enable_my_favorites=true 时才请求 is_favorited
if (props.showHeart && myFavoritesEnabled.value) {
  params.include_favorite_status = true
}
const res = await galleryApi.loadImages(params)
// newImages 元素已带 is_favorited 字段，无需额外 check
```

### 6.4 `FolderTile.vue` 识别虚拟磁贴

```vue
<template>
  <div v-if="folder.isVirtual" class="folder-tile virtual-tile" :class="`virtual-${folder.id}`">
    <div class="virtual-icon">
      <el-icon><StarFilled v-if="folder.id === 'my-favorites'" /><MagicStick v-else /></el-icon>
      <span>{{ folder.name }}</span>
    </div>
    <div class="virtual-count">{{ folder.local_count }} 张</div>
  </div>
  <template v-else>
    <!-- 现有 tile 逻辑 -->
  </template>
</template>
```

### 6.5 `FavoritePanel.vue` 前端插入虚拟磁贴（核心）

```js
// FavoritePanel.vue
import { useFavoritesConfig } from '@/composables/useFavoritesConfig'
const { enableMyFavorites, enableRandomBrowse } = useFavoritesConfig()

const virtualTiles = computed(() => {
  const tiles = []
  if (enableMyFavorites.value) {
    tiles.push({
      id: 'my-favorites',
      name: '我的最爱',
      isVirtual: true,
      local_count: myFavoritesCount.value,
      preview_images: [],
    })
  }
  if (enableRandomBrowse.value) {
    tiles.push({
      id: 'random',
      name: '随机浏览',
      isVirtual: true,
      local_count: 0,  // 随机浏览无固定数量
      preview_images: [],
    })
  }
  return tiles
})

// 渲染列表：虚拟磁贴 + 后端真实收藏夹
const displayItems = computed(() => [
  ...virtualTiles.value,
  ...realFolders.value,
])
```

**关键**：
- 虚拟磁贴**完全由前端生成**，调用 `get_folders_with_preview` 后**只在前面 prepend** 2 个虚拟项
- `myFavoritesCount` 通过 `GET /my-favorites/count` 异步获取（**只获取一次**，缓存到 `useFavoritesConfig` 单例）
- 点击虚拟磁贴：`id === 'my-favorites'` → 跳 `Gallery.vue?querySource=my-favorites`；`id === 'random'` → 跳 `Gallery.vue?querySource=random`

### 6.6 `Gallery.vue` 新增 querySource 模式

```js
const querySource = ref(localStorage.getItem('gallery_source') || 'local')
// 扩展: 'yande' | 'local' | 'favorites' | 'my-favorites' | 'random'

const showHeart = computed(() => {
  return querySource.value === 'my-favorites' || querySource.value === 'random'
})

// loadNewPage: 传入 showHeart 给 WaterfallGallery
<WaterfallGallery :show-heart="showHeart" ... />

// 详情页打开时传递 include_favorite_status（继承上层）
function openImageDetail(img) {
  // ...跳详情页 ...
  detailUrl += `&include_favorite_status=${enableMyFavorites.value}`
}
```

### 6.7 详情页 `ImageDetail.vue`（float-header-left）

在 `float-header-left` 显示 HeartOverlay：

```vue
<div class="float-header-left">
  <HeartOverlay
    v-if="enableMyFavorites"
    :image-id="imageDetail.id"
    :initial-favorited="imageDetail.is_favorited === true"
    :show-heart="true"
    @changed="handleFavoriteChanged"
  />
  <span>{{ imageDetail.rating }} | {{ imageDetail.score }}</span>
</div>
```

`imageDetail.is_favorited` 来自后端 `/gallery/detail?include_favorite_status=...` 响应。

### 6.8 `Config.vue` 收藏夹 section

```vue
<el-tab-pane label="收藏夹 + 我的最爱 + 随机浏览" name="favorites">
  <!-- 收藏夹展示总开关 -->
  <el-form-item label="收藏夹展示">
    <el-switch v-model="favoritesConfig.enable_favorite_folder" />
    <span class="form-help">关闭后整个收藏夹模块隐藏</span>
  </el-form-item>

  <!-- 我的最爱总开关 -->
  <el-form-item label="我的最爱">
    <el-switch v-model="favoritesConfig.enable_my_favorites" />
    <span class="form-help">关闭后，瀑布流图片右下角爱心隐藏，收藏夹列表我的最爱磁贴也隐藏</span>
  </el-form-item>

  <!-- 我的最爱自动下载开关 -->
  <el-form-item label="非本地图片自动下载">
    <el-switch v-model="favoritesConfig.enable_favorite_autodownload" :disabled="!favoritesConfig.enable_my_favorites" />
    <span class="form-help">关闭后，非本地图片加入我的最爱不会触发下载</span>
  </el-form-item>

  <!-- 随机浏览总开关 -->
  <el-form-item label="随机浏览">
    <el-switch v-model="favoritesConfig.enable_random_browse" />
    <span class="form-help">关闭后，收藏夹列表随机浏览磁贴隐藏</span>
  </el-form-item>

  <el-divider />

  <!-- 原有 5 个 UI 偏好（从 localStorage 迁过来）-->
  <el-form-item label="主页按钮显示">
    <el-radio-group v-model="favoritesConfig.button_mode">
      <el-radio value="hidden">隐藏</el-radio>
      <el-radio value="shown">显示</el-radio>
      <el-radio value="default">默认</el-radio>
    </el-radio-group>
  </el-form-item>
  <el-form-item label="tile 大小">
    <el-radio-group v-model="favoritesConfig.tile_size">
      <el-radio value="adaptive">自适应</el-radio>
      <el-radio value="4">4</el-radio>
      <el-radio value="6">6</el-radio>
      <el-radio value="8">8</el-radio>
    </el-radio-group>
  </el-form-item>
  <el-form-item label="预览图排序">
    <el-radio-group v-model="favoritesConfig.preview_order">
      <el-radio value="random">随机</el-radio>
      <el-radio value="asc">升序</el-radio>
      <el-radio value="desc">降序</el-radio>
    </el-radio-group>
  </el-form-item>
  <el-form-item label="预览含未下载">
    <el-switch v-model="favoritesConfig.include_online" />
  </el-form-item>
  <el-form-item label="每页条数">
    <el-radio-group v-model="favoritesConfig.folder_page_size">
      <el-radio :value="8">8</el-radio>
      <el-radio :value="12">12</el-radio>
      <el-radio :value="20">20</el-radio>
    </el-radio-group>
  </el-form-item>
</el-tab-pane>
```

### 6.9 `useFavoritesConfig.js` 重构

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
  // 4 个新开关
  enableMyFavorites: ref(false),
  enableRandomBrowse: ref(false),
  enableFavoriteFolder: ref(true),
  enableFavoriteAutodownload: ref(true),
  loaded: ref(false),
  // 我的最爱总数缓存（用于 FavoritePanel 角标）
  myFavoritesCount: ref(0),
}

export function useFavoritesConfig() {
  if (!state.loaded.value) {
    state.loaded.value = true
    api.get('/config/favorites').then(res => {
      const c = res.data
      state.buttonMode.value = c.button_mode
      state.tileSize.value = c.tile_size
      state.previewOrder.value = c.preview_order
      state.includeOnline.value = c.include_online
      state.folderPageSize.value = c.folder_page_size
      state.enableMyFavorites.value = c.enable_my_favorites
      state.enableRandomBrowse.value = c.enable_random_browse
      state.enableFavoriteFolder.value = c.enable_favorite_folder
      state.enableFavoriteAutodownload.value = c.enable_favorite_autodownload
    }).catch(err => console.warn('Load favorites config failed:', err))

    // 加载我的最爱总数（仅当开关开启）
    if (state.enableMyFavorites.value) {
      api.get('/my-favorites/count').then(res => {
        state.myFavoritesCount.value = res.data.count
      }).catch(() => {})
    }
  }

  return state
}

export async function saveFavoritesConfig(updates) {
  await api.put('/config/favorites', updates)
  Object.entries(updates).forEach(([k, v]) => {
    const key = k.replace(/_([a-z])/g, (_, c) => c.toUpperCase())
    if (key in state) state[key].value = v
  })
}
```

**兼容性**：
- 旧 localStorage key 保留 1 个版本作为一次性 fallback（读后即删除）
- Config.vue 保存成功后立刻同步 localStorage key 为空（避免下次启动再回退）

---

## 7. 状态机更新

### 7.1 顶层状态机扩展

```
querySource: 'yande' | 'local' | 'favorites' | 'my-favorites' | 'random'
favoritesView: null | 'folders' | 'folder-detail'
selectedFavoriteFolder: FavoriteFolder | null
```

| 用户动作 | querySource | favoritesView | selectedFavoriteFolder |
|---|---|---|---|
| 首次加载 | `'local'` | null | null |
| 点「收藏夹」 | `'favorites'` | `'folders'` | null |
| 点虚拟磁贴 `my-favorites` | `'my-favorites'` | null | null |
| 点虚拟磁贴 `random` | `'random'` | null | null |
| 点 FolderTile（id>0） | `'favorites'` | `'folder-detail'` | folder |
| 点返回 | 恢复 | `'folders'` | null |

### 7.2 我的最爱 / 随机浏览分页状态

- 瀑布流 + IntersectionObserver 懒加载，复用现有 `WaterfallGallery`
- 进入页面时 reset 到第 1 页
- `querySource='random'` 时在请求参数中加 `random=true`（后端 `ORDER BY RANDOM()` + `DISTINCT image_id`）

### 7.3 配置加载策略

- **首次加载**：`useFavoritesConfig()` 异步请求 `/config/favorites`，未返回前用默认值渲染
- **失败 fallback**：网络失败时静默用默认值（不影响主功能）
- **保存路径**：Config.vue 保存成功后同步本地 state + 写 localStorage 备份 key

### 7.4 我的最爱总数缓存策略

- `useFavoritesConfig().myFavoritesCount` 在首次 `useFavoritesConfig()` 调用时异步请求 `/my-favorites/count`
- 加入 / 取消我的最爱时，乐观更新该 ref（+1 / -1）
- 详情页打开时不重新请求

---

## 8. 测试

### 8.1 后端

| 模块 | 测试用例 |
|---|---|
| `dao/my_favorite_dao.py` | `add` 幂等（同 image_id 二次调用不抛异常） |
|  | `list_paginated` 按 created_at DESC |
|  | `count` 准确 |
|  | `get_preview` 限制 limit 正确，JOIN yande_data 正确 |
| `services/my_favorites.py` | `add` 已下载图片不触发 download_task |
|  | `add` 未下载图片 + `enable_favorite_autodownload=true` 触发 `DownloadService.create_task` |
|  | `add` 未下载图片 + `enable_favorite_autodownload=false` **不**触发下载 |
|  | `add` 不存在的 image_id 抛 ValueError |
|  | `remove` 幂等（不存在不报错） |
|  | `get_preview` 返回结构与 `FavoriteFolderWithMinimalPreview.preview_images` 对齐 |
| `services/gallery.py` | `load_images(include_favorite_status=False)` 不连表，响应无 `is_favorited` 字段 |
|  | `load_images(include_favorite_status=True, enable_my_favorites=False)` **不**连表 |
|  | `load_images(include_favorite_status=True, enable_my_favorites=True)` LEFT JOIN 正确 |
|  | `load_images(random=True)` `ORDER BY RANDOM() + DISTINCT image_id` 正确，id 不重复 |
|  | `get_image_detail(include_favorite_status=True)` 返回 is_favorited 字段 |
|  | `get_image_detail(include_favorite_status=False)` 返回 is_favorited=None |
| `services/config.py` | `update_favorites_config` 写入 yaml 成功 |
|  | `update_favorites_config` 非法值（Pydantic validator）抛 422 |
| `services/favorites.py` | `get_folders_with_preview` **不**注入"我的最爱"虚拟 folder（**回归测试**，确保不动现有行为） |

### 8.2 前端

| 模块 | 测试用例 |
|---|---|
| `HeartOverlay.vue` | 空心 → 点击 → 实心 |
|  | 实心 → 点击 → 空心 |
|  | toggle 中重复点击防抖 |
|  | 渲染时**无边框**（断言 computed style `border-width === 0` 或 `border-style === none`） |
| `WaterfallGallery.vue` | `showHeart=true` + `enableMyFavorites=true` 时请求参数自动带 `include_favorite_status=true` |
|  | `showHeart=false` 或 `enableMyFavorites=false` 时请求参数**不带** `include_favorite_status` |
|  | 响应图片含 `is_favorited` 字段时直接渲染实心/空心 |
| `FolderTile.vue` | `isVirtual=true` 时渲染虚拟磁贴样式（star/MagicStick icon） |
|  | `isVirtual=true` 时长按不弹编辑菜单 |
|  | `isVirtual=undefined` 时渲染现有逻辑 |
| `FavoritePanel.vue` | `enableMyFavorites=true` 时列表最前 prepend "我的最爱"虚拟磁贴 |
|  | `enableMyFavorites=false` 时不 prepend "我的最爱" |
|  | `enableRandomBrowse=true` 时列表最前 prepend "随机浏览"虚拟磁贴 |
|  | `enableRandomBrowse=false` 时不 prepend "随机浏览" |
|  | 点击虚拟磁贴 `my-favorites` 跳 `Gallery.vue?querySource=my-favorites` |
|  | 点击虚拟磁贴 `random` 跳 `Gallery.vue?querySource=random` |
| `Gallery.vue` | `querySource='my-favorites'` 时 WaterfallGallery `showHeart=true` |
|  | `querySource='random'` 时请求参数带 `random=true` + `showHeart=true` |
|  | `querySource='local'` 时 `showHeart=false` |
|  | 详情页打开时 `include_favorite_status` 跟随 `enableMyFavorites` |
| `useFavoritesConfig.js` | 首次调用触发 `GET /config/favorites` |
|  | 失败 fallback 到默认值 |
|  | `saveFavoritesConfig` 成功后本地 state 同步 |
|  | `myFavoritesCount` 在开关开启时触发 `GET /my-favorites/count` |
| `Config.vue` | 4 个新开关（`enable_my_favorites` / `enable_random_browse` / `enable_favorite_folder` / `enable_favorite_autodownload`）渲染 |
|  | `enable_my_favorites=false` 时 `enable_favorite_autodownload` switch 禁用 |
|  | 保存后调用 `PUT /config/favorites` |
|  | 原有 5 个 UI 偏好迁移到新位置 |

---

## 9. 风险与权衡

| 风险 | 缓解 |
|---|---|
| 大量图片瀑布流加载时 `check` 接口被频繁调用 | 已重构为主接口 JOIN 方案（`include_favorite_status` 参数），正常瀑布流**不调用** `/check`，问题已消除 |
| LEFT JOIN 大量图片瀑布流时性能损耗 | my_favorite 的 `image_id` 已有 UNIQUE 索引，JOIN 走索引查找；单次查询 < 5ms 损耗，可接受。**双重判断**（开关关闭时强制不 JOIN）保证零开销路径 |
| `get_folders_with_preview` 误改回原行为（注入虚拟 folder） | 回归测试：新增 `services/favorites.py` `test_get_folders_with_preview_no_virtual` 用例，确保响应列表中**无** id='my-favorites' 或 id='random' 虚拟项 |
| `ORDER BY RANDOM()` 在大表上慢 | YandeData 通常 < 10w 行，可接受；未来若慢可改为 `ORDER BY id LIMIT N OFFSET RANDOM()*MAX(id)` |
| localStorage → 后端迁移时旧用户丢失配置 | 保留旧 key 作为一次性 fallback（读后即删） |
| 加入我的最爱时下载任务被频繁创建（用户连续点图） | `DownloadQueue` 已有 `max_concurrent_tasks` 限流；`create_task` 已处理 race |
| `WaterfallGallery` 现有长按选择与爱心点击冲突 | `HeartOverlay` 使用 `.stop.prevent` 屏蔽冒泡；长按逻辑不变 |
| HeartOverlay 加边框破坏视觉一致性 | 显式断言 `border: none` 在测试中 |
| 收藏夹页实际首屏被新磁贴挤压 | 虚拟磁贴 + 真实收藏夹合并后**总数 +2**，前端分页用 `has_more` 判断，不影响分页逻辑 |
| 我的最爱总数缓存过期 | 加入/取消时乐观更新 +1/-1；其他场景忽略（仅作角标展示，过期影响小） |

### 9.1 YAGNI 决策（明确）

- ❌ 不做后端注入虚拟 folder（v1 方案废弃）
- ❌ 不做 `FavoriteFolder.is_system` 字段
- ❌ 不做在线随机浏览
- ❌ 不做后台扫描器自动补抓「我的最爱」
- ❌ 不做我的最爱导入/导出/分享/标签分组
- ❌ 不做 per-user 配置命名空间（单用户工具）
- ❌ 不做「我的最爱」图片编辑（重命名 tag 等）
- ❌ 不引入 `/api/v1/random` 独立路由（v1 方案废弃，复用 `/gallery/load?random=true`）
- ❌ 不新增 `RandomBrowser.vue` 组件（v1 方案废弃，直接走 Gallery 二级页）
- ❌ 不在本次迁移其他 localStorage 偏好（仅迁 5 项）
- ❌ 不动 `get_folders_with_preview` 接口

---

## 10. 实施步骤（高层）

### Phase 1：后端基础设施（无 UI 改动）

1. 新增 `models/database/my_favorite.py` + `table_constant.my_favorite`
2. 新增 `dao/my_favorite_dao.py`
3. 新增 `models/request/my_favorites.py` + `models/response/my_favorites.py`
4. 新增 `services/my_favorites.py`
5. 新增 `api/v1/my_favorites.py`（含 `/my-favorites/preview` 独立预览接口）
6. `FavoritesConfig` 注入 `Config`；扩 `services/config.py` + `api/v1/config.py`
7. 扩 `GalleryLoadRequest` 加 `include_favorite_status` + `random`；扩 `YandeData` / `YandeDataDetail` 响应模型加 `is_favorited: Optional[bool]`
8. `services/gallery.py` 实现 `load_images(include_favorite_status, random)` + `get_image_detail(include_favorite_status)`
9. **回归测试**：`services/favorites.py` `get_folders_with_preview` 不注入虚拟 folder

### Phase 2：后端测试 + LSP

10. 后端单元测试（DAO / Service / API）
11. LSP diagnostics 清洁

### Phase 3：前端 useFavoritesConfig 重构

12. 重构 `composables/useFavoritesConfig.js` 为后端 API 版本（含 4 个新开关 + myFavoritesCount 缓存）
13. `views/Config.vue` 「收藏夹」section 表单切换为 PUT /config/favorites（含 4 个新开关）
14. 前端测试（composable + Config.vue）

### Phase 4：前端组件

15. 新增 `components/HeartOverlay.vue`（**无边框**）+ `api/myFavorites.js`
16. `components/WaterfallGallery.vue` 集成 HeartOverlay + props `showHeart` + 自动加 `include_favorite_status`
17. `components/FolderTile.vue` 识别 `isVirtual` 字段
18. `components/FavoritePanel.vue` **前端 prepend** 虚拟磁贴（受开关控制）
19. `views/Gallery.vue` 新增 `querySource='my-favorites'` / `querySource='random'` 模式
20. 详情页 `ImageDetail.vue` 在 `float-header-left` 显示 HeartOverlay
21. 前端测试 + 视觉 QA

### Phase 5：联调与发布

22. 端到端验证：加我的最爱 → 自动下载 → 取消 → 重新加入
23. 验证 `enable_my_favorites=false` 时爱心 + 虚拟磁贴隐藏
24. 验证 `enable_random_browse=false` 时随机浏览磁贴隐藏
25. 验证 `enable_favorite_folder=false` 时整个收藏夹模块隐藏
26. 验证随机浏览 `ORDER BY RANDOM()` + `DISTINCT image_id` 不重复
27. **回归验证**：`get_folders_with_preview` 行为完全不变（v1 报错已消除）
28. 文档更新（README + AGENTS.md 重构状态行）
29. PR 提交 → next_dev 集成 → 发版流程（按 docs/release.md）

---

## 11. 兼容性矩阵

| 场景 | 行为 |
|---|---|
| 旧用户首次升级 | localStorage 5 个 key 作为一次性 fallback 读入；之后走后端 |
| 新用户首次安装 | config.yaml 默认值生效；前端读后端默认值 |
| `config.yaml` 中无 `favorites` 段 | Pydantic 自动用默认值（向后兼容） |
| 前端读 `enable_my_favorites=false` | HeartOverlay 不渲染；`FavoritePanel.vue` 不 prepend "我的最爱"磁贴；`/gallery/load` 不带 `include_favorite_status` |
| 后端 `enable_my_favorites=false` | 「我的最爱」POST 仍允许（开关只控 UI 渲染，不控业务行为），避免开关切换时丢数据；`/gallery/load` 强制不连表 |
| `down_flag=False` 时加入我的最爱 + `enable_favorite_autodownload=true` | 入 DownloadTask；前端 toast 提示「已加入收藏，正在下载」 |
| `down_flag=False` 时加入我的最爱 + `enable_favorite_autodownload=false` | 不入 DownloadTask；toast 仅提示「已加入收藏」 |
| 用户删除已下载图片后保留我的最爱 | 我的最爱保留（`image_id` 仍引用 YandeData 主表记录） |
| YandeData 中图片被删除 | 我的最爱中保留孤立记录（不上 UI 时无感知；清理脚本后续） |
| 随机浏览二级页翻页 | 每次都重发 `random=true`，保证新一轮随机抽样 |

---

## 12. 文档交付

| 文档 | 变更 |
|---|---|
| `docs/superpowers/specs/2026-09-20-my-favorites-and-random-browse-v2-design.md` | 本文档（新增） |
| `docs/release.md` | 版本号更新（按发版流程） |
| `README.md` | 「主要功能」新增「我的最爱」「随机浏览」 |
| `AGENTS.md` | 「重构状态追踪」追加本次变更记录 |

---

*最后更新：2026-09-20（v2 Draft，待用户审阅）*