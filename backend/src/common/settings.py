from functools import wraps
from pathlib import Path
from typing import Optional

import yaml
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from backend.src.common.constant import path_constant


class ConfigModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    @staticmethod
    def set_frozen_data_(func):
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
        user_agent: str = Field('', serialization_alias='User-Agent')
        accept: str = Field('', serialization_alias='Accept')
        accept_language: str = Field('', serialization_alias='Accept-Language')

    retry: int = Field(3, description='yandere失败重试')
    proxies: ProxiesConfig = ProxiesConfig()
    headers: Optional[Headers] = Field(Headers())


class DownloaderConfig(ConfigModel):
    thread_num: int = Field(4, description='切片最大线程')
    max_concurrent_tasks: int = Field(3, ge=1, le=8, description='最大同时下载数')
    chunk_size: int = Field(10 * 1024, ge=1024, description='最大同时下载数')
    split_size: int = Field(50 * 1024 * 1024, ge=5 * 1024 * 1024, description='最大同时下载数')


class MariaDBConfig(ConfigModel):
    enable: bool = Field(default=False)
    host: str = Field(default="localhost")
    port: int = Field(default=3306)
    user: str = Field(default="root")
    password: SecretStr = Field(default=SecretStr(""))
    schema_name: str = Field(default="Pictures")
    datatable: str = Field(default="YandeRE")


class Config(ConfigModel):
    database: MariaDBConfig = MariaDBConfig()
    yande_api: ApiConfig = ApiConfig()
    downloader: DownloaderConfig = DownloaderConfig()

    @ConfigModel.set_frozen_data_
    def update_config(self, config_model: MariaDBConfig | ApiConfig | DownloaderConfig):
        for config_name, config_data in self.__dict__.items():
            if isinstance(config_model, type(config_data)):
                self.__setattr__(config_name, config_model)
                break
        save_config(self, path_constant.config_file)


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


def save_config(_config: Config, config_path: Path = path_constant.config_file) -> None:
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
    return load_config(path_constant.config_file)


config = get_config()
