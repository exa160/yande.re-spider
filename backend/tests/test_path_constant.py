"""PathConstant 部署模式与配置路径测试。

验证：PathConstant 在实例化时立刻解析 YANDE_USER_CONFIG_DIR 环境变量，
无须手动 _resolve_paths() 也能正确读取 Docker / 自定义部署的配置路径。
"""
import importlib
import os
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def reload_constant():
    """重新加载 constant 模块，让模块级 path_constant 单例用当前 env 重建。

    ⚠️ 必须在 teardown 时把模块 **reload 回原始状态**。
    ``importlib.reload(constant_mod)`` 会就地重建该模块里的所有类对象
    （含 ``ErrMsg`` / ``Rating`` / ``TaskStatus`` 等枚举）。其他测试模块若已
    ``from src.common.constant import ErrMsg`` 并持有**旧类对象**引用，
    reload 之后新旧枚举身份不一致 → 后续 ``ErrorResponse.model_dump(mode="json")``
    校验失败，报 "Object of type ErrMsg is not JSON serializable"。

    该污染与本用例无关，但会让**同一进程内后续的 API 路由测试**随机失败
    （表现为全量 pytest 失败、单跑该文件却通过）。这里做二次 reload 复位，
    使 reload 对进程内其他模块透明。
    """
    import src.common.constant as constant_mod

    def _reload():
        importlib.reload(constant_mod)
        return constant_mod

    yield _reload

    # 复位：把模块恢复到「本夹具介入前」的状态——此时环境变量已还原，
    # 再 reload 一次即可让单例按当前（干净的）env 重建。
    importlib.reload(constant_mod)


def test_resolve_user_config_dir_env_override_posix():
    """YANDE_USER_CONFIG_DIR 环境变量优先于 POSIX 默认 ~/.config/yande-spider。"""
    from src.common.constant import _resolve_user_config_dir

    with patch("os.name", "posix"):
        with patch.dict(os.environ, {"YANDE_USER_CONFIG_DIR": "/app/config"}):
            assert _resolve_user_config_dir() == Path("/app/config")


def test_resolve_user_config_dir_env_override_beats_windows():
    """YANDE_USER_CONFIG_DIR 在 Windows 下同样生效（不会回退到 APPDATA）。"""
    from src.common.constant import _resolve_user_config_dir

    with patch("os.name", "nt"):
        with patch.dict(
            os.environ,
            {"YANDE_USER_CONFIG_DIR": "/docker/cfg", "APPDATA": "/fake/appdata"},
        ):
            assert str(_resolve_user_config_dir()) == "/docker/cfg"


def test_resolve_user_config_dir_windows_uses_appdata():
    """Windows 默认：%APPDATA%\\yande-spider。"""
    from src.common.constant import _resolve_user_config_dir

    with patch("os.name", "nt"):
        with patch.dict(os.environ, {"APPDATA": "/appdata"}, clear=False):
            # 用 str 比较避开 WindowsPath 在 POSIX mock 时的 NotImplementedError
            assert str(_resolve_user_config_dir()).endswith("/appdata/yande-spider")


def test_resolve_user_config_dir_posix_uses_home_config():
    """POSIX 默认：~/.config/yande-spider。"""
    from src.common.constant import _resolve_user_config_dir

    with patch("os.name", "posix"):
        with patch.dict(os.environ, {"HOME": "/fake/home"}, clear=False):
            assert _resolve_user_config_dir() == Path("/fake/home/.config/yande-spider")


def test_path_constant_module_singleton_reflects_env(reload_constant):
    """PathConstant 模块级单例 path_constant 在 import 时立即读 env。

    覆盖 Docker 部署场景：容器启动时 YANDE_USER_CONFIG_DIR 已在环境里，
    Python 进程启动 → constant.py 加载 → path_constant = PathConstant()
    → _resolve_user_config_dir() 立刻读 env → user_config_dir 正确，
    后续 config = get_config() 用对的 config_file，不会写到错位置。

    YANDE_USER_CONFIG_DIR 语义：用户配置**根**目录（其下还有 config/ 子目录）。
    Docker 设 /app → config_file = /app/config/config.yaml（对齐 ./config 挂载）。
    """
    with patch.dict(os.environ, {"YANDE_USER_CONFIG_DIR": "/app"}):
        constant_mod = reload_constant()
        assert constant_mod.path_constant.user_config_dir == Path("/app")
        assert constant_mod.path_constant.config_file == Path("/app/config/config.yaml")
        assert constant_mod.path_constant.port_file == Path("/app/port")