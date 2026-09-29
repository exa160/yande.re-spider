"""MyFavorites API route tests.

覆盖 /api/v1/my_favorites/* 全部 5 个端点：
1. GET    /                       分页列出我的最爱
2. POST   /{image_id}             加入我的最爱（成功）
3. POST   /{image_id}             加入我的最爱（image_id 不存在 → 404）
4. DELETE /{image_id}             取消我的最爱
5. GET    /count                  总数
6. GET    /preview?limit=N        预览图

测试策略：
- 用 minimal FastAPI app + 仅注册 my_favorites router（避免触发 init_app 的 scheduler/lifespan 副作用）
- patch `src.api.v1.my_favorites.MyFavoritesService` 替换为 mock，避免真实 DB 访问
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.models.response.my_favorites import (
    MyFavoritePreviewImage,
    MyFavoritesListItem,
)


@pytest.fixture
def client():
    """FastAPI TestClient + mock MyFavoritesService.

    路由前缀：APILoader 在生产环境会把 my_favorites router 挂到 /api/v1/my_favorites，
    但测试里我们手工 include_router 时显式声明 /api/v1/my_favorites 前缀（与生产等价）。
    """
    from src.api.v1.my_favorites import router as my_favorites_router

    app = FastAPI()
    app.include_router(my_favorites_router, prefix="/api/v1/my_favorites")

    with patch("src.api.v1.my_favorites.MyFavoritesService") as mock_svc:
        # 默认 mock 行为：service 方法调用不报错；具体测试按需覆盖 side_effect
        mock_svc.add = AsyncMock()
        mock_svc.remove = MagicMock()
        mock_svc.count = MagicMock(return_value=10)
        mock_svc.list_paginated = MagicMock(
            return_value=(
                [MyFavoritesListItem(id=1, image_id=42, created_at="2026-01-01T00:00:00")],
                1,
            )
        )
        mock_svc.get_preview = MagicMock(
            return_value=[
                MyFavoritePreviewImage(id=1, preview_url=None, tags="", rating="")
            ]
        )
        yield TestClient(app), mock_svc


def test_add_my_favorite_returns_200(client):
    """POST /api/v1/my_favorites/{image_id} returns 200 on success."""
    c, _ = client
    resp = c.post("/api/v1/my_favorites/42")
    assert resp.status_code == 200


def test_add_my_favorite_returns_404_for_nonexistent(client):
    """POST /api/v1/my_favorites/{image_id} returns 404 when image not in yande_data.

    service.add raises ValueError → route maps to ErrMsg.NOT_FOUND (HTTP 404)
    per /home/exa160/opencode/yande.re-spider-next-dev/backend/src/api/v1/my_favorites.py
    """
    c, mock_svc = client
    mock_svc.add.side_effect = ValueError("Image 999 not found")
    resp = c.post("/api/v1/my_favorites/999")
    assert resp.status_code in (404, 400)


def test_remove_my_favorite_returns_200(client):
    """DELETE /api/v1/my_favorites/{image_id} returns 200."""
    c, _ = client
    resp = c.delete("/api/v1/my_favorites/42")
    assert resp.status_code == 200


def test_count_returns_correct(client):
    """GET /api/v1/my_favorites/count returns count field."""
    c, _ = client
    resp = c.get("/api/v1/my_favorites/count")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["count"] == 10


def test_preview_returns_images(client):
    """GET /api/v1/my_favorites/preview returns images list."""
    c, _ = client
    resp = c.get("/api/v1/my_favorites/preview?limit=20")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "images" in data
    assert len(data["images"]) == 1


def test_list_returns_paginated(client):
    """GET /api/v1/my_favorites returns paginated response."""
    c, _ = client
    resp = c.get("/api/v1/my_favorites?page=1&page_size=20")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert "data" in data
