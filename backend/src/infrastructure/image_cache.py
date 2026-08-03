import os
from pathlib import Path
from random import uniform
import time
from typing import Optional, Tuple
from functools import wraps

import requests
from loguru import logger

from src.common import config, path_constant
from src.common.utils import configure_proxy_session


def _with_retry_write(method):
    @wraps(method)
    def wrapper(self, url: str, image_id: int, file_ext: str = "jpg") -> Path:
        dest_path = method(self, image_id, file_ext)
        if dest_path.exists():
            return dest_path

        self._ensure_dirs()
        last_exception = None
        action_name = method.__name__.replace("_", " ")

        for attempt in range(config.yande_api.retry):
            try:
                resp = self._session.get(url)
                resp.raise_for_status()
                dest_path.write_bytes(resp.content)
                return dest_path
            except requests.RequestException as e:
                last_exception = e
                logger.warning(
                    f"[{attempt + 1}] {action_name} failed for {image_id}: {e}"
                )
                jitter = uniform(0.5, 1.5)
                time.sleep(jitter)
        raise last_exception

    return wrapper


class ImageCache:
    def __init__(self):
        self.PREVIEWS_DIR = path_constant.previews_dir
        self.ORIGINALS_DIR = path_constant.originals_dir

        self._session = configure_proxy_session(requests.Session())
        self._session.timeout = config.yande_api.timeout

    def _ensure_dirs(self):
        self.PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)
        self.ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)

    def get_preview_path(self, image_id: int, file_ext: str = "jpg") -> Path:
        return self.PREVIEWS_DIR / f"{image_id}.{file_ext}"

    def get_original_path(self, image_id: int, file_ext: str = "jpg") -> Path:
        return self.ORIGINALS_DIR / f"{image_id}.{file_ext}"

    def get_preview_url(self, image_id: int, file_ext: str = "jpg") -> str | None:
        preview_path = self.get_preview_path(image_id, file_ext)
        if preview_path.exists():
            return f"/api/v1/cache/preview/{image_id}.{file_ext}"
        return None

    def get_original_url(self, image_id: int, file_ext: str = "jpg") -> str | None:
        original_path = self.get_original_path(image_id, file_ext)
        if original_path.exists():
            return f"/api/v1/cache/original/{image_id}.{file_ext}"
        return None

    @_with_retry_write
    def download_preview(
        self, image_id: int, file_ext: str = "jpg"
    ) -> Path:
        return self.get_preview_path(image_id, file_ext)

    @_with_retry_write
    def download_original(
        self, image_id: int, file_ext: str = "jpg"
    ) -> Path:
        return self.get_original_path(image_id, file_ext)

    def check_local_files(
        self, image_id: int, file_ext: str = "jpg"
    ) -> Tuple[bool, bool]:
        preview_exists = self.get_preview_path(image_id, file_ext).exists()
        original_exists = self.get_original_path(image_id, file_ext).exists()
        return preview_exists, original_exists

    def list_preview_files(self) -> list[Path]:
        """列出 previews/ 下所有非隐藏文件（用 os.scandir 性能更好）"""
        if not self.PREVIEWS_DIR.exists():
            return []
        return [
            Path(entry.path)
            for entry in os.scandir(self.PREVIEWS_DIR)
            if entry.is_file() and not entry.name.startswith(".")
        ]

    def safe_unlink(self, path: Path) -> bool:
        """安全删除单个文件，失败返回 False 不抛异常"""
        try:
            if path.exists():
                path.unlink()
            return True
        except OSError as e:
            logger.warning(f"Failed to unlink {path}: {e}")
            return False