"""POST /api/v1/favorites/{id}/local-count 与 /refresh 契约测试

背景：前端「下载完成 → 收藏夹角标 +N」走 /local-count（O(1)：一条 UPDATE by PK），
刻意避开 /refresh（后端重跑 `tags LIKE ... AND down_flag=1` 的 COUNT，随已下载库
线性放大，且该路由未走 asyncio.to_thread → 阻塞事件循环）。

本文件把这条「贵/便宜」分界锁死：
- /local-count：写值即可，**不得**触发 yande_data 扫描
- /refresh：会重算（记录现状，防止有人误把前端改回去）
"""
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.dao.database import Base
from src.models.database.yande import FavoriteFolder
from src.services.favorites import FavoritesService


@pytest.fixture
def client(monkeypatch):
    """in-memory sqlite + RequestSessionMiddleware（favorite_dao 走请求级 session）。

    注意要 patch **两处**：``src.middleware.session`` 在 import 时就把
    ``_get_session_factory`` 引用绑到了自己的模块命名空间（``from ... import``），
    只 patch ``src.dao.database`` 不会影响中间件 —— 中间件会去连真实的
    backend/data/yande_data.db，导致 404。
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr("src.dao.database._get_session_factory", lambda: TestSession)
    monkeypatch.setattr("src.middleware.session._get_session_factory", lambda: TestSession)

    from src.api.v1.favorites import router as favorites_router
    from src.middleware.session import RequestSessionMiddleware

    app = FastAPI()
    app.include_router(favorites_router, prefix="/api/v1/favorites")
    RequestSessionMiddleware.init_app(app)
    with TestClient(app) as c:
        yield c, TestSession


def _seed(TestSession, **kwargs) -> int:
    s = TestSession()
    folder = FavoriteFolder(name=kwargs.pop("name", "f1"), tags=kwargs.pop("tags", "tag_a"), **kwargs)
    s.add(folder)
    s.commit()
    folder_id = folder.id
    s.close()
    return folder_id


def test_local_count_writes_value_without_scanning_yande_data(client):
    """/local-count?count=N 直接写值，不跑 yande_data 的 COUNT（O(1) 增量路径）。"""
    c, TestSession = client
    folder_id = _seed(TestSession, local_count=100)

    with patch.object(
        FavoritesService, "_parse_tags_to_params", side_effect=AssertionError("不应解析 tag")
    ), patch(
        "src.dao.yande_data_dao.YandeDataRepository.query",
        side_effect=AssertionError("不应扫描 yande_data"),
    ):
        resp = c.post(f"/api/v1/favorites/{folder_id}/local-count", params={"count": 101})

    assert resp.status_code == 200
    assert resp.json()["data"]["count"] == 101

    s = TestSession()
    assert s.get(FavoriteFolder, folder_id).local_count == 101
    s.close()


def test_local_count_accepts_zero(client):
    c, TestSession = client
    folder_id = _seed(TestSession, local_count=50)
    resp = c.post(f"/api/v1/favorites/{folder_id}/local-count", params={"count": 0})
    assert resp.status_code == 200
    s = TestSession()
    assert s.get(FavoriteFolder, folder_id).local_count == 0
    s.close()


def test_local_count_requires_count_param(client):
    """count 是必填 query 参数：漏传直接 422（前端 setLocalCount 始终传）。"""
    c, TestSession = client
    folder_id = _seed(TestSession, local_count=10)
    assert c.post(f"/api/v1/favorites/{folder_id}/local-count").status_code == 422


def test_local_count_404_for_missing_folder(client):
    c, _ = client
    assert c.post("/api/v1/favorites/999999/local-count", params={"count": 1}).status_code >= 400


def test_refresh_recomputes_via_yande_data_query(client):
    """记录现状：/refresh 会重算（这正是前端要避开的那条贵路径）。"""
    c, TestSession = client
    folder_id = _seed(TestSession, name="f2", tags="tag_b", local_count=999)

    with patch(
        "src.dao.yande_data_dao.YandeDataRepository.query",
        return_value=([], 12),
    ) as mock_query:
        resp = c.post(f"/api/v1/favorites/{folder_id}/refresh")

    assert resp.status_code == 200
    assert mock_query.called
    s = TestSession()
    assert s.get(FavoriteFolder, folder_id).local_count == 12  # 999 被真实计数覆盖
    s.close()
