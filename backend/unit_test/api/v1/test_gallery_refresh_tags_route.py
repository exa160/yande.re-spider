"""POST /gallery/image/{id}/refresh-tags 路由契约。

只 mock GalleryService，验证：
1. 路由把 image_id 传给 service，返回 200 + BaseResponse.data
2. service 抛 APIException 时保留业务错误码（tagme 守卫 / 远端不存在）
"""
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.common.constant import ErrMsg
from src.middleware.errors import APIException, ErrorHandleMiddleware
from src.services.gallery import GalleryService


@pytest.fixture
def client():
    from src.api.v1.gallery import router

    app = FastAPI()
    ErrorHandleMiddleware.init_app(app)
    app.include_router(router, prefix="/api/v1/gallery")

    with patch.object(GalleryService, "refresh_image_tags") as mock_service:
        yield TestClient(app), mock_service


def test_refresh_tags_route_success(client):
    c, mock_service = client
    mock_service.return_value = {
        "image_id": 42,
        "tags": ["new", "old"],
        "added": ["new"],
        "removed": ["tagme"],
        "changed": True,
        "still_tagme": False,
    }

    resp = c.post("/api/v1/gallery/image/42/refresh-tags")

    assert resp.status_code == 200
    mock_service.assert_called_once_with(42)
    assert resp.json()["data"] == mock_service.return_value


def test_refresh_tags_route_preserves_not_allowed_error(client):
    c, mock_service = client
    mock_service.side_effect = APIException(ErrMsg.IMAGE_TAG_REFRESH_NOT_ALLOWED)

    resp = c.post("/api/v1/gallery/image/42/refresh-tags")

    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == ErrMsg.IMAGE_TAG_REFRESH_NOT_ALLOWED.code
    assert "tagme" in body["message"]


def test_refresh_tags_route_preserves_remote_not_found(client):
    c, mock_service = client
    mock_service.side_effect = APIException(ErrMsg.REMOTE_IMAGE_NOT_FOUND)

    resp = c.post("/api/v1/gallery/image/42/refresh-tags")

    assert resp.status_code == 404
    assert resp.json()["code"] == ErrMsg.REMOTE_IMAGE_NOT_FOUND.code
