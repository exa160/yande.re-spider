"""desktop.main 的最小测试：仅覆盖 wait_for_health HTTP 健康检查。

subprocess / PyWebView 窗口 / 托盘的行为不在单元测试范围内（开发模式手动验证）。
"""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from desktop.main import wait_for_health


class _HealthHandler(BaseHTTPRequestHandler):
    """对所有 GET 返回 200。"""

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args, **kwargs):  # noqa: D401, ARG002
        return  # 静默


@pytest.fixture
def health_server():
    """启动一个监听 18000 的 mock /health 服务器。"""
    server = HTTPServer(("127.0.0.1", 18000), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def test_wait_for_health_success(tmp_path: Path, health_server: HTTPServer) -> None:
    """健康检查在超时内成功返回 True。"""
    port_file = tmp_path / "port"
    port_file.write_text("18000", encoding="utf-8")

    result = wait_for_health(port_file, timeout=3.0)

    assert result is True


def test_wait_for_health_timeout(tmp_path: Path) -> None:
    """健康检查超时返回 False。"""
    port_file = tmp_path / "port"
    # 端口 1 几乎不会有进程监听（privileged），所以请求必失败
    port_file.write_text("1", encoding="utf-8")

    result = wait_for_health(port_file, timeout=1.0)

    assert result is False


def test_wait_for_health_missing_port_file(tmp_path: Path) -> None:
    """port_file 不存在时安全返回 False（不抛异常）。"""
    port_file = tmp_path / "no_such_file"

    result = wait_for_health(port_file, timeout=0.5)

    assert result is False


def test_wait_for_health_invalid_port_content(tmp_path: Path) -> None:
    """port_file 内容非数字时安全降级（轮询直到 timeout）。"""
    port_file = tmp_path / "port"
    port_file.write_text("not-a-port", encoding="utf-8")

    result = wait_for_health(port_file, timeout=0.5)

    assert result is False