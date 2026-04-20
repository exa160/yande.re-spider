from pathlib import Path
from typing import Optional

import yaml
from loguru import logger
from pydantic import BaseModel

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


class ConfigModel(BaseModel, frozen=True):
    ...
    def _set_forzen_data(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            self.model_config['frozen'] = False
            f = func(self, *args, **kwargs)
            self.model_config['frozen'] = True
            return f
        return wrapper


class ProxiesConfig(ConfigModel):
    http: str = ""
    https: str = ""


class ApiConfig(ConfigModel):
    retry: int = 3
    proxies: Optional[dict] = None
    headers: dict = {}


class DownloaderConfig(ConfigModel):
    thread_num: int = 4
    max_concurrent_tasks: int = 3
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


def load_config(config_path: Path = CONFIG_FILE) -> Config:
    if config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return Config.model_validate(data)
        except Exception as e:
            logger.warning(f"load config err: {e}")

    default_config = Config()
    save_config(default_config, config_path)
    return default_config


def save_config(config: Config, config_path: Path = CONFIG_FILE) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as f:
        yaml.dump(
            config.model_dump(),
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )


def get_config() -> Config:
    return load_config()


config = get_config()
