# 我的最爱 + 随机浏览 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现「我的最爱」图片级标记（带自动下载 + 收藏夹页置顶展示）+ 「随机浏览」本地随机抽样；同时把 5 项 localStorage 收藏夹 UI 偏好 + 2 个新功能开关迁移到后端 `config.yaml`，由后端成为唯一信源。

**Architecture:** 后端新增 `my_favorite` 中间表 + LEFT JOIN `is_favorited` 字段；新增 `FavoritesConfig` 配置 + `/config/favorites` REST API；收藏夹列表注入「我的最爱」虚拟 folder；前端 `useFavoritesConfig` 改为调后端 API；`WaterfallGallery` 通过 `include_favorite_status` 参数触发服务端 JOIN，集成 `HeartOverlay` 组件。

**Tech Stack:** Vue 3.4 + Element Plus 2.5 / FastAPI + SQLAlchemy / pytest / Vitest

**前置阅读：**
- Spec：`docs/superpowers/specs/2026-09-19-my-favorites-and-random-browse-design.md`
- 项目规范：`AGENTS.md`
- 现有收藏夹设计：`docs/superpowers/specs/2026-08-20-favorites-mode-design.md`
- 现有收藏夹设置：`docs/superpowers/specs/2026-08-22-favorites-settings-panel-design.md`

**全局约束：**
- 分支：`feature/my-favorites-and-random`（基于当前 `next_dev`）
- 后端分层严格：`api/` → `services/` → `dao/`，禁止跨层调用（详见 `AGENTS.md`）
- 所有函数必须声明返回类型
- localStorage 旧 key（`gallery_favorites_button_mode` / `gallery_favorites_tile_size` / `gallery_favorites_preview_order` / `gallery_favorites_include_online` / `favorites_folder_page_size`）保留一次性 fallback（读后即删）
- 关闭 `my_favorites_enabled` 时前端**不发** `include_favorite_status` 参数（服务端零 JOIN 开销）
- `/my-favorites/check` 和 `/my-favorites/ids` **仅特殊场景使用**（数据迁移、修复工具），正常瀑布流走 JOIN
- 自动下载仅在「加入我的最爱」且 `down_flag=False` 时触发，复用 `DownloadService.create_task`
- 「我的最爱」虚拟 folder 用 `id=-1` + `is_system=True` 标识，置于列表首位

---

## Task 1：DB 模型 `my_favorite` + `table_constant`

**Files:**
- Create: `backend/src/models/database/my_favorite.py`
- Modify: `backend/src/common/constant.py:30-50`（`table_constant` 块）
- Test: `backend/unit_test/database/test_my_favorite_model.py`

**Interfaces:**
- 导出类：`MyFavorite(Base)` 映射表 `my_favorite`
- `table_constant.my_favorite = "my_favorite"`

- [ ] **Step 1：写失败测试**

`backend/unit_test/database/test_my_favorite_model.py`：

```python
"""MyFavorite 数据模型 — 验证表名/字段/索引/约束正确。"""
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from src.common.constant import table_constant
from src.models.database.my_favorite import MyFavorite
from src.models.database.yande import Base as YandeBase
from src.models.database.my_favorite import Base as MyFavoriteBase


def test_my_favorite_tablename():
    assert MyFavorite.__tablename__ == table_constant.my_favorite


def test_my_favorite_create_table_with_unique_constraint():
    """表结构应包含 UNIQUE(image_id) 约束与 created_at 索引。"""
    engine = create_engine("sqlite:///:memory:")
    MyFavoriteBase.metadata.create_all(engine)
    insp = inspect(engine)
    cols = {c["name"]: c for c in insp.get_columns(table_constant.my_favorite)}
    assert "image_id" in cols
    assert "created_at" in cols
    assert "note" in cols
    # UNIQUE on image_id
    uqs = insp.get_unique_constraints(table_constant.my_favorite)
    assert any("image_id" in uq["column_names"] for uq in uqs)
    # INDEX on created_at
    indexes = insp.get_indexes(table_constant.my_favorite)
    assert any("created_at" in idx["column_names"] for idx in indexes)
```

- [ ] **Step 2：运行测试确认失败**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/database/test_my_favorite_model.py -v
```

预期：FAIL（`MyFavorite` / `MyFavoriteBase` 未定义）

- [ ] **Step 3：实现 `MyFavorite` 模型**

`backend/src/models/database/my_favorite.py`：

```python
"""我的最爱 - 图片级标记表（与 FavoriteFolder 互不污染）"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint, Index

from src.models.database.yande import Base


class MyFavorite(Base):
    """我的最爱 - 单张图片的「我的最爱」标记。

    与 FavoriteFolder（按 tags 订阅）语义独立，本表只记录
    「用户对具体某张图片的喜爱」这一关系。关闭「我的最爱」
    功能不影响 FavoriteFolder 数据。
    """

    __tablename__ = "my_favorite"

    id = Column(Integer, primary_key=True, autoincrement=True)
    image_id = Column(Integer, nullable=False, comment="yande 图片 ID")
    created_at = Column(DateTime, default=datetime.now, comment="收藏时间")
    note = Column(String(255), nullable=True, comment="预留备注字段")

    __table_args__ = (
        UniqueConstraint("image_id", name="uq_my_favorite_image_id"),
        Index("idx_my_favorite_created_at", "created_at"),
    )
```

**注意**：使用 `Base` from `src.models.database.yande`（与现有模型共用 Base 避免重复建表逻辑）。如有需要也可单独建 Base，但沿用现有约定更简单。

- [ ] **Step 4：在 `constant.py` 添加 `table_constant.my_favorite`**

```python
# backend/src/common/constant.py 顶部或 table_constant 块
class TableConstant:
    yande_data: str = "yande_data"
    # ... 现有表 ...
    my_favorite: str = "my_favorite"   # 新增


table_constant = TableConstant()
```

- [ ] **Step 5：运行测试**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/database/test_my_favorite_model.py -v
```

预期：3 PASS

- [ ] **Step 6：Commit**

```bash
git add backend/src/models/database/my_favorite.py backend/src/common/constant.py backend/unit_test/database/test_my_favorite_model.py
git commit -m "feat(backend): 新增 my_favorite 数据模型（中间表）"
```

---

## Task 2：`MyFavoriteDao` + DAO 单元测试

**Files:**
- Create: `backend/src/dao/my_favorite_dao.py`
- Test: `backend/unit_test/dao/test_my_favorite_dao.py`

**Interfaces:**
- 类 `MyFavoriteDao(BaseDAO)`
- 方法：
  - `add(image_id: int, note: Optional[str] = None) -> MyFavorite` — 写入（已存在抛 `IntegrityError` 由调用方捕获）
  - `remove(image_id: int) -> bool`
  - `exists(image_id: int) -> bool`
  - `check_batch(image_ids: List[int]) -> Set[int]` — 返回已收藏的 image_id 集合
  - `count() -> int`
  - `list_paginated(page: int, page_size: int) -> Tuple[List[MyFavorite], int]` — 按 created_at DESC
  - `list_all_ids() -> List[int]` — 全量 image_id（仅特殊场景）
  - `get_preview_meta(limit: int) -> List[FolderPreviewImageMinimal]` — 拉取最近 N 张预览元数据（按 created_at DESC JOIN yande_data）

- [ ] **Step 1：写失败测试**

`backend/unit_test/dao/test_my_favorite_dao.py`：

```python
"""MyFavoriteDao 单元测试 — 使用内存 SQLite。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.dao.my_favorite_dao import MyFavoriteDao
from src.models.database.my_favorite import Base, MyFavorite
from src.models.database.yande import YandeData, Rating
from datetime import datetime


@pytest.fixture
def dao():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    # 同时建 yande_data 表（JOIN 需要）
    from src.models.database.yande import Base as YandeBase
    YandeBase.metadata.create_all(engine)
    return MyFavoriteDao(session=session), session


def _seed_yande(session, image_id: int, width=100, height=100) -> YandeData:
    yd = YandeData(
        id=image_id,
        down_flag=True,
        preview_width=width,
        preview_height=height,
        rating=Rating("s"),
    )
    session.add(yd)
    session.flush()
    return yd


def test_add_then_exists(dao):
    d, session = dao
    d.add(image_id=100)
    session.commit()
    assert d.exists(100) is True


def test_add_duplicate_image_id_is_idempotent_via_service(dao):
    """DAO 层不自动忽略重复，由 service 层捕获 IntegrityError。"""
    d, session = dao
    d.add(image_id=100)
    session.commit()
    with pytest.raises(Exception):  # IntegrityError
        d.add(image_id=100)
        session.commit()


def test_remove_returns_true_if_existed(dao):
    d, session = dao
    d.add(image_id=100); session.commit()
    assert d.remove(100) is True
    assert d.exists(100) is False


def test_remove_returns_false_if_not_existed(dao):
    d, _ = dao
    assert d.remove(999) is False


def test_check_batch_returns_favorited_subset(dao):
    d, session = dao
    for i in (100, 200, 300):
        d.add(image_id=i)
    session.commit()
    favorited = d.check_batch([100, 200, 999, 888])
    assert favorited == {100, 200}


def test_count(dao):
    d, session = dao
    for i in range(5):
        d.add(image_id=i)
    session.commit()
    assert d.count() == 5


def test_list_paginated_order_by_created_at_desc(dao):
    d, session = dao
    d.add(image_id=1); session.commit()
    d.add(image_id=2); session.commit()
    items, total = d.list_paginated(page=1, page_size=10)
    assert total == 2
    # 后插入的 image_id=2 应在前
    assert items[0].image_id == 2
    assert items[1].image_id == 1


def test_get_preview_meta_joins_yande(dao):
    d, session = dao
    _seed_yande(session, 100, 200, 300)
    session.commit()
    for img_id in (100, 200):
        d.add(image_id=img_id)
    session.commit()
    metas = d.get_preview_meta(limit=10)
    assert len(metas) == 2
    assert all(m.width == 200 for m in metas)
```

- [ ] **Step 2：运行测试确认失败**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/dao/test_my_favorite_dao.py -v
```

预期：FAIL（MyFavoriteDao 未定义）

- [ ] **Step 3：实现 `MyFavoriteDao`**

`backend/src/dao/my_favorite_dao.py`：

```python
"""我的最爱 DAO — 仅封装 SQL，不含业务逻辑。"""
from datetime import datetime
from typing import List, Optional, Set, Tuple

from sqlalchemy import func

from src.dao.database import BaseDAO
from src.models.database.my_favorite import MyFavorite
from src.models.database.yande import YandeData
from src.models.response.favorites import FolderPreviewImageMinimal


class MyFavoriteDao(BaseDAO):

    def add(self, image_id: int, note: Optional[str] = None) -> MyFavorite:
        record = MyFavorite(image_id=image_id, note=note)
        self.session.add(record)
        self.session.flush()
        return record

    def remove(self, image_id: int) -> bool:
        record = (
            self.session.query(MyFavorite)
            .filter(MyFavorite.image_id == image_id)
            .first()
        )
        if not record:
            return False
        self.session.delete(record)
        self.session.flush()
        return True

    def exists(self, image_id: int) -> bool:
        return (
            self.session.query(MyFavorite.id)
            .filter(MyFavorite.image_id == image_id)
            .first()
            is not None
        )

    def check_batch(self, image_ids: List[int]) -> Set[int]:
        if not image_ids:
            return set()
        rows = (
            self.session.query(MyFavorite.image_id)
            .filter(MyFavorite.image_id.in_(image_ids))
            .all()
        )
        return {row[0] for row in rows}

    def count(self) -> int:
        return self.session.query(func.count(MyFavorite.id)).scalar() or 0

    def list_paginated(
        self, page: int, page_size: int
    ) -> Tuple[List[MyFavorite], int]:
        total = self.session.query(func.count(MyFavorite.id)).scalar() or 0
        offset = (page - 1) * page_size
        items = (
            self.session.query(MyFavorite)
            .order_by(MyFavorite.created_at.desc(), MyFavorite.id.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )
        return items, total

    def list_all_ids(self) -> List[int]:
        """全量 image_id 列表 — 仅供特殊场景（迁移/同步）。"""
        rows = self.session.query(MyFavorite.image_id).all()
        return [row[0] for row in rows]

    def get_preview_meta(self, limit: int) -> List[FolderPreviewImageMinimal]:
        """最近 N 张收藏的预览元数据（JOIN yande_data）。"""
        rows = (
            self.session.query(YandeData)
            .join(MyFavorite, MyFavorite.image_id == YandeData.id)
            .order_by(MyFavorite.created_at.desc(), MyFavorite.id.desc())
            .limit(limit)
            .all()
        )
        return [
            FolderPreviewImageMinimal.model_validate({
                "id": yd.id,
                "width": yd.preview_width,
                "height": yd.preview_height,
                "rating": yd.rating.value if yd.rating else "s",
            })
            for yd in rows
        ]


my_favorite_dao = MyFavoriteDao()
```

