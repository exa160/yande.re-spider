"""验证 /api/v1/gallery/load source='favorites' 分支。

Task 3 实施范围：
1. test_query_local_database_with_favorite_tags - 前置验证 service 现有能力（应 PASS）
2. test_route_favorites_include_online_merges - 验证 route 合并 local + yande
3. test_route_favorites_without_include_online - 验证默认只查 local
4. test_route_favorites_missing_folder - 验证 folder 不存在时优雅返回空
"""
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import app_config, init_app
from src.common.constant import Rating
from src.dao.database import _get_session_factory
from src.dao.favorite_dao import favorite_dao
from src.dao.yande_data_dao import YandeDataRepository
from src.middleware.session import _request_session
from src.models.database.yande import FavoriteFolder, YandeData
from src.models.request.gallery import GalleryLoadRequest
from src.services.gallery import GalleryService


@contextmanager
def _request_session_ctx():
    """为 favorite_dao 单例临时提供 request session contextvar。"""
    session = _get_session_factory()()
    token = _request_session.set(session)
    try:
        yield session
    finally:
        session.close()
        _request_session.reset(token)


def _clean() -> None:
    """清空 favorite_folders 和 yande_data 测试数据。"""
    with _request_session_ctx():
        with YandeDataRepository() as repo:
            repo.session.query(YandeData).delete()
            repo.session.query(FavoriteFolder).delete()


def _seed() -> int:
    """创建 1 个 folder（tags='sample'） + 3 张已下载图片，返回 folder.id。"""
    with _request_session_ctx():
        with favorite_dao as dao:
            folder = dao.create(name="f", tags="sample")
            folder_id = folder.id
        with YandeDataRepository() as repo:
            for i in range(3):
                repo.session.add(
                    YandeData(
                        id=7000 + i,
                        tags="sample",
                        width=100,
                        height=100,
                        file_ext="jpg",
                        file_size=1024,
                        file_url=f"http://a{i}.jpg",
                        preview_url=f"http://pa{i}.jpg",
                        md5=f"m{i}",
                        author="t",
                        created_at=datetime(2024, 1, 1),
                        down_flag=True,
                        rating=Rating.S,
                    )
                )
        return folder_id


# ---------- 前置验证：service 现有能力 ----------


def test_query_local_database_with_favorite_tags():
    """前置验证：GalleryService.query_local_database 可按 tags 查询。

    本测试在 Task 3 实施前应直接 PASS，验证 service 行为契约不被破坏。
    收藏夹 integration 由后续 route 测试覆盖。
    """
    _clean()
    _seed()
    req = GalleryLoadRequest(source="local", tags="sample", page_size=10)
    with _request_session_ctx():
        images, total = GalleryService.query_local_database(req)
    assert total == 3
    assert len(images) == 3
    assert {img.id for img in images} == {7000, 7001, 7002}


# ---------- API 路由层 ----------


@pytest.fixture
def client():
    test_app = FastAPI(**app_config.model_dump())
    init_app(test_app)
    return TestClient(test_app)


def test_route_favorites_include_online_merges(client, monkeypatch):
    """source='favorites' + include_online=True 应合并 local + yande，local 优先。

    - seed 3 张本地 (id 7000-7002)
    - monkeypatch yande 返回 2 条: id=7777 (新), id=7001 (重复, 应被去重)
    - 期望返回 4 条: 7000, 7001, 7002, 7777
    """
    _clean()
    fid = _seed()

    fake = [
        {
            "id": 7777,
            "tags": "sample",
            "width": 100,
            "height": 100,
            "file_ext": "jpg",
            "file_size": 1024,
            "file_url": "http://x.jpg",
            "preview_url": "http://px.jpg",
            "md5": "mx",
            "author": "t",
            "created_at": datetime(2024, 1, 1),
            "down_flag": False,
            "rating": Rating.S,
            "score": 0,
        },
        {
            "id": 7001,  # 与 local 重复，应被去重
            "tags": "sample",
            "width": 100,
            "height": 100,
            "file_ext": "jpg",
            "file_size": 1024,
            "file_url": "http://dup.jpg",
            "preview_url": "http://pdup.jpg",
            "md5": "mdup",
            "author": "t",
            "created_at": datetime(2024, 1, 1),
            "down_flag": True,
            "rating": Rating.S,
            "score": 0,
        },
    ]
    monkeypatch.setattr(
        "src.services.gallery.GalleryService.query_yande_api",
        staticmethod(lambda req: (fake, 2)),
    )

    resp = client.post(
        "/api/v1/gallery/load",
        json={
            "source": "favorites",
            "favorite_id": fid,
            "include_online": True,
            "page_size": 10,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    ids = [img["id"] for img in body["data"]]
    # yande 新增项应出现
    assert 7777 in ids
    # local 项应保留（且顺序在前）
    assert 7000 in ids
    assert 7001 in ids
    assert 7002 in ids
    # 去重：7001 不应出现两次
    assert ids.count(7001) == 1
    # 合并后总数 = 3 local + 1 new = 4
    assert len(ids) == 4


def test_route_favorites_without_include_online(client, monkeypatch):
    """source='favorites' + include_online=False（默认）只查 local，不调 yande。"""
    _clean()
    fid = _seed()

    def _should_not_be_called(req):
        raise AssertionError("query_yande_api should not be called when include_online=False")

    monkeypatch.setattr(
        "src.services.gallery.GalleryService.query_yande_api",
        staticmethod(_should_not_be_called),
    )

    resp = client.post(
        "/api/v1/gallery/load",
        json={
            "source": "favorites",
            "favorite_id": fid,
            "page_size": 10,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    ids = [img["id"] for img in body["data"]]
    assert sorted(ids) == [7000, 7001, 7002]


def test_route_favorites_missing_folder_returns_empty(client, monkeypatch):
    """source='favorites' 但 favorite_id 不存在 → 优雅返回空列表，不抛 500。"""
    _clean()

    def _should_not_be_called(req):
        raise AssertionError("should not query local/yande for missing folder")

    monkeypatch.setattr(
        "src.services.gallery.GalleryService.query_local_database",
        staticmethod(_should_not_be_called),
    )
    monkeypatch.setattr(
        "src.services.gallery.GalleryService.query_yande_api",
        staticmethod(_should_not_be_called),
    )

    resp = client.post(
        "/api/v1/gallery/load",
        json={
            "source": "favorites",
            "favorite_id": 99999,  # 不存在
            "include_online": True,
            "page_size": 10,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["total"] == 0
    assert body["has_more"] is False