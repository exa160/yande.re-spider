"""测试 GET /favorites/{folder_id}/preview 的 ?random=true 与 ?limit 参数

Spec 8.1 要求覆盖：
- test_preview_random
- test_preview_random_limit

API: GET /api/v1/favorites/{folder_id}/preview?limit={N}&random={true|false}
实现位于 backend/src/api/v1/favorites.py::preview_folder，转发到
FavoritesService.preview_folder(folder_id, limit, random)。

测试策略：在 FastAPI TestClient + monkeypatch FavoritesService.preview_folder，
验证 API 路由正确把 query 参数传给 service，service 根据 random 选择
random 抽样 vs 按当前 sort 排序，limit 控制返回上限。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import init_app, app_config


@pytest.fixture
def client():
    test_app = FastAPI(**app_config.model_dump())
    init_app(test_app)
    return TestClient(test_app)


def _mk_image(i: int) -> dict:
    return {
        "id": 1000 + i,
        "tags": "sample",
        "width": 100,
        "height": 100,
        "file_ext": "jpg",
        "file_size": 1024,
        "file_url": f"http://example.com/{i}.jpg",
        "preview_url": f"http://example.com/p_{i}.jpg",
        "md5": f"md5_{i}",
        "author": "tester",
        "down_flag": True,
    }


def test_preview_random_default_is_false(client, monkeypatch):
    """?random 不传 → 默认 False，调用 service 时 random=False"""
    captured = {}

    def fake_preview(folder_id, limit, random):
        captured["folder_id"] = folder_id
        captured["limit"] = limit
        captured["random"] = random
        return {"total": 100, "preview_images": [_mk_image(0)]}

    monkeypatch.setattr(
        "src.services.favorites.FavoritesService.preview_folder",
        staticmethod(fake_preview),
    )

    resp = client.get("/api/v1/favorites/1/preview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "0000"  # ErrMsg.OK
    assert body["data"]["total"] == 100
    assert len(body["data"]["preview_images"]) == 1
    # 校验 service 收到的参数
    assert captured["folder_id"] == 1
    assert captured["limit"] == 6  # API 默认 limit=6
    assert captured["random"] is False


def test_preview_random_true(client, monkeypatch):
    """?random=true → service 收到 random=True"""
    captured = {}

    def fake_preview(folder_id, limit, random):
        captured["folder_id"] = folder_id
        captured["limit"] = limit
        captured["random"] = random
        # 模拟 random 分支返回完全不同的图片集合
        return {"total": 50, "preview_images": [_mk_image(7), _mk_image(3)]}

    monkeypatch.setattr(
        "src.services.favorites.FavoritesService.preview_folder",
        staticmethod(fake_preview),
    )

    resp = client.get("/api/v1/favorites/42/preview?random=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["total"] == 50
    assert len(body["data"]["preview_images"]) == 2
    # 关键断言：random 参数原样透传到 service
    assert captured["folder_id"] == 42
    assert captured["random"] is True


def test_preview_random_false_explicit(client, monkeypatch):
    """?random=false → service 收到 random=False"""
    captured = {}

    def fake_preview(folder_id, limit, random):
        captured["random"] = random
        return {"total": 100, "preview_images": [_mk_image(0)]}

    monkeypatch.setattr(
        "src.services.favorites.FavoritesService.preview_folder",
        staticmethod(fake_preview),
    )

    resp = client.get("/api/v1/favorites/1/preview?random=false")
    assert resp.status_code == 200
    assert captured["random"] is False


def test_preview_random_limit_9(client, monkeypatch):
    """?limit=9 → service 收到 limit=9"""
    captured = {}

    def fake_preview(folder_id, limit, random):
        captured["folder_id"] = folder_id
        captured["limit"] = limit
        captured["random"] = random
        # 模拟 service 在 random=True 分支返回 9 张（按 limit 截断）
        return {"total": 100, "preview_images": [_mk_image(i) for i in range(9)]}

    monkeypatch.setattr(
        "src.services.favorites.FavoritesService.preview_folder",
        staticmethod(fake_preview),
    )

    resp = client.get("/api/v1/favorites/7/preview?random=true&limit=9")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["total"] == 100
    assert len(body["data"]["preview_images"]) == 9
    # 关键断言：limit 参数原样透传到 service
    assert captured["folder_id"] == 7
    assert captured["limit"] == 9
    assert captured["random"] is True


def test_preview_random_limit_validation(client, monkeypatch):
    """?limit=200 (>le=50) → API 应拒绝（Query 约束 le=50），返回 422"""
    captured = {}

    def fake_preview(folder_id, limit, random):
        captured["called"] = True
        return {"total": 0, "preview_images": []}

    monkeypatch.setattr(
        "src.services.favorites.FavoritesService.preview_folder",
        staticmethod(fake_preview),
    )

    resp = client.get("/api/v1/favorites/1/preview?random=true&limit=200")
    assert resp.status_code == 422
    assert "called" not in captured  # service 不应被调用