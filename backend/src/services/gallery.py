"""
图库业务逻辑层
"""

import time
from typing import List, Optional

import requests
from loguru import logger
from PIL import Image


from src.common.constant import CleanupMode
from src.common.constant import ErrMsg
from src.common.constant import path_constant
from src.common.utils import get_error_type_from_exception
from src.dao.yande_data_dao import YandeDataRepository
from src.infrastructure.image_cache import ImageCache
from src.infrastructure.yande_api import YandeApi
from src.middleware.errors import APIException
from src.models.database.yande import YandeData
from src.models.request.gallery import GalleryLoadRequest
from src.models.request.yande import YandeSearchTags


class GalleryService:
    """图库服务类"""

    @staticmethod
    def query_local_database(params: GalleryLoadRequest) -> tuple[List[YandeData], int]:
        """
        查询本地数据库

        Args:
            params: 查询参数字典

        Returns:
            (图片列表, 总数)
        """
        with YandeDataRepository() as repo:
            repo.YandeDataQueryParams.model_validate(params)
            images, total = repo.query(
                query_params=params,
                downloaded_only=True,
            )
        return images, total

    @staticmethod
    def query_yande_api(params: GalleryLoadRequest) -> tuple[List[dict], int]:
        """
        查询 yande.re API 并同步到本地数据库

        Args:
            params: 查询参数字典

        Returns:
            (图片列表, 总数)
        """
        yande_api = YandeApi()
        search_tags = YandeSearchTags.model_validate(params)

        try:
            yande_data = yande_api.get_ranking(
                query_params=YandeApi.PostRankQueryParams(
                    page=params.page,
                    limit=params.page_size,
                    tags=params.tags,
                    search_tags=search_tags
                )
            )
        except requests.RequestException as e:
            err_msg, detail = get_error_type_from_exception(e)
            raise APIException(err_msg=err_msg, data={"detail": detail})

        yande_items = list(yande_data.root)
        if not yande_items:
            return [], 0

        with YandeDataRepository() as repo:
            # 批量 upsert（一次数据库操作），并返回当前记录的 down_flag
            down_flags = repo.upsert_batch_with_down_flags(yande_data.model_dump())
        return down_flags, len(down_flags)

    @staticmethod
    def get_image_by_id(image_id: int, source: str = "local") -> Optional[dict]:
        """
        根据 ID 获取图片详情

        Args:
            image_id: 图片 ID
            source: 数据源 (local/yande)

        Returns:
            图片信息字典，不存在返回 None
        """
        if source == "local":
            images, _ = GalleryService.query_local_database({"page": 1, "page_size": 1})
        else:
            images, _ = GalleryService.query_yande_api({"page": 1, "page_size": 100})

        for img in images:
            if img["id"] == image_id:
                return img
        return None

    @staticmethod
    def get_statistics(source: str = "local") -> dict:
        """
        获取图库统计信息

        Args:
            source: 数据源 (local/yande)

        Returns:
            统计信息字典
        """
        if source == "local":
            images, total = GalleryService.query_local_database(
                {"page": 1, "page_size": 10000}
            )
            downloaded = total
        else:
            images = []
            total = 0
            downloaded = 0

        rating_distribution = {"Safe": 0, "Questionable": 0, "Explicit": 0}
        for img in images:
            rating = img.get("rating", "Safe")
            if rating in rating_distribution:
                rating_distribution[rating] += 1

        return {
            "total_images": total,
            "downloaded_images": downloaded,
            "rating_distribution": rating_distribution,
            "file_type_distribution": {},
        }

    @staticmethod
    def get_preview_path(filename: str):
        """获取预览图路径"""
        return path_constant.previews_dir / filename

    @staticmethod
    def get_original_path(filename: str):
        """获取原图路径"""
        return path_constant.originals_dir / filename

    @staticmethod
    def generate_preview(image_id: int, file_ext: str = "jpg"):
        cache = ImageCache()
        preview_path = cache.get_preview_path(image_id, "jpg")

        if preview_path.exists():
            return preview_path

        original_path = cache.get_original_path(image_id, file_ext)
        if not original_path.exists():
            logger.warning(f"Original image {image_id} not found for preview generation")
            return None

        try:
            img = Image.open(str(original_path))
            img.thumbnail(
                (600, 600), Image.Resampling.LANCZOS
            )
            if img.mode == "RGBA":
                img = img.convert("RGB")
            img.save(str(preview_path), "JPEG", quality=85)
            return preview_path if preview_path.exists() else None
        except Exception:
            logger.error(f"Failed to generate preview for image {image_id}", exc_info=True)
            return None

    @staticmethod
    def fetch_and_cache_preview(image_id: int):
        """
        从远程获取并缓存预览图,如果本地已存在则直接返回(默认jpg格式，有修改需适配preview_url)

        Args:
            image_id: 图片 ID

        Returns:
            预览图路径，失败抛出 APIException

        Raises:
            APIException: 获取或缓存失败时抛出
        """

        cache = ImageCache()
        preview_path = cache.get_preview_path(image_id, "jpg")

        if preview_path.exists():
            return preview_path

        with YandeDataRepository() as repo:
            image_data = repo.get_by_id(image_id)

        if not image_data:
            logger.warning(f"Image {image_id} not found in database")
            raise APIException(ErrMsg.NOT_FOUND, data={"image_id": image_id})

        preview_url = image_data.preview_url
        if not preview_url:
            logger.warning(f"Image {image_id} has no preview_url")
            raise APIException(ErrMsg.LOAD_PREVIEW_DATA_ERROR, e=Exception(f"ID: {image_id} has no preview URL available"))

        try:
            return cache.download_preview(preview_url, image_id, "jpg")
        except requests.RequestException as e:
            logger.error(f"Request error for image {image_id}: {e}")
            raise APIException(ErrMsg.LOAD_PREVIEW_DATA_ERROR, e=e)
        except IOError as e:
            logger.error(f"IO error saving preview {image_id}: {e}")
            raise APIException(ErrMsg.SAVE_PREVIEW_DATA_ERROR, e=e)
        except Exception as e:
            logger.error(f"Unexpected error fetching preview {image_id}: {e}")
            raise APIException(ErrMsg.LOAD_PREVIEW_DATA_ERROR, e=e)

    @staticmethod
    def get_preview_for_local(image_id: int):
        cache = ImageCache()
        preview_path = cache.get_preview_path(image_id, "jpg")

        if preview_path.exists():
            return preview_path

        with YandeDataRepository() as repo:
            actual_file_ext = repo.get_file_ext(image_id)

        original_path = cache.get_original_path(image_id, actual_file_ext)
        if original_path.exists():
            return GalleryService.generate_preview(image_id, actual_file_ext)

        return None

    @staticmethod
    def cleanup_previews(mode: CleanupMode, dry_run: bool) -> dict:
        """清理 preview 缩略图

        Args:
            mode: 清理模式（CLEAN_LOCAL_PREVIEWS 仅删 down_flag=True 的；
                  CLEAN_ALL_PREVIEWS 清空整个 previews/ 目录）
            dry_run: True 仅评估不删除，False 实际删除

        Returns:
            dict: 包含 mode / dry_run / matched / deleted / failed /
                  total_bytes / duration_ms 的结果

        Raises:
            APIException: 数据库查询失败时（仅 CLEAN_LOCAL_PREVIEWS 模式）
        """
        cache = ImageCache()
        previews_dir = path_constant.previews_dir
        start = time.monotonic()

        if not previews_dir.exists():
            return _empty_cleanup_result(mode, dry_run)

        all_previews = cache.list_preview_files()

        if mode == CleanupMode.CLEAN_LOCAL_PREVIEWS:
            try:
                with YandeDataRepository() as repo:
                    downloaded_ids = repo.get_downloaded_ids()
            except Exception as e:
                raise APIException(ErrMsg.QUERY_ERROR, e=e)

            targets = []
            for p in all_previews:
                image_id = GalleryService._parse_image_id(p.name)
                if image_id is not None and image_id in downloaded_ids:
                    targets.append(p)
        else:
            targets = all_previews

        matched = len(targets)
        total_bytes = 0
        for p in targets:
            try:
                total_bytes += p.stat().st_size
            except OSError:
                continue

        deleted, failed = 0, 0
        if not dry_run:
            for p in targets:
                if cache.safe_unlink(p):
                    deleted += 1
                else:
                    failed += 1

        duration_ms = int((time.monotonic() - start) * 1000)
        return {
            "mode": mode.value,
            "dry_run": dry_run,
            "matched": matched,
            "deleted": deleted,
            "failed": failed,
            "total_bytes": total_bytes,
            "duration_ms": duration_ms,
        }

    @staticmethod
    def _parse_image_id(filename: str) -> Optional[int]:
        """从 preview 文件名解析 image_id。约定：{id}.{ext}"""
        if filename.startswith("."):
            return None
        stem = filename.rsplit(".", 1)[0] if "." in filename else filename
        try:
            return int(stem)
        except ValueError:
            return None


def _empty_cleanup_result(mode: CleanupMode, dry_run: bool) -> dict:
    """previews 目录不存在时的零结果"""
    return {
        "mode": mode.value,
        "dry_run": dry_run,
        "matched": 0,
        "deleted": 0,
        "failed": 0,
        "total_bytes": 0,
        "duration_ms": 0,
    }
