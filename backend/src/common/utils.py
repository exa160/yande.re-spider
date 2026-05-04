
from typing import Optional

from src.common.constant import path_constant
from src.common.settings import config


def get_proxy() -> Optional[dict]:
    if config.yande_api.proxy_enable:
        return config.yande_api.proxies.model_dump(mode="json")
    return None


def check_local_file(image_id: int, file_ext: str, file_type: str) -> Optional[str]:
    base = path_constant.previews_dir if file_type == "preview" else path_constant.originals_dir
    extensions = (
        ["jpg", "jpeg", "png", "gif", "webp"] if file_type == "preview" else [file_ext]
    )
    for ext in extensions:
        file_path = base / f"{image_id}.{ext}"
        if file_path.exists():
            return f"{image_id}.{ext}"
    return None