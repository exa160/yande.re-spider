import os
from pathlib import Path
from typing import Optional

from loguru import logger
from pydantic import BaseModel


class ConfigModel(BaseModel, frozen=True):
    pass


class ProxiesConfig(ConfigModel):
    http: str = ""
    https: str = ""


class ApiConfig(ConfigModel):
    retry: int = 3
    proxies: Optional[dict] = None
    headers: dict = {}


class DownloaderConfig(ConfigModel):
    thread_num: int = 4
    chunk_size: int = 10 * 1024
    split_size: int = 5 * 1024 * 1024


class MariaDBConfig(ConfigModel):
    enable: bool = False
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = ""
    password: str = ""
    schema_name: str = "Pictures"
    datatable: str = "YandeRE"


class Config(ConfigModel):
    database: MariaDBConfig = MariaDBConfig()
    yande_api: ApiConfig = ApiConfig()
    downloader: DownloaderConfig = DownloaderConfig()


def load_config(config_path: str = "data.cfg") -> Config:
    if os.path.exists(config_path):
        with open(config_path, "rb") as f:
            try:
                return Config.model_validate_json(f.read())
            except Exception as e:
                logger.warning(f"load cfg err: {e}")

    default_config = Config()
    with open(config_path, "w") as f:
        f.write(default_config.model_dump_json(indent=4))

    return default_config


def get_config() -> Config:
    config_path = Path(__file__).parent.parent.parent / "config" / "data.cfg"
    return load_config(str(config_path))


config = get_config()