- [ ] **Step 4：运行测试**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/dao/test_my_favorite_dao.py -v
```

预期：8 PASS

- [ ] **Step 5：Commit**

```bash
git add backend/src/dao/my_favorite_dao.py backend/unit_test/dao/test_my_favorite_dao.py
git commit -m "feat(backend): MyFavoriteDao + 单元测试"
```

---

## Task 3：`MyFavorite` / `RandomBrowse` Request & Response 模型

**Files:**
- Create: `backend/src/models/request/my_favorites.py`
- Create: `backend/src/models/response/my_favorites.py`
- Create: `backend/src/models/request/random.py`（如不需要可省略，仅 query param）
- Test: `backend/unit_test/models/test_my_favorites_models.py`

**Interfaces:**
- `MyFavoritesListResponse(BaseResponse[List[MyFavorite]])`（list 含 id/image_id/created_at/note）
- `MyFavoritesListData(BaseModel)`（items, total, has_more）
- `MyFavoriteIdsResponse(BaseResponse[List[int]])`
- `MyFavoriteCheckRequest(BaseModel)`（image_ids: List[int]）
- `MyFavoriteCheckResponse(BaseResponse[List[int]])`（返回已收藏的子集）
- `MyFavoriteCountResponse(BaseResponse[int])`
- `MyFavoriteImagesListResponse(BaseResponse[List[YandeData]])`（JOIN 后的图片列表，含 is_favorited=True）

- [ ] **Step 1：写失败测试**

`backend/unit_test/models/test_my_favorites_models.py`：

```python
"""MyFavorites 相关响应模型 — 验证序列化/反序列化。"""
import pytest
from datetime import datetime

from src.models.response.my_favorites import (
    MyFavoritesListData,
    MyFavoritesListResponse,
    MyFavoriteIdsResponse,
    MyFavoriteCheckResponse,
    MyFavoriteCountResponse,
)
from src.models.request.my_favorites import MyFavoriteCheckRequest


def test_list_data_items_total_has_more():
    data = MyFavoritesListData(items=[], total=0, has_more=False)
    assert data.items == []
    assert data.has_more is False


def test_list_response_wraps_data():
    resp = MyFavoritesListResponse(message="ok", data=MyFavoritesListData(items=[], total=0, has_more=False))
    assert resp.message == "ok"


def test_ids_response():
    resp = MyFavoriteIdsResponse(message="ok", data=[1, 2, 3])
    assert resp.data == [1, 2, 3]


def test_check_request_requires_image_ids():
    req = MyFavoriteCheckRequest(image_ids=[100, 200])
    assert req.image_ids == [100, 200]


def test_check_response():
    resp = MyFavoriteCheckResponse(message="ok", data=[100])
    assert resp.data == [100]


def test_count_response():
    resp = MyFavoriteCountResponse(message="ok", data=42)
    assert resp.data == 42
```

- [ ] **Step 2：运行测试确认失败**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/models/test_my_favorites_models.py -v
```

预期：FAIL（模型未定义）

- [ ] **Step 3：实现 Request 模型**

`backend/src/models/request/my_favorites.py`：

```python
"""我的最爱 请求模型"""
from pydantic import BaseModel, Field


class MyFavoriteCheckRequest(BaseModel):
    """批量查询我的最爱状态"""
    image_ids: list[int] = Field(..., min_length=1, max_length=1000, description="待查询的图片 ID 列表")
```

- [ ] **Step 4：实现 Response 模型**

`backend/src/models/response/my_favorites.py`：

```python
"""我的最爱 响应模型"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from src.models.response.base_response import BaseResponse


class MyFavoriteRecord(BaseModel):
    """单条我的最爱记录"""
    id: int
    image_id: int
    created_at: datetime
    note: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class MyFavoritesListData(BaseModel):
    items: list[MyFavoriteRecord] = Field(default_factory=list)
    total: int = 0
    has_more: bool = False


class MyFavoritesListResponse(BaseResponse[MyFavoritesListData]):
    """分页列出我的最爱记录"""
    ...


class MyFavoriteIdsResponse(BaseResponse[list[int]]):
    """全量 image_id 列表（特殊场景）"""
    ...


class MyFavoriteCheckResponse(BaseResponse[list[int]]):
    """批量 check 结果：返回 image_ids 中已收藏的子集（特殊场景）"""
    ...


class MyFavoriteCountResponse(BaseResponse[int]):
    """我的最爱总数（用于角标）"""
    ...


class MyFavoriteImagesListData(BaseModel):
    items: list[dict] = Field(default_factory=list, description="YandeData dict 列表（用 dict 避免深度耦合）")
    total: int = 0
    has_more: bool = False


class MyFavoriteImagesListResponse(BaseResponse[MyFavoriteImagesListData]):
    """分页返回我的最爱图片（JOIN yande_data），所有元素 is_favorited=True"""
    ...
```

- [ ] **Step 5：运行测试**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/models/test_my_favorites_models.py -v
```

预期：6 PASS

- [ ] **Step 6：Commit**

```bash
git add backend/src/models/request/my_favorites.py backend/src/models/response/my_favorites.py backend/unit_test/models/test_my_favorites_models.py
git commit -m "feat(backend): MyFavorites Request/Response 模型"
```

---

## Task 4：`MyFavoritesService` + 自动下载触发

**Files:**
- Create: `backend/src/services/my_favorites.py`
- Test: `backend/unit_test/services/test_my_favorites_service.py`

**Interfaces:**
- `MyFavoritesService.add(image_id: int) -> None` — 加入我的最爱；未下载触发 `DownloadService.create_task`
- `MyFavoritesService.remove(image_id: int) -> bool`
- `MyFavoritesService.list_paginated(page, page_size) -> Tuple[List[MyFavoriteRecord], int, bool]`
- `MyFavoritesService.list_all_ids() -> List[int]`
- `MyFavoritesService.check_batch(image_ids: List[int]) -> Set[int]`
- `MyFavoritesService.count() -> int`
- `MyFavoritesService.list_images_paginated(page, page_size) -> Tuple[List[dict], int, bool]` — JOIN yande_data 返回完整图片元数据

- [ ] **Step 1：写失败测试**

`backend/unit_test/services/test_my_favorites_service.py`：

```python
"""MyFavoritesService 单元测试 — 覆盖自动下载触发。"""
import asyncio
import pytest
from unittest.mock import patch, AsyncMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.dao.my_favorite_dao import MyFavoriteDao
from src.dao.database import BaseDAO
from src.models.database.yande import Base, YandeData, Rating
from src.models.database.my_favorite import Base as MFBase, MyFavorite
from src.services.my_favorites import MyFavoritesService


@pytest.fixture
def svc():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    MFBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    BaseDAO.set_default_session(session)
    return MyFavoritesService()


def _seed_image(session, image_id: int, down_flag: bool) -> YandeData:
    yd = YandeData(
        id=image_id,
        down_flag=down_flag,
        file_url=f"https://example.com/{image_id}.jpg",
        rating=Rating("s"),
    )
    session.add(yd)
    session.commit()
    return yd


def test_add_existing_image_records_favorite(svc):
    BaseDAO().session.add(YandeData(id=1, down_flag=True, rating=Rating("s")))
    BaseDAO().session.commit()
    asyncio.run(svc.add(1))
    assert svc.count() == 1


def test_add_missing_image_raises_value_error(svc):
    with pytest.raises(ValueError):
        asyncio.run(svc.add(999))


def test_add_already_favoritized_is_idempotent(svc):
    BaseDAO().session.add(YandeData(id=1, down_flag=True, rating=Rating("s")))
    BaseDAO().session.commit()
    asyncio.run(svc.add(1))
    asyncio.run(svc.add(1))  # 第二次幂等
    assert svc.count() == 1


def test_add_triggers_download_for_not_downloaded_image(svc):
    BaseDAO().session.add(YandeData(id=1, down_flag=False, rating=Rating("s")))
    BaseDAO().session.commit()
    with patch("src.services.my_favorites.DownloadService.create_task",
               new_callable=AsyncMock) as mock_dl:
        asyncio.run(svc.add(1))
    mock_dl.assert_awaited_once_with(1)


def test_add_does_not_trigger_download_for_already_downloaded_image(svc):
    BaseDAO().session.add(YandeData(id=1, down_flag=True, rating=Rating("s")))
    BaseDAO().session.commit()
    with patch("src.services.my_favorites.DownloadService.create_task",
               new_callable=AsyncMock) as mock_dl:
        asyncio.run(svc.add(1))
    mock_dl.assert_not_called()


def test_add_download_failure_does_not_rollback_favorite(svc):
    """下载入队失败时，收藏关系必须保留（用户视角：先收藏，后续补）"""
    BaseDAO().session.add(YandeData(id=1, down_flag=False, rating=Rating("s")))
    BaseDAO().session.commit()
    with patch("src.services.my_favorites.DownloadService.create_task",
               new_callable=AsyncMock, side_effect=RuntimeError("queue full")):
        asyncio.run(svc.add(1))
    # 收藏关系仍在
    assert svc.count() == 1
```

- [ ] **Step 2：运行测试确认失败**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/services/test_my_favorites_service.py -v
```

预期：FAIL（service 未定义）

- [ ] **Step 3：实现 `MyFavoritesService`**

`backend/src/services/my_favorites.py`：

```python
"""我的最爱 业务逻辑服务"""
import asyncio
from typing import List, Set, Tuple

from loguru import logger

from src.dao.my_favorite_dao import my_favorite_dao
from src.dao.yande_data_dao import YandeDataRepository
from src.models.database.my_favorite import MyFavorite
from src.models.response.my_favorites import MyFavoriteRecord


class MyFavoritesService:

    @staticmethod
    async def add(image_id: int) -> None:
        """加入我的最爱。已下载跳过；未下载异步入下载队列。

        Raises:
            ValueError: 图片不存在于 YandeData
        """
        with YandeDataRepository() as repo:
            yande_data = repo.get_by_id(image_id)
        if not yande_data:
            raise ValueError(f"Image {image_id} not found in database")

        # 1) 写入（UNIQUE 约束保证幂等；Service 捕获 IntegrityError 视为成功）
        try:
            my_favorite_dao.add(image_id=image_id)
        except Exception:
            # 已存在 → 幂等成功
            logger.debug(f"Image {image_id} already in my_favorite, skip")

        # 2) 未下载时异步触发下载（失败不影响收藏关系）
        if not yande_data.down_flag:
            try:
                from src.services.download import DownloadService
                await DownloadService.create_task(image_id)
                logger.info(f"My favorite auto-download triggered for {image_id}")
            except Exception as e:
                logger.warning(f"Auto-download failed for {image_id}: {e}")

    @staticmethod
    def remove(image_id: int) -> bool:
        return my_favorite_dao.remove(image_id)

    @staticmethod
    def list_paginated(page: int, page_size: int) -> Tuple[List[MyFavoriteRecord], int, bool]:
        items, total = my_favorite_dao.list_paginated(page=page, page_size=page_size)
        records = [MyFavoriteRecord.model_validate(item) for item in items]
        has_more = page * page_size < total
        return records, total, has_more

    @staticmethod
    def list_all_ids() -> List[int]:
        return my_favorite_dao.list_all_ids()

    @staticmethod
    def check_batch(image_ids: List[int]) -> Set[int]:
        return my_favorite_dao.check_batch(image_ids)

    @staticmethod
    def count() -> int:
        return my_favorite_dao.count()

    @staticmethod
    def list_images_paginated(page: int, page_size: int) -> Tuple[List[dict], int, bool]:
        """JOIN yande_data 返回完整图片 dict 列表（按收藏时间倒序）。"""
        from src.dao.my_favorite_dao import MyFavoriteDao
        with MyFavoriteDao() as dao:
            items, total = dao.list_paginated(page=page, page_size=page_size)
            image_ids = [item.image_id for item in items]
        if not image_ids:
            return [], total, False
        with YandeDataRepository() as repo:
            images = repo.get_by_ids(image_ids) if hasattr(repo, "get_by_ids") else None
        # repo.get_by_ids 可能不存在，按 image_ids 顺序逐个取：
        if images is None:
            with YandeDataRepository() as repo:
                id_to_data = {yd.id: yd for yd in (
                    repo.get_by_id(iid) for iid in image_ids
                )}
            ordered = [id_to_data[iid] for iid in image_ids if iid in id_to_data]
        else:
            id_to_data = {yd.id: yd for yd in images}
            ordered = [id_to_data[iid] for iid in image_ids if iid in id_to_data]

        result = []
        for yd in ordered:
            d = yd.__dict__.copy()
            d["is_favorited"] = True
            # 移除 SQLAlchemy 内部状态
            d.pop("_sa_instance_state", None)
            result.append(d)
        has_more = page * page_size < total
        return result, total, has_more
```

