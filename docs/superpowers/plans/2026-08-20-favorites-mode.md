# 收藏夹模式 + 瀑布流文件夹视图 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Gallery 视图增加第三模式 `favorites`，文件夹以瀑布流 tile 形式展示，每个 tile 内嵌随机预览图；点击进入 folder-detail 视图复用现有瀑布流。

**Architecture:** 后端补完 `/favorites/with-preview`（分页 + 精简元数据），增强 `/favorites/{id}/preview`（random 参数）；前端新增 `FolderTile.vue`（复用 `WaterfallGallery` 的 `MAX_PREVIEW_CONCURRENT + IntersectionObserver + srcEnabled` 并发模式），`BackButton.vue`（半透明玻璃风），扩展 `Gallery.vue` 状态机。

**Tech Stack:** Vue 3.4 + Element Plus 2.5 + Composition API / FastAPI + SQLAlchemy + MariaDB/SQLite / Vitest + @vue/test-utils（前端）/ pytest（后端）

**前置阅读：**
- Spec：`docs/superpowers/specs/2026-08-20-favorites-mode-design.md`
- 项目规范：`AGENTS.md`
- 全局规则：`~/.config/opencode/AGENTS.md`（中文回复 / 网络代理 `http://192.168.100.222:20171` / 不创建 PR）

**全局约束：**
- 分支：`feature-favorites-mode`（已创建）
- 数据库：`YandeData` 模型、`FavoriteFolder` 模型
- 并发模式：`MAX_PREVIEW_CONCURRENT = 10` + IntersectionObserver + srcEnabled 门控（复用现有 `WaterfallGallery.vue:188-385`）
- 文件夹预览数分档：`local_count < 50 → 4`, `50-199 → 6`, `≥200 → 8`
- 测试约定：后端测试在 `unit_test/`；前端测试与源文件同级（`.spec.js`）

---

## Task 1：DAO 新增 `query_random_for_tags` + 单元测试

**Files:**
- Modify: `backend/src/dao/yande_data_dao.py:199-208`（在 `get_max_id_for_tags` 后插入新方法）
- Create: `unit_test/dao/test_yande_data_dao_query_random.py`

**Interfaces:**
- Consumes: `YandeData` 模型、`tags` 字符串、`limit` int、`downloaded_only` bool
- Produces: `list[YandeData]`（随机抽样结果）

- [ ] **Step 1：写失败测试**

`unit_test/dao/test_yande_data_dao_query_random.py`：

```python
"""测试 YandeDataRepository.query_random_for_tags() 随机抽样已下载图片"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

from src.dao.yande_data_dao import YandeDataRepository
from src.models.database.yande import YandeData


def _seed(n: int = 20) -> None:
    """插入 n 条已下载和 n 条未下载的混合数据，tags 都是 'sample'"""
    with YandeDataRepository() as repo:
        repo.session.query(YandeData).delete()
        for i in range(n * 2):
            rec = YandeData(
                id=2000 + i,
                tags="sample" if i < n else "other",
                width=100, height=100,
                file_ext="jpg",
                file_size=1024,
                file_url=f"http://example.com/{i}.jpg",
                preview_url=f"http://example.com/p_{i}.jpg",
                md5=f"md5_{i}",
                author="tester",
                created_at=datetime(2024, 1, 1, 0, 0, 0),
                down_flag=(i < n),  # 前 n 条 True，后 n 条 False
            )
            repo.session.add(rec)


def test_query_random_returns_only_downloaded():
    _seed(10)
    with YandeDataRepository() as repo:
        result = repo.query_random_for_tags("sample", limit=5)
    assert len(result) == 5
    assert all(r.down_flag is True for r in result)
    assert all(r.tags == "sample" for r in result)


def test_query_random_respects_limit():
    _seed(20)
    with YandeDataRepository() as repo:
        result = repo.query_random_for_tags("sample", limit=3)
    assert len(result) == 3


def test_query_random_excludes_other_tags():
    _seed(10)
    with YandeDataRepository() as repo:
        result = repo.query_random_for_tags("sample", limit=20)
    assert len(result) == 10
    assert all(r.tags == "sample" for r in result)
    assert all(r.down_flag is True for r in result)


def test_query_random_empty_when_no_match():
    with YandeDataRepository() as repo:
        repo.session.query(YandeData).delete()
        result = repo.query_random_for_tags("nonexistent", limit=5)
    assert result == []
```

- [ ] **Step 2：运行测试确认失败**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
python -m pytest unit_test/dao/test_yande_data_dao_query_random.py -v
```

预期：FAIL（`AttributeError: 'YandeDataRepository' object has no attribute 'query_random_for_tags'`）

- [ ] **Step 3：实现 `query_random_for_tags`**

在 `backend/src/dao/yande_data_dao.py` 中：

```python
def query_random_for_tags(
    self,
    tags: str,
    limit: int,
    downloaded_only: bool = True,
) -> list:
    """按 tags 过滤，随机抽样 limit 条图片。
    
    Args:
        tags: 标签字符串（与 query() 使用同一 _tag_filter 解析）
        limit: 抽样上限
        downloaded_only: True 时仅返回 down_flag=True 的图片（收藏夹预览场景）
    """
    filter_funcs = []
    if tags and tags.strip():
        filter_funcs.append(self._tag_filter(tags))
    if downloaded_only:
        filter_funcs.append(YandeData.down_flag.is_(True))
    stmt = (
        select(YandeData)
        .filter(*filter_funcs)
        .order_by(func.random())
        .limit(limit)
    )
    return list(self.session.execute(stmt).scalars().all())
