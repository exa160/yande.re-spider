"""验证 /favorites/with-preview 的 tile_size 参数决定预览图数

Spec: tile_size ∈ {adaptive, small, medium, large}
- adaptive: 永远返 8（前端按 tile 实际宽度像素裁剪 4/6/8 张显示）
- small: 固定 4
- medium: 固定 6
- large: 固定 8

测试策略：通过 FavoritesService.get_folders_with_preview(..., tile_size=...) 直接验证
service 层签名与行为。路由层 FastAPI TestClient 验证 tile_size 参数透传与正则校验。
"""
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import init_app, app_config
from src.dao.database import _get_session_factory
from src.dao.favorite_dao import favorite_dao
from src.dao.yande_data_dao import YandeDataRepository
from src.middleware.session import _request_session
from src.models.database.yande import FavoriteFolder, YandeData
from src.services.favorites import FavoritesService


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


def _seed_folder(local_count: int, name: str, tags: str = "tile_test_tag") -> int:
    """创建收藏夹并设置 local_count，提交后返回 id。"""
    with favorite_dao as dao:
        folder = dao.create(name=name, tags=tags)
        folder.local_count = local_count
        return folder.id


def _seed_yande_data(tag: str, count: int, start_id: int = 9000) -> None:
    """插入 count 条已下载图片。"""
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
                md5=f"md5_{start_id}_{i}",
                author="tester",
                created_at=datetime(2024, 1, 1, 0, 0, 0),
                down_flag=True,
                rating="s",
            )
            repo.session.add(rec)


# ---------- service 层 ----------

def test_tile_size_small_returns_4():
    """local_count=100 (adaptive 应返回 6) → small 强制返回 4"""
    _clean()
    _seed_folder(100, "ts_small")
    _seed_yande_data("tile_test_tag", 100)
    with _request_session_ctx():
        items, _, _ = FavoritesService.get_folders_with_preview(
            page=1, page_size=20, tile_size="small"
        )
    assert len(items[0].preview_images) == 4


def test_tile_size_medium_returns_6():
    """local_count=10 (adaptive 应返回 4) → medium 强制返回 6"""
    _clean()
    _seed_folder(10, "ts_medium")
    _seed_yande_data("tile_test_tag", 10)
    with _request_session_ctx():
        items, _, _ = FavoritesService.get_folders_with_preview(
            page=1, page_size=20, tile_size="medium"
        )
    assert len(items[0].preview_images) == 6


def test_tile_size_large_returns_8():
    """local_count=10 (adaptive 应返回 4) → large 强制返回 8"""
    _clean()
    _seed_folder(10, "ts_large")
    _seed_yande_data("tile_test_tag", 10)
    with _request_session_ctx():
        items, _, _ = FavoritesService.get_folders_with_preview(
            page=1, page_size=20, tile_size="large"
        )
    assert len(items[0].preview_images) == 8


def test_tile_size_adaptive_always_returns_8():
    """tile_size='adaptive' 不再按 local_count 分档，永远返 8 张

    即便 local_count=10（旧版 adaptive 会返 4），现在也必须返 8——后端只给上限，
    实际显示张数由前端 FolderTile 按 tile 实际宽度像素裁剪。
    """
    _clean()
    _seed_folder(10, "ts_adaptive")
    _seed_yande_data("tile_test_tag", 10)
    with _request_session_ctx():
        items, _, _ = FavoritesService.get_folders_with_preview(
            page=1, page_size=20, tile_size="adaptive"
        )
    assert len(items[0].preview_images) == 8


# ---------- API 路由层 ----------

@pytest.fixture
def client():
    test_app = FastAPI(**app_config.model_dump())
    init_app(test_app)
    return TestClient(test_app)


def test_api_tile_size_param_passthrough(client, monkeypatch):
    """GET /favorites/with-preview?tile_size=large → service 收到 tile_size='large'"""
    captured = {}

    def fake_get_folders_with_preview(page=1, page_size=20, tile_size="adaptive"):
        captured["page"] = page
        captured["page_size"] = page_size
        captured["tile_size"] = tile_size
        return [], 0, False

    monkeypatch.setattr(
        "src.services.favorites.FavoritesService.get_folders_with_preview",
        staticmethod(fake_get_folders_with_preview),
    )

    resp = client.get("/api/v1/favorites/with-preview?tile_size=large")
    assert resp.status_code == 200
    assert captured["tile_size"] == "large"
    assert captured["page"] == 1
    assert captured["page_size"] == 20


def test_api_tile_size_invalid_value_returns_422(client):
    """tile_size=invalid 不在正则白名单内 → 422"""
    resp = client.get("/api/v1/favorites/with-preview?tile_size=invalid")
    assert resp.status_code == 422