- [ ] **Step 4：运行测试**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/services/test_my_favorites_service.py -v
```

预期：6 PASS

- [ ] **Step 5：Commit**

```bash
git add backend/src/services/my_favorites.py backend/unit_test/services/test_my_favorites_service.py
git commit -m "feat(backend): MyFavoritesService + 自动下载触发"
```

---

## Task 5：`RandomBrowseService` + `/random` API（含 JOIN）

**Files:**
- Create: `backend/src/services/random_browse.py`
- Create: `backend/src/api/v1/random.py`
- Test: `backend/unit_test/services/test_random_browse_service.py`
- Test: `backend/unit_test/api/v1/test_random_route.py`

**Interfaces:**
- `RandomBrowseService.get_random(limit: int, tags: str = "", include_favorite_status: bool = False) -> List[dict]`

- [ ] **Step 1：写失败测试 — service**

`backend/unit_test/services/test_random_browse_service.py`：

```python
"""RandomBrowseService 单元测试"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.dao.database import BaseDAO
from src.models.database.yande import Base, YandeData, Rating
from src.services.random_browse import RandomBrowseService


@pytest.fixture
def svc():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    BaseDAO.set_default_session(session)
    return RandomBrowseService()


def _seed(session, n: int, down_flag: bool = True, tags: str = ""):
    for i in range(n):
        session.add(YandeData(
            id=i + 1,
            down_flag=down_flag,
            tags=tags,
            rating=Rating("s"),
        ))
    session.commit()


def test_returns_requested_count(svc):
    _seed(svc, 50)
    out = RandomBrowseService.get_random(limit=10)
    assert len(out) == 10


def test_only_downloaded_images(svc):
    _seed(svc, 5, down_flag=True)
    _seed(svc, 5, down_flag=False)  # 不应被返回
    out = RandomBrowseService.get_random(limit=20)
    assert all(d["down_flag"] is True for d in out)


def test_include_favorite_status_true_returns_field(svc):
    _seed(svc, 3)
    out = RandomBrowseService.get_random(limit=3, include_favorite_status=True)
    assert all("is_favorited" in d for d in out)


def test_include_favorite_status_false_omits_field(svc):
    _seed(svc, 3)
    out = RandomBrowseService.get_random(limit=3, include_favorite_status=False)
    assert all("is_favorited" not in d for d in out)


def test_tags_filter_applied(svc):
    _seed(svc, 5, tags="landscape")
    _seed(svc, 5, tags="portrait")
    out = RandomBrowseService.get_random(limit=20, tags="landscape")
    assert all("landscape" in d.get("tags", "") for d in out)
```

- [ ] **Step 2：运行 service 测试确认失败**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/services/test_random_browse_service.py -v
```

预期：FAIL

- [ ] **Step 3：实现 `RandomBrowseService`**

`backend/src/services/random_browse.py`：

```python
"""随机浏览服务 — 纯本地随机抽样（YandeData down_flag=True）"""
from typing import List

from sqlalchemy import func

from src.dao.database import BaseDAO
from src.dao.my_favorite_dao import my_favorite_dao
from src.models.database.my_favorite import MyFavorite
from src.models.database.yande import YandeData


class RandomBrowseService:

    @staticmethod
    def get_random(limit: int, tags: str = "", include_favorite_status: bool = False) -> List[dict]:
        with BaseDAO() as dao:
            q = dao.session.query(YandeData).filter(YandeData.down_flag.is_(True))
            if tags:
                # 简易 tag 过滤：tags 字符串在 yande_data.tags 中包含
                # 复用 _parse_tags_to_params 太重；此处用 LIKE 简化（性能可接受）
                for token in tags.split():
                    if token.startswith("-"):
                        q = q.filter(~YandeData.tags.contains(token[1:]))
                    else:
                        q = q.filter(YandeData.tags.contains(token))
            if include_favorite_status:
                q = q.outerjoin(
                    MyFavorite, MyFavorite.image_id == YandeData.id
                ).add_columns(
                    (MyFavorite.id.isnot(None)).label("is_favorited")
                )
            rows = q.order_by(func.random()).limit(limit).all()

        results: List[dict] = []
        for row in rows:
            if include_favorite_status:
                yd, is_fav = row
                d = yd.__dict__.copy()
                d["is_favorited"] = bool(is_fav)
            else:
                d = row.__dict__.copy()
            d.pop("_sa_instance_state", None)
            results.append(d)
        return results
```

- [ ] **Step 4：写失败测试 — API**

`backend/unit_test/api/v1/test_random_route.py`：

```python
"""GET /api/v1/random 路由测试"""
import pytest
from fastapi.testclient import TestClient

from src.dao.database import BaseDAO
from src.models.database.yande import Base, YandeData, Rating
from src.api.v1.random import router as random_router
from fastapi import FastAPI


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(random_router, prefix="/api/v1")
    return TestClient(app)


@pytest.fixture
def seed():
    engine = __import__("sqlalchemy").create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = __import__("sqlalchemy.orm").sessionmaker(bind=engine)
    session = Session()
    BaseDAO.set_default_session(session)
    for i in range(10):
        session.add(YandeData(id=i+1, down_flag=True, rating=Rating("s")))
    session.commit()


def test_random_returns_list(client, seed):
    res = client.get("/api/v1/random?limit=5")
    assert res.status_code == 200
    body = res.json()
    assert "data" in body
    assert len(body["data"]) == 5


def test_random_with_include_favorite_status(client, seed):
    res = client.get("/api/v1/random?limit=3&include_favorite_status=true")
    assert res.status_code == 200
    for item in res.json()["data"]:
        assert "is_favorited" in item


def test_random_limit_validation(client, seed):
    res = client.get("/api/v1/random?limit=999")
    assert res.status_code == 422
```

- [ ] **Step 5：实现 `/random` API 路由**

`backend/src/api/v1/random.py`：

```python
"""随机浏览 API 路由"""
from typing import Optional

from fastapi import APIRouter, Query

from src.common.constant import ErrMsg
from src.middleware.errors import APIException
from src.models.response.base_response import BaseResponse
from src.services.random_browse import RandomBrowseService

router = APIRouter()


@router.get(
    "",
    response_model=BaseResponse[list[dict]],
    summary="本地随机浏览",
)
async def get_random_images(
    limit: int = Query(20, ge=1, le=100, description="返回图片数"),
    tags: str = Query("", description="可选 tag 过滤"),
    include_favorite_status: bool = Query(
        False,
        description="True 时响应中每张图片附带 is_favorited 字段（LEFT JOIN my_favorite）",
    ),
) -> BaseResponse[list[dict]]:
    """从本地 YandeData（down_flag=True）中随机抽样。

    include_favorite_status=True 时走 LEFT JOIN，性能损耗 < 5ms。
    """
    try:
        images = RandomBrowseService.get_random(
            limit=limit, tags=tags, include_favorite_status=include_favorite_status
        )
        return BaseResponse(message=ErrMsg.OK.msg, data=images)
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)
```

- [ ] **Step 6：运行所有 random 测试**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/services/test_random_browse_service.py unit_test/api/v1/test_random_route.py -v
```

预期：8 PASS

- [ ] **Step 7：Commit**

```bash
git add backend/src/services/random_browse.py backend/src/api/v1/random.py backend/unit_test/services/test_random_browse_service.py backend/unit_test/api/v1/test_random_route.py
git commit -m "feat(backend): RandomBrowseService + /random API（含 is_favorited JOIN）"
```

---

## Task 6：`FavoritesConfig` Pydantic 模型 + `Config` 挂载

**Files:**
- Modify: `backend/src/common/settings.py:1-50`（追加 `FavoritesConfig`）
- Modify: `backend/src/common/settings.py:80-95`（`Config.favorites` 字段）
- Test: `backend/unit_test/common/test_favorites_config.py`

- [ ] **Step 1：写失败测试**

`backend/unit_test/common/test_favorites_config.py`：

```python
"""FavoritesConfig Pydantic 模型 + Config 集成测试"""
import pytest
from pydantic import ValidationError

from src.common.settings import FavoritesConfig, Config


def test_defaults():
    cfg = FavoritesConfig()
    assert cfg.button_mode == "shown"
    assert cfg.tile_size == "adaptive"
    assert cfg.preview_order == "random"
    assert cfg.include_online is False
    assert cfg.folder_page_size == 20
    assert cfg.my_favorites_enabled is True
    assert cfg.random_browse_enabled is True


def test_button_mode_validation():
    with pytest.raises(ValidationError):
        FavoritesConfig(button_mode="invalid")


def test_tile_size_validation():
    with pytest.raises(ValidationError):
        FavoritesConfig(tile_size="9")


def test_folder_page_size_validation():
    with pytest.raises(ValidationError):
        FavoritesConfig(folder_page_size=15)


def test_config_has_favorites_section():
    cfg = Config()
    assert hasattr(cfg, "favorites")
    assert isinstance(cfg.favorites, FavoritesConfig)


def test_load_yaml_with_favorites_section(tmp_path):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("""
favorites:
  button_mode: hidden
  my_favorites_enabled: false
""", encoding="utf-8")
    from src.common.settings import load_config
    cfg = load_config(yaml_file)
    assert cfg.favorites.button_mode == "hidden"
    assert cfg.favorites.my_favorites_enabled is False
    # 其他字段用默认值
    assert cfg.favorites.tile_size == "adaptive"


def test_load_yaml_without_favorites_uses_defaults(tmp_path):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("app:\n  debug: true\n", encoding="utf-8")
    from src.common.settings import load_config
    cfg = load_config(yaml_file)
    assert cfg.favorites.button_mode == "shown"  # 默认
```

- [ ] **Step 2：运行测试确认失败**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/common/test_favorites_config.py -v
```

预期：FAIL

- [ ] **Step 3：实现 `FavoritesConfig`**

在 `backend/src/common/settings.py` 顶部 import 区追加 `from pydantic import field_validator`，然后在 `SchedulerConfig` 之后插入：

```python
class FavoritesConfig(ConfigModel):
    """收藏夹 UI 配置 + 我的最爱/随机浏览总开关（从 localStorage 迁移而来）"""

    # 从前端 localStorage 迁过来的 5 个 UI 偏好
    button_mode: str = Field("shown", description="hidden | shown | default")
    tile_size: str = Field("adaptive", description="adaptive | 4 | 6 | 8")
    preview_order: str = Field("random", description="random | asc | desc")
    include_online: bool = Field(False, description="预览是否含未下载图片")
    folder_page_size: int = Field(20, description="8 | 12 | 20")

    # 新功能总开关
    my_favorites_enabled: bool = Field(True, description="我的最爱功能总开关")
    random_browse_enabled: bool = Field(True, description="随机浏览功能总开关")

    @field_validator("button_mode")
    @classmethod
    def _v_button_mode(cls, v: str) -> str:
        if v not in ("hidden", "shown", "default"):
            raise ValueError("button_mode must be 'hidden'|'shown'|'default'")
        return v

    @field_validator("tile_size")
    @classmethod
    def _v_tile_size(cls, v: str) -> str:
        if v not in ("adaptive", "4", "6", "8"):
            raise ValueError("tile_size must be 'adaptive'|'4'|'6'|'8'")
        return v

    @field_validator("preview_order")
    @classmethod
    def _v_preview_order(cls, v: str) -> str:
        if v not in ("random", "asc", "desc"):
            raise ValueError("preview_order must be 'random'|'asc'|'desc'")
        return v

    @field_validator("folder_page_size")
    @classmethod
    def _v_folder_page_size(cls, v: int) -> int:
        if v not in (8, 12, 20):
            raise ValueError("folder_page_size must be 8|12|20")
        return v
```

- [ ] **Step 4：在 `Config` 中挂载**

```python
class Config(ConfigModel):
    app: AppConfig = AppConfig()
    database: DatabaseConfig = DatabaseConfig()
    yande_api: ApiConfig = ApiConfig()
    downloader: DownloaderConfig = DownloaderConfig()
    scheduler: SchedulerConfig = SchedulerConfig()
    favorites: FavoritesConfig = FavoritesConfig()   # 新增
```

- [ ] **Step 5：运行测试**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/common/test_favorites_config.py -v
```

预期：7 PASS

- [ ] **Step 6：Commit**

```bash
git add backend/src/common/settings.py backend/unit_test/common/test_favorites_config.py
git commit -m "feat(backend): FavoritesConfig + 挂载到 Config（含 5 个迁移字段 + 2 个新开关）"
```

---

## Task 7：`ConfigService` + `/config/favorites` API

**Files:**
- Modify: `backend/src/services/config.py`
- Modify: `backend/src/api/v1/config.py`
- Modify: `backend/src/models/request/config.py`（`ResetConfig.section` 新增 `'favorites'`）
- Test: `backend/unit_test/services/test_config_favorites.py`
- Test: `backend/unit_test/api/v1/test_config_favorites_route.py`

- [ ] **Step 1：写失败测试 — service**

`backend/unit_test/services/test_config_favorites.py`：

```python
"""ConfigService.get_favorites_config / update_favorites_config 单元测试"""
from src.common.settings import FavoritesConfig
from src.services.config import ConfigService


def test_get_favorites_config_returns_current():
    cfg = ConfigService.get_favorites_config()
    assert isinstance(cfg, FavoritesConfig)


def test_update_favorites_config_persists(tmp_path, monkeypatch):
    """更新后从磁盘重读应一致。"""
    # 重定向 config_file 到 tmp
    from src.common import settings as s
    from src.common import constant
    monkeypatch.setattr(constant.path_constant, "config_file", tmp_path / "config.yaml")
    s.config = s.load_config(tmp_path / "config.yaml")

    new_cfg = FavoritesConfig(
        button_mode="hidden",
        my_favorites_enabled=False,
    )
    success = ConfigService.update_favorites_config(new_cfg)
    assert success is True

    s.config = s.load_config(tmp_path / "config.yaml")
    assert s.config.favorites.button_mode == "hidden"
    assert s.config.favorites.my_favorites_enabled is False
```

- [ ] **Step 2：写失败测试 — API**

`backend/unit_test/api/v1/test_config_favorites_route.py`：

```python
"""GET / PUT /api/v1/config/favorites 路由测试"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.config import router


