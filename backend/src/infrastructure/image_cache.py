import os
import requests
from pathlib import Path
from typing import Optional, Tuple

from src.common import config, path_constant


class ImageCache:
    def __init__(self):
        self.DOWNLOADS_DIR = path_constant.download_dir
        self.PREVIEWS_DIR = path_constant.previews_dir
        self.ORIGINALS_DIR = path_constant.originals_dir

    def _ensure_dirs(self):
        self.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
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

    def download_preview(
        self, preview_url: str, image_id: int, file_ext: str = "jpg"
    ) -> Optional[str]:
        preview_path = self.get_preview_path(image_id, file_ext)

        if preview_path.exists():
            return str(preview_path)

        try:
            resp = requests.get(preview_url, proxies=self._get_proxy(), timeout=10)
            if resp.status_code == 200:
                self._ensure_dirs()
                with open(preview_path, "wb") as f:
                    f.write(resp.content)
                return str(preview_path)
        except Exception as e:
            print(f"Failed to download preview {preview_url}: {e}")

        return None

    def save_original(
        self, file_url: str, image_id: int, file_ext: str = "jpg"
    ) -> Optional[str]:
        original_path = self.get_original_path(image_id, file_ext)

        if original_path.exists():
            return str(original_path)

        try:
            resp = requests.get(file_url, proxies=self._get_proxy(), timeout=30)
            if resp.status_code == 200:
                self._ensure_dirs()
                with open(original_path, "wb") as f:
                    f.write(resp.content)
                return str(original_path)
        except Exception as e:
            print(f"Failed to download original {file_url}: {e}")

        return None

    def check_local_files(
        self, image_id: int, file_ext: str = "jpg"
    ) -> Tuple[bool, bool]:
        preview_exists = self.get_preview_path(image_id, file_ext).exists()
        original_exists = self.get_original_path(image_id, file_ext).exists()
        return preview_exists, original_exists

    def _get_proxy(self) -> Optional[dict]:
        if config.yande_api.proxies:
            return config.yande_api.proxies
        return None


cache = ImageCache()