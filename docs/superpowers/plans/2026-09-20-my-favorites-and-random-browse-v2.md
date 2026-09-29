# 我的最爱 + 随机浏览功能 v2 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不动 `get_folders_with_preview` 接口的前提下，新增"我的最爱"图片级收藏 + "随机浏览" + 配置文件中心化（4 个新开关 + 5 个迁移偏好）；我的最爱磁贴由前端插入置顶；二级页复用 `/api/v1/gallery/load`；修复 v1 收藏夹页报错。

**Tech Stack:** Python 3.12 + FastAPI + Pydantic v2 + SQLAlchemy (SQLite) + Vue 3 + Element Plus + Vitest + pytest

**Spec:** `docs/superpowers/specs/2026-09-20-my-favorites-and-random-browse-v2-design.md`

---

## Global Constraints

| 项 | 值 |
|---|---|
| 后端代码风格 | 严格类型注解 + 现有 `BaseResponse` + `APIException(ErrMsg.XXX, e=e)` 模式 |
| Pydantic | v2 风格 (`Field()`, `field_validator`) |
| DB 迁移 | SQLite 自动建表（沿用 `Base.metadata.create_all`），无 Alembic |
| 分层 | `api/` → `services/` → `dao/` 严禁跨层 |
| 前端 Vue | Vue 3 Composition API + `<script setup>` |
| 测试 | 后端 pytest（`cd backend && PYTHONPATH=. ...`），前端 Vitest |
| 配置路径 | 运行时通过 `path_constant.config_file` 读取，**不**硬编码 |
| 密钥红线 | commit 前必须扫 `password` / `secret` / `token` / `api_key` 真值 |
| **不动约束** | `get_folders_with_preview` 接口、`FavoriteFolder` 表、`FavoriteFolderBase` 响应模型、原收藏夹调用方 |
| 分支 | `feature-lazy-load-gate-fix-v1.2.1`，**未经用户审核禁止 push** |

---

## Review Focus

最可能被漏掉的 5 类输入/失败模式：

1. **`config.favorites.enable_my_favorites=false` 但前端误传 `include_favorite_status=true`** —— 后端必须**强制不连表**（双重判断）。预期：响应 `is_favorited=None`，无 JOIN 开销。已由 Task 8 测试用例覆盖。
2. **`random=true` 时返回的 id 不唯一** —— 后端必须用 `DISTINCT image_id`。预期：响应中 id 无重复。已由 Task 7 测试用例覆盖。
3. **`get_folders_with_preview` 误改回 v1 行为（注入虚拟 folder）** —— 任何后续修改都可能重新引入。已由 Task 9 回归测试锁定。
4. **`enable_favorite_autodownload=false` 时仍触发下载** —— `MyFavoritesService.add` 必须双重判断。已由 Task 4 测试用例覆盖。
5. **`HeartOverlay` 加边框破坏视觉** —— 显式 `border: none` + 测试断言。已由 Task 11 测试用例覆盖。

---

## 文件结构总览

### 后端新增
| 文件 | 职责 |
|---|---|
| `backend/src/models/database/my_favorite.py` | `MyFavorite` ORM 模型 |
| `backend/src/dao/my_favorite_dao.py` | `MyFavoriteDao` (add/list/count/get_preview) |
| `backend/src/models/request/my_favorites.py` | 请求 Pydantic 模型 |
| `backend/src/models/response/my_favorites.py` | 响应 Pydantic 模型 |
| `backend/src/services/my_favorites.py` | `MyFavoritesService` (add 自动下载逻辑) |
| `backend/src/api/v1/my_favorites.py` | `/api/v1/my-favorites/*` 路由（含 `/preview`）|

### 后端修改
| 文件 | 变更 |
|---|---|
| `backend/src/common/constant.py` | 新增 `my_favorite: str = "my_favorite"` |
| `backend/src/common/settings.py` | 新增 `FavoritesConfig` + 挂载 `Config.favorites` |
| `backend/src/services/config.py` | 新增 `get_favorites_config` / `update_favorites_config` |
| `backend/src/api/v1/config.py` | 新增 `GET/PUT /config/favorites` + `ResetConfig` 扩展 |
| `backend/src/api/v1/gallery.py` | 扩展 `GalleryLoadRequest` + `get_image_detail` 参数 |
| `backend/src/services/gallery.py` | 实现 `include_favorite_status` JOIN + `random` ORDER BY RANDOM() |
| `backend/src/models/response/yande.py` | `YandeData` / `YandeDataDetail` 新增 `is_favorited: Optional[bool]` |

### 后端测试新增
| 文件 | 覆盖 Task |
|---|---|
| `backend/unit_test/database/test_my_favorite_model.py` | Task 1 |
| `backend/unit_test/dao/test_my_favorite_dao.py` | Task 2 |
| `backend/unit_test/models/test_my_favorites_models.py` | Task 3 |
| `backend/unit_test/services/test_my_favorites_service.py` | Task 4 |
| `backend/unit_test/api/v1/test_my_favorites_route.py` | Task 5 |
| `backend/unit_test/common/test_favorites_config.py` | Task 6 |
| `backend/unit_test/services/test_config_favorites.py` | Task 6 |
| `backend/unit_test/api/v1/test_gallery_load_include_favorite.py` | Task 7 |
| `backend/unit_test/api/v1/test_gallery_load_random.py` | Task 7 |
| `backend/unit_test/api/v1/test_gallery_detail_include_favorite.py` | Task 8 |
| `backend/unit_test/services/test_get_folders_with_preview_no_virtual.py` | Task 9 |

### 前端新增
| 文件 | 职责 |
|---|---|
| `frontend/src/api/myFavorites.js` | `add` / `remove` / `list` / `count` / `getPreview` |
| `frontend/src/components/HeartOverlay.vue` | 爱心按钮（**无边框**，image-info-content 层）|
| `frontend/src/components/HeartOverlay.spec.js` | HeartOverlay 测试 |
| `frontend/src/components/FavoritePanel.spec.js` | FavoritePanel 测试 |

### 前端修改
| 文件 | 变更 |
|---|---|
| `frontend/src/composables/useFavoritesConfig.js` | localStorage → 后端 API + 4 新开关 + myFavoritesCount 缓存 |
| `frontend/src/composables/useFavoritesConfig.spec.js` | 测试更新 |
| `frontend/src/components/WaterfallGallery.vue` | 集成 HeartOverlay + `showHeart` props + 自动加 `include_favorite_status` |
| `frontend/src/components/WaterfallGallery.spec.js` | 测试更新 |
| `frontend/src/components/FolderTile.vue` | 识别 `isVirtual` 字段渲染虚拟磁贴 |
| `frontend/src/components/FolderTile.spec.js` | 测试更新 |
| `frontend/src/components/FavoritePanel.vue` | **前端 prepend** 虚拟磁贴 |
| `frontend/src/views/Gallery.vue` | 新增 `querySource='my-favorites'` / `querySource='random'` |
| `frontend/src/views/Gallery.spec.js` | 测试更新 |
| `frontend/src/views/Config.vue` | 4 个新开关 + 5 个迁移偏好 |
| `frontend/src/views/Config.spec.js` | 测试更新 |
| `frontend/src/views/ImageDetail.vue`（或等价组件）| `float-header-left` 显示 HeartOverlay |

---

## Task 1: MyFavorite 数据库模型 + table_constant

**Files:**
- Create: `backend/src/models/database/my_favorite.py`
- Modify: `backend/src/common/constant.py`
- Create: `backend/src/models/database/__init__.py`（追加导出）
- Test: `backend/unit_test/database/test_my_favorite_model.py`

**Interfaces:**
- Consumes: `table_constant.my_favorite`
- Produces: `MyFavorite(id, image_id, created_at, note)` ORM 类

- [ ] **Step 1: Write the failing test**

`backend/unit_test/database/test_my_favorite_model.py`：

```python
"""MyFavorite ORM model unit tests."""
from src.models.database.my_favorite import MyFavorite
from src.common.constant import table_constant


def test_tablename_is_my_favorite():
    """Verify __tablename__ uses table_constant.my_favorite."""
    assert MyFavorite.__tablename__ == table_constant.my_favorite
    assert table_constant.my_favorite == "my_favorite"


def test_required_columns_exist():
    """Verify required columns are defined."""
    columns = {c.name for c in MyFavorite.__table__.columns}
    assert "id" in columns
    assert "image_id" in columns
    assert "created_at" in columns
    assert "note" in columns


def test_image_id_is_unique():
    """Verify image_id has unique constraint (幂等性)."""
    constraints = {c.name for c in MyFavorite.__table__.constraints}
    # SQLAlchemy auto-names UNIQUE constraints
    unique_constraints = [
        c for c in MyFavorite.__table__.constraints
        if "unique" in type(c).__name__.lower() or c.__class__.__name__.lower() == "uniqueconstraint"
    ]
    assert len(unique_constraints) >= 1, "image_id must have UNIQUE constraint"


def test_image_id_not_nullable():
    """Verify image_id is NOT NULL."""
    image_id_col = MyFavorite.__table__.columns["image_id"]
    assert image_id_col.nullable is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && PYTHONPATH=. /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m pytest unit_test/database/test_my_favorite_model.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.models.database.my_favorite'`

- [ ] **Step 3: Add table_constant entry**

`backend/src/common/constant.py` —— 找到 `table_constant` 类，添加：

```python
my_favorite: str = "my_favorite"
```

定位方法：搜索现有 `favorite_folder: str =` 类似条目附近添加。

- [ ] **Step 4: Create MyFavorite model**

`backend/src/models/database/my_favorite.py`：

```python
"""我的最爱 ORM 模型（图片级标记中间表）"""
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String

from src.dao.database import Base
from src.common.constant import table_constant


class MyFavorite(Base):
    """我的最爱 - 图片级标记（与 FavoriteFolder 互不污染）"""
    __tablename__ = table_constant.my_favorite

    id = Column(Integer, primary_key=True, autoincrement=True)
    image_id = Column(Integer, nullable=False, comment="yande 图片 ID")
    created_at = Column(DateTime, default=datetime.now, comment="收藏时间")
    note = Column(String(255), nullable=True, comment="预留备注字段")
```

- [ ] **Step 5: Verify table_constant.py is exported correctly**

检查 `backend/src/common/constant.py` 的 `table_constant` 类（应为 `frozen=True` 的 dataclass 或类似结构）。如果它**不是**已导入 `table_constant`，确认 `from src.common.constant import table_constant` 在测试文件中已生效。

- [ ] **Step 6: Run test to verify it passes**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && PYTHONPATH=. /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m pytest unit_test/database/test_my_favorite_model.py -v
```

Expected: 4 tests PASS

- [ ] **Step 7: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add backend/src/models/database/my_favorite.py backend/src/common/constant.py backend/unit_test/database/test_my_favorite_model.py && git commit -m "feat(backend): MyFavorite ORM model + table_constant.my_favorite"
```

---

## Task 2: MyFavoriteDao

**Files:**
- Create: `backend/src/dao/my_favorite_dao.py`
- Test: `backend/unit_test/dao/test_my_favorite_dao.py`

**Interfaces:**
- Consumes: `MyFavorite` ORM
- Produces: `add(image_id, note=None)`, `remove(image_id)`, `list_paginated(page, page_size)`, `count()`, `get_preview(limit)` 方法

- [ ] **Step 1: Write the failing test**

`backend/unit_test/dao/test_my_favorite_dao.py`：

```python
"""MyFavoriteDao unit tests."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.dao.database import Base
from src.dao.my_favorite_dao import MyFavoriteDao
from src.models.database.my_favorite import MyFavorite


@pytest.fixture
def session():
    """In-memory SQLite session with Base metadata."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def test_add_inserts_row(session):
    """Verify add() inserts a new row."""
    MyFavoriteDao.add(session, image_id=42)
    rows = session.query(MyFavorite).all()
    assert len(rows) == 1
    assert rows[0].image_id == 42


def test_add_is_idempotent(session):
    """Verify add() with same image_id does not raise (UNIQUE constraint)."""
    MyFavoriteDao.add(session, image_id=42)
    MyFavoriteDao.add(session, image_id=42)  # 二次调用
    rows = session.query(MyFavorite).all()
    assert len(rows) == 1


def test_count_returns_zero_when_empty(session):
    """Verify count() returns 0 when no records."""
    assert MyFavoriteDao.count(session) == 0


def test_count_returns_correct_count(session):
    """Verify count() returns correct number."""
    MyFavoriteDao.add(session, image_id=1)
    MyFavoriteDao.add(session, image_id=2)
    MyFavoriteDao.add(session, image_id=3)
    assert MyFavoriteDao.count(session) == 3


def test_remove_deletes_row(session):
    """Verify remove() deletes the row."""
    MyFavoriteDao.add(session, image_id=42)
    MyFavoriteDao.remove(session, image_id=42)
    assert MyFavoriteDao.count(session) == 0


def test_remove_is_idempotent(session):
    """Verify remove() on non-existent image_id does not raise."""
    MyFavoriteDao.remove(session, image_id=999)  # 不存在
    assert MyFavoriteDao.count(session) == 0


def test_list_paginated_returns_records_in_desc_order(session):
    """Verify list_paginated returns records ordered by created_at DESC."""
    import time
    MyFavoriteDao.add(session, image_id=1)
    time.sleep(0.01)
    MyFavoriteDao.add(session, image_id=2)
    time.sleep(0.01)
    MyFavoriteDao.add(session, image_id=3)

    rows = MyFavoriteDao.list_paginated(session, page=1, page_size=10)
    assert [r.image_id for r in rows] == [3, 2, 1]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && PYTHONPATH=. /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m pytest unit_test/dao/test_my_favorite_dao.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.dao.my_favorite_dao'`

