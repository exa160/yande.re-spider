"""PyWebView 主入口。

启动序列：
1. 单实例锁
2. 加载 icon
3. 启动 uvicorn subprocess（注入 YANDE_PORT 环境变量）
4. 等待 /health 通过
5. 创建 PyWebView 窗口加载 http://127.0.0.1:<port>/
6. 启动系统托盘
7. 阻塞运行
8. 退出：关闭托盘 → 终止 subprocess
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import requests
import webview
from loguru import logger

from desktop.paths import get_icon_path, get_install_dir, get_user_config_dir
from desktop.single_instance import SingleInstanceError, acquire_lock
from desktop.tray import SystemTray

HEALTH_TIMEOUT = 30.0
HEALTH_INTERVAL = 0.2


def wait_for_health(port_file: Path, timeout: float = HEALTH_TIMEOUT) -> bool:
    """阻塞等待 uvicorn ``/health`` 通过。

    读取 ``port_file`` 获取端口号（uvicorn 启动后写入），每 ``HEALTH_INTERVAL``
    秒探测一次直到 ``/health`` 返回 200 或超过 ``timeout``。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_file.exists():
            try:
                port = int(port_file.read_text(encoding="utf-8").strip())
                resp = requests.get(f"http://127.0.0.1:{port}/health", timeout=1.0)
                if resp.status_code == 200:
                    logger.info(f"Health check passed on port {port}")
                    return True
            except (ValueError, requests.RequestException):
                pass
        time.sleep(HEALTH_INTERVAL)
    return False


def start_uvicorn_subprocess(install_dir: Path) -> subprocess.Popen:
    """启动 uvicorn subprocess，端口由 OS 分配（``YANDE_PORT=0``）。

    frozen 时从 ``_internal/`` 找 python.exe；开发模式直接用 ``sys.executable``。
    """
    env = os.environ.copy()
    env["YANDE_HOST"] = "127.0.0.1"
    env["YANDE_PORT"] = "0"  # OS auto-allocate
    env["PYTHONPATH"] = str(install_dir / "_internal" / "backend")

    if getattr(sys, "frozen", False):
        # frozen: yande-spider.exe 与 _internal/ 同级，python 解释器在 _internal/python.exe
        python_exe = install_dir / "_internal" / "python.exe"
        cwd = install_dir / "_internal" / "backend"
    else:
        python_exe = sys.executable
        cwd = Path(__file__).resolve().parent.parent / "backend"

    service_module = "service"
    cmd = [str(python_exe), "-m", "uvicorn", f"{service_module}:main_app"]
    logger.info(f"Starting uvicorn: {cmd} (cwd={cwd})")
    return subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def _terminate_proc(proc: subprocess.Popen) -> None:
    """优雅终止 subprocess（先 SIGTERM，超时后 SIGKILL）。"""
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> int:
    """主入口。"""
    try:
        acquire_lock()
    except SingleInstanceError as e:
        logger.error(str(e))
        return 1

    install_dir = get_install_dir()
    user_config_dir = get_user_config_dir()
    user_config_dir.mkdir(parents=True, exist_ok=True)
    port_file = user_config_dir / "port"

    proc = start_uvicorn_subprocess(install_dir)

    if not wait_for_health(port_file):
        logger.error("Uvicorn failed to start within timeout.")
        _terminate_proc(proc)
        return 2

    port = int(port_file.read_text(encoding="utf-8").strip())
    url = f"http://127.0.0.1:{port}"

    icon_path = get_icon_path(install_dir)
    window = webview.create_window(
        title="Yande Spider",
        url=url,
        width=1280,
        height=800,
        resizable=True,
    )

    def on_closing() -> None:
        logger.info("PyWebView closing, terminating uvicorn.")
        _terminate_proc(proc)

    window.events.closing += on_closing

    tray: SystemTray | None = None

    def on_tray_quit() -> None:
        window.destroy()

    try:
        tray = SystemTray(
            icon_path=icon_path,
            title="Yande Spider",
            url=url,
            on_quit=on_tray_quit,
            window=window,
        )
        tray.start()
        webview.start()
    finally:
        if tray is not None:
            tray.stop()
        _terminate_proc(proc)

    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    sys.exit(main())