"""验证 ImageCache 缩略图/原图下载显式传 timeout 参数

背景：requests.Session.get() 不读 self.timeout 属性，必须显式传 timeout=。
ImageCache.__init__ 之前设了 self._session.timeout = config.yande_api.timeout，
但 requests 库忽略此属性——只有 timeout= 关键字参数生效。

修复后每次 GET 调用都应带 timeout= 参数，避免慢 HTTP 连接无限挂起。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

import pytest

import src.infrastructure.image_cache as _ic_module


def _make_fake_path_constant(tmp_path):
    pc = type("FakePathConstant", (), {
        "previews_dir": tmp_path / "previews",
        "originals_dir": tmp_path / "originals",
    })()
    pc.previews_dir.mkdir()
    pc.originals_dir.mkdir()
    return pc


@pytest.fixture
def fake_path_constant(tmp_path, monkeypatch):
    pc = _make_fake_path_constant(tmp_path)
    monkeypatch.setattr(_ic_module, "path_constant", pc)
    return pc


def _make_fake_session(get_impl):
    """构造一个最小可用的 requests.Session 替身"""
    class FakeSession:
        proxies = {}

        def get(self, url, **kwargs):
            return get_impl(url, **kwargs)
    return FakeSession()


def test_download_preview_passes_timeout(fake_path_constant, monkeypatch):
    """download_preview 的 GET 调用必须带 timeout= 参数"""
    from src.infrastructure import image_cache as ic
    from src.infrastructure.image_cache import ImageCache

    captured = {}

    def fake_get(url, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("STOP_TEST")

    fake_api = type("FakeApi", (), {"timeout": 17, "retry": 1})()
    fake_config = type("FakeConfig", (), {"yande_api": fake_api})()
    monkeypatch.setattr(ic, "config", fake_config)

    cache = ImageCache()
    cache._session = _make_fake_session(fake_get)

    with pytest.raises(RuntimeError, match="STOP_TEST"):
        cache.download_preview(123, "jpg")

    assert "timeout" in captured, "ImageCache.get() must pass timeout="
    assert captured["timeout"] == 17, (
        f"timeout 应等于 config.yande_api.timeout (17), 实际 {captured.get('timeout')}"
    )


def test_download_original_passes_timeout(fake_path_constant, monkeypatch):
    """download_original 的 GET 调用也必须带 timeout= 参数"""
    from src.infrastructure import image_cache as ic
    from src.infrastructure.image_cache import ImageCache

    captured = {}

    def fake_get(url, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("STOP_TEST")

    fake_api = type("FakeApi", (), {"timeout": 23, "retry": 1})()
    fake_config = type("FakeConfig", (), {"yande_api": fake_api})()
    monkeypatch.setattr(ic, "config", fake_config)

    cache = ImageCache()
    cache._session = _make_fake_session(fake_get)

    with pytest.raises(RuntimeError, match="STOP_TEST"):
        cache.download_original(456, "jpg")

    assert captured.get("timeout") == 23
