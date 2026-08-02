"""ConfigService.update_api_config 允许 headers 更新的测试。

覆盖:
1. update_api_config 接受新 headers(不再 exclude)
2. 调用后 src.common.config.yande_api.headers 被更新
3. 更新后的 headers 平铺到 YAML(无 extra_headers 键)
4. 其他字段(retry / timeout / proxy_enable)保留不变
"""
import yaml

from src.common import config as cfg_module
from src.common.constant import path_constant
from src.common.settings import (
    ApiConfig,
    Config,
    DatabaseConfig,
    DownloaderConfig,
    SchedulerConfig,
    save_config,
)


def _fresh_config() -> Config:
    return Config(
        database=DatabaseConfig(enable=False),
        yande_api=ApiConfig(retry=3, timeout=30, proxy_enable=False),
        downloader=DownloaderConfig(),
        scheduler=SchedulerConfig(),
    )


def _redirect_config_path(test_file):
    original = path_constant.config_file
    object.__setattr__(path_constant, "config_file", test_file)
    return original


def _restore_config_path(original):
    object.__setattr__(path_constant, "config_file", original)


def test_update_api_config_writes_headers(tmp_path):
    test_file = tmp_path / "config.yaml"
    save_config(_fresh_config(), test_file)
    original = _redirect_config_path(test_file)
    try:
        from src.services.config import ConfigService

        new_api_config = ApiConfig(
            retry=5,
            timeout=60,
            proxy_enable=False,
            headers={
                "User-agent": "UA-new",
                "Accept": "text/html",
                "Accept-Language": "zh-CN",
                "Authorization": "Bearer xxx",
            },
        )
        ConfigService.update_api_config(new_api_config)

        assert cfg_module.yande_api.headers.user_agent == "UA-new"
        extra = getattr(
            cfg_module.yande_api.headers, "__pydantic_extra__", None
        ) or {}
        assert extra.get("Authorization") == "Bearer xxx"

        yaml_data = yaml.safe_load(test_file.read_text())
        headers_section = yaml_data["yande_api"]["headers"]
        assert headers_section["User-agent"] == "UA-new"
        assert headers_section["Authorization"] == "Bearer xxx"
    finally:
        _restore_config_path(original)


def test_update_api_config_preserves_other_fields(tmp_path):
    test_file = tmp_path / "config.yaml"
    save_config(_fresh_config(), test_file)
    original = _redirect_config_path(test_file)
    try:
        from src.services.config import ConfigService

        new_api_config = ApiConfig(
            retry=10,
            timeout=120,
            proxy_enable=True,
            headers={"User-agent": "UA-new"},
        )
        ConfigService.update_api_config(new_api_config)

        assert cfg_module.yande_api.retry == 10
        assert cfg_module.yande_api.timeout == 120
        assert cfg_module.yande_api.proxy_enable is True
    finally:
        _restore_config_path(original)