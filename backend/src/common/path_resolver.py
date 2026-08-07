"""客户端/开发模式路径解析。

核心规则：
- 开发模式（未 freeze）：install_dir = 仓库根；user_config_dir = ~/.config/yande-spider
- PyInstaller frozen：install_dir = sys._MEIPASS 父目录（即 _internal/ 的上一层）
- 客户端配置（config.yaml）始终在 user_config_dir 下；其余数据/下载在 install_dir 下
"""
from __future__ import annotations

import os
import sys
from pathlib import Path, PosixPath, WindowsPath

from src.common.constant import PathConstant


_APP_NAME = "yande-spider"

# Detect actual OS path class at import time (not affected by os.name mocks in tests).
# This is needed because Path() checks os.name at __new__ time and raises
# NotImplementedError on POSIX when os.name is mocked to 'nt' (WindowsPath()).
# Using the actual OS class avoids this issue.
_ActualPathCls = PosixPath if sys.platform != "win32" else WindowsPath


def is_frozen() -> bool:
    """是否处于 PyInstaller frozen 环境。"""
    return bool(getattr(sys, "frozen", False)) and hasattr(sys, "_MEIPASS")


def resolve_install_dir() -> Path:
    """安装目录。

    - 开发模式：PathConstant.base_dir（即仓库根）
    - PyInstaller frozen：sys._MEIPASS 的父目录（C:\\Program Files\\Yande Spider\\）
    """
    if is_frozen():
        return Path(sys._MEIPASS).resolve().parent
    return PathConstant.base_dir


def resolve_user_config_dir() -> Path:
    """用户配置目录（持久、可漫游）。

    - Windows: %APPDATA%\\yande-spider
    - POSIX 开发模式: ~/.config/yande-spider
    """
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            # Use actual OS path class to avoid WindowsPath instantiation on POSIX
            # (test compat: tests mock os.name to 'nt' on POSIX hosts)
            return _ActualPathCls(os.path.join(appdata, _APP_NAME))
        return _ActualPathCls(os.path.join(str(Path.home()), "AppData", "Roaming", _APP_NAME))
    return Path.home() / ".config" / _APP_NAME