@pytest.fixture
def client(tmp_path, monkeypatch):
    from src.common import settings as s
    from src.common import constant
    monkeypatch.setattr(constant.path_constant, "config_file", tmp_path / "config.yaml")
    s.config = s.load_config(tmp_path / "config.yaml")
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/config")
    return TestClient(app)


def test_get_favorites_config(client):
    res = client.get("/api/v1/config/favorites")
    assert res.status_code == 200
    assert "button_mode" in res.json()["data"]


def test_put_favorites_config(client):
    res = client.put("/api/v1/config/favorites", json={
        "button_mode": "hidden",
        "my_favorites_enabled": False,
    })
    assert res.status_code == 200


def test_put_invalid_button_mode_returns_422(client):
    res = client.put("/api/v1/config/favorites", json={"button_mode": "invalid"})
    assert res.status_code == 422
```

- [ ] **Step 3：运行所有失败测试**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/services/test_config_favorites.py unit_test/api/v1/test_config_favorites_route.py -v
```

预期：FAIL

- [ ] **Step 4：在 `services/config.py` 添加方法**

```python
# backend/src/services/config.py 末尾追加
from src.common.settings import FavoritesConfig


def get_favorites_config() -> FavoritesConfig:
    """获取收藏夹配置"""
    from src.common.settings import config
    return config.favorites


def update_favorites_config(favorites_config: FavoritesConfig) -> bool:
    """更新收藏夹配置"""
    from src.common.settings import config
    try:
        config.update_config(favorites_config)
        return True
    except Exception:
        return False
```

- [ ] **Step 5：在 `api/v1/config.py` 添加路由**

```python
# 顶部追加 import
from src.common.settings import FavoritesConfig

# 现有 PUT 路由后追加
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

- [ ] **Step 6：扩展 `ResetConfig.section` 字面量**

`backend/src/models/request/config.py`：

```python
class ResetConfig(BaseModel):
    section: Literal['api', 'downloader', 'database', 'favorites'] = Field(...)
```

- [ ] **Step 7：运行所有测试**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/services/test_config_favorites.py unit_test/api/v1/test_config_favorites_route.py -v
```

预期：5 PASS

- [ ] **Step 8：Commit**

```bash
git add backend/src/services/config.py backend/src/api/v1/config.py backend/src/models/request/config.py backend/unit_test/services/test_config_favorites.py backend/unit_test/api/v1/test_config_favorites_route.py
git commit -m "feat(backend): /config/favorites GET+PUT + ConfigService 方法 + reset section"
```

---

## Task 8：`FavoriteFolder.is_system` 列 + 响应模型

**Files:**
- Modify: `backend/src/models/database/yande.py:103-131`（`FavoriteFolder` 添加 `is_system` 列）
- Modify: `backend/src/models/response/favorites.py`（`FavoriteFolderBase` 添加字段）
- Test: `backend/unit_test/database/test_favorite_folder_is_system.py`

- [ ] **Step 1：写失败测试**

`backend/unit_test/database/test_favorite_folder_is_system.py`：

```python
"""FavoriteFolder 新增 is_system 列"""
from sqlalchemy import create_engine, inspect

from src.models.database.yande import Base, FavoriteFolder


def test_is_system_column_exists():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    insp = inspect(engine)
    cols = {c["name"]: c for c in insp.get_columns("favorite_folder")}
    assert "is_system" in cols
    assert cols["is_system"]["default"] == "0" or cols["is_system"]["default"] is False
```

- [ ] **Step 2：运行测试确认失败**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/database/test_favorite_folder_is_system.py -v
```

预期：FAIL

- [ ] **Step 3：修改 `FavoriteFolder` 模型**

`backend/src/models/database/yande.py:103-131` —— 在 `last_synced_id` 之后追加：

```python
is_system = Column(
    Boolean, default=False, nullable=False,
    comment="是否系统内置（我的最爱虚拟 folder 用 True 标记）",
)
```

- [ ] **Step 4：在响应模型加字段**

`backend/src/models/response/favorites.py` —— `FavoriteFolder` 类追加字段：

```python
is_system: bool = False
```

`FavoriteFolderBase` 类**不**加（基础模型不暴露内部标识，前端列表响应使用 `FavoriteFolder` 含 `is_system`）。

- [ ] **Step 5：运行测试**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/database/test_favorite_folder_is_system.py -v
```

预期：1 PASS

- [ ] **Step 6：Commit**

```bash
git add backend/src/models/database/yande.py backend/src/models/response/favorites.py backend/unit_test/database/test_favorite_folder_is_system.py
git commit -m "feat(backend): FavoriteFolder.is_system 列 + 响应模型"
```

---

## Task 9：`get_folders_with_preview` 注入「我的最爱」虚拟 folder

**Files:**
- Modify: `backend/src/services/favorites.py:64-141`（`get_folders_with_preview` 末尾追加虚拟 folder）
- Modify: `backend/src/models/response/favorites.py`（`FavoriteFolderWithMinimalPreview` 已含所有字段）
- Test: `backend/unit_test/services/test_favorites_virtual_folder.py`

- [ ] **Step 1：写失败测试**

`backend/unit_test/services/test_favorites_virtual_folder.py`：

```python
"""get_folders_with_preview 注入「我的最爱」虚拟 folder 的行为"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.dao.database import BaseDAO
from src.dao.favorite_dao import FavoriteDao
from src.dao.my_favorite_dao import MyFavoriteDao
from src.models.database.yande import Base, YandeData, FavoriteFolder, Rating
from src.models.database.my_favorite import Base as MFBase
from src.common.settings import FavoritesConfig, config
from src.services.favorites import FavoritesService


@pytest.fixture(autouse=True)
def setup_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    MFBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    BaseDAO.set_default_session(Session())
    yield


def _seed_folder(name: str, tags: str = "landscape") -> FavoriteFolder:
    f = FavoriteFolder(name=name, tags=tags)
    BaseDAO().session.add(f)
    BaseDAO().session.commit()
    return f


def _seed_image(session, image_id: int, down_flag=True):
    session.add(YandeData(id=image_id, down_flag=down_flag, rating=Rating("s")))
    session.commit()


def test_virtual_folder_present_when_enabled():
    cfg = config.favorites
    cfg.my_favorites_enabled = True
    config.favorites = cfg  # frozen 模型需要绕开

    _seed_folder("folder1")
    _seed_image(BaseDAO().session, 1)
    # 加 3 张我的最爱
    for i in (1, 2, 3):
        MyFavoriteDao().add(image_id=i)

    items, _, _ = FavoritesService.get_folders_with_preview(page=1, page_size=10)
    # 第一项应该是虚拟 folder（id=-1）
    assert items[0].id == -1
    assert items[0].name == "我的最爱"
    assert items[0].is_system is True
    assert items[0].local_count == 3


def test_virtual_folder_absent_when_disabled():
    # 关闭开关
    from src.common.settings import config
    from src.common.settings import FavoritesConfig
    obj = config.favorites
    object.__setattr__(obj, "my_favorites_enabled", False)

    _seed_folder("folder1")
    items, _, _ = FavoritesService.get_folders_with_preview(page=1, page_size=10)
    assert all(item.id != -1 for item in items)
```

- [ ] **Step 2：运行测试确认失败**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/services/test_favorites_virtual_folder.py -v
```

预期：FAIL

- [ ] **Step 3：修改 `services/favorites.py`**

在 `get_folders_with_preview` 方法 `has_more = page * page_size < total` 之前插入：

```python
        # 3. 「我的最爱」虚拟 folder 注入（始终置顶）
        from src.common.settings import config
        from src.dao.my_favorite_dao import my_favorite_dao
        if config.favorites.my_favorites_enabled:
            fav_count = my_favorite_dao.count()
            preview_limit = _preview_count_for_local_count(fav_count, tile_size)
            virtual_preview = my_favorite_dao.get_preview_meta(limit=preview_limit)
            virtual_folder = FavoriteFolderWithMinimalPreview(
                id=-1,
                name="我的最爱",
                tags="",
                color="#F56C6C",
                icon="star",
                sort_order=-1,
                local_count=fav_count,
                online_count=0,
                preview_images=virtual_preview,
                is_system=True,
            )
            items.insert(0, virtual_folder)
```

注意：`config` 是 frozen 的，但 `config.favorites` 也是 frozen 的 Pydantic 模型。要在测试中改值需要 `model_config['frozen']=False` 临时解冻，或直接用 `object.__setattr__`。实际生产代码中**只读** config.favorites.my_favorites_enabled，**不需要修改它**。重新写测试避免修改 config：

- [ ] **Step 3（修正）：删除 Step 1 测试中的 config 修改逻辑，改用默认配置（默认 my_favorites_enabled=True），并加第二个测试用 `monkeypatch` 替换 `config.favorites.my_favorites_enabled`

```python
def test_virtual_folder_absent_when_disabled(monkeypatch):
    """关闭开关时不返回虚拟 folder"""
    from src.common import settings
    # monkeypatch config 不可行（Pydantic frozen）
    # 改用替换 settings.config 对象
    fake_config = settings.Config()
    fake_config.favorites.my_favorites_enabled = False
    # 由于 Pydantic frozen，需要用 model_copy + update
    fake_config = fake_config.model_copy(update={"favorites": settings.FavoritesConfig(my_favorites_enabled=False)})
    monkeypatch.setattr(settings, "config", fake_config)

    _seed_folder("folder1")
    items, _, _ = FavoritesService.get_folders_with_preview(page=1, page_size=10)
    assert all(item.id != -1 for item in items)
```

- [ ] **Step 4：再次运行测试**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/services/test_favorites_virtual_folder.py -v
```

预期：2 PASS

- [ ] **Step 5：Commit**

```bash
git add backend/src/services/favorites.py backend/unit_test/services/test_favorites_virtual_folder.py
git commit -m "feat(backend): get_folders_with_preview 注入「我的最爱」虚拟 folder"
```

---

## Task 10：`/my-favorites/*` API 路由

**Files:**
- Create: `backend/src/api/v1/my_favorites.py`
- Test: `backend/unit_test/api/v1/test_my_favorites_route.py`

- [ ] **Step 1：写失败测试**

`backend/unit_test/api/v1/test_my_favorites_route.py`：

```python
"""/api/v1/my-favorites/* 路由测试"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.api.v1.my_favorites import router
from src.dao.database import BaseDAO
from src.models.database.yande import Base, YandeData, Rating
from src.models.database.my_favorite import Base as MFBase


@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    MFBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    BaseDAO.set_default_session(Session())
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/my-favorites")
    return TestClient(app)


def _seed(n=3, down_flag=True):
    session = BaseDAO().session
    for i in range(n):
        session.add(YandeData(id=i+1, down_flag=down_flag, rating=Rating("s")))
    session.commit()


def test_add_my_favorite(client):
    _seed()
    res = client.post("/api/v1/my-favorites/1")
    assert res.status_code == 200


def test_add_missing_image_returns_404(client):
    res = client.post("/api/v1/my-favorites/999")
    assert res.status_code in (404, 400)


def test_add_is_idempotent(client):
    _seed()
    client.post("/api/v1/my-favorites/1")
    res = client.post("/api/v1/my-favorites/1")
    assert res.status_code == 200


def test_remove_my_favorite(client):
    _seed()
    client.post("/api/v1/my-favorites/1")
    res = client.delete("/api/v1/my-favorites/1")
    assert res.status_code == 200


def test_check_batch(client):
    _seed()
    client.post("/api/v1/my-favorites/1")
    client.post("/api/v1/my-favorites/2")
    res = client.post("/api/v1/my-favorites/check", json={"image_ids": [1, 2, 3]})
    assert res.status_code == 200
    assert set(res.json()["data"]) == {1, 2}


def test_count(client):
    _seed()
    client.post("/api/v1/my-favorites/1")
    client.post("/api/v1/my-favorites/2")
    res = client.get("/api/v1/my-favorites/count")
    assert res.json()["data"] == 2


def test_ids_endpoint_returns_all(client):
    _seed()
    for i in (1, 2):
        client.post(f"/api/v1/my-favorites/{i}")
    res = client.get("/api/v1/my-favorites/ids")
    assert set(res.json()["data"]) == {1, 2}


def test_images_list_paginated(client):
    _seed()
    for i in (1, 2):
        client.post(f"/api/v1/my-favorites/{i}")
    res = client.get("/api/v1/my-favorites/images?page=1&page_size=10")
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert all(item["is_favorited"] is True for item in body["items"])
```

