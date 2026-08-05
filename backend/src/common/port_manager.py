"""uvicorn 端口发现与端口文件协议。

PyWebView 主进程启动 uvicorn subprocess 时：
1. 主进程 find_free_port() → 端口号
2. 主进程 write_port_file(port_file, port)  → %APPDATA%/yande-spider/port
3. 启动 uvicorn subprocess，参数 --port <port>
4. uvicorn 健康检查通过后，主进程从 port_file 读端口，构造 PyWebView URL

uvicorn 自己不需要写端口文件（subprocess 启动参数已明确），但提供 helper
供测试和未来场景使用。
"""
from __future__ import annotations

import socket
from pathlib import Path
from typing import Optional


def find_free_port() -> int:
    """让 OS 分配一个空闲端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def write_port_file(port_file: Path, port: int) -> None:
    """写入端口号到端口文件。原子写：先临时文件后 rename。"""
    port_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = port_file.with_suffix(port_file.suffix + ".tmp")
    tmp.write_text(str(port), encoding="utf-8")
    tmp.replace(port_file)


def read_port_file(port_file: Path) -> Optional[int]:
    """读取端口号。文件不存在或内容无效返回 None。"""
    if not port_file.exists():
        return None
    try:
        return int(port_file.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None
