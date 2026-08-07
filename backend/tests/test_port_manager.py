import socket
from pathlib import Path

from src.common.port_manager import find_free_port, write_port_file, read_port_file


def test_find_free_port_returns_int():
    port = find_free_port()
    assert isinstance(port, int)
    assert 1024 < port < 65536


def test_port_file_roundtrip(tmp_path):
    port_file = tmp_path / "port"
    write_port_file(port_file, 12345)
    assert read_port_file(port_file) == 12345


def test_read_port_file_missing(tmp_path):
    assert read_port_file(tmp_path / "missing") is None


def test_read_port_file_corrupted(tmp_path):
    port_file = tmp_path / "port"
    port_file.write_text("not a number")
    assert read_port_file(port_file) is None