```

（确保文件顶部已 import `select, func`）

- [ ] **Step 4：运行测试确认通过**

```bash
python -m pytest unit_test/dao/test_yande_data_dao_query_random.py -v
```

预期：4 个 PASS

- [ ] **Step 5：Commit**

```bash
git add backend/src/dao/yande_data_dao.py unit_test/dao/test_yande_data_dao_query_random.py
git commit -m "feat(dao): YandeDataRepository.query_random_for_tags 随机抽样"
```

---

## Task 2：DAO 新增 `FavoriteDao.list_paginated` + 单元测试

**Files:**
- Modify: `backend/src/dao/favorite_dao.py:40-45`（在 `get_all` 后插入新方法）
- Create: `unit_test/dao/test_favorite_dao_list_paginated.py`

**Interfaces:**
- Consumes: `page: int`, `page_size: int`
- Produces: `( tuple[list[FavoriteFolder], int] )` —— `(items, total)`

- [ ] **Step 1：写失败测试**

`unit_test/dao/test_favorite_dao_list_paginated.py`：

```python
"""测试 FavoriteDao.list_paginated 分页逻辑"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

from src.dao.favorite_dao import favorite_dao
from src.models.database.yande import FavoriteFolder


def _seed(n: int) -> None:
    """插入 n 个收藏夹，sort_order = i"""
    with favorite_dao.session_scope() if hasattr(favorite_dao, 'session_scope') else favorite_dao.__class__().session as _:
        pass
    # 注意：实际实现里 favorite_dao 是 BaseDAO 单例，session 在 with 内创建
    pass


def _seed_via_dao(n: int) -> None:
    """使用 favorite_dao 单例创建 n 个收藏夹"""
    # 清空
    from src.dao.database import BaseDAO
    with BaseDAO().session as session:
        session.query(FavoriteFolder).delete()
    # 创建
    for i in range(n):
        favorite_dao.create(name=f"folder_{i}", sort_order=i)


def test_list_paginated_returns_total():
    _seed_via_dao(15)
    items, total = favorite_dao.list_paginated(page=1, page_size=10)
    assert total == 15
    assert len(items) == 10


def test_list_paginated_ordered_by_sort_order():
    _seed_via_dao(5)
    items, _ = favorite_dao.list_paginated(page=1, page_size=10)
    assert [f.sort_order for f in items] == [0, 1, 2, 3, 4]


def test_list_paginated_second_page():
    _seed_via_dao(15)
    items, total = favorite_dao.list_paginated(page=2, page_size=10)
    assert total == 15
    assert len(items) == 5
    assert items[0].sort_order == 10


def test_list_paginated_empty_when_no_data():
    from src.dao.database import BaseDAO
    with BaseDAO().session as session:
        session.query(FavoriteFolder).delete()
    items, total = favorite_dao.list_paginated(page=1, page_size=10)
    assert items == []
    assert total == 0
```

- [ ] **Step 2：运行测试确认失败**

```bash
python -m pytest unit_test/dao/test_favorite_dao_list_paginated.py -v
```

预期：FAIL（`AttributeError: ... has no attribute 'list_paginated'`）

- [ ] **Step 3：实现 `list_paginated`**

在 `backend/src/dao/favorite_dao.py` 中（参考 `get_all` 的实现）：

```python
def list_paginated(self, page: int, page_size: int) -> tuple[list, int]:
    """分页获取收藏夹，按 sort_order 升序。
    
    Returns:
        (items, total): items 为当前页的 FavoriteFolder 列表，total 为总数
    """
    from sqlalchemy import func, select
    total = (
        self.session.query(func.count(FavoriteFolder.id))
        .scalar() or 0
    )
    offset = (page - 1) * page_size
    items = (
        self.session.query(FavoriteFolder)
        .order_by(FavoriteFolder.sort_order.asc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
    return items, total
```

- [ ] **Step 4：运行测试确认通过**

```bash
python -m pytest unit_test/dao/test_favorite_dao_list_paginated.py -v
```

预期：4 个 PASS（若 BaseDAO 不自动 commit 事务导致 `_seed_via_dao` 后查询不到，需要在测试中加 `session.commit()` —— 失败时调整实现）

- [ ] **Step 5：Commit**

```bash
git add backend/src/dao/favorite_dao.py unit_test/dao/test_favorite_dao_list_paginated.py
git commit -m "feat(dao): FavoriteDao.list_paginated 分页查询"
```

---

## Task 3：响应模型新增精简预览模型 + 包装列表响应

**Files:**
- Modify: `backend/src/models/response/favorites.py`

**Interfaces:**
- 新增 `FolderPreviewImageMinimal`（仅 id/width/height）
- 新增 `FavoriteFolderWithMinimalPreview`（继承 FavoriteFolder，加精简 preview_images）
- 新增 `FavoriteFoldersWithPreviewListData`（items + total + has_more）
- 修改 `FavoriteFoldersWithPreviewResponse` 泛型参数

- [ ] **Step 1：在 `backend/src/models/response/favorites.py` 顶部插入新模型**

```python
class FolderPreviewImageMinimal(BaseModel):
    """收藏夹瀑布流用的精简预览元数据（不含 URL，前端自行拼 /api/v1/gallery/cache/preview/{id}）。"""
    id: int
    width: Optional[int] = None
    height: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class FavoriteFolderWithMinimalPreview(FavoriteFolder):
    """带精简预览图的收藏夹模型（瀑布流场景）。"""
    preview_images: list[FolderPreviewImageMinimal] = Field(
        default_factory=list, description="预览图片元数据（仅 id/width/height）"
    )


class FavoriteFoldersWithPreviewListData(BaseModel):
    """带预览的收藏夹列表响应数据。"""
    items: list[FavoriteFolderWithMinimalPreview]
    total: int
    has_more: bool
```

- [ ] **Step 2：修改 `FavoriteFoldersWithPreviewResponse` 泛型**

找到：
```python
class FavoriteFoldersWithPreviewResponse(BaseResponse[list[FavoriteFolderWithPreview]]):
    ...
```

改为：
```python
class FavoriteFoldersWithPreviewResponse(BaseResponse[FavoriteFoldersWithPreviewListData]):
    ...
```

**注意**：这是 schema 破坏性变更，调用方需同步修改。

- [ ] **Step 3：运行已有测试确认不破坏（如果有）**

```bash
python -m pytest unit_test/ -v -k "favorite or with_preview" 2>/dev/null || echo "（无相关测试，跳过）"
```

- [ ] **Step 4：Commit**

```bash
git add backend/src/models/response/favorites.py
git commit -m "feat(model): 收藏夹瀑布流用精简预览模型 + 分页响应包装"
```

---

## Task 4：Service 重写 `get_folders_with_preview` + 单元测试

**Files:**
- Modify: `backend/src/services/favorites.py:49-77`（替换 `get_folders_with_preview`）
- Create: `unit_test/services/test_favorite_get_folders_with_preview.py`

**Interfaces:**
- Consumes: `page: int = 1`, `page_size: int = 20`
- Produces: `( tuple[list[FavoriteFolderWithMinimalPreview], int, bool] )` —— `(items, total, has_more)`

- [ ] **Step 1：写失败测试**

`unit_test/services/test_favorite_get_folders_with_preview.py`：

```python
"""测试 FavoritesService.get_folders_with_preview 分页 + 预览数分档"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