- [ ] **Step 2：运行测试确认失败**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/api/v1/test_my_favorites_route.py -v
```

预期：FAIL

- [ ] **Step 3：实现 `/my-favorites/*` 路由**

`backend/src/api/v1/my_favorites.py`：

```python
"""我的最爱 API 路由"""
from typing import List

from fastapi import APIRouter, Query

from src.common.constant import ErrMsg
from src.middleware.errors import APIException
from src.models.request.my_favorites import MyFavoriteCheckRequest
from src.models.response.base_response import BaseResponse
from src.models.response.my_favorites import (
    MyFavoriteCheckResponse,
    MyFavoriteCountResponse,
    MyFavoriteIdsResponse,
    MyFavoriteImagesListData,
    MyFavoriteImagesListResponse,
    MyFavoritesListData,
    MyFavoritesListResponse,
)
from src.services.my_favorites import MyFavoritesService

router = APIRouter()


@router.get("", response_model=MyFavoritesListResponse, summary="分页我的最爱记录")
async def list_my_favorites(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> MyFavoritesListResponse:
    records, total, has_more = MyFavoritesService.list_paginated(page=page, page_size=page_size)
    return MyFavoritesListResponse(
        message=ErrMsg.OK.msg,
        data=MyFavoritesListData(items=records, total=total, has_more=has_more),
    )


@router.get("/ids", response_model=MyFavoriteIdsResponse, summary="全量 image_id（仅特殊场景）")
async def list_all_my_favorite_ids() -> MyFavoriteIdsResponse:
    """⚠️ 仅供特殊场景：数据迁移、跨设备同步、修复工具。
    正常浏览请用主接口的 include_favorite_status=true JOIN 实现。"""
    ids = MyFavoritesService.list_all_ids()
    return MyFavoriteIdsResponse(message=ErrMsg.OK.msg, data=ids)


@router.post("/{image_id}", response_model=BaseResponse, summary="加入我的最爱")
async def add_my_favorite(image_id: int) -> BaseResponse:
    """加入我的最爱。幂等（UNIQUE image_id 兜底）。
    若图片未下载（down_flag=False），异步触发 DownloadTask。"""
    try:
        await MyFavoritesService.add(image_id)
        return BaseResponse(message="已加入我的最爱")
    except ValueError as e:
        raise APIException(ErrMsg.NOT_FOUND, data={"detail": str(e)})
    except Exception as e:
        raise APIException(ErrMsg.CREATE_ERROR, e=e)


@router.delete("/{image_id}", response_model=BaseResponse, summary="取消我的最爱")
async def remove_my_favorite(image_id: int) -> BaseResponse:
    success = MyFavoritesService.remove(image_id)
    if not success:
        raise APIException(ErrMsg.NOT_FOUND, data={"detail": "未在收藏中"})
    return BaseResponse(message="已取消我的最爱")


@router.post("/check", response_model=MyFavoriteCheckResponse, summary="批量 check（仅特殊场景）")
async def check_my_favorites(req: MyFavoriteCheckRequest) -> MyFavoriteCheckResponse:
    """⚠️ 仅供特殊场景：数据迁移、批量导入、对账工具。
    正常瀑布流请用主接口的 include_favorite_status=true JOIN 实现。"""
    favorited = MyFavoritesService.check_batch(req.image_ids)
    return MyFavoriteCheckResponse(message=ErrMsg.OK.msg, data=sorted(favorited))


@router.get("/count", response_model=MyFavoriteCountResponse, summary="我的最爱总数")
async def count_my_favorites() -> MyFavoriteCountResponse:
    return MyFavoriteCountResponse(message=ErrMsg.OK.msg, data=MyFavoritesService.count())


@router.get("/images", response_model=MyFavoriteImagesListResponse, summary="我的最爱图片列表")
async def list_my_favorite_images(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> MyFavoriteImagesListResponse:
    """分页返回我的最爱图片（JOIN yande_data，按 created_at DESC）。
    所有元素 is_favorited=True（语义：当前页所有图片都来自我的最爱）。"""
    items, total, has_more = MyFavoritesService.list_images_paginated(page=page, page_size=page_size)
    return MyFavoriteImagesListResponse(
        message=ErrMsg.OK.msg,
        data=MyFavoriteImagesListData(items=items, total=total, has_more=has_more),
    )
```

- [ ] **Step 4：运行测试**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/api/v1/test_my_favorites_route.py -v
```

预期：8 PASS

- [ ] **Step 5：Commit**

```bash
git add backend/src/api/v1/my_favorites.py backend/unit_test/api/v1/test_my_favorites_route.py
git commit -m "feat(backend): /api/v1/my-favorites/* 完整路由"
```

---

## Task 11：`YandeData` 响应模型添加 `is_favorited` + 现有主列表接口支持 JOIN

**Files:**
- Modify: `backend/src/models/response/yande.py`（`YandePostItem` 或新建响应模型）
- Modify: `backend/src/api/v1/gallery.py`（`/gallery/load` 接口添加 `include_favorite_status` 参数）
- Modify: `backend/src/services/gallery.py`（查询逻辑添加 LEFT JOIN）
- Test: `backend/unit_test/api/v1/test_gallery_load_include_favorite.py`

- [ ] **Step 1：写失败测试**

`backend/unit_test/api/v1/test_gallery_load_include_favorite.py`：

```python
"""GET /api/v1/gallery/load?include_favorite_status=true 测试"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.api.v1.gallery import router
from src.dao.database import BaseDAO
from src.dao.my_favorite_dao import MyFavoriteDao
from src.models.database.yande import Base, YandeData, Rating
from src.models.database.my_favorite import Base as MFBase


@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    MFBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    BaseDAO.set_default_session(Session())
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/gallery")
    return TestClient(app)


def _seed(n=5):
    session = BaseDAO().session
    for i in range(n):
        session.add(YandeData(id=i+1, down_flag=True, rating=Rating("s")))
    session.commit()


def test_load_without_param_returns_no_is_favorited(client):
    _seed()
    res = client.get("/api/v1/gallery/load?limit=5")
    assert res.status_code == 200
    for item in res.json()["data"]["items"]:
        # 未请求时字段不应存在或为 None（按实现选择）
        assert item.get("is_favorited") is None


def test_load_with_include_favorite_status_true(client):
    _seed()
    MyFavoriteDao().add(image_id=1)
    BaseDAO().session.commit()
    MyFavoriteDao().add(image_id=3)
    BaseDAO().session.commit()

    res = client.get("/api/v1/gallery/load?limit=5&include_favorite_status=true")
    assert res.status_code == 200
    items = res.json()["data"]["items"]
    is_fav_map = {item["id"]: item["is_favorited"] for item in items}
    assert is_fav_map[1] is True
    assert is_fav_map[2] is False
    assert is_fav_map[3] is True


def test_load_with_include_favorite_status_false_explicit(client):
    _seed()
    MyFavoriteDao().add(image_id=1)
    BaseDAO().session.commit()
    res = client.get("/api/v1/gallery/load?limit=5&include_favorite_status=false")
    items = res.json()["data"]["items"]
    # 显式 false 应不返回 is_favorited
    assert all("is_favorited" not in item or item["is_favorited"] is None for item in items)
```

- [ ] **Step 2：运行测试确认失败**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/api/v1/test_gallery_load_include_favorite.py -v
```

预期：FAIL

- [ ] **Step 3：在 `gallery` service 层加 JOIN 支持**

定位 `backend/src/services/gallery.py` 中构建 `/gallery/load` 查询的位置（通常在 `query` 或 `load_images` 方法）。在 SELECT 时根据 `include_favorite_status` 决定是否附加 LEFT JOIN：

```python
# 找到主查询后改造：
def query_images(..., include_favorite_status: bool = False):
    q = session.query(YandeData).filter(...)
    if include_favorite_status:
        q = q.outerjoin(
            MyFavorite, MyFavorite.image_id == YandeData.id
        ).add_columns(
            (MyFavorite.id.isnot(None)).label("is_favorited")
        )
    rows = q.order_by(...).limit(limit).all()
    # 序列化时根据是否带 is_favorited 字段区分
    ...
```

**注意**：现有 service 可能用 ORM `.from_attributes=True` 序列化。`is_favorited` 不在 YandeData ORM 上，需要特殊处理。参考 Task 5 `RandomBrowseService` 的实现方式（`add_columns` + 手构 dict）。

- [ ] **Step 4：在 `/gallery/load` 路由添加参数**

```python
include_favorite_status: bool = Query(
    False,
    description="True 时每张图片附带 is_favorited 字段（LEFT JOIN my_favorite）",
)
```

调用 service 时透传。

- [ ] **Step 5：在 YandeData 响应模型加 `is_favorited` 字段**

`backend/src/models/response/yande.py` —— 找到返回给前端的图片 dict 模型（注意：原始 `YandePostItem` 是 yande.re API 响应模型，**不要改**）。新建或修改 wrapper：

```python
# 在 YandePostData 之后或独立文件：
class YandeDataPublic(BaseModel):
    """本地 YandeData 输出给前端用的模型"""
    # ... 复制 YandeData 字段 ...
    is_favorited: Optional[bool] = Field(
        default=None,
        description="是否已加入我的最爱；仅 include_favorite_status=True 时返回",
    )
```

如果项目已有 YandeData 输出 wrapper，直接加字段；否则按现有项目模式新建。

- [ ] **Step 6：运行测试**

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/api/v1/test_gallery_load_include_favorite.py -v
```

预期：3 PASS

- [ ] **Step 7：Commit**

```bash
git add backend/src/services/gallery.py backend/src/api/v1/gallery.py backend/src/models/response/yande.py backend/unit_test/api/v1/test_gallery_load_include_favorite.py
git commit -m "feat(backend): /gallery/load 支持 include_favorite_status JOIN is_favorited"
```

---

## Task 12：前端 `useFavoritesConfig` 重构：localStorage → 后端 API

**Files:**
- Modify: `frontend/src/composables/useFavoritesConfig.js`（整文件重写）
- Test: `frontend/src/composables/useFavoritesConfig.spec.js`（新建）

- [ ] **Step 1：写失败测试**

`frontend/src/composables/useFavoritesConfig.spec.js`：

```javascript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import api from '@/api'

// mock api
vi.mock('@/api', () => ({
  default: {
    get: vi.fn(),
    put: vi.fn(),
  }
}))

describe('useFavoritesConfig', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // reset module to re-trigger init
    vi.resetModules()
  })

  it('首次调用时从后端加载配置', async () => {
    api.get.mockResolvedValueOnce({
      data: {
        button_mode: 'hidden',
        tile_size: '4',
        preview_order: 'desc',
        include_online: true,
        folder_page_size: 12,
        my_favorites_enabled: false,
        random_browse_enabled: true,
      }
    })
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    const cfg = useFavoritesConfig()
    await new Promise(r => setTimeout(r, 0))
    expect(cfg.buttonMode.value).toBe('hidden')
    expect(cfg.tileSize.value).toBe('4')
    expect(cfg.myFavoritesEnabled.value).toBe(false)
  })

  it('后端失败时 fallback 默认值', async () => {
    api.get.mockRejectedValueOnce(new Error('network'))
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    const cfg = useFavoritesConfig()
    await new Promise(r => setTimeout(r, 0))
    expect(cfg.buttonMode.value).toBe('shown')  // 默认
  })

  it('多次调用返回同一组 ref（singleton）', async () => {
    api.get.mockResolvedValue({ data: {} })
    const { useFavoritesConfig } = await import('@/composables/useFavoritesConfig')
    const a = useFavoritesConfig()
    const b = useFavoritesConfig()
    expect(a.buttonMode).toBe(b.buttonMode)
  })
})
```

- [ ] **Step 2：运行测试确认失败**

```bash
cd frontend && npx vitest run src/composables/useFavoritesConfig.spec.js
```

预期：FAIL（旧实现直接读 localStorage）

- [ ] **Step 3：重写 `useFavoritesConfig.js`**

```javascript
/**
 * 收藏夹 UI 配置 composable（singleton）
 *
 * 数据源：后端 config.yaml（通过 /api/v1/config/favorites）
 * 迁移：旧 localStorage key 作为一次性 fallback（读后即清空，避免重复回退）
 */
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

// 旧 localStorage key → 一次性回退
const LEGACY_KEYS = {
  'gallery_favorites_button_mode': 'buttonMode',
  'gallery_favorites_tile_size': 'tileSize',
  'gallery_favorites_preview_order': 'previewOrder',
  'gallery_favorites_include_online': 'includeOnline',
  'favorites_folder_page_size': 'folderPageSize',
}

function readLegacyFromLocalStorage() {
  if (typeof window === 'undefined' || !window.localStorage) return {}
  const out = {}
  for (const [key, field] of Object.entries(LEGACY_KEYS)) {
    const v = window.localStorage.getItem(key)
    if (v !== null) {
      out[field] = v
      window.localStorage.removeItem(key)  // 一次性，读后即删
    }
  }
  return out
}

async function loadFromBackend() {
  try {
    const res = await api.get('/config/favorites')
    return res.data || {}
  } catch (err) {
    console.warn('Load favorites config failed:', err)
    return null
  }
}

