import threading
from functools import wraps
from pathlib import Path
from typing import ClassVar, Optional

import yaml
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_serializer

from src.common.constant import path_constant


class ConfigModel(BaseModel):
    model_config = ConfigDict(frozen=True)
    _lock: ClassVar[threading.Lock] = threading.Lock()

    @staticmethod
    def update_config_data(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            updates = func(self, *args, **kwargs)
            if updates:
                with self._lock:
                    new_instance = self.model_copy(update=updates)
                save_config(new_instance, path_constant.config_file)
                return new_instance
            return self
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


class CorsConfig(ConfigModel):
    allow_origins: list[str] = Field(default=["http://localhost:5173"], description='CORS允许的来源列表')
    allow_methods: list[str] = Field(default=["*"], description='CORS允许的HTTP方法')
    allow_headers: list[str] = Field(default=["*"], description='CORS允许的请求头')
    allow_credentials: bool = Field(default=True, description='是否允许携带凭证')


class Config(ConfigModel):
    app: AppConfig = AppConfig()
    database: DatabaseConfig = DatabaseConfig()
    yande_api: ApiConfig = ApiConfig()
    downloader: DownloaderConfig = DownloaderConfig()
    cors: CorsConfig = CorsConfig()

    @ConfigModel.update_config_data
    def update_config(self, config_model: DatabaseConfig | ApiConfig | DownloaderConfig | CorsConfig) -> dict:
        for config_name, config_data in self.__dict__.items():
            if isinstance(config_model, type(config_data)):
                logger.info(f"Updated config: {config_name}, new value: {config_model}")
                return {config_name: config_model}
        return {}


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