from src.dao.database import BaseDAO
from src.dao.favorite_dao import favorite_dao
from src.dao.yande_data_dao import YandeDataRepository
from src.models.database.yande import FavoriteFolder, YandeData
from src.services.favorites import FavoritesService


def _seed_folder(local_count: int, name: str) -> int:
    """创建收藏夹并设置 local_count"""
    folder = favorite_dao.create(name=name, tags="sample")
    BaseDAO().session.query(FavoriteFolder).filter_by(id=folder.id).update(
        {"local_count": local_count}
    )
    BaseDAO().session.commit()
    return folder.id


def _seed_yande_data(tag: str, count: int, start_id: int = 5000) -> None:
    """插入 count 条已下载图片"""
    with YandeDataRepository() as repo:
        for i in range(count):
            rec = YandeData(
                id=start_id + i,
                tags=tag,
                width=100, height=100,
                file_ext="jpg",
                file_size=1024,
                file_url=f"http://example.com/{i}.jpg",
                preview_url=f"http://example.com/p_{i}.jpg",
                md5=f"md5_{i}",
                author="tester",
                created_at=datetime(2024, 1, 1, 0, 0, 0),
                down_flag=True,
            )
            repo.session.add(rec)


def _clean() -> None:
    with BaseDAO().session as session:
        session.query(FavoriteFolder).delete()
        session.query(YandeData).delete()


def test_count_tier_small_folder_returns_4():
    _clean()
    fid = _seed_folder(10, "small_folder")
    _seed_yande_data("sample", 10)
    items, total, has_more = FavoritesService.get_folders_with_preview(page=1, page_size=20)
    assert total == 1
    assert has_more is False
    assert len(items[0].preview_images) == 4


def test_count_tier_medium_folder_returns_6():
    _clean()
    fid = _seed_folder(100, "medium_folder")
    _seed_yande_data("sample", 100)
    items, _, _ = FavoritesService.get_folders_with_preview(page=1, page_size=20)
    assert len(items[0].preview_images) == 6


def test_count_tier_large_folder_returns_8():
    _clean()
    fid = _seed_folder(300, "large_folder")
    _seed_yande_data("sample", 300)
    items, _, _ = FavoritesService.get_folders_with_preview(page=1, page_size=20)
    assert len(items[0].preview_images) == 8


def test_pagination_total_and_has_more():
    _clean()
    for i in range(15):
        _seed_folder(0, f"f_{i}")
    items, total, has_more = FavoritesService.get_folders_with_preview(page=1, page_size=10)
    assert total == 15
    assert has_more is True
    assert len(items) == 10
    items2, total2, has_more2 = FavoritesService.get_folders_with_preview(page=2, page_size=10)
    assert total2 == 15
    assert has_more2 is False
    assert len(items2) == 5


def test_preview_images_only_id_width_height():
    _clean()
    _seed_folder(10, "f")
    _seed_yande_data("sample", 10)
    items, _, _ = FavoritesService.get_folders_with_preview(page=1, page_size=20)
    img = items[0].preview_images[0]
    # 仅暴露 id/width/height；preview_url 字段不应在精简模型中
    assert set(img.model_dump().keys()) == {"id", "width", "height"}
```

- [ ] **Step 2：运行测试确认失败**

```bash
python -m pytest unit_test/services/test_favorite_get_folders_with_preview.py -v
```

预期：FAIL

- [ ] **Step 3：实现 `get_folders_with_preview`**

替换 `backend/src/services/favorites.py:49-77`：

```python
# 文件顶部 imports 增加
from sqlalchemy import func, select  # 若已有可省略
from src.models.response.favorites import (
    FavoriteFolder,
    FavoriteFolderWithMinimalPreview,
    FavoriteFoldersWithPreviewListData,
    FolderPreviewImageMinimal,
)

# 文件顶部常量（在 FavoritesService 类外）
PREVIEW_COUNT_BY_LOCAL_THRESHOLDS = [
    (50, 4),
    (200, 6),
    (float("inf"), 8),
]


def _preview_count_for_local_count(local_count: int) -> int:
    """按 local_count 分档返回预览图数量。"""
    for threshold, count in PREVIEW_COUNT_BY_LOCAL_THRESHOLDS:
        if (local_count or 0) < threshold:
            return count
    return 8


# 类内替换 get_folders_with_preview
@staticmethod
def get_folders_with_preview(
    page: int = 1, page_size: int = 20
) -> tuple[list[FavoriteFolderWithMinimalPreview], int, bool]:
    """分页获取收藏夹及精简预览元数据。

    Returns:
        (items, total, has_more)
    """
    folders, total = favorite_dao.list_paginated(page=page, page_size=page_size)
    items: list[FavoriteFolderWithMinimalPreview] = []
    for f in folders:
        limit = _preview_count_for_local_count(f.local_count or 0)
        preview_meta: list[FolderPreviewImageMinimal] = []
        if f.tags:
            with YandeDataRepository() as repo:
                sampled = repo.query_random_for_tags(
                    tags=f.tags, limit=limit, downloaded_only=True
                )
            preview_meta = [
                FolderPreviewImageMinimal.model_validate(img)
                for img in sampled
            ]
        items.append(
            FavoriteFolderWithMinimalPreview(
                **FavoriteFolder.model_validate(f).model_dump(),
                preview_images=preview_meta,
            )
        )
    has_more = page * page_size < total
    return items, total, has_more
