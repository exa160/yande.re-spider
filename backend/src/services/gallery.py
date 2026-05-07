"""
图库业务逻辑层
"""

from typing import List, Optional

import requests
from loguru import logger
from PIL import Image


from src.common.constant import ErrMsg
from src.common.constant import path_constant
from src.dao.yande_data_dao import YandeDataRepository
from src.infrastructure.image_cache import ImageCache
from src.infrastructure.yande_api import YandeApi
from src.middleware.errors import APIException
from src.models.database.yande import YandeData
from src.models.request.gallery import GalleryLoadRequest
from src.models.yande import YandeSearchTags


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

        success, yande_data = yande_api.get_ranking(
            query_params=YandeApi.PostRankQueryParams(
                page=params.page,
                limit=params.page_size,
                tags=params.tags,
                search_tags=search_tags
            )
        )

        if not success:
            raise APIException(message=yande_data.reason, e=yande_data)

        yande_items = list(yande_data.root)
        if not yande_items:
            return [], 0

        with YandeDataRepository() as repo:
            # 批量 upsert（一次数据库操作），并返回当前记录的 down_flag
            down_flags = repo.upsert_batch_with_down_flags(yande_data.model_dump())
            if not down_flags:
                logger.warning(f"Upsert batch returned no down_flag data, data may not be saved")
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
    def fetch_and_cache_preview(image_id: int, file_ext: str = "jpg"):
        """
        从远程获取并缓存预览图,如果本地已存在则直接返回(默认jpg格式，有修改需适配preview_url)

        Args:
            image_id: 图片 ID
            file_ext: 文件扩展名

        Returns:
            预览图路径，失败抛出 APIException

        Raises:
            APIException: 获取或缓存失败时抛出
        """

        cache = ImageCache()
        preview_path = cache.get_preview_path(image_id, file_ext)

        if preview_path.exists():
            return preview_path

        with YandeDataRepository() as repo:
            image_data = repo.get_by_id(image_id)

        if not image_data:
            logger.warning(f"Image {image_id} not found in database")
            raise APIException(ErrMsg.NOT_FOUND, data={"image_id": image_id})

        preview_url = image_data.get("preview_url")
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
    def get_preview_for_local(image_id: int, file_ext: str = None):
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
