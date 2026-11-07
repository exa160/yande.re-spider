"""MD5 校验开关回归测试。

背景：yande.re 少数 post 的 ``md5`` 字段与实际下发的文件字节不一致
（例如 1207570：下发文件底部被改动，实际 md5 与 post md5 永久对不上），
严格校验会让这类图片重试到失败。新增 ``downloader.verify_md5`` 开关：

- ``verify_md5=True``（默认）：MD5 不一致抛 ``MD5MismatchException``；
- ``verify_md5=False``：跳过校验，保留下载到的文件。
"""
import hashlib
from pathlib import Path
from queue import Queue
from threading import Event

import pytest

from src.common import config
from src.infrastructure.downloader import FileInfo, MD5MismatchException, MultiDown


def _write_file(tmp_path: Path, payload: bytes, name: str = "1.jpg") -> Path:
    target = tmp_path / name
    target.write_bytes(payload)
    return target


def _run_writer(tmp_path: Path, payload: bytes, expected_md5: str):
    """模拟下载器写盘 + 校验环节。"""
    data_q: Queue = Queue()
    data_q.put([0, len(payload), payload])
    close_event = Event()
    close_event.set()
    file_info = FileInfo(
        id=1,
        file_size=len(payload),
        file_name="1.jpg",
        file_path=tmp_path,
        md5=expected_md5,
        url="http://example.com/1.jpg",
    )
    MultiDown.file_writer(file_info, data_q, close_event)


@pytest.fixture
def set_verify():
    """download 配置是 frozen 模型，只能绕过 __setattr__ 临时改值，结束后还原。"""
    original = config.downloader.verify_md5

    def _apply(value: bool) -> None:
        object.__setattr__(config.downloader, "verify_md5", value)

    yield _apply
    object.__setattr__(config.downloader, "verify_md5", original)


def test_md5_mismatch_raises_when_verify_enabled(tmp_path, set_verify):
    """默认严格校验：字节与期望 md5 不一致 → 抛 MD5MismatchException"""
    set_verify(True)
    payload = b"yande-bytes"
    expected = "0" * 32

    with pytest.raises(MD5MismatchException):
        _run_writer(tmp_path, payload, expected)


def test_md5_mismatch_ignored_when_verify_disabled(tmp_path, set_verify):
    """关闭校验：同样的字节不再抛异常，文件原样保留"""
    set_verify(False)
    payload = b"yande-bytes"
    expected = "0" * 32

    _run_writer(tmp_path, payload, expected)

    written = (tmp_path / "1.jpg").read_bytes()
    assert written == payload
    assert hashlib.md5(written).hexdigest() != expected


def test_md5_match_still_passes_when_verify_disabled(tmp_path, set_verify):
    """关闭校验不会影响正常图片（md5 一致时同样正常落盘）"""
    set_verify(False)
    payload = b"perfect-bytes"
    expected = hashlib.md5(payload).hexdigest()

    _run_writer(tmp_path, payload, expected)

    assert (tmp_path / "1.jpg").read_bytes() == payload
