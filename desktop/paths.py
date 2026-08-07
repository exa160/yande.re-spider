"""桌面端路径解析（独立于 backend，避免循环依赖）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def get_install_dir() -> Path:
    """安装目录。frozen 时取 ``sys._MEIPASS`` 父目录（PyInstaller 解压根）。"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_user_config_dir() -> Path:
    """用户配置目录。Windows 取 ``%APPDATA%/yande-spider``；其他系统取 ``~/.config/yande-spider``。"""
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(appdata) / "yande-spider"
    return Path.home() / ".config" / "yande-spider"


def get_icon_path(install_dir: Path) -> Path:
    """图标路径。frozen 时从 ``_internal/desktop/icon.ico`` 取；开发模式取 ``desktop/icon.ico``。"""
    if getattr(sys, "frozen", False):
        return install_dir / "_internal" / "desktop" / "icon.ico"
    return Path(__file__).resolve().parent / "icon.ico"