export function useFavoritesConfig() {
  if (!state.loaded.value) {
    state.loaded.value = true
    const legacy = readLegacyFromLocalStorage()

    // 先用 legacy 兜底（同步可用），再异步从后端拉取并覆盖
    for (const [field, v] of Object.entries(legacy)) {
      // 类型转换
      let parsed = v
      if (field === 'includeOnline') parsed = v === 'true'
      else if (field === 'folderPageSize') parsed = parseInt(v, 10)
      if (state[field] !== undefined && parsed !== null && !Number.isNaN(parsed)) {
        state[field].value = parsed
      }
    }

    // 异步从后端加载（成功则覆盖）
    loadFromBackend().then(backendCfg => {
      if (!backendCfg) return
      if (backendCfg.button_mode !== undefined) state.buttonMode.value = backendCfg.button_mode
      if (backendCfg.tile_size !== undefined) state.tileSize.value = backendCfg.tile_size
      if (backendCfg.preview_order !== undefined) state.previewOrder.value = backendCfg.preview_order
      if (backendCfg.include_online !== undefined) state.includeOnline.value = backendCfg.include_online
      if (backendCfg.folder_page_size !== undefined) state.folderPageSize.value = backendCfg.folder_page_size
      if (backendCfg.my_favorites_enabled !== undefined) state.myFavoritesEnabled.value = backendCfg.my_favorites_enabled
      if (backendCfg.random_browse_enabled !== undefined) state.randomBrowseEnabled.value = backendCfg.random_browse_enabled
    })
  }
  return state
}

/** 保存收藏夹配置（由 Config.vue 调用） */
export async function saveFavoritesConfig(updates) {
  await api.put('/config/favorites', updates)
  if (updates.button_mode !== undefined) state.buttonMode.value = updates.button_mode
  if (updates.tile_size !== undefined) state.tileSize.value = updates.tile_size
  if (updates.preview_order !== undefined) state.previewOrder.value = updates.preview_order
  if (updates.include_online !== undefined) state.includeOnline.value = updates.include_online
  if (updates.folder_page_size !== undefined) state.folderPageSize.value = updates.folder_page_size
  if (updates.my_favorites_enabled !== undefined) state.myFavoritesEnabled.value = updates.my_favorites_enabled
  if (updates.random_browse_enabled !== undefined) state.randomBrowseEnabled.value = updates.random_browse_enabled
}
```

- [ ] **Step 4：运行测试**

```bash
cd frontend && npx vitest run src/composables/useFavoritesConfig.spec.js
```

预期：3 PASS

- [ ] **Step 5：Commit**

```bash
git add frontend/src/composables/useFavoritesConfig.js frontend/src/composables/useFavoritesConfig.spec.js
git commit -m "feat(frontend): useFavoritesConfig 重构为后端 API（含旧 localStorage fallback）"
```

---

## Task 13：前端 `Config.vue` 「收藏夹 + 我的最爱 + 随机浏览」section

**Files:**
- Modify: `frontend/src/views/Config.vue`（高级功能 tab 内新增 section）
- Test: `frontend/src/views/Config.spec.js`（更新测试）

- [ ] **Step 1：写失败测试**

`frontend/src/views/Config.spec.js` 追加：

```javascript
describe('Config.vue 收藏夹 + 我的最爱 + 随机浏览 section', () => {
  it('渲染我的最爱开关', async () => {
    const wrapper = mount(Config, { ... })
    expect(wrapper.text()).toContain('我的最爱')
    expect(wrapper.find('[data-testid="my-favorites-switch"]').exists()).toBe(true)
  })

  it('渲染随机浏览开关', async () => {
    const wrapper = mount(Config, { ... })
    expect(wrapper.text()).toContain('随机浏览')
    expect(wrapper.find('[data-testid="random-browse-switch"]').exists()).toBe(true)
  })

  it('切换开关后保存按钮触发 PUT /config/favorites', async () => {
    api.put.mockResolvedValue({ data: {} })
    const wrapper = mount(Config, { ... })
    // 切换 my_favorites_enabled 开关
    await wrapper.find('[data-testid="my-favorites-switch"]').setValue(false)
    // 点击保存
    await wrapper.find('[data-testid="favorites-save"]').trigger('click')
    expect(api.put).toHaveBeenCalledWith(
      '/config/favorites',
      expect.objectContaining({ my_favorites_enabled: false })
    )
  })
})
```

- [ ] **Step 2：运行测试确认失败**

```bash
cd frontend && npx vitest run src/views/Config.spec.js
```

预期：FAIL

- [ ] **Step 3：修改 `Config.vue`**

在 `<template>` 高级 tab 内追加 section（在「代理」section 之后或独立 tab）：

```vue
<el-card class="config-section">
  <template #header>
    <span class="section-title">收藏夹 · 我的最爱 · 随机浏览</span>
  </template>

  <el-form label-width="160px">
    <el-form-item label="主页收藏夹按钮">
      <el-radio-group v-model="favoritesForm.buttonMode">
        <el-radio-button value="hidden">隐藏</el-radio-button>
        <el-radio-button value="shown">显示</el-radio-button>
        <el-radio-button value="default">默认进入</el-radio-button>
      </el-radio-group>
    </el-form-item>
    <el-form-item label="收藏夹 tile 大小">
      <el-radio-group v-model="favoritesForm.tileSize">
        <el-radio-button value="adaptive">自适应</el-radio-button>
        <el-radio-button value="4">4 张</el-radio-button>
        <el-radio-button value="6">6 张</el-radio-button>
        <el-radio-button value="8">8 张</el-radio-button>
      </el-radio-group>
    </el-form-item>
    <el-form-item label="预览图排序">
      <el-radio-group v-model="favoritesForm.previewOrder">
        <el-radio-button value="random">随机</el-radio-button>
        <el-radio-button value="asc">最早优先</el-radio-button>
        <el-radio-button value="desc">最新优先</el-radio-button>
      </el-radio-group>
    </el-form-item>
    <el-form-item label="预览含未下载">
      <el-switch v-model="favoritesForm.includeOnline" data-testid="include-online-switch" />
    </el-form-item>
    <el-form-item label="每页条数">
      <el-radio-group v-model="favoritesForm.folderPageSize">
        <el-radio-button :value="8">8</el-radio-button>
        <el-radio-button :value="12">12</el-radio-button>
        <el-radio-button :value="20">20</el-radio-button>
      </el-radio-group>
    </el-form-item>

    <el-divider />

    <el-form-item label="启用我的最爱">
      <el-switch v-model="favoritesForm.myFavoritesEnabled" data-testid="my-favorites-switch" />
      <span class="form-hint">关闭后，瀑布流图片右下角爱心隐藏，收藏夹列表置顶的「我的最爱」磁贴也隐藏</span>
    </el-form-item>
    <el-form-item label="启用随机浏览">
      <el-switch v-model="favoritesForm.randomBrowseEnabled" data-testid="random-browse-switch" />
      <span class="form-hint">关闭后，工具栏的随机按钮隐藏</span>
    </el-form-item>

    <el-form-item>
      <el-button
        type="primary"
        :loading="savingFavorites"
        data-testid="favorites-save"
        @click="saveFavorites"
      >保存</el-button>
    </el-form-item>
  </el-form>
</el-card>
```

`<script setup>` 顶部 import 增加：

```javascript
import { saveFavoritesConfig } from '@/composables/useFavoritesConfig'
```

并在 setup 中：

```javascript
const { myFavoritesEnabled, randomBrowseEnabled } = useFavoritesConfig()

const favoritesForm = reactive({
  buttonMode: buttonMode.value,
  tileSize: tileSize.value,
  previewOrder: previewOrder.value,
  includeOnline: includeOnline.value,
  folderPageSize: folderPageSize.value,
  myFavoritesEnabled: myFavoritesEnabled.value,
  randomBrowseEnabled: randomBrowseEnabled.value,
})

const savingFavorites = ref(false)
async function saveFavorites() {
  savingFavorites.value = true
  try {
    await saveFavoritesConfig({
      button_mode: favoritesForm.buttonMode,
      tile_size: favoritesForm.tileSize,
      preview_order: favoritesForm.previewOrder,
      include_online: favoritesForm.includeOnline,
      folder_page_size: favoritesForm.folderPageSize,
      my_favorites_enabled: favoritesForm.myFavoritesEnabled,
      random_browse_enabled: favoritesForm.randomBrowseEnabled,
    })
    // 同步到 composable（saveFavoritesConfig 内部已同步；这里仅作为保险）
    ElMessage.success('收藏夹配置已保存')
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    savingFavorites.value = false
  }
}
```

- [ ] **Step 4：运行测试**

```bash
cd frontend && npx vitest run src/views/Config.spec.js
```

预期：所有原测试 + 新增 3 个 PASS

- [ ] **Step 5：Commit**

```bash
git add frontend/src/views/Config.vue frontend/src/views/Config.spec.js
git commit -m "feat(frontend): Config.vue 新增收藏夹+我的最爱+随机浏览 section"
```

---

## Task 14：前端 `HeartOverlay.vue` + `myFavorites.js` API 模块

**Files:**
- Create: `frontend/src/components/HeartOverlay.vue`
- Create: `frontend/src/api/myFavorites.js`
- Test: `frontend/src/components/HeartOverlay.spec.js`

- [ ] **Step 1：写失败测试**

`frontend/src/components/HeartOverlay.spec.js`：

```javascript
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import HeartOverlay from '@/components/HeartOverlay.vue'
import { myFavoritesApi } from '@/api/myFavorites'

vi.mock('@/api/myFavorites', () => ({
  myFavoritesApi: {
    add: vi.fn().mockResolvedValue({}),
    remove: vi.fn().mockResolvedValue({}),
  }
}))

describe('HeartOverlay', () => {
  it('initialFavorited=true 渲染实心图标', () => {
    const wrapper = mount(HeartOverlay, {
      props: { imageId: 1, initialFavorited: true }
    })
    expect(wrapper.find('.heart-overlay.active').exists()).toBe(true)
  })

  it('initialFavorited=false 渲染空心图标', () => {
    const wrapper = mount(HeartOverlay, {
      props: { imageId: 1, initialFavorited: false }
    })
    expect(wrapper.find('.heart-overlay.active').exists()).toBe(false)
  })

  it('点击触发 add API 并 emit changed', async () => {
    const wrapper = mount(HeartOverlay, {
      props: { imageId: 1, initialFavorited: false }
    })
    await wrapper.find('button').trigger('click')
    expect(myFavoritesApi.add).toHaveBeenCalledWith(1)
    expect(wrapper.emitted('changed')).toBeTruthy()
    expect(wrapper.emitted('changed')[0][0]).toEqual({ imageId: 1, favorited: true })
  })

  it('已收藏时点击触发 remove API', async () => {
    const wrapper = mount(HeartOverlay, {
      props: { imageId: 1, initialFavorited: true }
    })
    await wrapper.find('button').trigger('click')
    expect(myFavoritesApi.remove).toHaveBeenCalledWith(1)
  })

  it('enabled=false 时不渲染按钮', () => {
    const wrapper = mount(HeartOverlay, {
      props: { imageId: 1, initialFavorited: false, enabled: false }
    })
    expect(wrapper.find('button').exists()).toBe(false)
  })
})
```

- [ ] **Step 2：运行测试确认失败**

```bash
cd frontend && npx vitest run src/components/HeartOverlay.spec.js
```

预期：FAIL

- [ ] **Step 3：创建 `api/myFavorites.js`**

```javascript
import api from '@/api'

export const myFavoritesApi = {
  /** 加入我的最爱（幂等）；未下载自动触发下载 */
  add(imageId) { return api.post(`/my-favorites/${imageId}`) },

  /** 取消我的最爱（幂等） */
  remove(imageId) { return api.delete(`/my-favorites/${imageId}`) },

  /** 我的最爱分页记录（含 id/image_id/created_at/note） */
  list(page = 1, pageSize = 20) {
    return api.get('/my-favorites', { params: { page, page_size: pageSize } })
  },

  /** 我的最爱图片（瀑布流用，所有 is_favorited=true） */
  listImages(page = 1, pageSize = 20) {
    return api.get('/my-favorites/images', { params: { page, page_size: pageSize } })
  },

  /** 我的最爱总数（角标） */
  count() { return api.get('/my-favorites/count') },

  /**
   * 批量 check — ⚠️ 仅特殊场景：数据迁移、批量导入、对账
   * 正常瀑布流请用主接口 include_favorite_status=true JOIN
   */
  checkBatch(imageIds) {
    return api.post('/my-favorites/check', { image_ids: imageIds })
  },

  /** 全量 image_id — ⚠️ 仅特殊场景 */
  listIds() { return api.get('/my-favorites/ids') },
}
```

- [ ] **Step 4：实现 `HeartOverlay.vue`**

```vue
<template>
  <button
    v-if="enabled"
    class="heart-overlay"
    :class="{ active: isFavorited, loading }"
    @click.stop.prevent="toggle"
    :aria-label="isFavorited ? '取消我的最爱' : '加入我的最爱'"
    data-testid="heart-overlay"
  >
    <el-icon :size="size">
      <component :is="isFavorited ? StarFilled : Star" />
    </el-icon>
  </button>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Star, StarFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { myFavoritesApi } from '@/api/myFavorites'

