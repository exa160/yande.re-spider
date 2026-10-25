"""收藏夹一级页拆分后的单 folder 预览接口契约。

一级页改为 GET /favorites 取列表 + 逐 folder GET /favorites/{id}/preview 取预览。
本文件覆盖预览接口的排序 / include_online / 计数门禁 / 空 tags。
"""
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.common.constant import Rating, TaskStatus
from src.dao.favorite_dao import FavoriteDao
from src.middleware.session import _request_session
from src.models.database.yande import Base, DownloadTask, FavoriteFolder, YandeData


@pytest.fixture
def in_memory_session(monkeypatch):
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
        yield session, engine
    finally:
        _request_session.reset(token)
        session.close()


@pytest.fixture
def client(monkeypatch):
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

    seed = TestSession()
    folder = FavoriteFolder(name="fold", tags="pic_tag", local_count=999)
    seed.add(folder)
    seed.add_all(
        [
            _yande(5001, "pic_tag", down_flag=True),
            _yande(5002, "pic_tag", down_flag=True),
            _yande(5003, "pic_tag", down_flag=False),
        ]
    )
    seed.commit()
    folder_id = folder.id
    seed.close()

    with TestClient(app) as c:
        yield c, folder_id, TestSession


def _yande(image_id: int, tags: str, down_flag: bool = True) -> YandeData:
    return YandeData(
        id=image_id,
        tags=tags,
        width=100,
        height=100,
        file_ext="jpg",
        file_size=1024,
        file_url=f"http://a/{image_id}.jpg",
        preview_url=f"http://pa/{image_id}.jpg",
        md5=f"m{image_id}",
        author="t",
        created_at=datetime(2024, 1, 1),
        down_flag=down_flag,
        rating=Rating.S,
    )


def _seed_folder(sess, name: str, tags: str, local_count: int = 10) -> int:
    folder = FavoriteFolder(name=name, tags=tags, local_count=local_count)
    sess.add(folder)
    sess.commit()
    return folder.id


def _seed_completed_download(sess, image_id: int, completed_at: datetime) -> None:
    sess.add(
        DownloadTask(
            task_id=f"task-{image_id}",
            image_id=image_id,
            file_name=f"{image_id}.jpg",
            status=TaskStatus.COMPLETED,
            completed_at=completed_at,
            created_at=completed_at,
        )
    )
    sess.commit()


def test_preview_desc_returns_newest_first(client):
    c, folder_id, _ = client
    resp = c.get(
        f"/api/v1/favorites/{folder_id}/preview?limit=2&preview_order=desc"
    )
    assert resp.status_code == 200
    ids = [img["id"] for img in resp.json()["data"]["preview_images"]]
    assert ids == [5002, 5001]


def test_preview_asc_returns_oldest_first(client):
    c, folder_id, _ = client
    resp = c.get(
        f"/api/v1/favorites/{folder_id}/preview?limit=2&preview_order=asc"
    )
    assert resp.status_code == 200
    ids = [img["id"] for img in resp.json()["data"]["preview_images"]]
    assert ids == [5001, 5002]


def test_preview_defaults_to_downloaded_only(client):
    c, folder_id, _ = client
    resp = c.get(f"/api/v1/favorites/{folder_id}/preview?limit=8&preview_order=asc")
    assert resp.status_code == 200
    ids = [img["id"] for img in resp.json()["data"]["preview_images"]]
    assert ids == [5001, 5002]


def test_preview_include_online_includes_undownloaded(client):
    c, folder_id, _ = client
    resp = c.get(
        f"/api/v1/favorites/{folder_id}/preview"
        "?limit=8&preview_order=asc&include_online=true"
    )
    assert resp.status_code == 200
    ids = [img["id"] for img in resp.json()["data"]["preview_images"]]
    assert ids == [5001, 5002, 5003]


def test_preview_invalid_order_is_422(client):
    c, folder_id, _ = client
    resp = c.get(
        f"/api/v1/favorites/{folder_id}/preview?preview_order=sideways"
    )
    assert resp.status_code == 422


def test_preview_missing_folder_is_404(client):
    c, _, _ = client
    resp = c.get("/api/v1/favorites/99999/preview")
    assert resp.status_code == 404


def test_preview_uses_cached_count_when_fresh(in_memory_session):
    """last_refresh 晚于最近 completed 下载 → 不重算，total 返回缓存值。"""
    sess, _ = in_memory_session
    folder_id = _seed_folder(sess, "fresh", "fresh_tag", local_count=999)
    for image_id in (5101, 5102):
        sess.add(_yande(image_id, "fresh_tag"))
    sess.commit()
    FavoriteDao().update(
        folder_id,
        last_refresh=datetime(2025, 6, 1),
    )
    sess.commit()
    _seed_completed_download(sess, image_id=5101, completed_at=datetime(2025, 1, 1))

    from src.services.favorites import FavoritesService

    result = FavoritesService.preview_folder(
        folder_id=folder_id, limit=8, preview_order="desc"
    )

    assert result["total"] == 999
    assert FavoriteDao().get_by_id(folder_id).local_count == 999


def test_preview_refreshes_count_when_stale(in_memory_session):
    """last_refresh 早于最近 completed 下载 → 重算并落库。"""
    sess, _ = in_memory_session
    folder_id = _seed_folder(sess, "stale", "stale_tag", local_count=999)
    for image_id in (5201, 5202):
        sess.add(_yande(image_id, "stale_tag"))
    sess.commit()
    FavoriteDao().update(folder_id, last_refresh=datetime(2025, 1, 1))
    sess.commit()
    _seed_completed_download(sess, image_id=5201, completed_at=datetime(2025, 2, 1))

    from src.services.favorites import FavoritesService

    result = FavoritesService.preview_folder(
        folder_id=folder_id, limit=8, preview_order="desc"
    )

    assert result["total"] == 2
    folder = FavoriteDao().get_by_id(folder_id)
    assert folder.local_count == 2
    assert folder.last_refresh is not None
    assert folder.last_refresh > datetime(2025, 1, 1)


def test_preview_empty_tags_returns_no_images_and_cached_count(in_memory_session):
    sess, _ = in_memory_session
    folder_id = _seed_folder(sess, "empty", "", local_count=7)
    sess.add(_yande(5301, "anything"))
    sess.commit()

    from src.services.favorites import FavoritesService

    result = FavoritesService.preview_folder(
        folder_id=folder_id, limit=8, preview_order="desc"
    )

    assert result["preview_images"] == []
    assert result["total"] == 7


def test_preview_whitespace_tags_returns_no_images(in_memory_session):
    """空白 tags 视同空标签，不应退化成「全库下载图」。"""
    sess, _ = in_memory_session
    folder_id = _seed_folder(sess, "blank", "   ", local_count=7)
    sess.add(_yande(5302, "anything"))
    sess.commit()

    from src.services.favorites import FavoritesService

    result = FavoritesService.preview_folder(
        folder_id=folder_id, limit=8, preview_order="desc"
    )

    assert result["preview_images"] == []
    assert result["total"] == 7


def test_preview_rating_serializes_to_display(client):
    c, folder_id, _ = client
    resp = c.get(f"/api/v1/favorites/{folder_id}/preview?limit=1&preview_order=asc")
    assert resp.status_code == 200
    assert resp.json()["data"]["preview_images"][0]["rating"] == "Safe"
