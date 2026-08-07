"""验证 _compute_file_md5 正确计算文件 MD5 + 整文件 MD5 在 to_thread 中执行

背景：原 run_download_async 在事件循环线程做整文件读取 + MD5，
大文件会冻住整个后端。修复后 MD5 计算通过 asyncio.to_thread 调度。
"""
import sys
import asyncio
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

import pytest


def test_compute_file_md5_returns_correct_hash(tmp_path):
    """_compute_file_md5 正确计算文件 MD5"""
    from src.infrastructure.download_queue import _compute_file_md5

    test_file = tmp_path / "test.bin"
    test_file.write_bytes(b"hello world")
    md5 = _compute_file_md5(test_file)
    assert md5 == hashlib.md5(b"hello world").hexdigest()


def test_compute_file_md5_returns_none_for_missing_file(tmp_path):
    """_compute_file_md5 对不存在文件返回 None"""
    from src.infrastructure.download_queue import _compute_file_md5

    md5 = _compute_file_md5(tmp_path / "does_not_exist")
    assert md5 is None


def test_compute_file_md5_handles_large_file(tmp_path):
    """_compute_file_md5 处理大文件（超过单 chunk 大小）"""
    from src.infrastructure.download_queue import _compute_file_md5

    test_file = tmp_path / "big.bin"
    # 3MB 数据，超过 1MB chunk
    data = b"\xab" * (3 * 1024 * 1024)
    test_file.write_bytes(data)
    md5 = _compute_file_md5(test_file)
    assert md5 == hashlib.md5(data).hexdigest()


def test_compute_file_md5_runs_in_thread(monkeypatch, tmp_path):
    """_compute_file_md5 在 to_thread 中执行时不在事件循环线程"""
    import threading
    from src.infrastructure.download_queue import _compute_file_md5

    test_file = tmp_path / "x.bin"
    test_file.write_bytes(b"x" * 100)

    main_thread_id = threading.get_ident()
    captured = {"thread_id": None}

    original_compute = _compute_file_md5

    def spy_compute(file_path):
        captured["thread_id"] = threading.get_ident()
        return original_compute(file_path)

    monkeypatch.setattr(
        "src.infrastructure.download_queue._compute_file_md5", spy_compute
    )

    async def runner():
        return await asyncio.to_thread(
            __import__("src.infrastructure.download_queue", fromlist=["_compute_file_md5"])._compute_file_md5,
            test_file,
        )

    md5 = asyncio.run(runner())
    assert md5 is not None
    assert captured["thread_id"] is not None
    assert captured["thread_id"] != main_thread_id, (
        "_compute_file_md5 必须在 to_thread 中执行（不在事件循环线程）"
    )
