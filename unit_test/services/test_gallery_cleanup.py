"""测试 GalleryService.cleanup_previews() 的核心逻辑（dry_run / 模式过滤 / 隐藏文件 / 错误隔离）"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

import pytest

from src.common.constant import CleanupMode
from src.dao.yande_data_dao import YandeDataRepository
from src.models.database.yande import YandeData
from src.services.gallery import GalleryService


def _make_fake_path_constant(previews_dir, originals_dir):
    """path_constant 是 frozen Pydantic 模型，用 duck-typed 替身绕过 setattr 限制"""
    return type("FakePathConstant", (), {
        "previews_dir": previews_dir,
        "originals_dir": originals_dir,
    })()


@pytest.fixture
def tmp_previews(tmp_path, monkeypatch):
    """将 services.gallery 和 image_cache 模块的 path_constant 重定向到 tmp_path/previews"""
    previews_dir = tmp_path / "previews"
    previews_dir.mkdir()
    originals_dir = tmp_path / "originals"
    import src.services.gallery as _gallery_module
    import src.infrastructure.image_cache as _ic_module
    fake_pc = _make_fake_path_constant(previews_dir, originals_dir)
    monkeypatch.setattr(_gallery_module, "path_constant", fake_pc)
    monkeypatch.setattr(_ic_module, "path_constant", fake_pc)
    return previews_dir


def _mk_image(directory: Path, name: str, size: int = 100):
    p = directory / name
    p.write_bytes(b"\x00" * size)
    return p


def _seed_db(downloaded_ids: list[int]):
    """在数据库里塞入 down_flag=True 的 ID"""
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


def test_parse_image_id_normal():
    assert GalleryService._parse_image_id("12345.jpg") == 12345
    assert GalleryService._parse_image_id("12345") == 12345
    assert GalleryService._parse_image_id("12345.png") == 12345


def test_parse_image_id_hidden_file_returns_none():
    assert GalleryService._parse_image_id(".DS_Store") is None
    assert GalleryService._parse_image_id(".gitkeep") is None


def test_parse_image_id_invalid_format_returns_none():
    assert GalleryService._parse_image_id("abc.jpg") is None
    assert GalleryService._parse_image_id("not_a_number") is None


def test_cleanup_local_dry_run_does_not_delete_files(tmp_previews):
    _seed_db([100, 200])
    _mk_image(tmp_previews, "100.jpg")
    _mk_image(tmp_previews, "200.jpg")
    _mk_image(tmp_previews, "300.jpg")

    result = GalleryService.cleanup_previews(
        mode=CleanupMode.CLEAN_LOCAL_PREVIEWS,
        dry_run=True,
    )

    assert result["matched"] == 2
    assert result["deleted"] == 0
    assert result["total_bytes"] == 200
    assert result["dry_run"] is True
    assert {p.name for p in tmp_previews.iterdir()} == {"100.jpg", "200.jpg", "300.jpg"}


def test_cleanup_local_real_delete_only_downloaded(tmp_previews):
    _seed_db([100, 200])
    p100 = _mk_image(tmp_previews, "100.jpg")
    p200 = _mk_image(tmp_previews, "200.jpg")
    p300 = _mk_image(tmp_previews, "300.jpg")

    result = GalleryService.cleanup_previews(
        mode=CleanupMode.CLEAN_LOCAL_PREVIEWS,
        dry_run=False,
    )

    assert result["matched"] == 2
    assert result["deleted"] == 2
    assert result["failed"] == 0
    assert not p100.exists()
    assert not p200.exists()
    assert p300.exists()


def test_cleanup_all_removes_everything_except_hidden(tmp_previews):
    _seed_db([])
    _mk_image(tmp_previews, "1.jpg")
    _mk_image(tmp_previews, "2.jpg")
    _mk_image(tmp_previews, ".DS_Store")

    result = GalleryService.cleanup_previews(
        mode=CleanupMode.CLEAN_ALL_PREVIEWS,
        dry_run=False,
    )

    assert result["matched"] == 2
    assert result["deleted"] == 2
    remaining = {p.name for p in tmp_previews.iterdir()}
    assert remaining == {".DS_Store"}


def test_cleanup_local_with_missing_dir_returns_empty(tmp_path, monkeypatch):
    import src.services.gallery as _gallery_module
    import src.infrastructure.image_cache as _ic_module
    nonexistent = tmp_path / "nope"
    fake_pc = _make_fake_path_constant(nonexistent, tmp_path / "originals")
    monkeypatch.setattr(_gallery_module, "path_constant", fake_pc)
    monkeypatch.setattr(_ic_module, "path_constant", fake_pc)
    result = GalleryService.cleanup_previews(
        mode=CleanupMode.CLEAN_LOCAL_PREVIEWS,
        dry_run=True,
    )
    assert result["matched"] == 0
    assert result["deleted"] == 0


def test_cleanup_local_continues_when_single_unlink_fails(tmp_previews, monkeypatch):
    _seed_db([100, 200, 300])
    _mk_image(tmp_previews, "100.jpg")
    _mk_image(tmp_previews, "200.jpg")
    _mk_image(tmp_previews, "300.jpg")

    def _selective_safe_unlink(self, path):
        if "200" in path.name:
            return False
        path.unlink()
        return True

    monkeypatch.setattr(
        "src.infrastructure.image_cache.ImageCache.safe_unlink",
        _selective_safe_unlink,
    )

    result = GalleryService.cleanup_previews(
        mode=CleanupMode.CLEAN_LOCAL_PREVIEWS,
        dry_run=False,
    )

    assert result["matched"] == 3
    assert result["deleted"] == 2
    assert result["failed"] == 1
