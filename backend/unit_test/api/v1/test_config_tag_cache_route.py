"""/api/v1/config/tag-cache 端点 + tag_cache 配置段的读写

覆盖：
1. GET  /config/tag-cache  返回当前配置
2. PUT  /config/tag-cache  持久化 + 触发定时任务重挂
3. 非法 cron → 422（写不进配置）
4. POST /config/reset?section=tag_cache 支持重置该段
"""
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.common.settings import Config, TagCacheConfig


@pytest.fixture
def client(tmp_path, monkeypatch):
    """最小 FastAPI app + config 路由；配置落盘到 tmp_path。

    必须 patch ``src.common.settings.path_constant``：``update_config`` / ``save_config``
    是在函数体内读 ``path_constant.config_file``，而 path_constant 是 frozen model
    改不了，只能整体替换这个模块级名字。不 patch 会写到真实用户配置目录。
    """
    from types import SimpleNamespace

    from src.api.v1.config import router as config_router
    from src.common.settings import save_config
    from src.common import config as config_module

    cfg_path = tmp_path / "config.yaml"
    save_config(config_module, cfg_path)
    monkeypatch.setattr(
        "src.common.settings.path_constant",
        SimpleNamespace(config_file=cfg_path),
    )

    app = FastAPI()
    app.include_router(config_router, prefix="/api/v1/config")

    reload_calls = []
    import src.lifecycle.scheduler as lifecycle

    monkeypatch.setattr(
        lifecycle.SchedulerLifecycle,
        "reload_tag_cache_schedule",
        staticmethod(lambda: reload_calls.append(1)),
    )
    with TestClient(app) as c:
        yield c, reload_calls


def test_get_tag_cache_config(client):
    c, _ = client
    resp = c.get("/api/v1/config/tag-cache")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "enable_daily_refresh" in data
    assert "refresh_cron" in data
    assert "batch_limit" in data


def test_put_tag_cache_config_persists_and_reloads_schedule(client):
    c, reload_calls = client
    resp = c.put(
        "/api/v1/config/tag-cache",
        json={
            "enable_daily_refresh": False,
            "refresh_cron": "30 5 * * *",
            "batch_limit": 250,
        },
    )
    assert resp.status_code == 200
    # 保存后应触发定时任务重挂（免重启生效）
    assert reload_calls == [1]

    # 回读确认落库
    data = c.get("/api/v1/config/tag-cache").json()["data"]
    assert data["enable_daily_refresh"] is False
    assert data["refresh_cron"] == "30 5 * * *"
    assert data["batch_limit"] == 250


def test_put_rejects_invalid_cron(client):
    c, reload_calls = client
    resp = c.put(
        "/api/v1/config/tag-cache",
        json={"enable_daily_refresh": True, "refresh_cron": "not a cron", "batch_limit": 100},
    )
    assert resp.status_code == 422
    # 校验失败不应触发重挂
    assert reload_calls == []


def test_reset_tag_cache_section(client):
    c, _ = client
    c.put(
        "/api/v1/config/tag-cache",
        json={"enable_daily_refresh": False, "refresh_cron": "30 5 * * *", "batch_limit": 7},
    )
    resp = c.post("/api/v1/config/reset", params={"section": "tag_cache"})
    assert resp.status_code == 200
    data = c.get("/api/v1/config/tag-cache").json()["data"]
    assert data == TagCacheConfig().model_dump()


def test_config_model_has_tag_cache_section():
    assert Config().tag_cache.enable_daily_refresh is True
