"""refresh_online_count 的 TTL 保鲜 + online-count 端点清理

背景：online_count 是**远端数据**（yande.re 全站该 tags 的图片数），本地算不出来。
之前每次 POST /favorites/{id}/refresh-online 都会真的打一次 yande.re HTTP，
且路由是 async 但没解阻塞（同步 requests 卡事件循环）。现在：

- TTL：距 online_refreshed_at 不足 max_age_seconds 直接返回缓存，不打远端
- force=True 跳过 TTL
- online 刷新只写 online_refreshed_at，不再占用 last_refresh
  （last_refresh 被 local_count 共用，会让「刚重算过本地数」的 folder
    把陈旧的 online_count 误判成新鲜 → TTL 形同虚设）
- POST /favorites/{id}/online-count（客户端直接写值）已删除：零调用点
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

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
    """in-memory sqlite + RequestSessionMiddleware。

    必须 patch 两处 ``_get_session_factory``：middleware/session.py 在 import 时
    就把引用绑进了自己模块的命名空间，只 patch dao.database 对中间件无效。

    另：把请求级 session 的 ContextVar 在整个 fixture 期间设上，让**直接调用
    service** 的用例（不经 HTTP）也能拿到 session —— favorite_dao 单例走
    ``RequestSessionMiddleware.get_session()``，缺 ContextVar 会直接抛错
    （「For background tasks, use 'with FavoriteDao() as dao:'」）。
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
    from src.middleware.session import RequestSessionMiddleware, _request_session

    app = FastAPI()
    app.include_router(favorites_router, prefix="/api/v1/favorites")
    RequestSessionMiddleware.init_app(app)

    probe = TestSession()
    token = _request_session.set(probe)
    try:
        with TestClient(app) as c:
            yield c, TestSession
    finally:
        _request_session.reset(token)
        probe.close()


def _seed(TestSession, **kwargs) -> int:
    s = TestSession()
    folder = FavoriteFolder(
        name=kwargs.pop("name", "f1"), tags=kwargs.pop("tags", "tag_a"), **kwargs
    )
    s.add(folder)
    s.commit()
    folder_id = folder.id
    s.close()
    return folder_id


def _get(TestSession, folder_id) -> FavoriteFolder:
    s = TestSession()
    folder = s.get(FavoriteFolder, folder_id)
    s.close()
    return folder


# ============================================================
# Service：TTL
# ============================================================


def test_first_refresh_hits_remote_and_records_timestamp(client):
    _, TestSession = client
    folder_id = _seed(TestSession, online_count=0)
    api = MagicMock()
    api.get_count.return_value = 4242

    with patch("src.services.favorites.YandeApi", return_value=api):
        assert FavoritesService.refresh_online_count(folder_id) == 4242

    api.get_count.assert_called_once_with("tag_a")
    folder = _get(TestSession, folder_id)
    assert folder.online_count == 4242
    assert folder.online_refreshed_at is not None


def test_within_ttl_returns_cache_without_hitting_remote(client):
    """TTL 内的重复调用（每次进收藏夹二级页都会调）不再打 yande.re。"""
    _, TestSession = client
    folder_id = _seed(
        TestSession, online_count=99, online_refreshed_at=datetime.now() - timedelta(seconds=30)
    )
    api = MagicMock()
    api.get_count.return_value = 1

    with patch("src.services.favorites.YandeApi", return_value=api):
        assert FavoritesService.refresh_online_count(folder_id, max_age_seconds=600) == 99

    api.get_count.assert_not_called()
    assert _get(TestSession, folder_id).online_count == 99


def test_expired_ttl_refetches(client):
    _, TestSession = client
    folder_id = _seed(
        TestSession,
        online_count=99,
        online_refreshed_at=datetime.now() - timedelta(seconds=1200),
    )
    api = MagicMock()
    api.get_count.return_value = 555

    with patch("src.services.favorites.YandeApi", return_value=api):
        assert FavoritesService.refresh_online_count(folder_id, max_age_seconds=600) == 555

    api.get_count.assert_called_once()
    assert _get(TestSession, folder_id).online_count == 555


def test_force_skips_ttl(client):
    _, TestSession = client
    folder_id = _seed(
        TestSession, online_count=99, online_refreshed_at=datetime.now()
    )
    api = MagicMock()
    api.get_count.return_value = 777

    with patch("src.services.favorites.YandeApi", return_value=api):
        assert FavoritesService.refresh_online_count(folder_id, force=True) == 777

    api.get_count.assert_called_once()
    assert _get(TestSession, folder_id).online_count == 777


