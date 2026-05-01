
from typing import Optional

from src.common.settings import config


def get_proxy() -> Optional[dict]:
    if config.yande_api.proxy_enable:
        return config.yande_api.proxies.model_dump(mode="json")
    return None