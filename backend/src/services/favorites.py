"""
收藏夹业务逻辑层
"""

from datetime import datetime
from typing import List, Optional

from loguru import logger

from src.common.constant import ErrMsg, Rating
from src.dao.favorite_dao import favorite_dao
from src.dao.yande_data_dao import YandeDataRepository, SortBy
from src.infrastructure.scheduler import schedule_manager
from src.infrastructure.yande_api import YandeApi
from src.middleware.errors import APIException
from src.models.request.favorites import (
    FavoriteFolderCreate,
    FavoriteFolderUpdate,
)
from src.models.response.favorites import (
    FavoriteFolder,
    FavoriteFolderWithMinimalPreview,
    FolderPreviewImageMinimal,
)


# 瀑布流预览图数量分档：(local_count 上限, 预览张数)
PREVIEW_COUNT_BY_LOCAL_THRESHOLDS = [
    (50, 4),
    (200, 6),
    (float("inf"), 8),
]


def _preview_count_for_local_count(local_count: int) -> int:
    for threshold, count in PREVIEW_COUNT_BY_LOCAL_THRESHOLDS:
        if (local_count or 0) < threshold:
            return count
    return 8


class FavoritesService:
    """收藏夹服务类"""

    @staticmethod
    def _sync_schedule(folder, strict: bool = False) -> None:
        if folder.schedule_enabled and folder.schedule_cron:
            try:
                schedule_manager.register_folder(
                    folder_id=folder.id,
                    cron=folder.schedule_cron,
                    mode=folder.schedule_mode or "last_id",
                    max_images=folder.schedule_max_images,
                )
            except ValueError as e:
                if strict:
                    raise
                logger.warning(f"Failed to register schedule for folder {folder.id}: {e}")
        else:
            schedule_manager.unregister_folder(folder.id)

    @staticmethod
    def get_all_folders() -> List[FavoriteFolder]:
        """获取所有收藏夹"""
        folders = favorite_dao.get_all()
        return folders

    @staticmethod
    def get_folders_with_preview(
        page: int = 1, page_size: int = 20
    ) -> tuple[list[FavoriteFolderWithMinimalPreview], int, bool]:
        """分页获取收藏夹及精简预览元数据（瀑布流视图）。"""
        folders, total = favorite_dao.list_paginated(page=page, page_size=page_size)
        items: list[FavoriteFolderWithMinimalPreview] = []
        for f in folders:
            limit = _preview_count_for_local_count(f.local_count or 0)
            preview_meta: list[FolderPreviewImageMinimal] = []
            if f.tags:
                with YandeDataRepository() as repo:
                    sampled = repo.query_random_for_tags(
                        tags=f.tags, limit=limit, downloaded_only=True
                    )
                preview_meta = [
                    FolderPreviewImageMinimal.model_validate(img)
                    for img in sampled
                ]
            items.append(
                FavoriteFolderWithMinimalPreview(
                    **FavoriteFolder.model_validate(f).model_dump(),
                    preview_images=preview_meta,
                )
            )
        has_more = page * page_size < total
        return items, total, has_more

    @staticmethod
    def create_folder(folder: FavoriteFolderCreate) -> FavoriteFolder:
        """创建收藏夹"""
        count = favorite_dao.count()
        new_folder = favorite_dao.create(
            name=folder.name,
            tags=folder.tags,
            color=folder.color,
            icon=folder.icon,
            sort_order=folder.sort_order if folder.sort_order else count,
            schedule_enabled=folder.schedule_enabled,
            schedule_cron=folder.schedule_cron,
            schedule_mode=folder.schedule_mode,
            schedule_max_images=folder.schedule_max_images,
        )

        new_folder = FavoritesService._refresh_local_count(new_folder.id)
        FavoritesService._sync_schedule(new_folder)
        return FavoriteFolder.model_validate(new_folder)

    @staticmethod
    def get_folder(folder_id: int) -> Optional[FavoriteFolder]:
        """获取收藏夹详情"""
        folder = FavoritesService._refresh_local_count(folder_id)
        if folder is None:
            return None
        return FavoriteFolder.model_validate(folder)

    @staticmethod
    def update_folder(
        folder_id: int, folder: FavoriteFolderUpdate
    ) -> Optional[FavoriteFolder]:
        """更新收藏夹"""
        update_data = folder.model_dump(exclude_unset=True)
        updated = favorite_dao.update(folder_id, **update_data)
        if not updated:
            return None

        if "tags" in update_data:
            FavoritesService._refresh_local_count(folder_id)

        updated = favorite_dao.get_by_id(folder_id)
        schedule_fields_changed = bool(
            set(update_data) & {"schedule_enabled", "schedule_cron", "schedule_mode", "schedule_max_images"}
        )
        FavoritesService._sync_schedule(updated, strict=schedule_fields_changed)
        return FavoriteFolder.model_validate(updated)

    @staticmethod
    def delete_folder(folder_id: int) -> bool:
        """删除收藏夹"""
        schedule_manager.unregister_folder(folder_id)
        return favorite_dao.delete(folder_id)

    @staticmethod
    def reorder_folders(folder_ids: List[int]) -> bool:
        """批量更新排序"""
        return favorite_dao.reorder(folder_ids)

    @staticmethod
    def preview_folder(
        folder_id: int, limit: int = 6, random: bool = False
    ) -> Optional[dict]:
        """单文件夹预览。

        Args:
            folder_id: 收藏夹 ID
            limit: 预览图数量上限
            random: True 时随机抽样；False 时按当前 sort 排序取前 N 张
        """
        folder = favorite_dao.get_by_id(folder_id)
        if not folder:
            return None

        try:
            search_params = FavoritesService._parse_tags_to_params(folder.tags)
            search_params.page = 1
            search_params.page_size = limit
            with YandeDataRepository() as repo:
                if random:
                    images = repo.query_random_for_tags(
                        tags=folder.tags or "",
                        limit=limit,
                        downloaded_only=True,
                    )
                    _, total = repo.query(
                        query_params=search_params, downloaded_only=True
                    )
                else:
                    images, total = repo.query(
                        query_params=search_params, downloaded_only=True
                    )
            FavoritesService._refresh_local_count(folder_id)
            return {"total": total, "preview_images": images[:limit]}
        except Exception:
            return None

    @staticmethod
    def update_online_count(folder_id: int, count: int) -> bool:
        """更新在线数量"""
        folder = favorite_dao.get_by_id(folder_id)
        if not folder:
            return False

        favorite_dao.update(folder_id, online_count=count, last_refresh=datetime.now())
        return True

    @staticmethod
    def refresh_online_count(folder_id: int) -> Optional[int]:
        """从 yande.re XML API 刷新在线数量"""
        folder = favorite_dao.get_by_id(folder_id)
        if not folder:
            return None

        yande_api = YandeApi()
        count = yande_api.get_count(folder.tags or "")

        if count < 0:
            return None

        favorite_dao.update(folder_id, online_count=count, last_refresh=datetime.now())
        return count

    @staticmethod
    def update_local_count(folder_id: int, count: int) -> bool:
        """更新本地数量"""
        folder = favorite_dao.get_by_id(folder_id)
        if not folder:
            return False

        favorite_dao.update(folder_id, local_count=count, last_refresh=datetime.now())
        return True

    @staticmethod
    def _refresh_local_count(folder_id: int):
        """刷新收藏夹的本地图片数量"""
        folder = favorite_dao.get_by_id(folder_id)
        if not folder:
            return None
        try:
            search_params = FavoritesService._parse_tags_to_params(folder.tags)
            search_params.page = 1
            search_params.page_size = 1
            with YandeDataRepository() as repo:
                _, total = repo.query(
                    query_params=search_params,
                    downloaded_only=True,
                )
            folder = favorite_dao.update(
                folder_id, local_count=total, last_refresh=datetime.now()
            )
            return folder
        except Exception as e:
            folder = favorite_dao.update(folder_id, last_refresh=datetime.now())
            raise APIException[FavoriteFolder](err_msg=ErrMsg.REFRESH_LOCAL_COUNT_FAILED, data=folder, e=e)

    @staticmethod
    def _parse_tags_to_params(tags_str: str) -> YandeDataRepository.YandeDataQueryParams:
        """
        解析标签字符串为查询参数
        TODO 与生成tag的代码有重复
        TODO -排除功能
        """
        params = YandeDataRepository.YandeDataQueryParams()

        if not tags_str:
            return params

        tags_list = []
        parts = tags_str.split()
        for part in parts:
            if part.startswith("rating:"):
                rating_str = part.split(":", 1)[1]
                if not params.rating:
                    params.rating = []
                params.rating.append(Rating(rating_str))
            elif part.startswith("order:"):
                order = part.split(":", 1)[-1]
                params.sort_by = order.split("_")[0]
                params.sort_order = order.split("_")[1] if "_" in order else "desc"
            elif part.startswith("width:>="):
                width = part.split(":", 1)[1]
                params.min_width = int(width)
            elif part.startswith("width:<="):
                width = part.split(":", 1)[1]
                params.max_width = int(width)
            elif part.startswith("height:>="):
                height = part.split(":", 1)[1]
                params.min_height = int(height)
            elif part.startswith("height:<="):
                height = part.split(":", 1)[1]
                params.max_height = int(height)
            elif part.startswith("ext:"):
                ext = part.split(":", 1)[1]
                params.file_types = [ext]
            elif not part.startswith("-"):
                tags_list.append(part)

        if tags_list:
            params.tags = " ".join(tags_list)

        return params