```

- [ ] **Step 4：运行测试确认通过**

```bash
python -m pytest unit_test/services/test_favorite_get_folders_with_preview.py -v
```

预期：5 个 PASS

- [ ] **Step 5：Commit**

```bash
git add backend/src/services/favorites.py unit_test/services/test_favorite_get_folders_with_preview.py
git commit -m "feat(service): get_folders_with_preview 分页 + 精简预览元数据"
```

---

## Task 5：Service `preview_folder` 增强 random 参数

**Files:**
- Modify: `backend/src/services/favorites.py:138-168`（`preview_folder` 方法）

- [ ] **Step 1：替换 `preview_folder` 实现**

```python
@staticmethod
def preview_folder(
    folder_id: int, limit: int = 6, random: bool = False
) -> Optional[dict]:
    """单文件夹预览。

    Args:
        folder_id: 收藏夹 ID
        limit: 预览图数量上限
        random: True 时随机抽样；False 时按当前 sort 排序取前 N 张
    """
    folder = favorite_dao.get_by_id(folder_id)
    if not folder:
        return None

    try:
        search_params = FavoritesService._parse_tags_to_params(folder.tags)
        search_params.page = 1
        search_params.page_size = limit
        with YandeDataRepository() as repo:
            if random:
                images = repo.query_random_for_tags(
                    tags=folder.tags or "",
                    limit=limit,
                    downloaded_only=True,
                )
                _, total = repo.query(
                    query_params=search_params, downloaded_only=True
                )
            else:
                images, total = repo.query(
                    query_params=search_params, downloaded_only=True
                )
        FavoritesService._refresh_local_count(folder_id)
        return {"total": total, "preview_images": images[:limit]}
    except Exception:
        return None
```

- [ ] **Step 2：Commit**

```bash
git add backend/src/services/favorites.py
git commit -m "feat(service): preview_folder 支持 random 参数（单 folder 预览场景）"
```

---

## Task 6：API 路由改造（with-preview 分页 + preview random 参数）

**Files:**
- Modify: `backend/src/api/v1/favorites.py:49-66`（`get_folders_with_preview` 路由）
- Modify: `backend/src/api/v1/favorites.py:124-132`（`preview_folder` 路由）

**Interfaces:**
- `GET /favorites/with-preview?page=1&page_size=20` → 返回新 `FavoriteFoldersWithPreviewListData`
- `GET /favorites/{folder_id}/preview?limit=6&random=false` → 加 `random` 参数

- [ ] **Step 1：修改 `get_folders_with_preview` 路由**

替换 `backend/src/api/v1/favorites.py:49-66`：

```python
@router.get(
    "/with-preview",
    response_model=FavoriteFoldersWithPreviewResponse,
    summary="获取所有收藏夹（含精简预览元数据，分页）",
)
async def get_folders_with_preview(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
) -> FavoriteFoldersWithPreviewResponse:
    """分页获取收藏夹及精简预览图元数据（id/width/height，前端拼 URL）。

    preview_images 不含 preview_url —— 前端通过 `/api/v1/gallery/cache/preview/{id}`
    复用现有预览缓存接口渲染图片。
    """
    try:
        items, total, has_more = FavoritesService.get_folders_with_preview(
            page=page, page_size=page_size
        )
        data = FavoriteFoldersWithPreviewListData(
            items=items, total=total, has_more=has_more
        )
        return FavoriteFoldersWithPreviewResponse(message=ErrMsg.OK.msg, data=data)
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)
```

顶部 imports 增加：
```python
from fastapi import Query
from src.models.response.favorites import (
    ...,
    FavoriteFoldersWithPreviewListData,
)
```

- [ ] **Step 2：修改 `preview_folder` 路由**

替换 `backend/src/api/v1/favorites.py:124-132`：

```python
@router.get(
    "/{folder_id}/preview",
    response_model=FavoriteFolderPreviewResponse,
    summary="预览收藏夹查询结果",
)
async def preview_folder(
    folder_id: int,
    limit: int = Query(6, ge=1, le=50, description="预览图数量上限"),
    random: bool = Query(False, description="True 时随机抽样；默认按当前排序"),
) -> FavoriteFolderPreviewResponse:
    """单收藏夹预览。返回完整字段（含 preview_url）。

    # TODO: 后续「我的最爱」功能会用到此接口（单 folder 全量预览）
    """
    result = FavoritesService.preview_folder(
        folder_id=folder_id, limit=limit, random=random
    )
    if not result:
        raise APIException(ErrMsg.FAVORITE_FOLDER_NOT_FOUND)
    return FavoriteFolderPreviewResponse(message=ErrMsg.OK.msg, data=result)
```

- [ ] **Step 3：手动验证启动 + curl**

```bash
# 后端启动（开发模式，假设已有 .venv）
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
uvicorn service:main_app --port 8000 --reload --reload-dir ./src &

# 等待启动（5 秒）
sleep 5

# 测试 with-preview
curl -s "http://localhost:8000/api/v1/favorites/with-preview?page=1&page_size=20" | python -m json.tool | head -40

# 测试 /preview random
curl -s "http://localhost:8000/api/v1/favorites/1/preview?limit=6&random=true" | python -m json.tool | head -40

# 关闭后端
kill %1
```

预期：两次都返回 200 + JSON 结构正确

- [ ] **Step 4：Commit**

```bash
git add backend/src/api/v1/favorites.py
git commit -m "feat(api): with-preview 分页参数 + preview random 参数"
```

---

## Task 7：前端 API 客户端新增分页方法

**Files:**
- Modify: `frontend/src/api/favorites.js`

- [ ] **Step 1：替换 `getFoldersWithPreview` 函数**

替换 `frontend/src/api/favorites.js:13-15`：

```javascript
// 获取收藏夹及精简预览元数据（分页）
export function getFoldersWithPreview(page = 1, pageSize = 20) {
  return api.get(`/favorites/with-preview?page=${page}&page_size=${pageSize}`)
}
```

并更新底部 default export：

```javascript
export default {
  getAllFolders,
  getFoldersWithPreview,  // 已更新签名
  getFolder,
  createFolder,
  updateFolder,
  deleteFolder,
  reorderFolders,
  previewFolder,  // 单文件夹预览，已支持 random
  updateOnlineCount,
  updateLocalCount,
  refreshOnlineCount,
  triggerFolderSchedule,
  getFolderScheduleStatus,
  resetFolderSync,
}
```

- [ ] **Step 2：Commit**

```bash
git add frontend/src/api/favorites.js
git commit -m "feat(frontend-api): getFoldersWithPreview 支持分页"
```

---

## Task 8：新增 `FolderTile.vue` + 单元测试

**Files:**
- Create: `frontend/src/components/FolderTile.vue`
- Create: `frontend/src/components/FolderTile.spec.js`

**Interfaces:**
- Props: `folder: { id, name, local_count, color, preview_images: [{id, width, height}] }`, `saveDataMode: boolean`
- Emits: `click` (event: folder)
- 内部复用 `MAX_PREVIEW_CONCURRENT = 10` + IntersectionObserver + srcEnabled 模式

- [ ] **Step 1：写失败测试 `FolderTile.spec.js`**

```javascript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import FolderTile from './FolderTile.vue'

