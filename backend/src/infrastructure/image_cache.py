from pathlib import Path
from typing import Optional, Tuple

import requests
from loguru import logger

from src.common import config, path_constant
from src.common.utils import get_proxy


class ImageCache:
    def __init__(self):
        self.PREVIEWS_DIR = path_constant.previews_dir
        self.ORIGINALS_DIR = path_constant.originals_dir

    def _ensure_dirs(self):
        self.PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)
        self.ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)

    def get_preview_path(self, image_id: int, file_ext: str = "jpg") -> Path:
        return self.PREVIEWS_DIR / f"{image_id}.{file_ext}"

    def get_original_path(self, image_id: int, file_ext: str = "jpg") -> Path:
        return self.ORIGINALS_DIR / f"{image_id}.{file_ext}"

    def get_preview_url(self, image_id: int, file_ext: str = "jpg") -> str:
        preview_path = self.get_preview_path(image_id, file_ext)
        if preview_path.exists():
            return f"/api/v1/cache/preview/{image_id}.{file_ext}"
        return None

    def get_original_url(self, image_id: int, file_ext: str = "jpg") -> str:
        original_path = self.get_original_path(image_id, file_ext)
        if original_path.exists():
            return f"/api/v1/cache/original/{image_id}.{file_ext}"
        return None

    def download_preview(self, preview_url: str, image_id: int, file_ext: str = "jpg") -> Path:
        preview_path = self.get_preview_path(image_id, file_ext)
        if preview_path.exists():
            return preview_path

        last_exception = None
        for i in range(config.yande_api.retry):
            try:
                resp = requests.get(preview_url, proxies=get_proxy(), timeout=config.yande_api.timeout)
                resp.raise_for_status()
                self._ensure_dirs()
                preview_path.write_bytes(resp.content)
                return preview_path
            except requests.HTTPError as e:
                last_exception = e
                logger.warning(
                    f"[{i + 1}] HTTP error for preview {image_id}: {e.response.status_code}"
                 )
            except Exception as e:
                last_exception = e
                logger.warning(f"[{i + 1}] Failed to download preview {preview_url}: {e}")

        raise last_exception

    def save_original(
        self, file_url: str, image_id: int, file_ext: str = "jpg"
    ) -> Optional[str]:
        original_path = self.get_original_path(image_id, file_ext)

        if original_path.exists():
            return str(original_path)

        for i in range(config.yande_api.retry):
            last_exception = None
            try:
                resp = requests.get(file_url, proxies=get_proxy(), timeout=config.yande_api.timeout)
                resp.raise_for_status()
                self._ensure_dirs()
                original_path.write_bytes(resp.content)
                return str(original_path)
            except requests.HTTPError as e:
                last_exception = e
                logger.warning(
                    f"[{i + 1}] HTTP error for preview {image_id}: {e.response.status_code}"
                 )     
            except Exception as e:
                last_exception = e
                logger.warning(f"[{i + 1}] Failed to download original {file_url}: {e}")

        if last_exception:
            raise last_exception
        return None

    def check_local_files(
        self, image_id: int, file_ext: str = "jpg"
    ) -> Tuple[bool, bool]:
        preview_exists = self.get_preview_path(image_id, file_ext).exists()
        original_exists = self.get_original_path(image_id, file_ext).exists()
        return preview_exists, original_exists


cache = ImageCache()