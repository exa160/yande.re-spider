"""测试 POST /api/v1/gallery/cache/preview/cleanup 端点的请求校验 + dry_run + 真删行为

注：APILoader 自动给 gallery.py 加 v1/gallery 前缀，所以最终路径为
/api/v1/gallery/cache/preview/cleanup（与 spec §4.1 的 /api/v1/cache/... 不一致，
但与项目内其他 cache 路由约定一致）。
"""
import sys
from datetime import datetime
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[3] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import init_app, app_config
from src.common.constant import CleanupMode
from src.dao.yande_data_dao import YandeDataRepository
from src.models.database.yande import YandeData


def _make_fake_path_constant(previews_dir, originals_dir):
    """构造 path_constant fake，绕过 frozen 限制"""
    return type("FakePathConstant", (), {
        "previews_dir": previews_dir,
        "originals_dir": originals_dir,
    })()


@pytest.fixture
def tmp_previews(tmp_path, monkeypatch):
    """双模块 patch path_constant（services + image_cache），因为 ImageCache.__init__
    从 image_cache 模块的命名空间读取 path_constant"""
    previews_dir = tmp_path / "previews"
    previews_dir.mkdir()
    originals_dir = tmp_path / "originals"
    fake_pc = _make_fake_path_constant(previews_dir, originals_dir)

    import src.services.gallery as _g
    import src.infrastructure.image_cache as _ic
    monkeypatch.setattr(_g, "path_constant", fake_pc)
    monkeypatch.setattr(_ic, "path_constant", fake_pc)

    return previews_dir


@pytest.fixture
def client(tmp_previews):
    """FastAPI TestClient with dual-path-constant patch active"""
    test_app = FastAPI(**app_config.model_dump())
    init_app(test_app)
    return TestClient(test_app)


def _mk_image(directory: Path, name: str, size: int = 100):
    p = directory / name
    p.write_bytes(b"\x00" * size)
    return p


def _seed_db(downloaded_ids: list[int]):
    with YandeDataRepository() as repo:
        repo.session.query(YandeData).delete()
        for i in downloaded_ids:
            rec = YandeData(
                id=i,
                tags=f"t{i}",
                width=10, height=10,
                file_ext="jpg",
                file_size=100,
                file_url=f"http://x/{i}.jpg",
                preview_url=f"http://x/p_{i}.jpg",
                md5=f"m{i}",
                author="a",
                created_at=datetime(2024, 1, 1, 0, 0, 0),
                down_flag=True,
            )
            repo.session.add(rec)


def test_cleanup_local_dry_run_endpoint(client, tmp_previews):
    _seed_db([100, 200])
    _mk_image(tmp_previews, "100.jpg")
    _mk_image(tmp_previews, "200.jpg")

    resp = client.post(
        "/api/v1/gallery/cache/preview/cleanup",
        json={"mode": "clean_local_previews", "dry_run": True},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mode"] == "clean_local_previews"
    assert data["dry_run"] is True
    assert data["matched"] == 2
    assert data["deleted"] == 0
    # 文件未删
    assert {p.name for p in tmp_previews.iterdir()} == {"100.jpg", "200.jpg"}


def test_cleanup_local_real_delete_endpoint(client, tmp_previews):
    _seed_db([100])
    p = _mk_image(tmp_previews, "100.jpg")
    _mk_image(tmp_previews, "999.jpg")  # 不在 down_flag 中

    resp = client.post(
        "/api/v1/gallery/cache/preview/cleanup",
        json={"mode": "clean_local_previews", "dry_run": False},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["deleted"] == 1
    assert not p.exists()
    assert (tmp_previews / "999.jpg").exists()


def test_cleanup_all_endpoint(client, tmp_previews):
    _mk_image(tmp_previews, "1.jpg")
    _mk_image(tmp_previews, "2.jpg")
    _mk_image(tmp_previews, ".DS_Store")

    resp = client.post(
        "/api/v1/gallery/cache/preview/cleanup",
        json={"mode": "clean_all_previews", "dry_run": False},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["matched"] == 2
    assert data["deleted"] == 2
    # 隐藏文件保留
    assert {p.name for p in tmp_previews.iterdir()} == {".DS_Store"}


def test_cleanup_dry_run_defaults_to_true(client, tmp_previews):
    """dry_run 字段缺省时默认为 True（安全默认）"""
    _mk_image(tmp_previews, "1.jpg")

    resp = client.post(
        "/api/v1/gallery/cache/preview/cleanup",
        json={"mode": "clean_all_previews"},  # 不传 dry_run
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["dry_run"] is True
    assert data["deleted"] == 0
    assert (tmp_previews / "1.jpg").exists()


def test_cleanup_invalid_mode_returns_422(client):
    resp = client.post(
        "/api/v1/gallery/cache/preview/cleanup",
        json={"mode": "invalid_mode", "dry_run": True},
    )
    assert resp.status_code == 422
