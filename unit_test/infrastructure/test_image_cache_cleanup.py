"""测试 ImageCache.list_preview_files() 和 safe_unlink() 的目录隔离行为。

注意：path_constant 是 frozen Pydantic 模型，无法直接 setattr。
改用 monkeypatch 替换 image_cache 模块命名空间中的 path_constant 引用，
让 ImageCache.__init__ 读取到 fake 对象的 previews_dir/originals_dir。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

import pytest

import src.infrastructure.image_cache as _ic_module
from src.infrastructure.image_cache import ImageCache


def _make_fake_path_constant(previews_dir: Path, originals_dir: Path):
    """构造一个简易 path_constant 替身：仅暴露 __init__ 读取的两个属性"""
    return type("FakePathConstant", (), {
        "previews_dir": previews_dir,
        "originals_dir": originals_dir,
    })()


@pytest.fixture
def tmp_previews(tmp_path, monkeypatch):
    """将 image_cache 模块中的 path_constant 替换为指向 tmp_path 的替身"""
    previews_dir = tmp_path / "previews"
    previews_dir.mkdir()
    originals_dir = tmp_path / "originals"
    fake_pc = _make_fake_path_constant(previews_dir, originals_dir)
    monkeypatch.setattr(_ic_module, "path_constant", fake_pc)
    return previews_dir


def _make_image(directory: Path, name: str, size_bytes: int = 100):
    """在 directory 下创建指定大小的占位文件"""
    p = directory / name
    p.write_bytes(b"\x00" * size_bytes)
    return p


def test_list_preview_files_returns_all_regular_files(tmp_previews):
    _make_image(tmp_previews, "123.jpg")
    _make_image(tmp_previews, "456.png")
    _make_image(tmp_previews, "789.webp")

    cache = ImageCache()
    files = cache.list_preview_files()
    names = {p.name for p in files}
    assert names == {"123.jpg", "456.png", "789.webp"}


def test_list_preview_files_skips_hidden_files(tmp_previews):
    _make_image(tmp_previews, "123.jpg")
    _make_image(tmp_previews, ".DS_Store")
    _make_image(tmp_previews, ".gitkeep")

    cache = ImageCache()
    files = cache.list_preview_files()
    names = {p.name for p in files}
    assert names == {"123.jpg"}


def test_list_preview_files_returns_empty_when_dir_missing(tmp_path, monkeypatch):
    missing = tmp_path / "nope"
    fake_pc = _make_fake_path_constant(missing, tmp_path / "originals")
    monkeypatch.setattr(_ic_module, "path_constant", fake_pc)
    cache = ImageCache()
    assert cache.list_preview_files() == []


def test_safe_unlink_removes_existing_file(tmp_previews):
    p = _make_image(tmp_previews, "del.jpg")
    cache = ImageCache()
    assert cache.safe_unlink(p) is True
    assert not p.exists()


def test_safe_unlink_returns_true_for_nonexistent_file(tmp_previews):
    cache = ImageCache()
    ghost = tmp_previews / "ghost.jpg"
    assert cache.safe_unlink(ghost) is True


def test_safe_unlink_returns_false_on_permission_error(tmp_previews, monkeypatch):
    """模拟 unlink 抛 OSError，验证返回 False 不抛异常"""
    p = _make_image(tmp_previews, "locked.jpg")

    def _raise_oserror(self):
        raise OSError("permission denied")

    monkeypatch.setattr("pathlib.Path.unlink", _raise_oserror)

    cache = ImageCache()
    assert cache.safe_unlink(p) is False