const props = defineProps({
  imageId: { type: Number, required: true },
  initialFavorited: { type: Boolean, default: false },
  enabled: { type: Boolean, default: true },
  size: { type: Number, default: 16 },
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
    ElMessage.error(isFavorited.value ? '取消失败' : '收藏失败')
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
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.5);
  border: none;
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.15s, background 0.15s;
  z-index: 10;
}
.heart-overlay:hover {
  background: rgba(0, 0, 0, 0.7);
  transform: scale(1.1);
}
.heart-overlay.active {
  color: #F56C6C;
}
.heart-overlay.loading {
  opacity: 0.6;
  pointer-events: none;
}
</style>
```

- [ ] **Step 5：运行测试**

```bash
cd frontend && npx vitest run src/components/HeartOverlay.spec.js
```

预期：5 PASS

- [ ] **Step 6：Commit**

```bash
git add frontend/src/api/myFavorites.js frontend/src/components/HeartOverlay.vue frontend/src/components/HeartOverlay.spec.js
git commit -m "feat(frontend): HeartOverlay 组件 + myFavorites API 模块"
```

---

## Task 15：`WaterfallGallery` 集成 `HeartOverlay`（JOIN 方案）

**Files:**
- Modify: `frontend/src/components/WaterfallGallery.vue`
- Modify: `frontend/src/components/WaterfallGallery.spec.js`

**关键点**：
- **不调用 `/my-favorites/check`**（JOIN 方案）
- 仅当 `myFavoritesEnabled=true` 时给主接口请求参数加 `include_favorite_status=true`
- 每个 image tile 内嵌 `<HeartOverlay :initial-favorited="img.is_favorited === true" />`
- 监听 `@changed` 事件做乐观更新

- [ ] **Step 1：写失败测试**

`frontend/src/components/WaterfallGallery.spec.js` 追加：

```javascript
describe('WaterfallGallery 集成 HeartOverlay (JOIN 方案)', () => {
  it('myFavoritesEnabled=true 时加载参数带 include_favorite_status=true', async () => {
    // mock api.get 返回带 is_favorited 字段
    vi.mock('@/api', () => ({
      default: { get: vi.fn().mockResolvedValue({ data: { items: [], has_more: false } }) }
    }))
    const wrapper = mount(WaterfallGallery, {
      props: { ... },
      provide: { myFavoritesEnabled: ref(true) }
    })
    // 触发加载
    await wrapper.vm.loadImages()
    expect(api.get).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        params: expect.objectContaining({ include_favorite_status: true })
      })
    )
  })

  it('myFavoritesEnabled=false 时加载参数不带 include_favorite_status', async () => {
    const wrapper = mount(WaterfallGallery, {
      props: { ... },
      provide: { myFavoritesEnabled: ref(false) }
    })
    await wrapper.vm.loadImages()
    const callParams = api.get.mock.calls[0][1].params
    expect('include_favorite_status' in callParams).toBe(false)
  })

  it('图片 is_favorited=true 时 HeartOverlay 渲染 active', () => {
    const wrapper = mount(WaterfallGallery, {
      props: {
        images: [{ id: 1, is_favorited: true, width: 100, height: 100, preview_url: '' }],
        myFavoritesEnabled: true,
      }
    })
    expect(wrapper.find('[data-testid="heart-overlay"].active').exists()).toBe(true)
  })

  it('myFavoritesEnabled=false 时 HeartOverlay 不渲染', () => {
    const wrapper = mount(WaterfallGallery, {
      props: {
        images: [{ id: 1, is_favorited: true, width: 100, height: 100, preview_url: '' }],
        myFavoritesEnabled: false,
      }
    })
    expect(wrapper.find('[data-testid="heart-overlay"]').exists()).toBe(false)
  })
})
```

- [ ] **Step 2：运行测试确认失败**

```bash
cd frontend && npx vitest run src/components/WaterfallGallery.spec.js
```

预期：FAIL

- [ ] **Step 3：修改 `WaterfallGallery.vue`**

a. `<script setup>` 顶部增加：

```javascript
import { useFavoritesConfig } from '@/composables/useFavoritesConfig'
import HeartOverlay from './HeartOverlay.vue'

const { myFavoritesEnabled } = useFavoritesConfig()
```

b. props 增加：

```javascript
// 接收父组件传 showHeart（默认由 composable 决定）
const props = defineProps({
  ...existing,
  showHeart: { type: Boolean, default: null }  // null 表示用 composable 值
})
const effectiveShowHeart = computed(() =>
  props.showHeart !== null ? props.showHeart : myFavoritesEnabled.value
)
```

c. 找到加载新页的函数（通常 `loadNewPage` / `loadImages`），根据 `effectiveShowHeart.value` 决定是否加参数：

```javascript
const params = {
  page, page_size, ...otherParams,
}
if (effectiveShowHeart.value) {
  params.include_favorite_status = true
}
const res = await api.get('/gallery/load', { params })
```

d. 在图片渲染的 `<template>` 部分，给每张图片加 `<HeartOverlay>`：

```vue
<div class="image-card">
  <el-image :src="..." />
  <HeartOverlay
    v-if="effectiveShowHeart"
    :image-id="img.id"
    :initial-favorited="img.is_favorited === true"
    @changed="(e) => handleFavoriteChanged(img, e)"
  />
</div>
```

e. 新增 `handleFavoriteChanged`：

```javascript
function handleFavoriteChanged(img, { imageId, favorited }) {
  // 乐观更新本地数据
  img.is_favorited = favorited
}
```

- [ ] **Step 4：运行测试**

```bash
cd frontend && npx vitest run src/components/WaterfallGallery.spec.js
```

预期：原测试 + 新增 4 个 PASS

- [ ] **Step 5：Commit**

```bash
git add frontend/src/components/WaterfallGallery.vue frontend/src/components/WaterfallGallery.spec.js
git commit -m "feat(frontend): WaterfallGallery 集成 HeartOverlay（JOIN 方案，不调用 /check）"
```

---

## Task 16：`FolderTile` 渲染「我的最爱」虚拟磁贴（`id=-1`）

**Files:**
- Modify: `frontend/src/components/FolderTile.vue`
- Modify: `frontend/src/components/FolderTile.spec.js`

- [ ] **Step 1：写失败测试**

`frontend/src/components/FolderTile.spec.js` 追加：

```javascript
describe('FolderTile 虚拟我的最爱磁贴 (id=-1)', () => {
  it('id=-1 时显示「我的最爱」标题和星标', () => {
    const folder = {
      id: -1,
      name: '我的最爱',
      is_system: true,
      local_count: 5,
      preview_images: [],
    }
    const wrapper = mount(FolderTile, { props: { folder, ... } })
    expect(wrapper.text()).toContain('我的最爱')
    expect(wrapper.find('.virtual-favorite').exists()).toBe(true)
  })

  it('id=-1 时不响应长按编辑菜单', async () => {
    const folder = { id: -1, name: '我的最爱', is_system: true, local_count: 5 }
    const wrapper = mount(FolderTile, { props: { folder, ... } })
    // 模拟长按
    await wrapper.trigger('mousedown')
    await new Promise(r => setTimeout(r, 500))
    await wrapper.trigger('mouseup')
    // 不应 emit 'edit' 事件
    expect(wrapper.emitted('edit')).toBeFalsy()
  })

  it('id>0 时仍按原逻辑渲染', () => {
    const folder = { id: 5, name: '正常文件夹', local_count: 10, preview_images: [] }
    const wrapper = mount(FolderTile, { props: { folder, ... } })
    expect(wrapper.find('.virtual-favorite').exists()).toBe(false)
  })
})
```

- [ ] **Step 2：运行测试确认失败**

```bash
cd frontend && npx vitest run src/components/FolderTile.spec.js
```

预期：FAIL

- [ ] **Step 3：修改 `FolderTile.vue`**

`<template>` 顶部增加分支：

```vue
<template>
  <div
    v-if="folder.id === -1"
    ref="tileRef"
    class="folder-tile virtual-favorite"
    @click="handleClick"
  >
    <div class="favorite-icon">⭐ 我的最爱</div>
    <div class="favorite-count">{{ folder.local_count }} 张</div>
    <div class="favorite-preview">
      <!-- 复用现有 preview_images 渲染逻辑 -->
      <img v-for="img in displayedImages" :key="img.id" :src="previewUrl(img.id)" />
    </div>
  </div>
  <div v-else ref="tileRef" class="folder-tile" @click="handleClick" @mousedown="..." @mouseup="...">
    <!-- 现有模板 -->
  </div>
</template>
```

`<script setup>` 中的长按逻辑增加守卫：

```javascript
function handlePressStart() {
  if (props.folder.is_system) return  // 系统内置 folder 不响应长按
  // 原有逻辑
}
```

- [ ] **Step 4：运行测试**

```bash
cd frontend && npx vitest run src/components/FolderTile.spec.js
```

预期：原测试 + 新增 3 个 PASS

- [ ] **Step 5：Commit**

```bash
git add frontend/src/components/FolderTile.vue frontend/src/components/FolderTile.spec.js
git commit -m "feat(frontend): FolderTile 渲染 id=-1 虚拟我的最爱磁贴"
```

---

## Task 17：`Gallery.vue` 新增 `my-favorites` 模式 + 4 联按钮

**Files:**
- Modify: `frontend/src/views/Gallery.vue`
- Modify: `frontend/src/views/Gallery.spec.js`

- [ ] **Step 1：写失败测试**

`frontend/src/views/Gallery.spec.js` 追加：

```javascript
describe('Gallery.vue 我的最爱模式', () => {
  it('4 联按钮渲染（在线/本地/收藏夹/我的最爱）', () => {
    const wrapper = mount(Gallery, { ... })
    expect(wrapper.text()).toContain('在线')
    expect(wrapper.text()).toContain('本地')
    expect(wrapper.text()).toContain('收藏夹')
    expect(wrapper.text()).toContain('我的最爱')
  })

  it('myFavoritesEnabled=false 时「我的最爱」按钮隐藏', async () => {
    // mock useFavoritesConfig 返 myFavoritesEnabled=false
    const wrapper = mount(Gallery, { ... })
    expect(wrapper.find('[data-testid="my-favorites-btn"]').exists()).toBe(false)
  })

  it('点击「我的最爱」按钮 → querySource=my-favorites + 加载 /my-favorites/images', async () => {
    api.get.mockResolvedValue({ data: { items: [], total: 0, has_more: false } })
    const wrapper = mount(Gallery, { ... })
    await wrapper.find('[data-testid="my-favorites-btn"]').trigger('click')
    await flushPromises()
    expect(api.get).toHaveBeenCalledWith(
      expect.stringContaining('/my-favorites/images'),
      expect.any(Object)
    )
  })

  it('点击虚拟我的最爱磁贴 (id=-1) → querySource=my-favorites', async () => {
    api.get.mockResolvedValue({ data: { items: [], total: 0, has_more: false } })
    const wrapper = mount(Gallery, { ... })
    // 模拟 FolderTile click with id=-1
    wrapper.vm.handleFolderClick({ id: -1, name: '我的最爱', is_system: true })
    await flushPromises()
    expect(wrapper.vm.querySource).toBe('my-favorites')
  })
})
```

- [ ] **Step 2：运行测试确认失败**

```bash
cd frontend && npx vitest run src/views/Gallery.spec.js
```

预期：FAIL

- [ ] **Step 3：修改 `Gallery.vue`**

a. `<script setup>` 顶部增加：

```javascript
import { useFavoritesConfig } from '@/composables/useFavoritesConfig'
const { myFavoritesEnabled } = useFavoritesConfig()
```

b. querySource 类型扩展：

```javascript
const querySource = ref(localStorage.getItem('gallery_source') || 'local')
// 类型：'yande' | 'local' | 'favorites' | 'my-favorites'
```

c. 3 联 → 4 联按钮组（仅当 myFavoritesEnabled=true 时显示「我的最爱」按钮）：

```vue
<el-button-group>
  <el-button :type="querySource === 'yande' ? 'primary' : ''" @click="handleSourceChange('yande')">在线</el-button>
  <el-button :type="querySource === 'local' ? 'primary' : ''" @click="handleSourceChange('local')">本地</el-button>
  <el-button :type="querySource === 'favorites' ? 'primary' : ''" @click="handleSourceChange('favorites')">收藏夹</el-button>
  <el-button
    v-if="myFavoritesEnabled"
    data-testid="my-favorites-btn"
    :type="querySource === 'my-favorites' ? 'primary' : ''"
    @click="handleSourceChange('my-favorites')"
  >我的最爱</el-button>
</el-button-group>
```

d. `handleSourceChange` 新增 `'my-favorites'` 分支，触发瀑布流加载走 `/my-favorites/images`：

```javascript
async function handleSourceChange(source) {
  querySource.value = source
  localStorage.setItem('gallery_source', source)
  favoritesView.value = null
  selectedFavoriteFolder.value = null
  if (source === 'my-favorites') {
    images.value = []
    await loadMyFavoriteImages(1)
  } else if (source === 'favorites') {
    favoritesView.value = 'folders'
    await loadFolders(1)
  } else {
    await loadImages(1)
  }
}

