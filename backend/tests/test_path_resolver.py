import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.common.path_resolver import resolve_install_dir, resolve_user_config_dir, is_frozen


def test_is_frozen_false_in_dev():
    with patch.object(sys, "frozen", "", create=True):
        assert is_frozen() is False


def test_is_frozen_true_in_pyinstaller():
    with patch.object(sys, "frozen", "true", create=True):
        with patch.object(sys, "_MEIPASS", "/tmp/_MEIPASS", create=True):
            assert is_frozen() is True


def test_resolve_install_dir_dev_mode(tmp_path):
    """开发模式：install_dir = base_dir（仓库根）"""
    fake_repo = tmp_path / "repo"
    fake_src = fake_repo / "backend" / "src" / "common"
    fake_src.mkdir(parents=True)
    fake_file = fake_src / "constant.py"
    fake_file.touch()

    with patch("src.common.path_resolver.PathConstant.base_dir", fake_repo):
        assert resolve_install_dir() == fake_repo


def test_resolve_install_dir_frozen(tmp_path):
    """PyInstaller 环境：install_dir = sys._MEIPASS 的父目录"""
    fake_mei = tmp_path / "_MEIPASS"
    fake_mei.mkdir()
    fake_exe_parent = fake_mei.parent

    with patch.object(sys, "frozen", "true", create=True):
        with patch.object(sys, "_MEIPASS", str(fake_mei), create=True):
            assert resolve_install_dir() == fake_exe_parent


def test_resolve_user_config_dir_windows(tmp_path):
    """Windows：%APPDATA%\\yande-spider"""
    fake_appdata = tmp_path / "AppData" / "Roaming"
    with patch("os.name", "nt"):
        with patch.dict(os.environ, {"APPDATA": str(fake_appdata)}):
            result = resolve_user_config_dir()
            assert result == fake_appdata / "yande-spider"


def test_resolve_user_config_dir_posix(tmp_path):
    """POSIX 开发模式：~/.config/yande-spider"""
    fake_home = tmp_path / "home"
    with patch("os.name", "posix"):
        with patch.dict(os.environ, {"HOME": str(fake_home)}):
            result = resolve_user_config_dir()
            assert result == fake_home / ".config" / "yande-spider"
