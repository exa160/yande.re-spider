import os
from pathlib import Path
from typing import Optional

from loguru import logger
from pydantic import BaseModel


class ConfigModel(BaseModel, frozen=True):
    pass


class ProxiesConfig(ConfigModel):
    http: str = ''
    https: str = ''


class ApiConfig(ConfigModel):
    """
    api访问相关配置
    """
    retry: int = 3
    proxies: Optional[dict] = None
    headers: dict = {}


class DownloaderConfig(ConfigModel):
    thread_num: int = 4
    chunk_size: int = 10 * 1024
    split_size: int = 5 * 1024 * 1024


class MariaDBConfig(ConfigModel):
    enable: bool = False
    host: str = '127.0.0.1'
    port: str = '3306'
    user: str = ''
    password: str = ''
    schema_name: str = 'Pictures'
    datatable: str = 'YandeRE'


class Config(ConfigModel):
    database: MariaDBConfig = MariaDBConfig()
    yande_api: ApiConfig = ApiConfig()
    downloader: DownloaderConfig = DownloaderConfig()


def load_config(config_path: str = 'data.cfg'):
    """
    加载本地配置文件
    """
    _config = None

    if os.path.exists(config_path):
        with open(config_path, 'rb') as f:
            try:
                _config = Config.model_validate_json(f.read())
            except Exception as e:
                logger.warning(f'load cfg err: {e}')

    if _config is None:
        _config = Config().model_dump_json(indent=4)
        with open(config_path, 'w') as f:
            f.write(_config)

    return _config


config = load_config(str(Path(__file__).absolute().parent.parent / 'config' / 'data.cfg'))