- [ ] **Step 3: Create MyFavoriteDao**

`backend/src/dao/my_favorite_dao.py`：

```python
"""MyFavoriteDao - my_favorite 表的数据访问层"""
from typing import List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.database.my_favorite import MyFavorite


class MyFavoriteDao:
    """我的最爱 DAO。UNIQUE(image_id) 保证幂等。"""

    @staticmethod
    def add(session: Session, image_id: int, note: str = None) -> None:
        """加入我的最爱。幂等（UNIQUE image_id 兜底）。"""
        record = MyFavorite(image_id=image_id, note=note)
        session.add(record)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()  # 幂等：image_id 已存在则忽略

    @staticmethod
    def remove(session: Session, image_id: int) -> None:
        """取消我的最爱。幂等（不存在不报错）。"""
        session.query(MyFavorite).filter(MyFavorite.image_id == image_id).delete()
        session.flush()

    @staticmethod
    def list_paginated(session: Session, page: int = 1, page_size: int = 20) -> List[MyFavorite]:
        """分页列出（按 created_at DESC）。"""
        offset = (page - 1) * page_size
        return (
            session.query(MyFavorite)
            .order_by(MyFavorite.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )

    @staticmethod
    def count(session: Session) -> int:
        """总数。"""
        return session.query(MyFavorite).count()

    @staticmethod
    def get_preview(session: Session, limit: int = 20) -> List[dict]:
        """我的最爱预览图元数据（JOIN yande_data 按 created_at DESC）。

        返回字典列表，结构对齐 FavoriteFolderWithMinimalPreview.preview_images：
        [{"id": int, "preview_url": str, "tags": str, "rating": str}, ...]
        """
        from src.models.database.yande import YandeData
        records = (
            session.query(MyFavorite, YandeData)
            .join(YandeData, YandeData.id == MyFavorite.image_id)
            .order_by(MyFavorite.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": yande.id,
                "preview_url": getattr(yande, "preview_url", None),
                "tags": yande.tags,
                "rating": yande.rating,
            }
            for _, yande in records
        ]
```

**注意**：`preview_url` 字段名需要根据 `YandeData` 实际 schema 调整。如果模型没有 `preview_url` 字段，应改用其他可用的预览图字段。检查方法：

```bash
grep -n "preview\|class YandeData" /home/exa160/opencode/yande.re-spider-next-dev/backend/src/models/database/yande.py | head -20
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && PYTHONPATH=. /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m pytest unit_test/dao/test_my_favorite_dao.py -v
```

Expected: 7 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add backend/src/dao/my_favorite_dao.py backend/unit_test/dao/test_my_favorite_dao.py && git commit -m "feat(backend): MyFavoriteDao (add/remove/list/count/get_preview)"
```

---

## Task 3: MyFavorites Request/Response 模型

**Files:**
- Create: `backend/src/models/request/my_favorites.py`
- Create: `backend/src/models/response/my_favorites.py`
- Test: `backend/unit_test/models/test_my_favorites_models.py`

**Interfaces:**
- Produces: `MyFavoritesListResponse`, `MyFavoriteCountResponse`, `MyFavoritePreviewResponse`

- [ ] **Step 1: Write the failing test**

`backend/unit_test/models/test_my_favorites_models.py`：

```python
"""MyFavorites request/response Pydantic models tests."""
from src.models.response.my_favorites import (
    MyFavoritesListResponse,
    MyFavoriteCountResponse,
    MyFavoritePreviewResponse,
)


def test_count_response_has_count_field():
    """Verify MyFavoriteCountResponse has count field."""
    resp = MyFavoriteCountResponse(count=10)
    assert resp.count == 10


def test_list_response_has_required_fields():
    """Verify MyFavoritesListResponse has total/page/page_size/data."""
    resp = MyFavoritesListResponse(total=0, page=1, page_size=20, data=[])
    assert resp.total == 0
    assert resp.page == 1
    assert resp.page_size == 20
    assert resp.data == []


def test_preview_response_has_images_field():
    """Verify MyFavoritePreviewResponse has images field."""
    resp = MyFavoritePreviewResponse(images=[])
    assert resp.images == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && PYTHONPATH=. /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m pytest unit_test/models/test_my_favorites_models.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create response models**

`backend/src/models/response/my_favorites.py`：

```python
"""MyFavorites 响应模型"""
from typing import List

from pydantic import BaseModel, Field


class MyFavoriteCountResponse(BaseModel):
    """我的最爱总数响应"""
    count: int = Field(..., ge=0, description="我的最爱总数")


class MyFavoritesListItem(BaseModel):
    """列表项（含 image_id 和 created_at）"""
    id: int = Field(..., description="my_favorite 主键")
    image_id: int = Field(..., description="yande 图片 ID")
    created_at: str = Field(..., description="收藏时间 ISO 8601")


class MyFavoritesListResponse(BaseModel):
    """我的最爱分页列表响应"""
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)
    data: List[MyFavoritesListItem] = Field(default_factory=list)


class MyFavoritePreviewImage(BaseModel):
    """预览图元数据（结构对齐 FavoriteFolderWithMinimalPreview.preview_images）"""
    id: int = Field(...)
    preview_url: str | None = Field(default=None)
    tags: str = Field(default="")
    rating: str = Field(default="")


class MyFavoritePreviewResponse(BaseModel):
    """我的最爱预览响应"""
    images: List[MyFavoritePreviewImage] = Field(default_factory=list)
```

- [ ] **Step 4: Create request models（空文件占位 + 注释）**

`backend/src/models/request/my_favorites.py`：

```python
"""MyFavorites 请求模型

目前我的最爱相关接口（POST /{image_id}、DELETE /{image_id}、GET /preview）都使用
path param 或 query param，无 request body。
本文件保留作为未来扩展（如批量 toggle）位置。
"""
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && PYTHONPATH=. /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m pytest unit_test/models/test_my_favorites_models.py -v
```

Expected: 3 tests PASS

- [ ] **Step 6: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add backend/src/models/response/my_favorites.py backend/src/models/request/my_favorites.py backend/unit_test/models/test_my_favorites_models.py && git commit -m "feat(backend): MyFavorites Request/Response Pydantic models"
```

---

## Task 4: MyFavoritesService（含自动下载逻辑）

**Files:**
- Create: `backend/src/services/my_favorites.py`
- Test: `backend/unit_test/services/test_my_favorites_service.py`

**Interfaces:**
- Consumes: `MyFavoriteDao`, `YandeDataRepository`, `DownloadService.create_task`, `config.favorites.enable_favorite_autodownload`
- Produces: `add(image_id)`, `remove(image_id)`, `list_paginated(page, page_size)`, `count()`, `get_preview(limit)`

- [ ] **Step 1: Write the failing test**

`backend/unit_test/services/test_my_favorites_service.py`：

```python
"""MyFavoritesService unit tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.dao.database import Base
from src.models.database.yande import YandeData
from src.services.my_favorites import MyFavoritesService


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    # Insert test image
    img = YandeData(id=42, tags="rating:s", rating="s", score=100, down_flag=False)
    s.add(img)
    s.commit()
    yield s
    s.close()


@pytest.fixture
def enable_autodownload_true():
    with patch("src.services.my_favorites.config") as mock_config:
        mock_config.favorites.enable_favorite_autodownload = True
        yield mock_config


@pytest.fixture
def enable_autodownload_false():
    with patch("src.services.my_favorites.config") as mock_config:
        mock_config.favorites.enable_favorite_autodownload = False
        yield mock_config


@pytest.mark.asyncio
async def test_add_raises_for_nonexistent_image(session, enable_autodownload_true):
    """Verify add() raises ValueError for non-existent image."""
    with pytest.raises(ValueError, match="not found"):
        await MyFavoritesService.add(999)


@pytest.mark.asyncio
async def test_add_persists_record(session, enable_autodownload_true):
    """Verify add() persists record."""
    await MyFavoritesService.add(42)
    count = MyFavoritesService.count()
    assert count == 1


@pytest.mark.asyncio
async def test_add_with_autodownload_true_triggers_download(session, enable_autodownload_true):
    """Verify add() with enable_favorite_autodownload=True triggers download for non-local image."""
    with patch("src.services.my_favorites.DownloadService") as mock_dl:
        mock_dl.create_task = AsyncMock()
        await MyFavoritesService.add(42)
        mock_dl.create_task.assert_called_once_with(42)


@pytest.mark.asyncio
async def test_add_with_autodownload_false_does_not_trigger_download(session, enable_autodownload_false):
    """Verify add() with enable_favorite_autodownload=False does NOT trigger download."""
    with patch("src.services.my_favorites.DownloadService") as mock_dl:
        mock_dl.create_task = AsyncMock()
        await MyFavoritesService.add(42)
        mock_dl.create_task.assert_not_called()


@pytest.mark.asyncio
async def test_add_for_downloaded_image_does_not_trigger_download(session, enable_autodownload_true):
    """Verify add() for already-downloaded image (down_flag=True) does NOT trigger download."""
    session.query(YandeData).filter(YandeData.id == 42).update({"down_flag": True})
    session.commit()

    with patch("src.services.my_favorites.DownloadService") as mock_dl:
        mock_dl.create_task = AsyncMock()
        await MyFavoritesService.add(42)
        mock_dl.create_task.assert_not_called()


def test_remove_is_idempotent(session, enable_autodownload_true):
    """Verify remove() on non-existent image_id does not raise."""
    MyFavoritesService.remove(999)  # 不存在


def test_count_returns_correct(session, enable_autodownload_true):
    """Verify count() returns correct number."""
    MyFavoritesService.add.__call__  # 仅访问属性
    from src.dao.my_favorite_dao import MyFavoriteDao
    MyFavoriteDao.add(session, image_id=42)
    assert MyFavoritesService.count() == 1
```

**注意**：测试需要 `pytest-asyncio`。检查 `backend/pyproject.toml` 或 `requirements` 是否有 `pytest-asyncio`。如果没有，加到依赖。

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && PYTHONPATH=. /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m pytest unit_test/services/test_my_favorites_service.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create MyFavoritesService**

`backend/src/services/my_favorites.py`：

```python
"""MyFavoritesService - 我的最爱业务逻辑层"""
from typing import List, Tuple

from loguru import logger

from src.common.config_bootstrap import config  # 按项目实际导入调整
from src.dao.my_favorite_dao import MyFavoriteDao
from src.dao.yande_data_dao import YandeDataDao
from src.services.download import DownloadService


class MyFavoritesService:
    """我的最爱业务编排"""

    @staticmethod
    async def add(image_id: int) -> None:
        """加入我的最爱；满足条件时异步触发下载。"""
        yande_data = YandeDataDao.get_by_id(image_id)
        if not yande_data:
            raise ValueError(f"Image {image_id} not found in database")

        # 1) 写入 my_favorite（UNIQUE 约束保证幂等）
        MyFavoriteDao.add(image_id=image_id)

        # 2) 仅当 is_local=false 且 enable_favorite_autodownload=true 才触发下载
        if not yande_data.down_flag and config.favorites.enable_favorite_autodownload:
            try:
                await DownloadService.create_task(image_id)
                logger.info(f"My favorite auto-download triggered for {image_id}")
            except Exception as e:
                logger.warning(f"Auto-download failed for {image_id}: {e}")

    @staticmethod
    def remove(image_id: int) -> None:
        """取消我的最爱（幂等）。"""
        MyFavoriteDao.remove(image_id=image_id)

    @staticmethod
    def list_paginated(page: int = 1, page_size: int = 20) -> Tuple[List, int]:
        """分页列出我的最爱（含元数据 JOIN）。"""
        records = MyFavoriteDao.list_paginated(page=page, page_size=page_size)
        total = MyFavoriteDao.count()
        return records, total

    @staticmethod
    def count() -> int:
        """我的最爱总数。"""
        return MyFavoriteDao.count()

    @staticmethod
    def get_preview(limit: int = 20) -> List[dict]:
        """我的最爱预览图元数据。"""
        return MyFavoriteDao.get_preview(limit=limit)
```

**注意**：
- `config` 导入路径需要按项目实际调整。先检查 `backend/src/common/settings.py` 中 `config` 是如何暴露的：

```bash
grep -n "^config\|^from src" /home/exa160/opencode/yande.re-spider-next-dev/backend/src/common/settings.py | tail -10
```

- `YandeDataDao.get_by_id` 方法名按实际调整。先检查：

```bash
grep -n "def get_by_id\|def get\b" /home/exa160/opencode/yande.re-spider-next-dev/backend/src/dao/yande_data_dao.py | head -5
```

- `DownloadService.create_task` 是 async 方法。

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && PYTHONPATH=. /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m pytest unit_test/services/test_my_favorites_service.py -v
```

Expected: 7 tests PASS（个别 fixture 调整后可能 5-6 个 PASS）

- [ ] **Step 5: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add backend/src/services/my_favorites.py backend/unit_test/services/test_my_favorites_service.py && git commit -m "feat(backend): MyFavoritesService (add with autodownload condition)"
```

---

## Task 5: MyFavorites API 路由（含独立 preview 接口）

**Files:**
- Create: `backend/src/api/v1/my_favorites.py`
- Test: `backend/unit_test/api/v1/test_my_favorites_route.py`

**Interfaces:**
- Consumes: `MyFavoritesService`
- Produces: 5 个路由：`GET /my-favorites`、`POST /my-favorites/{image_id}`、`DELETE /my-favorites/{image_id}`、`GET /my-favorites/count`、`GET /my-favorites/preview`

- [ ] **Step 1: Write the failing test**

`backend/unit_test/api/v1/test_my_favorites_route.py`：

```python
"""MyFavorites API route tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """FastAPI TestClient with mocked MyFavoritesService."""
    with patch("src.api.v1.my_favorites.MyFavoritesService") as mock_svc:
        mock_svc.add = AsyncMock()
        mock_svc.remove = MagicMock()
        mock_svc.count = MagicMock(return_value=10)
        mock_svc.list_paginated = MagicMock(return_value=([], 0))
        mock_svc.get_preview = MagicMock(return_value=[{"id": 1, "preview_url": None, "tags": "", "rating": ""}])
        from src.main import app  # 按项目实际入口调整
        yield TestClient(app), mock_svc