def test_max_age_zero_always_refetches(client):
    _, TestSession = client
    folder_id = _seed(
        TestSession, online_count=1, online_refreshed_at=datetime.now()
    )
    api = MagicMock()
    api.get_count.return_value = 2

    with patch("src.services.favorites.YandeApi", return_value=api):
        FavoritesService.refresh_online_count(folder_id, max_age_seconds=0)

    api.get_count.assert_called_once()


def test_null_timestamp_always_refetches(client):
    """从未刷过的 folder（online_refreshed_at IS NULL）直接走远端。"""
    _, TestSession = client
    folder_id = _seed(TestSession, online_count=0, online_refreshed_at=None)
    api = MagicMock()
    api.get_count.return_value = 8

    with patch("src.services.favorites.YandeApi", return_value=api):
        assert FavoritesService.refresh_online_count(folder_id) == 8

    api.get_count.assert_called_once()


def test_online_refresh_does_not_touch_last_refresh(client):
    """online 刷新不能写 last_refresh：它与 local_count 共用，会破坏 TTL 判定。"""
    _, TestSession = client
    folder_id = _seed(TestSession, online_count=0, last_refresh=datetime(2020, 1, 1))
    api = MagicMock()
    api.get_count.return_value = 3

    with patch("src.services.favorites.YandeApi", return_value=api):
        FavoritesService.refresh_online_count(folder_id)

    folder = _get(TestSession, folder_id)
    assert folder.last_refresh == datetime(2020, 1, 1)  # 未被污染
    assert folder.online_refreshed_at is not None


def test_remote_failure_returns_none_and_keeps_cache(client):
    """get_count 返回 -1（网络失败）→ None，不覆盖已有缓存、不更新时间戳。"""
    _, TestSession = client
    stamp = datetime.now() - timedelta(seconds=5000)
    folder_id = _seed(TestSession, online_count=42, online_refreshed_at=stamp)
    api = MagicMock()
    api.get_count.return_value = -1

    with patch("src.services.favorites.YandeApi", return_value=api):
        assert FavoritesService.refresh_online_count(folder_id) is None

    folder = _get(TestSession, folder_id)
    assert folder.online_count == 42
    assert folder.online_refreshed_at == stamp


def test_missing_folder_returns_none(client):
    _, _ = client
    api = MagicMock()
    with patch("src.services.favorites.YandeApi", return_value=api):
        assert FavoritesService.refresh_online_count(999999) is None
    api.get_count.assert_not_called()


# ============================================================
# Route
# ============================================================


def test_route_passes_ttl_params_through(client):
    c, TestSession = client
    folder_id = _seed(TestSession, online_count=0)
    with patch("src.api.v1.favorites.FavoritesService.refresh_online_count") as svc:
        svc.return_value = 12
        resp = c.post(
            f"/api/v1/favorites/{folder_id}/refresh-online",
            params={"max_age_seconds": 120, "force": True},
        )
    assert resp.status_code == 200
    svc.assert_called_once_with(folder_id, 120, True)


def test_route_defaults_ttl_to_600(client):
    c, TestSession = client
    folder_id = _seed(TestSession, online_count=0)
    with patch("src.api.v1.favorites.FavoritesService.refresh_online_count") as svc:
        svc.return_value = 1
        c.post(f"/api/v1/favorites/{folder_id}/refresh-online")
    svc.assert_called_once_with(folder_id, 600, False)


def test_route_returns_error_when_refresh_fails(client):
    c, TestSession = client
    folder_id = _seed(TestSession, online_count=0)
    with patch("src.api.v1.favorites.FavoritesService.refresh_online_count") as svc:
        svc.return_value = None
        resp = c.post(f"/api/v1/favorites/{folder_id}/refresh-online")
    assert resp.status_code >= 400


def test_online_count_endpoint_is_removed(client):
    """POST /favorites/{id}/online-count 已删除（客户端直接写值，零调用点）。"""
    c, TestSession = client
    folder_id = _seed(TestSession, online_count=0)
    resp = c.post(f"/api/v1/favorites/{folder_id}/online-count", params={"count": 5})
    assert resp.status_code == 404


def test_refresh_online_runs_off_event_loop(client):
    """路由必须 to_thread：同步 requests 直接写在 async 路由里会阻塞事件循环。"""
    import inspect

    from src.api.v1 import favorites as fav_api

    src = inspect.getsource(fav_api.refresh_online_count)
    assert "asyncio.to_thread" in src
