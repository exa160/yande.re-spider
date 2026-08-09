"""Windows 单实例锁（避免重复启动托盘）。

策略：尝试绑定固定端口 ``47299``；失败说明已有实例在运行。
锁通过进程句柄持有，进程退出时 OS 自动释放。
"""
from __future__ import annotations

import socket

LOCK_PORT = 47299


class SingleInstanceError(RuntimeError):
    """已有实例在运行时抛出。"""


def acquire_lock(lock_port: int = LOCK_PORT) -> socket.socket:
    """尝试绑定 ``lock_port``；失败说明已有实例在运行。

    返回的 socket 必须由调用方持有（持有期间保持单实例锁）。
    进程退出时 OS 会自动释放端口。
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", lock_port))
        sock.listen(1)
        return sock
    except OSError as e:
        sock.close()
        raise SingleInstanceError(
            f"Another instance is already running (lock port {lock_port} busy)."
        ) from e