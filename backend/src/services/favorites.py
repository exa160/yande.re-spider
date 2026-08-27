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


def _preview_count_for_local_count(local_count: int, tile_size: str = "adaptive") -> int:
    if tile_size == "small":
        return 4
    if tile_size == "medium":
        return 6
    if tile_size == "large":
        return 8
    # adaptive：前端按 tile 宽度像素裁剪，后端统一返 8 张作为上限
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
        page: int = 1,
        page_size: int = 20,
        tile_size: str = "adaptive",
        keyword: Optional[str] = None,
        preview_order: str = "random",
        include_online: bool = False,
    ) -> tuple[list[FavoriteFolderWithMinimalPreview], int, bool]:
        """分页获取收藏夹及精简预览元数据（瀑布流视图）。

        Args:
            page: 页码，从 1 开始
            page_size: 每页数量
            tile_size: 'adaptive' 永远返 8 张（前端按 tile 宽度像素裁剪 4/6/8 张）；
                        'small/medium/large' 固定 4/6/8 张
            keyword: 关键字过滤，按 folder.name / folder.tags 模糊匹配（不区分大小写）
            preview_order: 预览图顺序。
                - 'random'（默认）：随机抽样
                - 'desc'      ：按 ID 倒序（最新优先）
                - 'asc'       ：按 ID 正序（最早优先）
            include_online: True 时预览图同时包含未下载的在线图片（未来「我的最爱」
                            支持收藏未下载图时启用；启用后前端预览加载走
                            /cache/preview → /local → /fetch 的 fallback chain）。

        性能要点（v1 旧实现的 N+1 已修复）：
        - 旧实现：每个 folder 新开一个 session，调 query_random_for_tags → func.random() 在
          大表上 O(n) 排序，一页 20 个 folder = 20 次慢查询 + 20 次 session open/close。
        - 新实现：单次会话遍历所有 folder，每 folder 用 ORDER BY id + LIMIT（命中索引），
          random 模式才走 func.random()（按需）。
        - 跨 folder 的 tags 字符串可能重复（多个 folder 引用同一组 tags），用 LRU 缓存复用
          query 结果，避免同一查询重复跑。
        """
        # 1. 关键字过滤（在 DAO 层做，避免 N 个 folder 都被加载后过滤）
        if keyword:
            folders, total = favorite_dao.search_paginated(
                page=page, page_size=page_size, keyword=keyword
            )
        else:
            folders, total = favorite_dao.list_paginated(
                page=page, page_size=page_size
            )
        if not folders:
            return [], total, False

        # 2. 共享一个 repo session，遍历所有 folder 收集预览元数据
        items: list[FavoriteFolderWithMinimalPreview] = []
        # 缓存同 tags 字符串的查询结果（多 folder 共享时复用）
        # cache_key 加 include_online 维度，因为相同 tags 在不同 include_online 下结果不同
        tags_query_cache: dict[str, list[FolderPreviewImageMinimal]] = {}
        with YandeDataRepository() as repo:
            for f in folders:
                limit = _preview_count_for_local_count(
                    f.local_count or 0, tile_size
                )
                preview_meta: list[FolderPreviewImageMinimal] = []
                if f.tags and limit > 0:
                    cache_key = f"{f.tags}|{limit}|{preview_order}|{include_online}"
                    if cache_key not in tags_query_cache:
                        sampled = repo.query_preview_for_tags(
                            tags=f.tags,
                            limit=limit,
                            downloaded_only=not include_online,
                            order=preview_order,
                        )
                        tags_query_cache[cache_key] = [
                            FolderPreviewImageMinimal.model_validate(img)
                            for img in sampled
                        ]
                    preview_meta = tags_query_cache[cache_key]
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