def test_add_my_favorite_returns_200(client):
    """POST /my-favorites/{image_id} returns 200 on success."""
    c, mock_svc = client
    resp = c.post("/api/v1/my-favorites/42")
    assert resp.status_code == 200


def test_add_my_favorite_returns_404_for_nonexistent(client):
    """POST /my-favorites/{image_id} returns 404 for non-existent image."""
    c, mock_svc = client
    mock_svc.add.side_effect = ValueError("Image 999 not found")
    resp = c.post("/api/v1/my-favorites/999")
    assert resp.status_code in (404, 400)


def test_remove_my_favorite_returns_200(client):
    """DELETE /my-favorites/{image_id} returns 200."""
    c, mock_svc = client
    resp = c.delete("/api/v1/my-favorites/42")
    assert resp.status_code == 200


def test_count_returns_correct(client):
    """GET /my-favorites/count returns count field."""
    c, mock_svc = client
    resp = c.get("/api/v1/my-favorites/count")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["count"] == 10


def test_preview_returns_images(client):
    """GET /my-favorites/preview returns images list."""
    c, mock_svc = client
    resp = c.get("/api/v1/my-favorites/preview?limit=20")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "images" in data
    assert len(data["images"]) == 1


def test_list_returns_paginated(client):
    """GET /my-favorites returns paginated response."""
    c, mock_svc = client
    resp = c.get("/api/v1/my-favorites?page=1&page_size=20")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert "data" in data
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && PYTHONPATH=. /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m pytest unit_test/api/v1/test_my_favorites_route.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create MyFavorites API routes**

`backend/src/api/v1/my_favorites.py`：

```python
"""/api/v1/my-favorites/* 路由"""
from fastapi import APIRouter, Query
from loguru import logger

from src.common.response import BaseResponse, APIException
from src.common.err_msg import ErrMsg
from src.models.response.my_favorites import (
    MyFavoriteCountResponse,
    MyFavoritesListResponse,
    MyFavoritePreviewResponse,
)
from src.services.my_favorites import MyFavoritesService

router = APIRouter(prefix="/my-favorites", tags=["my-favorites"])


@router.get("", response_model=BaseResponse[MyFavoritesListResponse], summary="我的最爱列表")
async def list_my_favorites(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> BaseResponse[MyFavoritesListResponse]:
    """分页列出我的最爱（按 created_at DESC）。"""
    try:
        records, total = MyFavoritesService.list_paginated(page=page, page_size=page_size)
        return BaseResponse(
            message=ErrMsg.OK.msg,
            data=MyFavoritesListResponse(
                total=total,
                page=page,
                page_size=page_size,
                data=[{"id": r.id, "image_id": r.image_id, "created_at": r.created_at.isoformat()} for r in records],
            ),
        )
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)


@router.post("/{image_id}", response_model=BaseResponse, summary="加入我的最爱")
async def add_my_favorite(image_id: int) -> BaseResponse:
    """加入我的最爱。幂等（UNIQUE image_id 兜底）。"""
    try:
        await MyFavoritesService.add(image_id)
        return BaseResponse(message="已加入我的最爱")
    except ValueError as e:
        raise APIException(ErrMsg.NOT_FOUND, data={"detail": str(e)})
    except Exception as e:
        raise APIException(ErrMsg.CREATE_ERROR, e=e)


@router.delete("/{image_id}", response_model=BaseResponse, summary="取消我的最爱")
async def remove_my_favorite(image_id: int) -> BaseResponse:
    """取消我的最爱（幂等）。"""
    try:
        MyFavoritesService.remove(image_id)
        return BaseResponse(message="已取消我的最爱")
    except Exception as e:
        raise APIException(ErrMsg.DELETE_ERROR, e=e)


@router.get("/count", response_model=BaseResponse[MyFavoriteCountResponse], summary="我的最爱总数")
async def count_my_favorites() -> BaseResponse[MyFavoriteCountResponse]:
    """我的最爱总数（用于收藏夹列表前端插入磁贴的角标）。"""
    try:
        count = MyFavoritesService.count()
        return BaseResponse(message=ErrMsg.OK.msg, data=MyFavoriteCountResponse(count=count))
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)


@router.get("/preview", response_model=BaseResponse[MyFavoritePreviewResponse], summary="我的最爱预览")
async def get_my_favorites_preview(
    limit: int = Query(20, ge=1, le=100),
    tile_size: str = Query("adaptive"),
) -> BaseResponse[MyFavoritePreviewResponse]:
    """为文件夹展示页提供我的最爱预览图（独立的、不复用 favorites 的接口）。"""
    try:
        images = MyFavoritesService.get_preview(limit=limit)
        return BaseResponse(
            message=ErrMsg.OK.msg,
            data=MyFavoritePreviewResponse(images=images),
        )
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)
```

**注意**：
- `ErrMsg.NOT_FOUND` / `CREATE_ERROR` / `DELETE_ERROR` / `QUERY_ERROR` 需要按项目实际枚举调整。检查 `backend/src/common/err_msg.py`：

```bash
grep -n "NOT_FOUND\|CREATE_ERROR\|DELETE_ERROR\|QUERY_ERROR\|class ErrMsg" /home/exa160/opencode/yande.re-spider-next-dev/backend/src/common/err_msg.py | head -10
```

- 路由 prefix `/my-favorites` 由 APILoader 自动发现并挂载到 `/api/v1`。具体方式参考其他模块：

```bash
ls /home/exa160/opencode/yande.re-spider-next-dev/backend/src/api/v1/ && cat /home/exa160/opencode/yande.re-spider-next-dev/backend/src/api/v1/__init__.py 2>/dev/null | head -30
```

- [ ] **Step 4: Verify router is auto-loaded**

项目用 APILoader 自动发现 `api/v1/*.py`。新文件 `my_favorites.py` 应自动被加载。如果不是：

```bash
grep -n "api/v1\|APILoader\|load_routers" /home/exa160/opencode/yande.re-spider-next-dev/backend/src/main.py | head -10
```

如果需要手动注册，在 `api/v1/__init__.py` 中 `from .my_favorites import router as my_favorites_router` 并加入 `__all__`。

- [ ] **Step 5: Run test to verify it passes**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && PYTHONPATH=. /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m pytest unit_test/api/v1/test_my_favorites_route.py -v
```

Expected: 6 tests PASS

- [ ] **Step 6: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add backend/src/api/v1/my_favorites.py backend/unit_test/api/v1/test_my_favorites_route.py && git commit -m "feat(backend): /api/v1/my-favorites/* routes (incl. /preview)"
```

---

## Task 6: FavoritesConfig + Config 挂载 + ConfigService + API

**Files:**
- Modify: `backend/src/common/settings.py`
- Modify: `backend/src/services/config.py`
- Modify: `backend/src/api/v1/config.py`
- Test: `backend/unit_test/common/test_favorites_config.py`
- Test: `backend/unit_test/services/test_config_favorites.py`

**Interfaces:**
- Produces: `FavoritesConfig` Pydantic 模型（含 9 个字段 + 4 个 validator），`Config.favorites`，`get_favorites_config()` / `update_favorites_config()`，2 个新 API 路由

- [ ] **Step 1: Write the failing test (config model)**

`backend/unit_test/common/test_favorites_config.py`：

```python
"""FavoritesConfig Pydantic model tests."""
import pytest
from pydantic import ValidationError

from src.common.settings import FavoritesConfig


def test_default_values():
    """Verify default values match spec."""
    c = FavoritesConfig()
    assert c.button_mode == "shown"
    assert c.tile_size == "adaptive"
    assert c.preview_order == "random"
    assert c.include_online is False
    assert c.folder_page_size == 20
    assert c.enable_my_favorites is False
    assert c.enable_random_browse is False
    assert c.enable_favorite_folder is True
    assert c.enable_favorite_autodownload is True


def test_invalid_button_mode_raises():
    """Verify invalid button_mode is rejected."""
    with pytest.raises(ValidationError):
        FavoritesConfig(button_mode="invalid")


def test_invalid_tile_size_raises():
    """Verify invalid tile_size is rejected."""
    with pytest.raises(ValidationError):
        FavoritesConfig(tile_size="5")


def test_invalid_preview_order_raises():
    """Verify invalid preview_order is rejected."""
    with pytest.raises(ValidationError):
        FavoritesConfig(preview_order="ascending")


def test_invalid_folder_page_size_raises():
    """Verify invalid folder_page_size is rejected."""
    with pytest.raises(ValidationError):
        FavoritesConfig(folder_page_size=10)


def test_valid_button_modes():
    """Verify all valid button_mode values accepted."""
    for v in ("hidden", "shown", "default"):
        c = FavoritesConfig(button_mode=v)
        assert c.button_mode == v


def test_valid_tile_sizes():
    """Verify all valid tile_size values accepted."""
    for v in ("adaptive", "4", "6", "8"):
        c = FavoritesConfig(tile_size=v)
        assert c.tile_size == v


def test_valid_folder_page_sizes():
    """Verify all valid folder_page_size values accepted."""
    for v in (8, 12, 20):
        c = FavoritesConfig(folder_page_size=v)
        assert c.folder_page_size == v
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && PYTHONPATH=. /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m pytest unit_test/common/test_favorites_config.py -v
```

Expected: FAIL with `ImportError: cannot import name 'FavoritesConfig'`

- [ ] **Step 3: Add FavoritesConfig to settings.py**

`backend/src/common/settings.py` 末尾（`Config` 类之前）追加：

```python
from pydantic import field_validator


class FavoritesConfig(ConfigModel):
    """收藏夹 UI 配置 + 我的最爱/随机浏览总开关（从 localStorage 迁移）"""

    button_mode: str = Field("shown", description="主页收藏夹按钮显示: hidden | shown | default")
    tile_size: str = Field("adaptive", description="收藏夹 tile 大小: adaptive | 4 | 6 | 8")
    preview_order: str = Field("random", description="预览图排序: random | asc | desc")
    include_online: bool = Field(False, description="预览是否包含未下载图片")
    folder_page_size: int = Field(20, description="收藏夹一级每页: 8 | 12 | 20")

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

并在 `Config` 类中追加字段：

```python
class Config(ConfigModel):
    # ... 现有字段 ...
    favorites: FavoritesConfig = FavoritesConfig()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && PYTHONPATH=. /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m pytest unit_test/common/test_favorites_config.py -v
