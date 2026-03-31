import os
import hashlib
import requests
from pathlib import Path
from typing import Optional, Tuple


class ImageCache:
    DOWNLOADS_DIR = Path(__file__).parent.parent.parent / "downloads"
    PREVIEWS_DIR = DOWNLOADS_DIR / "previews"
    ORIGINALS_DIR = DOWNLOADS_DIR / "originals"

    def __init__(self):
        self.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        self.PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)
        self.ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)

    def get_preview_path(self, image_id: int, file_ext: str = "jpg") -> str:
        return str(self.PREVIEWS_DIR / f"{image_id}.{file_ext}")

    def get_original_path(self, image_id: int, file_ext: str = "jpg") -> str:
        return str(self.ORIGINALS_DIR / f"{image_id}.{file_ext}")

    def get_preview_url(self, image_id: int, file_ext: str = "jpg") -> str:
        preview_path = self.get_preview_path(image_id, file_ext)
        if os.path.exists(preview_path):
            return f"/api/v1/cache/preview/{image_id}.{file_ext}"
        return None

    def get_original_url(self, image_id: int, file_ext: str = "jpg") -> str:
        original_path = self.get_original_path(image_id, file_ext)
        if os.path.exists(original_path):
            return f"/api/v1/cache/original/{image_id}.{file_ext}"
        return None

    def download_preview(
        self, preview_url: str, image_id: int, file_ext: str = "jpg"
    ) -> Optional[str]:
        preview_path = self.get_preview_path(image_id, file_ext)

        if os.path.exists(preview_path):
            return preview_path

        try:
            resp = requests.get(preview_url, proxies=current_proxy(), timeout=10)
            if resp.status_code == 200:
                with open(preview_path, "wb") as f:
                    f.write(resp.content)
                return preview_path
        except Exception as e:
            print(f"Failed to download preview {preview_url}: {e}")

        return None

    def save_original(
        self, file_url: str, image_id: int, file_ext: str = "jpg"
    ) -> Optional[str]:
        original_path = self.get_original_path(image_id, file_ext)

        if os.path.exists(original_path):
            return original_path

        try:
            resp = requests.get(file_url, proxies=current_proxy(), timeout=30)
            if resp.status_code == 200:
                with open(original_path, "wb") as f:
                    f.write(resp.content)
                return original_path
        except Exception as e:
            print(f"Failed to download original {file_url}: {e}")

        return None

    def check_local_files(
        self, image_id: int, file_ext: str = "jpg"
    ) -> Tuple[bool, bool]:
        preview_exists = os.path.exists(self.get_preview_path(image_id, file_ext))
        original_exists = os.path.exists(self.get_original_path(image_id, file_ext))
        return preview_exists, original_exists


def current_proxy() -> Optional[dict]:
    from backend.config.settings import config

    if config.yande_api.proxies:
        return config.yande_api.proxies
    return None


cache = ImageCache()
