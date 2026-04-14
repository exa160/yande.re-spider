import yaml
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


def load_config(config_path: str = "data.yaml") -> Config:
    config_path = Path(config_path)
    cfg_path = config_path.with_suffix(".cfg")

    if config_path.exists():
        try:
            config_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if config_data:
                return Config.model_validate(config_data)
        except yaml.YAMLError as e:
            logger.error(f"YAML parsing error in {config_path}: {e}")
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")

    if cfg_path.exists():
        try:
            import json

            config_data = json.loads(cfg_path.read_text(encoding="utf-8"))
            if config_data:
                cfg_config = Config.model_validate(config_data)
                try:
                    config_path.parent.mkdir(parents=True, exist_ok=True)
                    config_path.write_text(
                        yaml.dump(
                            cfg_config.model_dump(),
                            default_flow_style=False,
                            allow_unicode=True,
                            sort_keys=False,
                        ),
                        encoding="utf-8",
                    )
                    logger.info(f"Migrated config from JSON to YAML: {config_path}")
                except Exception as e:
                    logger.error(f"Failed to save migrated config: {e}")
                return cfg_config
        except Exception as e:
            logger.error(f"Failed to load config from {cfg_path}: {e}")

    logger.warning(
        f"Config file not found or invalid, creating default config at {config_path}"
    )
    default_config = Config()

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            yaml.dump(
                default_config.model_dump(),
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        logger.info(f"Default configuration saved to {config_path}")
    except Exception as e:
        logger.error(f"Failed to save default config: {e}")

    return default_config


def get_config() -> Config:
    config_path = Path(__file__).parent.parent.parent / "config" / "data.yaml"
    return load_config(str(config_path))


config = get_config()