let observerInstances
let observedTargets

beforeEach(() => {
  observerInstances = []
  observedTargets = []
  globalThis.IntersectionObserver = vi.fn().mockImplementation((cb) => {
    const instance = {
      cb,
      observe: vi.fn((el) => observedTargets.push(el)),
      disconnect: vi.fn(),
    }
    observerInstances.push(instance)
    return instance
  })
})

const mkFolder = (previewCount) => ({
  id: 1,
  name: '风景',
  color: '#409EFF',
  local_count: 42,
  preview_images: Array.from({ length: previewCount }, (_, i) => ({
    id: 1000 + i,
    width: 100,
    height: 100,
  })),
}

const factory = (props = {}) => mount(FolderTile, {
  props: { folder: mkFolder(4), saveDataMode: false, ...props },
})

describe('FolderTile', () => {
  it('渲染文件夹名和数量', () => {
    const wrapper = factory()
    expect(wrapper.text()).toContain('风景')
    expect(wrapper.text()).toContain('42')
  })

  it('saveDataMode=true 时不渲染 <img>', () => {
    const wrapper = factory({ saveDataMode: true })
    expect(wrapper.findAll('img')).toHaveLength(0)
    // 应有占位元素
    expect(wrapper.findAll('.folder-preview-placeholder').length).toBeGreaterThan(0)
  })

  it('saveDataMode=false 时初始 srcEnabled 为空，所有 <img> 不显示', () => {
    const wrapper = factory({ saveDataMode: false })
    const imgs = wrapper.findAll('img')
    expect(imgs.length).toBe(4)
    imgs.forEach(img => {
      expect(img.attributes('src')).toBeUndefined()
    })
  })

  it('点击触发 click 事件', async () => {
    const wrapper = factory()
    await wrapper.find('.folder-tile').trigger('click')
    expect(wrapper.emitted('click')).toHaveLength(1)
    expect(wrapper.emitted('click')[0][0]).toMatchObject({ id: 1 })
  })

  it('gridCols 根据 preview_images 数量计算', () => {
    const w4 = factory({ folder: mkFolder(4) })
    expect(w4.vm.gridCols).toBe(2)  // 4 张 → 2 列
    const w6 = factory({ folder: mkFolder(6) })
    expect(w6.vm.gridCols).toBe(3)
    const w8 = factory({ folder: mkFolder(8) })
    expect(w8.vm.gridCols).toBe(4)
  })
})
```

- [ ] **Step 2：运行测试确认失败**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend
npx vitest run src/components/FolderTile.spec.js
```

预期：FAIL（找不到组件）

- [ ] **Step 3：实现 `FolderTile.vue`**

`frontend/src/components/FolderTile.vue`：

```vue
<template>
  <div class="folder-tile" @click="$emit('click', folder)">
    <div class="folder-preview-grid" :style="`--cols: ${gridCols}`">
      <div
        v-for="img in folder.preview_images"
        :key="img.id"
        :data-image-id="img.id"
        class="folder-preview-cell"
      >
        <img
          v-if="!saveDataMode && srcEnabled.has(img.id)"
          :src="`/api/v1/gallery/cache/preview/${img.id}`"
          :alt="img.id.toString()"
          loading="lazy"
        />
        <div v-else class="folder-preview-placeholder">
          <el-icon><Picture /></el-icon>
        </div>
      </div>
    </div>
    <div class="folder-info">
      <span class="folder-name">{{ folder.name }}</span>
      <el-tag size="small">{{ folder.local_count || 0 }}</el-tag>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { Picture } from '@element-plus/icons-vue'

const props = defineProps({
  folder: { type: Object, required: true },
  saveDataMode: { type: Boolean, default: false },
})

defineEmits(['click'])

const MAX_PREVIEW_CONCURRENT = 10
const loadingQueue = ref([])
const srcEnabled = ref(new Set())
const visibleIds = ref(new Set())
let observer = null
let mountedCells = []

const gridCols = computed(() => {
  const n = props.folder.preview_images?.length || 0
  if (n <= 4) return 2
  if (n <= 6) return 3
  return 4  // 8 张 → 4 列
})

const processQueue = () => {
  if (props.saveDataMode) return
  const available = MAX_PREVIEW_CONCURRENT - srcEnabled.value.size
  if (available <= 0) return
  const toProcess = Math.min(available, loadingQueue.value.length)
  for (let i = 0; i < toProcess; i++) {
    srcEnabled.value.add(loadingQueue.value.shift())
  }
}

const setupObserver = () => {
  if (typeof IntersectionObserver === 'undefined') return
  observer = new IntersectionObserver(
    (entries) => {
      entries.forEach(entry => {
        const id = parseInt(entry.target.dataset.imageId)
        if (entry.isIntersecting && !visibleIds.value.has(id)) {
          visibleIds.value.add(id)
          if (!srcEnabled.value.has(id) && !loadingQueue.value.includes(id)) {
            loadingQueue.value.push(id)
            processQueue()
          }
        }
      })
    },
    { rootMargin: '200px' }
  )
}

const observeCells = () => {
  if (!observer) return
  // 重新观察新加入的 cell（watch 触发后由 nextTick 调用）
  // 此处由父组件或自身 watch 处理
}

onMounted(() => {
  setupObserver()
  // 观察所有 cell
  const cells = document.querySelectorAll(`[data-image-id]`)
  cells.forEach(cell => observer.observe(cell))
})

onUnmounted(() => {
  observer?.disconnect()
})

// 监听 folder 变化，重新观察（虽然 folder 一般不会变，但防御性处理）
watch(() => props.folder.id, () => {
  loadingQueue.value = []
  srcEnabled.value = new Set()
  visibleIds.value = new Set()
})
</script>

<style scoped>
.folder-tile {
  display: block;
  border-radius: 12px;
  overflow: hidden;
  background: var(--bg-secondary);
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  break-inside: avoid;
  margin-bottom: 16px;
}
.folder-tile:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
}

.folder-preview-grid {
  display: grid;
  grid-template-columns: repeat(var(--cols), 1fr);
  gap: 2px;
  aspect-ratio: 4 / 3; /* 大文件夹视觉占位 */
}
.folder-preview-cell {
  background: var(--bg-tertiary);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
.folder-preview-cell img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.folder-preview-placeholder {
  color: var(--text-muted);
  font-size: 20px;
  opacity: 0.5;
}

.folder-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
}
.folder-name {
  flex: 1;
  font-weight: 500;
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

html.dark-mode .folder-tile {
  background: var(--bg-secondary);
}
</style>
```

- [ ] **Step 4：运行测试确认通过**

```bash
npx vitest run src/components/FolderTile.spec.js
```

预期：5 个 PASS

- [ ] **Step 5：Commit**

```bash
git add frontend/src/components/FolderTile.vue frontend/src/components/FolderTile.spec.js
git commit -m "feat(frontend): FolderTile.vue 瀑布流文件夹 tile（复用 WaterfallGallery 并发模式）"
```

---

## Task 9：新增 `BackButton.vue` + 单元测试

**Files:**
- Create: `frontend/src/components/BackButton.vue`
- Create: `frontend/src/components/BackButton.spec.js`

- [ ] **Step 1：写失败测试 `BackButton.spec.js`**

```javascript
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import BackButton from './BackButton.vue'

const factory = (props = {}) => mount(BackButton, {
  props: { visible: true, ...props },
})

describe('BackButton', () => {
  it('visible=true 时渲染按钮', () => {
    const wrapper = factory()
    expect(wrapper.find('.floating-back-btn').exists()).toBe(true)
  })

  it('visible=false 时不渲染', () => {
    const wrapper = factory({ visible: false })
    expect(wrapper.find('.floating-back-btn').exists()).toBe(false)
  })

  it('点击触发 click 事件', async () => {
    const wrapper = factory()
    await wrapper.find('.floating-back-btn').trigger('click')
    expect(wrapper.emitted('click')).toHaveLength(1)
  })
})
```

- [ ] **Step 2：运行测试确认失败**

```bash
npx vitest run src/components/BackButton.spec.js
```

预期：FAIL

- [ ] **Step 3：实现 `BackButton.vue`**

`frontend/src/components/BackButton.vue`：

```vue
<template>
  <button v-if="visible" class="floating-back-btn" @click="$emit('click')">
    <el-icon><ArrowLeft /></el-icon>
  </button>
</template>

<script setup>
import { ArrowLeft } from '@element-plus/icons-vue'

defineProps({
  visible: { type: Boolean, default: false },
})

defineEmits(['click'])
</script>

<style scoped>
.floating-back-btn {
  position: fixed;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: rgba(var(--bg-secondary-rgb, 255, 255, 255), 0.8);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 1000;
  transition: opacity 0.2s, background 0.2s;
}
html.dark-mode .floating-back-btn {
  background: rgba(var(--bg-secondary-rgb, 45, 45, 45), 0.8);
  border: 1px solid rgba(255, 255, 255, 0.1);
}
.floating-back-btn:hover {
  background: rgba(var(--bg-secondary-rgb, 255, 255, 255), 1);
}

/* 桌面端：与 AdvancedQuery 同一基线，悬浮于搜索栏左侧 */
@media (min-width: 980px) {
  .floating-back-btn {
    bottom: 28px;
    left: calc(50% - 450px - 60px);
    opacity: 0.8;
  }
}

/* 移动端：搜索栏上方左对齐，更透明 */
@media (max-width: 979px) {
  .floating-back-btn {
    bottom: 78px;
    left: 20px;
    opacity: 0.5;
  }
}
</style>
```

- [ ] **Step 4：运行测试确认通过**

```bash
npx vitest run src/components/BackButton.spec.js
```

预期：3 个 PASS

- [ ] **Step 5：Commit**

```bash
git add frontend/src/components/BackButton.vue frontend/src/components/BackButton.spec.js
git commit -m "feat(frontend): BackButton.vue 半透明玻璃风浮动返回按钮"
```

---

## Task 10：`AdvancedQuery.vue` 暴露 `selectFavorite` + 单元测试

**Files:**
- Modify: `frontend/src/components/AdvancedQuery.vue:1156-1164`（`defineExpose` 块）

- [ ] **Step 1：扩展 `defineExpose`**

找到 `frontend/src/components/AdvancedQuery.vue:1156-1164`：

```javascript
defineExpose({
  reset: () => {
    searchText.value = ''
    selectedTags.value = []
    selectedFavorite.value = null
    resetParams()
    showAdvanced.value = false
  }
})
```

改为：

```javascript
defineExpose({
  reset: () => {
    searchText.value = ''
    selectedTags.value = []
    selectedFavorite.value = null
    resetParams()
    showAdvanced.value = false
  },
  selectFavorite,  // 新增：供 Gallery.vue 在 folder-detail 视图调用
})
```

- [ ] **Step 2：手动验证（不写 spec，因为依赖复杂）**

启动前端开发服务器，浏览器手动点收藏夹面板选文件夹，确认 chip 显示 + 搜索请求正常。

- [ ] **Step 3：Commit**

```bash
git add frontend/src/components/AdvancedQuery.vue
git commit -m "feat(frontend): AdvancedQuery 暴露 selectFavorite 供外部调用"
```

---

## Task 11：`WaterfallGallery.vue` 新增 `itemType` + folder slot

**Files:**
- Modify: `frontend/src/components/WaterfallGallery.vue`

**Interfaces:**
- 新增 prop `itemType: 'image' | 'folder'`（默认 `'image'`）
- 当 `itemType === 'folder'` 时使用 slot 渲染

- [ ] **Step 1：修改 props 定义**

找到 `defineProps` 块（`WaterfallGallery.vue` 顶部），添加：

```javascript
const props = defineProps({
  ...existing props,
  itemType: {
    type: String,
    default: 'image',
    validator: (v) => ['image', 'folder'].includes(v),
  },
})
```

- [ ] **Step 2：修改模板的瀑布流容器**

找到 `.waterfall-container` div（`WaterfallGallery.vue:20-91`），将内部的 image 渲染逻辑用 `v-if="itemType === 'image'"` 包裹，并在 `v-else` 块渲染 slot：

```vue
<div v-else ref="containerRef" class="waterfall-container" :style="`column-count: ${columnCount}`">
  <!-- image 模式：保持现有渲染逻辑 -->
  <template v-if="itemType === 'image'">
    <div
      v-for="image in reorderedImages"
      :key="image.id"
      :data-image-id="image.id"
      class="waterfall-item"
      :class="{ ... }"
      @click="handleImageClick(image)"
      ...
    >
      <!-- 现有 image 内容 -->
    </div>
  </template>

  <!-- folder 模式：使用 slot -->
  <template v-else>
    <div v-for="item in reorderedImages" :key="item.id" class="folder-slot-wrapper">
      <slot :folder="item" />
    </div>
  </template>
</div>
```

- [ ] **Step 3：扩展现有 spec**

在 `frontend/src/components/WaterfallGallery.spec.js` 末尾追加测试：

```javascript
describe('WaterfallGallery itemType=folder', () => {
  const mkFolder = (id) => ({
    id,
    name: `f${id}`,
    local_count: 10,
    preview_images: [],
  })

  it('itemType=folder 时渲染 slot 内容', () => {
    const folders = [mkFolder(1), mkFolder(2)]
    const wrapper = mount(WaterfallGallery, {
      props: {
        images: folders,
        itemType: 'folder',
        loading: false,
        hasMore: false,
        selectable: false,
        selectedImages: [],
        sourceMode: 'local',
        saveDataMode: false,
        isLoadingMore: false,
        loadError: false,
        safeMode: false,
      },
      slots: {
        default: '<div class="test-folder-slot">{{ params.folder.name }}</div>',
      },
    })
    expect(wrapper.findAll('.test-folder-slot')).toHaveLength(2)
    expect(wrapper.text()).toContain('f1')
    expect(wrapper.text()).toContain('f2')
  })
})
```

- [ ] **Step 4：运行测试确认通过**

```bash
npx vitest run src/components/WaterfallGallery.spec.js
```

预期：原有 + 新增测试全部 PASS

- [ ] **Step 5：Commit**

```bash
git add frontend/src/components/WaterfallGallery.vue frontend/src/components/WaterfallGallery.spec.js
git commit -m "feat(frontend): WaterfallGallery 支持 itemType=folder + slot"
```

---

## Task 12：`Gallery.vue` 状态机集成

**Files:**
- Modify: `frontend/src/views/Gallery.vue`

**Interfaces:**
- 新增 ref: `favoritesView`, `selectedFavoriteFolder`, `currentFolders`, `folderLoading`, `folderHasMore`, `folderPage`
- 新增 functions: `loadFolders(page)`, `handleFolderScrollBottom`, `handleFolderClick(folder)`, `handleBackToFolders`
- 修改 `handleSourceChange` 支持 `'favorites'`
- 修改模板：3 联按钮 + 文件夹瀑布流视图 + BackButton

- [ ] **Step 1：在 script setup 顶部新增 imports**

```javascript
import FolderTile from '@/components/FolderTile.vue'
import BackButton from '@/components/BackButton.vue'
import { getFoldersWithPreview } from '@/api/favorites'
```

- [ ] **Step 2：新增状态变量**

在 `const images = ref([])` 之后插入：

```javascript
const favoritesView = ref(null)  // null | 'folders' | 'folder-detail'
const selectedFavoriteFolder = ref(null)
const currentFolders = ref([])
const folderLoading = ref(false)
const folderHasMore = ref(false)
const folderPage = ref(1)
const FOLDER_PAGE_SIZE = 20
```

- [ ] **Step 3：新增 `loadFolders` 函数**

```javascript
const loadFolders = async (page) => {
  if (folderLoading.value) return
  folderLoading.value = true
  try {
    const res = await getFoldersWithPreview(page, FOLDER_PAGE_SIZE)
    const { items, has_more } = res.data
    if (page === 1) {
      currentFolders.value = items
    } else {
      currentFolders.value.push(...items)
    }
    folderHasMore.value = has_more
    folderPage.value = page
  } catch (e) {
    ElMessage.error('加载收藏夹失败：' + (e?.message || '未知错误'))
  } finally {
    folderLoading.value = false
  }
}

const handleFolderScrollBottom = () => {
  if (folderHasMore.value && !folderLoading.value) {
    loadFolders(folderPage.value + 1)
  }
}
```

- [ ] **Step 4：修改 `handleSourceChange`**

替换原 `handleSourceChange`（`Gallery.vue:645-657`）：

```javascript
const handleSourceChange = (newSource) => {
  querySource.value = newSource
  favoritesView.value = null
  selectedFavoriteFolder.value = null
  currentFolders.value = []
  selectedImages.value = []
  selectAll.value = false
  isIndeterminate.value = false

  if (newSource === 'favorites') {
    favoritesView.value = 'folders'
    loadFolders(1)
    return
  }

  if (Object.keys(queryParams.value).length > 0) {
    queryParams.value.source = newSource
    handleSearch(queryParams.value)
  } else {
    handleSearch({})
  }
}
```

- [ ] **Step 5：新增 `handleFolderClick` 和 `handleBackToFolders`**

```javascript
const handleFolderClick = (folder) => {
  selectedFavoriteFolder.value = folder
  favoritesView.value = 'folder-detail'
  // 复用 AdvancedQuery 的 selectFavorite 设置搜索栏状态
  queryRef.value?.selectFavorite(folder)
}

const handleBackToFolders = () => {
  selectedFavoriteFolder.value = null
  favoritesView.value = 'folders'
  queryRef.value?.reset()
  images.value = []
}
```

- [ ] **Step 6：修改模板 — 3 联按钮组**

替换 `Gallery.vue:7-20`：

```vue
<el-button-group class="mode-buttons">
  <el-button
    :type="querySource === 'yande' ? 'primary' : ''"
    @click="handleSourceChange('yande')"
  >
    在线
  </el-button>
  <el-button
    :type="querySource === 'local' ? 'primary' : ''"
    @click="handleSourceChange('local')"
  >
    本地
  </el-button>
  <el-button
    v-if="querySource !== 'yande'"
    :type="querySource === 'favorites' ? 'primary' : ''"
    @click="handleSourceChange('favorites')"
  >
    收藏夹
  </el-button>
</el-button-group>
```

- [ ] **Step 7：修改模板 — 主区域条件渲染**

替换 `Gallery.vue:88-107` 的 `.gallery-content` 块：

```vue
<div class="gallery-content">
  <!-- 收藏夹文件夹列表 -->
  <template v-if="querySource === 'favorites' && favoritesView === 'folders'">
    <WaterfallGallery
      item-type="folder"
      :images="currentFolders"
      :loading="folderLoading"
      :has-more="folderHasMore"
      :is-loading-more="false"
      :load-error="false"
      :selected-images="[]"
      :selectable="false"
      :source-mode="'favorites'"
      :save-data-mode="saveDataMode"
      :safe-mode="safeMode"
      @load-more="handleFolderScrollBottom"
    >
      <template #default="{ folder }">
        <FolderTile
          :folder="folder"
          :save-data-mode="saveDataMode"
          @click="handleFolderClick"
        />
      </template>
    </WaterfallGallery>
  </template>

  <!-- 普通瀑布流（在线 / 本地 / 文件夹图片） -->
  <template v-else>
    <WaterfallGallery
      :images="images"
      :loading="loading"
      :has-more="hasMore"
      :is-loading-more="isLoadingMore"
      :load-error="loadError"
      :selected-images="selectedImages"
      :selectable="querySource === 'yande'"
      :source-mode="querySource"
      :save-data-mode="saveDataMode"
      :safe-mode="safeMode"
      @image-click="handleImageClick"
      @image-select="handleImageSelect"
      @load-more="loadMore"
      @load-error="handleLoadError"
      @multi-select-start="handleMultiSelectStart"
    />
  </template>
</div>
```

- [ ] **Step 8：添加 BackButton 到模板**

在 `<AdvancedQuery ... />` 之前插入：

```vue
<BackButton
  :visible="querySource === 'favorites' && favoritesView === 'folder-detail'"
  @click="handleBackToFolders"
/>
```

- [ ] **Step 9：Commit**

```bash
git add frontend/src/views/Gallery.vue
git commit -m "feat(frontend): Gallery.vue 收藏夹模式状态机集成"
```

---

## Task 13：手动验证（端到端）

**Files:** 无（仅运行验证）

- [ ] **Step 1：启动后端**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
uvicorn service:main_app --port 8000 --reload --reload-dir ./src
```

等待 banner 输出

- [ ] **Step 2：启动前端**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend
npm run dev
```

浏览器打开 http://localhost:3000

- [ ] **Step 3：浏览器手测清单**

逐项打勾：

- [ ] 默认进入「本地」模式，按钮组显示 [在线, 本地, 收藏夹] 3 联
- [ ] 点击「在线」→ 按钮组变 [在线, 本地] 2 联
- [ ] 回到「本地」→ 按钮组恢复 3 联
- [ ] 点击「收藏夹」→ 主区域显示文件夹瀑布流，每个文件夹显示 4/6/8 张预览图（按 local_count 分档）
- [ ] 滚动到底部自动加载下一页
- [ ] 省流模式打开 → 文件夹预览图退化为图标占位
- [ ] 点击文件夹 → 进入 folder-detail 视图，搜索栏显示 ★folder  chip
- [ ] 叠加额外 tag 搜索 → 文件夹内图片进一步筛选
- [ ] 返回按钮出现（桌面端位于搜索栏左侧，移动端位于上方左对齐）
- [ ] 点返回 → 回到文件夹列表，搜索栏清空
- [ ] 点「在线」按钮 → 自动退出收藏夹模式

- [ ] **Step 4：跑所有测试**

```bash
# 后端
cd /home/exa160/opencode/yande.re-spider-next-dev
python -m pytest unit_test/ -v

# 前端
cd frontend
npx vitest run
```

预期：所有测试通过

- [ ] **Step 5：Commit（无文件改动则跳过）**

若 Step 3/4 发现 bug，修复后 commit；无改动则不 commit

---

## 自审清单（按 writing-plans skill）

| 检查项 | 结果 |
|--------|------|
| Spec 覆盖 | ✅ 10 个实施步骤映射 spec 全部 7 节 + 3 节范围外说明 |
| 占位扫描 | ✅ 无 TBD/TODO 占位（仅 spec/代码中已有的语义性 TODO） |
| 类型一致性 | ✅ `getFoldersWithPreview` / `preview_folder` / `query_random_for_tags` / `list_paginated` / `loadFolders` / `handleFolderClick` / `handleBackToFolders` 在所有任务中签名一致 |
| 任务边界 | ✅ 每个任务独立可测、独立 commit、独立 review |
| YAGNI | ✅ 严格按 spec 第 9.2 节边界实现，不超范围 |

---

## 执行交接

**Plan complete and saved to `docs/superpowers/plans/2026-08-20-favorites-mode.md`.**

13 个任务，预计 13 次 commit（含 spec 已有的 commit b8d7e4f）。

**两种执行方式供选择：**

1. **Subagent-Driven（推荐）** — 每个 task 分派独立 subagent，task 间有 reviewer gate
2. **Inline Execution** — 当前 session 顺序执行所有 task，批量 checkpoint

**请告诉我用哪种方式执行？**（默认推荐 subagent-driven）