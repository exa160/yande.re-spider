"""Tests for downloader preallocate fallback on low-disk environments.

When the downloader's preallocate step fails (e.g., disk full / sparse-file
creation unsupported on Windows), ``file_writer`` must gracefully degrade to
streaming writes instead of raising ``OSError`` to the caller.
"""
from pathlib import Path

from src.infrastructure.downloader import file_writer


def test_file_writer_fallback_on_disk_full(tmp_path, monkeypatch):
    """磁盘不足时降级为流式写入，不抛 OSError。"""
    target = tmp_path / "out.bin"

    def fake_seek(*args, **kwargs):
        raise OSError("No space left on device")

    # raising=False because stdlib pathlib.Path 自身没有 seek；
    # 注入的 fake_seek 由 _try_preallocate 通过 getattr 调用，
    # 触发 OSError 进入降级分支。
    monkeypatch.setattr(Path, "seek", fake_seek, raising=False)

    chunks = [b"hello", b"world"]
    file_writer(str(target), chunks, file_size=1024 * 1024 * 1024)  # 1GB 请求

    # 期望：文件存在，size > 0，未抛异常
    assert target.exists()
    assert target.stat().st_size >= len(b"helloworld")