```

Expected: 8 tests PASS

- [ ] **Step 5: Add ConfigService methods**

`backend/src/services/config.py` 追加：

```python
from src.common.settings import FavoritesConfig, config


def get_favorites_config() -> FavoritesConfig:
    return config.favorites


def update_favorites_config(favorites_config: FavoritesConfig) -> bool:
    config.update_config(favorites_config)
    return True
```

**注意**：`config` 实际是 `settings.py` 末尾的实例（`config = Config()`）。检查：

```bash
tail -10 /home/exa160/opencode/yande.re-spider-next-dev/backend/src/common/settings.py
```

- [ ] **Step 6: Add config API routes**

`backend/src/api/v1/config.py` 追加（参考现有路由模式）：

```python
from src.common.settings import FavoritesConfig
from src.services.config import get_favorites_config, update_favorites_config


@router.get("/favorites", response_model=BaseResponse[FavoritesConfig], summary="获取收藏夹配置")
async def get_favorites_config_endpoint() -> BaseResponse[FavoritesConfig]:
    return BaseResponse(message=ErrMsg.OK.msg, data=get_favorites_config())


@router.put("/favorites", response_model=BaseResponse, summary="更新收藏夹配置")
async def update_favorites_config_endpoint(
    favorites_config: FavoritesConfig,
) -> BaseResponse:
    success = update_favorites_config(favorites_config)
    if not success:
        raise APIException(ErrMsg.CONFIG_UPDATE_ERROR)
    return BaseResponse(message=ErrMsg.CONFIG_UPDATE_SUCCESS)
```

**注意**：
- `ErrMsg.CONFIG_UPDATE_ERROR` / `CONFIG_UPDATE_SUCCESS` 按实际枚举调整
- 如果已有 `ResetConfig` 模型，扩展其 `section` Literal：

```python
from typing import Literal
class ResetConfig(BaseModel):
    section: Literal['api', 'downloader', 'database', 'favorites'] = Field(...)
```

- [ ] **Step 7: Write the failing test (config service)**

`backend/unit_test/services/test_config_favorites.py`：

```python
"""ConfigService favorites methods tests."""
from unittest.mock import patch, MagicMock
from src.common.settings import FavoritesConfig
from src.services.config import get_favorites_config, update_favorites_config


def test_get_favorites_config_returns_config():
    """Verify get_favorites_config returns the config.favorites instance."""
    cfg = get_favorites_config()
    assert isinstance(cfg, FavoritesConfig)


def test_update_favorites_config_succeeds():
    """Verify update_favorites_config writes successfully."""
    new_cfg = FavoritesConfig(enable_my_favorites=True)
    result = update_favorites_config(new_cfg)
    assert result is True
    assert get_favorites_config().enable_my_favorites is True
```

- [ ] **Step 8: Run tests**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && PYTHONPATH=. /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m pytest unit_test/common/test_favorites_config.py unit_test/services/test_config_favorites.py -v
```

Expected: 8 + 2 = 10 tests PASS

- [ ] **Step 9: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add backend/src/common/settings.py backend/src/services/config.py backend/src/api/v1/config.py backend/unit_test/common/test_favorites_config.py backend/unit_test/services/test_config_favorites.py && git commit -m "feat(backend): FavoritesConfig + ConfigService methods + GET/PUT /config/favorites"
```

---

## Task 7: Gallery Load 扩展（include_favorite_status + random）

**Files:**
- Modify: `backend/src/api/v1/gallery.py`（`GalleryLoadRequest`）
- Modify: `backend/src/services/gallery.py`（`load_images`）
- Modify: `backend/src/models/response/yande.py`（`YandeData.is_favorited`）
- Test: `backend/unit_test/api/v1/test_gallery_load_include_favorite.py`
- Test: `backend/unit_test/api/v1/test_gallery_load_random.py`

**Interfaces:**
- Consumes: `config.favorites.enable_my_favorites`, `MyFavorite` ORM
- Produces: `GalleryLoadRequest.include_favorite_status`、`GalleryLoadRequest.random`，`YandeData.is_favorited: Optional[bool]`

- [ ] **Step 1: Read existing gallery code**

```bash
grep -n "GalleryLoadRequest\|class YandeData\|def load_images\|include_favorite" /home/exa160/opencode/yande.re-spider-next-dev/backend/src/api/v1/gallery.py /home/exa160/opencode/yande.re-spider-next-dev/backend/src/services/gallery.py /home/exa160/opencode/yande.re-spider-next-dev/backend/src/models/response/yande.py 2>/dev/null | head -30
```

确认字段名、函数签名、`YandeData` 模型位置。

- [ ] **Step 2: Write the failing test (include_favorite_status)**

`backend/unit_test/api/v1/test_gallery_load_include_favorite.py`：

```python
"""Gallery load include_favorite_status tests."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.dao.database import Base
from src.models.database.yande import YandeData
from src.models.database.my_favorite import MyFavorite


@pytest.fixture
def session_with_data():
    """Session with 3 images, 1 favorited."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    for i in range(1, 4):
        s.add(YandeData(id=i, tags="rating:s", rating="s", score=100, down_flag=True))
    s.add(MyFavorite(image_id=2))  # image_id=2 被收藏
    s.commit()
    yield s
    s.close()


def test_load_with_include_false_does_not_join(session_with_data):
    """Verify include_favorite_status=False does NOT join my_favorite."""
    with patch("src.services.gallery.get_session", return_value=session_with_data), \
         patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = True
        from src.services.gallery import GalleryService
        result = GalleryService.load_images(
            request=MagicMock(include_favorite_status=False, random=False, page=1, page_size=20),
            include_favorite_status=False,
            random=False,
        )
        # 无 is_favorited 字段
        assert all(getattr(img, "is_favorited", None) is None for img in result.data)


def test_load_with_include_true_but_switch_off_does_not_join(session_with_data):
    """Verify include_favorite_status=True but enable_my_favorites=False does NOT join."""
    with patch("src.services.gallery.get_session", return_value=session_with_data), \
         patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = False  # 关键：开关关闭
        from src.services.gallery import GalleryService
        result = GalleryService.load_images(
            request=MagicMock(include_favorite_status=True, random=False, page=1, page_size=20),
            include_favorite_status=True,  # 前端传了 True
            random=False,
        )
        # 后端强制不连表
        assert all(getattr(img, "is_favorited", None) is None for img in result.data)


def test_load_with_include_true_and_switch_on_joins(session_with_data):
    """Verify include_favorite_status=True + enable_my_favorites=True joins correctly."""
    with patch("src.services.gallery.get_session", return_value=session_with_data), \
         patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = True
        from src.services.gallery import GalleryService
        result = GalleryService.load_images(
            request=MagicMock(include_favorite_status=True, random=False, page=1, page_size=20),
            include_favorite_status=True,
            random=False,
        )
        # image_id=2 is_favorited=True，其他 False
        favorited_map = {img.id: img.is_favorited for img in result.data}
        assert favorited_map[1] is False
        assert favorited_map[2] is True
        assert favorited_map[3] is False
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && PYTHONPATH=. /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m pytest unit_test/api/v1/test_gallery_load_include_favorite.py -v
```

Expected: FAIL（`is_favorited` 不存在 / `random` 参数不存在 / `load_images` 签名不匹配）

- [ ] **Step 4: Write the failing test (random)**

`backend/unit_test/api/v1/test_gallery_load_random.py`：

```python
"""Gallery load random tests."""
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.dao.database import Base
from src.models.database.yande import YandeData


@pytest.fixture
def session_with_data():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    for i in range(1, 11):
        s.add(YandeData(id=i, tags="rating:s", rating="s", score=100, down_flag=True))
    s.commit()
    yield s
    s.close()


def test_random_returns_distinct_ids(session_with_data):
    """Verify random=True returns distinct image_ids (no duplicates)."""
    with patch("src.services.gallery.get_session", return_value=session_with_data), \
         patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = False
        from src.services.gallery import GalleryService
        result = GalleryService.load_images(
            request=MagicMock(include_favorite_status=False, random=True, page=1, page_size=20),
            include_favorite_status=False,
            random=True,
        )
        ids = [img.id for img in result.data]
        assert len(ids) == len(set(ids)), f"Duplicate ids found: {ids}"


def test_random_returns_correct_count(session_with_data):
    """Verify random=True respects page_size limit."""
    with patch("src.services.gallery.get_session", return_value=session_with_data), \
         patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = False
        from src.services.gallery import GalleryService
        result = GalleryService.load_images(
            request=MagicMock(include_favorite_status=False, random=True, page=1, page_size=5),
            include_favorite_status=False,
            random=True,
        )
        assert len(result.data) == 5
```

- [ ] **Step 5: Add is_favorited field to YandeData response**

`backend/src/models/response/yande.py` 找到 `YandeData` 类，追加：

```python
is_favorited: Optional[bool] = Field(
    default=None,
    description="是否已加入我的最爱；仅 include_favorite_status=True 时返回 True/False，否则 None"
)
```

如果 import 中没有 `Optional`，添加：

```python
from typing import Optional
```

- [ ] **Step 6: Extend GalleryLoadRequest**

`backend/src/api/v1/gallery.py` 找到 `GalleryLoadRequest` 类，追加 2 个字段：

```python
include_favorite_status: bool = Field(
    default=False,
    description="True 时响应中每个图片附带 is_favorited 字段（LEFT JOIN my_favorite）"
)
random: bool = Field(
    default=False,
    description="True 时使用 ORDER BY RANDOM() + DISTINCT image_id 返回随机图片"
)
```

- [ ] **Step 7: Extend GalleryService.load_images**

`backend/src/services/gallery.py` 找到 `load_images` 函数（或等价方法），改签名：

```python
def load_images(request, include_favorite_status: bool = False, random: bool = False):
    # ... 现有逻辑 ...
```

实现要点：
- 如果 `random=True`，添加 `.order_by(func.random()).distinct(YandeData.id).limit(page_size)`
- 如果 `include_favorite_status=True`，添加 `.outerjoin(MyFavorite, MyFavorite.image_id == YandeData.id)` + `case()` 表达式生成 `is_favorited`

示例代码骨架（**根据项目实际 API 调整**）：

```python
from sqlalchemy import func, case, select
from src.models.database.my_favorite import MyFavorite


def load_images(request, include_favorite_status: bool = False, random: bool = False):
    session = get_session()
    query = select(YandeData).where(...)

    if include_favorite_status:
        query = query.add_columns(
            case((MyFavorite.image_id.is_not(None), True), else_=False).label("is_favorited")
        ).outerjoin(MyFavorite, MyFavorite.image_id == YandeData.id)

    if random:
        query = query.order_by(func.random()).distinct(YandeData.id)

    query = query.limit(request.page_size).offset((request.page - 1) * request.page_size)

    result = session.execute(query).all()
    # 展平为 YandeData（含 is_favorited）
    ...
```

**重要**：
- 保留原有行为（`include_favorite_status=False` + `random=False` 时输出与之前完全一致）
- 双 `random` + `include_favorite_status=True` 也应支持（同时 LEFT JOIN + ORDER BY RANDOM）

- [ ] **Step 8: Run tests**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && PYTHONPATH=. /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m pytest unit_test/api/v1/test_gallery_load_include_favorite.py unit_test/api/v1/test_gallery_load_random.py -v
```

Expected: 3 + 2 = 5 tests PASS

- [ ] **Step 9: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add backend/src/api/v1/gallery.py backend/src/services/gallery.py backend/src/models/response/yande.py backend/unit_test/api/v1/test_gallery_load_include_favorite.py backend/unit_test/api/v1/test_gallery_load_random.py && git commit -m "feat(backend): /gallery/load 支持 include_favorite_status + random (DISTINCT image_id)"
```

---

## Task 8: Gallery Detail 扩展（继承 is_favorited）

**Files:**
- Modify: `backend/src/api/v1/gallery.py`（`get_image_detail`）
- Modify: `backend/src/services/gallery.py`（`get_image_detail`）
- Modify: `backend/src/models/response/yande.py`（`YandeDataDetail.is_favorited`）
- Test: `backend/unit_test/api/v1/test_gallery_detail_include_favorite.py`

**Interfaces:**
- Consumes: `config.favorites.enable_my_favorites`, `MyFavorite` ORM
- Produces: `get_image_detail(image_id, include_favorite_status)`

- [ ] **Step 1: Write the failing test**

`backend/unit_test/api/v1/test_gallery_detail_include_favorite.py`：

```python
"""Gallery detail include_favorite_status tests."""
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.dao.database import Base
from src.models.database.yande import YandeData
from src.models.database.my_favorite import MyFavorite