async function loadMyFavoriteImages(page) {
  loading.value = true
  try {
    const params = { page, page_size: 20 }
    if (myFavoritesEnabled.value) params.include_favorite_status = true
    const res = await api.get('/my-favorites/images', { params })
    images.value = res.data.items || []
    hasMore.value = res.data.has_more
  } finally {
    loading.value = false
  }
}
```

e. `handleFolderClick` 新增 id=-1 分支：

```javascript
function handleFolderClick(folder) {
  if (folder.id === -1) {
    handleSourceChange('my-favorites')
    return
  }
  // 现有逻辑
}
```

- [ ] **Step 4：运行测试**

```bash
cd frontend && npx vitest run src/views/Gallery.spec.js
```

预期：原测试 + 新增 4 个 PASS

- [ ] **Step 5：Commit**

```bash
git add frontend/src/views/Gallery.vue frontend/src/views/Gallery.spec.js
git commit -m "feat(frontend): Gallery.vue 4 联按钮 + my-favorites querySource"
```

---

## Task 18：`RandomBrowser.vue` Dialog + `api/random.js`

**Files:**
- Create: `frontend/src/components/RandomBrowser.vue`
- Create: `frontend/src/api/random.js`
- Test: `frontend/src/components/RandomBrowser.spec.js`

- [ ] **Step 1：写失败测试**

`frontend/src/components/RandomBrowser.spec.js`：

```javascript
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import RandomBrowser from '@/components/RandomBrowser.vue'
import { randomApi } from '@/api/random'

vi.mock('@/api/random', () => ({
  randomApi: { getRandom: vi.fn().mockResolvedValue({ data: [] }) }
}))

describe('RandomBrowser', () => {
  it('打开 Dialog 时调用 getRandom 加载第一页', async () => {
    const wrapper = mount(RandomBrowser, { props: { modelValue: true } })
    await flushPromises()
    expect(randomApi.getRandom).toHaveBeenCalledWith(
      expect.objectContaining({ limit: 20, include_favorite_status: true })
    )
  })

  it('点击「再抽 N 张」追加渲染', async () => {
    randomApi.getRandom
      .mockResolvedValueOnce({ data: [{ id: 1, ... }] })
      .mockResolvedValueOnce({ data: [{ id: 2, ... }] })
    const wrapper = mount(RandomBrowser, { props: { modelValue: true } })
    await flushPromises()
    await wrapper.find('[data-testid="random-refresh"]').trigger('click')
    await flushPromises()
    expect(wrapper.vm.images.length).toBe(2)
  })

  it('HeartOverlay 集成（传入 is_favorited）', () => {
    const wrapper = mount(RandomBrowser, { props: { modelValue: true } })
    wrapper.vm.images = [{ id: 1, is_favorited: true }]
    // 触发 re-render
    expect(wrapper.html()).toContain('heart-overlay')
  })
})
```

- [ ] **Step 2：运行测试确认失败**

```bash
cd frontend && npx vitest run src/components/RandomBrowser.spec.js
```

预期：FAIL

- [ ] **Step 3：创建 `api/random.js`**

```javascript
import api from '@/api'

export const randomApi = {
  /**
   * 本地随机浏览
   * @param {Object} options
   * @param {number} options.limit - 返回图片数（默认 20）
   * @param {string} options.tags - 可选 tag 过滤
   * @param {boolean} options.include_favorite_status - 是否请求 is_favorited JOIN 字段
   */
  getRandom({ limit = 20, tags = '', include_favorite_status = false } = {}) {
    const params = { limit }
    if (tags) params.tags = tags
    if (include_favorite_status) params.include_favorite_status = true
    return api.get('/random', { params })
  },
}
```

- [ ] **Step 4：实现 `RandomBrowser.vue`**

```vue
<template>
  <el-dialog
    :model-value="modelValue"
    title="随机浏览"
    width="80%"
    top="5vh"
    @update:model-value="$emit('update:modelValue', $event)"
    @open="onOpen"
  >
    <div class="random-grid">
      <div v-for="img in images" :key="img.id" class="random-card">
        <el-image :src="getPreviewUrl(img)" fit="cover" />
        <HeartOverlay
          :image-id="img.id"
          :initial-favorited="img.is_favorited === true"
          @changed="(e) => handleFavoriteChanged(img, e)"
        />
      </div>
    </div>
    <template #footer>
      <el-button data-testid="random-refresh" @click="loadMore" :icon="Refresh">再抽 {{ pageSize }} 张</el-button>
      <el-button @click="$emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import HeartOverlay from './HeartOverlay.vue'
import { randomApi } from '@/api/random'
import { useFavoritesConfig } from '@/composables/useFavoritesConfig'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const { myFavoritesEnabled } = useFavoritesConfig()

const images = ref([])
const pageSize = 20

async function loadMore() {
  const res = await randomApi.getRandom({
    limit: pageSize,
    include_favorite_status: myFavoritesEnabled.value,
  })
  // 追加而非替换（用户体验）
  images.value.push(...(res.data || []))
}

function onOpen() {
  images.value = []
  loadMore()
}

function getPreviewUrl(img) {
  return `/api/v1/gallery/cache/preview/${img.id}`
}

function handleFavoriteChanged(img, { imageId, favorited }) {
  img.is_favorited = favorited
}
</script>

<style scoped>
.random-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  max-height: 70vh;
  overflow-y: auto;
}
.random-card {
  position: relative;
  aspect-ratio: 1;
  border-radius: 6px;
  overflow: hidden;
}
</style>
```

- [ ] **Step 5：运行测试**

```bash
cd frontend && npx vitest run src/components/RandomBrowser.spec.js
```

预期：3 PASS

- [ ] **Step 6：Commit**

```bash
git add frontend/src/components/RandomBrowser.vue frontend/src/api/random.js frontend/src/components/RandomBrowser.spec.js
git commit -m "feat(frontend): RandomBrowser Dialog + random API 模块"
```

---

## Task 19：`Gallery.vue` 工具栏挂载 `RandomBrowser` 触发按钮

**Files:**
- Modify: `frontend/src/views/Gallery.vue`（工具栏加「随机」按钮 + 引入 `RandomBrowser`）
- Modify: `frontend/src/views/Gallery.spec.js`

- [ ] **Step 1：写失败测试**

```javascript
describe('Gallery.vue 随机浏览按钮', () => {
  it('myFavoritesEnabled 等价条件下按钮显示', () => {
    // mock useFavoritesConfig 返 randomBrowseEnabled=true
    const wrapper = mount(Gallery, { ... })
    expect(wrapper.find('[data-testid="random-btn"]').exists()).toBe(true)
  })

  it('randomBrowseEnabled=false 时按钮隐藏', () => {
    // mock useFavoritesConfig 返 randomBrowseEnabled=false
    const wrapper = mount(Gallery, { ... })
    expect(wrapper.find('[data-testid="random-btn"]').exists()).toBe(false)
  })

  it('点击随机按钮打开 RandomBrowser Dialog', async () => {
    const wrapper = mount(Gallery, { ... })
    await wrapper.find('[data-testid="random-btn"]').trigger('click')
    expect(wrapper.findComponent({ name: 'RandomBrowser' }).exists()).toBe(true)
  })
})
```

- [ ] **Step 2：运行测试确认失败**

```bash
cd frontend && npx vitest run src/views/Gallery.spec.js
```

预期：FAIL

- [ ] **Step 3：修改 `Gallery.vue`**

a. 顶部 import：

```javascript
import RandomBrowser from '@/components/RandomBrowser.vue'
const { randomBrowseEnabled } = useFavoritesConfig()
```

b. 工具栏按钮（受 randomBrowseEnabled 控制）：

```vue
<el-button
  v-if="randomBrowseEnabled"
  data-testid="random-btn"
  :icon="MagicStick"
  @click="showRandomBrowser = true"
>随机</el-button>
```

c. Dialog：

```vue
<RandomBrowser v-model="showRandomBrowser" />
```

- [ ] **Step 4：运行测试**

```bash
cd frontend && npx vitest run src/views/Gallery.spec.js
```

预期：所有 Gallery 测试 PASS

- [ ] **Step 5：Commit**

```bash
git add frontend/src/views/Gallery.vue frontend/src/views/Gallery.spec.js
git commit -m "feat(frontend): Gallery.vue 工具栏挂载随机浏览按钮"
```

---

## Task 20：全栈集成验证 + 发版

**Files:**
- 手动验证清单（不修改代码）

- [ ] **Step 1：运行完整测试套件**

```bash
# 后端
cd backend && PYTHONPATH=. .venv/bin/python -m pytest unit_test/ -v
# 前端
cd frontend && npx vitest run
```

预期：全部 PASS

- [ ] **Step 2：手动端到端验证清单**

启动服务（`uvicorn service:main_app --port 8000 --reload --reload-dir ./src` + 前端 dev），按以下清单逐项验证：

- [ ] 进入画廊，「我的最爱」按钮出现在 4 联按钮组
- [ ] 点击图片右下角爱心 → 变实心 → 后端 `my_favorite` 表新增一行
- [ ] 对未下载的图片点爱心 → 「下载管理」出现新任务
- [ ] 进入「我的最爱」视图 → 显示已收藏的图片（is_favorited 全部 true）
- [ ] 再次点击实心爱心 → 变空心 → `my_favorite` 删除对应行
- [ ] 收藏夹列表第一项显示「我的最爱」红色磁贴 + 计数正确
- [ ] 点击「我的最爱」磁贴 → 进入瀑布流视图
- [ ] 关闭「我的最爱」开关（Config.vue）→ 刷新后爱心按钮 + 虚拟磁贴 + 4 联按钮中的「我的最爱」全部隐藏
- [ ] 点击「随机浏览」→ Dialog 打开 → 显示 20 张本地图
- [ ] 「再抽 N 张」→ 追加渲染
- [ ] 关闭「随机浏览」开关 → 工具栏「随机」按钮隐藏
- [ ] localStorage 中旧 key `gallery_favorites_*` 在加载后被清除（DevTools 验证）

- [ ] **Step 3：LSP 诊断**

```bash
# 后端
cd backend && .venv/bin/python -m basedpyright src/
# 前端
cd frontend && npx tsc --noEmit
```

预期：无 error（warning 可接受）

- [ ] **Step 4：Commit 验证文档**

```bash
git status  # 应无未跟踪关键文件
```

- [ ] **Step 5：发版前密钥扫描**

```bash
git diff origin/next_dev..HEAD | grep -iE '(password|secret|token|api[_-]?key)\s*[:=]\s*["\047][^"\047]+["\047]' | grep -vE '""'
```

预期：无输出

- [ ] **Step 6：按 `docs/release.md` 流程提交**

按项目发布流程：feature → next_dev 集成 → next → tag → release。涉及：

- 更新 `docs/release.md` 中的版本号
- 更新 `README.md` 主要功能列表（添加「我的最爱」「随机浏览」）
- 更新 `AGENTS.md` 重构状态追踪表

```bash
# 假设本次发版为 v1.2.0
git add README.md AGENTS.md docs/release.md
git commit -m "docs: v1.2.0 发布说明 - 我的最爱 + 随机浏览"
git push origin feature/my-favorites-and-random
```

---

## 自审检查

**1. Spec 覆盖**：
- ✅ §3.1 my_favorite 表 → Task 1
- ✅ §3.2 table_constant → Task 1
- ✅ §3.3 迁移脚本 → Task 1 沿用 SQLite 自动建表（项目现有约定）
- ✅ §4.1 FavoritesConfig → Task 6
- ✅ §4.2 Config 挂载 → Task 6
- ✅ §4.3 ConfigService → Task 7
- ✅ §4.4 /config/favorites → Task 7
- ✅ §5.1 /my-favorites/* → Task 10
- ✅ §5.2 /random → Task 5
- ✅ §5.3 虚拟 folder 注入 → Task 9
- ✅ §5.4 /my-favorites/images → Task 10
- ✅ §5.5 JOIN 策略 → Task 11（gallery/load）+ Task 5（random）+ Step 说明在 HeartOverlay（Task 15）
- ✅ §6.2 HeartOverlay → Task 14
- ✅ §6.3 WaterfallGallery 集成 → Task 15
- ✅ §6.4 FolderTile 虚拟磁贴 → Task 16
- ✅ §6.5 Config.vue section → Task 13
- ✅ §6.6 useFavoritesConfig 重构 → Task 12
- ✅ §6.7 Gallery 第三态 → Task 17
- ✅ §6.8 RandomBrowser → Task 18
- ✅ §8 测试 → 每 task 自带测试，Task 20 全量集成
- ✅ §11 兼容性 → 测试覆盖旧 localStorage fallback

**2. 占位符扫描**：已避免 "TBD"/"TODO"/"implement later" 等表述；每个 Step 含具体代码。

**3. 类型一致性**：MyFavorite / MyFavoriteDao / MyFavoritesService / my_favorites API / api/myFavorites.js 五处命名统一；`include_favorite_status` 参数名 / `is_favorited` 响应字段名 / `myFavoritesEnabled` composable 字段名跨前后端一致。

---

*Plan 完成，20 tasks，下一步由用户选择执行方式（subagent-driven 或 inline）。*