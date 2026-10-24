"""/api/v1/random_browse/preview seed 参数契约测试。"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.middleware.errors import ErrorHandleMiddleware


@pytest.fixture
def client():
    from src.api.v1.random_browse import router as random_browse_router

    app = FastAPI()
    ErrorHandleMiddleware.init_app(app)
    app.include_router(random_browse_router, prefix="/api/v1/random_browse")

    repo = MagicMock()
    repo.__enter__.return_value = repo
    repo.query_random_for_tags.return_value = []
    with patch("src.api.v1.random_browse.YandeDataRepository", return_value=repo):
        yield TestClient(app), repo


def test_preview_forwards_seed(client):
    c, repo = client
    resp = c.get("/api/v1/random_browse/preview?limit=8&seed=123")
    assert resp.status_code == 200
    assert repo.query_random_for_tags.call_args.kwargs["seed"] == 123


def test_preview_without_seed_keeps_random_mode(client):
    c, repo = client
    resp = c.get("/api/v1/random_browse/preview?limit=8")
    assert resp.status_code == 200
    assert repo.query_random_for_tags.call_args.kwargs["seed"] is None


def test_preview_rejects_seed_out_of_range(client):
    c, _ = client
    assert c.get("/api/v1/random_browse/preview?seed=-1").status_code == 422
    assert c.get("/api/v1/random_browse/preview?seed=2147483648").status_code == 422