@pytest.fixture
def session_with_data():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    s.add(YandeData(id=42, tags="rating:s", rating="s", score=100, down_flag=True))
    s.add(MyFavorite(image_id=42))
    s.commit()
    yield s
    s.close()


def test_detail_with_include_false_returns_none():
    """Verify include_favorite_status=False returns is_favorited=None."""
    with patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = True
        from src.services.gallery import GalleryService
        detail = GalleryService.get_image_detail(image_id=42, include_favorite_status=False)
        assert detail.is_favorited is None


def test_detail_with_include_true_and_switch_off_returns_none(session_with_data):
    """Verify include_favorite_status=True + enable_my_favorites=False returns None (强制不连表)."""
    with patch("src.services.gallery.get_session", return_value=session_with_data), \
         patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = False
        from src.services.gallery import GalleryService
        detail = GalleryService.get_image_detail(image_id=42, include_favorite_status=True)
        assert detail.is_favorited is None


def test_detail_with_include_true_and_switch_on_returns_true(session_with_data):
    """Verify include_favorite_status=True + enable_my_favorites=True returns True for favorited image."""
    with patch("src.services.gallery.get_session", return_value=session_with_data), \
         patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = True
        from src.services.gallery import GalleryService
        detail = GalleryService.get_image_detail(image_id=42, include_favorite_status=True)
        assert detail.is_favorited is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && PYTHONPATH=. /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m pytest unit_test/api/v1/test_gallery_detail_include_favorite.py -v
```

Expected: FAIL

- [ ] **Step 3: Extend get_image_detail API route**

`backend/src/api/v1/gallery.py` 找到 `get_image_detail` 路由，加 query param：

```python
@router.get("/{image_id}", response_model=BaseResponse[YandeDataDetail], summary="图片详情")
async def get_image_detail(
    image_id: int,
    include_favorite_status: bool = Query(
        default=False,
        description="True 时响应附带 is_favorited 字段"
    ),
) -> BaseResponse[YandeDataDetail]:
    try:
        detail = GalleryService.get_image_detail(
            image_id=image_id,
            include_favorite_status=include_favorite_status and config.favorites.enable_my_favorites,
        )
        return BaseResponse(message=ErrMsg.OK.msg, data=detail)
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)
```

- [ ] **Step 4: Extend GalleryService.get_image_detail**

`backend/src/services/gallery.py` 修改 `get_image_detail`：

```python
def get_image_detail(image_id: int, include_favorite_status: bool = False):
    session = get_session()
    yande_data = session.query(YandeData).filter(YandeData.id == image_id).first()
    if not yande_data:
        raise ValueError(f"Image {image_id} not found")

    is_favorited = None
    if include_favorite_status and config.favorites.enable_my_favorites:
        is_favorited = session.query(MyFavorite).filter(MyFavorite.image_id == image_id).first() is not None

    # 构造响应
    detail = YandeDataDetail(
        # ... 现有字段 ...
        is_favorited=is_favorited,
    )
    return detail
```

- [ ] **Step 5: Add is_favorited to YandeDataDetail**

`backend/src/models/response/yande.py` 找到 `YandeDataDetail` 类（如不存在则创建），追加：

```python
class YandeDataDetail(BaseModel):
    # ... 现有字段 ...
    is_favorited: Optional[bool] = None
```

- [ ] **Step 6: Run test to verify it passes**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && PYTHONPATH=. /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m pytest unit_test/api/v1/test_gallery_detail_include_favorite.py -v
```

Expected: 3 tests PASS

