"""MyFavorites /images endpoint tests.

覆盖「我的最爱瀑布流二级页」新增 GET /api/v1/my_favorites/images 端点：
1. 路由层：返回 GalleryLoadResponse shape（total / page / page_size / has_more / data）
2. service 层：按 my_favorite.created_at DESC 排序
3. service 层：无任何我的最爱时返回 ([], 0)
4. service 层：page=2 跳过前 page_size 条（验证 OFFSET 生效）

测试策略：
- 全部走真实 service + in-memory sqlite + ContextVar session，
  与 test_my_favorites_service.py / test_gallery_load_include_favorite.py 同款
- 路由层测试用 FastAPI TestClient include_router(相同 prefix)，验证序列化与 has_more 计算
"""
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.common.constant import Rating
from src.dao.database import Base
from src.dao.my_favorite_dao import MyFavoriteDao
from src.middleware.session import _request_session
from src.models.database.yande import YandeData


@pytest.fixture
def in_memory_session(monkeypatch):
    """干净的 in-memory sqlite + ContextVar session，与现有测试同款。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    session = TestSession()
    token = _request_session.set(session)
    monkeypatch.setattr(
        "src.dao.database._get_session_factory",
        lambda: TestSession,
    )
    try:
        yield session
    finally:
        _request_session.reset(token)
        session.close()


def _seed_yande(sess, image_id: int, **overrides) -> YandeData:
    """种一张最小可用的 YandeData 记录。"""
    defaults = dict(
        tags="rating:s",
        width=100,
        height=100,
        file_ext="jpg",
        file_size=1024,
        file_url=f"http://a/{image_id}.jpg",
        preview_url=f"http://pa/{image_id}.jpg",
        md5=f"m{image_id}",
        author="t",
        rating=Rating.S,
        down_flag=True,
        created_at=datetime(2024, 1, 1),
    )
    defaults.update(overrides)
    rec = YandeData(id=image_id, **defaults)
    sess.add(rec)
    return rec


def _make_test_client():
    """FastAPI TestClient + 真实 my_favorites router。"""
    from src.api.v1.my_favorites import router as my_favorites_router

    app = FastAPI()
    app.include_router(my_favorites_router, prefix="/api/v1/my_favorites")
    return TestClient(app)


# ============================================================
# 路由层：响应字段 + has_more 计算
# ============================================================


def test_images_route_returns_paginated_response(in_memory_session):
    """GET /api/v1/my_favorites/images 返回 GalleryLoadResponse shape（含 has_more）。

    收藏 1 张图（image_id=42），page=1 page_size=20 → has_more=False（1 < 20）。
    GalleryLoadResponse 继承 PaginatedResponse，data / total / page / page_size / has_more
    是顶层兄弟字段（与 /gallery/load 响应同结构）。
    """
    _seed_yande(in_memory_session, 42)
    in_memory_session.commit()
    MyFavoriteDao.add(in_memory_session, image_id=42)
    in_memory_session.commit()

    client = _make_test_client()
    resp = client.get("/api/v1/my_favorites/images?page=1&page_size=20")
    assert resp.status_code == 200
    body = resp.json()
    # BaseResponse 三段
    assert body["code"] == "0000"
    assert body["message"] == "OK."
    # GalleryLoadResponse 顶层字段：data + total + page + page_size + has_more（兄弟，非嵌套）
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 1
    assert body["data"][0]["id"] == 42
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["has_more"] is False  # 1 < 20 → 没更多


def test_images_route_returns_empty_when_no_favorites(in_memory_session):
    """空收藏：data=[]，total=0，has_more=False。"""
    _seed_yande(in_memory_session, 1)  # 种 yande 但不收藏
    in_memory_session.commit()

    client = _make_test_client()
    resp = client.get("/api/v1/my_favorites/images?page=1&page_size=20")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["data"] == []
    assert body["has_more"] is False


# ============================================================
# service 层：排序契约 + 分页偏移
# ============================================================


def test_service_orders_images_by_favorite_created_at_desc(in_memory_session):
    """service.list_images_paginated 按 my_favorite.created_at DESC 排序。

    验证：先收藏 image_id=2，再收藏 image_id=1 → 返回顺序应是 [1, 2]（最新在前）。
    这与 /my_favorites 列表端点契约保持一致。
    """
    from src.services.my_favorites import MyFavoritesService

    _seed_yande(in_memory_session, 1)
    _seed_yande(in_memory_session, 2)
    in_memory_session.commit()

    MyFavoriteDao.add(in_memory_session, image_id=2)
    in_memory_session.commit()
    MyFavoriteDao.add(in_memory_session, image_id=1)
    in_memory_session.commit()

    images, total = MyFavoritesService.list_images_paginated(page=1, page_size=20)
    assert total == 2
    assert [img.id for img in images] == [1, 2]


def test_service_returns_empty_when_no_favorites(in_memory_session):
    """无我的最爱：service 返回 ([], 0)。"""
    from src.services.my_favorites import MyFavoritesService

    _seed_yande(in_memory_session, 1)
    _seed_yande(in_memory_session, 2)
    in_memory_session.commit()

    images, total = MyFavoritesService.list_images_paginated(page=1, page_size=20)
    assert images == []
    assert total == 0


def test_service_pagination_skips_previous_pages(in_memory_session):
    """page=2 时跳过前 page_size 条；用 page_size=1 验证 OFFSET 生效。

    收藏顺序：2 (最早) → 1 → 3 (最新)。
    page=1 page_size=1 → [3]
    page=2 page_size=1 → [1]
    page=3 page_size=1 → [2]
    """
    from src.services.my_favorites import MyFavoritesService

    for i in (1, 2, 3):
        _seed_yande(in_memory_session, i)
    in_memory_session.commit()

    MyFavoriteDao.add(in_memory_session, image_id=2)
    in_memory_session.commit()
    MyFavoriteDao.add(in_memory_session, image_id=1)
    in_memory_session.commit()
    MyFavoriteDao.add(in_memory_session, image_id=3)
    in_memory_session.commit()

    p1, _ = MyFavoritesService.list_images_paginated(page=1, page_size=1)
    p2, _ = MyFavoritesService.list_images_paginated(page=2, page_size=1)
    p3, _ = MyFavoritesService.list_images_paginated(page=3, page_size=1)
    assert [img.id for img in p1] == [3]
    assert [img.id for img in p2] == [1]
    assert [img.id for img in p3] == [2]