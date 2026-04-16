from functools import wraps
from pathlib import Path
from typing import Optional

import yaml
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from backend.src.common.constant import CONFIG_FILE


class ConfigModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    @staticmethod
    def _set_frozen_data(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            self.model_config['frozen'] = False
            f = func(self, *args, **kwargs)
            self.model_config['frozen'] = True
            return f
        return wrapper

class ApiConfig(ConfigModel):
    class ProxiesConfig(ConfigModel):
        http: str = ""
        https: str = ""

    class Headers(ConfigModel):
        user_agent: str = Field('', validation_alias='user-agent')
        accept: str = Field('', validation_alias='Accept')
        accept_language: str = Field('', validation_alias='Accept-Language')

    retry: int = 3
    proxies: ProxiesConfig = ProxiesConfig()
    headers: Optional[Headers] = Field(Headers())


class DownloaderConfig(ConfigModel):
    thread_num: int = 4
    max_concurrent_tasks: int = 3
    chunk_size: int = 10 * 1024
    split_size: int = 5 * 1024 * 1024


class MariaDBConfig(ConfigModel):
    enable: bool = Field(default=False)
    host: str = Field(default="localhost")
    port: int = Field(default=3306)
    user: str = Field(default="root")
    password: str = Field(default="")
    schema_name: str = Field(default="Pictures")
    datatable: str = Field(default="YandeRE")


class Config(ConfigModel):
    database: MariaDBConfig = MariaDBConfig()
    yande_api: ApiConfig = ApiConfig()
    downloader: DownloaderConfig = DownloaderConfig()


def load_config(config_path: Path = Path('config.yaml')) -> Config:
    if config_path.exists():
        try:
            data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            return Config.model_validate(data)
        except Exception as e:
            logger.warning(f"load config err: {e}")

    default_config = Config()
    save_config(default_config, config_path)
    return default_config


def save_config(_config: Config, config_path: Path = Path('config.yaml')) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.dump(
            _config.model_dump(),
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
    )


def get_config() -> Config:
    return load_config()


config = get_config()
