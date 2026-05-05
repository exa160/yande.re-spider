from pathlib import Path
from random import random
import time
from typing import Optional, Tuple

import requests
from loguru import logger

from src.common import config, path_constant
from src.common.utils import get_proxy


class ImageCache:
    def __init__(self):
        self.PREVIEWS_DIR = path_constant.previews_dir
        self.ORIGINALS_DIR = path_constant.originals_dir

        self._session = requests.Session()
        self._session.proxies = get_proxy()   # 需要在 get_proxy() 返回字典
        self._session.timeout = config.yande_api.timeout

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

        # self._ensure_dirs()
        for attempt in range(config.yande_api.retry):
            try:
                resp = self._session.get(preview_url)
                resp.raise_for_status()
                preview_path.write_bytes(resp.content)
                return preview_path
            except requests.RequestException as e:
                last_exception = e
                logger.warning(f"[{attempt + 1}] Failed to download preview {image_id}: {e}")
                jitter = random.uniform(0.5, 1.5)
                time.sleep(jitter)
        else:
            raise last_exception

    def save_original(
        self, file_url: str, image_id: int, file_ext: str = "jpg"
    ) -> Optional[Path]:
        original_path = self.get_original_path(image_id, file_ext)

        if original_path.exists():
            return original_path
        # self._ensure_dirs()
        for attempt in range(config.yande_api.retry):
            last_exception = None
            try:
                resp = self._session.get(file_url)
                resp.raise_for_status()
                original_path.write_bytes(resp.content)
                return original_path
            except requests.RequestException as e:
                last_exception = e
                logger.warning(f"[{attempt + 1}] Failed to download original {image_id}: {e}")
                jitter = random.uniform(0.5, 1.5)
                time.sleep(jitter)
        else:
            raise last_exception

    def check_local_files(
        self, image_id: int, file_ext: str = "jpg"
    ) -> Tuple[bool, bool]:
        preview_exists = self.get_preview_path(image_id, file_ext).exists()
        original_exists = self.get_original_path(image_id, file_ext).exists()
        return preview_exists, original_exists


cache = ImageCache()