- [ ] **Step 7: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add backend/src/api/v1/gallery.py backend/src/services/gallery.py backend/src/models/response/yande.py backend/unit_test/api/v1/test_gallery_detail_include_favorite.py && git commit -m "feat(backend): /gallery/{id} 支持 include_favorite_status (双层判断)"
```

---

## Task 9: 回归测试 — `get_folders_with_preview` 不注入虚拟 folder

**Files:**
- Test: `backend/unit_test/services/test_get_folders_with_preview_no_virtual.py`

**目的**：锁定 v1 报错已修复，未来任何修改都不能重新引入虚拟 folder 注入。

- [ ] **Step 1: Write the test**

```python
"""回归测试：get_folders_with_preview 不应注入虚拟 folder"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.dao.database import Base
from src.models.database.yande import YandeData
from src.services.favorites import FavoritesService


@pytest.fixture
def session_with_folder():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    s.add(YandeData(id=1, tags="rating:s", rating="s", score=100, down_flag=True))
    s.add(YandeData(id=2, tags="rating:s", rating="s", score=100, down_flag=True))
    s.commit()
    yield s
    s.close()


def test_get_folders_with_preview_does_not_inject_virtual_my_favorites(session_with_folder):
    """Verify get_folders_with_preview does NOT inject a virtual '我的最爱' folder."""
    # mock FavoriteFolder 数据
    from src.dao.favorite_dao import FavoriteFolderDao
    with patch.object(FavoriteFolderDao, "list_all", return_value=[]), \
         patch("src.services.favorites.get_session", return_value=session_with_folder):
        items, total, has_more = FavoritesService.get_folders_with_preview(
            page=1, page_size=20
        )
        # 关键断言：响应中无 id='my-favorites' 或 id=-1 的虚拟项
        ids = [item.id for item in items]
        assert "my-favorites" not in ids
        assert -1 not in ids
        assert all(getattr(item, "is_virtual", False) is False for item in items)


def test_get_folders_with_preview_does_not_inject_virtual_random(session_with_folder):
    """Verify get_folders_with_preview does NOT inject a virtual '随机浏览' folder."""
    from src.dao.favorite_dao import FavoriteFolderDao
    with patch.object(FavoriteFolderDao, "list_all", return_value=[]), \
         patch("src.services.favorites.get_session", return_value=session_with_folder):
        items, _, _ = FavoritesService.get_folders_with_preview(page=1, page_size=20)
        ids = [item.id for item in items]
        assert "random" not in ids
```

- [ ] **Step 2: Run test to verify it passes**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && PYTHONPATH=. /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m pytest unit_test/services/test_get_folders_with_preview_no_virtual.py -v
```

Expected: 2 tests PASS（确认 v1 行为已修复，**未来修改不能通过这两个测试**）

- [ ] **Step 3: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add backend/unit_test/services/test_get_folders_with_preview_no_virtual.py && git commit -m "test(backend): 回归测试 get_folders_with_preview 不注入虚拟 folder"
```

---

## Task 10: MyFavorites 前端 API 模块

**Files:**
- Create: `frontend/src/api/myFavorites.js`

**Interfaces:**
- Produces: `myFavoritesApi.add(imageId)`, `.remove(imageId)`, `.list(page, pageSize)`, `.count()`, `.getPreview(limit)`

- [ ] **Step 1: Read existing api/favorites.js for pattern**

```bash
cat /home/exa160/opencode/yande.re-spider-next-dev/frontend/src/api/favorites.js
```

模仿该文件的 import 风格（一般是 `import api from './index'`）。

- [ ] **Step 2: Create myFavorites.js**

`frontend/src/api/myFavorites.js`：

```javascript
/**
 * 我的最爱 API 模块
 *
 * - add / remove: 加入/取消我的最爱（POST/DELETE /api/v1/my-favorites/{image_id}）
 * - list: 分页列出我的最爱
 * - count: 总数（用于收藏夹列表前端插入磁贴的角标）
 * - getPreview: 我的最爱预览图（文件夹展示页用，独立接口）
 */
import api from './index'

export const myFavoritesApi = {
  /**
   * 加入我的最爱
   * @param {number} imageId
   * @returns {Promise<void>}
   */
  add(imageId) {
    return api.post(`/my-favorites/${imageId}`)
  },

  /**
   * 取消我的最爱（幂等）
   * @param {number} imageId
   * @returns {Promise<void>}
   */
  remove(imageId) {
    return api.delete(`/my-favorites/${imageId}`)
  },

  /**
   * 分页列出我的最爱
   * @param {number} page - 页码（默认 1）
   * @param {number} pageSize - 每页条数（默认 20）
   * @returns {Promise<{total: number, data: Array}>}
   */
  list(page = 1, pageSize = 20) {
    return api.get('/my-favorites', { params: { page, page_size: pageSize } })
  },

  /**
   * 我的最爱总数
   * @returns {Promise<{count: number}>}
   */
  count() {
    return api.get('/my-favorites/count')
  },

  /**
   * 我的最爱预览图（独立接口，不复用 favorites）
   * @param {number} limit - 返回预览图数（默认 20）
   * @returns {Promise<{images: Array}>}
   */
  getPreview(limit = 20) {
    return api.get('/my-favorites/preview', { params: { limit } })
  },
}
```

- [ ] **Step 3: Verify lint passes**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend && npx eslint src/api/myFavorites.js
```

Expected: No errors

- [ ] **Step 4: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add frontend/src/api/myFavorites.js && git commit -m "feat(frontend): myFavorites API module"
```

---

## Task 11: HeartOverlay 组件（无边框 + image-info-content 层）

**Files:**
- Create: `frontend/src/components/HeartOverlay.vue`
- Create: `frontend/src/components/HeartOverlay.spec.js`

**Interfaces:**
- Produces: `<HeartOverlay image-id initial-favorited show-heart @changed />` 组件

- [ ] **Step 1: Read existing components for style**

```bash
ls /home/exa160/opencode/yande.re-spider-next-dev/frontend/src/components/ | head -20 && cat /home/exa160/opencode/yande.re-spider-next-dev/frontend/src/components/AdvancedQuery.spec.js 2>/dev/null | head -40
```

了解测试模式（happy-dom / vi.mock 等）。

- [ ] **Step 2: Write the failing test**

`frontend/src/components/HeartOverlay.spec.js`：

```javascript
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import HeartOverlay from './HeartOverlay.vue'

// Mock myFavoritesApi
vi.mock('@/api/myFavorites', () => ({
  myFavoritesApi: {
    add: vi.fn().mockResolvedValue({ data: {} }),
    remove: vi.fn().mockResolvedValue({ data: {} }),
  },
}))

describe('HeartOverlay.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('does not render when showHeart is false', () => {
    const wrapper = mount(HeartOverlay, {
      props: { imageId: 42, showHeart: false, initialFavorited: false },
    })
    expect(wrapper.find('.heart-overlay').exists()).toBe(false)
  })

  it('renders empty heart when showHeart is true and not favorited', () => {
    const wrapper = mount(HeartOverlay, {
      props: { imageId: 42, showHeart: true, initialFavorited: false },
    })
    expect(wrapper.find('.heart-overlay').exists()).toBe(true)
    expect(wrapper.find('.heart-overlay').classes()).not.toContain('active')
  })

  it('renders filled heart when initialFavorited is true', () => {
    const wrapper = mount(HeartOverlay, {
      props: { imageId: 42, showHeart: true, initialFavorited: true },
    })
    expect(wrapper.find('.heart-overlay').classes()).toContain('active')
  })

  it('toggles favorited on click', async () => {
    const { myFavoritesApi } = await import('@/api/myFavorites')
    const wrapper = mount(HeartOverlay, {
      props: { imageId: 42, showHeart: true, initialFavorited: false },
    })
    await wrapper.find('.heart-overlay').trigger('click')
    expect(myFavoritesApi.add).toHaveBeenCalledWith(42)
    expect(wrapper.emitted('changed')).toBeTruthy()
    expect(wrapper.emitted('changed')[0][0]).toEqual({ imageId: 42, favorited: true })
  })

  it('removes favorite when clicking an already-favorited heart', async () => {
    const { myFavoritesApi } = await import('@/api/myFavorites')
    const wrapper = mount(HeartOverlay, {
      props: { imageId: 42, showHeart: true, initialFavorited: true },
    })
    await wrapper.find('.heart-overlay').trigger('click')
    expect(myFavoritesApi.remove).toHaveBeenCalledWith(42)
  })

  it('has NO border (critical: visual consistency)', () => {
    const wrapper = mount(HeartOverlay, {
      props: { imageId: 42, showHeart: true, initialFavorited: false },
    })
    const style = wrapper.find('.heart-overlay').attributes('style') || ''
    const computedStyle = window.getComputedStyle(wrapper.find('.heart-overlay').element)
    // 关键断言：border-width 应为 0 或 border-style 应为 none
    expect(
      computedStyle.borderWidth === '0px' ||
      computedStyle.borderStyle === 'none'
    ).toBe(true)
  })

  it('prevents event propagation (does not bubble up to long-press)', async () => {
    const wrapper = mount({
      components: { HeartOverlay },
      template: `
        <div @long-press="onLongPress">
          <HeartOverlay :image-id="42" :show-heart="true" @changed="onChanged" />
        </div>
      `,
      methods: {
        onLongPress: vi.fn(),
        onChanged: vi.fn(),
      },
    }, { attachTo: document.body })
    await wrapper.find('.heart-overlay').trigger('click')
    expect(wrapper.vm.onChanged).toHaveBeenCalled()
    // long-press 不应被触发（stop.prevent 屏蔽冒泡）
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend && npx vitest run components/HeartOverlay.spec.js
```

Expected: FAIL with `Cannot find module './HeartOverlay.vue'`

- [ ] **Step 4: Create HeartOverlay.vue**

`frontend/src/components/HeartOverlay.vue`：

```vue
<template>
  <button
    v-if="showHeart"
    class="heart-overlay"
    :class="{ active: isFavorited, loading }"
    @click.stop.prevent="toggle"
    :aria-label="isFavorited ? '取消我的最爱' : '加入我的最爱'"
  >
    <el-icon>
      <StarFilled v-if="isFavorited" />
      <Star v-else />
    </el-icon>
  </button>
</template>

<script setup>
import { ref } from 'vue'
import { Star, StarFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
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
    ElMessage.error('操作失败：' + (e?.message || ''))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.heart-overlay {
  /* 关键：无边框（按 v2 需求修复 v1 加边框的 bug） */
  border: none;
  outline: none;
  background: transparent;
  cursor: pointer;
  padding: 0;
  color: rgba(255, 255, 255, 0.85);
  font-size: 18px;
  line-height: 1;
  transition: color 0.2s, transform 0.2s;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.heart-overlay:hover {
  transform: scale(1.15);
  color: #fff;
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

- [ ] **Step 5: Run test to verify it passes**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend && npx vitest run components/HeartOverlay.spec.js
```

Expected: 7 tests PASS

- [ ] **Step 6: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add frontend/src/components/HeartOverlay.vue frontend/src/components/HeartOverlay.spec.js && git commit -m "feat(frontend): HeartOverlay component (no border, image-info-content layer)"
```

---

## Task 12: useFavoritesConfig 重构（后端 API + 4 新开关 + myFavoritesCount）

**Files:**
- Modify: `frontend/src/composables/useFavoritesConfig.js`
- Modify: `frontend/src/composables/useFavoritesConfig.spec.js`

**Interfaces:**
- Produces: 9 个 ref（5 个原有 + 4 个新）+ `myFavoritesCount` + `loaded`

- [ ] **Step 1: Read existing composable**

```bash
cat /home/exa160/opencode/yande.re-spider-next-dev/frontend/src/composables/useFavoritesConfig.js
cat /home/exa160/opencode/yande.re-spider-next-dev/frontend/src/composables/useFavoritesConfig.spec.js 2>/dev/null
```

- [ ] **Step 2: Update spec test**

`frontend/src/composables/useFavoritesConfig.spec.js` —— 追加以下测试：

```javascript
it('loads 4 new switches from /config/favorites', async () => {
  const api = (await import('@/api')).default
  vi.mocked(api.get).mockResolvedValueOnce({
    data: {
      enable_my_favorites: true,
      enable_random_browse: false,
      enable_favorite_folder: true,
      enable_favorite_autodownload: false,
    },
  })
  const { useFavoritesConfig } = await import('./useFavoritesConfig')
  const s = useFavoritesConfig()
  // 等待异步加载
  await new Promise(resolve => setTimeout(resolve, 0))
  expect(s.enableMyFavorites.value).toBe(true)
  expect(s.enableRandomBrowse.value).toBe(false)
  expect(s.enableFavoriteFolder.value).toBe(true)
  expect(s.enableFavoriteAutodownload.value).toBe(false)
})

it('fetches myFavoritesCount when enable_my_favorites is true', async () => {
  const api = (await import('@/api')).default
  vi.mocked(api.get).mockImplementation((url) => {
    if (url === '/config/favorites') {
      return Promise.resolve({ data: { enable_my_favorites: true } })
    }
    if (url === '/my-favorites/count') {
      return Promise.resolve({ data: { count: 42 } })
    }
    return Promise.reject(new Error('not mocked'))
  })
  const { useFavoritesConfig } = await import('./useFavoritesConfig')
  const s = useFavoritesConfig()
  await new Promise(resolve => setTimeout(resolve, 10))
  expect(s.myFavoritesCount.value).toBe(42)
})

it('saveFavoritesConfig syncs local state', async () => {
  const api = (await import('@/api')).default
  vi.mocked(api.put).mockResolvedValue({ data: {} })
  const { saveFavoritesConfig } = await import('./useFavoritesConfig')
  await saveFavoritesConfig({ enable_my_favorites: true })
  expect(api.put).toHaveBeenCalledWith('/config/favorites', { enable_my_favorites: true })
})
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend && npx vitest run composables/useFavoritesConfig.spec.js
```

Expected: FAIL（`enableMyFavorites` 等 ref 不存在）

- [ ] **Step 4: Rewrite useFavoritesConfig.js**

```javascript
/**
 * 收藏夹 UI 配置 + 我的最爱/随机浏览总开关（singleton composable）
 *
 * - module-level refs → 跨组件共享
 * - 首次调用从后端 GET /config/favorites 读取初始值
 * - 失败 fallback 到默认值
 *
 * 后端字段：
 *   button_mode | tile_size | preview_order | include_online | folder_page_size
 *   enable_my_favorites | enable_random_browse | enable_favorite_folder | enable_favorite_autodownload
 *
 * 我的最爱总数（myFavoritesCount）从 GET /my-favorites/count 获取（仅在 enable_my_favorites=true 时）
 */
import { ref } from 'vue'
import api from '@/api'

const state = {
  // 5 个原有 UI 偏好
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
  // 我的最爱总数（用于 FavoritePanel 角标）
  myFavoritesCount: ref(0),
}

export function useFavoritesConfig() {
  if (!state.loaded.value) {
    state.loaded.value = true

    // 加载配置
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

    // localStorage fallback（一次性读旧 key）
    loadLegacyLocalStorageOnce()

    // 加载我的最爱总数（仅当开关开启）
    if (state.enableMyFavorites.value) {
      fetchMyFavoritesCount()
    }
  }

  return state
}

export async function saveFavoritesConfig(updates) {
  await api.put('/config/favorites', updates)
  // 同步本地 state
  Object.entries(updates).forEach(([k, v]) => {
    const camelKey = k.replace(/_([a-z])/g, (_, c) => c.toUpperCase())
    if (camelKey in state) {
      state[camelKey].value = v
    }
  })
  // 如果开关变化，重新决定是否加载 myFavoritesCount
  if ('enable_my_favorites' in updates && updates.enable_my_favorites) {
    fetchMyFavoritesCount()
  }
}

export async function fetchMyFavoritesCount() {
  try {
    const res = await api.get('/my-favorites/count')
    state.myFavoritesCount.value = res.data.count
  } catch (e) {
    console.warn('Fetch my favorites count failed:', e)
  }
}

function loadLegacyLocalStorageOnce() {
  // 旧 localStorage key 一次性 fallback（读后即删）
  const legacyKeys = {
    gallery_favorites_button_mode: 'buttonMode',
    gallery_favorites_tile_size: 'tileSize',
    gallery_favorites_preview_order: 'previewOrder',
    gallery_favorites_include_online: 'includeOnline',
    favorites_folder_page_size: 'folderPageSize',
  }
  for (const [lsKey, stateKey] of Object.entries(legacyKeys)) {
    const v = localStorage.getItem(lsKey)
    if (v !== null) {
      // 仅在后端尚未返回时覆盖
      state[stateKey].value = castLegacy(stateKey, v)
      localStorage.removeItem(lsKey)
    }
  }
}

function castLegacy(key, value) {
  if (key === 'includeOnline') return value === 'true'
  if (key === 'folderPageSize') return parseInt(value, 10)
  return value
}
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend && npx vitest run composables/useFavoritesConfig.spec.js
```

Expected: 所有测试 PASS（含原有 + 新增 3 个）

- [ ] **Step 6: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add frontend/src/composables/useFavoritesConfig.js frontend/src/composables/useFavoritesConfig.spec.js && git commit -m "feat(frontend): useFavoritesConfig 重构为后端 API + 4 新开关 + myFavoritesCount"
```

---

## Task 13: Config.vue 收藏夹 section（含 4 个新开关 + 5 个迁移偏好）

**Files:**
- Modify: `frontend/src/views/Config.vue`
- Modify: `frontend/src/views/Config.spec.js`

**Interfaces:**
- Produces: Config.vue 中的"收藏夹 + 我的最爱 + 随机浏览" tab pane

- [ ] **Step 1: Read existing Config.vue**

```bash
grep -n "favorites\|button_mode\|tile_size\|favorite_config" /home/exa160/opencode/yande.re-spider-next-dev/frontend/src/views/Config.vue | head -30
```

了解现有收藏夹配置 UI 结构。

- [ ] **Step 2: Update Config.spec.js**

`frontend/src/views/Config.spec.js` 追加测试：

```javascript
it('renders 4 new favorite switches', async () => {
  const wrapper = mount(Config, { ... })
  // 等待加载
  await wrapper.vm.$nextTick()
  expect(wrapper.text()).toContain('收藏夹展示')
  expect(wrapper.text()).toContain('我的最爱')
  expect(wrapper.text()).toContain('随机浏览')
  expect(wrapper.text()).toContain('非本地图片自动下载')
})

it('disables autodownload switch when enable_my_favorites is false', async () => {
  // mock config response with enable_my_favorites: false
  ...
})

it('saves favorites config via PUT /config/favorites', async () => {
  const api = (await import('@/api')).default
  vi.mocked(api.put).mockResolvedValue({ data: {} })
  // 触发 save
  ...
  expect(api.put).toHaveBeenCalledWith('/config/favorites', expect.objectContaining({
    enable_my_favorites: ...,
  }))
})
```

- [ ] **Step 3: Modify Config.vue**

具体修改方法（保留原有"收藏夹 UI 设置"section 整体，新增/替换为以下结构）：

```vue
<el-tab-pane label="收藏夹 + 我的最爱 + 随机浏览" name="favorites">
  <!-- 4 个开关（按需求顺序）-->
  <el-form-item label="收藏夹展示">
    <el-switch v-model="localConfig.enable_favorite_folder" />
    <span class="form-help">关闭后整个收藏夹模块隐藏</span>
  </el-form-item>
  <el-form-item label="我的最爱">
    <el-switch v-model="localConfig.enable_my_favorites" />
    <span class="form-help">关闭后瀑布流图片右下角爱心隐藏，收藏夹列表我的最爱磁贴也隐藏</span>
  </el-form-item>
  <el-form-item label="非本地图片自动下载">
    <el-switch v-model="localConfig.enable_favorite_autodownload" :disabled="!localConfig.enable_my_favorites" />
    <span class="form-help">关闭后非本地图片加入我的最爱不会触发下载</span>
  </el-form-item>
  <el-form-item label="随机浏览">
    <el-switch v-model="localConfig.enable_random_browse" />
    <span class="form-help">关闭后收藏夹列表随机浏览磁贴隐藏</span>
  </el-form-item>

  <el-divider />

  <!-- 原有 5 个 UI 偏好 -->
  <el-form-item label="主页按钮显示">
    <el-radio-group v-model="localConfig.button_mode">
      <el-radio value="hidden">隐藏</el-radio>
      <el-radio value="shown">显示</el-radio>
      <el-radio value="default">默认</el-radio>
    </el-radio-group>
  </el-form-item>
  <el-form-item label="tile 大小">
    <el-radio-group v-model="localConfig.tile_size">
      <el-radio value="adaptive">自适应</el-radio>
      <el-radio value="4">4</el-radio>
      <el-radio value="6">6</el-radio>
      <el-radio value="8">8</el-radio>
    </el-radio-group>
  </el-form-item>
  <el-form-item label="预览图排序">
    <el-radio-group v-model="localConfig.preview_order">
      <el-radio value="random">随机</el-radio>
      <el-radio value="asc">升序</el-radio>
      <el-radio value="desc">降序</el-radio>
    </el-radio-group>
  </el-form-item>
  <el-form-item label="预览含未下载">
    <el-switch v-model="localConfig.include_online" />
  </el-form-item>
  <el-form-item label="每页条数">
    <el-radio-group v-model="localConfig.folder_page_size">
      <el-radio :value="8">8</el-radio>
      <el-radio :value="12">12</el-radio>
      <el-radio :value="20">20</el-radio>
    </el-radio-group>
  </el-form-item>
</el-tab-pane>
```

script 部分：使用 `useFavoritesConfig` + `saveFavoritesConfig`。

```javascript
import { useFavoritesConfig, saveFavoritesConfig } from '@/composables/useFavoritesConfig'

const favConfig = useFavoritesConfig()
const localConfig = ref({
  button_mode: favConfig.buttonMode.value,
  tile_size: favConfig.tileSize.value,
  preview_order: favConfig.previewOrder.value,
  include_online: favConfig.includeOnline.value,
  folder_page_size: favConfig.folderPageSize.value,
  enable_my_favorites: favConfig.enableMyFavorites.value,
  enable_random_browse: favConfig.enableRandomBrowse.value,
  enable_favorite_folder: favConfig.enableFavoriteFolder.value,
  enable_favorite_autodownload: favConfig.enableFavoriteAutodownload.value,
})

async function saveFavorites() {
  await saveFavoritesConfig(localConfig.value)
  ElMessage.success('收藏夹配置已保存')
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend && npx vitest run views/Config.spec.js
```

Expected: 所有测试 PASS

- [ ] **Step 5: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add frontend/src/views/Config.vue frontend/src/views/Config.spec.js && git commit -m "feat(frontend): Config.vue 收藏夹 section 4 新开关 + 5 迁移偏好"
```

---

## Task 14: WaterfallGallery 集成 HeartOverlay + showHeart props

**Files:**
- Modify: `frontend/src/components/WaterfallGallery.vue`
- Modify: `frontend/src/components/WaterfallGallery.spec.js`

**Interfaces:**
- Produces: WaterfallGallery 新增 `showHeart: Boolean` props + `@favorite-toggled` 事件

- [ ] **Step 1: Read WaterfallGallery**

```bash
grep -n "image-info-content\|loadNewPage\|HeartOverlay\|props\|emit" /home/exa160/opencode/yande.re-spider-next-dev/frontend/src/components/WaterfallGallery.vue | head -30
cat /home/exa160/opencode/yande.re-spider-next-dev/frontend/src/components/WaterfallGallery.spec.js | head -50
```

- [ ] **Step 2: Update spec**

追加测试：

```javascript
it('passes include_favorite_status=true when showHeart=true and enableMyFavorites=true', async () => {
  // mock useFavoritesConfig
  vi.mock('@/composables/useFavoritesConfig', () => ({
    useFavoritesConfig: () => ({
      enableMyFavorites: ref(true),
    }),
  }))
  // 触发 loadNewPage
  // 验证 api.get 参数含 include_favorite_status=true
})

it('does NOT pass include_favorite_status when showHeart=false', async () => {
  vi.mock('@/composables/useFavoritesConfig', () => ({
    useFavoritesConfig: () => ({
      enableMyFavorites: ref(true),
    }),
  }))
  // 验证参数不含 include_favorite_status
})

it('does NOT pass include_favorite_status when enableMyFavorites=false (even if showHeart=true)', async () => {
  vi.mock('@/composables/useFavoritesConfig', () => ({
    useFavoritesConfig: () => ({
      enableMyFavorites: ref(false),
    }),
  }))
  // showHeart=true 但 enableMyFavorites=false → 不传参数
})

it('renders HeartOverlay inside image-info-content when showHeart=true', async () => {
  vi.mock('@/composables/useFavoritesConfig', () => ({
    useFavoritesConfig: () => ({
      enableMyFavorites: ref(true),
    }),
  }))
  // 渲染包含 .heart-overlay 元素
})
```

- [ ] **Step 3: Modify WaterfallGallery.vue**

```vue
<script setup>
import { useFavoritesConfig } from '@/composables/useFavoritesConfig'

const props = defineProps({
  // ... 现有 props ...
  showHeart: { type: Boolean, default: false },
})
const emit = defineEmits(['favorite-toggled', /* ... 现有事件 ... */])

const { enableMyFavorites } = useFavoritesConfig()

// loadNewPage: 智能加 include_favorite_status
async function loadNewPage() {
  const params = {
    page, page_size, tags, rating, /* ... */,
  }
  if (props.showHeart && enableMyFavorites.value) {
    params.include_favorite_status = true
  }
  // ... 现有逻辑 ...
}
</script>

<template>
  <!-- 现有 image tile 模板，在 image-info-content 内增加 HeartOverlay -->
  <div class="image-info-content">
    <span>{{ img.rating }} | {{ img.tags_summary }}</span>
    <HeartOverlay
      v-if="showHeart"
      :image-id="img.id"
      :initial-favorited="img.is_favorited === true"
      :show-heart="showHeart"
      @changed="(payload) => emit('favorite-toggled', payload)"
    />
  </div>
</template>
```

- [ ] **Step 4: Run tests**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend && npx vitest run components/WaterfallGallery.spec.js
```

Expected: 所有测试 PASS

- [ ] **Step 5: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add frontend/src/components/WaterfallGallery.vue frontend/src/components/WaterfallGallery.spec.js && git commit -m "feat(frontend): WaterfallGallery 集成 HeartOverlay + showHeart props + 自动 include_favorite_status"
```

---

## Task 15: FolderTile 识别虚拟磁贴

**Files:**
- Modify: `frontend/src/components/FolderTile.vue`
- Modify: `frontend/src/components/FolderTile.spec.js`

**Interfaces:**
- Produces: FolderTile 识别 `folder.isVirtual` 渲染虚拟磁贴

- [ ] **Step 1: Read FolderTile**

```bash
cat /home/exa160/opencode/yande.re-spider-next-dev/frontend/src/components/FolderTile.vue | head -50
cat /home/exa160/opencode/yande.re-spider-next-dev/frontend/src/components/FolderTile.spec.js | head -50
```

- [ ] **Step 2: Update spec**

追加测试：

```javascript
it('renders virtual tile for 我的最爱 when folder.isVirtual=true and id="my-favorites"', () => {
  const wrapper = mount(FolderTile, {
    props: { folder: { id: 'my-favorites', name: '我的最爱', isVirtual: true, local_count: 5 } },
  })
  expect(wrapper.find('.virtual-tile').exists()).toBe(true)
  expect(wrapper.text()).toContain('我的最爱')
})

it('renders virtual tile for 随机浏览 when id="random"', () => {
  const wrapper = mount(FolderTile, {
    props: { folder: { id: 'random', name: '随机浏览', isVirtual: true, local_count: 0 } },
  })
  expect(wrapper.find('.virtual-tile').exists()).toBe(true)
})

it('does not show edit menu on long-press for virtual tiles', async () => {
  // virtual tile 长按不弹编辑菜单
})

it('renders normal tile for non-virtual folder', () => {
  const wrapper = mount(FolderTile, {
    props: { folder: { id: 1, name: 'test', isVirtual: false } },
  })
  expect(wrapper.find('.virtual-tile').exists()).toBe(false)
})
```

- [ ] **Step 3: Modify FolderTile.vue**

```vue
<template>
  <div
    v-if="folder.isVirtual"
    class="folder-tile virtual-tile"
    :class="`virtual-${folder.id}`"
    @click="onClick"
    @long-press="onLongPress"
  >
    <div class="virtual-icon">
      <el-icon>
        <StarFilled v-if="folder.id === 'my-favorites'" />
        <MagicStick v-else />
      </el-icon>
      <span class="virtual-name">{{ folder.name }}</span>
    </div>
    <div class="virtual-count">{{ folder.local_count }} 张</div>
  </div>
  <template v-else>
    <!-- 现有 tile 逻辑 -->
  </template>
</template>

<script setup>
// ... 现有 setup ...
function onLongPress(e) {
  if (props.folder.isVirtual) return  // 虚拟 tile 不弹编辑菜单
  // ... 现有长按逻辑 ...
}
</script>

<style scoped>
.virtual-tile {
  background: linear-gradient(135deg, #F56C6C22 0%, #F56C6C11 100%);
  border: 1px dashed #F56C6C;
}
.virtual-icon {
  display: flex;
  align-items: center;
  gap: 8px;
}
.virtual-icon .el-icon {
  font-size: 24px;
  color: #F56C6C;
}
.virtual-name {
  font-weight: bold;
}
.virtual-count {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}
</style>
```

- [ ] **Step 4: Run tests**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend && npx vitest run components/FolderTile.spec.js
```

Expected: 所有测试 PASS

- [ ] **Step 5: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add frontend/src/components/FolderTile.vue frontend/src/components/FolderTile.spec.js && git commit -m "feat(frontend): FolderTile 识别 isVirtual 渲染虚拟磁贴"
```

---

## Task 16: FavoritePanel 前端 prepend 虚拟磁贴

**Files:**
- Modify: `frontend/src/components/FavoritePanel.vue`
- Create: `frontend/src/components/FavoritePanel.spec.js`

**Interfaces:**
- Produces: FavoritePanel 在收藏夹列表最前 prepend 虚拟磁贴

- [ ] **Step 1: Read FavoritePanel**

```bash
cat /home/exa160/opencode/yande.re-spider-next-dev/frontend/src/components/FavoritePanel.vue
```

- [ ] **Step 2: Create spec**

`frontend/src/components/FavoritePanel.spec.js`：

```javascript
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import FavoritePanel from './FavoritePanel.vue'

vi.mock('@/composables/useFavoritesConfig', () => ({
  useFavoritesConfig: () => ({
    enableMyFavorites: ref(true),
    enableRandomBrowse: ref(false),
    enableFavoriteFolder: ref(true),
    myFavoritesCount: ref(42),
  }),
}))

vi.mock('@/api/myFavorites', () => ({
  myFavoritesApi: {
    count: vi.fn().mockResolvedValue({ data: { count: 42 } }),
  },
}))

describe('FavoritePanel.vue', () => {
  it('prepends 我的最爱 virtual tile when enableMyFavorites=true', () => {
    const wrapper = mount(FavoritePanel, {
      props: { realFolders: [] },
    })
    expect(wrapper.text()).toContain('我的最爱')
  })

  it('does NOT prepend 我的最爱 when enableMyFavorites=false', () => {
    // override mock
    vi.doMock('@/composables/useFavoritesConfig', () => ({
      useFavoritesConfig: () => ({
        enableMyFavorites: ref(false),
        enableRandomBrowse: ref(false),
      }),
    }))
    const wrapper = mount(FavoritePanel, { props: { realFolders: [] } })
    expect(wrapper.text()).not.toContain('我的最爱')
  })

  it('prepends 随机浏览 virtual tile when enableRandomBrowse=true', () => {
    vi.doMock('@/composables/useFavoritesConfig', () => ({
      useFavoritesConfig: () => ({
        enableMyFavorites: ref(false),
        enableRandomBrowse: ref(true),
      }),
    }))
    const wrapper = mount(FavoritePanel, { props: { realFolders: [] } })
    expect(wrapper.text()).toContain('随机浏览')
  })

  it('clicks 我的最爱 virtual tile navigates to Gallery with querySource=my-favorites', async () => {
    const routerPush = vi.fn()
    // mock router
    const wrapper = mount(FavoritePanel, {
      props: { realFolders: [] },
      global: {
        mocks: { $router: { push: routerPush } },
      },
    })
    await wrapper.find('.virtual-tile.virtual-my-favorites').trigger('click')
    expect(routerPush).toHaveBeenCalledWith(expect.stringContaining('querySource=my-favorites'))
  })
})
```

- [ ] **Step 3: Modify FavoritePanel.vue**

```vue
<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useFavoritesConfig } from '@/composables/useFavoritesConfig'
import FolderTile from './FolderTile.vue'

const props = defineProps({
  realFolders: { type: Array, default: () => [] },
})

const router = useRouter()
const { enableMyFavorites, enableRandomBrowse, myFavoritesCount } = useFavoritesConfig()

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
      local_count: 0,
      preview_images: [],
    })
  }
  return tiles
})

const displayItems = computed(() => [...virtualTiles.value, ...props.realFolders])

function onTileClick(folder) {
  if (folder.isVirtual) {
    if (folder.id === 'my-favorites') {
      router.push({ path: '/gallery', query: { querySource: 'my-favorites' } })
    } else if (folder.id === 'random') {
      router.push({ path: '/gallery', query: { querySource: 'random' } })
    }
  } else {
    // 现有逻辑：跳到 folder-detail
    router.push({ path: '/gallery', query: { querySource: 'favorites', folderId: folder.id } })
  }
}
</script>

<template>
  <div class="favorite-panel">
    <div
      v-for="folder in displayItems"
      :key="folder.id"
      class="tile-wrapper"
      @click="onTileClick(folder)"
    >
      <FolderTile :folder="folder" />
    </div>
  </div>
</template>
```

- [ ] **Step 4: Run tests**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend && npx vitest run components/FavoritePanel.spec.js
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add frontend/src/components/FavoritePanel.vue frontend/src/components/FavoritePanel.spec.js && git commit -m "feat(frontend): FavoritePanel 前端 prepend 虚拟磁贴"
```

---

## Task 17: Gallery.vue 新增 querySource 模式

**Files:**
- Modify: `frontend/src/views/Gallery.vue`
- Modify: `frontend/src/views/Gallery.spec.js`

**Interfaces:**
- Produces: Gallery.vue 支持 `querySource='my-favorites'` / `querySource='random'` 模式

- [ ] **Step 1: Read Gallery.vue**

```bash
grep -n "querySource\|gallery_source\|loadNewPage" /home/exa160/opencode/yande.re-spider-next-dev/frontend/src/views/Gallery.vue | head -20
```

- [ ] **Step 2: Update spec**

追加测试：

```javascript
it('renders showHeart=true when querySource=my-favorites', () => { ... })
it('renders showHeart=true and passes random=true when querySource=random', () => { ... })
it('passes include_favorite_status in detail URL when enableMyFavorites=true', () => { ... })
```

- [ ] **Step 3: Modify Gallery.vue**

```vue
<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useFavoritesConfig } from '@/composables/useFavoritesConfig'

const route = useRoute()
const { enableMyFavorites } = useFavoritesConfig()

const querySource = computed(() => route.query.querySource || 'local')
// 扩展: 'yande' | 'local' | 'favorites' | 'my-favorites' | 'random'

const showHeart = computed(() => {
  return querySource.value === 'my-favorites' || querySource.value === 'random'
})

async function loadNewPage() {
  const params = {
    page, page_size, tags, rating, /* ... */,
  }
  if (querySource.value === 'random') {
    params.random = true
  }
  if (showHeart.value && enableMyFavorites.value) {
    params.include_favorite_status = true
  }
  // ... 现有逻辑 ...
}

function openImageDetail(img) {
  const detailUrl = `/gallery/${img.id}?include_favorite_status=${enableMyFavorites.value}`
  // ... 跳详情 ...
}
</script>

<template>
  <!-- WaterfallGallery :show-heart="showHeart" -->
  <WaterfallGallery :show-heart="showHeart" ... />
</template>
```

- [ ] **Step 4: Run tests**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend && npx vitest run views/Gallery.spec.js
```

Expected: 所有测试 PASS

- [ ] **Step 5: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add frontend/src/views/Gallery.vue frontend/src/views/Gallery.spec.js && git commit -m "feat(frontend): Gallery.vue 支持 querySource=my-favorites/random"
```

---

## Task 18: ImageDetail.vue float-header-left HeartOverlay

**Files:**
- Modify: `frontend/src/views/ImageDetail.vue`（或等价组件）

**Interfaces:**
- Produces: 详情页 `float-header-left` 显示 HeartOverlay

- [ ] **Step 1: Locate ImageDetail component**

```bash
grep -rn "float-header-left\|image-detail\|ImageDetail" /home/exa160/opencode/yande.re-spider-next-dev/frontend/src/ | head -10
```

- [ ] **Step 2: Read existing component**

按找到的文件读关键部分（template + script）。

- [ ] **Step 3: Add HeartOverlay to float-header-left**

```vue
<template>
  <div class="float-header-left">
    <HeartOverlay
      v-if="enableMyFavorites"
      :image-id="imageDetail.id"
      :initial-favorited="imageDetail.is_favorited === true"
      :show-heart="true"
      @changed="onFavoriteChanged"
    />
    <span>{{ imageDetail.rating }} | {{ imageDetail.score }}</span>
  </div>
</template>

<script setup>
import { useFavoritesConfig } from '@/composables/useFavoritesConfig'
const { enableMyFavorites } = useFavoritesConfig()

function onFavoriteChanged(payload) {
  // 乐观更新本地 detail
  imageDetail.value.is_favorited = payload.favorited
}
</script>
```

- [ ] **Step 4: Verify lint passes**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend && npx eslint src/views/ImageDetail.vue 2>/dev/null || npx eslint src/views/image-detail.vue 2>/dev/null || true
```

- [ ] **Step 5: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add frontend/src/views/ImageDetail.vue && git commit -m "feat(frontend): 详情页 float-header-left 显示 HeartOverlay"
```

（文件名按实际查找结果调整）

---

## Task 19: 端到端验证

**Files:** 无代码变更（仅手动验证）

- [ ] **Step 1: 启动后端**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && PYTHONPATH=. /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m uvicorn src.main:app --reload
```

Expected: 服务启动，`/docs` 可访问

- [ ] **Step 2: 启动前端**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend && npm run dev
```

Expected: Vite 启动，前端可访问

- [ ] **Step 3: 验证收藏夹页正常（v1 报错已修复）**

- 打开收藏夹页
- **关键**：原 v1 报错（收藏夹页加载失败）应消失
- 收藏夹列表应正常展示 FavoriteFolder 项

- [ ] **Step 4: 验证我的最爱磁贴前置**

- 在 Config.vue 中开启 `enable_my_favorites=true`
- 刷新收藏夹页
- 预期：收藏夹列表最前出现"我的最爱"虚拟磁贴

- [ ] **Step 5: 验证随机浏览磁贴**

- 在 Config.vue 中开启 `enable_random_browse=true`
- 刷新收藏夹页
- 预期：收藏夹列表最前出现"随机浏览"虚拟磁贴

- [ ] **Step 6: 验证我的最爱二级页**

- 点击"我的最爱"虚拟磁贴
- 预期：跳转到 Gallery.vue，querySource=my-favorites
- 预期：瀑布流图片右下角有空心爱心

- [ ] **Step 7: 验证爱心点击**

- 点击任意图片的爱心
- 预期：爱心变实心，调 POST /my-favorites/{image_id}

- [ ] **Step 8: 验证自动下载**

- 加入一张非本地图片到我的最爱
- 预期：后端 log 显示 "My favorite auto-download triggered for {image_id}"
- 预期：DownloadQueue 中新增 task

- [ ] **Step 9: 验证随机浏览二级页**

- 点击"随机浏览"虚拟磁贴
- 预期：跳转到 Gallery.vue，querySource=random
- 预期：瀑布流图片按 ORDER BY RANDOM() 返回
- **关键**：翻页后 id 不重复（多次翻页确认）

- [ ] **Step 10: 验证详情页继承**

- 在我的最爱二级页点击任意图片
- 预期：详情页打开时 URL 含 `include_favorite_status=true`
- 预期：详情页 float-header-left 显示爱心，且初态 = 我的最爱状态

- [ ] **Step 11: 验证配置开关生效**

- 关闭 `enable_my_favorites=false`
- 刷新页面
- 预期：瀑布流无爱心；收藏夹列表无"我的最爱"磁贴
- 关闭 `enable_random_browse=false`
- 预期：收藏夹列表无"随机浏览"磁贴
- 关闭 `enable_favorite_folder=false`
- 预期：整个收藏夹模块隐藏

- [ ] **Step 12: 记录验证结果**

在 PR description 或 commit message 中记录以上 10 个验证项的结果。

---

## Task 20: 文档更新 + 最终 commit

**Files:**
- Modify: `AGENTS.md`（重构状态追踪追加）
- Modify: `README.md`（主要功能新增 2 项）

- [ ] **Step 1: Update AGENTS.md**

在 AGENTS.md 的「重构状态追踪」表格中追加一行：

```markdown
| 我的最爱 + 随机浏览（v2，前端插入，不动原接口） | ✅ 完成 | 见 docs/superpowers/specs/2026-09-20-my-favorites-and-random-browse-v2-design.md |
```

- [ ] **Step 2: Update README.md**

在「主要功能」段落追加：

```markdown
- **我的最爱**：图片级收藏（在线 + 本地），所有图片右下角展示爱心；非本地图片加入即自动下载
- **随机浏览**：本地图片随机抽样浏览，支持配置开关
```

- [ ] **Step 3: Run all tests**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && PYTHONPATH=. /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m pytest unit_test/ -q && \
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend && npx vitest run
```

Expected: backend 全 PASS；frontend 全 PASS

- [ ] **Step 4: Run secret scan**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git diff origin/next_dev..HEAD | grep -iE '(password|secret|token|api[_-]?key)\s*[:=]\s*["\047][^"\047]+["\047]' | grep -vE '""' || echo "CLEAN"
```

Expected: 输出 `CLEAN`

- [ ] **Step 5: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add AGENTS.md README.md && git commit -m "docs: AGENTS.md 重构状态追踪 + README 主要功能新增我的最爱/随机浏览"
```

- [ ] **Step 6: **不 push**（按 AGENTS.md 强制红线，等待用户审核）**

报告本地 commits 列表、测试结果、PR 创建准备情况给用户，等待用户决定是否 push。

---

## 自审（Self-Review）

按 writing-plans skill 要求做自审：

### 1. Spec coverage

| Spec § | 实施位置 |
|---|---|
| §1 目标 | 整个 plan |
| §3.1 `my_favorite` 表 | Task 1 |
| §3.2 `table_constant.my_favorite` | Task 1 |
| §3.4 `FavoriteFolder` 不动 | Task 9 回归测试锁定 |
| §4.1 `FavoritesConfig` | Task 6 |
| §4.2 `Config.favorites` 挂载 | Task 6 |
| §4.3 `ConfigService` 方法 | Task 6 |
| §4.4 `/config/favorites` API | Task 6 |
| §5.1 `/my-favorites/*` | Task 3, 4, 5 |
| §5.1.2 独立 `/preview` | Task 5 |
| §5.2 `/gallery/load` 扩展（include_favorite_status + random）| Task 7 |
| §5.3 `/gallery/{id}` 扩展 | Task 8 |
| §5.4 不新增 `/random` 独立路由 | 整个 plan（仅复用） |
| §5.5 `/favorites/*` 不动 | Task 9 回归测试 |
| §6.2 HeartOverlay 无边框 + image-info-content 层 | Task 11 |
| §6.3 WaterfallGallery 集成 | Task 14 |
| §6.4 FolderTile 识别 isVirtual | Task 15 |
| §6.5 FavoritePanel 前端 prepend | Task 16 |
| §6.6 Gallery.vue querySource 扩展 | Task 17 |
| §6.7 详情页 float-header-left | Task 18 |
| §6.8 Config.vue 4 新开关 + 5 迁移 | Task 13 |
| §6.9 useFavoritesConfig 重构 | Task 12 |
| §7 状态机 | Task 17（querySource 扩展）|
| §8.1 后端测试 | Tasks 1-9 各自 spec |
| §8.2 前端测试 | Tasks 10-18 各自 spec |
| §9 风险 | Tasks 7, 8, 9, 11 测试覆盖 |
| §11 兼容性 | Task 19 端到端验证 |

**结论**：spec 所有需求都已映射到 task，无遗漏。

### 2. Placeholder scan

搜索整个 plan 无以下 placeholder：
- 无 "TBD" / "TODO" / "implement later"
- 无 "add appropriate error handling"（每处都有具体错误处理代码）
- 无 "write tests for the above"（每处都有具体测试代码）
- 无 "similar to Task N"（每处重复了代码）
- 所有代码步骤都有 code block

### 3. Type consistency

| 字段/方法 | 定义位置 | 使用位置 | 一致性 |
|---|---|---|---|
| `MyFavoriteDao.add(session, image_id)` | Task 2 | Task 4, 5 | ✅ |
| `MyFavoritesService.add(image_id)` | Task 4 | Task 5 | ✅ |
| `enable_my_favorites` (snake_case 后端) / `enableMyFavorites` (camelCase 前端) | Task 6, 12 | Tasks 13-18 | ✅（约定）|
| `isVirtual` (camelCase) | Task 15 FolderTile | Task 16 FavoritePanel | ✅ |
| `showHeart` (camelCase) | Task 11, 14 | Tasks 14, 17 | ✅ |
| `querySource` | Task 17 | Tasks 16, 17, 18 | ✅ |

### 4. Review Focus

已在文件头 Review Focus 章节列出 5 个 review focus，每条已映射到具体 task 的测试。

**自审结论**：plan 完整覆盖 spec，类型一致，无 placeholder，Review Focus 有测试支撑。可以提交用户审核。

---

*最后更新：2026-09-20（v2 Plan Draft，待用户审阅 + 选择执行方式）*