from functools import wraps
from pathlib import Path
from typing import Optional

import yaml
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_serializer

from src.common.constant import path_constant


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
        user_agent: str = Field('', serialization_alias='User-agent')
        accept: str = Field('', serialization_alias='Accept')
        accept_language: str = Field('', serialization_alias='Accept-Language')

    proxy_enable: bool = Field(default=False)
    proxies: ProxiesConfig = ProxiesConfig()
    timeout: int = Field(default=30)
    retry: int = Field(3, description='yandere失败重试')
    headers: Optional[Headers] = Field(Headers())


class DownloaderConfig(ConfigModel):
    thread_num: int = Field(4, description='切片最大线程')
    max_concurrent_tasks: int = Field(3, ge=1, le=8, description='最大同时下载数')
    chunk_size: int = Field(10 * 1024, ge=1024, description='最大同时下载数')
    split_size: int = Field(50 * 1024 * 1024, ge=5 * 1024 * 1024, description='最大同时下载数')
    retry_times: int = Field(default=3, ge=0, le=50, description='最大重试次数')


class SchedulerConfig(ConfigModel):
    max_concurrent_schedules: int = Field(2, ge=1, le=10, description="同时抓取的收藏夹数")
    max_images_per_run_default: int = Field(200, ge=1, description="单收藏夹单次拉取上限兜底")
    max_pages_per_run: int = Field(5, ge=1, le=20, description="单收藏夹单次分页上限兜底")


class DatabaseConfig(ConfigModel):
    enable: bool = Field(default=False)
    host: str = Field(default="localhost")
    port: int = Field(default=3306)
    user: str = Field(default="root")
    password: SecretStr = Field(default=SecretStr(""))
    schema_name: str = Field(default="Pictures")

    @field_serializer('password', when_used="json")
    def serialize_password(self, password: SecretStr) -> str:
        return password.get_secret_value()


class AppConfig(ConfigModel):
    debug: bool = Field(default=False, description='开启时接口返回完整错误信息')


class Config(ConfigModel):
    app: AppConfig = AppConfig()
    database: DatabaseConfig = DatabaseConfig()
    yande_api: ApiConfig = ApiConfig()
    downloader: DownloaderConfig = DownloaderConfig()
    scheduler: SchedulerConfig = SchedulerConfig()

    @ConfigModel.set_frozen_data_
    def update_config(self, config_model: DatabaseConfig | ApiConfig | DownloaderConfig | SchedulerConfig):
        for config_name, config_data in self.__dict__.items():
            logger.info(f"{isinstance(config_model, type(config_data))}， Checking config: {config_name}, type: {type(config_data)}, new type: {type(config_model)}")
            if isinstance(config_model, type(config_data)):
                self.__setattr__(config_name, config_model)
                logger.info(f"Updated config: {config_name}, new value: {config_model}")
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
            _config.model_dump(mode="json"),
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8"
    )


def get_config() -> Config:
    return load_config(path_constant.config_file)


config = get_config()
